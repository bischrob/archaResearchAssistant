# Playbook: Add a New UI Workflow

## Goal
Add a new user workflow to the static frontend without introducing regressions.

## Files
- `webapp/static/index.html`
- `webapp/static/app.js`
- `webapp/static/styles.css`

## Steps
1. Add a panel section and output container in `index.html`.
2. Add handler + API call in `app.js`.
3. Add renderer function with clear loading/success/failure states.
4. Reuse `renderSimpleMessage`, `statusHeader`, and `progressBlock` patterns.
5. Add minimal CSS for layout consistency.
6. Add backend endpoint/tests if workflow is new.

## Guardrails
- Keep HTML escaped via `escapeHtml` for dynamic text.
- Stop pollers on terminal states.
- Keep status messages explicit and user-actionable.

## Validation checklist
- Manual click-through verifies idle/running/completed/failed paths.
- No JS console errors during normal flow.
