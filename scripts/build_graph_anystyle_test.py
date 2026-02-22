#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.anystyle_refs import extract_citations_with_anystyle_docker
from src.rag.pipeline import choose_pdfs, ingest_pdfs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a test ingest that attempts citation extraction with Anystyle in Docker."
    )
    parser.add_argument(
        "--pdf-dir",
        default="pdfs",
        help="Directory containing candidate PDFs.",
    )
    parser.add_argument(
        "--mode",
        default="batch",
        choices=["batch", "all", "custom", "test3"],
        help="batch ingests first N (see --partial-count), all ingests all PDFs in --pdf-dir, custom uses --pdf list.",
    )
    parser.add_argument(
        "--partial-count",
        type=int,
        default=1,
        help="Batch size used for batch mode.",
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
    parser.add_argument(
        "--anystyle-service",
        default="anystyle",
        help="Docker compose service name to run Anystyle from.",
    )
    parser.add_argument(
        "--anystyle-timeout",
        type=int,
        default=240,
        help="Timeout (seconds) per PDF for Anystyle extraction.",
    )
    parser.add_argument(
        "--require-anystyle",
        action="store_true",
        help="Fail instead of falling back to built-in citation extraction when Anystyle errors.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        pdfs = choose_pdfs(
            mode=args.mode,
            source_dir=args.pdf_dir,
            explicit_pdfs=args.pdf,
            skip_existing=not args.override_existing,
            require_metadata=True,
            partial_count=args.partial_count,
        )
    except ValueError as exc:
        msg = str(exc)
        if "No PDFs found to ingest after filtering" in msg and not args.override_existing:
            raise SystemExit(f"{msg}\nHint: re-run with --override-existing for a deterministic test run.") from exc
        raise

    print("Selected PDFs:")
    for p in pdfs:
        print(f" - {p}")

    citation_overrides = {}
    anystyle_failures: list[dict[str, str]] = []
    anystyle_empty: list[str] = []

    print("Extracting references with Anystyle (Docker)...")
    for pdf in pdfs:
        try:
            citations = extract_citations_with_anystyle_docker(
                pdf,
                compose_service=args.anystyle_service,
                timeout_seconds=args.anystyle_timeout,
                project_root=ROOT,
            )
            if citations:
                citation_overrides[pdf.stem] = citations
                print(f" - {pdf.name}: {len(citations)} references via Anystyle")
            else:
                anystyle_empty.append(pdf.name)
                print(f" - {pdf.name}: 0 references via Anystyle (fallback to built-in parser)")
        except Exception as exc:
            anystyle_failures.append({"pdf": str(pdf), "error": str(exc)})
            print(f" - {pdf.name}: Anystyle failed, fallback to built-in parser ({exc})")

    if args.require_anystyle and anystyle_failures:
        print("Aborting because --require-anystyle was set and extraction failed.")
        for item in anystyle_failures:
            print(f" - {item['pdf']}: {item['error']}")
        raise SystemExit(2)

    print("Building graph...")
    summary = ingest_pdfs(
        selected_pdfs=pdfs,
        wipe=False,
        skip_existing=not args.override_existing,
        citation_overrides=citation_overrides,
    )

    print("Done.")
    print(f"Ingested articles: {summary.ingested_articles}")
    print(f"Total chunks: {summary.total_chunks}")
    print(f"Total extracted references: {summary.total_references}")
    print(f"Anystyle overrides applied: {len(citation_overrides)}/{len(pdfs)}")
    if anystyle_empty:
        print(f"Anystyle empty extraction: {len(anystyle_empty)}")
    if summary.skipped_existing_pdfs:
        print(f"Skipped existing PDFs: {len(summary.skipped_existing_pdfs)}")
    if summary.skipped_no_metadata_pdfs:
        print(f"Skipped no-metadata PDFs: {len(summary.skipped_no_metadata_pdfs)}")
    if anystyle_failures:
        print(f"Anystyle failures (fallback used): {len(anystyle_failures)}")
        for item in anystyle_failures[:20]:
            print(f" - {item['pdf']}: {item['error']}")
    if summary.failed_pdfs:
        print(f"Failed PDFs during ingest: {len(summary.failed_pdfs)}")
        for item in summary.failed_pdfs[:20]:
            print(f" - {item['pdf']}: {item['error']}")


if __name__ == "__main__":
    main()
