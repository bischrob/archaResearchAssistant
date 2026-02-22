# Backend Module: Settings and Config

## Source files
- `src/rag/config.py`
- `webapp/main.py` (`_load_dotenv`, `_openai_api_key_set`)

## Responsibility
Centralize runtime settings for DB, chunking, metadata path, and embedding identifier.

## Core behavior
- `Settings` dataclass pulls env vars at instantiation.
- Defaults are production-like and non-empty (including default Neo4j password).
- Web app also loads `.env` manually before app creation.

## Inputs
- Process environment
- `.env` in repository root

## Outputs
- `Settings` object used by ingest, query, and diagnostics paths.

## Failure modes
- Wrong `NEO4J_*` values cause connection failures across API endpoints.
- Missing `OPENAI_API_KEY` only impacts `/api/ask` and preprocess query rewrite.
- Invalid numeric env vars (`CHUNK_*`) will raise at parse time.

## Extension points
- Add new settings as dataclass fields in `config.py`.
- Surface new runtime checks in `/api/diagnostics`.

## Design caveat
`EMBEDDING_MODEL` is configurable but not honored by `GraphStore` implementation (hash embedder fixed).

## Related
- [[10_Backend/05_graph_store_module]]
- [[20_WebAPI/06_diagnostics_api]]
