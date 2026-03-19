# archaResearch Asssistant

archaResearch Asssistant is a Neo4j-backed PDF ingest and retrieval system with a web UI, Zotero-aware sync, citation parsing, and grounded search workflows.

## Start Here

- New user setup: [docs/NEW_USER_SETUP.md](docs/NEW_USER_SETUP.md)
- Documentation hub: [docs/INDEX.md](docs/INDEX.md)
- Model setup: [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md)
- Anystyle setup: [docs/ANYSTYLE_SETUP.md](docs/ANYSTYLE_SETUP.md)
- Citation-first lookup: [docs/CITATION_LOOKUP.md](docs/CITATION_LOOKUP.md)
- Troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## Included vs Excluded

Included in GitHub:

- application source
- tests
- scripts
- Zotero plugin scaffold
- public documentation

Excluded from GitHub:

- PDFs
- Neo4j runtime data
- local models
- logs
- `.env`
- local Vault notes
- Zotero debug logs

## LoRA Release Asset

Recommended citation-extraction LoRA:

- https://github.com/bischrob/archaResearchAssistant/releases/tag/lora-20260319-104710

## Recommended Qwen3 Base Model

Current code and training scripts in this repository are aligned to:

- `Qwen/Qwen3-4B-Instruct-2507`

Recommended source:

- https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507

## Supported Setup Matrix

- OS: Linux and WSL are the primary documented environments
- Docker: required
- Neo4j: required
- Zotero backend: recommended default
- GPU: optional
- OpenAI API key: required for grounded LLM answer flows
- Local Qwen3 base model: optional unless using local Qwen-powered parsing or preprocessing

## Quickstart

```bash
cp .env.example .env
make preflight
make start
make smoke
```

For full setup, including Zotero, LoRA, and Anystyle:

- [docs/NEW_USER_SETUP.md](docs/NEW_USER_SETUP.md)

## Core Workflow

1. Configure `.env` with your OpenAI key and Zotero paths.
2. Start the stack with `make start`.
3. Open the web UI and use `Sync + Ingest`.
4. Use `Search` for paper or chunk retrieval.

## Plugin

The Zotero plugin scaffold lives in:

- `plugins/zotero-rag-sync/`

It can trigger the combined backend sync and ingest workflow and supports bearer-token auth when enabled.

## Testing

```bash
make test-unit
make test-e2e
make smoke
```

## Local Conveniences

- Auto-versioning can be enabled locally with:

```bash
git config core.hooksPath .githooks
```

- Optional daily Dropbox sync helper:

```bash
scripts/rclone_sync_dropbox.sh
```
