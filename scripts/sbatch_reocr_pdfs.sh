#!/usr/bin/env bash
# Submit from project root on SOL:
#   sbatch --array=0-15%6 scripts/sbatch_reocr_pdfs.sh
#
# Optional overrides:
#   PDF_DIR='\\192.168.0.37\pooled\media\Books\pdfs' \
#   OUTPUT_DIR=/scratch/$USER/researchAssistant/data/ocr/paddleocr \
#   BACKEND=paddleocr-vl \
#   VL_MODEL_DIR=/scratch/$USER/researchAssistant/models/PaddleOCR-VL-1.5 \
#   OCR_DEVICE=cpu OVERWRITE=0 \
#   sbatch --array=0-15%6 scripts/sbatch_reocr_pdfs.sh

#SBATCH -c 4
#SBATCH --mem=24G
#SBATCH -t 0-08:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -J reocr-paddle
#SBATCH -o slurm-%x-%A_%a.out
#SBATCH -e slurm-%x-%A_%a.err
#SBATCH --array=0-7%4
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=rjbischo@asu.edu
#SBATCH --export=ALL

set -eEuo pipefail

on_error() {
  local exit_code=$?
  local line_no="${1:-unknown}"
  echo "[ERROR] sbatch script failed at line ${line_no} (exit=${exit_code})." >&2
  exit "${exit_code}"
}
trap 'on_error $LINENO' ERR

SUBMIT_DIR="${SLURM_SUBMIT_DIR:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${SUBMIT_DIR}" ]]; then
  case "${SUBMIT_DIR}" in
    */scripts)
      PROJECT_ROOT="$(cd "${SUBMIT_DIR}/.." && pwd)"
      ;;
    *)
      PROJECT_ROOT="${SUBMIT_DIR}"
      ;;
  esac
else
  PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

PY_SCRIPT="${PROJECT_ROOT}/scripts/reocr_pdfs.py"
PDF_DIR="${PDF_DIR:-${PDF_SOURCE_DIR:-\\\\192.168.0.37\\pooled\\media\\Books\\pdfs}}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/data/ocr/paddleocr}"
SUMMARY_DIR="${SUMMARY_DIR:-${OUTPUT_DIR}/summaries}"
OCR_LANG="${OCR_LANG:-en}"
OCR_DEVICE="${OCR_DEVICE:-cpu}"   # cpu|gpu|auto
BACKEND="${BACKEND:-paddleocr-vl}"
VL_MODEL_DIR="${VL_MODEL_DIR:-${PROJECT_ROOT}/models/PaddleOCR-VL-1.5}"
OVERWRITE="${OVERWRITE:-0}"       # 1 = overwrite existing outputs
LIMIT="${LIMIT:-0}"               # Optional per-task cap (0 = unlimited)

MAMBA_MODULE="${MAMBA_MODULE:-mamba/latest}"
MAMBA_ENV_NAME="${MAMBA_ENV_NAME:-catmapper-paddleocr}"
MAMBA_ENV_PATH="${MAMBA_ENV_PATH:-/scratch/${USER}/.conda/envs/${MAMBA_ENV_NAME}}"
PYTHON_BIN="${PYTHON_BIN:-${MAMBA_ENV_PATH}/bin/python}"
PADDLEPADDLE_PKG="${PADDLEPADDLE_PKG:-paddlepaddle==3.2.0}"
PADDLEOCR_PKG="${PADDLEOCR_PKG:-paddleocr[doc-parser]==3.3.3}"
ENV_VERSION_TAG="${ENV_VERSION_TAG:-pp320_po333}"
ENV_READY_MARKER="${MAMBA_ENV_PATH}/.catmapper_paddleocr_env_ready_${ENV_VERSION_TAG}"
ENV_LOCK_FILE="${MAMBA_ENV_PATH}/.install.lock"
ENV_CREATE_LOCK="${MAMBA_ENV_PATH}/.create.lock"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "[ERROR] Missing OCR script: ${PY_SCRIPT}" >&2
  exit 1
fi
if [[ ! -d "${PDF_DIR}" ]]; then
  echo "[ERROR] PDF directory does not exist: ${PDF_DIR}" >&2
  exit 1
fi
if [[ "${BACKEND}" == "paddleocr-vl" && ! -d "${VL_MODEL_DIR}" ]]; then
  echo "[ERROR] PaddleOCR-VL model directory does not exist: ${VL_MODEL_DIR}" >&2
  exit 1
fi

if ! command -v module >/dev/null 2>&1; then
  if [[ -f /etc/profile.d/modules.sh ]]; then
    # shellcheck source=/etc/profile.d/modules.sh
    source /etc/profile.d/modules.sh
  fi
fi
if ! command -v module >/dev/null 2>&1; then
  echo "[ERROR] Environment modules command not found." >&2
  exit 1
fi

module purge || true
module load "${MAMBA_MODULE}"

mkdir -p "$(dirname "${ENV_CREATE_LOCK}")"
(
  flock -w 1200 9 || {
    echo "[ERROR] Could not acquire env create lock: ${ENV_CREATE_LOCK}" >&2
    exit 1
  }
  if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "[INFO] Creating mamba environment at ${MAMBA_ENV_PATH}"
    mamba create -y -p "${MAMBA_ENV_PATH}" python=3.11 pip
  fi
) 9>"${ENV_CREATE_LOCK}"

# shellcheck disable=SC1091
source activate "${MAMBA_ENV_PATH}"
export LD_LIBRARY_PATH="${MAMBA_ENV_PATH}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

mkdir -p "$(dirname "${ENV_LOCK_FILE}")"
(
  flock -w 1200 9 || {
    echo "[ERROR] Could not acquire env install lock: ${ENV_LOCK_FILE}" >&2
    exit 1
  }
  if [[ ! -f "${ENV_READY_MARKER}" ]]; then
    echo "[INFO] Installing PaddleOCR dependencies into ${MAMBA_ENV_PATH}"
    python -m pip install --upgrade pip
    python -m pip install --upgrade --force-reinstall \
      "${PADDLEPADDLE_PKG}" \
      "${PADDLEOCR_PKG}" \
      "PyMuPDF>=1.24,<1.27"
    touch "${ENV_READY_MARKER}"
  fi
) 9>"${ENV_LOCK_FILE}"

mkdir -p "${OUTPUT_DIR}" "${SUMMARY_DIR}"

TASK_ID="${SLURM_ARRAY_TASK_ID:-0}"
if [[ -n "${SLURM_ARRAY_TASK_COUNT:-}" && "${SLURM_ARRAY_TASK_COUNT}" != "0" ]]; then
  NUM_TASKS="${SLURM_ARRAY_TASK_COUNT}"
elif [[ -n "${SLURM_ARRAY_TASK_MAX:-}" ]]; then
  NUM_TASKS="$((SLURM_ARRAY_TASK_MAX + 1))"
else
  NUM_TASKS=1
fi

EXTRA_ARGS=()
if [[ "${OVERWRITE}" == "1" ]]; then
  EXTRA_ARGS+=(--overwrite)
fi
if [[ "${LIMIT}" != "0" ]]; then
  EXTRA_ARGS+=(--limit "${LIMIT}")
fi

echo "[INFO] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[INFO] PDF_DIR=${PDF_DIR}"
echo "[INFO] OUTPUT_DIR=${OUTPUT_DIR}"
echo "[INFO] SUMMARY_DIR=${SUMMARY_DIR}"
echo "[INFO] TASK_ID=${TASK_ID} NUM_TASKS=${NUM_TASKS}"
echo "[INFO] BACKEND=${BACKEND} VL_MODEL_DIR=${VL_MODEL_DIR}"
echo "[INFO] OCR_LANG=${OCR_LANG} OCR_DEVICE=${OCR_DEVICE}"
echo "[INFO] PADDLEPADDLE_PKG=${PADDLEPADDLE_PKG}"
echo "[INFO] PADDLEOCR_PKG=${PADDLEOCR_PKG}"

if [[ "${OCR_DEVICE}" == "gpu" || "${OCR_DEVICE}" == "auto" ]]; then
  if command -v nvidia-smi >/dev/null 2>&1; then
    echo "[INFO] Visible GPU devices:"
    nvidia-smi -L || true
  else
    echo "[WARN] OCR_DEVICE=${OCR_DEVICE}, but nvidia-smi is not available on this node."
  fi
fi

python "${PY_SCRIPT}" \
  --pdf-dir "${PDF_DIR}" \
  --output-dir "${OUTPUT_DIR}" \
  --summary-dir "${SUMMARY_DIR}" \
  --task-id "${TASK_ID}" \
  --num-tasks "${NUM_TASKS}" \
  --lang "${OCR_LANG}" \
  --backend "${BACKEND}" \
  --vl-model-dir "${VL_MODEL_DIR}" \
  --device "${OCR_DEVICE}" \
  "${EXTRA_ARGS[@]}"

echo "[INFO] Re-OCR task completed."
