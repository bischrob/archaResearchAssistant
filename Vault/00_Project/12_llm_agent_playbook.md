# LLM Agent Playbook

Last reviewed: 2026-03-19

## Purpose
Give LLM agents a deterministic path to operate this codebase without guessing.

## Source-of-Truth Order
When docs and code conflict, trust in this order:
1. `webapp/main.py` (API contracts and behavior)
2. `src/rag/config.py` (effective runtime defaults/env keys)
3. `src/rag/*` modules (pipeline/retrieval behavior)
4. `README.md`
5. Vault notes

## First 5 Files To Read
1. `README.md`
2. `Vault/Index.md`
3. `webapp/main.py`
4. `src/rag/config.py`
5. `Vault/20_WebAPI/08_api_reference.md`

## Task Recipes

### Known paper lookup (citation-first)
1. Try exact citekey:
   - `GET /api/article/{citekey}`
2. If multiple citekeys:
   - `POST /api/articles/by-citekeys`
3. If citekey unknown:
   - `POST /api/query` with `limit_scope="papers"` and `chunks_per_paper=1`

### Verify ingest/sync state quickly
1. `GET /api/sync/status`
2. `GET /api/ingest/status`
3. If needed, inspect `result`/`error` fields from the job status payload.

### Validate service availability
1. `GET /`
2. `GET /api/sync/status`
3. `GET /api/ingest/status`
4. Treat `/api/health` as secondary if startup is under heavy load.

## Common LLM Failure Modes
- Using semantic query for exact known citation when citekey lookup exists.
- Treating legacy Paperpile docs as current default behavior.
- Assuming `start.sh` always completes quickly even when Docker CLI is slow/hung.
- Assuming docs are current without checking `Last reviewed` date.

## Documentation Hygiene Rules
- Add `Last reviewed: YYYY-MM-DD` to operational notes.
- Add explicit “Source of truth” file references.
- Prefer task-oriented sections (`If user wants X, call Y`) over conceptual prose.
- Every new Vault note must be linked in `Vault/Index.md`.

## Related
- [[20_WebAPI/08_api_reference]]
- [[20_WebAPI/09_citation_lookup_quickstart]]
- [[00_Project/03_runtime_and_config]]
