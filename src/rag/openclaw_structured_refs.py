from __future__ import annotations

import re
from pathlib import Path

from .config import Settings
from .openclaw_agent import invoke_openclaw_agent
from .anystyle_refs import parse_reference_strings_with_anystyle_docker
from .qwen_structured_refs import (
    APPENDIX_HEADING_RE,
    BACK_MATTER_HEADING_RE,
    NOISE_REFERENCE_RE,
    REFERENCE_HEADING_RE,
    SectionSpan,
    StructuredExtraction,
    TAIL_NOISE_RE,
    _build_body_chunks,
    _build_section_metadata,
    _build_typed_sections,
    _extract_lines_with_page,
    _heading_candidates,
    _heuristic_reference_split,
    _heuristic_reference_starts,
    _looks_invalid_split,
    _parse_reference_rows,
    _sanitize_reference_rows,
    _write_references_sidecar,
)

GENERIC_BRACKET_MARKER_RE = re.compile(r"\[[^\]\s]{1,24}\]\s")
GENERIC_BRACKET_SPLIT_RE = re.compile(r"(?=\[[^\]\s]{1,24}\]\s)")
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
APPENDIX_STYLE_HEADING_RE = re.compile(r"^(?:[A-Z](?:\.\d+)?|[IVX]+(?:\.\d+)?)\s+[A-Z].*")
SUSPICIOUS_REFERENCE_TAIL_RE = re.compile(
    r"^(?:[A-Z](?:\.\d+)?\s+[A-Z].*|Figure\s+[A-Z]\.\d|<\|endofprompt\|>|C:\\\\|Hydra\b|Microsoft Windows \[Version|F\.\d+|G Supplementary Materials)",
    re.IGNORECASE,
)
SUSPICIOUS_REFERENCE_ROW_TAIL_RE = re.compile(
    r"(?:\bA GPT-4 has common sense grounding\b|Figure\s+[A-Z]\.\d|<\|endofprompt\|>|Microsoft Windows \[Version|\bHydra\b|C:\\Zoo>|\bG Supplementary Materials\b)",
    re.IGNORECASE,
)
TAIL_AGENT_MIN_TRIGGER_LINES = 6
TAIL_AGENT_WINDOW_LINES = 80
TAIL_AGENT_CONTEXT_LINES = 12


def _is_reference_like_line(line: str) -> bool:
    clean = " ".join((line or "").split()).strip()
    if not clean:
        return False
    if REFERENCE_HEADING_RE.match(clean):
        return True
    if GENERIC_BRACKET_MARKER_RE.match(clean):
        return True
    if YEAR_RE.search(clean) and (clean.startswith("[") or re.match(r"^(?:\d+[.)]\s+)?[A-Z]", clean)):
        return True
    return False


def _fallback_reference_start(lines: list[str]) -> int | None:
    if len(lines) < 4:
        return None
    start_floor = max(0, int(len(lines) * 0.45))
    best_idx: int | None = None
    best_score = 0.0
    for idx in range(start_floor, len(lines)):
        if not _is_reference_like_line(lines[idx]):
            continue
        window = lines[idx : min(len(lines), idx + 24)]
        score = sum(1 for row in window if _is_reference_like_line(row)) / max(1, len(window))
        if score >= 0.45 and score > best_score:
            best_idx = idx
            best_score = score
    return best_idx


def _prune_heading_indices_after_reference_start(lines: list[str], heading_indices: list[int], reference_start: int | None) -> list[int]:
    if reference_start is None:
        return heading_indices
    kept: list[int] = []
    for idx in sorted(set(heading_indices)):
        if idx <= reference_start:
            kept.append(idx)
            continue
        clean = " ".join((lines[idx] or "").split()).strip()
        if APPENDIX_HEADING_RE.match(clean) or BACK_MATTER_HEADING_RE.match(clean) or APPENDIX_STYLE_HEADING_RE.match(clean) or REFERENCE_HEADING_RE.match(clean):
            kept.append(idx)
    return kept


def detect_section_plan(lines: list[str], *, settings: Settings | None = None) -> tuple[list[int], int | None]:
    _ = settings
    if not lines:
        return [0], None
    heading_indices = sorted({0, *[idx for idx, _ in _heading_candidates(lines)]})
    explicit_ref_starts = [idx for idx, raw in enumerate(lines) if REFERENCE_HEADING_RE.match(" ".join((raw or "").split()).strip())]
    ref_starts = sorted({*_heuristic_reference_starts(lines), *explicit_ref_starts})
    if not ref_starts:
        fallback = _fallback_reference_start(lines)
        if fallback is not None:
            ref_starts = [fallback]
    ref_start = min(ref_starts) if ref_starts else None
    heading_indices = _prune_heading_indices_after_reference_start(lines, heading_indices, ref_start)
    if ref_start is not None and ref_start not in heading_indices:
        heading_indices.append(ref_start)
        heading_indices.sort()
    return heading_indices, ref_start


def detect_section_plan_details(
    lines: list[str],
    *,
    settings: Settings | None = None,
    min_section_lines: int = 24,
) -> tuple[list[dict[str, object]], list[SectionSpan], list[int]]:
    heading_indices, reference_start = detect_section_plan(lines, settings=settings)
    reference_starts = sorted({*(_heuristic_reference_starts(lines)), *(([reference_start] if reference_start is not None else []))})
    sections = _build_typed_sections(
        lines,
        heading_indices=heading_indices,
        reference_starts=reference_starts,
        reference_start=reference_start,
        min_section_lines=min_section_lines,
    )
    headings: list[dict[str, object]] = []
    seen: set[int] = set()
    for section in sections:
        if section.start_line in seen:
            continue
        seen.add(section.start_line)
        label = " ".join((lines[section.start_line] or "").split()).strip()[:120] if lines else ""
        if not label:
            if section.kind == "frontmatter":
                label = "Front Matter"
            elif section.kind == "references":
                label = "References"
            else:
                label = "Document Start"
        headings.append({"line_idx": section.start_line, "kind": section.kind, "heading": label})
    ref_blocks = [section.start_line for section in sections if section.kind == "references"]
    return headings, sections, ref_blocks




def _parse_last_reference_line(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("last_reference_line", "last_reference_idx", "last_line", "end_line", "line_idx", "line", "idx", "index"):
        idx = payload.get(key)
        if isinstance(idx, int):
            return idx
        if isinstance(idx, str) and idx.strip().isdigit():
            return int(idx.strip())
    return None


def _find_suspicious_tail_start(block_lines: list[str]) -> int | None:
    if len(block_lines) < TAIL_AGENT_MIN_TRIGGER_LINES:
        return None
    first_hit: int | None = None
    for idx, line in enumerate(block_lines):
        compact = " ".join((line or "").split()).strip()
        if not compact:
            continue
        if SUSPICIOUS_REFERENCE_TAIL_RE.match(compact):
            first_hit = idx
            break
    if first_hit is not None:
        return first_hit

    probe_start = max(0, len(block_lines) - TAIL_AGENT_WINDOW_LINES)
    probe = block_lines[probe_start:]
    bad_run = 0
    for offset, line in enumerate(probe):
        compact = " ".join((line or "").split()).strip()
        if not compact:
            continue
        reference_like = _is_reference_like_line(compact) or bool(YEAR_RE.search(compact))
        if reference_like:
            bad_run = 0
            continue
        bad_run += 1
        if bad_run >= TAIL_AGENT_MIN_TRIGGER_LINES:
            return probe_start + offset - bad_run + 1
    return None


def _trim_reference_block_lines_with_openclaw_agent(block_lines: list[str], *, settings: Settings | None = None) -> list[str]:
    suspicious_start = _find_suspicious_tail_start(block_lines)
    if suspicious_start is None:
        return block_lines

    context_start = max(0, suspicious_start - TAIL_AGENT_CONTEXT_LINES)
    numbered_lines = [
        {"line_idx": idx, "text": " ".join((block_lines[idx] or "").split()).strip()}
        for idx in range(context_start, len(block_lines))
        if " ".join((block_lines[idx] or "").split()).strip()
    ]
    if len(numbered_lines) < TAIL_AGENT_MIN_TRIGGER_LINES:
        return block_lines[:suspicious_start]

    payload = {
        "instruction": "Find the last line that still belongs to the bibliography. Return JSON only.",
        "suspicious_start_line": suspicious_start,
        "tail_lines": numbered_lines,
    }
    try:
        response = invoke_openclaw_agent("reference_tail_trim", payload, settings=settings, timeout=180)
    except Exception:
        response = None
    last_reference_line = _parse_last_reference_line(response)
    if last_reference_line is None:
        return block_lines[:suspicious_start]
    if last_reference_line < 0:
        return []
    if last_reference_line >= len(block_lines):
        return block_lines
    if last_reference_line + 1 < suspicious_start - 2:
        return block_lines[:suspicious_start]
    return block_lines[: last_reference_line + 1]

def _split_generic_bracket_rows(text: str) -> list[str]:
    parts = GENERIC_BRACKET_SPLIT_RE.split(text or "")
    return [part.strip() for part in parts if (part or "").strip()]


def _trim_reference_row_tail(row: str) -> str:
    clean = " ".join((row or "").split()).strip()
    match = SUSPICIOUS_REFERENCE_ROW_TAIL_RE.search(clean)
    if match:
        clean = clean[: match.start()].strip()
    return clean


def _finalize_reference_rows(rows: list[str]) -> list[str]:
    out: list[str] = []
    for row in rows:
        clean = _trim_reference_row_tail(row)
        if clean and YEAR_RE.search(clean):
            out.append(clean)
    return out


def split_reference_strings_heuristic(reference_text: str) -> list[str]:
    generic_bracketed = _finalize_reference_rows(_sanitize_reference_rows(_split_generic_bracket_rows(reference_text)))
    if len(GENERIC_BRACKET_MARKER_RE.findall(reference_text or "")) >= 2 and generic_bracketed:
        return generic_bracketed
    return _finalize_reference_rows(_sanitize_reference_rows(_heuristic_reference_split(reference_text)))


def split_reference_strings_with_openclaw_agent(reference_text: str, *, settings: Settings | None = None) -> list[str]:
    payload = {
        "instruction": "Reconstruct this references block into one reference per line. Preserve order. Return JSON with a top-level 'references' array only.",
        "reference_block": reference_text,
    }
    response = invoke_openclaw_agent("reference_split", payload, settings=settings, timeout=180)
    if not response:
        return []
    rows = _parse_reference_rows(response)
    return _finalize_reference_rows(_sanitize_reference_rows(rows))


def split_reference_strings_for_anystyle(reference_text: str, *, settings: Settings | None = None) -> list[str]:
    heuristic = split_reference_strings_heuristic(reference_text)
    generic_markers = len(GENERIC_BRACKET_MARKER_RE.findall(reference_text or ""))
    too_few_for_markers = generic_markers >= 8 and len(heuristic) <= max(2, generic_markers // 6)
    if not _looks_invalid_split(heuristic, reference_text) and not too_few_for_markers:
        return heuristic
    repaired = split_reference_strings_with_openclaw_agent(reference_text, settings=settings)
    if repaired:
        return repaired
    return heuristic


def _reference_block_text(lines: list[str], section: SectionSpan, *, settings: Settings | None = None) -> str:
    block_lines = lines[section.start_line : section.end_line + 1]
    if block_lines and REFERENCE_HEADING_RE.match(" ".join((block_lines[0] or "").split()).strip()):
        block_lines = block_lines[1:]
    cleaned: list[str] = []
    generic_marker_count = sum(1 for line in block_lines if GENERIC_BRACKET_MARKER_RE.match(" ".join((line or "").split()).strip()))
    seen_generic_markers = 0
    for line in block_lines:
        compact = " ".join((line or "").split()).strip()
        if not compact:
            continue
        if GENERIC_BRACKET_MARKER_RE.match(compact):
            seen_generic_markers += 1
        if generic_marker_count >= 8 and seen_generic_markers >= 5 and SUSPICIOUS_REFERENCE_TAIL_RE.match(compact):
            break
        if NOISE_REFERENCE_RE.fullmatch(compact):
            continue
        noise_match = TAIL_NOISE_RE.search(compact)
        if noise_match:
            compact = compact[: noise_match.start()].strip()
        if compact:
            cleaned.append(compact)
    cleaned = _trim_reference_block_lines_with_openclaw_agent(cleaned, settings=settings)
    return "\n".join(cleaned).strip()


def extract_structured_chunks_and_citations(
    *,
    pdf_path: Path,
    article_id: str,
    settings: Settings,
    chunk_size_words: int,
    chunk_overlap_words: int,
    strip_page_noise: bool,
    preferred_text_path: Path | None = None,
    references_sidecar_path: Path | None = None,
) -> StructuredExtraction:
    lines_with_page = _extract_lines_with_page(
        pdf_path,
        settings=settings,
        strip_page_noise=strip_page_noise,
        preferred_text_path=preferred_text_path,
    )
    if not lines_with_page:
        return StructuredExtraction(chunks=[], citations=[], reference_strings=[], sections=[])

    lines = [line for _, line in lines_with_page]
    _headings, sections, _ = detect_section_plan_details(lines, settings=settings)
    section_rows = _build_section_metadata(article_id, lines_with_page, sections)
    chunks = _build_body_chunks(
        article_id=article_id,
        lines_with_page=lines_with_page,
        sections=[(x.start_line, x.end_line, x.kind, next((s.heading for s in section_rows if s.start_line == x.start_line), None)) for x in sections],
        chunk_size_words=chunk_size_words,
        chunk_overlap_words=chunk_overlap_words,
    )

    reference_strings: list[str] = []
    if references_sidecar_path is not None and references_sidecar_path.exists() and references_sidecar_path.is_file():
        reference_strings = [line.strip() for line in references_sidecar_path.read_text(encoding='utf-8', errors='ignore').splitlines() if line.strip()]
    else:
        for section in sections:
            if section.kind != "references":
                continue
            block = _reference_block_text(lines, section, settings=settings)
            if block:
                reference_strings.extend(split_reference_strings_for_anystyle(block, settings=settings))

    _write_references_sidecar(pdf_path, reference_strings)
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
        sections=section_rows,
    )
