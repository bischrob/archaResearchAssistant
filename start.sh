#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

port_is_free() {
  local port="$1"
  python - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind(("0.0.0.0", port))
except OSError:
    sys.exit(1)
finally:
    s.close()
sys.exit(0)
PY
}

pick_open_port() {
  local start_port="$1"
  local port="${start_port}"
  while (( port <= 65535 )); do
    if port_is_free "${port}"; then
      echo "${port}"
      return 0
    fi
    ((port++))
  done
  return 1
}

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

REQUESTED_PORT="${PORT:-8000}"
if ! [[ "${REQUESTED_PORT}" =~ ^[0-9]+$ ]] || (( REQUESTED_PORT < 1 || REQUESTED_PORT > 65535 )); then
  echo "Error: PORT must be an integer between 1 and 65535 (received '${REQUESTED_PORT}')." >&2
  exit 1
fi

SELECTED_PORT="$(pick_open_port "${REQUESTED_PORT}")"
if [[ -z "${SELECTED_PORT}" ]]; then
  echo "Error: Could not find an open port between ${REQUESTED_PORT} and 65535." >&2
  exit 1
fi

if [[ "${SELECTED_PORT}" != "${REQUESTED_PORT}" ]]; then
  echo "Port ${REQUESTED_PORT} is in use. Using open port ${SELECTED_PORT}."
else
  echo "Using port ${SELECTED_PORT}."
fi

echo "Web GUI URL: http://localhost:${SELECTED_PORT}"
export PORT="${SELECTED_PORT}"

exec "${ROOT_DIR}/scripts/run_web_gui.sh"
