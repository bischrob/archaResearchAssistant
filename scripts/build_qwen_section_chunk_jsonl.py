#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.qwen_structured_refs import (
    REFERENCE_HEADING_RE,
    SECTION_SYSTEM_PROMPT,
    _build_typed_sections,
    _heading_candidates,
    _heuristic_reference_starts,
    _toc_mapped_heading_candidates,
    _toc_window,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Build a Qwen3 section-chunk training dataset from existing OCR/reference-split metadata. "
            "Rows are aligned to detect_section_plan_with_qwen() prompt/response format."
        )
    )
    p.add_argument(
        "--source-jsonl",
        action="append",
        default=[],
        help="Source JSONL file(s) with OCR path and reference_start_line metadata.",
    )
    p.add_argument("--sample-size", type=int, default=250)
    p.add_argument("--eval-ratio", type=float, default=0.10)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--overrides-json",
        default="data/qwen3_section_chunk_audit/manual_section_overrides.json",
    )
    p.add_argument(
        "--output-jsonl",
        default="data/qwen3_section_chunk_audit/section_chunk_local_250_20260319.jsonl",
    )
    p.add_argument(
        "--output-train-jsonl",
        default="data/qwen3_section_chunk_audit/section_chunk_local_250_20260319_train_eval/train.jsonl",
    )
    p.add_argument(
        "--output-eval-jsonl",
        default="data/qwen3_section_chunk_audit/section_chunk_local_250_20260319_train_eval/eval.jsonl",
    )
    p.add_argument(
        "--output-summary-md",
        default="data/qwen3_section_chunk_audit/section_chunk_local_250_20260319_SUMMARY.md",
    )
    return p.parse_args()


def _default_sources() -> list[Path]:
    return [
        Path("data/qwen3_reference_audit/reference_split_local_500_20260317_train_eval/train.jsonl"),
        Path("data/qwen3_reference_audit/reference_split_local_500_20260317_train_eval/eval.jsonl"),
    ]


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s:
            continue
        rows.append(json.loads(s))
    return rows


def _load_overrides(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_source_rows(paths: list[Path]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        for row in _read_jsonl(path):
            meta = row.get("meta") or {}
            article_id = str(meta.get("article_id") or "").strip()
            if not article_id or article_id in seen:
                continue
            seen.add(article_id)
            out.append(row)
    return out


def _read_ocr_lines(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return [line.strip() for line in raw.splitlines() if line and line.strip()]


SECTION_NUMBER_RE = re.compile(r"^(?:\d+(?:\.\d+)*|[IVXLC]+|[A-Z])[\.\)]?\s+\S")
SECTION_PREFIX_RE = re.compile(r"^(?:chapter|appendix|part)\b", re.I)
TIMESTAMP_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}\b")
BAD_HEADING_RE = re.compile(
    r"("
    r"copyright|issn|doi|crossmark|keywords?:|article\s+info|articleinfo|accepted\s+manuscript|"
    r"springer|elsevier|routledge|taylor\s*&\s*francis|journal\s+of|hum nat|plos|"
    r"brigham\s+young\s+university|university|provo|utah|arizona|table\s+\d+|figure\s+\d+|"
    r"property\s+of|proofreading|promotional\s+purposes|see\s+profile"
    r")",
    re.I,
)
GOOD_SECTION_TITLES = {
    "abstract",
    "introduction",
    "background",
    "methods",
    "materials",
    "materials and methods",
    "methodology",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
    "summary",
    "acknowledgements",
    "acknowledgments",
    "preface",
    "contents",
    "objectives",
    "research design",
    "terminology",
    "glossary",
    "appendix",
    "appendixes",
}
SECTION_CUE_WORDS = {
    "abstract",
    "introduction",
    "background",
    "study",
    "area",
    "methods",
    "materials",
    "methodology",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
    "summary",
    "analysis",
    "design",
    "theory",
    "chronology",
    "appendix",
    "appendixes",
    "preface",
    "objectives",
    "glossary",
    "terminology",
}


def _clean_heading_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _is_probable_toc_line(text: str) -> bool:
    clean = _clean_heading_text(text)
    if not clean:
        return False
    return clean.endswith(".") and len(clean.split()) <= 6


def _reference_heading_indices(lines: list[str]) -> list[int]:
    out: list[int] = []
    toc_window = _toc_window(lines)
    for idx, line in enumerate(lines):
        if toc_window is not None and toc_window[0] < idx <= toc_window[1]:
            continue
        clean = _clean_heading_text(line)
        if not REFERENCE_HEADING_RE.match(clean):
            continue
        start = max(0, idx - 4)
        end = min(len(lines), idx + 6)
        window = [_clean_heading_text(lines[pos]) for pos in range(start, end)]
        short_toc = sum(1 for row in window if _is_probable_toc_line(row) or row.isdigit())
        prose = sum(1 for row in window if len(row.split()) >= 8 and not _is_probable_toc_line(row))
        if short_toc >= 4 and prose == 0:
            continue
        out.append(idx)
    return out


def _looks_like_true_section_start(text: str, idx: int, ref_start: int | None) -> bool:
    clean = _clean_heading_text(text)
    if not clean:
        return False
    lower = clean.lower()
    if BAD_HEADING_RE.search(clean):
        return False
    if TIMESTAMP_RE.match(clean):
        return False
    if clean.isdigit():
        return False
    if sum(ch.isdigit() for ch in clean) >= 3:
        return False
    if "," in clean:
        return False
    words = clean.split()
    if len(words) > 8:
        return False
    if lower in GOOD_SECTION_TITLES:
        return True
    if SECTION_PREFIX_RE.match(clean):
        return True
    if SECTION_NUMBER_RE.match(clean):
        return True
    # Accept short title-case/all-caps headings only if they contain strong section cue words.
    alpha_words = [w for w in words if any(ch.isalpha() for ch in w)]
    if not alpha_words:
        return False
    titleish = sum(1 for w in alpha_words if w[:1].isupper() or w.isupper())
    if titleish / len(alpha_words) < 0.85:
        return False
    cue_hits = sum(1 for w in alpha_words if w.lower().strip(":-") in SECTION_CUE_WORDS)
    if cue_hits == 0:
        return False
    if len(alpha_words) <= 6 and len(clean) <= 60:
        return True
    return False


def _normalize_reference_start(meta: dict, total_lines: int) -> int | None:
    raw = meta.get("reference_start_line")
    if raw is None:
      return None
    try:
        idx = int(raw)
    except Exception:
        return None
    # Existing builder wrote 1-based line numbers.
    idx = idx - 1 if idx > 0 else idx
    if idx < 0 or idx >= total_lines:
        return None
    return idx


def _anchor_reference_start(lines: list[str], idx: int | None) -> int | None:
    if idx is None or not lines:
        return idx
    if 0 <= idx < len(lines) and REFERENCE_HEADING_RE.match(_clean_heading_text(lines[idx])):
        return idx
    start = max(0, idx - 5)
    for pos in range(idx - 1, start - 1, -1):
        if REFERENCE_HEADING_RE.match(_clean_heading_text(lines[pos])):
            return pos
    return idx


def _select_reference_starts(lines: list[str], meta_reference_start: int | None) -> list[int]:
    detected = _heuristic_reference_starts(lines)
    if detected:
        return sorted(set(detected))
    if meta_reference_start is None:
        return []
    anchored = _anchor_reference_start(lines, meta_reference_start)
    return [anchored] if anchored is not None else []


def _label_headings(lines: list[str], reference_starts: list[int]) -> list[dict]:
    candidates = _heading_candidates(lines)
    toc_mapped = {idx for idx, _ in _toc_mapped_heading_candidates(lines)}
    toc_window = _toc_window(lines)
    out: list[dict] = []
    seen: set[int] = set()
    last_kept_idx: int | None = None
    reference_start_set = set(reference_starts)
    earliest_ref = min(reference_starts) if reference_starts else None
    for idx, heading_text in candidates:
        if idx in seen:
            continue
        if toc_window is not None and toc_window[0] < idx <= toc_window[1] and idx not in toc_mapped:
            continue
        if idx in reference_start_set:
            seen.add(idx)
            out.append({"line_idx": idx, "kind": "references", "heading": _clean_heading_text(heading_text)})
            last_kept_idx = idx
            continue
        if not _looks_like_true_section_start(heading_text, idx=idx, ref_start=earliest_ref):
            continue
        if last_kept_idx is not None and idx != 0 and (idx - last_kept_idx) < 8:
            continue
        seen.add(idx)
        out.append({"line_idx": idx, "kind": "body", "heading": _clean_heading_text(heading_text)})
        last_kept_idx = idx

    for reference_start in reference_starts:
        if reference_start in seen:
            continue
        heading = " ".join(lines[reference_start].split())[:120] if lines else "References"
        out.append({"line_idx": reference_start, "kind": "references", "heading": heading or "References"})

    out.sort(key=lambda row: int(row["line_idx"]))
    if not out:
        out = [{"line_idx": 0, "kind": "body", "heading": "Document Start"}]
    return out


def _build_row(source_row: dict) -> dict | None:
    meta = source_row.get("meta") or {}
    article_id = str(meta.get("article_id") or "").strip()
    ocr_path = Path(str(meta.get("ocr_path") or "")).resolve()
    if not article_id or not ocr_path.exists():
        return None

    lines = _read_ocr_lines(ocr_path)
    if not lines:
        return None
    meta_reference_start = _normalize_reference_start(meta, len(lines))
    if meta_reference_start is None:
        return None
    reference_starts = _select_reference_starts(lines, meta_reference_start)
    if not reference_starts:
        reference_starts = sorted(set(_reference_heading_indices(lines)))
    if not reference_starts:
        return None

    override = OVERRIDES.get(article_id)
    if override:
        sections = []
        for row in override.get("section_chunks", []):
            sections.append(
                {
                    "start_line": int(row["start_line"]),
                    "end_line": int(row["end_line"]),
                    "kind": str(row.get("kind") or "body"),
                }
            )
        headings = [
            {
                "line_idx": int(section["start_line"]),
                "kind": str(section["kind"]),
                "heading": _clean_heading_text(lines[int(section["start_line"])])[:120] if lines else "",
            }
            for section in sections
        ]
        reference_blocks = override.get("reference_blocks") or [
            {"start_line": int(section["start_line"]), "end_line": int(section["end_line"])}
            for section in sections
            if str(section.get("kind")) == "references"
        ]
        ref_line = override.get("reference_start_line")
    else:
        seed_headings = _label_headings(lines, reference_starts=reference_starts)
        built_sections = _build_typed_sections(
            lines,
            heading_indices=[int(row["line_idx"]) for row in seed_headings],
            reference_starts=reference_starts,
            reference_start=(min(reference_starts) if reference_starts else None),
        )
        sections = [
            {"start_line": s.start_line, "end_line": s.end_line, "kind": s.kind}
            for s in built_sections
        ]
        headings = []
        for section in built_sections:
            raw = _clean_heading_text(lines[section.start_line]) if lines else ""
            if not raw:
                if section.kind == "front_matter":
                    raw = "Front Matter"
                elif section.kind == "preface":
                    raw = "Preface"
                elif section.kind == "appendix":
                    raw = "Appendix"
                elif section.kind == "references":
                    raw = "References"
                else:
                    raw = "Document Start"
            headings.append({"line_idx": section.start_line, "kind": section.kind, "heading": raw[:120]})
        reference_blocks = [
            {"start_line": section["start_line"], "end_line": section["end_line"]}
            for section in sections
            if section["kind"] == "references"
        ]
        ref_line = min(reference_starts) if reference_starts else None
    payload = [{"idx": int(row["line_idx"]), "line": str(row["heading"])} for row in headings]
    user = (
        "Candidate heading lines as JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Return only JSON in the required schema."
    )
    assistant = json.dumps(
        {
            "headings": headings,
            "reference_start_line": ref_line,
        },
        ensure_ascii=False,
    )
    return {
        "task": "detect_section_plan",
        "messages": [
            {"role": "system", "content": SECTION_SYSTEM_PROMPT},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "meta": {
            "source": "derived_from_reference_split_ocr",
            "source_article_id": article_id,
            "ocr_path": str(ocr_path),
            "reference_start_line": ref_line,
            "reference_blocks": reference_blocks,
            "line_count": len(lines),
            "candidate_heading_count": len(payload),
            "section_chunks": sections,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "manual_override_applied": bool(override),
        },
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_summary(path: Path, *, all_rows: list[dict], train_rows: list[dict], eval_rows: list[dict], seed: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate_counts = [int((row.get("meta") or {}).get("candidate_heading_count") or 0) for row in all_rows]
    line_counts = [int((row.get("meta") or {}).get("line_count") or 0) for row in all_rows]
    section_kind_counts = Counter()
    for row in all_rows:
        for section in (row.get("meta") or {}).get("section_chunks") or []:
            section_kind_counts[str(section.get("kind") or "unknown")] += 1
    lines = [
        "# Qwen3 Section Chunk Dataset Summary",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Seed: {seed}",
        f"- Documents total: {len(all_rows)}",
        f"- Train rows: {len(train_rows)}",
        f"- Eval rows: {len(eval_rows)}",
        f"- Candidate heading count range: {min(candidate_counts) if candidate_counts else 0} to {max(candidate_counts) if candidate_counts else 0}",
        f"- OCR line count range: {min(line_counts) if line_counts else 0} to {max(line_counts) if line_counts else 0}",
        f"- Section chunk counts: {dict(section_kind_counts)}",
        "",
        "## Outputs",
        "",
        f"- Full dataset: `{args.output_jsonl}`",
        f"- Train split: `{args.output_train_jsonl}`",
        f"- Eval split: `{args.output_eval_jsonl}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


args = parse_args()
OVERRIDES = _load_overrides(Path(args.overrides_json))
source_paths = [Path(p) for p in args.source_jsonl] or _default_sources()
source_rows = _load_source_rows(source_paths)
if not source_rows:
    raise SystemExit("No source rows loaded.")

rnd = random.Random(args.seed)
rnd.shuffle(source_rows)
selected = source_rows[: min(int(args.sample_size), len(source_rows))]
built_rows = [row for row in (_build_row(src) for src in selected) if row is not None]
if not built_rows:
    raise SystemExit("No dataset rows built.")

rnd.shuffle(built_rows)
eval_n = max(1, int(round(len(built_rows) * max(0.05, min(0.40, float(args.eval_ratio))))))
eval_rows = built_rows[:eval_n]
train_rows = built_rows[eval_n:]
if not train_rows:
    raise SystemExit("Eval ratio left no training rows.")

_write_jsonl(Path(args.output_jsonl), built_rows)
_write_jsonl(Path(args.output_train_jsonl), train_rows)
_write_jsonl(Path(args.output_eval_jsonl), eval_rows)
_write_summary(Path(args.output_summary_md), all_rows=built_rows, train_rows=train_rows, eval_rows=eval_rows, seed=args.seed)

print(
    json.dumps(
        {
            "source_rows": len(source_rows),
            "dataset_rows": len(built_rows),
            "train_rows": len(train_rows),
            "eval_rows": len(eval_rows),
            "output_jsonl": args.output_jsonl,
            "output_train_jsonl": args.output_train_jsonl,
            "output_eval_jsonl": args.output_eval_jsonl,
            "output_summary_md": args.output_summary_md,
        },
        indent=2,
    )
)
