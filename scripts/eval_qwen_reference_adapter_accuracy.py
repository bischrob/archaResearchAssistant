#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import math
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.qwen_local import clear_qwen_runtime_cache, decode_qwen_json, generate_with_qwen
from src.rag.qwen_structured_refs import detect_section_plan_with_qwen


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate Qwen3 adapter quality for reference splitting and section boundary detection."
    )
    p.add_argument("--eval-jsonl", required=True)
    p.add_argument("--base-model-path", required=True)
    p.add_argument("--adapter-path", required=True)
    p.add_argument("--output-json", required=True)
    p.add_argument("--max-rows", type=int, default=0, help="0 means all rows.")
    p.add_argument("--max-new-tokens", type=int, default=256)
    p.add_argument("--qwen-max-input-chars", type=int, default=12000)
    p.add_argument("--device", default="auto")
    p.add_argument("--dtype", default="auto")
    p.add_argument("--skip-section-eval", action="store_true")
    return p.parse_args()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def _canon(text: str) -> str:
    t = _norm(text)
    t = re.sub(r"\bdoi:\s*", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    seq = difflib.SequenceMatcher(a=a, b=b).ratio()
    sa = set(a.split())
    sb = set(b.split())
    jacc = (len(sa & sb) / len(sa | sb)) if (sa and sb) else 0.0
    return max(seq, jacc)


def _fuzzy_match_count(gold: list[str], pred: list[str], threshold: float = 0.72) -> int:
    g = [_canon(x) for x in gold if _canon(x)]
    p = [_canon(x) for x in pred if _canon(x)]
    used: set[int] = set()
    hits = 0
    for gi in g:
        best_idx = -1
        best_score = 0.0
        for idx, pj in enumerate(p):
            if idx in used:
                continue
            score = _similarity(gi, pj)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx >= 0 and best_score >= threshold:
            used.add(best_idx)
            hits += 1
    return hits


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
    gset = set(_norm(x) for x in gold if _norm(x))
    pset = set(_norm(x) for x in pred if _norm(x))
    inter = len(gset & pset)
    precision = inter / len(pset) if pset else 0.0
    recall = inter / len(gset) if gset else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    fuzzy_inter = _fuzzy_match_count(list(gset), list(pset))
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


def _macro(rows: list[dict[str, Any]], keys: list[str]) -> dict[str, float]:
    if not rows:
        return {k: 0.0 for k in keys}
    return {k: round(sum(float(r.get(k, 0.0)) for r in rows) / len(rows), 4) for k in keys}


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
    split_rows: list[dict[str, Any]] = []
    section_rows: list[dict[str, Any]] = []
    split_errors = 0
    section_errors = 0

    for idx, row in enumerate(rows):
        messages = row.get("messages") or []
        if not isinstance(messages, list) or len(messages) < 3:
            split_errors += 1
            continue
        system_msg = str((messages[0] or {}).get("content") or "")
        user_msg = str((messages[1] or {}).get("content") or "")
        gold_raw = str((messages[2] or {}).get("content") or "")
        meta = row.get("meta") or {}
        article_id = str(meta.get("article_id") or f"row_{idx}")

        try:
            gold = _refs_from_payload(json.loads(gold_raw))
        except Exception:
            gold = []

        try:
            raw = generate_with_qwen(
                [{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}],
                settings=cfg,
                task="citation",
                max_new_tokens=max(16, int(args.max_new_tokens)),
                temperature=0.0,
            )
            pred = _refs_from_payload(decode_qwen_json(raw))
            m = _metrics_for(gold, pred)
            m["article_id"] = article_id
            m["error"] = ""
        except Exception as exc:
            split_errors += 1
            m = _metrics_for(gold, [])
            m["article_id"] = article_id
            m["error"] = str(exc)[:400]
        split_rows.append(m)

        if args.skip_section_eval:
            continue
        ref_start_gold = _safe_int(meta.get("reference_start_line"))
        lines = _section_lines_from_meta(meta)
        if ref_start_gold is None or not lines:
            continue
        try:
            _, ref_start_pred = detect_section_plan_with_qwen(lines, settings=cfg)
            delta = None if ref_start_pred is None else (ref_start_pred - ref_start_gold)
            row_out = {
                "article_id": article_id,
                "gold_reference_start_line": ref_start_gold,
                "pred_reference_start_line": ref_start_pred,
                "delta_lines": delta,
                "abs_delta_lines": abs(delta) if delta is not None else None,
                "exact_match": (delta == 0) if delta is not None else False,
                "error": "",
            }
        except Exception as exc:
            section_errors += 1
            row_out = {
                "article_id": article_id,
                "gold_reference_start_line": ref_start_gold,
                "pred_reference_start_line": None,
                "delta_lines": None,
                "abs_delta_lines": None,
                "exact_match": False,
                "error": str(exc)[:400],
            }
        section_rows.append(row_out)

    section_abs = [float(x["abs_delta_lines"]) for x in section_rows if x.get("abs_delta_lines") is not None]
    section_exact = [1.0 if bool(x.get("exact_match")) else 0.0 for x in section_rows]

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_jsonl": str(eval_path),
        "rows_evaluated": len(rows),
        "base_model_path": str(Path(args.base_model_path).resolve()),
        "adapter_path": str(Path(args.adapter_path).resolve()),
        "settings": {
            "device": cfg.qwen_device,
            "dtype": cfg.qwen_dtype,
            "max_new_tokens": int(args.max_new_tokens),
            "qwen_max_input_chars": int(cfg.qwen_max_input_chars),
            "skip_section_eval": bool(args.skip_section_eval),
        },
        "reference_split": {
            "errors": split_errors,
            "metrics": _macro(
                split_rows,
                ["precision", "recall", "f1", "fuzzy_precision", "fuzzy_recall", "fuzzy_f1"],
            ),
            "rows": split_rows,
        },
        "section_detection": {
            "errors": section_errors,
            "rows_used": len(section_rows),
            "exact_match_rate": round(sum(section_exact) / len(section_exact), 4) if section_exact else 0.0,
            "mae_lines": round(sum(section_abs) / len(section_abs), 4) if section_abs else None,
            "rmse_lines": (
                round(math.sqrt(sum(x * x for x in section_abs) / len(section_abs)), 4) if section_abs else None
            ),
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
