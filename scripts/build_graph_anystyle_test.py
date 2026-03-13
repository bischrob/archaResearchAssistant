#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.pipeline import choose_pdfs, ingest_pdfs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a test ingest using the shared pipeline with Anystyle citation extraction."
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
        "--anystyle-gpu-service",
        default="anystyle-gpu",
        help="Docker compose service name to run Anystyle GPU parsing from.",
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
    parser.add_argument(
        "--anystyle-use-gpu",
        action="store_true",
        help="Run Anystyle container with Docker GPU access (`--gpus`).",
    )
    parser.add_argument(
        "--anystyle-gpu-devices",
        default="all",
        help="Docker `--gpus` value (e.g., all or device=0).",
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

    settings = replace(
        Settings(),
        citation_parser="anystyle",
        anystyle_service=args.anystyle_service,
        anystyle_gpu_service=args.anystyle_gpu_service,
        anystyle_timeout_seconds=max(1, int(args.anystyle_timeout)),
        anystyle_require_success=args.require_anystyle,
        anystyle_use_gpu=args.anystyle_use_gpu,
        anystyle_gpu_devices=(args.anystyle_gpu_devices or "all").strip() or "all",
    )
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
    print(f"Anystyle attempted PDFs: {summary.anystyle_attempted_pdfs}")
    print(f"Anystyle applied PDFs: {summary.anystyle_applied_pdfs}")
    print(f"Anystyle empty PDFs: {summary.anystyle_empty_pdfs}")
    print(f"Anystyle failed PDFs: {summary.anystyle_failed_pdfs}")
    if summary.anystyle_disabled_reason:
        print(f"Anystyle disabled during run: {summary.anystyle_disabled_reason}")
    if summary.skipped_existing_pdfs:
        print(f"Skipped existing PDFs: {len(summary.skipped_existing_pdfs)}")
    if summary.skipped_no_metadata_pdfs:
        print(f"Skipped no-metadata PDFs: {len(summary.skipped_no_metadata_pdfs)}")
    if summary.anystyle_failure_samples:
        print(f"Anystyle failure samples: {len(summary.anystyle_failure_samples)}")
        for item in summary.anystyle_failure_samples[:20]:
            print(f" - {item}")
    if summary.failed_pdfs:
        print(f"Failed PDFs during ingest: {len(summary.failed_pdfs)}")
        for item in summary.failed_pdfs[:20]:
            print(f" - {item['pdf']}: {item['error']}")


if __name__ == "__main__":
    main()
