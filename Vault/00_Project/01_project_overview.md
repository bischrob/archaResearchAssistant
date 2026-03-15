# Project Overview

## One-line description
Neo4j-backed PDF research assistant with ingest, hybrid retrieval, and grounded LLM answering via a FastAPI web UI.

## Primary capabilities
- Sync PDFs from Google Drive (`rclone` wrapper).
- Parse PDFs into chunked text + extracted references.
- Store graph entities in Neo4j (`Article`, `Author`, `Chunk`, `Token`, `Reference`, `CITES`).
- Hybrid retrieval (vector + token + author + title channels).
- Grounded answer generation using OpenAI with inline citation IDs (`[C#]`).
- Export answer reports (Markdown, CSV, PDF via pandoc).

## Runtime shape
- FastAPI app in `webapp/main.py`.
- Long-running operations managed by in-process thread-based `JobManager`.
- Neo4j used as the only online datastore.
- Heavy local data footprint from PDFs and caches.

## Core workflows
1. Sync remote PDFs into `\\192.168.0.37\pooled\media\Books\pdfs`.
2. Select PDFs based on mode + metadata + existing graph state.
3. Parse and chunk PDFs, then ingest into Neo4j.
4. Retrieve context for a query.
5. Optionally ask OpenAI for grounded answer using retrieved chunks.

## Important constraints
- Ingest requires metadata match in `Paperpile.json` by default.
- LLM answering requires `OPENAI_API_KEY`.
- `all` ingest mode is batched in API layer (batch size is `partial_count`).
- Pipeline is non-destructive (no automatic graph wipe).

## Related notes
- [[00_Project/05_startup_runbook]]
- [[10_Backend/04_ingest_pipeline_module]]
- [[20_WebAPI/01_api_surface]]
