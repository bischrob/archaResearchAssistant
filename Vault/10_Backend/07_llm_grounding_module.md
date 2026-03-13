# Backend Module: LLM Grounding

## Source file
- `src/rag/llm_answer.py`

## Responsibility
Build citation-tagged context, call OpenAI chat completions, and enforce citation-grounded answers.

## Main APIs
- `ask_openai_grounded(question, rows, model, enforce_citations)`
- `preprocess_search_query(question, model)`

## Grounded answer flow
1. Build context blocks with stable IDs `[C1]...[Cn]` from retrieved chunks.
2. Send strict system prompt requiring only provided context usage.
3. Parse response text and extract inline citation IDs.
4. Return used citations and all provided citations.
5. If enforcement enabled and no citations found, replace answer with failure message.

## Query preprocess flow
- Calls configured backend (`QUERY_PREPROCESS_BACKEND=openai|qwen`) to rewrite question into a structured directive line.
- Extracts `authors|years|title_terms|content_terms` fields.
- Cleans boolean symbols/operators and composes a compact search query string.
- Falls back to sanitized raw response or original question.

## Failure modes
- Missing `OPENAI_API_KEY` raises runtime error.
- API errors bubble as runtime errors with partial response body.
- Model output format drift can degrade rewrite quality.
- Missing/invalid Qwen model or adapter path raises runtime error when Qwen preprocess is enabled.

## Extension points
- Move to OpenAI SDK and structured outputs for stronger parsing guarantees.
- Add token/cost logging and retry policy.
- Add multilingual query rewrite support.

## Related
- [[20_WebAPI/05_query_and_ask_api]]
- [[10_Backend/08_answer_audit_export_module]]
