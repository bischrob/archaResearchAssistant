# Security Policy

## Reporting a vulnerability

If you believe you have found a security issue, do not open a public issue with exploit details.

Instead:

1. Open a private GitHub security advisory if available for this repository.
2. If that is not practical, contact the maintainer directly through a non-public channel and include:
   - affected component
   - reproduction steps
   - impact assessment
   - any suggested mitigation

## Scope

Security reports are most useful for:

- exposed API auth issues
- secret leakage
- unsafe file handling
- dependency risks that materially affect deployment or data handling

This repository is provided for research and engineering workflows, so reports should distinguish between:

- local-only development assumptions
- issues that affect a real deployed service
