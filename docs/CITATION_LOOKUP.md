# Citation Lookup Guide

Use this when you already know roughly which paper you want.

## Fastest lookup paths

If you know the citekey:

```bash
curl "http://127.0.0.1:8000/api/article/<citekey>?chunk_limit=1"
```

If you know several citekeys:

```bash
curl -X POST "http://127.0.0.1:8000/api/articles/by-citekeys" \
  -H "Content-Type: application/json" \
  -d '{"citekeys":["smith2024copyright","doe2023genai"],"chunk_limit":1}'
```

If you know title, author, or year but not citekey:

```bash
curl -X POST "http://127.0.0.1:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query":"\"Copyright and Artificial Intelligence\" 2024 Guadamuz",
    "limit":10,
    "limit_scope":"papers",
    "chunks_per_paper":1
  }'
```

## Recommended search settings

- `limit_scope=papers`
- `chunks_per_paper=1`
- keep result count low for citation-first lookup

## What to expect

Results should include, when present:

- citekey
- title
- year
- DOI
- authors
