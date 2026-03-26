# Anystyle Setup

Anystyle is used during ingest to turn one-reference-per-line text into structured citation fields.

## What the recommended parser does

With the recommended parser mode:

```bash
CITATION_PARSER=openclaw_refsplit_anystyle
```

the active ingest path:

1. uses heuristics to detect section boundaries and reference blocks
2. writes or reconstructs one reference per line for each references block
3. uses the OpenClaw agent only when heuristics are ambiguous or clearly merged
4. passes the repaired one-line references to Anystyle for structured parsing

Qwen-backed reference splitting is no longer the recommended runtime path.

## Build and run

```bash
docker compose build anystyle
docker compose up -d anystyle
```

## Recommended environment settings

```bash
CITATION_PARSER=openclaw_refsplit_anystyle
OPENCLAW_AGENT_COMMAND=/path/to/openclaw-adapter
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
- If the OpenClaw agent is not configured, the pipeline keeps the heuristic split instead of blocking ingest.
- The `.references.txt` sidecar is the canonical one-reference-per-line artifact used to feed Anystyle.
