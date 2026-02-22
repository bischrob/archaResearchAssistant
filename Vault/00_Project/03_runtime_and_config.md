# Runtime and Configuration

## Environment variables (effective)
Defined via `src/rag/config.py` and usage in `src/rag/llm_answer.py`/`webapp/main.py`:
- `NEO4J_URI` (default `bolt://localhost:7687`)
- `NEO4J_USER` (default `neo4j`)
- `NEO4J_PASSWORD` (configured via environment; value redacted)
- `EMBEDDING_MODEL` (currently ignored by implementation; hashing embedder is hardcoded)
- `PAPERPILE_JSON` (default `Paperpile.json`)
- `CHUNK_SIZE_WORDS` (default `220`)
- `CHUNK_OVERLAP_WORDS` (default `45`)
- `CITATION_MIN_QUALITY` (default `0.35`; filters low-quality references before graph write)
- `CHUNK_STRIP_PAGE_NOISE` (default enabled; strips repeated headers/footers/page numbers before chunking)
- `OPENAI_API_KEY` (required for `/api/ask`)
- `OPENAI_MODEL` (default `gpt-5.1`)

## Dotenv behavior
- `webapp/main.py` loads `.env` manually at import time.
- Aliases `OpenAPIKey` and `OPENAPIKEY` are mapped to `OPENAI_API_KEY`.
- Existing process env takes precedence; `.env` does not override set values.

## Service configuration
- Neo4j credentials and APOC plugin enabled in `docker-compose.yml`.
- `start.sh` optionally initializes schema (`INIT_NEO4J_SCHEMA=1` by default).

## Observed local `.env` keys
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

## Config caveats
- `EMBEDDING_MODEL` suggests model selection but `GraphStore` always uses deterministic `HashingEmbedder` (384 dims).
- Secrets are expected in env files; repository `.gitignore` excludes `.env` and `google.config`.

## Related notes
- [[10_Backend/01_settings_and_config_module]]
- [[10_Backend/05_graph_store_module]]
- [[40_Scripts/03_docker_services]]
