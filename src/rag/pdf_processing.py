from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import fitz


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]*")
HEADING_RE = re.compile(r"^\s*(references|bibliography|works cited|literature cited)\s*$", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
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
            )
        )
    return citations


def load_article(
    pdf_path: Path,
    chunk_size_words: int,
    chunk_overlap_words: int,
    metadata: dict | None = None,
) -> ArticleDoc:
    fallback_author, fallback_year, fallback_title = parse_filename_metadata(pdf_path)
    metadata = metadata or {}
    title = metadata.get("title") or fallback_title
    year = metadata.get("year") if metadata.get("year") is not None else fallback_year
    authors = metadata.get("authors") or [fallback_author]
    primary_author = authors[0] if authors else fallback_author
    article_id = pdf_path.stem

    page_text = _extract_page_text(pdf_path)
    lines_with_page: list[tuple[int, str]] = []
    for page_num, text in page_text:
        for line in text.splitlines():
            line = line.strip()
            if line:
                lines_with_page.append((page_num, line))

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
        doi=metadata.get("doi"),
        journal=metadata.get("journal"),
        publisher=metadata.get("publisher"),
        source_path=str(pdf_path),
        chunks=chunks,
        citations=citations,
    )
