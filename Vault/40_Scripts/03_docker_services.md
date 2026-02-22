# Docker and Services

## Source files
- `docker-compose.yml`
- `pdf2epub/docker-compose.yml`
- `anystyle/Dockerfile`

## Primary compose services (`docker-compose.yml`)
- `neo4j`: main graph DB with APOC and host-mounted volumes.
- `neo4j-admin`: utility container for admin commands.
- `anystyle`: Ruby container for Anystyle CLI workflows, now used by default ingest citation parsing (`CITATION_PARSER=anystyle`).

## Neo4j service details
- Image: `neo4j:2025.02.0-community`.
- Auth configured via `NEO4J_AUTH` (credential value redacted).
- Ports: `7474`, `7687`.
- Volume mounts into `db/` directory.

## PDF2EPUB compose
- Separate `marker` service mapping local Windows-style paths.
- GPU-oriented config (`TORCH_DEVICE=cuda`, NVIDIA capabilities).

## Build caveat
- `anystyle/Dockerfile` was corrected to remove the trailing-space backslash issue in the apt package line.
- Build command for local verification: `docker compose build anystyle`.

## Operational caveats
- Host permissions for mounted `db/*` directories can block local inspection.
- Compose files are environment-specific; `pdf2epub` paths are machine-specific.

## Related
- [[00_Project/04_data_and_storage]]
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
