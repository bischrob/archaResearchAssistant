#!/usr/bin/env bash
# Submit from project root on SOL:
#   sbatch scripts/sbatch_sol_qwen3_reference_eval.sh
#
# Minimal-resource evaluation for latest Qwen3 reference adapter.

#SBATCH -c 4
#SBATCH --mem=16G
#SBATCH -t 0-04:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -G 1g.20gb:1
#SBATCH -J qwen3-ref-eval
#SBATCH -o slurm-%x-%j.out
#SBATCH -e slurm-%x-%j.err
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=rjbischo@asu.edu
#SBATCH --export=NONE

set -eEuo pipefail

SUBMIT_DIR="${SLURM_SUBMIT_DIR:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${SUBMIT_DIR}" ]]; then
  case "${SUBMIT_DIR}" in
    */scripts) PROJECT_ROOT="$(cd "${SUBMIT_DIR}/.." && pwd)" ;;
    *) PROJECT_ROOT="${SUBMIT_DIR}" ;;
  esac
else
  PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

MAMBA_MODULE="${MAMBA_MODULE:-mamba/latest}"
MAMBA_ENV_PATH="${MAMBA_ENV_PATH:-${HOME}/.conda/envs/catmapper-qwen3-ref}"
EVAL_SCRIPT="${PROJECT_ROOT}/scripts/eval_qwen_reference_adapter_accuracy.py"

BASE_MODEL_PATH="${BASE_MODEL_PATH:-${PROJECT_ROOT}/models/base/Qwen3-4B-Instruct-2507}"
ADAPTER_PATH="${ADAPTER_PATH:-${PROJECT_ROOT}/models/qwen3-reference-split-500-cpu_49006992}"
EVAL_JSONL="${EVAL_JSONL:-${PROJECT_ROOT}/data/qwen3_reference_audit/reference_split_local_500_20260317_train_eval/eval.jsonl}"
MAX_ROWS="${MAX_ROWS:-0}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-96}"
QWEN_MAX_INPUT_CHARS="${QWEN_MAX_INPUT_CHARS:-6000}"
SKIP_SECTION_EVAL="${SKIP_SECTION_EVAL:-1}"
OUTPUT_JSON="${OUTPUT_JSON:-${PROJECT_ROOT}/data/qwen3_reference_audit/latest_qwen3_accuracy_eval_${SLURM_JOB_ID:-manual}.json}"

on_error() {
  local exit_code=$?
  local line_no="${1:-unknown}"
  echo "[ERROR] SBATCH script failed at line ${line_no} (exit=${exit_code})." >&2
  exit "${exit_code}"
}
trap 'on_error $LINENO' ERR

cd "${PROJECT_ROOT}"

for path in "${EVAL_SCRIPT}" "${EVAL_JSONL}"; do
  if [[ ! -f "${path}" ]]; then
    echo "[ERROR] Missing required file: ${path}" >&2
    exit 1
  fi
done
for path in "${BASE_MODEL_PATH}" "${ADAPTER_PATH}"; do
  if [[ ! -d "${path}" ]]; then
    echo "[ERROR] Missing required model directory: ${path}" >&2
    exit 1
  fi
done

if ! command -v module >/dev/null 2>&1; then
  # shellcheck source=/etc/profile.d/modules.sh
  source /etc/profile.d/modules.sh
fi
module purge || true
module load "${MAMBA_MODULE}"

# shellcheck disable=SC1091
source activate "${MAMBA_ENV_PATH}"
export LD_LIBRARY_PATH="${MAMBA_ENV_PATH}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

echo "[INFO] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[INFO] BASE_MODEL_PATH=${BASE_MODEL_PATH}"
echo "[INFO] ADAPTER_PATH=${ADAPTER_PATH}"
echo "[INFO] EVAL_JSONL=${EVAL_JSONL}"
echo "[INFO] OUTPUT_JSON=${OUTPUT_JSON}"
echo "[INFO] MAX_ROWS=${MAX_ROWS} MAX_NEW_TOKENS=${MAX_NEW_TOKENS}"
echo "[INFO] SKIP_SECTION_EVAL=${SKIP_SECTION_EVAL}"

EXTRA_ARGS=()
if [[ "${SKIP_SECTION_EVAL}" == "1" ]]; then
  EXTRA_ARGS+=(--skip-section-eval)
fi

python "${EVAL_SCRIPT}" \
  --eval-jsonl "${EVAL_JSONL}" \
  --base-model-path "${BASE_MODEL_PATH}" \
  --adapter-path "${ADAPTER_PATH}" \
  --output-json "${OUTPUT_JSON}" \
  --max-rows "${MAX_ROWS}" \
  --max-new-tokens "${MAX_NEW_TOKENS}" \
  --qwen-max-input-chars "${QWEN_MAX_INPUT_CHARS}" \
  --device auto \
  --dtype auto \
  "${EXTRA_ARGS[@]}"

echo "[INFO] Evaluation completed successfully."
