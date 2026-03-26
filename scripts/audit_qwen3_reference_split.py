#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.path_utils import resolve_input_path
from src.rag.qwen_structured_refs import (
    _build_sections,
    _extract_lines_with_page,
    _heuristic_reference_split,
    detect_section_plan_with_qwen,
    split_reference_strings_with_qwen,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Qwen3 reference identification/splitting. "
            "Step 1: identify section boundaries and reference chunk(s). "
            "Step 2: split reference chunk(s) into individual references. "
            "Writes markdown artifacts for manual review."
        )
    )
    parser.add_argument(
        "--pdf",
        action="append",
        default=[],
        help="PDF path (repeatable). Accepts WSL paths and UNC paths.",
    )
    parser.add_argument(
        "--pdf-dir",
        default="",
        help="Optional PDF root used to resolve relative --pdf inputs.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/qwen3_reference_audit",
        help="Directory for markdown audit outputs.",
    )
    parser.add_argument(
        "--max-ref-preview-chars",
        type=int,
        default=260,
        help="Max characters shown per reference preview in markdown.",
    )
    parser.add_argument(
        "--max-lines-preview",
        type=int,
        default=12,
        help="Max source lines shown per section preview.",
    )
    return parser.parse_args()


def _resolve_pdf_paths(args: argparse.Namespace, settings: Settings) -> list[Path]:
    source_dir_raw = args.pdf_dir.strip() if args.pdf_dir else settings.pdf_source_dir
    source_dir = resolve_input_path(source_dir_raw)
    out: list[Path] = []
    for raw in args.pdf:
        item = (raw or "").strip().strip('"').strip("'")
        if not item:
            continue
        p = resolve_input_path(item)
        if not p.is_absolute():
            p = source_dir / item
        p = p.resolve()
        if not p.exists():
            raise FileNotFoundError(f"Missing PDF: {p}")
        out.append(p)
    if not out:
        raise ValueError("No PDFs provided. Use --pdf <path>.")
    return out


def _preview(text: str, max_chars: int) -> str:
    body = " ".join((text or "").split())
    if len(body) <= max_chars:
        return body
    return body[: max_chars - 3] + "..."


def _write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _section_block(
    *,
    lines: list[str],
    sections: list[tuple[int, int, str]],
    max_lines_preview: int,
) -> list[str]:
    out: list[str] = []
    out.append("## Section Plan")
    out.append("")
    out.append("| idx | kind | line_start | line_end | line_count | preview |")
    out.append("|---:|---|---:|---:|---:|---|")
    for idx, (start, end, kind) in enumerate(sections):
        snippet = _preview(lines[start] if 0 <= start < len(lines) else "", 80)
        out.append(f"| {idx} | {kind} | {start} | {end} | {end - start + 1} | {snippet} |")
    out.append("")
    out.append("### Section Previews")
    out.append("")
    for idx, (start, end, kind) in enumerate(sections):
        out.append(f"#### Section {idx} ({kind}) lines {start}-{end}")
        out.append("")
        sample = lines[start : min(end + 1, start + max_lines_preview)]
        if not sample:
            out.append("_No lines_")
            out.append("")
            continue
        out.append("```text")
        out.extend(sample)
        if end - start + 1 > len(sample):
            out.append("... [truncated]")
        out.append("```")
        out.append("")
    return out


def _run_pdf(pdf_path: Path, settings: Settings, output_dir: Path, max_ref_preview_chars: int, max_lines_preview: int) -> dict:
    lines_with_page = _extract_lines_with_page(
        pdf_path,
        settings=settings,
        strip_page_noise=settings.chunk_strip_page_noise,
    )
    lines = [line for _, line in lines_with_page]
    heading_indices, reference_start = detect_section_plan_with_qwen(lines, settings=settings)
    sections = _build_sections(len(lines), heading_indices=heading_indices, reference_start=reference_start)

    reference_blocks: list[dict] = []
    for sec_idx, (start, end, kind) in enumerate(sections):
        if kind != "references":
            continue
        block_lines = lines[start : end + 1]
        block_text = "\n".join(block_lines).strip()
        if not block_text:
            continue
        qwen_refs = split_reference_strings_with_qwen(block_text, settings=settings)
        heuristic_refs = _heuristic_reference_split(block_text)
        reference_blocks.append(
            {
                "section_index": sec_idx,
                "line_start": start,
                "line_end": end,
                "line_count": len(block_lines),
                "raw_text": block_text,
                "qwen_reference_strings": qwen_refs,
                "heuristic_reference_strings": heuristic_refs,
            }
        )

    report_dir = output_dir / pdf_path.stem
    report_dir.mkdir(parents=True, exist_ok=True)

    for idx, block in enumerate(reference_blocks):
        raw_file = report_dir / f"reference_block_{idx:02d}.txt"
        raw_file.write_text(str(block["raw_text"]).strip() + "\n", encoding="utf-8")

    md: list[str] = []
    md.append(f"# Qwen3 Reference Audit: {pdf_path.name}")
    md.append("")
    md.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    md.append(f"- PDF path: `{pdf_path}`")
    md.append(f"- Total extracted lines: {len(lines)}")
    md.append(f"- Heading indices returned: {heading_indices}")
    md.append(f"- Reference start line: {reference_start}")
    md.append(f"- Reference sections found: {len(reference_blocks)}")
    md.append("")
    md.extend(_section_block(lines=lines, sections=sections, max_lines_preview=max_lines_preview))
    md.append("## Reference Split Audit")
    md.append("")
    if not reference_blocks:
        md.append("_No reference section detected._")
        md.append("")
    for idx, block in enumerate(reference_blocks):
        qwen_refs = block["qwen_reference_strings"]
        heuristic_refs = block["heuristic_reference_strings"]
        raw_file = report_dir / f"reference_block_{idx:02d}.txt"
        md.append(f"### Reference Block {idx}")
        md.append("")
        md.append(f"- Section index: {block['section_index']}")
        md.append(f"- Source lines: {block['line_start']}-{block['line_end']} ({block['line_count']} lines)")
        md.append(f"- Raw text file: `{raw_file}`")
        md.append(f"- Qwen split count: {len(qwen_refs)}")
        md.append(f"- Heuristic split count: {len(heuristic_refs)}")
        md.append("")
        md.append("#### Qwen Split Output")
        md.append("")
        if not qwen_refs:
            md.append("_No Qwen references produced._")
            md.append("")
        for ref_idx, ref in enumerate(qwen_refs):
            md.append(f"{ref_idx + 1}. {_preview(ref, max_ref_preview_chars)}")
        md.append("")
        md.append("#### Heuristic Split Output (Comparison)")
        md.append("")
        if not heuristic_refs:
            md.append("_No heuristic references produced._")
            md.append("")
        for ref_idx, ref in enumerate(heuristic_refs):
            md.append(f"{ref_idx + 1}. {_preview(ref, max_ref_preview_chars)}")
        md.append("")

    report_md = report_dir / "report.md"
    _write_markdown(report_md, md)

    return {
        "pdf": str(pdf_path),
        "report_md": str(report_md),
        "lines": len(lines),
        "heading_indices": heading_indices,
        "reference_start": reference_start,
        "reference_blocks": [
            {
                "section_index": x["section_index"],
                "line_start": x["line_start"],
                "line_end": x["line_end"],
                "line_count": x["line_count"],
                "qwen_reference_count": len(x["qwen_reference_strings"]),
                "heuristic_reference_count": len(x["heuristic_reference_strings"]),
            }
            for x in reference_blocks
        ],
    }


def main() -> int:
    args = parse_args()
    settings = Settings()
    pdf_paths = _resolve_pdf_paths(args, settings)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for pdf_path in pdf_paths:
        results.append(
            _run_pdf(
                pdf_path=pdf_path,
                settings=settings,
                output_dir=output_dir,
                max_ref_preview_chars=max(80, int(args.max_ref_preview_chars)),
                max_lines_preview=max(3, int(args.max_lines_preview)),
            )
        )

    summary_lines: list[str] = []
    summary_lines.append("# Qwen3 Reference Audit Summary")
    summary_lines.append("")
    summary_lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    summary_lines.append(f"- Output dir: `{output_dir}`")
    summary_lines.append(f"- PDFs audited: {len(results)}")
    summary_lines.append("")
    summary_lines.append("| PDF | Lines | Reference Start | Ref Blocks | Qwen Ref Count | Heuristic Ref Count | Report |")
    summary_lines.append("|---|---:|---:|---:|---:|---:|---|")
    for row in results:
        qwen_total = sum(x["qwen_reference_count"] for x in row["reference_blocks"])
        heuristic_total = sum(x["heuristic_reference_count"] for x in row["reference_blocks"])
        ref_blocks = len(row["reference_blocks"])
        rel_report = Path(row["report_md"]).resolve().relative_to(output_dir)
        summary_lines.append(
            f"| {Path(row['pdf']).name} | {row['lines']} | {row['reference_start']} | {ref_blocks} | {qwen_total} | {heuristic_total} | `{rel_report}` |"
        )
    summary_lines.append("")

    summary_md = output_dir / "SUMMARY.md"
    _write_markdown(summary_md, summary_lines)
    print(f"Wrote: {summary_md}")
    for row in results:
        print(f"Wrote: {row['report_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

