from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from .config import Settings
from .pdf_processing import Citation, normalize_title


REFERENCE_HEADING_VARIANTS = {
    "references",
    "bibliography",
    "works cited",
    "references cited",
    "literature cited",
    "cited references",
    "reference list",
    "sources cited",
}
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'/-]*")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
REFERENCE_ENTRY_START_RE = re.compile(
    r"^\s*(?:\[\d+\]|\d+[.)])?\s*(?:[A-Z][A-Za-z'`-]+(?:,\s*[A-Z][A-Za-z'`.\-]+)*|\w.+?)\s*(?:\(|,)?\s*(?:19|20)\d{2}\b"
)
TRAILING_TITLE_BAD_RE = re.compile(r"(?:,\s*pp\b|pp\.\s*\d|^\d+(?:\.\d+)+$)", re.IGNORECASE)
CONTINUATION_HINT_RE = re.compile(
    r"^(?:https?://|doi:|10\.\d{4,9}/|pp?\.\s*\d|vol\.|no\.|issue\s+\d|journal\b|proceedings\b|press\b|university\b|publisher\b)",
    re.IGNORECASE,
)
NUMBERED_INLINE_REF_RE = re.compile(r"(?<!\w)(\[\d+\]|\d{1,3}[)])\s+")
IMAGE_ARTIFACT_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
FIGURE_ARTIFACT_RE = re.compile(r"^(?:figure|fig\.)\s*\d+\b", re.IGNORECASE)
EMBEDDED_AUTHOR_YEAR_START_RE = re.compile(
    r"(?:[A-Z][A-Za-z'`.-]+(?:,\s*[A-Z][A-Za-z'`.-]+(?:\s+[A-Z][A-Za-z'`.-]+)*){0,4}\.?\s+(?:19|20)\d{2}\.)"
)


@dataclass(frozen=True)
class ReferenceSectionDetection:
    start_line: int | None
    end_line: int | None
    method: str
    confidence: float


@dataclass(frozen=True)
class ReferenceSectionSpan:
    start_line: int
    end_line: int
    method: str
    confidence: float


@dataclass(frozen=True)
class ReferenceSplitResult:
    entries: list[str]
    method: str
    confidence: float
    failures: list[dict[str, Any]]


def normalize_heading_text(text: str) -> str:
    lowered = (text or "").strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


def _clean_line(line: str) -> str:
    return " ".join((line or "").split()).strip()


def _normalize_reference_row(line: str) -> str:
    clean = _clean_line(IMAGE_ARTIFACT_RE.sub(" ", line or ""))
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        return ""
    if FIGURE_ARTIFACT_RE.match(clean):
        return ""
    return clean


def _lead_word_count(line: str) -> int:
    match = YEAR_RE.search(line or "")
    if not match:
        return 0
    lead = (line or "")[: match.start()].strip(" ,;:.-")
    return len(WORD_RE.findall(lead))


def _looks_like_reference_lead(line: str) -> bool:
    clean = _clean_line(line)
    if not clean or not REFERENCE_ENTRY_START_RE.match(clean):
        return False
    if clean.lower().startswith(("http://", "https://", "doi:")):
        return False
    lead_words = _lead_word_count(clean)
    if not (1 <= lead_words <= 16):
        return False
    year_match = YEAR_RE.search(clean)
    if not year_match:
        return False
    lead = clean[: year_match.start()].strip(" ,;:.-")
    tokens = re.findall(r"[A-Za-z][A-Za-z'`.-]*", lead)
    if not tokens:
        return False
    if "," in lead or len(tokens) <= 2:
        return True
    titleish = sum(1 for token in tokens if token[:1].isupper())
    return (titleish / max(1, len(tokens))) >= 0.6


def _is_continuation_line(line: str) -> bool:
    clean = _clean_line(line)
    if not clean:
        return False
    if CONTINUATION_HINT_RE.match(clean):
        return True
    if DOI_RE.fullmatch(clean.rstrip(".;, ")):
        return True
    if URL_RE.fullmatch(clean):
        return True
    if clean[:1].islower():
        return True
    return False


def _split_inline_numbered_references(text: str) -> list[str]:
    clean = _clean_line(text)
    if not clean:
        return []
    matches = list(NUMBERED_INLINE_REF_RE.finditer(clean))
    if len(matches) < 2:
        return [clean]
    parts: list[str] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if (idx + 1) < len(matches) else len(clean)
        chunk = clean[start:end].strip()
        if chunk:
            parts.append(chunk)
    return parts or [clean]


def _split_merged_author_year_entry(text: str) -> list[str]:
    clean = _clean_line(text)
    if not clean:
        return []
    starts = [0]
    for match in EMBEDDED_AUTHOR_YEAR_START_RE.finditer(clean):
        start = match.start()
        if start == 0:
            continue
        prefix = clean[:start].rstrip()
        if not prefix:
            continue
        if DOI_RE.search(prefix) or URL_RE.search(prefix) or prefix.endswith("."):
            starts.append(start)
    starts = sorted(set(starts))
    if len(starts) <= 1:
        return [clean]
    out: list[str] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if (idx + 1) < len(starts) else len(clean)
        chunk = _clean_line(clean[start:end])
        if chunk:
            out.append(chunk)
    return out or [clean]


def _expand_candidate_entries(entries: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    expanded: list[str] = []
    failures: list[dict[str, Any]] = []
    for entry in entries:
        numbered_parts = _split_inline_numbered_references(entry)
        if len(numbered_parts) > 1:
            failures.append({"kind": "split_inline_numbered_references", "raw_text": entry, "count": len(numbered_parts)})
        for part in numbered_parts:
            author_parts = _split_merged_author_year_entry(part)
            if len(author_parts) > 1:
                failures.append({"kind": "split_merged_author_year_entry", "raw_text": part, "count": len(author_parts)})
            expanded.extend(author_parts)
    return expanded, failures


def detect_reference_sections_from_lines(lines: list[str]) -> list[ReferenceSectionSpan]:
    if not lines:
        return []
    markdown_headings: list[tuple[int, int, str]] = []
    for idx, raw in enumerate(lines):
        heading = HEADING_RE.match(raw)
        if not heading:
            continue
        markdown_headings.append((idx, len(heading.group(1)), normalize_heading_text(heading.group(2))))
    out: list[ReferenceSectionSpan] = []
    for pos, (idx, level, norm) in enumerate(markdown_headings):
        if norm not in REFERENCE_HEADING_VARIANTS:
            continue
        end = len(lines) - 1
        for next_idx, next_level, _next_norm in markdown_headings[pos + 1 :]:
            if next_level <= level:
                end = next_idx - 1
                break
        if end >= idx:
            out.append(ReferenceSectionSpan(idx, end, "heading", 0.98))
    if out:
        return out
    plain_heading_indices = [idx for idx, raw in enumerate(lines) if normalize_heading_text(raw) in REFERENCE_HEADING_VARIANTS]
    if plain_heading_indices:
        spans: list[ReferenceSectionSpan] = []
        for pos, idx in enumerate(plain_heading_indices):
            end = (plain_heading_indices[pos + 1] - 1) if (pos + 1) < len(plain_heading_indices) else (len(lines) - 1)
            if end >= idx:
                spans.append(ReferenceSectionSpan(idx, end, "plain_heading", 0.92))
        return spans
    tail_start = max(0, len(lines) - 80)
    for idx in range(tail_start, len(lines)):
        if not _looks_like_reference_lead(lines[idx]):
            continue
        lead_hits = 0
        continuation_hits = 0
        for probe_idx in range(idx, min(len(lines), idx + 12)):
            probe = _clean_line(lines[probe_idx])
            if _looks_like_reference_lead(probe):
                lead_hits += 1
            elif _is_continuation_line(probe):
                continuation_hits += 1
        if lead_hits >= 3 and (lead_hits + continuation_hits) >= 3:
            confidence = 0.78 if idx >= max(0, len(lines) - 50) else 0.7
            return [ReferenceSectionSpan(idx, len(lines) - 1, "tail_cluster", confidence)]
    return []


def detect_reference_section_from_lines(lines: list[str]) -> ReferenceSectionDetection:
    spans = detect_reference_sections_from_lines(lines)
    if not spans:
        return ReferenceSectionDetection(None, None, "none", 0.0)
    first = spans[0]
    return ReferenceSectionDetection(first.start_line, first.end_line, first.method, first.confidence)


def split_references_from_lines(
    lines: list[str],
    *,
    section_detection: ReferenceSectionDetection | None = None,
    section_spans: list[ReferenceSectionSpan] | None = None,
) -> ReferenceSplitResult:
    spans = section_spans or ([
        ReferenceSectionSpan(section_detection.start_line, section_detection.end_line, section_detection.method, section_detection.confidence)
    ] if section_detection and section_detection.start_line is not None and section_detection.end_line is not None else detect_reference_sections_from_lines(lines))
    if not spans:
        return ReferenceSplitResult([], "none", 0.0, [])
    entries: list[str] = []
    failures: list[dict[str, Any]] = []
    merge_events = 0
    methods: list[str] = []
    confidences: list[float] = []
    for span in spans:
        methods.append(span.method)
        confidences.append(span.confidence)
        rows = lines[span.start_line : span.end_line + 1]
        if rows and HEADING_RE.match(rows[0]):
            rows = rows[1:]
        current: list[str] = []
        for raw in rows:
            clean = _normalize_reference_row(raw)
            if not clean:
                continue
            if _looks_like_reference_lead(clean):
                if current:
                    entries.append(" ".join(current).strip())
                current = [clean]
                continue
            if current and _is_continuation_line(clean):
                current.append(clean)
                merge_events += 1
                continue
            if current:
                current.append(clean)
                failures.append({"kind": "suspicious_continuation", "line": clean, "section_start": span.start_line})
            else:
                failures.append({"kind": "orphan_line", "line": clean, "section_start": span.start_line})
        if current:
            entries.append(" ".join(current).strip())

    entries, expansion_failures = _expand_candidate_entries(entries)
    failures.extend(expansion_failures)

    deduped: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        key = entry.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)

    base_confidence = sum(confidences) / max(1, len(confidences))
    method = methods[0] if len(set(methods)) == 1 else "multi_section"
    confidence = min(0.98, max(0.35, base_confidence + (0.05 if merge_events else 0.0) - (0.05 * min(3, len(failures)))))
    return ReferenceSplitResult(deduped, method, confidence, failures)


def detect_references_section(markdown_text: str) -> tuple[int | None, int | None]:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    detection = detect_reference_section_from_lines(lines)
    return detection.start_line, detection.end_line


def split_reference_entries(markdown_text: str) -> list[str]:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return split_references_from_lines(lines).entries


def _extract_year_from_text(text: str) -> int | None:
    match = YEAR_RE.search(text or "")
    if not match:
        return None
    try:
        return int(match.group(0))
    except Exception:
        return None


def _extract_doi_from_text(text: str) -> str | None:
    match = DOI_RE.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip(".;,")


def _extract_authors_from_text(text: str) -> list[str]:
    prefix = (text or "").strip()
    year_match = YEAR_RE.search(prefix)
    if year_match:
        prefix = prefix[: year_match.start()].strip(" .,;:-")
    if not prefix:
        return []
    prefix = re.sub(r"\bet al\.?$", "", prefix, flags=re.IGNORECASE).strip(" ,;")
    parts = re.split(r"\s+(?:and|&)\s+|,\s+(?=[A-Z][A-Za-z'`-]+(?:\s+[A-Z][A-Za-z'`.-]+)*)", prefix)
    authors: list[str] = []
    for part in parts:
        clean = _clean_line(part).strip(" ,;")
        if clean and re.search(r"[A-Za-z]", clean):
            authors.append(clean)
    return list(dict.fromkeys(authors))


def _extract_author_tokens_from_text(text: str) -> list[str]:
    out: list[str] = []
    for author in _extract_authors_from_text(text):
        tokens = re.findall(r"[A-Za-z][A-Za-z'-]+", author.lower())
        if tokens:
            out.append(tokens[-1])
    return list(dict.fromkeys(out))


def _extract_title_from_text(text: str) -> str:
    clean = _clean_line(text)
    if not clean:
        return ""
    year_match = YEAR_RE.search(clean)
    remainder = clean[year_match.end() :].strip(" .,:;") if year_match else clean
    remainder = DOI_RE.sub("", remainder).strip(" .,:;")
    pieces = re.split(r"\.\s+", remainder, maxsplit=1)
    candidate = pieces[0].strip(" .,:;") if pieces else remainder
    if candidate:
        return candidate[:240]
    return clean[:240]


def _looks_invalid_reference_text(text: str) -> bool:
    clean = _clean_line(text)
    if not clean or len(clean) < 12:
        return True
    doi_only = DOI_RE.fullmatch(clean.rstrip(".;, ")) is not None
    url_only = URL_RE.fullmatch(clean) is not None
    if doi_only or url_only:
        return True
    if IMAGE_ARTIFACT_RE.search(clean):
        return True
    if FIGURE_ARTIFACT_RE.match(clean):
        return True
    if len(WORD_RE.findall(clean)) > 70 and YEAR_RE.search(clean):
        return True
    return False


def _citation_quality_details(citation: Citation) -> tuple[float, bool, list[str]]:
    reasons: list[str] = []
    score = 0.0
    raw = _clean_line(citation.raw_text)
    title = _clean_line(citation.title_guess)
    if _looks_invalid_reference_text(raw):
        reasons.append("invalid_reference_text")
        return 0.0, True, reasons
    if citation.year is not None:
        score += 0.2
    else:
        reasons.append("missing_year")
    if title and 8 <= len(title) <= 240:
        score += 0.25
    else:
        reasons.append("weak_title")
    if citation.authors:
        score += 0.2
    else:
        reasons.append("missing_authors")
    if citation.doi:
        score += 0.15
    if citation.split_confidence is not None:
        score += max(0.0, min(0.2, citation.split_confidence * 0.2))
    if citation.source == "llm":
        score += 0.1
    if citation.source == "heuristic":
        score += 0.05
    if TRAILING_TITLE_BAD_RE.search(title):
        score -= 0.2
        reasons.append("truncated_title")
    if len(WORD_RE.findall(raw)) > 55:
        score -= 0.2
        reasons.append("prose_like_reference")
    needs_review = any(reason in {"missing_year", "weak_title", "truncated_title", "prose_like_reference"} for reason in reasons)
    return max(0.0, min(1.0, score)), needs_review, reasons


def _citation_from_text(
    text: str,
    *,
    article_id: str,
    index: int,
    split_confidence: float,
    parse_method: str,
) -> Citation:
    title_guess = _extract_title_from_text(text)
    citation = Citation(
        citation_id=f"{article_id}::ref::{index}",
        raw_text=_clean_line(text),
        raw_text_original=text,
        year=_extract_year_from_text(text),
        title_guess=title_guess or _clean_line(text)[:120],
        normalized_title=normalize_title(title_guess or _clean_line(text)[:120]),
        doi=_extract_doi_from_text(text),
        source=parse_method,
        type_guess=None,
        author_tokens=_extract_author_tokens_from_text(text),
        authors=_extract_authors_from_text(text),
        parse_method=parse_method,
        split_confidence=split_confidence,
    )
    quality, needs_review, _ = _citation_quality_details(citation)
    citation.quality_score = quality
    citation.parse_confidence = quality
    citation.needs_review = needs_review
    return citation


def parse_reference_strings_heuristic(
    references: list[str],
    *,
    article_id: str,
    split_confidence: float = 0.8,
) -> tuple[list[Citation], list[dict[str, Any]]]:
    expanded_references, expansion_failures = _expand_candidate_entries(references)
    citations: list[Citation] = []
    failures: list[dict[str, Any]] = list(expansion_failures)
    for idx, raw in enumerate(expanded_references):
        text = _clean_line(raw)
        if not text:
            continue
        if _looks_invalid_reference_text(text):
            failures.append({"index": idx, "raw_text": text, "error": "invalid_reference_text", "parser_mode": "heuristic"})
            continue
        citation = _citation_from_text(
            text,
            article_id=article_id,
            index=len(citations),
            split_confidence=split_confidence,
            parse_method="heuristic",
        )
        citations.append(citation)
    return citations, failures


def _llm_repair_prompt(entries: list[dict[str, Any]]) -> str:
    return (
        "You repair scholarly reference parsing. Return JSON only as "
        '{"references":[{"index":0,"title":"...","year":2020,"doi":"...","authors":["..."],"type_guess":"...","needs_review":false,"parse_confidence":0.9}]}. '
        "Do not invent data. Preserve missing values as null or empty arrays. "
        f"Entries: {json.dumps(entries, ensure_ascii=False)}"
    )


def _repair_with_openai(
    citations: list[Citation],
    *,
    settings: Settings,
) -> tuple[list[Citation], list[dict[str, Any]]]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return citations, [{"error": "missing_openai_api_key", "parser_mode": "hybrid_llm"}]
    payload_entries = []
    repairable: list[tuple[int, Citation]] = []
    for idx, citation in enumerate(citations):
        if citation.needs_review:
            repairable.append((idx, citation))
            payload_entries.append(
                {
                    "index": idx,
                    "raw_text": citation.raw_text,
                    "title_guess": citation.title_guess,
                    "year": citation.year,
                    "doi": citation.doi,
                    "authors": citation.authors or [],
                }
            )
    if not payload_entries:
        return citations, []
    payload_entries = payload_entries[: max(1, settings.reference_parser_llm_max_references)]
    resp = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": settings.reference_parser_llm_model,
            "input": _llm_repair_prompt(payload_entries),
            "text": {"format": {"type": "json_object"}},
        },
        timeout=max(5, int(settings.reference_parser_llm_timeout_seconds)),
    )
    resp.raise_for_status()
    body = resp.json()
    text = ""
    for item in body.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                text += content.get("text", "")
    parsed = json.loads(text or "{}")
    repaired = list(citations)
    failures: list[dict[str, Any]] = []
    for row in parsed.get("references", []):
        if not isinstance(row, dict):
            continue
        idx = row.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(repaired):
            continue
        citation = repaired[idx]
        title = _clean_line(str(row.get("title") or citation.title_guess))
        doi = _clean_line(str(row.get("doi") or citation.doi or "")) or None
        year = row.get("year") if isinstance(row.get("year"), int) else citation.year
        authors = [str(x).strip() for x in (row.get("authors") or []) if str(x).strip()]
        citation.title_guess = title or citation.title_guess
        citation.normalized_title = normalize_title(citation.title_guess)
        citation.doi = doi
        citation.year = year
        citation.authors = authors or citation.authors
        citation.author_tokens = _extract_author_tokens_from_text(" ".join(authors)) if authors else citation.author_tokens
        citation.parse_method = "hybrid_llm_repair"
        citation.source = "llm"
        quality, needs_review, reasons = _citation_quality_details(citation)
        citation.parse_confidence = float(row.get("parse_confidence") or quality)
        citation.quality_score = quality
        citation.needs_review = bool(row.get("needs_review", needs_review))
        if reasons and citation.needs_review:
            failures.append({"index": idx, "raw_text": citation.raw_text, "error": ",".join(reasons), "parser_mode": "hybrid_llm"})
    return repaired, failures


def parse_reference_entries(
    references: list[str],
    *,
    article_id: str,
    settings: Settings,
    parser_mode: str,
    split_confidence: float = 0.8,
) -> tuple[list[Citation], list[dict[str, Any]]]:
    mode = (parser_mode or "heuristic").strip().lower()
    citations, failures = parse_reference_strings_heuristic(
        references,
        article_id=article_id,
        split_confidence=split_confidence,
    )
    if mode == "heuristic":
        return citations, failures
    if mode in {"hybrid_llm", "llm"}:
        try:
            repaired, llm_failures = _repair_with_openai(citations if mode == "hybrid_llm" else [
                _citation_from_text(text, article_id=article_id, index=idx, split_confidence=split_confidence, parse_method="llm_seed")
                for idx, text in enumerate(references)
                if _clean_line(text)
            ], settings=settings)
            return repaired, failures + llm_failures
        except Exception as exc:
            failures.append({"index": None, "raw_text": None, "error": str(exc), "parser_mode": mode})
            return citations, failures
    if mode == "legacy_anystyle":
        return citations, failures
    return citations, failures
