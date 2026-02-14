#!/usr/bin/env bash
set -euo pipefail

# Delete invalid PDF files under a directory (default: ./pdfs).
# A PDF is treated as invalid if:
# 1) it does not start with %PDF
# 2) PyMuPDF cannot open it
#
# Usage:
#   scripts/delete_invalid_pdfs.sh
#   scripts/delete_invalid_pdfs.sh --dry-run
#   scripts/delete_invalid_pdfs.sh --root pdfs

ROOT_DIR="pdfs"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --root)
      ROOT_DIR="${2:-}"
      if [[ -z "${ROOT_DIR}" ]]; then
        echo "Error: --root requires a directory value." >&2
        exit 1
      fi
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--dry-run] [--root <dir>]" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "${ROOT_DIR}" ]]; then
  echo "Error: directory not found: ${ROOT_DIR}" >&2
  exit 1
fi

if ! command -v python >/dev/null 2>&1; then
  echo "Error: python not found in PATH." >&2
  exit 1
fi

echo "Scanning for invalid PDFs under: ${ROOT_DIR}"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Mode: dry-run (no files will be deleted)"
fi

python - <<'PY' "${ROOT_DIR}" "${DRY_RUN}"
from __future__ import annotations

import os
import sys
from pathlib import Path

import fitz

root = Path(sys.argv[1])
dry_run = sys.argv[2] == "1"

invalid: list[tuple[Path, str]] = []
checked = 0

for path in root.rglob("*"):
    if not path.is_file() or path.suffix.lower() != ".pdf":
        continue
    checked += 1
    reason = None
    try:
        with open(path, "rb") as f:
            header = f.read(4)
        if header != b"%PDF":
            reason = "bad header"
        else:
            doc = fitz.open(path)
            doc.close()
    except Exception as exc:
        reason = f"unreadable ({exc})"

    if reason:
        invalid.append((path, reason))

deleted = 0
for path, reason in invalid:
    print(f"INVALID: {path} [{reason}]")
    if not dry_run:
        try:
            os.remove(path)
            deleted += 1
        except Exception as exc:
            print(f"ERROR deleting {path}: {exc}")

print(f"\nChecked PDFs: {checked}")
print(f"Invalid PDFs: {len(invalid)}")
if dry_run:
    print("Deleted PDFs: 0 (dry-run)")
else:
    print(f"Deleted PDFs: {deleted}")
PY

