#!/usr/bin/env bash
set -euo pipefail

# Sync Google Drive Paperpile PDFs to local ./pdfs directory.
# - Copies remote -> local
# - Never overwrites existing local files
# - Never deletes local files

REMOTE_PATH="${REMOTE_PATH:-gdrive:Library/Paperpile/allPapers}"
LOCAL_DIR="${LOCAL_DIR:-pdfs}"
GOOGLE_CONFIG_FILE="${GOOGLE_CONFIG_FILE:-google.config}"
RCLONE_TRANSFERS="${RCLONE_TRANSFERS:-16}"
RCLONE_CHECKERS="${RCLONE_CHECKERS:-32}"
RCLONE_DRIVE_CHUNK_SIZE="${RCLONE_DRIVE_CHUNK_SIZE:-64M}"
RCLONE_BUFFER_SIZE="${RCLONE_BUFFER_SIZE:-32M}"
RCLONE_RETRIES="${RCLONE_RETRIES:-6}"
RCLONE_LOW_LEVEL_RETRIES="${RCLONE_LOW_LEVEL_RETRIES:-20}"

DRY_RUN_MODE="false"
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN_MODE="true"
fi

if ! command -v rclone >/dev/null 2>&1; then
  echo "Error: rclone is not installed or not in PATH." >&2
  exit 1
fi

read_config_value() {
  local key="$1"
  local file="$2"
  [[ -f "${file}" ]] || return 0
  awk -F= -v k="${key}" '
    $0 ~ "^[[:space:]]*" k "[[:space:]]*=" {
      sub(/^[^=]*=/, "", $0)
      print $0
      exit
    }
  ' "${file}"
}

trim_quotes_and_space() {
  local v="$1"
  v="${v#"${v%%[![:space:]]*}"}"
  v="${v%"${v##*[![:space:]]}"}"
  if [[ "${v}" =~ ^\".*\"$ ]]; then
    v="${v:1:-1}"
  elif [[ "${v}" =~ ^\'.*\'$ ]]; then
    v="${v:1:-1}"
  fi
  printf '%s' "${v}"
}

REMOTE_NAME="${REMOTE_PATH%%:*}"
if [[ "${REMOTE_NAME}" == "${REMOTE_PATH}" ]]; then
  echo "Error: REMOTE_PATH must include a remote prefix (example: gdrive:path/to/folder)." >&2
  exit 1
fi
REMOTE_ENV_NAME="$(printf '%s' "${REMOTE_NAME}" | tr '[:lower:]-' '[:upper:]_' | tr -cd 'A-Z0-9_')"

OAUTH_VALUE_RAW="$(read_config_value "OAuth" "${GOOGLE_CONFIG_FILE}" || true)"
OAUTH_VALUE="$(trim_quotes_and_space "${OAUTH_VALUE_RAW}")"
OAUTH_SECRET_RAW="$(read_config_value "OAuthSecret" "${GOOGLE_CONFIG_FILE}" || true)"
OAUTH_SECRET="$(trim_quotes_and_space "${OAUTH_SECRET_RAW}")"

if [[ -n "${OAUTH_VALUE}" ]]; then
  if [[ "${OAUTH_VALUE}" == \{* ]]; then
    TOKEN_VAR="RCLONE_CONFIG_${REMOTE_ENV_NAME}_TOKEN"
    export "${TOKEN_VAR}=${OAUTH_VALUE}"
    echo "Using OAuth token from ${GOOGLE_CONFIG_FILE} for remote '${REMOTE_NAME}'."
  else
    CLIENT_ID_VAR="RCLONE_CONFIG_${REMOTE_ENV_NAME}_CLIENT_ID"
    export "${CLIENT_ID_VAR}=${OAUTH_VALUE}"
    echo "Using OAuth client ID from ${GOOGLE_CONFIG_FILE} for remote '${REMOTE_NAME}'."
  fi
else
  echo "No OAuth value found in ${GOOGLE_CONFIG_FILE}; using existing rclone remote auth."
fi

if [[ -n "${OAUTH_SECRET}" ]]; then
  CLIENT_SECRET_VAR="RCLONE_CONFIG_${REMOTE_ENV_NAME}_CLIENT_SECRET"
  export "${CLIENT_SECRET_VAR}=${OAUTH_SECRET}"
  echo "Using OAuth client secret from ${GOOGLE_CONFIG_FILE} for remote '${REMOTE_NAME}'."
fi

mkdir -p "${LOCAL_DIR}"

echo "Syncing from: ${REMOTE_PATH}"
echo "Syncing to:   ${LOCAL_DIR}"
echo "Mode: copy (non-destructive, ignore existing files)"
[[ "${DRY_RUN_MODE}" == "true" ]] && echo "Mode: dry-run (no changes written)"

RCLONE_CMD=(
  rclone copy
  "${REMOTE_PATH}"
  "${LOCAL_DIR}"
  --include "*.pdf"
  --ignore-existing
  --fast-list
  --transfers "${RCLONE_TRANSFERS}"
  --checkers "${RCLONE_CHECKERS}"
  --drive-chunk-size "${RCLONE_DRIVE_CHUNK_SIZE}"
  --buffer-size "${RCLONE_BUFFER_SIZE}"
  --retries "${RCLONE_RETRIES}"
  --low-level-retries "${RCLONE_LOW_LEVEL_RETRIES}"
  --stats 10s
  --stats-one-line
  --progress
)

if [[ "${DRY_RUN_MODE}" == "true" ]]; then
  RCLONE_CMD+=(--dry-run)
fi

"${RCLONE_CMD[@]}"

echo "Sync complete."
