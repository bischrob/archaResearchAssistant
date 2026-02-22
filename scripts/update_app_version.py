#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
APP_FILE = ROOT / "webapp" / "main.py"
FASTAPI_VERSION_RE = re.compile(
    r'(app\s*=\s*FastAPI\([\s\S]*?\bversion\s*=\s*")([^"]+)(")',
    re.MULTILINE,
)
GENERIC_VERSION_RE = re.compile(r'(\bversion\s*=\s*")([^"]+)(")')


def current_utc_version() -> str:
    return datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M%S")


def update_app_version(version: str) -> tuple[str, str]:
    text = APP_FILE.read_text(encoding="utf-8")

    old_version: str | None = None

    def _replace(match: re.Match[str]) -> str:
        nonlocal old_version
        old_version = match.group(2)
        return f"{match.group(1)}{version}{match.group(3)}"

    new_text, count = FASTAPI_VERSION_RE.subn(_replace, text, count=1)
    if count == 0:
        new_text, count = GENERIC_VERSION_RE.subn(_replace, text, count=1)
    if count == 0:
        raise RuntimeError(f"Could not find FastAPI version assignment in {APP_FILE}.")

    if new_text != text:
        APP_FILE.write_text(new_text, encoding="utf-8")
    return old_version or "", version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update FastAPI app version to a datetime-based value."
    )
    parser.add_argument(
        "version",
        nargs="?",
        default=current_utc_version(),
        help="Version string to write (default: current UTC datetime version).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    old_version, new_version = update_app_version(args.version)
    if old_version == new_version:
        print(f"App version unchanged: {new_version}")
    else:
        print(f"App version updated: {old_version} -> {new_version}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"Failed to update app version: {exc}", file=sys.stderr)
        raise
