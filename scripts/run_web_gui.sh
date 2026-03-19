#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
UVICORN_RELOAD="${UVICORN_RELOAD:-0}"

if [[ "${UVICORN_RELOAD}" == "1" ]]; then
  echo "[WARN] Starting web GUI with --reload enabled for interactive development only."
  exec python -m uvicorn webapp.main:app --host "${HOST}" --port "${PORT}" --reload
fi

echo "[INFO] Starting web GUI without --reload for deterministic long-running operation."
exec python -m uvicorn webapp.main:app --host "${HOST}" --port "${PORT}"
