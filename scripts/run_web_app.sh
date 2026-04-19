#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
UVICORN_RELOAD="${UVICORN_RELOAD:-0}"
PYTHON_BIN="${PYTHON_BIN:-$("${ROOT_DIR}/scripts/resolve_python.sh")}"

if [[ "${UVICORN_RELOAD}" == "1" ]]; then
  echo "[WARN] Starting web GUI with --reload enabled for interactive development only."
  exec "${PYTHON_BIN}" -m uvicorn webapp.main:app --host "${HOST}" --port "${PORT}" --reload
fi

echo "[INFO] Starting web GUI without --reload for deterministic long-running operation."
exec "${PYTHON_BIN}" -m uvicorn webapp.main:app --host "${HOST}" --port "${PORT}"
