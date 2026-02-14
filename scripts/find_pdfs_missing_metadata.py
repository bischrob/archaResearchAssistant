#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.paperpile_metadata import find_unmatched_pdfs, load_paperpile_index


def write_csv(out_csv: Path, pdf_root: Path, unmatched: list[Path]) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "relative_path", "absolute_path"])
        for p in unmatched:
            try:
                rel = p.relative_to(pdf_root)
            except Exception:
                rel = p
            writer.writerow([p.name, str(rel), str(p)])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find PDFs in a folder that do not have matching attachment metadata in Paperpile.json.",
    )
    parser.add_argument(
        "--pdf-root",
        default=r"G:\My Drive\Library\Paperpile\allPapers",
        help=r"Root folder to scan for PDFs (default: G:\My Drive\Library\Paperpile\allPapers).",
    )
    parser.add_argument(
        "--paperpile-json",
        default="Paperpile.json",
        help="Path to Paperpile.json (default: Paperpile.json in current directory).",
    )
    parser.add_argument(
        "--out-csv",
        default="missing_metadata_pdfs.csv",
        help="Output CSV path (default: missing_metadata_pdfs.csv).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pdf_root = Path(args.pdf_root)
    paperpile_json = Path(args.paperpile_json)
    out_csv = Path(args.out_csv)

    if not pdf_root.exists() or not pdf_root.is_dir():
        raise SystemExit(f"PDF root does not exist or is not a directory: {pdf_root}")
    if not paperpile_json.exists() or not paperpile_json.is_file():
        raise SystemExit(f"Paperpile JSON not found: {paperpile_json}")

    metadata_index = load_paperpile_index(str(paperpile_json))
    unmatched = find_unmatched_pdfs(str(pdf_root), metadata_index)
    write_csv(out_csv, pdf_root, unmatched)

    print(f"PDF root: {pdf_root}")
    print(f"Paperpile metadata file: {paperpile_json}")
    print(f"Metadata index entries: {len(metadata_index)}")
    print(f"Unmatched PDFs: {len(unmatched)}")
    print(f"CSV written: {out_csv.resolve()}")


if __name__ == "__main__":
    main()
