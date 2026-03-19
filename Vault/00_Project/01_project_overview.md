# Project Overview

## One-line description
Neo4j-backed PDF research assistant with ingest, hybrid retrieval, and grounded LLM answering via a FastAPI web UI.

## Primary capabilities
- Refresh local PDF coverage from configured source directories (filesystem, ZIP-backed, or Zotero DB attachment paths).
- Parse PDFs into chunked text + extracted references.
- Store graph entities in Neo4j (`Article`, `Author`, `Chunk`, `Token`, `Reference`, `CITES`).
- Hybrid retrieval (vector + token + author + title channels).
- Grounded answer generation using OpenAI with inline citation IDs (`[C#]`).
- Export answer reports (Markdown, CSV, PDF via pandoc).
- Exact citation lookup by citekey (`/api/article/{citekey}` and `/api/articles/by-citekeys`).

## Runtime shape
- FastAPI app in `webapp/main.py`.
- Long-running operations managed by in-process thread-based `JobManager`.
- Neo4j used as the only online datastore.
- Heavy local data footprint from PDFs and caches.

## Core workflows
1. Discover/validate local source PDFs (`source_mode=filesystem|zotero_db`).
2. Select PDFs based on mode + metadata + existing graph state.
3. Parse and chunk PDFs, then ingest into Neo4j.
4. Retrieve context for a query.
5. Optionally ask OpenAI for grounded answer using retrieved chunks.
6. For known papers, use citekey-first lookup to fetch citation metadata directly.

## Important constraints
- Ingest defaults to strict metadata matching (`METADATA_REQUIRE_MATCH=1`), typically via Zotero metadata backend.
- LLM answering requires `OPENAI_API_KEY`.
- `all` ingest mode is batched in API layer (batch size is `partial_count`).
- Pipeline is non-destructive (no automatic graph wipe).
- Query endpoint defaults to paper-scope retrieval with configurable per-paper chunk count.

## Related notes
- [[00_Project/05_startup_runbook]]
- [[00_Project/12_llm_agent_playbook]]
- [[10_Backend/04_ingest_pipeline_module]]
- [[20_WebAPI/01_api_surface]]
