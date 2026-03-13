#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.paperpile_metadata import find_metadata_for_pdf, load_paperpile_index
from src.rag.pdf_processing import Citation, filter_citations, load_article, normalize_title


SYSTEM_PROMPT = (
    "You are a bibliography parser. Convert each raw reference string into compact JSON with fields: "
    "title, year, doi, author_tokens, and type."
)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
AUTHOR_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate additional LoRA supervision examples from sampled PDFs.")
    p.add_argument("--pdf-dir", default="pdfs", help="Directory containing PDFs.")
    p.add_argument("--paperpile-json", default="Paperpile.json", help="Paperpile metadata JSON path.")
    p.add_argument("--sample-pdfs", type=int, default=80, help="How many PDFs to sample.")
    p.add_argument("--seed", type=int, default=42, help="Random seed.")
    p.add_argument("--max-citations-per-pdf", type=int, default=20, help="Cap examples per PDF.")
    p.add_argument("--min-quality", type=float, default=0.35, help="Citation quality threshold.")
    p.add_argument(
        "--existing-jsonl",
        action="append",
        default=[],
        help="Optional existing JSONL files for deduplication (can pass multiple).",
    )
    p.add_argument(
        "--output-jsonl",
        default="data/reference_lora_pdf_samples.jsonl",
        help="Output JSONL file for newly generated examples.",
    )
    p.add_argument(
        "--summary-json",
        default="data/reference_lora_pdf_samples_summary.json",
        help="Output summary JSON path.",
    )
    p.add_argument(
        "--merge-into-train",
        default="",
        help="Optional train JSONL to append merged deduped examples into.",
    )
    p.add_argument(
        "--merge-into-eval",
        default="",
        help="Optional eval JSONL to append merged deduped examples into.",
    )
    p.add_argument(
        "--eval-ratio",
        type=float,
        default=0.15,
        help="Eval split ratio when merge targets are provided.",
    )
    return p.parse_args()


def _safe_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1400 <= value <= 2100 else None
    text = str(value)
    m = re.search(r"\b(19|20)\d{2}\b", text)
    return int(m.group(0)) if m else None


def _safe_doi(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        match = DOI_RE.search(str(value))
        if match:
            return match.group(0).rstrip(".;,")
    return None


def _author_tokens_from_text(text: str) -> list[str]:
    head = (text or "").split(".")[0]
    toks = AUTHOR_TOKEN_RE.findall(head.lower())
    if not toks:
        return []
    keep: list[str] = []
    for tok in toks[:8]:
        if len(tok) < 3:
            continue
        keep.append(tok)
    return list(dict.fromkeys(keep[:3]))


def _author_tokens_from_metadata(meta: dict[str, Any] | None) -> list[str]:
    if not meta:
        return []
    authors = meta.get("authors") or []
    out = []
    for value in authors:
        toks = AUTHOR_TOKEN_RE.findall(str(value).lower())
        if toks:
            out.append(toks[-1])
    return list(dict.fromkeys(out))


def _iter_pdf_files(pdf_dir: Path) -> list[Path]:
    return sorted([p for p in pdf_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"], key=lambda p: str(p).lower())


def _load_existing_keys(paths: list[str]) -> set[tuple[str, str, str, str]]:
    keys: set[tuple[str, str, str, str]] = set()
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                messages = row.get("messages") if isinstance(row, dict) else None
                if not isinstance(messages, list) or len(messages) < 3:
                    continue
                user = str(messages[1].get("content") or "")
                assistant = str(messages[2].get("content") or "")
                raw_ref = user.split("Raw reference:", 1)[-1].strip().lower()
                try:
                    target = json.loads(assistant)
                except Exception:
                    target = {}
                title = str(target.get("title") or "").strip().lower()
                year = str(target.get("year") or "")
                doi = str(target.get("doi") or "").strip().lower()
                keys.add((raw_ref, title, year, doi))
    return keys


def _paperpile_title_index(paperpile: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in paperpile:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        norm = normalize_title(title)
        if norm and norm not in out:
            out[norm] = row
    return out


def _citation_target(citation: Citation, matched: dict[str, Any] | None, article_meta: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    if matched:
        title = str(matched.get("title") or citation.title_guess or "").strip()
        year = _safe_year((matched.get("published") or {}).get("year") if isinstance(matched.get("published"), dict) else matched.get("published"))
        doi = _safe_doi(matched.get("doi"), citation.doi, citation.raw_text)
        author_tokens = _author_tokens_from_metadata({"authors": [a.get("formatted") for a in (matched.get("author") or []) if isinstance(a, dict)]})
        if not author_tokens:
            author_tokens = _author_tokens_from_text(citation.raw_text)
        type_guess = str(matched.get("pubtype") or "").strip() or None
        confidence = "matched_paperpile_title"
    else:
        title = str(citation.title_guess or "").strip() or (citation.raw_text or "").strip()[:180]
        year = _safe_year(citation.year)
        doi = _safe_doi(citation.doi, citation.raw_text)
        author_tokens = citation.author_tokens or _author_tokens_from_text(citation.raw_text)
        if not author_tokens:
            author_tokens = _author_tokens_from_metadata(article_meta)
        type_guess = citation.type_guess or None
        confidence = "heuristic_citation"
    target = {
        "title": title,
        "year": year,
        "doi": doi,
        "author_tokens": list(dict.fromkeys([t for t in author_tokens if t]))[:6],
        "type": type_guess,
    }
    return target, confidence


def _make_example(raw_reference: str, target: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Parse this raw reference string into JSON with keys "
                    "title, year, doi, author_tokens, type. Return JSON only.\n"
                    f"Raw reference: {raw_reference}"
                ),
            },
            {"role": "assistant", "content": json.dumps(target, ensure_ascii=False)},
        ],
        "meta": meta,
    }


def _dedup_key(example: dict[str, Any]) -> tuple[str, str, str, str]:
    messages = example.get("messages") or []
    user = str(messages[1].get("content") if len(messages) > 1 and isinstance(messages[1], dict) else "")
    raw_ref = user.split("Raw reference:", 1)[-1].strip().lower()
    assistant = str(messages[2].get("content") if len(messages) > 2 and isinstance(messages[2], dict) else "")
    try:
        target = json.loads(assistant)
    except Exception:
        target = {}
    title = str(target.get("title") or "").strip().lower()
    year = str(target.get("year") or "")
    doi = str(target.get("doi") or "").strip().lower()
    return (raw_ref, title, year, doi)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                out.append(row)
    return out


def main() -> None:
    args = parse_args()
    rnd = random.Random(args.seed)
    pdf_dir = Path(args.pdf_dir).resolve()
    output_jsonl = Path(args.output_jsonl).resolve()
    summary_json = Path(args.summary_json).resolve()
    merge_train = Path(args.merge_into_train).resolve() if args.merge_into_train else None
    merge_eval = Path(args.merge_into_eval).resolve() if args.merge_into_eval else None

    pdf_files = _iter_pdf_files(pdf_dir)
    if not pdf_files:
        raise SystemExit(f"No PDFs found under {pdf_dir}")
    sample_n = max(1, min(int(args.sample_pdfs), len(pdf_files)))
    sampled = rnd.sample(pdf_files, sample_n)

    paperpile_index = load_paperpile_index(args.paperpile_json)
    paperpile = json.loads(Path(args.paperpile_json).read_text(encoding="utf-8"))
    paperpile_title_idx = _paperpile_title_index(paperpile if isinstance(paperpile, list) else [])
    existing_keys = _load_existing_keys(args.existing_jsonl)

    generated: list[dict[str, Any]] = []
    parse_failures: list[dict[str, str]] = []
    seen_keys = set(existing_keys)
    source_counts = {"matched_paperpile_title": 0, "heuristic_citation": 0}
    per_pdf_counts: dict[str, int] = {}

    for pdf_path in sampled:
        article_meta = find_metadata_for_pdf(paperpile_index, pdf_path.name) or {}
        try:
            article = load_article(
                pdf_path=pdf_path,
                chunk_size_words=220,
                chunk_overlap_words=45,
                metadata=article_meta,
                strip_page_noise=True,
            )
        except Exception as exc:
            parse_failures.append({"pdf": str(pdf_path), "error": str(exc)})
            continue

        citations = filter_citations(article.citations, min_score=float(args.min_quality))
        if not citations:
            continue

        count = 0
        for citation in citations:
            if count >= max(1, int(args.max_citations_per_pdf)):
                break
            raw_ref = (citation.raw_text or "").strip()
            if len(raw_ref) < 20:
                continue
            matched = paperpile_title_idx.get(citation.normalized_title or "")
            target, confidence = _citation_target(citation, matched=matched, article_meta=article_meta)
            if not target.get("title"):
                continue
            example = _make_example(
                raw_reference=raw_ref,
                target=target,
                meta={
                    "source": "pdf_sampling",
                    "confidence": confidence,
                    "pdf": str(pdf_path),
                    "article_id": article.article_id,
                    "article_title": article.title,
                    "article_year": article.year,
                    "citation_id": citation.citation_id,
                    "quality_score": citation.quality_score,
                },
            )
            key = _dedup_key(example)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            source_counts[confidence] = source_counts.get(confidence, 0) + 1
            generated.append(example)
            count += 1
        if count:
            per_pdf_counts[str(pdf_path)] = count

    rnd.shuffle(generated)
    _write_jsonl(output_jsonl, generated)

    merged_train_written = 0
    merged_eval_written = 0
    if merge_train and merge_eval:
        base_train = _read_jsonl(merge_train)
        base_eval = _read_jsonl(merge_eval)
        merged = base_train + base_eval
        dedup_rows = []
        dedup_keys: set[tuple[str, str, str, str]] = set()
        for row in merged + generated:
            key = _dedup_key(row)
            if key in dedup_keys:
                continue
            dedup_keys.add(key)
            dedup_rows.append(row)

        rnd.shuffle(dedup_rows)
        eval_n = max(1, int(round(len(dedup_rows) * max(0.01, min(0.5, float(args.eval_ratio)))))) if dedup_rows else 0
        new_eval = dedup_rows[:eval_n]
        new_train = dedup_rows[eval_n:]
        _write_jsonl(merge_train, new_train)
        _write_jsonl(merge_eval, new_eval)
        merged_train_written = len(new_train)
        merged_eval_written = len(new_eval)

    summary = {
        "pdf_dir": str(pdf_dir),
        "sampled_pdfs": sample_n,
        "total_pdf_candidates": len(pdf_files),
        "generated_examples": len(generated),
        "existing_dedup_keys_loaded": len(existing_keys),
        "source_counts": source_counts,
        "parse_failures": parse_failures[:50],
        "parse_failure_count": len(parse_failures),
        "per_pdf_counts_top20": sorted(
            [{"pdf": pdf, "count": cnt} for pdf, cnt in per_pdf_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:20],
        "output_jsonl": str(output_jsonl),
        "merge_train": str(merge_train) if merge_train else None,
        "merge_eval": str(merge_eval) if merge_eval else None,
        "merge_train_written": merged_train_written,
        "merge_eval_written": merged_eval_written,
    }
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

