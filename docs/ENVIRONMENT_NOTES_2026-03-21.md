# Environment notes — 2026-03-21

## Summary

The `researchAssistant` repo currently supports **true sentence-transformer embeddings** in code, but the active/default conda environments on this machine were not set up to use that path successfully.

## What I checked

### Existing conda environments in WSL

Detected:

- `base` → `/home/rjbischo/miniconda3`
- `textsearch` → `/home/rjbischo/miniconda3/envs/textsearch`

### Repo environment declarations

The repo contains:

- `.env`
- `requirements.txt`

The repo does **not** currently contain a clear conda environment spec such as:

- `environment.yml`
- `environment.yaml`

It also does not contain an obvious checked-in `.venv`/`venv` or `pyproject.toml`.

## Embedding code path status

In `src/rag/neo4j_store.py`, `GraphStore._build_embedder()` now supports:

- `HashingEmbedder` fallback
- `SentenceTransformerEmbedder` using `sentence-transformers/all-MiniLM-L6-v2` by default

Relevant env vars:

- `EMBEDDING_PROVIDER`
- `EMBEDDING_MODEL`
- `EMBEDDING_DEVICE`
- `EMBEDDING_BATCH_SIZE`
- `EMBEDDING_NORMALIZE`

This means the current codebase is **not** limited to fake/hash embeddings only.

## What failed in the current envs

### `textsearch`

`textsearch` is not a viable runtime env for this repo right now. Import probe showed it was missing even core packages like:

- `numpy`
- `torch`
- `transformers`
- `sentence_transformers`

### `base`

`base` had:

- `torch` ✅
- `transformers` ✅
- `numpy` ✅

But it was missing:

- `sentence_transformers` ❌

So the repo's real embedding path cannot work in `base` as-is.

## Fresh environment creation attempts

### Attempt 1: `researchassistant` with Python 3.12

Created env:

- `researchassistant`

Result: **requirements install failed**.

Two concrete packaging issues surfaced:

1. `nipype==1.10.0` does not support Python 3.12 (`Requires-Python <3.12`)
2. `torch==2.6.0+cu124` is not available from the default pip index, so plain `pip install -r requirements.txt` fails unless the PyTorch wheel index is supplied

### Attempt 2: `researchassistant311` with Python 3.11

Created env:

- `researchassistant311`

This is the correct direction because Python 3.11 is compatible with the `nipype` pin. Installation was started using the PyTorch CUDA 12.4 wheel index so the `torch==2.6.0+cu124` requirement can resolve.

## Main conclusion

The immediate reason "true embeddings" were not working was **not** that the repo lacks support. The current code *does* support sentence-transformer embeddings.

The actual blockers were environment/setup problems:

1. no repo-declared conda environment file
2. `base` missing `sentence_transformers`
3. `textsearch` not provisioned for this repo
4. `requirements.txt` did not install cleanly in a fresh generic env without:
   - Python 3.11 instead of 3.12
   - PyTorch extra index configuration for `torch==2.6.0+cu124`
5. the pinned versions contained an internal resolver conflict:
   - `fastapi==0.115.8`
   - `starlette==0.46.1`

## Follow-up changes implemented

After this diagnosis, the repo was updated to:

- add `environment.yml` targeting Python 3.11
- add the PyTorch CUDA 12.4 wheel index to `requirements.txt`
- change `starlette` pin to `0.45.3` to match the `fastapi` constraint
- remove erroneous `fitz==0.0.1.dev2` dependency so `PyMuPDF` provides the `fitz` import cleanly
- remove the hash-embedding fallback from `GraphStore`
- make embedding misconfiguration fail hard
- update docs and backend Vault notes to reflect the real embedding behavior

## Recommendations

1. Add a real `environment.yml` for the repo
2. Standardize on a named env (for example `researchassistant311`)
3. Document that the repo currently expects Python 3.11
4. Document the PyTorch wheel index requirement explicitly
5. Update/remove stale internal notes in `Vault/` that still describe the graph store as hash-only

## Suggested next repo changes

- add `environment.yml`
- add a short "known-good env" section to `README.md` or `docs/NEW_USER_SETUP.md`
- consider splitting GPU-specific pins from core requirements
- consider providing a CPU-safe requirements variant for easier setup/testing
 or `docs/NEW_USER_SETUP.md`
- consider splitting GPU-specific pins from core requirements
- consider providing a CPU-safe requirements variant for easier setup/testing
