#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="$(${ROOT_DIR}/scripts/resolve_python.sh)"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Error: Could not locate a usable Python interpreter for archaResearch Assistant." >&2
  exit 1
fi

export PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
: "${RA_BASE_URL:=http://127.0.0.1:8001}"
export RA_BASE_URL
exec "${PYTHON_BIN}" -m rag.cli "$@"
