# Web API: Query and Ask Endpoints

## Source file
- `webapp/main.py` (`/api/query*`, `/api/ask*`)

## Query endpoints
- `POST /api/query`
- `GET /api/query/status`
- `POST /api/query/stop`

### Query behavior
- Validates non-empty query string.
- Runs `contextual_retrieve` with requested limit.
- Returns retrieved rows including scores and citation-neighborhood context.

## Ask endpoints
- `POST /api/ask`
- `POST /api/ask/export`

### Ask behavior
1. Validate non-empty question.
2. Optionally preprocess search query with LLM rewrite.
3. Retrieve RAG rows using rewritten or original query.
4. Call grounded answer function with optional citation enforcement.
5. Audit answer support and return report object.

### Ask export behavior
- markdown: plain markdown response.
- csv: used citation table.
- pdf: pandoc conversion of markdown report.

## Failure modes
- Missing OpenAI key or API errors -> HTTP 400 detail.
- Preprocess rewrite errors do not fail ask; they fallback to original query and capture error in metadata.
- Citation enforcement can intentionally replace answer when no valid `[C#]` references detected.

## Related
- [[10_Backend/06_retrieval_module]]
- [[10_Backend/07_llm_grounding_module]]
- [[10_Backend/08_answer_audit_export_module]]
