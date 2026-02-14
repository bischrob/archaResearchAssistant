# Research Assistant RAG (Neo4j + Web GUI)

This project provides:

- PDF sync from Google Drive (`rclone`)
- Ingestion into Neo4j (`Article`, `Author`, `Chunk`, `Token`, `Reference`, `CITES`)
- Contextual retrieval (token + vector signal + citation neighborhood)
- A web GUI for sync, ingest, and search

## 1) Start Neo4j

```bash
docker compose up -d neo4j
```

Default DB env values:

- `NEO4J_URI=bolt://localhost:7687`
- `NEO4J_USER=neo4j`
- `NEO4J_PASSWORD=archaResearchAssistant`

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
  - `test3` (first 3)
  - `all` (all PDFs in `pdfs/`)
  - `custom` (specific files)
- contextual query
- stop/cancel for sync, ingest, and query jobs

Notes:

- `all` mode can take time on large libraries.
- unreadable/non-PDF-content files are skipped and returned in `failed_pdfs`.
- ingest is non-destructive and does not erase existing Neo4j data.
- default ingest behavior skips already-ingested PDFs; use override existing to reprocess.

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
