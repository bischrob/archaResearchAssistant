#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${1:-${HOME}/.local/bin}"
TARGET_PATH="${TARGET_DIR}/ra"
mkdir -p "${TARGET_DIR}"

get_env_value() {
  local key="$1"
  local env_file="${ROOT_DIR}/.env"
  if [[ -f "${env_file}" ]]; then
    grep -E "^${key}=" "${env_file}" | tail -n1 | cut -d'=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' || true
  fi
}

DEFAULT_RA_REPO_DIR="${RA_REPO_DIR:-$(get_env_value RA_REPO_DIR)}"
if [[ -z "${DEFAULT_RA_REPO_DIR}" ]]; then
  DEFAULT_RA_REPO_DIR="${ROOT_DIR}"
fi

if grep -qi microsoft /proc/version 2>/dev/null || [[ -n "${WSL_DISTRO_NAME:-}" ]]; then
  DEFAULT_RA_BASE_URL="http://192.168.0.37:8001"
else
  DEFAULT_RA_BASE_URL="http://127.0.0.1:8001"
fi

cat > "${TARGET_PATH}" <<LAUNCHER
#!/usr/bin/env bash
set -euo pipefail
export RA_REPO_DIR="\${RA_REPO_DIR:-${DEFAULT_RA_REPO_DIR}}"
export RA_BASE_URL="\${RA_BASE_URL:-${DEFAULT_RA_BASE_URL}}"
exec "\${RA_REPO_DIR}/scripts/run_ra_from_repo.sh" "\$@"
LAUNCHER
chmod +x "${TARGET_PATH}"

echo "Installed WSL ra launcher at ${TARGET_PATH}"
echo "Default RA_REPO_DIR for this launcher: ${DEFAULT_RA_REPO_DIR}"
echo "Default RA_BASE_URL for this launcher: ${DEFAULT_RA_BASE_URL}"
case ":${PATH}:" in
  *":${TARGET_DIR}:"*)
    echo "${TARGET_DIR} is already on PATH."
    ;;
  *)
    echo "Warning: ${TARGET_DIR} is not currently on PATH. Add this to your shell profile:" >&2
    echo "  export PATH=\"${TARGET_DIR}:\$PATH\"" >&2
    ;;
esac
