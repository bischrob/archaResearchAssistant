#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.qwen_structured_refs import split_reference_strings_for_anystyle


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate heuristic reference splitting against gold split rows.")
    p.add_argument("--eval-jsonl", required=True)
    p.add_argument("--output-json", required=True)
    p.add_argument("--max-rows", type=int, default=0, help="0 means all rows")
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


def _extract_reference_block(user_content: str) -> str:
    marker = "Bibliography text:\n"
    if marker in user_content:
        return user_content.split(marker, 1)[1].strip()
    return user_content.strip()


def main() -> int:
    args = parse_args()
    eval_path = Path(args.eval_jsonl).resolve()
    rows = _load_rows(eval_path, max(0, int(args.max_rows)))
    if not rows:
        raise ValueError(f"No rows found: {eval_path}")

    split_rows: list[dict[str, Any]] = []
    split_errors = 0

    for idx, row in enumerate(rows):
        messages = row.get("messages") or []
        if not isinstance(messages, list) or len(messages) < 3:
            split_errors += 1
            continue
        user_msg = str((messages[1] or {}).get("content") or "")
        gold_raw = str((messages[2] or {}).get("content") or "")
        meta = row.get("meta") or {}
        article_id = str(meta.get("article_id") or f"row_{idx}")

        try:
            gold = _refs_from_payload(json.loads(gold_raw))
        except Exception:
            gold = []

        try:
            block = _extract_reference_block(user_msg)
            pred = split_reference_strings_for_anystyle(block)
            m = _metrics_for(gold, pred)
            m["article_id"] = article_id
            m["error"] = ""
        except Exception as exc:
            split_errors += 1
            m = _metrics_for(gold, [])
            m["article_id"] = article_id
            m["error"] = str(exc)[:400]
        split_rows.append(m)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "eval_jsonl": str(eval_path),
        "rows_evaluated": len(split_rows),
        "errors": split_errors,
        "split_macro": _macro(
            split_rows,
            ["precision", "recall", "f1", "fuzzy_precision", "fuzzy_recall", "fuzzy_f1"],
        ),
        "rows": split_rows,
    }

    out_path = Path(args.output_json).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
