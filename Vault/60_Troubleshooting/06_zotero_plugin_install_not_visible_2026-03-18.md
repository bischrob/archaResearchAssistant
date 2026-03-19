# Zotero Plugin Install Not Visible (2026-03-18)

## Symptom
- Zotero 8 plugin appears "not installing" (no plugin behavior in UI, no plugin log entries).

## Evidence from `zoterodebuglog.txt`
- Runtime line reports `safeMode => true` on `Zotero 8.0.4`.
- Extensions listed are disabled in that run.
- No lines reference `rag-sync@rjbischo.local`, `RAG Sync`, or `ragsync.js`.
- Local XPI build succeeds and includes expected files: `manifest.json`, `bootstrap.js`, `prefs.js`, `content/scripts/ragsync.js`.
- Updated log includes definitive install failure:
  - `Loading extension 'rag-sync@rjbischo.local': Reading manifest: applications.zotero.update_url not provided`
  - `Invalid XPI: Error: Extension is invalid`
- Latest follow-up log still shows the same `update_url not provided` and `Invalid XPI` errors.
- `safeMode` is not present in the latest header, so Zotero appears to be running in normal mode now.

## Likely Causes
- Zotero launched in Safe Mode, so add-ons are disabled for that session.
- Plugin may be copied to a different profile than the active Zotero profile.
- Install action may not have been triggered in the captured session.
- Add-on manifest missing required `applications.zotero.update_url` for this Zotero 8 install path.
- Zotero is still loading an older/stale XPI from the profile `extensions` directory that does not include the patched manifest.

## Checks and Fixes
1. Start Zotero normally (not Troubleshoot/Safe Mode).
2. Verify active profile path in Zotero debug header and confirm file exists:
   - `.../Profiles/<active>/extensions/rag-sync@rjbischo.local.xpi`
3. In Zotero Add-ons Manager, confirm plugin appears and is enabled.
4. Re-run debug with normal startup and search for:
   - `rag-sync@rjbischo.local`
   - `RAG Sync: startup`
5. If still missing, install by drag-and-drop the built XPI from:
   - `/tmp/rag-sync@rjbischo.local.xpi`
6. Remove stale profile copy and reinstall:
   - delete `.../Profiles/<active>/extensions/rag-sync@rjbischo.local.xpi`
   - copy/reinstall freshly built `/tmp/rag-sync@rjbischo.local.xpi`
   - fully restart Zotero and re-check debug output
7. If plugin appears as only `Print` under Tools:
   - cause: plugin registered placeholder `l10nID: menu-print`
   - fix: use explicit `RAG Sync` Tools submenu labels (current repo patch) and reinstall
8. If `Sync Now` appears to do nothing:
   - cause: action was previously log-only with no UI feedback
   - fix: current repo patch adds a centered in-app progress overlay during sync and explicit alert on failure
9. If status is still too vague during sync:
   - cause: plugin was not polling `/api/sync/status` and backend sync messages were coarse
   - fix: current repo patch now polls `/api/sync/status` continuously and backend sync now reports per-file scan messages (`Scanning <i>/<n>: <filename>`)
10. If sync fails on inaccessible default PDF source path:
   - cause: backend default source path did not match Zotero linked-files directory
   - fix: sync now accepts per-request `source_dir`; plugin preference `extensions.zotero-rag-sync.sourceDir` is configurable (default `C:\Users\rjbischo\Nextcloud\zotero`)

## Implemented Repo Fix
- Added `applications.zotero.update_url` to `plugins/zotero-rag-sync/manifest.json`.
- Hardened `scripts/build_zotero_plugin_xpi.sh` to fail builds missing `applications.zotero.update_url`.
- Replaced placeholder Tools menu registration (`menu-print`) with explicit `RAG Sync` submenu injection containing:
  - `Sync Now`
  - `Retry Failed`
  - `Pause/Resume`
  - `Show Diagnostics`
- Implemented `Sync Now` execution feedback:
  - centered in-app progress overlay while polling backend `/api/sync/status` until terminal state
  - live progress percent + message updates from backend status
  - error popup via `Zotero.alert(...)` on failure
  - temporary `Sync Now (Running...)` label while active
  - completion summary with scanned/matched/unmatched counts and unmatched filename sample
- Added configurable sync source directory:
  - backend `/api/sync` accepts `source_dir`
  - plugin sends `extensions.zotero-rag-sync.sourceDir`
  - backend resolves both UNC and Windows drive-letter paths under WSL

## Related
- [[40_Scripts/02_shell_scripts]]
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
