# Web API: Query and Ask Endpoints

## Source file
- `webapp/main.py` (`/api/query*`, `/api/ask*`)

## Query endpoints
- `POST /api/query`
- `GET /api/query/status`
- `POST /api/query/stop`

Known-paper lookup mode:
- Set `limit_scope="papers"` and `chunks_per_paper=1` when users are trying to find a specific citation record quickly.
- If citekey is known, prefer `GET /api/article/{citekey}` instead of `/api/query`.

### Query behavior
- Validates non-empty query string.
- Supports query controls:
  - `limit` (default 20)
  - `limit_scope` (`papers` default, or `chunks`)
  - `chunks_per_paper` (used in paper scope)
- Runs `contextual_retrieve` with requested scope.
- Returns retrieved rows including scores and citation-neighborhood context.
  - In paper scope, rows include `paper_score` and `highlight_chunks`.

## Ask endpoints
- `POST /api/ask`
- `POST /api/ask/export`

### Ask behavior
1. Validate non-empty question.
2. Optionally preprocess search query with LLM rewrite.
   - backend is controlled by `QUERY_PREPROCESS_BACKEND` (`openai` or local `qwen`).
3. Retrieve RAG rows using rewritten or original query (chunk scope for grounding context).
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
