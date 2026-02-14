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

## 3) Run the web GUI

```bash
scripts/run_web_gui.sh
```

Open:

- `http://localhost:8000`

The GUI includes in-app instructions and buttons for:

- health/stats
- sync PDFs
- ingest modes:
  - `test3` (partial ingest; first N via `partial_count`, default 3)
  - `all` (all PDFs in `pdfs/`)
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
- in `test3` mode, selection order is: readable PDFs -> skip existing (unless override) -> metadata filter -> first N.
- ingest metadata is pulled from `Paperpile.json` by matching attachment filename to the local PDF basename.
- PDFs without matching `Paperpile.json` metadata are skipped automatically.
- LLM answers are citation-grounded and include `[C#]` references mapped to source chunks.
- LLM answers are rendered as Markdown in the UI.
- Retrieval is two-pass: broader candidate recall (vector + token + author channels) followed by stricter reranking on chunk/title/author/year/phrase and citation-neighborhood signals.
- Ask flow defaults to pre-LLM query rewrite; responses include the exact `search_query_used` for transparency.

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

## 4) CLI usage (optional)

Build graph:

```bash
python scripts/build_graph.py --mode test3 --pdf-dir pdfs
python scripts/build_graph.py --mode all --pdf-dir pdfs
python scripts/build_graph.py --mode test3 --pdf-dir pdfs --override-existing
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
