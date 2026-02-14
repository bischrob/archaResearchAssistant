#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.pipeline import choose_pdfs, ingest_pdfs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Neo4j graph for PDF-based RAG testing.")
    parser.add_argument(
        "--pdf-dir",
        default="pdfs",
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
    pdfs = choose_pdfs(
        mode=args.mode,
        source_dir=args.pdf_dir,
        explicit_pdfs=args.pdf,
        skip_existing=not args.override_existing,
        require_metadata=True,
        partial_count=args.partial_count,
    )

    print("Selected PDFs:")
    for p in pdfs:
        print(f" - {p}")

    print("Building graph...")
    summary = ingest_pdfs(
        selected_pdfs=pdfs,
        wipe=False,
        skip_existing=not args.override_existing,
    )

    print("Done.")
    print(f"Ingested articles: {summary.ingested_articles}")
    print(f"Total chunks: {summary.total_chunks}")
    print(f"Total extracted references: {summary.total_references}")
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
