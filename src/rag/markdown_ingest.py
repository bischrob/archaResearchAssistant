from __future__ import annotations

from dataclasses import dataclass
import re


HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'/-]*")
REFERENCE_HEADING_VARIANTS = {
    "references",
    "bibliography",
    "works cited",
    "references cited",
    "literature cited",
    "cited references",
    "reference list",
}
REFERENCE_ENTRY_START_RE = re.compile(
    r"^\s*(?:\[\d+\]|\d+[.)])?\s*(?:[A-Z][A-Za-z'`-]+(?:,\s*[A-Z][A-Za-z'`-]+)*|\w.+?)\s*(?:\(|,)?\s*(?:19|20)\d{2}\b"
)


@dataclass(frozen=True)
class MarkdownSection:
    heading_path: list[str]
    lines: list[str]
    start_line: int
    end_line: int


@dataclass(frozen=True)
class MarkdownChunk:
    text: str
    heading_path: list[str]
    token_count: int
    section_start_line: int
    section_end_line: int


def normalize_heading_text(text: str) -> str:
    lowered = (text or "").strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


def _word_count(lines: list[str]) -> int:
    return len(WORD_RE.findall("\n".join(lines)))


def _token_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def _build_sections(markdown_text: str) -> list[MarkdownSection]:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    sections: list[MarkdownSection] = []
    heading_stack: list[tuple[int, str]] = []
    current_lines: list[str] = []
    current_start = 0
    current_path: list[str] = []

    def flush(end_idx: int) -> None:
        nonlocal current_lines, current_start, current_path
        if not current_lines:
            return
        sections.append(
            MarkdownSection(
                heading_path=list(current_path),
                lines=list(current_lines),
                start_line=current_start,
                end_line=end_idx,
            )
        )
        current_lines = []

    for idx, raw in enumerate(lines):
        heading = HEADING_RE.match(raw)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).strip()
            if level <= 3:
                flush(idx - 1)
                heading_stack = [entry for entry in heading_stack if entry[0] < level]
                heading_stack.append((level, text))
                current_path = [entry[1] for entry in heading_stack]
                current_start = idx
            current_lines.append(raw)
            continue
        if not current_lines:
            current_start = idx
        current_lines.append(raw)
    flush(len(lines) - 1)
    return sections


def detect_references_section(markdown_text: str) -> tuple[int | None, int | None]:
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for idx, raw in enumerate(lines):
        m = HEADING_RE.match(raw)
        if not m:
            continue
        norm = normalize_heading_text(m.group(2))
        if norm in REFERENCE_HEADING_VARIANTS:
            return idx, len(lines) - 1
    for idx, raw in enumerate(lines):
        norm = normalize_heading_text(raw)
        if norm in REFERENCE_HEADING_VARIANTS:
            return idx, len(lines) - 1
    return None, None


def _to_semantic_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            current.append(line)
            in_code = not in_code
            if not in_code:
                blocks.append(current)
                current = []
            continue
        if in_code:
            current.append(line)
            continue
        if not stripped:
            if current:
                blocks.append(current)
                current = []
            continue
        if stripped.startswith(("-", "*", "+")) or re.match(r"^\d+[.)]\s+", stripped) or stripped.startswith("|"):
            if current:
                blocks.append(current)
                current = []
            blocks.append([line])
            continue
        current.append(line)
    if current:
        blocks.append(current)
    return [b for b in blocks if any(x.strip() for x in b)]


def _split_oversized(lines: list[str], *, min_words: int, target_words: int, max_words: int) -> list[list[str]]:
    blocks = _to_semantic_blocks(lines)
    chunks: list[list[str]] = []
    current: list[str] = []
    current_words = 0
    for block in blocks:
        block_words = _word_count(block)
        if block_words > max_words:
            block_text = " ".join(" ".join(block).split())
            words = block_text.split()
            cursor = 0
            while cursor < len(words):
                end = min(len(words), cursor + max_words)
                piece = " ".join(words[cursor:end]).strip()
                if piece:
                    if current and (current_words + len(piece.split()) > max_words):
                        chunks.append(current)
                        current = []
                        current_words = 0
                    current.append(piece)
                    current_words += len(piece.split())
                    if current_words >= target_words:
                        chunks.append(current)
                        current = []
                        current_words = 0
                cursor = end
            continue
        if current and (current_words + block_words > max_words):
            chunks.append(current)
            current = []
            current_words = 0
        current.extend(block)
        current_words += block_words
        if current_words >= target_words:
            chunks.append(current)
            current = []
            current_words = 0
    if current:
        if chunks and _word_count(current) < min_words:
            chunks[-1].extend([""] + current)
        else:
            chunks.append(current)
    return chunks


def chunk_markdown_by_headings(
    markdown_text: str,
    *,
    min_words: int = 120,
    target_words: int = 220,
    max_words: int = 360,
) -> list[MarkdownChunk]:
    ref_start, _ = detect_references_section(markdown_text)
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body_text = "\n".join(lines[:ref_start] if ref_start is not None else lines)
    sections = _build_sections(body_text)
    merged_sections: list[MarkdownSection] = []
    for section in sections:
        if not merged_sections:
            merged_sections.append(section)
            continue
        if _word_count(section.lines) < min_words:
            prev = merged_sections[-1]
            merged_sections[-1] = MarkdownSection(
                heading_path=prev.heading_path or section.heading_path,
                lines=prev.lines + [""] + section.lines,
                start_line=prev.start_line,
                end_line=section.end_line,
            )
            continue
        merged_sections.append(section)

    out: list[MarkdownChunk] = []
    for section in merged_sections:
        section_words = _word_count(section.lines)
        if section_words <= max_words:
            text = "\n".join(section.lines).strip()
            if text:
                out.append(
                    MarkdownChunk(
                        text=text,
                        heading_path=section.heading_path,
                        token_count=_token_count(text),
                        section_start_line=section.start_line,
                        section_end_line=section.end_line,
                    )
                )
            continue
        for sub_lines in _split_oversized(
            section.lines,
            min_words=min_words,
            target_words=target_words,
            max_words=max_words,
        ):
            text = "\n".join(sub_lines).strip()
            if not text:
                continue
            out.append(
                MarkdownChunk(
                    text=text,
                    heading_path=section.heading_path,
                    token_count=_token_count(text),
                    section_start_line=section.start_line,
                    section_end_line=section.end_line,
                )
            )
    return out


def split_reference_entries(markdown_text: str) -> list[str]:
    start, end = detect_references_section(markdown_text)
    if start is None or end is None:
        return []
    lines = markdown_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")[start : end + 1]
    if lines and HEADING_RE.match(lines[0]):
        lines = lines[1:]
    entries: list[str] = []
    current: list[str] = []
    for line in lines:
        clean = " ".join((line or "").split()).strip()
        if not clean:
            continue
        if REFERENCE_ENTRY_START_RE.match(clean) and current:
            entries.append(" ".join(current).strip())
            current = [clean]
        else:
            current.append(clean)
    if current:
        entries.append(" ".join(current).strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        key = entry.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped
