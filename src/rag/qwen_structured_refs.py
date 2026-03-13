from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import fitz

from .anystyle_refs import parse_reference_strings_with_anystyle_docker
from .config import Settings
from .pdf_processing import Chunk, Citation, STOPWORDS, TOKEN_RE, build_lines_with_page
from .qwen_local import decode_qwen_json, generate_with_qwen


REFERENCE_HEADING_RE = re.compile(
    r"^\s*(references|bibliography|works cited|literature cited|sources cited)\s*$",
    re.IGNORECASE,
)
HEADING_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'&/-]*")
REFERENCE_START_RE = re.compile(r"^(?:\[\d+\]\s*|\d+\.\s+)?[A-Z][A-Za-z .,'&-]+(?:\(|,)?\s*(?:19|20)\d{2}\b")

SECTION_SYSTEM_PROMPT = (
    "You are segmenting academic PDF text by section headings. "
    "Input is candidate heading lines with absolute line indexes. "
    "Return JSON only with this schema: "
    '{"headings":[{"line_idx":12,"kind":"body","heading":"Methods"}],"reference_start_line":340}. '
    "Only include true section starts. "
    "Use kind='references' for bibliography/reference sections. "
    "If no reference start is visible, set reference_start_line to null."
)
REFERENCE_SPLIT_SYSTEM_PROMPT = (
    "You split bibliography text into individual references. "
    'Return JSON only with this schema: {"references":["<one reference>", "<one reference>"]}. '
    "Do not add commentary and do not invent text."
)


@dataclass
class StructuredExtraction:
    chunks: list[Chunk]
    citations: list[Citation]
    reference_strings: list[str]


def _extract_page_text(pdf_path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    with fitz.open(pdf_path) as doc:
        for idx, page in enumerate(doc):
            text = page.get_text("text")
            if text and text.strip():
                out.append((idx + 1, text))
    return out


def _titlecase_ratio(text: str) -> float:
    words = [w for w in HEADING_WORD_RE.findall(text) if w]
    if not words:
        return 0.0
    titleish = sum(1 for w in words if w[:1].isupper())
    return titleish / max(1, len(words))


def _is_heading_candidate(line: str) -> bool:
    clean = " ".join((line or "").split()).strip()
    if not clean:
        return False
    if REFERENCE_HEADING_RE.match(clean):
        return True
    if len(clean) < 3 or len(clean) > 120:
        return False
    if clean.endswith("."):
        return False
    words = HEADING_WORD_RE.findall(clean)
    if not words or len(words) > 14:
        return False
    upper = sum(1 for ch in clean if ch.isupper())
    alpha = sum(1 for ch in clean if ch.isalpha())
    upper_ratio = (upper / alpha) if alpha else 0.0
    if upper_ratio >= 0.60:
        return True
    return _titlecase_ratio(clean) >= 0.70


def _heading_candidates(lines: list[str], max_candidates: int = 160) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for idx, raw in enumerate(lines):
        if _is_heading_candidate(raw):
            out.append((idx, " ".join(raw.split())[:120]))
    if not out:
        out = [(0, "Document Start")]
    if out[0][0] != 0:
        out = [(0, lines[0][:120] if lines else "Document Start")] + out

    if len(out) > max_candidates:
        front = out[: max_candidates // 2]
        back = out[-(max_candidates - len(front)) :]
        merged = front + back
        seen: set[int] = set()
        out = []
        for idx, line in merged:
            if idx in seen:
                continue
            seen.add(idx)
            out.append((idx, line))
        out.sort(key=lambda x: x[0])
    return out


def _heuristic_reference_start(lines: list[str]) -> int | None:
    for idx, raw in enumerate(lines):
        if REFERENCE_HEADING_RE.match(" ".join((raw or "").split()).strip()):
            return idx
    return None


def _parse_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _line_idx_from_row(row: dict) -> int | None:
    for key in ("line_idx", "line", "start_line", "start", "idx", "index"):
        idx = _parse_int(row.get(key))
        if idx is not None:
            return idx
    return None


def detect_section_plan_with_qwen(lines: list[str], *, settings: Settings | None = None) -> tuple[list[int], int | None]:
    cfg = settings or Settings()
    if not lines:
        return [0], None

    candidates = _heading_candidates(lines)
    payload = [{"idx": idx, "line": text} for idx, text in candidates]
    user = (
        "Candidate heading lines as JSON:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Return only JSON in the required schema."
    )
    parsed = None
    try:
        raw = generate_with_qwen(
            messages=[
                {"role": "system", "content": SECTION_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            settings=cfg,
            task="citation",
            max_new_tokens=max(256, min(int(cfg.qwen_citation_max_new_tokens), 768)),
            temperature=0.0,
        )
        parsed = decode_qwen_json(raw)
    except Exception:
        parsed = None

    heading_indices: set[int] = {0}
    ref_start: int | None = None

    if isinstance(parsed, dict):
        rows = parsed.get("headings") or parsed.get("sections") or []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                idx = _line_idx_from_row(row)
                if idx is None or idx < 0 or idx >= len(lines):
                    continue
                heading_indices.add(idx)
                kind = str(row.get("kind") or "").strip().lower()
                if kind == "references":
                    if ref_start is None or idx < ref_start:
                        ref_start = idx
        ref_candidate = _parse_int(
            parsed.get("reference_start_line")
            or parsed.get("references_start_line")
            or parsed.get("reference_start")
        )
        if ref_candidate is not None and 0 <= ref_candidate < len(lines):
            ref_start = ref_candidate if ref_start is None else min(ref_start, ref_candidate)

    heuristic_ref = _heuristic_reference_start(lines)
    if ref_start is None:
        ref_start = heuristic_ref
    elif heuristic_ref is not None:
        ref_start = min(ref_start, heuristic_ref)
    if ref_start is not None:
        heading_indices.add(ref_start)

    return sorted(heading_indices), ref_start


def _build_sections(total_lines: int, heading_indices: list[int], reference_start: int | None) -> list[tuple[int, int, str]]:
    if total_lines <= 0:
        return []
    starts = sorted({x for x in heading_indices if 0 <= x < total_lines} | {0})
    sections: list[tuple[int, int, str]] = []
    for idx, start in enumerate(starts):
        end = (starts[idx + 1] - 1) if (idx + 1) < len(starts) else (total_lines - 1)
        if end < start:
            continue
        kind = "references" if (reference_start is not None and start >= reference_start) else "body"
        sections.append((start, end, kind))
    return sections


def _word_spans(length: int, size: int, overlap: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start = 0
    while start < length:
        end = min(start + size, length)
        out.append((start, end))
        if end == length:
            break
        start = max(0, end - overlap)
    return out


def _tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in TOKEN_RE.findall(text or "")]
    return [t for t in tokens if len(t) > 1 and t not in STOPWORDS]


def _build_body_chunks(
    article_id: str,
    lines_with_page: list[tuple[int, str]],
    sections: list[tuple[int, int, str]],
    chunk_size_words: int,
    chunk_overlap_words: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    chunk_idx = 0
    for start, end, kind in sections:
        if kind != "body":
            continue
        words_with_page: list[tuple[str, int]] = []
        for page_num, line in lines_with_page[start : end + 1]:
            for word in line.split():
                words_with_page.append((word, page_num))
        if not words_with_page:
            continue
        words = [w for w, _ in words_with_page]
        for span_start, span_end in _word_spans(
            len(words),
            max(32, int(chunk_size_words)),
            max(0, int(chunk_overlap_words)),
        ):
            chunk_words = words[span_start:span_end]
            if not chunk_words:
                continue
            text = " ".join(chunk_words).strip()
            token_list = _tokenize(text)
            counts = Counter(token_list)
            chunks.append(
                Chunk(
                    chunk_id=f"{article_id}::chunk::{chunk_idx}",
                    index=chunk_idx,
                    text=text,
                    tokens=sorted(counts.keys()),
                    token_counts=dict(counts),
                    page_start=words_with_page[span_start][1],
                    page_end=words_with_page[span_end - 1][1],
                )
            )
            chunk_idx += 1
    return chunks


def _heuristic_reference_split(reference_text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", x).strip() for x in (reference_text or "").splitlines() if x and x.strip()]
    if not lines:
        return []
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        if REFERENCE_START_RE.match(line) and current:
            blocks.append(" ".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(" ".join(current).strip())
    return [x for x in blocks if len(x) > 12]


def _reference_windows(reference_text: str, max_chars: int) -> list[str]:
    lines = [x.strip() for x in (reference_text or "").splitlines() if x and x.strip()]
    if not lines:
        return []
    windows: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for line in lines:
        add = len(line) + 1
        if cur and (cur_len + add) > max_chars:
            windows.append("\n".join(cur))
            cur = [line]
            cur_len = add
        else:
            cur.append(line)
            cur_len += add
    if cur:
        windows.append("\n".join(cur))
    return windows


def _parse_reference_rows(payload: object) -> list[str]:
    rows: list[str] = []
    if isinstance(payload, dict):
        payload = payload.get("references")
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                rows.append(item)
                continue
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("reference") or item.get("raw") or "").strip()
                if text:
                    rows.append(text)
    return rows


def split_reference_strings_with_qwen(reference_text: str, *, settings: Settings | None = None) -> list[str]:
    cfg = settings or Settings()
    max_input_chars = max(1200, int(cfg.qwen_max_input_chars * 0.78))
    windows = _reference_windows(reference_text, max_chars=max_input_chars)
    if not windows:
        return []

    out: list[str] = []
    for block in windows:
        user = (
            "Split the bibliography text below into one item per full reference.\n"
            "Return JSON only in the required schema.\n\n"
            f"Bibliography text:\n{block}"
        )
        parsed = None
        try:
            raw = generate_with_qwen(
                messages=[
                    {"role": "system", "content": REFERENCE_SPLIT_SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                settings=cfg,
                task="citation",
                max_new_tokens=max(256, min(int(cfg.qwen_citation_max_new_tokens), 900)),
                temperature=0.0,
            )
            parsed = decode_qwen_json(raw)
        except Exception:
            parsed = None

        refs = _parse_reference_rows(parsed)
        if not refs:
            refs = _heuristic_reference_split(block)
        out.extend(refs)

    deduped: list[str] = []
    seen: set[str] = set()
    for row in out:
        clean = " ".join((row or "").split()).strip()
        if len(clean) < 12:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(clean)
    return deduped


def extract_structured_chunks_and_citations(
    *,
    pdf_path: Path,
    article_id: str,
    settings: Settings,
    chunk_size_words: int,
    chunk_overlap_words: int,
    strip_page_noise: bool,
) -> StructuredExtraction:
    page_text = _extract_page_text(pdf_path)
    lines_with_page = build_lines_with_page(page_text, strip_page_noise=strip_page_noise)
    if not lines_with_page:
        return StructuredExtraction(chunks=[], citations=[], reference_strings=[])

    lines = [line for _, line in lines_with_page]
    heading_indices, reference_start = detect_section_plan_with_qwen(lines, settings=settings)
    sections = _build_sections(len(lines), heading_indices=heading_indices, reference_start=reference_start)
    chunks = _build_body_chunks(
        article_id=article_id,
        lines_with_page=lines_with_page,
        sections=sections,
        chunk_size_words=chunk_size_words,
        chunk_overlap_words=chunk_overlap_words,
    )

    reference_chunks: list[str] = []
    for start, end, kind in sections:
        if kind != "references":
            continue
        block = "\n".join(lines[start : end + 1]).strip()
        if block:
            reference_chunks.append(block)

    reference_strings: list[str] = []
    for block in reference_chunks:
        reference_strings.extend(split_reference_strings_with_qwen(block, settings=settings))

    citations = parse_reference_strings_with_anystyle_docker(
        reference_strings,
        article_id=article_id,
        compose_service=settings.anystyle_service,
        timeout_seconds=settings.anystyle_timeout_seconds,
        use_gpu=settings.anystyle_use_gpu,
        gpu_devices=settings.anystyle_gpu_devices,
        gpu_service=settings.anystyle_gpu_service,
    )
    return StructuredExtraction(
        chunks=chunks,
        citations=citations,
        reference_strings=reference_strings,
    )
