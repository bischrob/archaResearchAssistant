# Documentation Index

Start here based on your role.

## New user

- [New User Setup](NEW_USER_SETUP.md)
- [Model Setup](MODEL_SETUP.md)
- [Anystyle Setup](ANYSTYLE_SETUP.md)

## Operator

- [New User Setup](NEW_USER_SETUP.md)
- [Troubleshooting](TROUBLESHOOTING.md)

## Developer

- [README](../README.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- Text ingest now defaults to native PDF extraction first, with a conservative malformed-text gate before PaddleOCR fallback. OCR fallback provenance now carries engine/model/version (best effort), OCR timestamp, and a heuristic OCR quality summary into cache and Neo4j Article storage.

## Research user

- [Citation Lookup Guide](CITATION_LOOKUP.md)
- [New User Setup](NEW_USER_SETUP.md)

## Supported setup matrix

- OS: Linux and WSL are the primary supported environments in current docs
- Docker: required
- Neo4j: required
- Zotero backend: recommended default
- GPU: optional
- OpenAI API key: required for grounded LLM answer flows
- Local Qwen3 base model: optional unless using local Qwen-powered parsing or preprocessing
- Recommended Qwen base model for current usage: `Qwen/Qwen3-4B-Instruct-2507`
- LoRA adapter: recommended for local citation extraction workflows
