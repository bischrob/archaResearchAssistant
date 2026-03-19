# Runtime and Configuration

Last reviewed: 2026-03-19
Source of truth: `src/rag/config.py`, `webapp/main.py`, `docker-compose.yml`

## Core Environment Variables
Graph and source:
- `NEO4J_URI` (default `bolt://localhost:7687`)
- `NEO4J_USER` (default `neo4j`)
- `NEO4J_PASSWORD` (default `archaResearchAssistant`)
- `PDF_SOURCE_DIR` (falls back to `NEXTCLOUD_PDF_ROOT`, then UNC default)
- `METADATA_BACKEND` (`zotero` default; `paperpile` legacy)
- `METADATA_REQUIRE_MATCH` (`1` default strict mode)
- `ZOTERO_DB_PATH` / `ZOTERO_LOCAL_DB_PATH` (optional alias)
- `ZOTERO_STORAGE_ROOT` / `ZOTERO_STORAGE_DIR` (optional alias)
- `PAPERPILE_JSON` (legacy fallback metadata file)

Ingest and citation parsing:
- `CHUNK_SIZE_WORDS` (default `220`)
- `CHUNK_OVERLAP_WORDS` (default `45`)
- `CITATION_MIN_QUALITY` (default `0.35`)
- `CHUNK_STRIP_PAGE_NOISE` (default enabled)
- `CITATION_PARSER` (default `qwen_refsplit_anystyle`)
- `ANYSTYLE_SERVICE` (default `anystyle`)
- `ANYSTYLE_GPU_SERVICE` (default `anystyle-gpu`)
- `ANYSTYLE_TIMEOUT_SECONDS` (default `240`)
- `ANYSTYLE_REQUIRE_SUCCESS` (default disabled)
- `ANYSTYLE_USE_GPU` (default disabled)
- `ANYSTYLE_GPU_DEVICES` (default `all`)

Qwen local models:
- `QWEN3_MODEL_PATH`
- `QWEN3_QUERY_MODEL_PATH`
- `QWEN3_QUERY_ADAPTER_PATH`
- `QWEN3_QUERY_MAX_NEW_TOKENS` (default `96`)
- `QWEN3_CITATION_MODEL_PATH`
- `QWEN3_CITATION_ADAPTER_PATH` (defaults to latest local adapter when unset)
- `QWEN3_CITATION_MAX_NEW_TOKENS` (default `768`)
- `QWEN3_CITATION_BATCH_SIZE` (default `24`)
- `QWEN3_DEVICE` (default `auto`)
- `QWEN3_DTYPE` (default `auto`)
- `QWEN3_MAX_INPUT_CHARS` (default `12000`)
- `QWEN3_REFERENCE_SPLIT_WINDOW_CHARS` (default `2600`)
- `QWEN3_REQUIRE_SUCCESS` (default disabled)

OCR and ZIP source handling:
- `PADDLEOCR_TEXT_DIR` (default `ocr/paddleocr/text`)
- `PADDLEOCR_TEXT_FALLBACK_DIR` (default `data/ocr/paddleocr/text`)
- `PADDLEOCR_PREFER_TEXT` (default enabled)
- `PADDLEOCR_AUTO_GENERATE_MISSING_TEXT` (default enabled)
- `PADDLEOCR_AUTO_LANG` (default `en`)
- `PADDLEOCR_AUTO_DEVICE` (default `cpu`)
- `PADDLEOCR_AUTO_RENDER_DPI` (default `180`)
- `ZIP_PDF_ENABLE` (default enabled)
- `ZIP_PDF_CACHE_DIR` (default `.cache/zotero_zip_pdf_cache`)

LLM and API:
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default `gpt-5.1`)
- `QUERY_PREPROCESS_BACKEND` (`openai` default; optional `qwen`)
- `API_BEARER_TOKEN` (optional; gates sync/ingest/query endpoints when set)

## Dotenv Behavior
- `.env` is loaded manually by `webapp/main.py` at import time.
- Aliases `OpenAPIKey` and `OPENAPIKEY` are mapped to `OPENAI_API_KEY`.
- Existing process environment values are not overridden by `.env`.

## Service Defaults
- `start.sh` starts Neo4j if needed and initializes schema unless `INIT_NEO4J_SCHEMA=0`.
- `scripts/run_web_gui.sh` runs uvicorn without reload by default (`UVICORN_RELOAD=0`).
- Docker compose defines `neo4j`, `neo4j-admin`, `anystyle`, and `anystyle-gpu`.

## LLM-Agent Notes
- For exact known-paper retrieval, prefer citekey endpoints over semantic query:
  - `GET /api/article/{citekey}`
  - `POST /api/articles/by-citekeys`
- If citekey is unknown, use paper-scope query:
  - `POST /api/query` with `limit_scope="papers"` and `chunks_per_paper=1`

## Related notes
- [[00_Project/12_llm_agent_playbook]]
- [[10_Backend/01_settings_and_config_module]]
- [[10_Backend/05_graph_store_module]]
- [[20_WebAPI/08_api_reference]]
