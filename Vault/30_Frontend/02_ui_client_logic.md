# Frontend: Client Logic

## Source file
- `webapp/static/app.js`

## Architecture
Vanilla JS controller that:
- sends API requests
- polls job status endpoints
- renders dynamic HTML to output containers

## Core behaviors
- `api(path, body)` helper handles POST + JSON + error propagation.
- `startPolling(name, onUpdate)` polls `/api/<job>/status` every second.
- dedicated renderers for:
  - health
  - sync job
  - ingest job + preview
  - query results
  - ask report + citations
  - diagnostics table

## Markdown rendering
- Custom lightweight markdown parser in `markdownToHtml`.
- Escapes HTML before formatting to mitigate raw HTML injection.
- Supports headings, emphasis, inline code, fenced code, bullet lists, and links.

## Ask UX
- Shows staged loading messages while `/api/ask` runs.
- Stores last ask report for export buttons.

## Failure handling
- API error messages are surfaced in panel outputs.
- Pollers auto-stop when job state leaves `running`.

## Extension points
- Add new panels by defining endpoint call + renderer + button handler.
- Replace custom markdown parser with library if richer markdown needed.

## Related
- [[20_WebAPI/01_api_surface]]
- [[70_Feature_Playbooks/04_add_ui_workflow]]
