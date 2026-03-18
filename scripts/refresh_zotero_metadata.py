#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.metadata_provider import find_unmatched_pdfs, iter_pdf_files
from src.rag.pipeline import _load_metadata_index_for_settings


def main() -> None:
    settings = Settings()
    metadata_index = _load_metadata_index_for_settings(settings)
    pdf_root = Path(settings.pdf_source_dir)
    if not pdf_root.exists():
        raise SystemExit(f"PDF source directory not found: {pdf_root}")

    pdf_files = iter_pdf_files(pdf_root)
    unmatched = find_unmatched_pdfs(pdf_root, metadata_index)
    matched = len(pdf_files) - len(unmatched)

    print(f"Metadata backend: {metadata_index.backend}")
    print(f"PDF source: {pdf_root}")
    print(f"Total PDFs: {len(pdf_files)}")
    print(f"Matched: {matched}")
    print(f"Unmatched: {len(unmatched)}")
    if unmatched:
        print("Unmatched sample:")
        for p in unmatched[:30]:
            print(f" - {p}")


if __name__ == "__main__":
    main()
