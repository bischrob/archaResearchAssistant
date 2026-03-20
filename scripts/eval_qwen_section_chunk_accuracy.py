#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.qwen_local import clear_qwen_runtime_cache
from src.rag.qwen_structured_refs import detect_section_plan_with_qwen


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate Qwen3 adapter quality for section/reference-start detection."
    )
    p.add_argument("--eval-jsonl", required=True)
    p.add_argument("--base-model-path", required=True)
    p.add_argument("--adapter-path", required=True)
    p.add_argument("--output-json", required=True)
    p.add_argument("--max-rows", type=int, default=0, help="0 means all rows.")
    p.add_argument("--qwen-max-input-chars", type=int, default=12000)
    p.add_argument("--device", default="auto")
    p.add_argument("--dtype", default="auto")
    return p.parse_args()


def _load_rows(path: Path, max_rows: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            rows.append(obj)
    if max_rows > 0:
        rows = rows[:max_rows]
    return rows


def _section_lines_from_meta(meta: dict[str, Any]) -> list[str]:
    ocr_path = str(meta.get("ocr_path") or "").strip()
    if not ocr_path:
        return []
    p = Path(ocr_path)
    if not p.exists():
        return []
    body = p.read_text(encoding="utf-8", errors="ignore")
    return [line.strip() for line in body.splitlines() if line and line.strip()]


def _safe_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _parse_gold_headings(row: dict[str, Any]) -> tuple[list[int], int | None]:
    messages = row.get("messages") or []
    if not isinstance(messages, list) or len(messages) < 3:
        return [], None
    try:
        payload = json.loads(str((messages[2] or {}).get("content") or "{}"))
    except Exception:
        payload = {}
    heading_rows = payload.get("headings") or []
    heading_idxs: list[int] = []
    if isinstance(heading_rows, list):
        for item in heading_rows:
            if not isinstance(item, dict):
                continue
            idx = _safe_int(item.get("line_idx"))
            if idx is not None:
                heading_idxs.append(idx)
    ref_start = _safe_int(
        payload.get("reference_start_line")
        or payload.get("references_start_line")
        or payload.get("reference_start")
    )
    return sorted(set(heading_idxs)), ref_start


def _f1(gold: set[int], pred: set[int]) -> tuple[float, float, float]:
    inter = len(gold & pred)
    precision = inter / len(pred) if pred else 0.0
    recall = inter / len(gold) if gold else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def main() -> int:
    args = parse_args()

    eval_path = Path(args.eval_jsonl).resolve()
    rows = _load_rows(eval_path, max(0, int(args.max_rows)))
    if not rows:
        raise ValueError(f"No rows found: {eval_path}")

    cfg = replace(
        Settings(),
        qwen_citation_model_path=str(Path(args.base_model_path).resolve()),
        qwen_citation_adapter_path=str(Path(args.adapter_path).resolve()),
        qwen_device=args.device.strip().lower() or "auto",
        qwen_dtype=args.dtype.strip().lower() or "auto",
        qwen_max_input_chars=max(500, int(args.qwen_max_input_chars)),
    )

    clear_qwen_runtime_cache()
    section_rows: list[dict[str, Any]] = []
    section_errors = 0

    for idx, row in enumerate(rows):
        meta = row.get("meta") or {}
        article_id = str(meta.get("source_article_id") or meta.get("article_id") or f"row_{idx}")
        gold_heading_idxs, gold_ref_start = _parse_gold_headings(row)
        lines = _section_lines_from_meta(meta)
        if gold_ref_start is None or not lines:
            continue
        try:
            pred_heading_idxs, pred_ref_start = detect_section_plan_with_qwen(lines, settings=cfg)
            delta = None if pred_ref_start is None else (pred_ref_start - gold_ref_start)
            prec, rec, f1 = _f1(set(gold_heading_idxs), set(pred_heading_idxs))
            row_out = {
                "article_id": article_id,
                "gold_reference_start_line": gold_ref_start,
                "pred_reference_start_line": pred_ref_start,
                "delta_lines": delta,
                "abs_delta_lines": abs(delta) if delta is not None else None,
                "exact_match": (delta == 0) if delta is not None else False,
                "gold_heading_count": len(gold_heading_idxs),
                "pred_heading_count": len(pred_heading_idxs),
                "heading_precision": round(prec, 4),
                "heading_recall": round(rec, 4),
                "heading_f1": round(f1, 4),
                "error": "",
            }
        except Exception as exc:
            section_errors += 1
            row_out = {
                "article_id": article_id,
                "gold_reference_start_line": gold_ref_start,
                "pred_reference_start_line": None,
                "delta_lines": None,
                "abs_delta_lines": None,
                "exact_match": False,
                "gold_heading_count": len(gold_heading_idxs),
                "pred_heading_count": 0,
                "heading_precision": 0.0,
                "heading_recall": 0.0,
                "heading_f1": 0.0,
                "error": str(exc)[:400],
            }
        section_rows.append(row_out)

    section_abs = [float(x["abs_delta_lines"]) for x in section_rows if x.get("abs_delta_lines") is not None]
    section_exact = [1.0 if bool(x.get("exact_match")) else 0.0 for x in section_rows]
    heading_p = [float(x["heading_precision"]) for x in section_rows]
    heading_r = [float(x["heading_recall"]) for x in section_rows]
    heading_f = [float(x["heading_f1"]) for x in section_rows]

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_jsonl": str(eval_path),
        "rows_evaluated": len(rows),
        "base_model_path": str(Path(args.base_model_path).resolve()),
        "adapter_path": str(Path(args.adapter_path).resolve()),
        "settings": {
            "device": cfg.qwen_device,
            "dtype": cfg.qwen_dtype,
            "qwen_max_input_chars": int(cfg.qwen_max_input_chars),
        },
        "section_detection": {
            "errors": section_errors,
            "rows_used": len(section_rows),
            "exact_match_rate": round(sum(section_exact) / len(section_exact), 4) if section_exact else 0.0,
            "mae_lines": round(sum(section_abs) / len(section_abs), 4) if section_abs else None,
            "rmse_lines": (
                round(math.sqrt(sum(x * x for x in section_abs) / len(section_abs)), 4) if section_abs else None
            ),
            "heading_macro_precision": round(sum(heading_p) / len(heading_p), 4) if heading_p else 0.0,
            "heading_macro_recall": round(sum(heading_r) / len(heading_r), 4) if heading_r else 0.0,
            "heading_macro_f1": round(sum(heading_f) / len(heading_f), 4) if heading_f else 0.0,
            "rows": section_rows,
        },
    }

    output_path = Path(args.output_json).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
