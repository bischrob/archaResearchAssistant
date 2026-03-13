# Qwen3 Reference Curriculum Training on SOL

## Purpose
- Train the Qwen3 reference LoRA with a staged curriculum.
- Stage 1 is synthetic/silver-heavy.
- Stage 2 is gold-heavy and continues from the stage 1 adapter.

## Scripts
- Dataset prep: [[40_Scripts/01_cli_scripts]] via `scripts/prepare_qwen_reference_curriculum.py`
- Trainer: `scripts/train_qwen_reference_lora.py`
- SOL batch launcher: `scripts/sbatch_sol_qwen3_reference_curriculum.sh`

## Curriculum Inputs
- Silver JSONL: `data/reference_lora_train.jsonl`, `data/reference_lora_eval.jsonl`
- Synthetic JSONL: `data/reference_lora_pdf_samples.jsonl`
- Gold supervision: `data/reference_lora_gold_articles.json`

## Outputs
- `data/reference_lora_curriculum/stage1_train.jsonl`
- `data/reference_lora_curriculum/stage1_eval.jsonl`
- `data/reference_lora_curriculum/stage2_train.jsonl`
- `data/reference_lora_curriculum/stage2_eval.jsonl`
- `data/reference_lora_curriculum/curriculum_summary.json`
- `models/qwen3-reference-lora-curriculum_<jobid>/stage1`
- `models/qwen3-reference-lora-curriculum_<jobid>/stage2`

## SOL Run
- `ssh sol`
- `cd ~/researchAssistant`
- `sbatch scripts/sbatch_sol_qwen3_reference_curriculum.sh`

## Resource Profile
- Default batch profile is queue-friendly:
- `#SBATCH -G 1g.20gb:1` (partial GPU node)
- `#SBATCH --mem=28G` (below 32GB)
- `#SBATCH -c 8`
- `#SBATCH -t 0-12:00:00`
- `MAX_LENGTH=768` default for lower memory pressure.
- `USE_4BIT=0` default to avoid SOL bitsandbytes/sitecustomize import recursion failures.

## Stage Control
- Stage toggles:
- `RUN_STAGE1=1` / `RUN_STAGE2=1` by default.
- Run stage 1 only:
- `RUN_STAGE2=0 sbatch scripts/sbatch_sol_qwen3_reference_curriculum.sh`
- Run stage 2 only (using existing stage 1 adapter):
- `RUN_STAGE1=0 RUN_STAGE2=1 STAGE1_OUTPUT=<path_to_stage1_adapter> sbatch ...`

## Notes
- The SOL script follows the same style as the CatMapper Vault SOL job pattern.
- `stage2` uses `--init-adapter-path <stage1>` to continue LoRA training rather than restarting from scratch.
