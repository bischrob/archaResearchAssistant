# Backend Module: Ingest Pipeline

## Source file
- `src/rag/pipeline.py`

## Responsibility
Select PDFs, parse/cache article docs, and ingest into Neo4j through `GraphStore`.

## Main APIs
- `choose_pdfs(...)`.
- `ingest_pdfs(selected_pdfs, ...)`.

## Selection logic (`choose_pdfs`)
- Modes:
  - `batch`: first `partial_count` readable PDFs.
  - `all`: all PDFs.
  - `custom`: explicit list (with path cleanup and source-dir fallback).
  - `test3`: alias to `batch`.
- Filters (optional):
  - skip existing graph article IDs
  - require matching metadata

## Ingest logic (`ingest_pdfs`)
- Loads metadata index.
- Filters selected list by existing IDs and metadata again.
- Parses articles with cache key on:
  - absolute path, mtime, size
  - chunk size and overlap
  - chunk page-noise stripping toggle
  - metadata JSON
- Citation extraction path is now centralized in `ingest_pdfs`:
  - optional explicit `citation_overrides` win first
  - parser mode is selected by `CITATION_PARSER` (`anystyle`, `heuristic`, `qwen`)
  - Anystyle path falls back to built-in heuristic references on failure/empty output unless strict mode is enabled
  - Qwen path uses local model + optional LoRA adapter and falls back to built-in heuristic references on failure/empty output unless strict mode is enabled
  - caches Anystyle results under `.cache/anystyle_refs` keyed by file path + mtime + size
  - caches Qwen results under `.cache/qwen_refs` keyed by file path + mtime + size + model/adapter settings
- Filters article citations by quality threshold (`CITATION_MIN_QUALITY`).
- Uploads parsed articles with progress callbacks.
- Returns parser diagnostics in `IngestSummary` (`anystyle_*` and `qwen_*` counters, failure samples, optional disabled reason).
- Returns `IngestSummary` including skipped/failed files.

## Cancellation model
Caller can pass `should_cancel`; checked during parse and upload.

## Failure modes
- Empty final selection raises `ValueError` in several branches.
- If all parses fail, raises readable `ValueError` with failed file preview.
- DB connection failure in `_get_existing_article_ids` silently falls back to no-skip behavior.

## Extension points
- Add additional selection predicates (e.g., year ranges, author filters).
- Add retry strategy for transient parse failures.
- Add cache pruning command for stale `.cache/rag_articles` entries.

## Related
- [[20_WebAPI/04_ingest_api]]
- [[10_Backend/05_graph_store_module]]
