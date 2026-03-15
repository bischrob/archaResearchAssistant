#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dataclasses import replace

from src.rag.config import Settings
from src.rag.qwen_local import clear_qwen_runtime_cache, decode_qwen_json, generate_with_qwen


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Smoke-evaluate Qwen reference-splitting quality before/after a LoRA adapter. "
            "Default mode uses isolated worker subprocesses with per-row timeouts."
        )
    )
    p.add_argument("--eval-jsonl", default="", help="Evaluation JSONL with split_reference_chunk messages.")
    p.add_argument("--base-model-path", default="", help="Base local Qwen model path.")
    p.add_argument("--adapter-path", default="", help="Optional adapter path for after-model evaluation.")
    p.add_argument("--output-json", default="data/qwen3_reference_audit/smoke_eval_before_after.json")
    p.add_argument("--max-rows", type=int, default=0, help="Optional cap on rows (0 = all).")
    p.add_argument("--timeout-seconds", type=int, default=240, help="Per-row timeout in subprocess mode.")
    p.add_argument("--max-new-tokens", type=int, default=256)
    p.add_argument("--device", default="auto", help="Qwen device (auto/cpu/cuda:0).")
    p.add_argument("--dtype", default="auto", help="Qwen dtype (auto/fp16/bf16/fp32).")
    p.add_argument("--qwen-max-input-chars", type=int, default=12000)
    p.add_argument(
        "--in-process",
        action="store_true",
        help="Run evaluation in one process (faster, less fault-isolated).",
    )

    # Hidden worker flags
    p.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--row-json", default="", help=argparse.SUPPRESS)
    p.add_argument("--model-path", default="", help=argparse.SUPPRESS)
    p.add_argument("--adapter", default="", help=argparse.SUPPRESS)
    return p.parse_args()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _is_marker_only(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    return bool(re.fullmatch(r"(?:\[\d+\]|\d+[.)]?|[A-Za-z]-\d+)", t))


def _canon(text: str) -> str:
    t = _norm(text)
    t = re.sub(r"\bdoi:\s*", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    ratio = difflib.SequenceMatcher(a=a, b=b).ratio()
    at = set(a.split())
    bt = set(b.split())
    jacc = (len(at & bt) / len(at | bt)) if (at and bt) else 0.0
    return max(ratio, jacc)


def _fuzzy_match_count(gold: list[str], pred: list[str], threshold: float = 0.72) -> int:
    g = [_canon(x) for x in gold if _canon(x)]
    p = [_canon(x) for x in pred if _canon(x)]
    used: set[int] = set()
    matches = 0
    for gi in g:
        best_idx = -1
        best_sim = 0.0
        for idx, pj in enumerate(p):
            if idx in used:
                continue
            sim = _similarity(gi, pj)
            if sim > best_sim:
                best_sim = sim
                best_idx = idx
        if best_idx >= 0 and best_sim >= threshold:
            used.add(best_idx)
            matches += 1
    return matches


def _refs_from_payload(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        payload = payload.get("references")
    out: list[str] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                t = item.strip()
            elif isinstance(item, dict):
                t = str(item.get("text") or item.get("reference") or item.get("raw") or "").strip()
            else:
                t = ""
            if t:
                out.append(t)
    return out


def _metrics_for(gold: list[str], pred: list[str]) -> dict[str, float | int]:
    gold_items = [_norm(x) for x in gold if _norm(x) and not _is_marker_only(x)]
    pred_items = [_norm(x) for x in pred if _norm(x) and not _is_marker_only(x)]

    gset = set(gold_items)
    pset = set(pred_items)
    inter = len(gset & pset)
    precision = inter / len(pset) if pset else 0.0
    recall = inter / len(gset) if gset else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    fuzzy_inter = _fuzzy_match_count(gold_items, pred_items)
    fuzzy_precision = fuzzy_inter / len(pset) if pset else 0.0
    fuzzy_recall = fuzzy_inter / len(gset) if gset else 0.0
    fuzzy_f1 = (
        2 * fuzzy_precision * fuzzy_recall / (fuzzy_precision + fuzzy_recall)
        if (fuzzy_precision + fuzzy_recall) > 0
        else 0.0
    )
    return {
        "gold_n": len(gset),
        "pred_n": len(pset),
        "overlap": inter,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "fuzzy_overlap": fuzzy_inter,
        "fuzzy_precision": round(fuzzy_precision, 4),
        "fuzzy_recall": round(fuzzy_recall, 4),
        "fuzzy_f1": round(fuzzy_f1, 4),
    }


def _row_eval(
    row: dict[str, Any],
    *,
    model_path: str,
    adapter_path: str,
    device: str,
    dtype: str,
    qwen_max_input_chars: int,
    max_new_tokens: int,
) -> dict[str, Any]:
    messages = row.get("messages") or []
    if not isinstance(messages, list) or len(messages) < 3:
        return {"error": "Row missing expected messages (system,user,assistant)."}
    system_msg = str((messages[0] or {}).get("content") or "")
    user_msg = str((messages[1] or {}).get("content") or "")
    gold_raw = str((messages[2] or {}).get("content") or "")

    try:
        gold = _refs_from_payload(json.loads(gold_raw))
    except Exception:
        gold = []

    clear_qwen_runtime_cache()
    cfg = replace(
        Settings(),
        qwen_citation_model_path=model_path,
        qwen_citation_adapter_path=adapter_path,
        qwen_device=device.strip().lower() or "auto",
        qwen_dtype=dtype.strip().lower() or "auto",
        qwen_max_input_chars=max(500, int(qwen_max_input_chars)),
    )

    out: dict[str, Any] = {}
    try:
        raw = generate_with_qwen(
            [{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}],
            settings=cfg,
            task="citation",
            max_new_tokens=max(16, int(max_new_tokens)),
            temperature=0.0,
        )
        pred = _refs_from_payload(decode_qwen_json(raw))
        out.update(_metrics_for(gold, pred))
        out["error"] = ""
        out["raw_preview"] = (raw or "")[:500]
    except Exception as exc:
        out.update(_metrics_for(gold, []))
        out["error"] = str(exc)[:400]
        out["raw_preview"] = ""
    return out


def _worker_main(args: argparse.Namespace) -> int:
    if not args.row_json:
        raise ValueError("--row-json is required in --worker mode")
    if not args.model_path:
        raise ValueError("--model-path is required in --worker mode")
    row = json.loads(Path(args.row_json).read_text(encoding="utf-8"))
    result = _row_eval(
        row,
        model_path=args.model_path,
        adapter_path=args.adapter or "",
        device=args.device,
        dtype=args.dtype,
        qwen_max_input_chars=args.qwen_max_input_chars,
        max_new_tokens=args.max_new_tokens,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _load_rows(path: Path, max_rows: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            continue
        rows.append(obj)
    if max_rows > 0:
        rows = rows[:max_rows]
    return rows


def _run_mode_subprocess(
    *,
    rows: list[dict[str, Any]],
    model_path: str,
    adapter_path: str,
    timeout_seconds: int,
    max_new_tokens: int,
    device: str,
    dtype: str,
    qwen_max_input_chars: int,
) -> list[dict[str, Any]]:
    out_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        meta = row.get("meta") or {}
        article_id = str(meta.get("article_id") or f"row_{idx}")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False) as tf:
            tf.write(json.dumps(row, ensure_ascii=False))
            row_json_path = tf.name
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--row-json",
            row_json_path,
            "--model-path",
            model_path,
            "--adapter",
            adapter_path or "",
            "--max-new-tokens",
            str(max_new_tokens),
            "--device",
            device,
            "--dtype",
            dtype,
            "--qwen-max-input-chars",
            str(qwen_max_input_chars),
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=max(30, int(timeout_seconds)),
                check=False,
            )
            if proc.returncode != 0:
                row_result = {
                    "gold_n": 0,
                    "pred_n": 0,
                    "overlap": 0,
                    "precision": 0.0,
                    "recall": 0.0,
                    "f1": 0.0,
                    "fuzzy_overlap": 0,
                    "fuzzy_precision": 0.0,
                    "fuzzy_recall": 0.0,
                    "fuzzy_f1": 0.0,
                    "error": (proc.stderr or proc.stdout or f"worker exited {proc.returncode}")[:400],
                    "raw_preview": "",
                }
            else:
                row_result = json.loads((proc.stdout or "").strip().splitlines()[-1])
        except subprocess.TimeoutExpired:
            row_result = {
                "gold_n": 0,
                "pred_n": 0,
                "overlap": 0,
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "fuzzy_overlap": 0,
                "fuzzy_precision": 0.0,
                "fuzzy_recall": 0.0,
                "fuzzy_f1": 0.0,
                "error": f"timeout after {timeout_seconds}s",
                "raw_preview": "",
            }
        finally:
            try:
                Path(row_json_path).unlink(missing_ok=True)
            except Exception:
                pass

        row_result["article_id"] = article_id
        out_rows.append(row_result)
    return out_rows


def _run_mode_in_process(
    *,
    rows: list[dict[str, Any]],
    model_path: str,
    adapter_path: str,
    max_new_tokens: int,
    device: str,
    dtype: str,
    qwen_max_input_chars: int,
) -> list[dict[str, Any]]:
    out_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        meta = row.get("meta") or {}
        article_id = str(meta.get("article_id") or f"row_{idx}")
        res = _row_eval(
            row,
            model_path=model_path,
            adapter_path=adapter_path,
            device=device,
            dtype=dtype,
            qwen_max_input_chars=qwen_max_input_chars,
            max_new_tokens=max_new_tokens,
        )
        res["article_id"] = article_id
        out_rows.append(res)
    return out_rows


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "macro_precision": 0.0,
            "macro_recall": 0.0,
            "macro_f1": 0.0,
            "macro_fuzzy_precision": 0.0,
            "macro_fuzzy_recall": 0.0,
            "macro_fuzzy_f1": 0.0,
        }
    return {
        "macro_precision": round(sum(float(r.get("precision", 0.0)) for r in rows) / len(rows), 4),
        "macro_recall": round(sum(float(r.get("recall", 0.0)) for r in rows) / len(rows), 4),
        "macro_f1": round(sum(float(r.get("f1", 0.0)) for r in rows) / len(rows), 4),
        "macro_fuzzy_precision": round(sum(float(r.get("fuzzy_precision", 0.0)) for r in rows) / len(rows), 4),
        "macro_fuzzy_recall": round(sum(float(r.get("fuzzy_recall", 0.0)) for r in rows) / len(rows), 4),
        "macro_fuzzy_f1": round(sum(float(r.get("fuzzy_f1", 0.0)) for r in rows) / len(rows), 4),
    }


def main() -> int:
    args = parse_args()
    if args.worker:
        return _worker_main(args)
    if not args.eval_jsonl:
        raise ValueError("--eval-jsonl is required")
    if not args.base_model_path:
        raise ValueError("--base-model-path is required")

    eval_path = Path(args.eval_jsonl).resolve()
    rows = _load_rows(eval_path, max_rows=max(0, int(args.max_rows)))
    if not rows:
        raise ValueError(f"No rows found in {eval_path}")

    base_model_path = str(Path(args.base_model_path).resolve())
    adapter_path = str(Path(args.adapter_path).resolve()) if args.adapter_path else ""

    runner = _run_mode_in_process if args.in_process else _run_mode_subprocess

    common_kwargs = dict(
        rows=rows,
        model_path=base_model_path,
        max_new_tokens=max(16, int(args.max_new_tokens)),
        device=args.device,
        dtype=args.dtype,
        qwen_max_input_chars=max(500, int(args.qwen_max_input_chars)),
    )
    if args.in_process:
        before_rows = runner(
            **common_kwargs,
            adapter_path="",
        )
    else:
        before_rows = runner(
            **common_kwargs,
            adapter_path="",
            timeout_seconds=max(30, int(args.timeout_seconds)),
        )

    after_rows = []
    if adapter_path:
        if args.in_process:
            after_rows = runner(
                **common_kwargs,
                adapter_path=adapter_path,
            )
        else:
            after_rows = runner(
                **common_kwargs,
                adapter_path=adapter_path,
                timeout_seconds=max(30, int(args.timeout_seconds)),
            )

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_jsonl": str(eval_path),
        "rows_evaluated": len(rows),
        "base_model_path": base_model_path,
        "adapter_path": adapter_path,
        "mode": "in_process" if args.in_process else "subprocess_timeout",
        "settings": {
            "device": args.device,
            "dtype": args.dtype,
            "max_new_tokens": int(args.max_new_tokens),
            "timeout_seconds": int(args.timeout_seconds),
            "qwen_max_input_chars": int(args.qwen_max_input_chars),
        },
        "before": {"metrics": _aggregate(before_rows), "rows": before_rows},
        "after": {"metrics": _aggregate(after_rows), "rows": after_rows} if after_rows else None,
    }

    output_path = Path(args.output_json).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
