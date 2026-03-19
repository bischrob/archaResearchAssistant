# Research Assistant RAG

Research Assistant is a Neo4j-backed PDF ingest and retrieval system with a web UI, Zotero-aware sync, citation parsing, and grounded search workflows.

## Start Here

- New user setup: [docs/NEW_USER_SETUP.md](docs/NEW_USER_SETUP.md)
- Documentation hub: [docs/INDEX.md](docs/INDEX.md)
- Model setup: [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md)
- Anystyle setup: [docs/ANYSTYLE_SETUP.md](docs/ANYSTYLE_SETUP.md)
- Citation-first lookup: [docs/CITATION_LOOKUP.md](docs/CITATION_LOOKUP.md)
- Troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## Included vs Excluded

Included in GitHub:

- application source
- tests
- scripts
- Zotero plugin scaffold
- public documentation

Excluded from GitHub:

- PDFs
- Neo4j runtime data
- local models
- logs
- `.env`
- local Vault notes
- Zotero debug logs

## LoRA Release Asset

Recommended citation-extraction LoRA:

- https://github.com/bischrob/archaResearchAssistant/releases/tag/lora-20260319-104710

## Supported Setup Matrix

- OS: Linux and WSL are the primary documented environments
- Docker: required
- Neo4j: required
- Zotero backend: recommended default
- GPU: optional
- OpenAI API key: required for grounded LLM answer flows
- Local Qwen3 base model: optional unless using local Qwen-powered parsing or preprocessing

## Quickstart

```bash
cp .env.example .env
make preflight
make start
make smoke
```

For full setup, including Zotero, LoRA, and Anystyle:

- [docs/NEW_USER_SETUP.md](docs/NEW_USER_SETUP.md)

## Core Workflow

1. Configure `.env` with your OpenAI key and Zotero paths.
2. Start the stack with `make start`.
3. Open the web UI and use `Sync + Ingest`.
4. Use `Search` for paper or chunk retrieval.

## Plugin

The Zotero plugin scaffold lives in:

- `plugins/zotero-rag-sync/`

It can trigger the combined backend sync and ingest workflow and supports bearer-token auth when enabled.

## Testing

```bash
make test-unit
make test-e2e
make smoke
```

## Local Conveniences

- Auto-versioning can be enabled locally with:

```bash
git config core.hooksPath .githooks
```

- Optional daily Dropbox sync helper:

```bash
scripts/rclone_sync_dropbox.sh
```
cd ~/researchAssistant
sbatch scripts/sbatch_sol_qwen3_reference_curriculum.sh
```

Queue-friendly overrides (still partial GPU, <=32GB RAM):

```bash
ssh sol
cd ~/researchAssistant
RUN_STAGE2=0 MAX_LENGTH=768 STAGE1_EPOCHS=1.0 sbatch scripts/sbatch_sol_qwen3_reference_curriculum.sh
```

Note: `USE_4BIT=0` is the default in this script for SOL stability. Enable only if needed:

```bash
USE_4BIT=1 sbatch scripts/sbatch_sol_qwen3_reference_curriculum.sh
```

Then run stage 2 in a separate job:

```bash
ssh sol
cd ~/researchAssistant
RUN_STAGE1=0 RUN_STAGE2=1 STAGE1_OUTPUT=models/qwen3-reference-lora-curriculum_<stage1_jobid>/stage1 \
  sbatch scripts/sbatch_sol_qwen3_reference_curriculum.sh
```

Generate extra supervision examples from sampled PDFs:

```bash
python scripts/generate_reference_lora_samples.py \
  --pdf-dir '\\192.168.0.37\pooled\media\Books\pdfs' \
  --paperpile-json Paperpile.json \
  --sample-pdfs 120 \
  --max-citations-per-pdf 18 \
  --existing-jsonl data/reference_lora_train.jsonl \
  --existing-jsonl data/reference_lora_eval.jsonl \
  --output-jsonl data/reference_lora_pdf_samples.jsonl \
  --summary-json data/reference_lora_pdf_samples_summary.json \
  --merge-into-train data/reference_lora_train.jsonl \
  --merge-into-eval data/reference_lora_eval.jsonl \
  --eval-ratio 0.15
```

Custom files:

```bash
python scripts/build_graph.py --mode custom \
  --pdf '\\192.168.0.37\pooled\media\Books\pdfs\file1.pdf' \
  --pdf '\\192.168.0.37\pooled\media\Books\pdfs\file2.pdf'
```

Query:

```bash
python scripts/query_graph.py "fremont culture chronology" --limit 5
```
