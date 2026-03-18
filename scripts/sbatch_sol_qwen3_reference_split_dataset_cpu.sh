#!/usr/bin/env bash
# Submit from project root on SOL:
#   sbatch scripts/sbatch_sol_qwen3_reference_split_dataset_cpu.sh
#
# Minimal CPU-only resource profile for split-dataset LoRA training.

#SBATCH -c 4
#SBATCH --mem=24G
#SBATCH -t 1-00:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -J qwen3-ref-split500-cpu
#SBATCH -o slurm-%x-%j.out
#SBATCH -e slurm-%x-%j.err
#SBATCH --mail-type=ALL
#SBATCH --mail-user=rjbischo@asu.edu
#SBATCH --export=ALL

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
MAMBA_ENV_NAME="${MAMBA_ENV_NAME:-catmapper-qwen3-ref}"
MAMBA_ENV_PATH="${MAMBA_ENV_PATH:-${HOME}/.conda/envs/${MAMBA_ENV_NAME}}"
PYTHON_BIN="${PYTHON_BIN:-${MAMBA_ENV_PATH}/bin/python}"
ENV_READY_MARKER="${MAMBA_ENV_PATH}/.catmapper_qwen3_ref_env_ready"
PYTHON_SHIM_DIR="${PROJECT_ROOT}/python_bootstrap"
TRAIN_SCRIPT="${PROJECT_ROOT}/scripts/train_qwen_reference_lora.py"

MODEL_PATH="${MODEL_PATH:-${PROJECT_ROOT}/models/base/Qwen3-4B-Instruct-2507}"
TRAIN_JSONL="${TRAIN_JSONL:-${PROJECT_ROOT}/data/qwen3_reference_audit/reference_split_local_500_20260317_train_eval/train.jsonl}"
EVAL_JSONL="${EVAL_JSONL:-${PROJECT_ROOT}/data/qwen3_reference_audit/reference_split_local_500_20260317_train_eval/eval.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}/models/qwen3-reference-split-500-cpu_${SLURM_JOB_ID:-manual}}"

SEED="${SEED:-42}"
EPOCHS="${EPOCHS:-1.0}"
LEARNING_RATE="${LEARNING_RATE:-2e-4}"
BATCH_SIZE="${BATCH_SIZE:-1}"
GRAD_ACCUM="${GRAD_ACCUM:-8}"
MAX_LENGTH="${MAX_LENGTH:-512}"
WARMUP_RATIO="${WARMUP_RATIO:-0.03}"
WEIGHT_DECAY="${WEIGHT_DECAY:-0.0}"
LORA_R="${LORA_R:-16}"
LORA_ALPHA="${LORA_ALPHA:-32}"
LORA_DROPOUT="${LORA_DROPOUT:-0.05}"

cancel_job() {
  local reason="$1"
  echo "[ERROR] ${reason}" >&2
  if [[ -n "${SLURM_JOB_ID:-}" ]]; then
    scancel "${SLURM_JOB_ID}" >/dev/null 2>&1 || true
  fi
  exit 1
}

on_error() {
  local exit_code=$?
  local line_no="${1:-unknown}"
  cancel_job "SBATCH script failed at line ${line_no} (exit=${exit_code})."
}
trap 'on_error $LINENO' ERR

cd "${PROJECT_ROOT}"

if [[ ! -f "${TRAIN_SCRIPT}" ]]; then
  cancel_job "Missing train script: ${TRAIN_SCRIPT}"
fi
if [[ ! -d "${MODEL_PATH}" ]]; then
  cancel_job "Base model path not found on SOL: ${MODEL_PATH}"
fi
if [[ ! -f "${TRAIN_JSONL}" ]]; then
  cancel_job "Training dataset not found: ${TRAIN_JSONL}"
fi
if [[ ! -f "${EVAL_JSONL}" ]]; then
  cancel_job "Eval dataset not found: ${EVAL_JSONL}"
fi

if ! command -v module >/dev/null 2>&1; then
  if [[ -f /etc/profile.d/modules.sh ]]; then
    # shellcheck source=/etc/profile.d/modules.sh
    source /etc/profile.d/modules.sh
  fi
fi
if ! command -v module >/dev/null 2>&1; then
  cancel_job "Environment modules command not found."
fi

module purge || true
module load "${MAMBA_MODULE}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "[INFO] Creating mamba environment at ${MAMBA_ENV_PATH}"
  mamba create -y -p "${MAMBA_ENV_PATH}" python=3.11 pip
fi

# shellcheck disable=SC1091
source activate "${MAMBA_ENV_PATH}"
export LD_LIBRARY_PATH="${MAMBA_ENV_PATH}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
if [[ -d "${PYTHON_SHIM_DIR}" ]]; then
  export PYTHONPATH="${PYTHON_SHIM_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
fi
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

if [[ ! -f "${ENV_READY_MARKER}" ]]; then
  echo "[INFO] Installing Python dependencies into ${MAMBA_ENV_PATH}"
  python -m pip install --upgrade pip
  python -m pip install \
    "torch>=2.6,<2.8" \
    "transformers>=4.51,<4.58" \
    "datasets>=3.4,<4" \
    "accelerate>=1.4,<1.11" \
    "trl>=0.20,<0.21" \
    "peft>=0.15,<0.18" \
    "sentencepiece>=0.2,<0.3" \
    "protobuf>=5.29,<7"
  touch "${ENV_READY_MARKER}"
fi

mkdir -p "${OUTPUT_DIR}"

echo "[INFO] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[INFO] MODEL_PATH=${MODEL_PATH}"
echo "[INFO] TRAIN_JSONL=${TRAIN_JSONL}"
echo "[INFO] EVAL_JSONL=${EVAL_JSONL}"
echo "[INFO] OUTPUT_DIR=${OUTPUT_DIR}"
echo "[INFO] CPU_ONLY=1 CPUS=${SLURM_CPUS_PER_TASK:-4} MEM=${SLURM_MEM_PER_NODE:-unknown}"

python "${TRAIN_SCRIPT}" \
  --model-path "${MODEL_PATH}" \
  --train-jsonl "${TRAIN_JSONL}" \
  --eval-jsonl "${EVAL_JSONL}" \
  --output-dir "${OUTPUT_DIR}" \
  --epochs "${EPOCHS}" \
  --learning-rate "${LEARNING_RATE}" \
  --batch-size "${BATCH_SIZE}" \
  --grad-accum "${GRAD_ACCUM}" \
  --max-length "${MAX_LENGTH}" \
  --warmup-ratio "${WARMUP_RATIO}" \
  --weight-decay "${WEIGHT_DECAY}" \
  --lora-r "${LORA_R}" \
  --lora-alpha "${LORA_ALPHA}" \
  --lora-dropout "${LORA_DROPOUT}" \
  --gradient-checkpointing \
  --seed "${SEED}"

echo "[INFO] CPU split-dataset training completed successfully."
