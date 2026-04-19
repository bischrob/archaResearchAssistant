# Model Setup

This project can run with OpenAI-backed answering alone. The active ingest parser no longer depends on local Qwen citation/refsplit runtime components.

## Recommended ingest parser

```bash
CITATION_PARSER=heuristic
```

That parser means:

- heuristics detect one or more reference sections
- repeated chapter-level bibliography blocks in edited volumes are supported
- split/continuation handling is deterministic and local by default
- low-confidence entries can be flagged for review without requiring an LLM

Other supported modes:

- `CITATION_PARSER=hybrid_llm`
  - deterministic parsing first, optional OpenAI repair for low-confidence entries only
- `CITATION_PARSER=llm`
  - strongest OpenAI-assisted repair path, still preserving the raw reference text for auditability

Optional LLM repair settings:

- `REFERENCE_PARSER_LLM_MODEL`
- `REFERENCE_PARSER_LLM_MAX_REFERENCES`
- `REFERENCE_PARSER_LLM_TIMEOUT_SECONDS`

If `OPENAI_API_KEY` is not set, the LLM-assisted parser modes fall back cleanly and record the reason in parse failures rather than hard-failing ingest.

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
