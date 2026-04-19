#!/usr/bin/env bash
# Submit from project root on SOL:
#   sbatch scripts/sbatch_reference_lora_curriculum.sh
#
# Optional overrides:
#   MODEL_PATH=/path/to/Qwen3-4B-Instruct-2507 \
#   OUTPUT_ROOT=/path/to/output \
#   sbatch scripts/sbatch_reference_lora_curriculum.sh

#SBATCH -c 8
#SBATCH --mem=28G
#SBATCH -t 0-12:00:00
#SBATCH -p public
#SBATCH -q public
#SBATCH -G 1g.20gb:1
#SBATCH -J qwen3-ref-curriculum
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

MAMBA_MODULE="${MAMBA_MODULE:-mamba/latest}"
MAMBA_ENV_NAME="${MAMBA_ENV_NAME:-catmapper-qwen3-ref}"
MAMBA_ENV_PATH="${MAMBA_ENV_PATH:-${HOME}/.conda/envs/${MAMBA_ENV_NAME}}"
PYTHON_BIN="${PYTHON_BIN:-${MAMBA_ENV_PATH}/bin/python}"
ENV_READY_MARKER="${MAMBA_ENV_PATH}/.catmapper_qwen3_ref_env_ready"
ENV_SETUP_LOCK="${MAMBA_ENV_PATH}/.setup.lock"
PYTHON_SHIM_DIR="${PROJECT_ROOT}/python_bootstrap"

PREP_SCRIPT="${PROJECT_ROOT}/scripts/prepare_reference_lora_curriculum.py"
TRAIN_SCRIPT="${PROJECT_ROOT}/scripts/train_reference_lora.py"

CURRICULUM_DIR="${CURRICULUM_DIR:-${PROJECT_ROOT}/data/reference_lora_curriculum}"
GOLD_JSON="${GOLD_JSON:-${PROJECT_ROOT}/data/reference_lora_gold_articles.json}"
SILVER_JSONL_1="${SILVER_JSONL_1:-${PROJECT_ROOT}/data/reference_lora_train.jsonl}"
SILVER_JSONL_2="${SILVER_JSONL_2:-${PROJECT_ROOT}/data/reference_lora_eval.jsonl}"
SYNTH_JSONL_1="${SYNTH_JSONL_1:-${PROJECT_ROOT}/data/reference_lora_pdf_samples.jsonl}"

MODEL_PATH="${MODEL_PATH:-${PROJECT_ROOT}/models/base/Qwen3-4B-Instruct-2507}"
OUTPUT_ROOT="${OUTPUT_ROOT:-${PROJECT_ROOT}/models/qwen3-reference-lora-curriculum_${SLURM_JOB_ID:-manual}}"
STAGE1_OUTPUT="${STAGE1_OUTPUT:-${OUTPUT_ROOT}/stage1}"
STAGE2_OUTPUT="${STAGE2_OUTPUT:-${OUTPUT_ROOT}/stage2}"

SEED="${SEED:-42}"
EVAL_RATIO="${EVAL_RATIO:-0.15}"
STAGE1_WEIGHTS="${STAGE1_WEIGHTS:-synthetic=6,silver=3,gold=1}"
STAGE2_WEIGHTS="${STAGE2_WEIGHTS:-gold=6,silver=3,synthetic=1}"
STAGE1_TASK_WEIGHTS="${STAGE1_TASK_WEIGHTS:-parse_reference_json=1,split_reference_chunk=3}"
STAGE2_TASK_WEIGHTS="${STAGE2_TASK_WEIGHTS:-parse_reference_json=1,split_reference_chunk=6}"
SPLIT_FROM_PARSE_PER_TIER="${SPLIT_FROM_PARSE_PER_TIER:-160}"
SPLIT_WINDOW_SIZE="${SPLIT_WINDOW_SIZE:-12}"
SPLIT_WINDOW_STEP="${SPLIT_WINDOW_STEP:-8}"
SPLIT_NOISE_PROB="${SPLIT_NOISE_PROB:-0.35}"

STAGE1_EPOCHS="${STAGE1_EPOCHS:-1.0}"
STAGE2_EPOCHS="${STAGE2_EPOCHS:-1.0}"
LEARNING_RATE="${LEARNING_RATE:-2e-4}"
BATCH_SIZE="${BATCH_SIZE:-1}"
GRAD_ACCUM="${GRAD_ACCUM:-8}"
MAX_LENGTH="${MAX_LENGTH:-768}"
WARMUP_RATIO="${WARMUP_RATIO:-0.03}"
WEIGHT_DECAY="${WEIGHT_DECAY:-0.0}"
LORA_R="${LORA_R:-16}"
LORA_ALPHA="${LORA_ALPHA:-32}"
LORA_DROPOUT="${LORA_DROPOUT:-0.05}"
STAGE1_MAX_TRAIN="${STAGE1_MAX_TRAIN:-2000}"
STAGE2_MAX_TRAIN="${STAGE2_MAX_TRAIN:-3000}"
RUN_STAGE1="${RUN_STAGE1:-1}"
RUN_STAGE2="${RUN_STAGE2:-1}"
USE_4BIT="${USE_4BIT:-0}"
SPLIT_SAMPLE_LOSS_WEIGHT="${SPLIT_SAMPLE_LOSS_WEIGHT:-1.6}"
SPLIT_BOUNDARY_LOSS_WEIGHT="${SPLIT_BOUNDARY_LOSS_WEIGHT:-2.2}"

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

if [[ ! -f "${PREP_SCRIPT}" ]]; then
  cancel_job "Missing preparation script: ${PREP_SCRIPT}"
fi
if [[ ! -f "${TRAIN_SCRIPT}" ]]; then
  cancel_job "Missing training script: ${TRAIN_SCRIPT}"
fi
if [[ ! -d "${MODEL_PATH}" ]]; then
  cancel_job "Base model path not found on SOL: ${MODEL_PATH}"
fi
if [[ ! -f "${GOLD_JSON}" ]]; then
  cancel_job "Gold supervision file not found: ${GOLD_JSON}"
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

mkdir -p "$(dirname "${ENV_SETUP_LOCK}")"
(
  flock -w 1200 9 || {
    echo "[ERROR] Could not acquire env setup lock: ${ENV_SETUP_LOCK}" >&2
    exit 1
  }

  if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "[INFO] Creating mamba environment at ${MAMBA_ENV_PATH}"
    mamba create -y -p "${MAMBA_ENV_PATH}" python=3.11 pip
  fi

  # shellcheck disable=SC1091
  source activate "${MAMBA_ENV_PATH}"

  if [[ ! -f "${ENV_READY_MARKER}" ]]; then
    echo "[INFO] Installing Python dependencies into ${MAMBA_ENV_PATH}"
    python -m pip install --upgrade pip
    BASE_PIP_PACKAGES=(
      "torch>=2.6,<2.8" \
      "transformers>=4.51,<4.58" \
      "datasets>=3.4,<4" \
      "accelerate>=1.4,<1.11" \
      "trl>=0.20,<0.21" \
      "peft>=0.15,<0.18" \
      "sentencepiece>=0.2,<0.3" \
      "protobuf>=5.29,<7"
    )
    if [[ "${USE_4BIT}" == "1" ]]; then
      BASE_PIP_PACKAGES+=("bitsandbytes>=0.45,<0.49")
    fi
    python -m pip install "${BASE_PIP_PACKAGES[@]}"
    touch "${ENV_READY_MARKER}"
  fi
) 9>"${ENV_SETUP_LOCK}"

# shellcheck disable=SC1091
source activate "${MAMBA_ENV_PATH}"
export LD_LIBRARY_PATH="${MAMBA_ENV_PATH}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
if [[ -d "${PYTHON_SHIM_DIR}" ]]; then
  export PYTHONPATH="${PYTHON_SHIM_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
fi

mkdir -p "${CURRICULUM_DIR}" "${STAGE1_OUTPUT}" "${STAGE2_OUTPUT}"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  cancel_job "nvidia-smi not found. GPU node was not provisioned correctly."
fi

echo "[INFO] PROJECT_ROOT=${PROJECT_ROOT}"
echo "[INFO] MODEL_PATH=${MODEL_PATH}"
echo "[INFO] CURRICULUM_DIR=${CURRICULUM_DIR}"
echo "[INFO] OUTPUT_ROOT=${OUTPUT_ROOT}"
echo "[INFO] USE_4BIT=${USE_4BIT}"
echo "[INFO] CUDA devices visible:"
nvidia-smi -L

FOURBIT_ARGS=()
if [[ "${USE_4BIT}" == "1" ]]; then
  FOURBIT_ARGS=(--load-in-4bit)
fi

python "${PREP_SCRIPT}" \
  --silver-jsonl "${SILVER_JSONL_1}" \
  --silver-jsonl "${SILVER_JSONL_2}" \
  --synthetic-jsonl "${SYNTH_JSONL_1}" \
  --gold-articles-json "${GOLD_JSON}" \
  --output-dir "${CURRICULUM_DIR}" \
  --eval-ratio "${EVAL_RATIO}" \
  --seed "${SEED}" \
  --stage1-max-train "${STAGE1_MAX_TRAIN}" \
  --stage2-max-train "${STAGE2_MAX_TRAIN}" \
  --stage1-weights "${STAGE1_WEIGHTS}" \
  --stage2-weights "${STAGE2_WEIGHTS}" \
  --stage1-task-weights "${STAGE1_TASK_WEIGHTS}" \
  --stage2-task-weights "${STAGE2_TASK_WEIGHTS}" \
  --split-from-parse-per-tier "${SPLIT_FROM_PARSE_PER_TIER}" \
  --split-window-size "${SPLIT_WINDOW_SIZE}" \
  --split-window-step "${SPLIT_WINDOW_STEP}" \
  --split-noise-prob "${SPLIT_NOISE_PROB}"

if [[ "${RUN_STAGE1}" == "1" ]]; then
  python "${TRAIN_SCRIPT}" \
    --model-path "${MODEL_PATH}" \
    --train-jsonl "${CURRICULUM_DIR}/stage1_train.jsonl" \
    --eval-jsonl "${CURRICULUM_DIR}/stage1_eval.jsonl" \
    --output-dir "${STAGE1_OUTPUT}" \
    --epochs "${STAGE1_EPOCHS}" \
    --learning-rate "${LEARNING_RATE}" \
    --batch-size "${BATCH_SIZE}" \
    --grad-accum "${GRAD_ACCUM}" \
    --max-length "${MAX_LENGTH}" \
    --warmup-ratio "${WARMUP_RATIO}" \
    --weight-decay "${WEIGHT_DECAY}" \
    --lora-r "${LORA_R}" \
    --lora-alpha "${LORA_ALPHA}" \
    --lora-dropout "${LORA_DROPOUT}" \
    --split-sample-loss-weight "${SPLIT_SAMPLE_LOSS_WEIGHT}" \
    --split-boundary-loss-weight "${SPLIT_BOUNDARY_LOSS_WEIGHT}" \
    --gradient-checkpointing \
    --seed "${SEED}" \
    "${FOURBIT_ARGS[@]}"
fi

if [[ "${RUN_STAGE2}" == "1" ]]; then
  if [[ ! -f "${STAGE1_OUTPUT}/adapter_config.json" ]]; then
    cancel_job "Stage 2 requested, but stage 1 adapter not found at ${STAGE1_OUTPUT}"
  fi
  python "${TRAIN_SCRIPT}" \
    --model-path "${MODEL_PATH}" \
    --init-adapter-path "${STAGE1_OUTPUT}" \
    --train-jsonl "${CURRICULUM_DIR}/stage2_train.jsonl" \
    --eval-jsonl "${CURRICULUM_DIR}/stage2_eval.jsonl" \
    --output-dir "${STAGE2_OUTPUT}" \
    --epochs "${STAGE2_EPOCHS}" \
    --learning-rate "${LEARNING_RATE}" \
    --batch-size "${BATCH_SIZE}" \
    --grad-accum "${GRAD_ACCUM}" \
    --max-length "${MAX_LENGTH}" \
    --warmup-ratio "${WARMUP_RATIO}" \
    --weight-decay "${WEIGHT_DECAY}" \
    --lora-r "${LORA_R}" \
    --lora-alpha "${LORA_ALPHA}" \
    --lora-dropout "${LORA_DROPOUT}" \
    --split-sample-loss-weight "${SPLIT_SAMPLE_LOSS_WEIGHT}" \
    --split-boundary-loss-weight "${SPLIT_BOUNDARY_LOSS_WEIGHT}" \
    --gradient-checkpointing \
    --seed "${SEED}" \
    "${FOURBIT_ARGS[@]}"
fi

echo "[INFO] Curriculum training completed successfully."
