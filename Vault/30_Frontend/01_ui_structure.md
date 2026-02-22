# Frontend: UI Structure

## Source files
- `webapp/static/index.html`
- `webapp/static/styles.css`

## Layout
- Single-page app with two tabs:
  - `Operations`
  - `Model Details & Diagnostics`

## Operations tab components
- System health panel.
- Sync controls (run/stop/dry-run).
- Ingest controls and preview table.
- Search query panel.
- LLM answer panel with export buttons.

## Details tab components
- Static architecture explanation.
- Query process explanation.
- Diagnostics action/output table.

## Styling characteristics
- Warm light theme using CSS variables.
- Status pill classes (`status-running`, etc.) and progress bar.
- Responsive grid for system/sync blocks.

## Accessibility/UX notes
- Uses semantic buttons and tables.
- No client-side routing.
- Long outputs shown in `<details>` sections.

## Related
- [[30_Frontend/02_ui_client_logic]]
- [[20_WebAPI/01_api_surface]]
