#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="${1:-${HOME}/.local/bin}"
TARGET_PATH="${TARGET_DIR}/ra"
mkdir -p "${TARGET_DIR}"

cat > "${TARGET_PATH}" <<LAUNCHER
#!/usr/bin/env bash
set -euo pipefail
exec "${ROOT_DIR}/scripts/run_ra_from_repo.sh" "\$@"
LAUNCHER
chmod +x "${TARGET_PATH}"

echo "Installed WSL ra launcher at ${TARGET_PATH}"
case ":${PATH}:" in
  *":${TARGET_DIR}:"*)
    echo "${TARGET_DIR} is already on PATH."
    ;;
  *)
    echo "Warning: ${TARGET_DIR} is not currently on PATH. Add this to your shell profile:" >&2
    echo "  export PATH=\"${TARGET_DIR}:\$PATH\"" >&2
    ;;
esac
