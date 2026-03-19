# Citation Lookup Quickstart

Last reviewed: 2026-03-19
Source of truth: `webapp/main.py`, `src/rag/retrieval.py`

## Goal
Find a known paper quickly in the graph with minimal noise.

## Fastest Path (Known Citekey)
Use exact citekey lookup:

```bash
curl "http://127.0.0.1:8000/api/article/<citekey>?chunk_limit=1"
```

Why:
- deterministic single-record lookup
- no semantic ranking ambiguity

## Batch Path (Multiple Known Citekeys)
```bash
curl -X POST "http://127.0.0.1:8000/api/articles/by-citekeys" \
  -H "Content-Type: application/json" \
  -d '{"citekeys":["smith2024copyright","doe2023genai"],"chunk_limit":1}'
```

Use `missing_citekeys` in the response to identify not-yet-ingested or mismatched records.

## Fallback Path (Citekey Unknown)
Use paper-scope retrieval:

```bash
curl -X POST "http://127.0.0.1:8000/api/query" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -d '{
    "query":"\"Copyright and Artificial Intelligence\" 2024 Guadamuz",
    "limit":10,
    "limit_scope":"papers",
    "chunks_per_paper":1
  }'
```

Interpretation:
- `limit`: number of papers returned
- `chunks_per_paper`: number of support chunks per paper (set to `1` for citation-first lookup)

## Fields To Trust For Citation Identity
- `article_citekey`
- `article_title`
- `article_year`
- `article_doi`
- `authors`

## If Not Found
1. Check ingest preview includes the file (`POST /api/ingest/preview`).
2. Confirm metadata match exists (`metadata_found=true`).
3. Re-run targeted ingest for that PDF (`POST /api/ingest` with `mode=custom`).
4. Re-check with `/api/article/{citekey}`.

## Related
- [[20_WebAPI/08_api_reference]]
- [[20_WebAPI/05_query_and_ask_api]]
- [[10_Backend/06_retrieval_module]]
