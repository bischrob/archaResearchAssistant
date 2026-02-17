#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: Docker is not installed or not in PATH." >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "Error: docker compose is not available." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker daemon is not running. Start Docker and retry." >&2
  exit 1
fi

NEO4J_RUNNING="$(docker inspect -f '{{.State.Running}}' neo4j 2>/dev/null || true)"
if [[ "${NEO4J_RUNNING}" != "true" ]]; then
  echo "Starting Neo4j container..."
  "${COMPOSE_CMD[@]}" up -d neo4j
else
  echo "Neo4j container already running."
fi

if [[ "${INIT_NEO4J_SCHEMA:-1}" == "1" ]]; then
  echo "Initializing Neo4j schema..."
  python "${ROOT_DIR}/scripts/init_neo4j_indexes.py" \
    --wait-seconds "${NEO4J_INIT_WAIT_SECONDS:-90}" \
    --retry-interval "${NEO4J_INIT_RETRY_INTERVAL:-2}"
fi

exec "${ROOT_DIR}/scripts/run_web_gui.sh"
