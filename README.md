# Research Assistant RAG (Neo4j + Web GUI)

This project provides:

- PDF sync from Google Drive (`rclone`)
- Ingestion into Neo4j (`Article`, `Author`, `Chunk`, `Token`, `Reference`, `CITES`)
- Contextual retrieval (token + vector signal + citation neighborhood)
- A web GUI for sync, ingest, and search
- Metadata enrichment from `Paperpile.json` (title, authors, year, citekey, DOI, journal, publisher)
- Grounded LLM Q&A via OpenAI API using only retrieved RAG context and returning citations

## 1) Start Neo4j

```bash
docker compose up -d neo4j
```

Default DB env values:

- `NEO4J_URI=bolt://localhost:7687`
- `NEO4J_USER=neo4j`
- `NEO4J_PASSWORD=archaResearchAssistant`
- `PAPERPILE_JSON=Paperpile.json`
- `OPENAI_API_KEY=...`
- `OPENAI_MODEL=gpt-5.1` (optional; defaults to `gpt-5.1`)
- `CITATION_MIN_QUALITY=0.35` (optional; drops low-quality parsed references during ingest)
- `CHUNK_STRIP_PAGE_NOISE=1` (optional; strips repeated headers/footers/page numbers before chunking)
- `CITATION_PARSER=anystyle` (default; supports `anystyle`, `heuristic`, `qwen`/`qwen_lora`, and `qwen_refsplit_anystyle`)
- `ANYSTYLE_SERVICE=anystyle` (optional; docker compose service name)
- `ANYSTYLE_GPU_SERVICE=anystyle-gpu` (optional; docker compose service used when GPU mode is enabled)
- `ANYSTYLE_TIMEOUT_SECONDS=240` (optional; timeout per PDF)
- `ANYSTYLE_REQUIRE_SUCCESS=0` (optional; if `1`, ingest fails when Anystyle extraction fails)
- `ANYSTYLE_USE_GPU=0` (optional; if `1`, routes parsing to `ANYSTYLE_GPU_SERVICE`)
- `ANYSTYLE_GPU_DEVICES=all` (optional; compose `gpus:` value for `anystyle-gpu`, e.g. `all` or `device=0`)
- `QUERY_PREPROCESS_BACKEND=openai` (optional; set `qwen` to run query rewrite locally and reduce OpenAI tokens)
- `QWEN3_MODEL_PATH=...` (optional; base local Qwen3 model path, Windows paths are supported)
- `QWEN3_CITATION_ADAPTER_PATH=...` (optional; LoRA adapter for citation extraction)
- `QWEN3_QUERY_ADAPTER_PATH=...` (optional; LoRA adapter for query preprocessing)
- `QWEN3_REQUIRE_SUCCESS=0` (optional; if `1`, ingest fails if Qwen citation extraction fails)

Example for your model directory:

```bash
export QWEN3_MODEL_PATH='C:\Users\rjbischo\ASU Dropbox\Robert Bischoff\RA\CatMapper\LLM'
```

## 2) Sync PDFs from Google Drive

The script uses:

- `gdrive:Library/Paperpile/allPapers` -> local `pdfs/`

Run:

```bash
scripts/sync_pdfs_from_gdrive.sh
```

Dry-run:

```bash
scripts/sync_pdfs_from_gdrive.sh --dry-run
```

## 2b) Export Paperpile references as JSON (browser automation)

Install browser automation dependencies once:

```bash
pip install playwright
python -m playwright install chromium
```

Run export:

```bash
python scripts/export_paperpile_json.py --output Paperpile.json
```

Notes:

- Uses a persistent Chromium profile (`.cache/paperpile-playwright-profile`) so Google sign-in is usually only needed once.
- First run opens a browser window; complete Google login manually if prompted.
- If Google blocks login with a "browser/app not secure" message, run with system Chrome channel:
  - `python scripts/export_paperpile_json.py --browser-channel chrome --output Paperpile.json`
- CDP attach mode (uses an already-open Chrome session):
  - Start Chrome with remote debugging on port `9222` (use a dedicated profile directory):
    - Linux: `google-chrome --remote-debugging-port=9222 --user-data-dir=$HOME/.cache/chrome-cdp-paperpile`
    - macOS: `/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir=$HOME/.cache/chrome-cdp-paperpile`
  - Verify CDP endpoint is live: `curl http://127.0.0.1:9222/json/version`
  - Then run:
    - `python scripts/export_paperpile_json.py --attach-cdp --cdp-url http://127.0.0.1:9222 --output Paperpile.json`
- Script targets `Settings -> Data and files -> Export data -> JSON` and falls back to waiting for manual export clicks while capturing the download.

## 2c) Apply reference corrections (repeatable cleanup)

Use this after placing your correction file at `corrections/export.csv` with:

- `valid = F` for invalid/non-reference rows.
- `citekey = <Paperpile citekey>` for valid references that should resolve to an existing `Article`.

Dry-run first (no database writes):

```bash
python scripts/apply_reference_corrections.py --dry-run
```

Apply changes:

```bash
python scripts/apply_reference_corrections.py
```

What it does in order:

- refreshes existing `Article` metadata from the current `Paperpile.json` (citekey/doi/title/year/etc.)
- deletes invalid `Reference` nodes based on `valid = F`
- resolves valid references to `Article` nodes by `citekey` and writes manual `CITES` links
- if a correction citekey is missing in `Article`, it creates a lightweight `Article` stub from `Paperpile.json` and then links to it
- removes stale reference-derived `CITES` edges left unsupported after cleanup

## 3) Run the web GUI

```bash
./start.sh
```

Open:

- `start.sh` prints the URL. Default is `http://localhost:8000`, but it will auto-pick the next open port if `8000` is busy.

## 4) Enable auto-versioning on commit

The repository includes hooks that:

- update `webapp/main.py` `FastAPI(..., version="...")` to a UTC datetime version
- create a matching git tag (`v<version>`) after each commit

Enable them in your local clone:

```bash
git config core.hooksPath .githooks
```

`start.sh` will:

- ensure the Neo4j container is running
- initialize Neo4j constraints/indexes (`scripts/init_neo4j_indexes.py`)
- launch the web app

The GUI includes in-app instructions and buttons for:

- health/stats
- sync PDFs
- ingest modes:
  - `batch` (batch upload; first N via `partial_count`, default 3)
  - `all` (all PDFs in `pdfs/`, automatically processed in batches of `partial_count`)
  - `custom` (specific files)
- contextual query
- pre-LLM query parsing (tokens, years, phrases, author terms) with multi-channel retrieval
- stop/cancel for sync, ingest, and query jobs
- grounded ChatGPT Q&A with configurable RAG context size
- export of answer reports (Markdown, CSV, PDF via pandoc)
- a dedicated `Model Details & Diagnostics` tab with architecture notes and environment/data checks

Notes:

- `all` mode can take time on large libraries.
- unreadable/non-PDF-content files are skipped and returned in `failed_pdfs`.
- ingest is non-destructive and does not erase existing Neo4j data.
- default ingest behavior skips already-ingested PDFs; use override existing to reprocess.
- in `batch` mode, selection order is: readable PDFs -> skip existing (unless override) -> metadata filter -> first N.
- in `all` mode, selected PDFs are processed as sequential batches and progress is updated after each batch.
- ingest metadata is pulled from `Paperpile.json` by matching attachment filename to the local PDF basename.
- PDFs without matching `Paperpile.json` metadata are skipped automatically.
- ingest uses Anystyle citation extraction by default and falls back to the built-in heuristic parser if Anystyle fails or returns no references.
- ingest can alternatively run local Qwen3 LoRA citation parsing when `CITATION_PARSER=qwen`.
- ingest can run a structured hybrid pipeline when `CITATION_PARSER=qwen_refsplit_anystyle`:
  qwen detects section boundaries/headings, qwen splits reference sections into individual reference strings, then anystyle parses those strings into structured citation fields.
- ingest drops low-quality references using the `CITATION_MIN_QUALITY` threshold.
- re-ingesting a PDF refreshes its `Reference` nodes/edges to avoid stale duplicate reference data.
- chunk extraction can strip repeated page headers/footers and page numbers (`CHUNK_STRIP_PAGE_NOISE`).
- LLM answers are citation-grounded and include `[C#]` references mapped to source chunks.
- LLM answers are rendered as Markdown in the UI.
- Retrieval is two-pass: broader candidate recall (vector + token + author channels) followed by stricter reranking on chunk/title/author/year/phrase and citation-neighborhood signals.
- Ask flow defaults to pre-LLM query rewrite; responses include the exact `search_query_used` for transparency.
- Ask flow query rewrite can run on local Qwen3 (`QUERY_PREPROCESS_BACKEND=qwen`) before grounded ChatGPT answering.

PDF export dependency:

- Install `pandoc` and at least one PDF engine (`xelatex`, `pdflatex`, `wkhtmltopdf`, or `weasyprint`) available in `PATH`.

## 5) Diagnostics and model structure

Use the **Model Details & Diagnostics** tab in the web UI to inspect:

- pipeline architecture (source metadata -> graph model -> retrieval -> grounded LLM answer)
- graph schema (`Article`, `Author`, `Chunk`, `Token`, `Reference`, `CITES`)
- retrieval strategy (token + vector + rerank)
- grounding and citation enforcement design

Click **Run Diagnostics** to execute runtime checks:

- `paperpile_json_exists`
- `sync_script_exists`
- `openai_api_key_set`
- `metadata_coverage_nonzero`
- `pdf_headers_sample_quality`
- `neo4j_connectivity`

If a check fails, review the check details shown in the table and correct the corresponding file/config/runtime dependency.

## 6) CLI usage (optional)

Build graph:

```bash
python scripts/build_graph.py --mode batch --pdf-dir pdfs
python scripts/build_graph.py --mode all --pdf-dir pdfs
python scripts/build_graph.py --mode batch --pdf-dir pdfs --override-existing
```

Build Anystyle image (recommended for ingest quality):

```bash
docker compose build anystyle
```

Test ingest with shared pipeline in forced-Anystyle mode:

```bash
python scripts/build_graph_anystyle_test.py --mode batch --pdf-dir pdfs --partial-count 1
```

Train a Qwen3 LoRA adapter for reference extraction:

```bash
python scripts/train_qwen_reference_lora.py \
  --model-path 'C:\Users\rjbischo\ASU Dropbox\Robert Bischoff\RA\CatMapper\LLM' \
  --train-jsonl data/reference_lora_train.jsonl \
  --eval-jsonl data/reference_lora_eval.jsonl \
  --output-dir models/qwen3-reference-lora
```

Prepare staged curriculum datasets (synthetic/silver/gold, plus split-task examples):

```bash
python scripts/prepare_qwen_reference_curriculum.py \
  --silver-jsonl data/reference_lora_train.jsonl \
  --silver-jsonl data/reference_lora_eval.jsonl \
  --synthetic-jsonl data/reference_lora_pdf_samples.jsonl \
  --gold-articles-json data/reference_lora_gold_articles.json \
  --output-dir data/reference_lora_curriculum
```

Train stage 1 then stage 2 (stage 2 continues from stage 1 adapter):

```bash
python scripts/train_qwen_reference_lora.py \
  --model-path 'C:\Users\rjbischo\ASU Dropbox\Robert Bischoff\RA\CatMapper\LLM' \
  --train-jsonl data/reference_lora_curriculum/stage1_train.jsonl \
  --eval-jsonl data/reference_lora_curriculum/stage1_eval.jsonl \
  --output-dir models/qwen3-reference-lora-curriculum/stage1 \
  --load-in-4bit \
  --gradient-checkpointing

python scripts/train_qwen_reference_lora.py \
  --model-path 'C:\Users\rjbischo\ASU Dropbox\Robert Bischoff\RA\CatMapper\LLM' \
  --init-adapter-path models/qwen3-reference-lora-curriculum/stage1 \
  --train-jsonl data/reference_lora_curriculum/stage2_train.jsonl \
  --eval-jsonl data/reference_lora_curriculum/stage2_eval.jsonl \
  --output-dir models/qwen3-reference-lora-curriculum/stage2 \
  --load-in-4bit \
  --gradient-checkpointing
```

Submit full staged training on ASU SOL (build curriculum + train both stages):

```bash
ssh sol
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
  --pdf-dir pdfs \
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
  --pdf pdfs/file1.pdf --pdf pdfs/file2.pdf
```

Query:

```bash
python scripts/query_graph.py "fremont culture chronology" --limit 5
```
