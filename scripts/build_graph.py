#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.pipeline import choose_pdfs, ingest_pdfs


def parse_args() -> argparse.Namespace:
    default_pdf_dir = Settings().pdf_source_dir
    parser = argparse.ArgumentParser(description="Build Neo4j graph for PDF-based RAG testing.")
    parser.add_argument(
        "--pdf-dir",
        default=default_pdf_dir,
        help="Directory containing candidate PDFs.",
    )
    parser.add_argument(
        "--mode",
        default="batch",
        choices=["batch", "all", "custom", "test3"],
        help="batch ingests first N (see --partial-count), all ingests all PDFs in --pdf-dir, custom uses --pdf list. test3 is accepted as a legacy alias.",
    )
    parser.add_argument(
        "--partial-count",
        type=int,
        default=3,
        help="Batch size. Used as first-N for batch mode and as per-batch size for all mode in the web UI.",
    )
    parser.add_argument(
        "--pdf",
        action="append",
        default=[],
        help="Specific PDF path(s). Used when --mode custom.",
    )
    parser.add_argument(
        "--override-existing",
        action="store_true",
        help="Reprocess PDFs that are already ingested (default skips existing).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings()
    pdfs = choose_pdfs(
        mode=args.mode,
        source_mode=args.source_mode,
        source_dir=args.pdf_dir,
        explicit_pdfs=args.pdf,
        skip_existing=not args.override_existing,
        require_metadata=True,
        settings=settings,
        partial_count=args.partial_count,
    )

    print("Selected PDFs:")
    for p in pdfs:
        print(f" - {p}")

    print("Building graph...")
    summary = ingest_pdfs(
        selected_pdfs=pdfs,
        wipe=False,
        settings=settings,
        skip_existing=not args.override_existing,
    )

    print("Done.")
    print(f"Ingested articles: {summary.ingested_articles}")
    print(f"Total chunks: {summary.total_chunks}")
    print(f"Total extracted references: {summary.total_references}")
    print(f"Citation parser mode: {settings.citation_parser}")
    print(f"Anystyle attempted PDFs: {summary.anystyle_attempted_pdfs}")
    print(f"Anystyle applied PDFs: {summary.anystyle_applied_pdfs}")
    print(f"Anystyle empty PDFs: {summary.anystyle_empty_pdfs}")
    print(f"Anystyle failed PDFs: {summary.anystyle_failed_pdfs}")
    if summary.anystyle_disabled_reason:
        print(f"Anystyle disabled during run: {summary.anystyle_disabled_reason}")
    if summary.anystyle_failure_samples:
        print(f"Anystyle failure samples: {len(summary.anystyle_failure_samples)}")
        for item in summary.anystyle_failure_samples[:20]:
            print(f" - {item}")
    print(f"Qwen attempted PDFs: {summary.qwen_attempted_pdfs}")
    print(f"Qwen applied PDFs: {summary.qwen_applied_pdfs}")
    print(f"Qwen empty PDFs: {summary.qwen_empty_pdfs}")
    print(f"Qwen failed PDFs: {summary.qwen_failed_pdfs}")
    if summary.qwen_disabled_reason:
        print(f"Qwen disabled during run: {summary.qwen_disabled_reason}")
    if summary.qwen_failure_samples:
        print(f"Qwen failure samples: {len(summary.qwen_failure_samples)}")
        for item in summary.qwen_failure_samples[:20]:
            print(f" - {item}")
    if summary.skipped_existing_pdfs:
        print(f"Skipped existing PDFs: {len(summary.skipped_existing_pdfs)}")
    if summary.skipped_no_metadata_pdfs:
        print(f"Skipped no-metadata PDFs: {len(summary.skipped_no_metadata_pdfs)}")
    if summary.failed_pdfs:
        print(f"Failed PDFs: {len(summary.failed_pdfs)}")
        for item in summary.failed_pdfs[:20]:
            print(f" - {item['pdf']}: {item['error']}")


if __name__ == "__main__":
    main()
