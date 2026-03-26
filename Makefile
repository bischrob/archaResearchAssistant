.PHONY: help preflight start test test-unit test-e2e smoke sync-example ingest-preview-example

help:
	@echo "Available targets:"
	@echo "  make preflight            # Validate local prerequisites and config"
	@echo "  make start                # Start Neo4j + API/web GUI"
	@echo "  make test                 # Run non-e2e pytest tests (safe default)"
	@echo "  make test-unit            # Run non-e2e pytest tests"
	@echo "  make test-e2e             # Run live e2e tests (requires RUN_E2E=1)"
	@echo "  make smoke                # Hit health/query/diagnostics endpoints"
	@echo "  make sync-example         # Example sync trigger via API"
	@echo "  make ingest-preview-example # Example ingest preview trigger via API"

preflight:
	./scripts/preflight_check.sh

start:
	./start.sh

test:
	pytest -m "not e2e"

test-unit:
	pytest -m "not e2e"

test-e2e:
	RUN_E2E=1 pytest -m e2e

smoke:
	./scripts/smoke_local_workflow.sh

sync-example:
	@bash -lc 'auth=(); \
	if [[ -n "$${API_BEARER_TOKEN:-}" ]]; then auth=(-H "Authorization: Bearer $${API_BEARER_TOKEN}"); fi; \
	curl -fsS -X POST http://127.0.0.1:8000/api/sync "$${auth[@]}" \
	  -H "Content-Type: application/json" \
	  -d '"'"'{"dry_run":true,"source_mode":"zotero_db","run_ingest":false}'"'"' | python -m json.tool'

ingest-preview-example:
	@bash -lc 'auth=(); \
	if [[ -n "$${API_BEARER_TOKEN:-}" ]]; then auth=(-H "Authorization: Bearer $${API_BEARER_TOKEN}"); fi; \
	curl -fsS -X POST http://127.0.0.1:8000/api/ingest/preview "$${auth[@]}" \
	  -H "Content-Type: application/json" \
	  -d '"'"'{"mode":"batch","partial_count":3,"override_existing":false}'"'"' | python -m json.tool'
