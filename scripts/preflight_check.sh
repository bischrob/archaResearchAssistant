#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="${PYTHON_BIN:-$("${ROOT_DIR}/scripts/resolve_python.sh")}"

warn() { echo "[WARN] $*"; }
ok() { echo "[OK] $*"; }
fail() { echo "[FAIL] $*"; exit 1; }

PORT_TO_CHECK="${1:-${PORT:-8000}}"

get_env_value() {
  local key="$1"
  if [[ -f .env ]]; then
    grep -E "^${key}=" .env | tail -n1 | cut -d'=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' || true
  fi
}

check_path_exists() {
  local label="$1"
  local raw="$2"
  if [[ -z "${raw}" ]]; then
    return
  fi
  if [[ -e "${raw}" ]]; then
    ok "${label} exists: ${raw}"
  else
    warn "${label} is set but does not exist on this host: ${raw}"
  fi
}

check_dir_writable_if_exists() {
  local label="$1"
  local raw="$2"
  if [[ -z "${raw}" || ! -e "${raw}" ]]; then
    return
  fi
  if [[ -d "${raw}" && -w "${raw}" ]]; then
    ok "${label} is writable: ${raw}"
  elif [[ -d "${raw}" ]]; then
    warn "${label} exists but is not writable: ${raw}"
  fi
}

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing required command: $cmd"
  ok "Found command: $cmd"
}

require_python() {
  [[ -x "${PYTHON_BIN}" ]] || fail "Missing required Python interpreter: ${PYTHON_BIN}"
  ok "Using python: ${PYTHON_BIN}"
}

check_env_file() {
  if [[ ! -f .env ]]; then
    warn ".env not found. Copy .env.example to .env and set values."
    return 0
  fi
  ok "Found .env"

  local backend
  backend="$(grep -E '^METADATA_BACKEND=' .env | tail -n1 | cut -d'=' -f2- | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]' || true)"
  if [[ -z "${backend}" ]]; then
    warn "METADATA_BACKEND is not set in .env (expected 'zotero' or 'paperpile')."
    return 0
  fi

  if [[ "${backend}" == "zotero" ]]; then
    if ! grep -Eq '^ZOTERO_DB_PATH=.+' .env; then
      warn "METADATA_BACKEND=zotero but ZOTERO_DB_PATH is missing/empty."
    else
      ok "ZOTERO_DB_PATH appears set for zotero backend"
    fi
  elif [[ "${backend}" == "paperpile" ]]; then
    if ! grep -Eq '^PAPERPILE_JSON=.+' .env; then
      warn "METADATA_BACKEND=paperpile but PAPERPILE_JSON is missing/empty."
    else
      ok "PAPERPILE_JSON appears set for paperpile backend"
    fi
  else
    warn "METADATA_BACKEND='${backend}' is not recognized (expected zotero or paperpile)."
  fi
}

check_compose() {
  if docker compose version >/dev/null 2>&1; then
    ok "docker compose available"
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    ok "docker-compose available"
    return
  fi
  fail "Neither 'docker compose' nor 'docker-compose' is available"
}

check_docker_daemon() {
  docker info >/dev/null 2>&1 || fail "Docker daemon is not reachable. Start Docker and retry."
  ok "Docker daemon reachable"
}

check_port_8000() {
  "${PYTHON_BIN}" - "${PORT_TO_CHECK}" <<'PY'
import socket
import sys

port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind(("0.0.0.0", port))
except OSError:
    print(f"[WARN] Port {port} is in use. start.sh will auto-select the next open port.")
else:
    print(f"[OK] Port {port} is free")
finally:
    s.close()
PY
}

check_configured_paths() {
  local metadata_backend
  local zotero_db_path
  local zotero_storage_root
  local pdf_source_dir
  local paperpile_json

  metadata_backend="$(get_env_value "METADATA_BACKEND" | tr '[:upper:]' '[:lower:]')"
  zotero_db_path="$(get_env_value "ZOTERO_DB_PATH")"
  zotero_storage_root="$(get_env_value "ZOTERO_STORAGE_ROOT")"
  pdf_source_dir="$(get_env_value "PDF_SOURCE_DIR")"
  paperpile_json="$(get_env_value "PAPERPILE_JSON")"

  if [[ -n "${metadata_backend}" ]]; then
    ok "METADATA_BACKEND=${metadata_backend}"
  fi

  check_path_exists "ZOTERO_DB_PATH" "${zotero_db_path}"
  check_path_exists "ZOTERO_STORAGE_ROOT" "${zotero_storage_root}"
  check_path_exists "PDF_SOURCE_DIR" "${pdf_source_dir}"
  check_path_exists "PAPERPILE_JSON" "${paperpile_json}"
  check_dir_writable_if_exists "ZOTERO_STORAGE_ROOT" "${zotero_storage_root}"
}

check_neo4j_if_running() {
  if docker inspect -f '{{.State.Running}}' neo4j >/dev/null 2>&1; then
    if [[ "$(docker inspect -f '{{.State.Running}}' neo4j 2>/dev/null || true)" == "true" ]]; then
      "${PYTHON_BIN}" - <<'PY'
driver = None
try:
    from neo4j import GraphDatabase
    from src.rag.config import Settings

    s = Settings()
    driver = GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
    with driver.session() as sess:
        sess.run("RETURN 1 AS ok").single()
    print("[OK] Neo4j connectivity check succeeded")
except Exception as exc:
    print(f"[WARN] Neo4j container is running but connection check failed: {exc}")
finally:
    try:
        if driver is not None:
            driver.close()
    except Exception:
        pass
PY
      return
    fi
  fi
  warn "Neo4j container not running (this is fine before first start)."
}

main() {
  echo "Running preflight checks in ${ROOT_DIR}"
  require_python
  require_cmd docker
  check_compose
  check_docker_daemon
  check_env_file
  check_configured_paths
  check_port_8000
  check_neo4j_if_running
  echo "Preflight complete."
}

main "$@"
