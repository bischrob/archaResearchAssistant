#!/usr/bin/env bash
set -euo pipefail

NEO4J_RESTART_NEEDED=0

restart_neo4j() {
  if [[ "${NEO4J_RESTART_NEEDED}" == "1" ]]; then
    if docker compose start neo4j; then
      echo "[INFO] Neo4j restarted after backup path."
    else
      echo "[ERROR] Failed to restart Neo4j after backup path failure; start it manually with: docker compose start neo4j" >&2
    fi
  fi
}
trap restart_neo4j EXIT

docker compose stop neo4j
NEO4J_RESTART_NEEDED=1

docker compose run --rm neo4j-admin neo4j-admin database dump neo4j --to-path=/var/lib/neo4j/import

# To restore (optional)
# docker compose run --rm neo4j-admin neo4j-admin database load neo4j --from-path=/var/lib/neo4j/import --force

docker compose start neo4j
NEO4J_RESTART_NEEDED=0
