#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-$("${ROOT_DIR}/scripts/resolve_python.sh")}"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "Error: Could not locate a usable Python interpreter." >&2
  exit 1
fi

export PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec "${PYTHON_BIN}" -m rag.cli serve-web "$@"
