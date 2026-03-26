#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

has_required_modules() {
  local python_bin="$1"
  "${python_bin}" - <<'PY' >/dev/null 2>&1
import importlib.util
import sys

required = ("fastapi", "uvicorn", "neo4j", "sentence_transformers")
missing = [name for name in required if importlib.util.find_spec(name) is None]
sys.exit(0 if not missing else 1)
PY
}

append_candidate() {
  local candidate="$1"
  [[ -n "${candidate}" ]] || return 0
  [[ -x "${candidate}" ]] || return 0
  _RESOLVE_PYTHON_CANDIDATES+=("${candidate}")
}

append_conda_env_candidates() {
  local conda_base="$1"
  [[ -n "${conda_base}" ]] || return 0
  for env_name in researchassistant researchAssistant researchassistant311; do
    append_candidate "${conda_base}/envs/${env_name}/bin/python"
  done
}

_RESOLVE_PYTHON_CANDIDATES=()

append_candidate "${PYTHON_BIN:-}"
append_candidate "${ROOT_DIR}/.venv/bin/python"
append_candidate "${VIRTUAL_ENV:-}/bin/python"
append_candidate "${CONDA_PREFIX:-}/bin/python"

conda_bases=()
if [[ -n "${CONDA_EXE:-}" ]]; then
  conda_bases+=("$(cd "$(dirname "${CONDA_EXE}")/.." && pwd)")
elif command -v conda >/dev/null 2>&1; then
  maybe_base="$(conda info --base 2>/dev/null || true)"
  [[ -n "${maybe_base}" ]] && conda_bases+=("${maybe_base}")
fi
for common_base in \
  "${HOME:-}/miniconda3" \
  "${HOME:-}/anaconda3" \
  "/opt/conda"; do
  [[ -d "${common_base}" ]] && conda_bases+=("${common_base}")
done

for conda_base in "${conda_bases[@]}"; do
  append_conda_env_candidates "${conda_base}"
done

if command -v python3 >/dev/null 2>&1; then
  append_candidate "$(command -v python3)"
fi
if command -v python >/dev/null 2>&1; then
  append_candidate "$(command -v python)"
fi

for candidate in "${_RESOLVE_PYTHON_CANDIDATES[@]}"; do
  if has_required_modules "${candidate}"; then
    echo "${candidate}"
    exit 0
  fi
done

{
  echo "Error: Could not locate a usable Python interpreter with required modules (fastapi, uvicorn, neo4j, sentence_transformers)."
  echo "Checked candidates in priority order:"
  for candidate in "${_RESOLVE_PYTHON_CANDIDATES[@]}"; do
    echo "  - ${candidate}"
  done
  echo "Hint: create the repo environment and install dependencies, e.g. .venv/bin/pip install -e . && .venv/bin/pip install -r requirements.txt"
} >&2
exit 1
