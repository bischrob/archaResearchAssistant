#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

python -m uvicorn webapp.main:app --host "${HOST}" --port "${PORT}" --reload

