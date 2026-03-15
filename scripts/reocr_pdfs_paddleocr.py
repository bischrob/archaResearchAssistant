#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import inspect
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.path_utils import resolve_input_path


@dataclass
class FileResult:
    pdf: str
    status: str
    pages: int = 0
    lines: int = 0
    error: str = ""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_args() -> argparse.Namespace:
    default_pdf_dir = os.getenv("PDF_SOURCE_DIR", r"\\192.168.0.37\pooled\media\Books\pdfs").strip()
    parser = argparse.ArgumentParser(
        description="Re-OCR PDFs with PaddleOCR (classic or VL) and persist per-PDF outputs."
    )
    parser.add_argument("--pdf-dir", default=default_pdf_dir, help="Directory containing input PDFs.")
    parser.add_argument(
        "--output-dir",
        default="data/ocr/paddleocr",
        help="Root output directory for OCR artifacts.",
    )
    parser.add_argument(
        "--summary-dir",
        default="data/ocr/paddleocr/summaries",
        help="Directory for per-task summary JSON files.",
    )
    parser.add_argument(
        "--task-id",
        type=int,
        default=None,
        help="Current shard index (0-based). Defaults to SLURM_ARRAY_TASK_ID or 0.",
    )
    parser.add_argument(
        "--num-tasks",
        type=int,
        default=None,
        help="Total shard count. Defaults to SLURM array size or 1.",
    )
    parser.add_argument(
        "--lang",
        default="en",
        help="PaddleOCR language code (classic backend only).",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        choices=["cpu", "gpu", "auto"],
        help="Inference device preference.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-run OCR even when output files already exist.",
    )
    parser.add_argument(
        "--backend",
        default="paddleocr-vl",
        choices=["paddleocr-vl", "paddleocr-classic"],
        help="OCR backend. `paddleocr-vl` uses PaddleOCRVL doc parser.",
    )
    parser.add_argument(
        "--vl-model-dir",
        default=os.getenv("PADDLEOCR_VL_MODEL_DIR", "").strip(),
        help="Local model directory for PaddleOCR-VL (e.g. /scratch/.../PaddleOCR-VL-1.5).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional cap on PDFs processed by this task (0 means no cap).",
    )
    return parser.parse_args()


def _resolve_tasking(args: argparse.Namespace) -> tuple[int, int]:
    env_task_id = int(os.getenv("SLURM_ARRAY_TASK_ID", "0"))
    env_task_count = (
        int(os.getenv("SLURM_ARRAY_TASK_COUNT", "0"))
        or int(os.getenv("SLURM_ARRAY_TASK_MAX", "0")) + 1
    )
    task_id = env_task_id if args.task_id is None else int(args.task_id)
    num_tasks = env_task_count if args.num_tasks is None else int(args.num_tasks)
    num_tasks = max(1, num_tasks)
    if task_id < 0 or task_id >= num_tasks:
        raise ValueError(f"Invalid tasking: task_id={task_id}, num_tasks={num_tasks}")
    return task_id, num_tasks


def _collect_pdfs(pdf_dir: Path) -> list[Path]:
    return sorted(p for p in pdf_dir.rglob("*.pdf") if p.is_file())


def _extract_lines(page_payload: Any) -> list[str]:
    lines: list[str] = []
    if not isinstance(page_payload, list):
        return lines
    for item in page_payload:
        if not isinstance(item, list) or len(item) < 2:
            continue
        line_payload = item[1]
        if isinstance(line_payload, list) and line_payload:
            text = str(line_payload[0]).strip()
            if text:
                lines.append(text)
    return lines


def _extract_lines_from_predict_item(item: Any) -> list[str]:
    # PaddleOCR 3.x predict() typically exposes a dict-like payload through `.json`.
    if hasattr(item, "json"):
        payload = getattr(item, "json")
    else:
        payload = item
    if not isinstance(payload, dict):
        return []

    inner = payload.get("res") if isinstance(payload.get("res"), dict) else payload
    rec_texts = inner.get("rec_texts")
    if not isinstance(rec_texts, list):
        return []

    lines: list[str] = []
    for value in rec_texts:
        text = str(value).strip()
        if text:
            lines.append(text)
    return lines


def _extract_lines_from_vl_payload(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []

    lines: list[str] = []
    markdown_payload = payload.get("markdown")
    if isinstance(markdown_payload, dict):
        markdown_text = markdown_payload.get("text")
        if isinstance(markdown_text, str) and markdown_text.strip():
            lines.extend(markdown_text.splitlines())

    inner = payload.get("res")
    if isinstance(inner, dict):
        rec_texts = inner.get("rec_texts")
        if isinstance(rec_texts, list):
            for value in rec_texts:
                text = str(value).strip()
                if text:
                    lines.append(text)
    return [line for line in lines if line.strip()]


def _vl_result_payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item

    for attr in ("json", "res"):
        if hasattr(item, attr):
            value = getattr(item, attr)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue
            if isinstance(value, dict):
                return value

    if hasattr(item, "to_dict"):
        try:
            value = item.to_dict()
            if isinstance(value, dict):
                return value
        except Exception:
            pass

    return {"repr": repr(item)}


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _save_text(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(lines).strip()
    if body:
        body += "\n"
    path.write_text(body, encoding="utf-8")


def _should_use_gpu(device: str) -> bool:
    if device == "gpu":
        return True
    if device == "cpu":
        return False
    try:
        import paddle  # type: ignore

        return bool(paddle.device.is_compiled_with_cuda())
    except Exception:
        return False


def _build_vl_pipeline(vl_model_dir: Path, use_gpu: bool) -> Any:
    try:
        from paddleocr import PaddleOCRVL  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Failed to import PaddleOCRVL. Install with: pip install 'paddleocr[doc-parser]' paddlepaddle"
        ) from exc

    if not vl_model_dir.exists():
        raise FileNotFoundError(f"PaddleOCR-VL model directory not found: {vl_model_dir}")

    device = "gpu:0" if use_gpu else "cpu"
    kwargs: dict[str, Any] = {"device": device}

    try:
        sig = inspect.signature(PaddleOCRVL)
        params = set(sig.parameters.keys())
    except Exception:
        params = set()

    if "vl_rec_model_dir" in params:
        kwargs["vl_rec_model_dir"] = str(vl_model_dir)
    elif "model_dir" in params:
        kwargs["model_dir"] = str(vl_model_dir)
    else:
        # Best-effort fallback for older/newer wrappers that still accept this kw.
        kwargs["vl_rec_model_dir"] = str(vl_model_dir)

    if "vl_rec_model_name" in params:
        kwargs["vl_rec_model_name"] = "PaddleOCR-VL-1.5"

    if "pipeline_version" in params:
        kwargs["pipeline_version"] = "v1.5"
    if "use_doc_orientation_classify" in params:
        kwargs["use_doc_orientation_classify"] = False
    if "use_doc_unwarping" in params:
        kwargs["use_doc_unwarping"] = False

    return PaddleOCRVL(**kwargs)


def _build_classic_pipeline(use_gpu: bool, lang: str) -> Any:
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Failed to import PaddleOCR. Install with: pip install paddleocr paddlepaddle"
        ) from exc

    try:
        return PaddleOCR(
            lang=lang,
            device="gpu:0" if use_gpu else "cpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        return PaddleOCR(use_angle_cls=True, lang=lang, use_gpu=use_gpu)


def _run_vl_pdf(pipeline: Any, pdf_path: Path, temp_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    pages_payload: list[dict[str, Any]] = []
    merged_lines: list[str] = []

    with tempfile.TemporaryDirectory(prefix="paddleocr_vl_", dir=str(temp_root)) as temp_dir:
        temp_path = Path(temp_dir)
        md_path = temp_path / "md"
        json_path = temp_path / "json"
        md_path.mkdir(parents=True, exist_ok=True)
        json_path.mkdir(parents=True, exist_ok=True)

        output = pipeline.predict(input=str(pdf_path))
        for item in output:
            payload = _vl_result_payload(item)
            pages_payload.append(payload)
            merged_lines.extend(_extract_lines_from_vl_payload(payload))

            if hasattr(item, "save_to_markdown"):
                try:
                    item.save_to_markdown(save_path=str(md_path))
                except Exception:
                    pass
            if hasattr(item, "save_to_json"):
                try:
                    item.save_to_json(save_path=str(json_path))
                except Exception:
                    pass

        # Fallback: harvest saved markdown files when direct payload extraction is sparse.
        if not merged_lines:
            for md_file in sorted(md_path.rglob("*.md")):
                body = md_file.read_text(encoding="utf-8", errors="ignore")
                if body.strip():
                    merged_lines.extend(body.splitlines())

    return pages_payload, [line for line in merged_lines if line.strip()]


def main() -> int:
    args = _parse_args()
    task_id, num_tasks = _resolve_tasking(args)

    pdf_dir = resolve_input_path(args.pdf_dir).resolve()
    out_root = Path(args.output_dir).resolve()
    summary_dir = Path(args.summary_dir).resolve()
    text_root = out_root / "text"
    raw_root = out_root / "raw"
    temp_root = out_root / ".tmp"
    summary_dir.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)

    if not pdf_dir.exists():
        raise FileNotFoundError(f"PDF directory not found: {pdf_dir}")

    all_pdfs = _collect_pdfs(pdf_dir)
    task_pdfs = [pdf for idx, pdf in enumerate(all_pdfs) if idx % num_tasks == task_id]
    if args.limit > 0:
        task_pdfs = task_pdfs[: int(args.limit)]

    use_gpu = _should_use_gpu(args.device)
    vl_model_dir = Path(args.vl_model_dir).resolve() if args.vl_model_dir else None
    print(
        f"[INFO] task_id={task_id}/{num_tasks} total_pdfs={len(all_pdfs)} shard_pdfs={len(task_pdfs)} "
        f"backend={args.backend} device={'gpu' if use_gpu else 'cpu'}",
        flush=True,
    )
    if args.backend == "paddleocr-vl":
        if vl_model_dir is None:
            raise ValueError(
                "PaddleOCR-VL backend requires --vl-model-dir (or PADDLEOCR_VL_MODEL_DIR)."
            )
        print(f"[INFO] using PaddleOCR-VL model_dir={vl_model_dir}", flush=True)
        pipeline = _build_vl_pipeline(vl_model_dir=vl_model_dir, use_gpu=use_gpu)
    else:
        pipeline = _build_classic_pipeline(use_gpu=use_gpu, lang=args.lang)

    results: list[FileResult] = []
    for index, pdf_path in enumerate(task_pdfs, start=1):
        rel = pdf_path.relative_to(pdf_dir)
        json_path = (raw_root / rel).with_suffix(".json")
        txt_path = (text_root / rel).with_suffix(".txt")

        if not args.overwrite and json_path.exists() and txt_path.exists():
            results.append(FileResult(pdf=str(rel), status="skipped_existing"))
            continue

        try:
            page_lines: list[list[str]]
            pages_payload: list[dict[str, Any]] = []
            if args.backend == "paddleocr-vl":
                pages_payload, merged_lines = _run_vl_pdf(
                    pipeline=pipeline,
                    pdf_path=pdf_path,
                    temp_root=temp_root,
                )
                page_lines = [[] for _ in pages_payload]
            else:
                if hasattr(pipeline, "predict"):
                    predicted: Iterable[Any] = pipeline.predict(str(pdf_path))
                    page_lines = [_extract_lines_from_predict_item(item) for item in predicted]
                else:
                    payload = pipeline.ocr(str(pdf_path), cls=True)
                    pages = payload if isinstance(payload, list) else []
                    page_lines = [_extract_lines(page) for page in pages]
                merged_lines = [line for lines in page_lines for line in lines if line.strip()]

            _save_json(
                json_path,
                {
                    "pdf": str(rel),
                    "generated_at": _utc_now_iso(),
                    "task_id": task_id,
                    "num_tasks": num_tasks,
                    "backend": args.backend,
                    "vl_model_dir": str(vl_model_dir) if vl_model_dir else "",
                    "pages": page_lines if args.backend != "paddleocr-vl" else [],
                    "vl_pages": pages_payload if args.backend == "paddleocr-vl" else [],
                },
            )
            _save_text(txt_path, merged_lines)

            results.append(
                FileResult(
                    pdf=str(rel),
                    status="ok",
                    pages=len(page_lines),
                    lines=len(merged_lines),
                )
            )
        except Exception as exc:
            results.append(
                FileResult(
                    pdf=str(rel),
                    status="failed",
                    error=str(exc),
                )
            )

        if index % 5 == 0 or index == len(task_pdfs):
            done = sum(1 for r in results if r.status in {"ok", "skipped_existing"})
            failed = sum(1 for r in results if r.status == "failed")
            print(
                f"[INFO] task={task_id} progress={index}/{len(task_pdfs)} done={done} failed={failed}",
                flush=True,
            )

    summary_path = summary_dir / f"task_{task_id:04d}.json"
    ok_count = sum(1 for r in results if r.status == "ok")
    skipped_count = sum(1 for r in results if r.status == "skipped_existing")
    failed_items = [r for r in results if r.status == "failed"]
    _save_json(
        summary_path,
        {
            "generated_at": _utc_now_iso(),
            "task_id": task_id,
            "num_tasks": num_tasks,
            "pdf_dir": str(pdf_dir),
            "output_dir": str(out_root),
            "device": "gpu" if use_gpu else "cpu",
            "lang": args.lang,
            "overwrite": bool(args.overwrite),
            "total_seen_in_shard": len(task_pdfs),
            "ok": ok_count,
            "skipped_existing": skipped_count,
            "failed": len(failed_items),
            "failed_items": [r.__dict__ for r in failed_items],
            "results": [r.__dict__ for r in results],
        },
    )
    print(f"[INFO] wrote summary: {summary_path}", flush=True)
    print(
        f"[INFO] shard complete ok={ok_count} skipped={skipped_count} failed={len(failed_items)}",
        flush=True,
    )
    # Cleanup temp material generated by VL save helpers.
    shutil.rmtree(temp_root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
