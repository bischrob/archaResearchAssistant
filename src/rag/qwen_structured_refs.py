from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import tempfile

try:
    import fitz
except Exception:  # pragma: no cover - optional import for lightweight test environments
    fitz = None

from .anystyle_refs import parse_reference_strings_with_anystyle_docker
from .config import Settings
from .pdf_processing import Chunk, Citation, Section, STOPWORDS, TOKEN_RE, build_lines_with_page


REFERENCE_HEADING_RE = re.compile(
    r"^\s*(references|bibliography|works cited|literature cited|sources cited)\s*$",
    re.IGNORECASE,
)
HEADING_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'&/-]*")
REFERENCE_START_RE = re.compile(r"^(?:\[\d+\]\s*|\d+\.\s+)?[A-Z][A-Za-z .,'&-]+(?:\(|,)?\s*(?:19|20)\d{2}\b")
LEADING_REF_MARKER_RE = re.compile(r"^\s*(?:\[\d+\]|\d+[.)])\s+")
MERGED_MARKER_RE = re.compile(r"\[(\d+)\]\s")
TOC_DOTTED_RE = re.compile(r"\.{2,}\s*\d+\s*$")
PURE_PAGE_NUMBER_RE = re.compile(r"^\s*\d+\s*$")
TOC_HEADING_RE = re.compile(r"^\s*(contents|table of contents)\s*$", re.I)
FRONT_MATTER_HEADING_RE = re.compile(
    r"^\s*(title page|contents|table of contents|acknowledg(?:e)?ments?|list of tables|list of figures|copyright|figures?|tables?)\s*$",
    re.I,
)
PREFACE_HEADING_RE = re.compile(r"^\s*preface\s*$", re.I)
APPENDIX_HEADING_RE = re.compile(r"^\s*(appendix|appendixes|appendix\s+[a-z0-9ivxlc]+(?:[.:].*)?|appendix\s+[a-z0-9ivxlc]+\b.*)$", re.I)
BACK_MATTER_HEADING_RE = re.compile(
    r"^\s*(appendix|appendixes|list of tables|list of figures|tables?|figures?)\b",
    re.I,
)
NOISE_REFERENCE_RE = re.compile(
    r"(attention visualizations|<eos>|<pad>|^\s*references\s*$|^figure\s+\d+)",
    re.IGNORECASE,
)
TAIL_NOISE_RE = re.compile(
    r"(attention visualizations|<eos>|<pad>|\bfigure\s+\d+\s*:)",
    re.IGNORECASE,
)

SECTION_SYSTEM_PROMPT = (
    "You are segmenting academic PDF text by section headings. "
    "Input is candidate heading lines with absolute line indexes. "
    "Return JSON only with this schema: "
    '{"headings":[{"line_idx":12,"kind":"body","heading":"Methods"}],"reference_start_line":340}. '
    "Only include true section starts. "
    "Use kind values from {front_matter,preface,body,references,appendix}. "
    "Use kind='references' for bibliography/reference sections. "
    "If no reference start is visible, set reference_start_line to null."
)
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
class StructuredExtraction:
    chunks: list[Chunk]
    citations: list[Citation]
    reference_strings: list[str]
    sections: list[Section]


@dataclass
class SectionSpan:
    start_line: int
    end_line: int
    kind: str


def _extract_page_text(pdf_path: Path) -> list[tuple[int, str]]:
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF parsing.")
    out: list[tuple[int, str]] = []
    with fitz.open(pdf_path) as doc:
        for idx, page in enumerate(doc):
            text = page.get_text("text")
            if text and text.strip():
                out.append((idx + 1, text))
    return out


def _normalize_lookup_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


@lru_cache(maxsize=16)
def _ocr_text_index(root: str) -> dict[str, list[str]]:
    path = Path(root).resolve()
    if not path.exists() or not path.is_dir():
        return {}
    out: dict[str, list[str]] = {}
    for item in path.rglob("*.txt"):
        key = _normalize_lookup_key(item.stem)
        if not key:
            continue
        out.setdefault(key, []).append(str(item.resolve()))
    return out


def _candidate_ocr_dirs(settings: Settings) -> list[Path]:
    dirs: list[Path] = []
    for raw in [settings.paddleocr_text_dir, settings.paddleocr_text_fallback_dir]:
        if not raw:
            continue
        p = Path(raw).resolve()
        if p not in dirs:
            dirs.append(p)
    return dirs


def _locate_ocr_text(pdf_path: Path, settings: Settings) -> Path | None:
    pdf_key = _normalize_lookup_key(pdf_path.stem)
    if not pdf_key:
        return None

    for root in _candidate_ocr_dirs(settings):
        direct = root / f"{pdf_path.stem}.txt"
        if direct.exists() and direct.is_file():
            return direct

        index = _ocr_text_index(str(root))
        hits = index.get(pdf_key) or []
        if hits:
            return Path(hits[0])
    return None


def _extract_lines_with_page_from_ocr_text(ocr_text_path: Path) -> list[tuple[int, str]]:
    raw = ocr_text_path.read_text(encoding="utf-8", errors="ignore")
    lines = [line.strip() for line in raw.splitlines() if line and line.strip()]
    return [(1, line) for line in lines]


def _paddleocr_use_gpu(device: str) -> bool:
    d = (device or "").strip().lower()
    if d == "gpu":
        return True
    if d == "cpu":
        return False
    # auto: best effort
    try:
        import paddle  # type: ignore

        return bool(paddle.device.is_compiled_with_cuda())
    except Exception:
        return False


@lru_cache(maxsize=2)
def _build_paddleocr_pipeline(lang: str, device: str) -> object:
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:
        raise RuntimeError("PaddleOCR is not installed in this environment.") from exc

    use_gpu = _paddleocr_use_gpu(device)
    try:
        return PaddleOCR(
            lang=lang,
            device="gpu:0" if use_gpu else "cpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        return PaddleOCR(use_angle_cls=True, lang=lang, use_gpu=use_gpu)


def _extract_lines_from_paddle_page_payload(payload: object) -> list[str]:
    if not isinstance(payload, list):
        return []
    lines: list[str] = []
    for item in payload:
        if not isinstance(item, list) or len(item) < 2:
            continue
        line_payload = item[1]
        if isinstance(line_payload, list) and line_payload:
            text = str(line_payload[0]).strip()
            if text:
                lines.append(text)
    return lines


def _generate_ocr_text_with_paddle(pdf_path: Path, settings: Settings) -> str:
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is required for OCR text generation.")
    pipeline = _build_paddleocr_pipeline(settings.paddleocr_auto_lang, settings.paddleocr_auto_device)
    dpi = max(96, int(settings.paddleocr_auto_render_dpi))
    scale = dpi / 72.0
    collected: list[str] = []

    with fitz.open(pdf_path) as doc:
        with tempfile.TemporaryDirectory(prefix="paddleocr_pages_") as temp_dir:
            tmp = Path(temp_dir)
            for page_idx, page in enumerate(doc):
                image_path = tmp / f"page_{page_idx:05d}.png"
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                pix.save(str(image_path))
                payload = pipeline.ocr(str(image_path), cls=True)
                page_rows = payload if isinstance(payload, list) else []
                for line in _extract_lines_from_paddle_page_payload(page_rows):
                    if line:
                        collected.append(line)

    return "\n".join(collected).strip()


def _preferred_ocr_output_path(pdf_path: Path, settings: Settings) -> Path:
    roots = _candidate_ocr_dirs(settings)
    target_root = roots[0] if roots else Path("ocr/paddleocr/text").resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    return target_root / f"{pdf_path.stem}.txt"


def _generate_ocr_text_sidecar_if_missing(pdf_path: Path, settings: Settings) -> Path | None:
    if not settings.paddleocr_auto_generate_missing_text:
        return None
    try:
        body = _generate_ocr_text_with_paddle(pdf_path, settings)
    except Exception:
        return None
    if not body:
        return None
    out_path = _preferred_ocr_output_path(pdf_path, settings)
    out_path.write_text(body + "\n", encoding="utf-8")
    _ocr_text_index.cache_clear()
    return out_path


def _extract_lines_with_page(
    pdf_path: Path,
    *,
    settings: Settings,
    strip_page_noise: bool,
    preferred_text_path: Path | None = None,
) -> list[tuple[int, str]]:
    if preferred_text_path is not None and preferred_text_path.exists() and preferred_text_path.is_file():
        preferred_lines = _extract_lines_with_page_from_ocr_text(preferred_text_path)
        if preferred_lines:
            return preferred_lines
    if settings.paddleocr_prefer_text:
        ocr_path = _locate_ocr_text(pdf_path, settings)
        if ocr_path is None:
            ocr_path = _generate_ocr_text_sidecar_if_missing(pdf_path, settings)
        if ocr_path is not None:
            ocr_lines = _extract_lines_with_page_from_ocr_text(ocr_path)
            if ocr_lines:
                return ocr_lines

    page_text = _extract_page_text(pdf_path)
    return build_lines_with_page(page_text, strip_page_noise=strip_page_noise)


def _titlecase_ratio(text: str) -> float:
    words = [w for w in HEADING_WORD_RE.findall(text) if w]
    if not words:
        return 0.0
    titleish = sum(1 for w in words if w[:1].isupper())
    return titleish / max(1, len(words))


def _normalize_noise_key(text: str) -> str:
    clean = " ".join((text or "").split()).strip().lower()
    clean = re.sub(r"\b\d+\b", "", clean)
    clean = re.sub(r"[^a-z]+", " ", clean)
    return " ".join(clean.split())


def _is_probable_toc_line(text: str) -> bool:
    clean = " ".join((text or "").split()).strip()
    if not clean:
        return False
    if TOC_DOTTED_RE.search(clean):
        return True
    if clean.endswith(".") and len(clean.split()) <= 6:
        return True
    return False


def _toc_window(lines: list[str]) -> tuple[int, int] | None:
    for idx, raw in enumerate(lines):
        clean = " ".join((raw or "").split()).strip()
        if not TOC_HEADING_RE.match(clean):
            continue
        end = idx
        sparse = 0
        toc_hits = 0
        for probe in range(idx + 1, min(len(lines), idx + 120)):
            row = " ".join((lines[probe] or "").split()).strip()
            if not row:
                sparse += 1
                if sparse > 10 and (probe - idx) > 20:
                    break
                continue
            sparse = 0
            if _is_probable_toc_line(row):
                end = probe
                toc_hits += 1
                continue
            if len(row.split()) <= 7 and _titlecase_ratio(row) >= 0.60:
                end = probe
                continue
            if len(row.split()) <= 10 and row.isupper():
                end = probe
                continue
            if toc_hits >= 2:
                break
            if (probe - end) > 12:
                break
        if end > idx:
            return idx, end
    return None


def _clean_toc_entry(text: str) -> str:
    clean = " ".join((text or "").split()).strip()
    clean = re.sub(r"\.{2,}\s*\d+\s*$", "", clean).strip()
    clean = re.sub(r"\s+\d+\s*$", "", clean).strip()
    return clean


def _extract_toc_entries(lines: list[str]) -> list[str]:
    window = _toc_window(lines)
    if window is None:
        return []
    start, end = window
    entries: list[str] = []
    carry: list[str] = []
    for idx in range(start + 1, end + 1):
        row = " ".join((lines[idx] or "").split()).strip()
        if not row or PURE_PAGE_NUMBER_RE.fullmatch(row):
            continue
        if TOC_DOTTED_RE.search(row):
            clean = _clean_toc_entry(" ".join(carry + [row]))
            carry = []
            if clean and not TOC_HEADING_RE.match(clean):
                entries.append(clean)
            continue
        if len(row.split()) <= 14 and (_titlecase_ratio(row) >= 0.60 or row.isupper()):
            carry.append(row)
            continue
        carry = []
    out: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        key = _normalize_lookup_key(entry)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def _find_toc_entry_later_match(lines: list[str], entry: str) -> int | None:
    needle = _normalize_lookup_key(entry)
    if not needle:
        return None
    window = _toc_window(lines)
    toc_end = window[1] if window else -1
    for idx in range(toc_end + 1, len(lines)):
        row = " ".join((lines[idx] or "").split()).strip()
        if not row:
            continue
        row_key = _normalize_lookup_key(row)
        if not row_key:
            continue
        if needle == row_key or needle in row_key or row_key in needle:
            return idx
    return None


def _toc_mapped_heading_candidates(lines: list[str]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    seen: set[int] = set()
    for entry in _extract_toc_entries(lines):
        idx = _find_toc_entry_later_match(lines, entry)
        if idx is None or idx in seen:
            continue
        seen.add(idx)
        out.append((idx, entry[:120]))
    return sorted(out, key=lambda x: x[0])


def _toc_mapped_heading_index(lines: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for idx, heading in _toc_mapped_heading_candidates(lines):
        key = _normalize_lookup_key(heading)
        if key and key not in out:
            out[key] = idx
    return out


def _toc_mapped_reference_starts(lines: list[str]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for idx, heading in _toc_mapped_heading_candidates(lines):
        if not REFERENCE_HEADING_RE.match(_clean_toc_entry(heading)):
            continue
        if idx in seen:
            continue
        seen.add(idx)
        out.append(idx)
    return sorted(out)


def _is_toc_reference_heading(lines: list[str], idx: int) -> bool:
    start = max(0, idx - 4)
    end = min(len(lines), idx + 6)
    window = [" ".join((lines[pos] or "").split()).strip() for pos in range(start, end)]
    toc_like = 0
    short_numeric = 0
    prose_like = 0
    for row in window:
        if not row:
            continue
        if _is_probable_toc_line(row):
            toc_like += 1
        if PURE_PAGE_NUMBER_RE.fullmatch(row):
            short_numeric += 1
        if len(row.split()) >= 8 and not TOC_DOTTED_RE.search(row):
            prose_like += 1
    return (toc_like + short_numeric) >= 4 and prose_like == 0


def _repeated_heading_noise_indices(lines: list[str]) -> set[int]:
    by_key: dict[str, list[int]] = {}
    for idx, raw in enumerate(lines):
        clean = " ".join((raw or "").split()).strip()
        key = _normalize_noise_key(clean)
        if not key:
            continue
        words = key.split()
        if len(words) == 0 or len(words) > 6:
            continue
        alpha_chars = sum(1 for ch in clean if ch.isalpha())
        upper_chars = sum(1 for ch in clean if ch.isupper())
        titleish = _titlecase_ratio(clean)
        if alpha_chars and ((upper_chars / alpha_chars) >= 0.55 or titleish >= 0.70):
            by_key.setdefault(key, []).append(idx)

    noise: set[int] = set()
    for hits in by_key.values():
        if len(hits) < 3:
            continue
        # Keep the earliest occurrence as the most likely real section start and suppress later repeats.
        for idx in hits[1:]:
            noise.add(idx)
    return noise


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
    toc_window = _toc_window(lines)
    toc_mapped = _toc_mapped_heading_index(lines)
    repeated_noise = _repeated_heading_noise_indices(lines)
    for idx, raw in enumerate(lines):
        if toc_window is not None and toc_window[0] < idx <= toc_window[1]:
            continue
        if idx in repeated_noise:
            continue
        key = _normalize_lookup_key(raw)
        mapped_idx = toc_mapped.get(key)
        if mapped_idx is not None and idx < mapped_idx:
            continue
        if _is_heading_candidate(raw):
            out.append((idx, " ".join(raw.split())[:120]))
    out.extend(_toc_mapped_heading_candidates(lines))
    if out:
        dedup: dict[int, str] = {}
        for idx, text in out:
            dedup.setdefault(idx, text)
        out = sorted(dedup.items(), key=lambda x: x[0])
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
        clean = " ".join((raw or "").split()).strip()
        if REFERENCE_HEADING_RE.match(clean) and not _is_toc_reference_heading(lines, idx):
            return idx
    return None


def _heuristic_reference_starts(lines: list[str]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for idx in _toc_mapped_reference_starts(lines):
        if idx not in seen:
            seen.add(idx)
            out.append(idx)
    for idx, raw in enumerate(lines):
        clean = " ".join((raw or "").split()).strip()
        if REFERENCE_HEADING_RE.match(clean) and not _is_toc_reference_heading(lines, idx) and idx not in seen:
            seen.add(idx)
            out.append(idx)
    # Fallback for note-first/OCR text that has a bibliography tail without an explicit heading.
    # Require a run of likely author-year reference starts near the end of the document so body
    # prose with citations does not get misclassified as a references block.
    tail_start = max(0, len(lines) - 80)
    for idx in range(tail_start, len(lines)):
        clean = " ".join((lines[idx] or "").split()).strip()
        if idx in seen or not clean:
            continue
        if not (REFERENCE_START_RE.match(clean) or _looks_like_author_year_start(clean)):
            continue
        window_hits = 0
        for look_ahead in range(idx, min(len(lines), idx + 12)):
            probe = " ".join((lines[look_ahead] or "").split()).strip()
            if REFERENCE_START_RE.match(probe) or _looks_like_author_year_start(probe):
                window_hits += 1
        if window_hits >= 3:
            seen.add(idx)
            out.append(idx)
            break
    return out


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
    _ = settings
    if not lines:
        return [0], None
    heading_indices = sorted({0, *[idx for idx, _ in _heading_candidates(lines)]})
    ref_starts = _heuristic_reference_starts(lines)
    ref_start = min(ref_starts) if ref_starts else None
    if ref_start is not None and ref_start not in heading_indices:
        heading_indices.append(ref_start)
        heading_indices.sort()
    return heading_indices, ref_start


def detect_section_plan_details_with_qwen(
    lines: list[str],
    *,
    settings: Settings | None = None,
    min_section_lines: int = 24,
) -> tuple[list[dict[str, object]], list[SectionSpan], list[int]]:
    heading_indices, reference_start = detect_section_plan_with_qwen(lines, settings=settings)
    sections = _build_typed_sections(
        lines,
        heading_indices=heading_indices,
        reference_starts=_heuristic_reference_starts(lines),
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


def _classify_start_kind(lines: list[str], start: int, reference_starts: set[int], first_content_start: int) -> str:
    clean = " ".join((lines[start] or "").split()).strip()
    if start in reference_starts:
        return "references"
    if start < first_content_start:
        return "frontmatter"
    if PREFACE_HEADING_RE.match(clean):
        return "frontmatter"
    if APPENDIX_HEADING_RE.match(clean) or BACK_MATTER_HEADING_RE.match(clean):
        return "backmatter_other"
    return "body"


def _find_first_content_start(lines: list[str], starts: list[int], reference_starts: set[int]) -> int:
    for start in starts:
        clean = " ".join((lines[start] or "").split()).strip()
        if PREFACE_HEADING_RE.match(clean):
            return start
    for start in starts:
        clean = " ".join((lines[start] or "").split()).strip()
        if start in reference_starts:
            return start
        if PREFACE_HEADING_RE.match(clean):
            return start
        if FRONT_MATTER_HEADING_RE.match(clean):
            continue
        if APPENDIX_HEADING_RE.match(clean):
            continue
        if _is_probable_toc_line(clean) or PURE_PAGE_NUMBER_RE.fullmatch(clean):
            continue
        return start
    return 0


def _resolve_reference_boundaries(lines: list[str], starts: list[int], ref_set: set[int]) -> list[tuple[int, int]]:
    if not ref_set:
        return []
    ordered = sorted(starts)
    out: list[tuple[int, int]] = []
    for pos, start in enumerate(ordered):
        if start not in ref_set:
            continue
        end = len(lines) - 1
        for nxt in ordered[pos + 1 :]:
            clean = " ".join((lines[nxt] or "").split()).strip()
            if nxt in ref_set:
                end = nxt - 1
                break
            if APPENDIX_HEADING_RE.match(clean) or BACK_MATTER_HEADING_RE.match(clean):
                end = nxt - 1
                break
        if end >= start:
            out.append((start, end))
    return out


def _merge_short_sections(sections: list[SectionSpan], min_section_lines: int) -> list[SectionSpan]:
    if not sections:
        return sections
    merged: list[SectionSpan] = []
    for section in sections:
        length = section.end_line - section.start_line + 1
        should_merge = False
        if merged and section.kind == merged[-1].kind:
            if section.kind == "frontmatter":
                should_merge = True
            elif section.kind == "body" and length < min_section_lines:
                should_merge = True
        if should_merge:
            prev = merged[-1]
            merged[-1] = SectionSpan(start_line=prev.start_line, end_line=section.end_line, kind=prev.kind)
            continue
        merged.append(section)
    return merged


def _build_typed_sections(
    lines: list[str],
    *,
    heading_indices: list[int],
    reference_starts: list[int],
    reference_start: int | None,
    min_section_lines: int = 24,
) -> list[SectionSpan]:
    total_lines = len(lines)
    if total_lines <= 0:
        return []
    ref_set = {idx for idx in reference_starts if 0 <= idx < total_lines}
    if reference_start is not None and 0 <= reference_start < total_lines:
        ref_set.add(reference_start)
    starts = sorted({x for x in heading_indices if 0 <= x < total_lines} | ref_set | {0})
    first_content_start = _find_first_content_start(lines, starts, ref_set)
    ref_bounds = {s: e for s, e in _resolve_reference_boundaries(lines, starts, ref_set)}
    sections: list[SectionSpan] = []
    for idx, start in enumerate(starts):
        end = (starts[idx + 1] - 1) if (idx + 1) < len(starts) else (total_lines - 1)
        if end < start:
            continue
        kind = _classify_start_kind(lines, start, ref_set, first_content_start)
        if kind == "references":
            end = min(end, ref_bounds.get(start, end))
        sections.append(SectionSpan(start_line=start, end_line=end, kind=kind))
    return _merge_short_sections(sections, min_section_lines=min_section_lines)


def _heading_for_section(lines: list[str], start_line: int, kind: str) -> str:
    clean = " ".join((lines[start_line] or "").split()).strip()
    if clean:
        return clean[:120]
    defaults = {"frontmatter": "Front Matter", "body": "Body", "references": "References", "backmatter_other": "Back Matter"}
    return defaults.get(kind, "Section")


def _build_section_metadata(article_id: str, lines_with_page: list[tuple[int, str]], sections: list[SectionSpan]) -> list[Section]:
    lines = [line for _, line in lines_with_page]
    out: list[Section] = []
    for section in sections:
        segment = lines_with_page[section.start_line : section.end_line + 1]
        if segment:
            page_start = segment[0][0]
            page_end = segment[-1][0]
        else:
            page_start = 1
            page_end = 1
        out.append(Section(
            section_id=f"{article_id}::section::{section.start_line}",
            kind=section.kind,
            start_line=section.start_line,
            end_line=section.end_line,
            page_start=page_start,
            page_end=page_end,
            heading=_heading_for_section(lines, section.start_line, section.kind),
        ))
    return out


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
    sections: list[tuple[int, int, str, str | None]],
    chunk_size_words: int,
    chunk_overlap_words: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    chunk_idx = 0
    for start, end, kind, heading in sections:
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
                    section_type=kind,
                    section_id=f"{article_id}::section::{start}",
                    section_label=heading,
                )
            )
            chunk_idx += 1
    return chunks


def _looks_like_author_year_start(line: str) -> bool:
    clean = (line or "").strip()
    if not clean:
        return False
    if not re.search(r"\b(?:19|20)\d{2}\b", clean):
        return False
    if not re.match(r"^[A-Z][A-Za-z'`-]+,\s+", clean):
        return False
    return True


def _heuristic_reference_split(reference_text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", x).strip() for x in (reference_text or "").splitlines() if x and x.strip()]
    if not lines:
        return []
    blocks: list[str] = []
    current: list[str] = []
    for line in lines:
        starts_new = REFERENCE_START_RE.match(line) or _looks_like_author_year_start(line)
        if starts_new and current:
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


def _clean_reference_row(row: str) -> str:
    return " ".join((row or "").split()).strip()


def _split_numbered_rows(text: str) -> list[str]:
    parts = re.split(r"(?=\[\d+\]\s)", text or "")
    out: list[str] = []
    for part in parts:
        clean = _clean_reference_row(part)
        if clean:
            out.append(clean)
    return out


def _drop_leading_marker(text: str) -> str:
    return LEADING_REF_MARKER_RE.sub("", (text or "").strip())


def _sanitize_reference_rows(rows: list[str]) -> list[str]:
    cleaned: list[str] = []
    for row in rows:
        text = _clean_reference_row(row)
        if not text or len(text) < 12:
            continue
        noise_match = TAIL_NOISE_RE.search(text)
        if noise_match:
            text = _clean_reference_row(text[: noise_match.start()])
            if not text or len(text) < 12:
                continue
        if NOISE_REFERENCE_RE.fullmatch(text):
            continue
        marker_count = len(MERGED_MARKER_RE.findall(text))
        if marker_count > 1:
            cleaned.extend(_split_numbered_rows(text))
            continue
        cleaned.append(text)

    out: list[str] = []
    seen: set[str] = set()
    for row in cleaned:
        compact = _drop_leading_marker(_clean_reference_row(row))
        if not compact or len(compact) < 12:
            continue
        if NOISE_REFERENCE_RE.search(compact):
            continue
        key = compact.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(compact)
    return out


def _looks_invalid_split(rows: list[str], source_block: str) -> bool:
    if not rows:
        return True
    noise_rows = sum(1 for row in rows if NOISE_REFERENCE_RE.search(row))
    if noise_rows > 0:
        return True
    suspicious = sum(
        1
        for row in rows
        if ("references" in row.lower() or "figure" in row.lower())
        and not re.search(r"\b(?:19|20)\d{2}\b", row)
    )
    if suspicious > 0:
        return True
    marker_hits = len(re.findall(r"\[\d+\]\s", source_block or ""))
    if marker_hits >= 8 and len(rows) <= max(2, marker_hits // 6):
        return True
    return False


def split_reference_strings_heuristic(reference_text: str) -> list[str]:
    numbered = _sanitize_reference_rows(_split_numbered_rows(reference_text))
    if len(MERGED_MARKER_RE.findall(reference_text or "")) > 0 and numbered:
        return numbered
    return _sanitize_reference_rows(_heuristic_reference_split(reference_text))


def split_reference_strings_with_qwen(reference_text: str, *, settings: Settings | None = None) -> list[str]:
    _ = settings
    return split_reference_strings_heuristic(reference_text)


def split_reference_strings_for_anystyle(reference_text: str, *, settings: Settings | None = None) -> list[str]:
    heuristic = split_reference_strings_heuristic(reference_text)
    if not _looks_invalid_split(heuristic, reference_text):
        return heuristic
    return split_reference_strings_with_qwen(reference_text, settings=settings)


def _write_references_sidecar(pdf_path: Path, reference_strings: list[str]) -> Path | None:
    sidecar = pdf_path.with_suffix('.references.txt')
    body = "\n".join(x.strip() for x in reference_strings if (x or '').strip()).strip()
    if not body:
        if sidecar.exists():
            sidecar.unlink()
        return None
    sidecar.write_text(body + "\n", encoding="utf-8")
    return sidecar


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
    headings, sections, _ = detect_section_plan_details_with_qwen(lines, settings=settings)
    section_rows = _build_section_metadata(article_id, lines_with_page, sections)
    chunks = _build_body_chunks(
        article_id=article_id,
        lines_with_page=lines_with_page,
        sections=[(x.start_line, x.end_line, x.kind, next((s.heading for s in section_rows if s.start_line == x.start_line), None)) for x in sections],
        chunk_size_words=chunk_size_words,
        chunk_overlap_words=chunk_overlap_words,
    )

    reference_chunks: list[str] = []
    for section in sections:
        if section.kind != "references":
            continue
        block = "\n".join(lines[section.start_line : section.end_line + 1]).strip()
        if block:
            reference_chunks.append(block)

    reference_strings: list[str] = []
    if references_sidecar_path is not None and references_sidecar_path.exists() and references_sidecar_path.is_file():
        reference_strings = [line.strip() for line in references_sidecar_path.read_text(encoding='utf-8', errors='ignore').splitlines() if line.strip()]
    else:
        for block in reference_chunks:
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
