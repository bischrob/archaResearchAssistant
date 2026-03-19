# Troubleshooting

## Zotero DB path missing

Set:

- `ZOTERO_DB_PATH=/path/to/zotero.sqlite`

## Zotero storage path missing

Set:

- `ZOTERO_STORAGE_ROOT=/path/to/Zotero/storage`

## Anystyle not running

Start it with:

```bash
docker compose up -d anystyle
```

## Qwen model or LoRA not found

Set:

- `QWEN3_MODEL_PATH`
- `QWEN3_CITATION_ADAPTER_PATH`

See:

- [Model Setup](MODEL_SETUP.md)

## API bearer token mismatch

- If `API_BEARER_TOKEN` is set in `.env`, enter the same token in the web UI System panel.
- If auth is not needed, leave both unset.

## Docker or Neo4j not reachable

Run:

```bash
make preflight
docker compose up -d neo4j
```

Then refresh health in the UI.
