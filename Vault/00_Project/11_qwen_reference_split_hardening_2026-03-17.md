# Qwen Reference Split Hardening (2026-03-17)

Parent: [[00_Project/09_qwen3_reference_curriculum_training_on_sol]]

## Goal
- Improve reference split quality on holdout PDFs by addressing merged outputs and post-reference noise.

## Implemented
- Curriculum builder updates in `scripts/prepare_qwen_reference_curriculum.py`:
  - Canonicalized split targets to one-reference-per-item with marker/noise stripping.
  - Added split-task synthesis from parse pools (`--split-from-parse-per-tier`, windowing controls).
  - Added hard-negative noise injection (`--split-noise-prob`) for captions/padding artifacts.
  - Added task-level stage weights (`--stage1-task-weights`, `--stage2-task-weights`).
- Training updates in `scripts/train_qwen_reference_lora.py`:
  - Added weighted loss for split samples and boundary tokens via:
    - `--split-sample-loss-weight`
    - `--split-boundary-loss-weight`
  - Implemented `WeightedLossTrainer` with token-level weighted CE.
- Runtime split guardrails in `src/rag/qwen_structured_refs.py`:
  - Added strict two-pass prompt retry.
  - Added sanitization and de-merge logic for multi-reference items.
  - Added noise filtering and numbered-reference fallback extraction.
- SOL launcher wiring in `scripts/sbatch_sol_qwen3_reference_curriculum.sh` for all new knobs.

## Validation Snapshot
- Holdout PDF test (`data/tmp_pdf_test/holdout.pdf`) before patch: Qwen split count 7 (merged/noisy).
- Same model after runtime patch: Qwen split count 39 (major improvement; minor split errors remain).

## Follow-up
- Retrain stage1/stage2 with new curriculum and weighted loss settings.
- Re-run holdout audit and smoke eval to measure split exactness and contamination rates.
