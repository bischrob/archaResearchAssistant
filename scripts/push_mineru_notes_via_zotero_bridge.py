#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import httpx


def iter_markdown_files(source_dir: Path, limit: int | None) -> Iterable[Path]:
    count = 0
    for path in sorted(source_dir.glob("*.md")):
        stem = path.stem.strip()
        if len(stem) != 8:
            continue
        yield path
        count += 1
        if limit is not None and count >= limit:
            break


def push_note(
    client: httpx.Client,
    endpoint: str,
    auth_token: str,
    md_path: Path,
) -> dict:
    payload = {
        "auth_token": auth_token,
        "attachment_key": md_path.stem.upper(),
        "md_content": md_path.read_text(encoding="utf-8"),
    }
    headers = {
        "Content-Type": "application/json",
        "X-RAG-Sync-Token": auth_token,
        "Authorization": f"Bearer {auth_token}",
    }
    response = client.post(endpoint, content=json.dumps(payload), headers=headers)
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Push MinerU markdown notes into Zotero through the local zotero-rag-sync bridge."
    )
    parser.add_argument("source_dir", help="Directory containing attachment-key-named .md files")
    parser.add_argument("--endpoint", default="http://127.0.0.1:23119/rag-sync/bridge/import-mineru-note")
    parser.add_argument("--token", required=True, help="Bridge token from extensions.zotero-rag-sync.externalBridgeToken")
    parser.add_argument("--limit", type=int, default=None, help="Optional batch limit")
    args = parser.parse_args()

    source_dir = Path(args.source_dir).expanduser().resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"Source directory not found: {source_dir}")

    created = 0
    updated = 0
    unchanged = 0
    failed = 0

    with httpx.Client(timeout=120.0) as client:
        for md_path in iter_markdown_files(source_dir, args.limit):
            try:
                result = push_note(client, args.endpoint, args.token, md_path)
                status = str(result.get("status") or "").strip().lower()
                if status == "created":
                    created += 1
                elif status == "updated":
                    updated += 1
                elif status == "unchanged":
                    unchanged += 1
                else:
                    failed += 1
                    print(f"[unknown] {md_path.name}: {result}")
                    continue
                print(f"[{status}] {md_path.name} -> note {result.get('note_item_id')}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"[failed] {md_path.name}: {exc}")

    print(
        json.dumps(
            {
                "source_dir": str(source_dir),
                "created": created,
                "updated": updated,
                "unchanged": unchanged,
                "failed": failed,
            },
            indent=2,
        )
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
