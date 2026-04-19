#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-$("${ROOT_DIR}/scripts/resolve_python.sh")}"
PORT_TO_CHECK="${1:-${PORT:-8000}}"
export PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
exec "${PYTHON_BIN}" -m rag.cli preflight --port "${PORT_TO_CHECK}"
