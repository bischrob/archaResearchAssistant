# Model Setup

This project can run with OpenAI-backed answering alone. The active ingest parser no longer depends on local Qwen citation/refsplit runtime components.

## What you need for the recommended ingest path

- `OPENCLAW_AGENT_COMMAND` so the OpenClaw agent can repair ambiguous reference blocks into one-reference-per-line text
- Docker + Anystyle for structured citation parsing

## Recommended ingest parser

```bash
CITATION_PARSER=openclaw_refsplit_anystyle
```

That parser means:

- heuristics find headings and probable reference sections
- OpenClaw resolves ambiguous or merged reference blocks
- Anystyle parses the resulting one-line references into structured citation fields

## Legacy local Qwen assets

These variables may still exist for research, evaluation, or training scripts under `scripts/`, but they are not the recommended production ingest path:

- `QWEN3_MODEL_PATH`
- `QWEN3_CITATION_ADAPTER_PATH`
- `QWEN3_QUERY_ADAPTER_PATH`

If you keep using local Qwen experiments, treat them as offline research tooling rather than the default ingest architecture.

## Embeddings

The ingest/search stack requires **real sentence-transformer embeddings**.

Recommended default:

- `EMBEDDING_PROVIDER=sentence_transformers`
- `EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2`

Hash-placeholder embeddings are intentionally disabled so environment problems fail loudly instead of silently degrading retrieval quality.
