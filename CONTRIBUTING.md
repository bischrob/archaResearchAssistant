# Contributing

This repository is open to issues and pull requests.

## Before opening a pull request

1. Open an issue first for large changes, workflow changes, or interface changes.
2. Keep changes focused and easy to review.
3. Do not commit secrets, local data, PDFs, models, logs, or `.env` files.

## Local checks

Run the checks that match your change:

```bash
make preflight
make smoke
make test-unit
```

If your change affects live workflow behavior, also run:

```bash
make test-e2e
```

## Scope expectations

- Documentation updates should stay aligned across `README.md`, `docs/`, and any in-app help text.
- Public-facing docs should not depend on local-only `Vault/` notes.
- Files removed from Git tracking should be removed with `git rm --cached`, not deleted from disk, unless deletion is explicitly intended.
