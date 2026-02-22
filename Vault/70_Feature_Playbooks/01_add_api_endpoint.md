# Playbook: Add a New API Endpoint

## Goal
Add a new FastAPI endpoint safely with predictable frontend and test behavior.

## Steps
1. Define request/response model in `webapp/main.py` if needed.
2. Implement endpoint function with explicit validation and clear error messages.
3. Reuse `Settings`, `GraphStore`, and existing module helpers where possible.
4. If long-running, integrate with `JobManager` and add status/stop endpoints.
5. Add UI controls and renderer in `webapp/static/app.js` and `index.html`.
6. Add tests in `tests/test_web_api.py` with monkeypatched dependencies.

## Design rules
- Keep endpoint orchestration in API layer; heavy logic belongs in `src/rag` modules.
- Return stable JSON shape for frontend compatibility.
- Use `HTTPException` for user-actionable failures.

## Validation checklist
- Route appears in API surface note.
- Frontend action path tested manually.
- pytest updated for success and failure branches.
