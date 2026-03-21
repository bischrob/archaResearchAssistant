from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz

from .config import Settings
from .text_acquisition import acquire_pdf_text


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]*")
HEADING_RE = re.compile(r"^\s*(references|bibliography|works cited|literature cited)\s*$", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
PAGE_NUMBER_RE = re.compile(r"^(?:page\s*)?\d{1,4}$", re.IGNORECASE)
ROMAN_PAGE_NUMBER_RE = re.compile(r"^(?:page\s*)?[ivxlcdm]{1,10}$", re.IGNORECASE)
HEADER_FOOTER_SCAN_LINES = 3
HEADER_FOOTER_MIN_PAGE_HITS = 2
REFERENCE_JUNK_PHRASES = (
    "downloaded from",
    "terms and conditions",
    "creative commons license",
    "wiley online library",
    "all rights reserved",
    "for rules of use",
)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "that", "the", "their", "this", "to", "was", "were", "with",
}


@dataclass
class Chunk:
    chunk_id: str
    index: int
    text: str
    tokens: list[str]
    token_counts: dict[str, int]
    page_start: int
    page_end: int


@dataclass
class Citation:
    citation_id: str
    raw_text: str
    year: int | None
    title_guess: str
    normalized_title: str
    doi: str | None = None
    source: str | None = None
    type_guess: str | None = None
    author_tokens: list[str] | None = None
    quality_score: float | None = None


@dataclass
class ArticleDoc:
    article_id: str
    title: str
    normalized_title: str
    year: int | None
    author: str
    authors: list[str]
    citekey: str | None
    paperpile_id: str | None
    doi: str | None
    journal: str | None
    publisher: str | None
    source_path: str
    chunks: list[Chunk]
    citations: list[Citation]
    zotero_persistent_id: str | None = None
    zotero_item_key: str | None = None
    zotero_attachment_key: str | None = None
    title_year_key: str | None = None
    metadata_source: str | None = None
    text_acquisition_method: str | None = None
    text_acquisition_fallback_used: bool = False
    text_quality_check_backend: str | None = None
    native_text_malformed: bool = False
    native_text_malformed_reason: str | None = None
    native_text_char_count: int | None = None
    paddleocr_text_path: str | None = None
    ocr_engine: str | None = None
    ocr_model: str | None = None
    ocr_version: str | None = None
    ocr_processed_at: str | None = None
    ocr_quality_summary: str | None = None


def normalize_title(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _humanize_slug(slug: str) -> str:
    cleaned = slug.replace("_", " ").replace(",", ", ")
    cleaned = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -_,")
    return cleaned


def parse_filename_metadata(pdf_path: Path) -> tuple[str, int | None, str]:
    stem = pdf_path.stem
    m = re.match(r"([A-Za-z]+)(\d{4})-(.+)", stem)
    if m:
        author_slug, year_raw, title_slug = m.groups()
        author = author_slug.capitalize()
        year = int(year_raw)
        title = _humanize_slug(title_slug)
        return author, year, title
    return "Unknown Author", None, _humanize_slug(stem)


def _extract_page_text(pdf_path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text")
            if text and text.strip():
                out.append((i + 1, text))
    return out


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().lower()


def _is_page_number_line(line: str) -> bool:
    candidate = _normalize_line(line)
    if not candidate:
        return False
    if PAGE_NUMBER_RE.match(candidate):
        return True
    return ROMAN_PAGE_NUMBER_RE.match(candidate) is not None


def _split_page_lines(page_text: list[tuple[int, str]]) -> list[tuple[int, list[str]]]:
    out: list[tuple[int, list[str]]] = []
    for page_num, text in page_text:
        lines = [line.strip() for line in text.splitlines() if line and line.strip()]
        out.append((page_num, lines))
    return out


def _flatten_page_lines(page_lines: list[tuple[int, list[str]]]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for page_num, lines in page_lines:
        for line in lines:
            out.append((page_num, line))
    return out


def _remove_header_footer_noise(page_lines: list[tuple[int, list[str]]]) -> list[tuple[int, str]]:
    edge_hits: dict[str, set[int]] = defaultdict(set)
    for page_num, lines in page_lines:
        line_count = len(lines)
        if not line_count:
            continue
        for idx, line in enumerate(lines):
            normalized = _normalize_line(line)
            if not normalized or len(normalized) > 120:
                continue
            at_edge = idx < HEADER_FOOTER_SCAN_LINES or idx >= max(0, line_count - HEADER_FOOTER_SCAN_LINES)
            if at_edge:
                edge_hits[normalized].add(page_num)

    repeated_edges = {
        normalized
        for normalized, pages in edge_hits.items()
        if len(pages) >= HEADER_FOOTER_MIN_PAGE_HITS
    }

    filtered: list[tuple[int, str]] = []
    for page_num, lines in page_lines:
        line_count = len(lines)
        for idx, line in enumerate(lines):
            normalized = _normalize_line(line)
            if not normalized:
                continue
            at_edge = idx < HEADER_FOOTER_SCAN_LINES or idx >= max(0, line_count - HEADER_FOOTER_SCAN_LINES)
            if _is_page_number_line(normalized):
                continue
            if at_edge and normalized in repeated_edges:
                continue
            filtered.append((page_num, line))
    return filtered


def build_lines_with_page(page_text: list[tuple[int, str]], strip_page_noise: bool = True) -> list[tuple[int, str]]:
    page_lines = _split_page_lines(page_text)
    flattened = _flatten_page_lines(page_lines)
    if not strip_page_noise or not flattened:
        return flattened

    cleaned = _remove_header_footer_noise(page_lines)
    # Safety fallback: if cleaning removes too much content, keep original lines.
    if cleaned and len(cleaned) >= int(len(flattened) * 0.35):
        return cleaned
    return flattened


def _split_main_and_references(lines: list[str]) -> tuple[int | None, list[str], list[str]]:
    for idx, line in enumerate(lines):
        if HEADING_RE.match(line.strip()):
            return idx, lines[:idx], lines[idx + 1 :]
    return None, lines, []


def _tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in TOKEN_RE.findall(text)]
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def _chunk_words(words: list[str], size: int, overlap: int) -> Iterable[tuple[int, int]]:
    start = 0
    while start < len(words):
        end = min(start + size, len(words))
        yield start, end
        if end == len(words):
            break
        start = max(0, end - overlap)


def _extract_citations(reference_lines: list[str], article_id: str) -> list[Citation]:
    blocks: list[str] = []
    current: list[str] = []
    start_re = re.compile(r"^[A-Z][A-Za-z .,'-]+(?:\(|,)?\s*(?:19|20)\d{2}\b")

    for raw in reference_lines:
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if start_re.match(line) and current:
            blocks.append(" ".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(" ".join(current))

    citations: list[Citation] = []
    for idx, raw in enumerate(blocks):
        year_match = YEAR_RE.search(raw)
        year = int(year_match.group(0)) if year_match else None
        title_guess = ""
        if year_match:
            tail = raw[year_match.end() :]
            candidate = tail.split(".")[0].strip(" .;:-")
            title_guess = candidate
        if not title_guess:
            title_guess = raw[:120]
        citations.append(
            Citation(
                citation_id=f"{article_id}::ref::{idx}",
                raw_text=raw,
                year=year,
                title_guess=title_guess,
                normalized_title=normalize_title(title_guess),
                source="heuristic",
            )
        )
    return citations


def citation_quality_score(citation: Citation) -> float:
    title = (citation.title_guess or "").strip()
    raw = (citation.raw_text or "").strip()
    title_lower = title.lower()
    raw_lower = raw.lower()
    has_junk = any(phrase in title_lower or phrase in raw_lower for phrase in REFERENCE_JUNK_PHRASES)

    score = 0.0
    if title:
        if 8 <= len(title) <= 260:
            score += 0.5
        elif 6 <= len(title) <= 340:
            score += 0.2
    if citation.year is not None and 1600 <= citation.year <= 2100:
        score += 0.25
    if citation.author_tokens:
        score += 0.15
    if citation.doi:
        score += 0.15
    if has_junk:
        score -= 0.5
    if "http://" in raw_lower or "https://" in raw_lower:
        if "doi.org/" not in raw_lower:
            score -= 0.1
    return max(0.0, min(1.0, score))


def is_citation_quality_acceptable(citation: Citation, min_score: float = 0.35) -> bool:
    title = (citation.title_guess or "").strip()
    if not title:
        return False
    if len(title) < 6:
        return False
    title_lower = title.lower()
    raw_lower = (citation.raw_text or "").lower()
    if any(phrase in title_lower or phrase in raw_lower for phrase in REFERENCE_JUNK_PHRASES):
        return False
    return citation_quality_score(citation) >= max(0.0, min(1.0, float(min_score)))


def filter_citations(citations: list[Citation], min_score: float = 0.35) -> list[Citation]:
    out: list[Citation] = []
    for citation in citations:
        citation.quality_score = citation_quality_score(citation)
        if is_citation_quality_acceptable(citation, min_score=min_score):
            out.append(citation)
    return out


def load_article(
    pdf_path: Path,
    chunk_size_words: int,
    chunk_overlap_words: int,
    metadata: dict | None = None,
    strip_page_noise: bool = True,
    settings: Settings | None = None,
) -> ArticleDoc:
    fallback_author, fallback_year, fallback_title = parse_filename_metadata(pdf_path)
    metadata = metadata or {}
    title = metadata.get("title") or fallback_title
    year = metadata.get("year") if metadata.get("year") is not None else fallback_year
    authors = metadata.get("authors") or [fallback_author]
    primary_author = authors[0] if authors else fallback_author
    article_id = pdf_path.stem

    settings = settings or Settings()
    acquisition = acquire_pdf_text(
        pdf_path,
        settings=settings,
        strip_page_noise=strip_page_noise,
    )
    page_text = _extract_page_text(pdf_path)
    lines_with_page = acquisition.lines_with_page

    lines = [line for _, line in lines_with_page]
    split_idx, main_lines, ref_lines = _split_main_and_references(lines)
    citations = _extract_citations(ref_lines, article_id)

    words_with_page: list[tuple[str, int]] = []
    cutoff = split_idx if split_idx is not None else len(lines_with_page)
    for page_num, line in lines_with_page[:cutoff]:
        for word in line.split():
            words_with_page.append((word, page_num))

    chunks: list[Chunk] = []
    all_words = [w for w, _ in words_with_page]
    for idx, (start, end) in enumerate(_chunk_words(all_words, chunk_size_words, chunk_overlap_words)):
        chunk_words = all_words[start:end]
        if not chunk_words:
            continue
        chunk_text = " ".join(chunk_words).strip()
        token_list = _tokenize(chunk_text)
        counts = Counter(token_list)
        page_start = words_with_page[start][1]
        page_end = words_with_page[end - 1][1]
        chunks.append(
            Chunk(
                chunk_id=f"{article_id}::chunk::{idx}",
                index=idx,
                text=chunk_text,
                tokens=sorted(counts.keys()),
                token_counts=dict(counts),
                page_start=page_start,
                page_end=page_end,
            )
        )

    if not chunks and main_lines:
        text = " ".join(main_lines)
        token_list = _tokenize(text)
        counts = Counter(token_list)
        chunks = [
            Chunk(
                chunk_id=f"{article_id}::chunk::0",
                index=0,
                text=text,
                tokens=sorted(counts.keys()),
                token_counts=dict(counts),
                page_start=1,
                page_end=max((p for p, _ in page_text), default=1),
            )
        ]

    return ArticleDoc(
        article_id=article_id,
        title=title,
        normalized_title=normalize_title(title),
        year=year,
        author=primary_author,
        authors=authors,
        citekey=metadata.get("citekey"),
        paperpile_id=metadata.get("paperpile_id"),
        zotero_persistent_id=metadata.get("zotero_persistent_id"),
        zotero_item_key=metadata.get("zotero_item_key"),
        zotero_attachment_key=metadata.get("zotero_attachment_key"),
        doi=metadata.get("doi"),
        journal=metadata.get("journal"),
        publisher=metadata.get("publisher"),
        title_year_key=metadata.get("title_year_key"),
        metadata_source=metadata.get("metadata_source"),
        text_acquisition_method=acquisition.method,
        text_acquisition_fallback_used=acquisition.fallback_used,
        text_quality_check_backend=acquisition.native_text_report.backend,
        native_text_malformed=acquisition.native_text_report.is_malformed,
        native_text_malformed_reason=acquisition.native_text_report.reason,
        native_text_char_count=acquisition.native_text_report.char_count,
        paddleocr_text_path=acquisition.ocr_text_path,
        ocr_engine=acquisition.ocr_engine,
        ocr_model=acquisition.ocr_model,
        ocr_version=acquisition.ocr_version,
        ocr_processed_at=acquisition.ocr_processed_at,
        ocr_quality_summary=acquisition.ocr_quality_summary,
        source_path=str(pdf_path),
        chunks=chunks,
        citations=citations,
    )
