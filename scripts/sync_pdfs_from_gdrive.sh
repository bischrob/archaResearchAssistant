#!/usr/bin/env bash
set -euo pipefail

# Sync Google Drive Paperpile PDFs to local ./pdfs directory.
# - Mirrors remote -> local
# - Deletes local files not present remotely
# - Skips files that already exist locally

REMOTE_PATH="${REMOTE_PATH:-gdrive:My Drive/Library/Paperpile/allPapers}"
LOCAL_DIR="${LOCAL_DIR:-pdfs}"

DRY_RUN_FLAG=""
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN_FLAG="--dry-run"
fi

if ! command -v rclone >/dev/null 2>&1; then
  echo "Error: rclone is not installed or not in PATH." >&2
  exit 1
fi

mkdir -p "${LOCAL_DIR}"

echo "Syncing from: ${REMOTE_PATH}"
echo "Syncing to:   ${LOCAL_DIR}"
[[ -n "${DRY_RUN_FLAG}" ]] && echo "Mode: dry-run (no changes written)"

rclone sync \
  "${REMOTE_PATH}" \
  "${LOCAL_DIR}" \
  --include "*.pdf" \
  --ignore-existing \
  --delete-excluded \
  --fast-list \
  --progress \
  ${DRY_RUN_FLAG}

echo "Sync complete."

