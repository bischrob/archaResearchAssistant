---
name: Bug report
about: Report a defect or regression in the app, sync flow, plugin, or docs
title: "[Bug] "
labels: ["bug"]
assignees: []
---

## Summary

Describe the problem in one or two sentences.

## Impact

- What workflow is blocked?
- Is this a regression?
- How severe is it?

## Environment

- OS:
- Python version:
- Docker version:
- Zotero version:
- Browser:
- Commit or tag:

## Reproduction Steps

1.
2.
3.

## Expected Behavior

Describe what should have happened.

## Actual Behavior

Describe what happened instead.

## Logs or Screenshots

Include relevant output from:

- `make preflight`
- `make smoke`
- web UI status output
- Zotero plugin diagnostics
- backend logs

## Config Notes

List only non-secret configuration relevant to the problem, such as:

- `METADATA_BACKEND`
- `CITATION_PARSER`
- whether `API_BEARER_TOKEN` is enabled
- whether `QWEN3_MODEL_PATH` and `QWEN3_CITATION_ADAPTER_PATH` are set

Do not paste secrets, API keys, tokens, or private PDF content.
