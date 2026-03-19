#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RCLONE_REMOTE="${RCLONE_REMOTE:-dropbox:}"
RCLONE_DEST_PATH="${RCLONE_DEST_PATH:-Projects/researchAssistant}"
DEST="${RCLONE_REMOTE%:}:$RCLONE_DEST_PATH"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d_%H-%M-%S)"
LOG_FILE="${LOG_DIR}/rclone_sync_${TS}.log"

if ! command -v rclone >/dev/null 2>&1; then
  echo "ERROR: rclone not found in PATH" | tee -a "$LOG_FILE"
  exit 1
fi

if ! rclone listremotes | grep -qx "${RCLONE_REMOTE%:}:"; then
  echo "ERROR: rclone remote '${RCLONE_REMOTE%:}' is not configured." | tee -a "$LOG_FILE"
  echo "Run: rclone config" | tee -a "$LOG_FILE"
  exit 2
fi

echo "Starting sync: ${ROOT_DIR} -> ${DEST}" | tee -a "$LOG_FILE"
rclone sync "${ROOT_DIR}" "${DEST}" \
  --exclude ".git/**" \
  --exclude "__pycache__/**" \
  --exclude ".pytest_cache/**" \
  --exclude ".mypy_cache/**" \
  --exclude ".ruff_cache/**" \
  --exclude "tmp/**" \
  --create-empty-src-dirs \
  --fast-list \
  --transfers 4 \
  --checkers 8 \
  --log-file "$LOG_FILE" \
  --log-level INFO

echo "Sync complete: ${DEST}" | tee -a "$LOG_FILE"
