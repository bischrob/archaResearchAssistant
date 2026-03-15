# CLI Scripts (Python)

## Source files
- `scripts/build_graph.py`
- `scripts/build_graph_anystyle_test.py`
- `scripts/query_graph.py`
- `scripts/init_neo4j_indexes.py`
- `scripts/find_pdfs_missing_metadata.py`
- `scripts/export_paperpile_json.py`
- `scripts/apply_reference_corrections.py`
- `scripts/train_qwen_reference_lora.py`
- `scripts/generate_reference_lora_samples.py`
- `scripts/audit_qwen3_reference_split.py`
- `scripts/build_qwen_reference_split_jsonl_from_ocr.py`

## `build_graph.py`
- Purpose: choose + ingest PDFs from CLI.
- Inputs: mode, pdf-dir, partial-count, explicit `--pdf`, `--override-existing`.
- Uses `choose_pdfs` and `ingest_pdfs`.
- Uses shared citation parser config (`CITATION_PARSER`; default `qwen_refsplit_anystyle`) and reports parser stats in output.

## `build_graph_anystyle_test.py`
- Purpose: run test ingest through the same shared ingest pipeline while forcing Anystyle mode.
- Inputs: ingest mode args plus `--anystyle-service`, `--anystyle-timeout`, `--require-anystyle`.
- Behavior: relies on pipeline-native Anystyle extraction/caching/fallback behavior (no separate pre-pass override logic).
- Re-ingest behavior is duplicate-safe for per-article references because existing reference/citation edges are refreshed before write.

## `query_graph.py`
- Purpose: run contextual retrieval from CLI.
- Inputs: query string, limit.
- Prints ranked results with chunk excerpt and citation neighborhood.

## `init_neo4j_indexes.py`
- Purpose: wait for Neo4j, create schema, list indexes/constraints.
- Inputs: wait/retry parameters.
- Useful for startup and troubleshooting schema state.

## `find_pdfs_missing_metadata.py`
- Purpose: detect PDFs without Paperpile attachment metadata match.
- Outputs: CSV with filename and paths.

## `export_paperpile_json.py`
- Purpose: automate export of full Paperpile library metadata to JSON via browser automation.
- Behavior: launches persistent Chromium profile by default, supports first-run manual Google sign-in, and can also attach to an already-open Chrome session over CDP (`--attach-cdp`).
- Export path: `Settings > Data and files > Export data`.
- Output: JSON file (default `Paperpile.json`).

## `apply_reference_corrections.py`
- Purpose: apply iterative Neo4j reference cleanup from `corrections/export.csv`.
- Behavior: refreshes `Article` metadata from `Paperpile.json`, deletes invalid `Reference` nodes (`valid=F`), resolves corrected references to `Article` by `citekey`, auto-creates missing `Article` stubs from `Paperpile.json` for unresolved citekeys, then removes stale reference-derived `CITES` edges.
- Supports `--dry-run` preview mode before writes.

## `train_qwen_reference_lora.py`
- Purpose: fine-tune a Qwen LoRA adapter for reference extraction from JSONL supervision data.
- Inputs: base model path (`--model-path`), train/eval JSONL (`--train-jsonl`, `--eval-jsonl`), LoRA hyperparameters, output directory.
- Output: adapter weights + tokenizer files for use via `QWEN3_CITATION_ADAPTER_PATH` (and optionally `QWEN3_QUERY_ADAPTER_PATH`).

## `generate_reference_lora_samples.py`
- Purpose: sample local PDFs, extract citation candidates, and generate additional JSONL supervision rows in chat-message format.
- Inputs: `--pdf-dir`, sample size/seed, citation quality filters, optional existing JSONLs for dedup, optional merge targets for train/eval.
- Output: standalone sample JSONL + summary JSON; can also rewrite merged train/eval splits.

## `audit_qwen3_reference_split.py`
- Purpose: audit Qwen3 section/reference detection and reference splitting with markdown artifacts.
- Pipeline under test:
  - Step 1: Qwen3 identifies section boundaries and reference chunk(s).
  - Step 2: Qwen3 splits each reference chunk into individual references.
- Inputs: one or more `--pdf` paths (UNC or WSL paths supported), optional `--pdf-dir`, optional output directory.
- Output: per-PDF markdown report + raw reference chunk text files + summary markdown under `data/qwen3_reference_audit/`.

## `build_qwen_reference_split_jsonl_from_ocr.py`
- Purpose: generate split-reference training JSONL from OCR text using a local heuristic parser as pseudo-gold labels.
- Inputs: OCR directory, anchor OCR file, sample count/seed, min/max parsed-reference thresholds.
- Output:
  - JSONL with `task=split_reference_chunk` rows (`messages` + `meta`) for Qwen3 training.
  - Per-document markdown audits in `data/qwen3_reference_audit/local_split_dataset/`.
  - Dataset summary markdown with selected docs and parsed-reference counts.

## Shared behavior
Each script prepends repo root to `sys.path` to allow `src.*` imports without package install.

## Related
- [[10_Backend/04_ingest_pipeline_module]]
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
