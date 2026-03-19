#!/usr/bin/env bash
set -euo pipefail

# Sync Google Drive Paperpile PDFs to local network directory.
# - Copies remote -> local
# - Never overwrites existing local files
# - Never deletes local files

REMOTE_PATH="${REMOTE_PATH:-gdrive:Library/Paperpile/allPapers}"
LOCAL_DIR="${LOCAL_DIR:-\\\\192.168.0.37\\pooled\\media\\Books\\pdfs}"
GOOGLE_CONFIG_FILE="${GOOGLE_CONFIG_FILE:-google.config}"
RCLONE_TRANSFERS="${RCLONE_TRANSFERS:-16}"
RCLONE_CHECKERS="${RCLONE_CHECKERS:-32}"
RCLONE_DRIVE_CHUNK_SIZE="${RCLONE_DRIVE_CHUNK_SIZE:-64M}"
RCLONE_BUFFER_SIZE="${RCLONE_BUFFER_SIZE:-32M}"
RCLONE_RETRIES="${RCLONE_RETRIES:-6}"
RCLONE_LOW_LEVEL_RETRIES="${RCLONE_LOW_LEVEL_RETRIES:-20}"
SYNC_REFRESH_CHANGED="${SYNC_REFRESH_CHANGED:-0}"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_TIMESTAMP_UTC="${RUN_TIMESTAMP_UTC:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

DRY_RUN_MODE="false"
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN_MODE="true"
fi

if ! command -v rclone >/dev/null 2>&1; then
  echo "Error: rclone is not installed or not in PATH." >&2
  exit 1
fi

is_wsl() {
  [[ -n "${WSL_DISTRO_NAME:-}" ]] && return 0
  grep -qi "microsoft" /proc/version 2>/dev/null
}

resolve_unc_to_wsl_path() {
  local raw="$1"
  if [[ "${raw}" != \\\\* ]]; then
    printf '%s' "${raw}"
    return 0
  fi
  if command -v wslpath >/dev/null 2>&1; then
    local converted
    converted="$(wslpath -u "${raw}" 2>/dev/null || true)"
    if [[ -n "${converted}" ]]; then
      printf '%s' "${converted}"
      return 0
    fi
  fi
  printf '%s' "${raw}"
}

try_mount_unc_share_drvfs() {
  local raw="$1"
  [[ "${raw}" == \\\\* ]] || return 0
  is_wsl || return 0
  if [[ ! "${raw}" =~ ^\\\\([^\\]+)\\([^\\]+)(\\.*)?$ ]]; then
    return 0
  fi
  local host="${BASH_REMATCH[1]}"
  local share="${BASH_REMATCH[2]}"
  local rest="${BASH_REMATCH[3]:-}"
  rest="${rest#\\}"
  local mount_root="/mnt/${share,,}"
  mkdir -p "${mount_root}"
  if mountpoint -q "${mount_root}" 2>/dev/null; then
    :
  else
    mount -t drvfs "\\\\${host}\\${share}" "${mount_root}" >/dev/null 2>&1 \
      || sudo -n mount -t drvfs "\\\\${host}\\${share}" "${mount_root}" >/dev/null 2>&1 \
      || true
  fi
  local candidate="${mount_root}"
  if [[ -n "${rest}" ]]; then
    candidate="${mount_root}/$(printf '%s' "${rest}" | tr '\\' '/')"
  fi
  printf '%s' "${candidate}"
}

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
    # A bare client ID without its companion client secret causes
    # remote auth override failures ("invalid_client"). Skip override
    # unless both values are present.
    if [[ -n "${OAUTH_SECRET}" ]]; then
      CLIENT_ID_VAR="RCLONE_CONFIG_${REMOTE_ENV_NAME}_CLIENT_ID"
      export "${CLIENT_ID_VAR}=${OAUTH_VALUE}"
      echo "Using OAuth client ID from ${GOOGLE_CONFIG_FILE} for remote '${REMOTE_NAME}'."
    else
      echo "OAuth in ${GOOGLE_CONFIG_FILE} looks like a client ID but OAuthSecret is missing; using existing rclone remote auth."
    fi
  fi
else
  echo "No OAuth value found in ${GOOGLE_CONFIG_FILE}; using existing rclone remote auth."
fi

if [[ -n "${OAUTH_SECRET}" && "${OAUTH_VALUE}" != \{* ]]; then
  CLIENT_SECRET_VAR="RCLONE_CONFIG_${REMOTE_ENV_NAME}_CLIENT_SECRET"
  export "${CLIENT_SECRET_VAR}=${OAUTH_SECRET}"
  echo "Using OAuth client secret from ${GOOGLE_CONFIG_FILE} for remote '${REMOTE_NAME}'."
fi

if is_wsl; then
  UNC_LOCAL_DIR="${LOCAL_DIR}"
  LOCAL_DIR="$(resolve_unc_to_wsl_path "${LOCAL_DIR}")"
  if [[ "${LOCAL_DIR}" == \\\\* ]]; then
    mounted_dir="$(try_mount_unc_share_drvfs "${UNC_LOCAL_DIR}")"
    if [[ -n "${mounted_dir:-}" && "${mounted_dir}" != "${UNC_LOCAL_DIR}" ]]; then
      LOCAL_DIR="${mounted_dir}"
    fi
  fi
fi

SYNC_MANIFEST_DIR="${SYNC_MANIFEST_DIR:-${LOCAL_DIR}/.sync-manifests}"
RUN_MANIFEST="${RUN_MANIFEST:-${SYNC_MANIFEST_DIR}/sync_${RUN_ID}_$$.manifest}"

mkdir -p "${LOCAL_DIR}"
mkdir -p "${SYNC_MANIFEST_DIR}"
if [[ ! -w "${LOCAL_DIR}" ]]; then
  echo "Error: LOCAL_DIR is not writable: ${LOCAL_DIR}" >&2
  echo "Fix permissions (example): sudo chown -R \"$(id -u):$(id -g)\" \"${LOCAL_DIR}\"" >&2
  exit 1
fi

write_manifest() {
  local exit_code="${1:-0}"
  {
    echo "run_id=${RUN_ID}"
    echo "timestamp_utc=${RUN_TIMESTAMP_UTC}"
    echo "remote_path=${REMOTE_PATH}"
    echo "local_dir=${LOCAL_DIR}"
    echo "dry_run=${DRY_RUN_MODE}"
    echo "refresh_changed=${SYNC_REFRESH_CHANGED}"
    echo "ignore_existing=$([[ "${SYNC_REFRESH_CHANGED}" == "1" ]] && printf 'false' || printf 'true')"
    echo "manifest_note=Default mode skips existing local files; upstream edits that reuse a filename can remain stale until removed locally or rerun with SYNC_REFRESH_CHANGED=1."
    echo "status=$([[ "${exit_code}" -eq 0 ]] && printf 'success' || printf 'failed')"
    echo "exit_code=${exit_code}"
  } > "${RUN_MANIFEST}"
}
trap 'write_manifest $?' EXIT

echo "Syncing from: ${REMOTE_PATH}"
echo "Syncing to:   ${LOCAL_DIR}"
echo "Mode: copy (non-destructive, ignore existing files)"
if [[ "${SYNC_REFRESH_CHANGED}" == "1" ]]; then
  echo "Mode: refresh-changed (checksum comparison enabled for existing files)"
else
  echo "Warning: existing local files are skipped, so upstream changes to the same filename can stay stale."
fi
[[ "${DRY_RUN_MODE}" == "true" ]] && echo "Mode: dry-run (no changes written)"
echo "Run manifest: ${RUN_MANIFEST}"

RCLONE_CMD=(
  rclone copy
  "${REMOTE_PATH}"
  "${LOCAL_DIR}"
  --include "*.pdf"
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

if [[ "${SYNC_REFRESH_CHANGED}" == "1" ]]; then
  RCLONE_CMD+=(--checksum)
else
  RCLONE_CMD+=(--ignore-existing)
fi

if [[ "${DRY_RUN_MODE}" == "true" ]]; then
  RCLONE_CMD+=(--dry-run)
fi

"${RCLONE_CMD[@]}"

echo "Sync complete."
