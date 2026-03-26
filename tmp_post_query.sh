#!/usr/bin/env bash
set -x
curl -v --max-time 30 -H 'Content-Type: application/json' --data @/mnt/c/Users/rjbischo/.openclaw/workspace/query_payload.json http://127.0.0.1:8000/api/query
