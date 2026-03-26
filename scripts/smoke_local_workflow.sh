#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-30}"
POLL_INTERVAL="${POLL_INTERVAL:-1}"
RUN_DIAGNOSTICS="${RUN_DIAGNOSTICS:-1}"
API_BEARER_TOKEN_SMOKE="${API_BEARER_TOKEN_SMOKE:-${API_BEARER_TOKEN:-}}"

usage() {
  cat <<USAGE
Usage: scripts/smoke_local_workflow.sh [--base-url URL] [--timeout seconds] [--skip-diagnostics]

Checks:
  1) GET /api/health
  2) POST /api/query and poll /api/query/status to terminal state
  3) Optional GET /api/diagnostics
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url) BASE_URL="$2"; shift 2 ;;
    --timeout) TIMEOUT_SECONDS="$2"; shift 2 ;;
    --skip-diagnostics) RUN_DIAGNOSTICS=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 2 ;;
  esac
done

hdr=(-H "Content-Type: application/json")
if [[ -n "${API_BEARER_TOKEN_SMOKE}" ]]; then
  hdr+=( -H "Authorization: Bearer ${API_BEARER_TOKEN_SMOKE}" )
fi

fail() { echo "[FAIL] $*"; exit 1; }
ok() { echo "[OK] $*"; }

health_json="$(curl -fsS "${BASE_URL}/api/health")" || fail "Health check request failed (${BASE_URL}/api/health)"
python - <<'PY' "$health_json" || fail "Health payload missing expected shape"
import json, sys
p = json.loads(sys.argv[1])
assert isinstance(p, dict)
assert 'status' in p
PY
ok "Health endpoint reachable"

start_json="$(curl -fsS -X POST "${BASE_URL}/api/query" "${hdr[@]}" -d '{"query":"smoke test query","limit":1,"limit_scope":"chunks","chunks_per_paper":1}')" || fail "Failed to start query job"
python - <<'PY' "$start_json" || fail "Query start payload invalid"
import json, sys
p = json.loads(sys.argv[1])
assert p.get('status') in {'running', 'completed', 'idle'}
PY
ok "Query start accepted"

end_ts=$(( $(date +%s) + TIMEOUT_SECONDS ))
terminal=""
while [[ $(date +%s) -lt ${end_ts} ]]; do
  status_json="$(curl -fsS "${BASE_URL}/api/query/status")" || fail "Failed polling /api/query/status"
  terminal="$(python - <<'PY' "$status_json"
import json, sys
p = json.loads(sys.argv[1])
status = p.get('status', '')
if status in {'completed','failed','cancelled','idle'}:
    print(status)
PY
)"
  if [[ -n "${terminal}" ]]; then
    break
  fi
  sleep "${POLL_INTERVAL}"
done

[[ -n "${terminal}" ]] || fail "Timed out waiting for /api/query/status terminal state"
ok "Query reached terminal state: ${terminal}"
if [[ "${terminal}" == "failed" || "${terminal}" == "cancelled" ]]; then
  fail "Query terminal state indicates failure: ${terminal}"
fi

if [[ "${RUN_DIAGNOSTICS}" == "1" ]]; then
  diag_json="$(curl -fsS "${BASE_URL}/api/diagnostics")" || fail "Diagnostics request failed"
  python - <<'PY' "$diag_json" || fail "Diagnostics payload missing expected keys"
import json, sys
p = json.loads(sys.argv[1])
assert 'ok' in p
assert 'checks' in p
PY
  ok "Diagnostics endpoint reachable"
fi

echo "Smoke workflow passed."
