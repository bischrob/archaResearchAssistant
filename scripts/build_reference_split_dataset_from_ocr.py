#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings


REFERENCE_SPLIT_SYSTEM_PROMPT = (
    "You split bibliography text into individual references. "
    'Return JSON only with this schema: {"references":["<one reference>", "<one reference>"]}. '
    "Page breaks, page numbers, and running headers do NOT end the references section. "
    "A reference may continue across page boundaries and line wraps; keep it as one item. "
    "Do not return numeric labels like [1], 1., or citation keys alone; return full reference strings only. "
    "Keep original order and preserve full content for each reference as a single line item. "
    "Do not omit trailing references after page breaks. "
    "Do not add commentary and do not invent text."
)


@dataclass
class ParsedDoc:
    ocr_path: Path
    stem: str
    ref_start_line: int
    scanned_lines: int
    reference_block: str
    references: list[str]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Build Qwen3 split-reference training JSONL from OCR text files using a local heuristic parser. "
            "Also writes per-PDF markdown audit artifacts."
        )
    )
    p.add_argument("--ocr-dir", default="ocr/paddleocr/text", help="Root directory containing OCR .txt files.")
    p.add_argument(
        "--anchor-ocr",
        default="ocr/paddleocr/text/aikens1966-PlainsRelationshipsOfFremontCulture-ASummaryStatementOfAHypothesis.txt",
        help="OCR file to include as the first seed sample.",
    )
    p.add_argument(
        "--no-anchor",
        action="store_true",
        help="Do not force-include --anchor-ocr; sample only random OCR files.",
    )
    p.add_argument(
        "--exclude-jsonl",
        action="append",
        default=[],
        help="JSONL file(s) whose meta.article_id entries are excluded from sampling.",
    )
    p.add_argument("--additional", type=int, default=9, help="How many extra OCR files to sample.")
    p.add_argument("--seed", type=int, default=42, help="Random seed for reproducible sampling.")
    p.add_argument("--min-refs", type=int, default=8, help="Minimum parsed references to keep an OCR file.")
    p.add_argument("--max-refs", type=int, default=120, help="Maximum parsed references to keep an OCR file.")
    p.add_argument(
        "--output-jsonl",
        default="data/qwen3_reference_audit/reference_split_local_10pdf.jsonl",
        help="Output JSONL path.",
    )
    p.add_argument(
        "--output-summary-md",
        default="data/qwen3_reference_audit/reference_split_local_10pdf_SUMMARY.md",
        help="Output markdown summary path.",
    )
    p.add_argument(
        "--audit-dir",
        default="data/qwen3_reference_audit/local_split_dataset",
        help="Directory for per-document markdown audit files.",
    )
    return p.parse_args()


def _normalize_line(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _extract_reference_region(lines: list[str]) -> tuple[int | None, int]:
    start = None
    for i, line in enumerate(lines):
        if line.strip().lower() == "references":
            start = i + 1
            break
    if start is None:
        return None, len(lines)

    stop = len(lines)
    for i in range(start, len(lines)):
        l = lines[i].strip().lower()
        if "(article continued from" in l or "article continued from" in l:
            stop = i
            break
        if "evidenceof acculturation" in l:
            stop = i
            break
    return start, stop


def _local_split_reference_lines(lines: list[str]) -> list[str]:
    cleaned = [_normalize_line(x) for x in lines]
    cleaned = [x for x in cleaned if x and not re.fullmatch(r"\d{1,3}", x)]

    author_re = re.compile(
        r"^[A-Z][A-Za-z'`.-]+(?:,\s*[A-Z][A-Za-z .,'`&-]+)?(?:\s+and\s+[A-Z][A-Za-z .,'`&-]+)?$"
    )
    year_re = re.compile(r"^(19|20)\d{2}[a-z]?\b", re.I)
    author_year_same_line_re = re.compile(r"^[A-Z].*\b(19|20)\d{2}[a-z]?\b")

    refs: list[str] = []
    current: list[str] = []
    current_author = ""

    def flush() -> None:
        if not current:
            return
        txt = " ".join(current).strip(" .;")
        if len(txt) >= 28:
            refs.append(txt)

    i = 0
    while i < len(cleaned):
        line = cleaned[i]
        if line in {"9", "10", "11", "12"}:
            i += 1
            continue

        if author_re.match(line):
            nxt = cleaned[i + 1] if i + 1 < len(cleaned) else ""
            if year_re.match(nxt):
                current_author = line
                i += 1
                continue

        if year_re.match(line):
            flush()
            current = []
            if current_author:
                current.append(current_author)
            current.append(line)
            i += 1
            continue

        if author_year_same_line_re.match(line):
            flush()
            current = [line]
            i += 1
            continue

        if not current:
            i += 1
            continue

        current.append(line)
        i += 1

    flush()
    deduped: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        key = ref.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def _parse_ocr_file(path: Path) -> ParsedDoc | None:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    start, stop = _extract_reference_region(lines)
    if start is None:
        return None
    region = lines[start:stop]
    refs = _local_split_reference_lines(region)
    if not refs:
        return None
    return ParsedDoc(
        ocr_path=path.resolve(),
        stem=path.stem,
        ref_start_line=start + 1,  # human 1-based
        scanned_lines=max(0, stop - start),
        reference_block="\n".join(region).strip(),
        references=refs,
    )


def _write_doc_audit(doc: ParsedDoc, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{doc.stem}.md"
    lines: list[str] = []
    lines.append(f"# Local Split Audit: {doc.stem}")
    lines.append("")
    lines.append(f"- OCR: `{doc.ocr_path}`")
    lines.append(f"- Reference section starts at line: {doc.ref_start_line}")
    lines.append(f"- Lines scanned in reference region: {doc.scanned_lines}")
    lines.append(f"- Parsed references: {len(doc.references)}")
    lines.append("")
    lines.append("## Parsed References")
    lines.append("")
    for idx, ref in enumerate(doc.references, start=1):
        lines.append(f"{idx}. {ref}")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def _jsonl_row(doc: ParsedDoc) -> dict:
    user = (
        "Split the bibliography text below into one item per full reference.\n"
        "Important: page breaks do not end references; continue references across page boundaries.\n"
        "Return JSON only in the required schema.\n\n"
        f"Bibliography text:\n{doc.reference_block}"
    )
    assistant = json.dumps({"references": doc.references}, ensure_ascii=False)
    return {
        "task": "split_reference_chunk",
        "messages": [
            {"role": "system", "content": REFERENCE_SPLIT_SYSTEM_PROMPT},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "meta": {
            "source": "ocr_local_split",
            "ocr_path": str(doc.ocr_path),
            "article_id": doc.stem,
            "reference_start_line": doc.ref_start_line,
            "reference_line_count": doc.scanned_lines,
            "expected_references": len(doc.references),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def _load_excluded_article_ids(paths: list[str]) -> set[str]:
    excluded: set[str] = set()
    for raw in paths:
        p = Path(raw).resolve()
        if not p.exists() or not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            meta = obj.get("meta") or {}
            article_id = str(meta.get("article_id") or "").strip()
            if article_id:
                excluded.add(article_id)
    return excluded


def main() -> int:
    args = parse_args()
    _settings = Settings()

    ocr_root = Path(args.ocr_dir).resolve()
    if not ocr_root.exists():
        raise FileNotFoundError(f"OCR directory not found: {ocr_root}")

    rnd = random.Random(int(args.seed))
    min_refs = max(1, int(args.min_refs))
    max_refs = max(min_refs, int(args.max_refs))
    excluded_ids = _load_excluded_article_ids(list(args.exclude_jsonl))

    selected: list[ParsedDoc] = []
    target_count = int(args.additional)

    anchor = Path(args.anchor_ocr).resolve()
    if not args.no_anchor:
        if not anchor.exists():
            raise FileNotFoundError(f"Anchor OCR file not found: {anchor}")
        parsed_anchor = _parse_ocr_file(anchor)
        if parsed_anchor is None:
            raise RuntimeError(f"Anchor OCR file had no parseable references: {anchor}")
        if parsed_anchor.stem not in excluded_ids:
            selected.append(parsed_anchor)
            target_count += 1

    candidates = list(ocr_root.rglob("*.txt"))
    if not args.no_anchor:
        candidates = [p for p in candidates if p.resolve() != anchor]
    candidates = [p for p in candidates if p.stem not in excluded_ids]
    rnd.shuffle(candidates)

    for path in candidates:
        parsed = _parse_ocr_file(path)
        if parsed is None:
            continue
        n = len(parsed.references)
        if n < min_refs or n > max_refs:
            continue
        selected.append(parsed)
        if len(selected) >= target_count:
            break

    if len(selected) < target_count:
        raise RuntimeError(
            f"Could only collect {len(selected)} docs (wanted {target_count}). "
            "Relax --min-refs/--max-refs or verify OCR corpus."
        )

    audit_dir = Path(args.audit_dir).resolve()
    audit_paths: list[Path] = []
    for doc in selected:
        audit_paths.append(_write_doc_audit(doc, audit_dir))

    output_jsonl = Path(args.output_jsonl).resolve()
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with output_jsonl.open("w", encoding="utf-8") as f:
        for doc in selected:
            f.write(json.dumps(_jsonl_row(doc), ensure_ascii=False) + "\n")

    summary_md = Path(args.output_summary_md).resolve()
    summary_md.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Local Split Dataset Summary")
    lines.append("")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- OCR root: `{ocr_root}`")
    lines.append(f"- Total docs: {len(selected)}")
    lines.append(f"- Output JSONL: `{output_jsonl}`")
    lines.append(f"- Audit dir: `{audit_dir}`")
    lines.append("")
    lines.append("| # | Article ID | Ref Start Line | Ref Lines | Parsed Refs | Audit |")
    lines.append("|---:|---|---:|---:|---:|---|")
    for idx, (doc, md_path) in enumerate(zip(selected, audit_paths), start=1):
        lines.append(
            f"| {idx} | {doc.stem} | {doc.ref_start_line} | {doc.scanned_lines} | {len(doc.references)} | `{md_path.name}` |"
        )
    lines.append("")
    summary_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote JSONL: {output_jsonl}")
    print(f"Wrote summary: {summary_md}")
    print(f"Wrote audits: {audit_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
