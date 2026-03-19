# Anystyle Setup

Anystyle is used during ingest to improve citation and reference parsing quality.

## What Anystyle does

With the recommended parser mode:

```bash
CITATION_PARSER=qwen_refsplit_anystyle
```

the pipeline:

1. uses Qwen-aware logic to detect structure and reference boundaries
2. splits reference sections into individual candidate citations
3. passes those candidate citations to Anystyle for structured parsing

## Build and run

```bash
docker compose build anystyle
docker compose up -d anystyle
```

## Recommended environment settings

```bash
CITATION_PARSER=qwen_refsplit_anystyle
ANYSTYLE_SERVICE=anystyle
ANYSTYLE_TIMEOUT_SECONDS=240
ANYSTYLE_REQUIRE_SUCCESS=0
```

Optional GPU settings:

```bash
ANYSTYLE_USE_GPU=1
ANYSTYLE_GPU_SERVICE=anystyle-gpu
ANYSTYLE_GPU_DEVICES=all
```

## Failure and fallback behavior

- If `ANYSTYLE_REQUIRE_SUCCESS=0`, ingest continues when Anystyle fails or returns no usable output.
- If `ANYSTYLE_REQUIRE_SUCCESS=1`, ingest fails when Anystyle fails.
- This is useful if you want strict parsing guarantees during evaluation runs.
