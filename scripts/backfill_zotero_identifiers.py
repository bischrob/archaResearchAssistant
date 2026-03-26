#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.rag.config import Settings
from src.rag.metadata_provider import metadata_title_year_key
from src.rag.neo4j_store import GraphStore
from src.rag.path_utils import resolve_input_path


def _normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    normalized = doi.strip().lower()
    normalized = re.sub(r"^https?://(dx\.)?doi\.org/", "", normalized)
    return normalized.strip().rstrip(".;,")


def _norm_path(path_str: str | None) -> str:
    raw = (path_str or "").strip()
    if not raw:
        return ""
    return str(Path(raw)).replace("\\", "/").lower()


def _discover_zotero_db_path(settings: Settings) -> Path:
    raw = (settings.zotero_db_path or "").strip()
    if raw:
        return resolve_input_path(raw)

    candidates = [
        Path.home() / "Zotero" / "zotero.sqlite",
        Path("/mnt/c/Users") / "rjbischo" / "Zotero" / "zotero.sqlite",
    ]
    try:
        candidates.extend(sorted(Path("/mnt/c/Users").glob("*/Zotero/zotero.sqlite")))
    except Exception:
        pass
    for c in candidates:
        try:
            if c.exists():
                return c
        except Exception:
            continue
    return Path("")


def _resolve_storage_root(settings: Settings, db_path: Path) -> Path:
    raw = (settings.zotero_storage_root or "").strip()
    if raw:
        return resolve_input_path(raw)
    if db_path:
        return db_path.parent / "storage"
    return Path("")


def _resolve_attachment_path(raw_path: str | None, attachment_key: str, storage_root: Path) -> str | None:
    path_raw = (raw_path or "").strip()
    if not path_raw:
        return None
    if path_raw.lower().startswith("storage:"):
        rel = path_raw.split(":", 1)[1].strip().lstrip("/\\")
        if storage_root:
            return str(storage_root / attachment_key / rel)
        return rel
    return str(resolve_input_path(path_raw))


@dataclass
class ZoteroEntry:
    library_id: int
    item_key: str
    attachment_key: str
    doi: str
    title: str
    year: int | None
    attachment_path: str

    @property
    def persistent_id(self) -> str:
        return f"{self.library_id}:{self.item_key}"

    @property
    def title_year_key(self) -> str | None:
        return metadata_title_year_key({"title": self.title, "year": self.year})


def _load_zotero_entries(db_path: Path, storage_root: Path) -> list[ZoteroEntry]:
    uri = f"file:{db_path}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
              parent.libraryID AS library_id,
              parent.key AS parent_key,
              att.key AS attachment_key,
              ai.path AS attachment_path_raw,
              max(CASE WHEN f.fieldName = 'title' THEN idv.value END) AS title,
              max(CASE WHEN f.fieldName = 'DOI' THEN idv.value END) AS doi,
              max(CASE WHEN f.fieldName = 'date' THEN idv.value END) AS date_value
            FROM itemAttachments ai
            JOIN items att ON att.itemID = ai.itemID
            JOIN items parent ON parent.itemID = ai.parentItemID
            LEFT JOIN itemData id ON id.itemID = ai.parentItemID
            LEFT JOIN fields f ON f.fieldID = id.fieldID
            LEFT JOIN itemDataValues idv ON idv.valueID = id.valueID
            WHERE ai.parentItemID IS NOT NULL
              AND (
                lower(coalesce(ai.contentType, '')) = 'application/pdf'
                OR lower(coalesce(ai.path, '')) LIKE '%.pdf%'
              )
            GROUP BY parent.libraryID, parent.key, att.key, ai.path
            """
        ).fetchall()
    finally:
        conn.close()

    out: list[ZoteroEntry] = []
    for row in rows:
        item_key = (row["parent_key"] or "").strip()
        attachment_key = (row["attachment_key"] or "").strip()
        if not item_key or not attachment_key:
            continue
        date_raw = (row["date_value"] or "").strip()
        year_match = re.search(r"\b(19|20)\d{2}\b", date_raw)
        year = int(year_match.group(0)) if year_match else None
        path = _resolve_attachment_path(row["attachment_path_raw"], attachment_key, storage_root)
        if not path or not path.lower().endswith(".pdf"):
            continue
        out.append(
            ZoteroEntry(
                library_id=int(row["library_id"] or 1),
                item_key=item_key,
                attachment_key=attachment_key,
                doi=_normalize_doi(row["doi"]),
                title=(row["title"] or "").strip(),
                year=year,
                attachment_path=path,
            )
        )
    return out


def _unique_map(entries: list[ZoteroEntry], key_fn) -> dict[str, ZoteroEntry]:
    bucket: dict[str, list[ZoteroEntry]] = {}
    for e in entries:
        key = (key_fn(e) or "").strip().lower()
        if not key:
            continue
        bucket.setdefault(key, []).append(e)
    return {k: v[0] for k, v in bucket.items() if len(v) == 1}


def _choose_entry(
    article: dict[str, Any],
    *,
    by_path: dict[str, ZoteroEntry],
    by_doi: dict[str, ZoteroEntry],
    by_title_year: dict[str, ZoteroEntry],
    by_item_key: dict[str, ZoteroEntry],
) -> tuple[ZoteroEntry | None, str]:
    existing_item_key = str(article.get("zotero_item_key") or "").strip().lower()
    if existing_item_key and existing_item_key in by_item_key:
        return by_item_key[existing_item_key], "existing_item_key"

    source_path = _norm_path(article.get("source_path"))
    if source_path and source_path in by_path:
        return by_path[source_path], "source_path"

    doi = _normalize_doi(article.get("doi"))
    if doi and doi in by_doi:
        return by_doi[doi], "doi"

    ty = metadata_title_year_key({"title": article.get("title"), "year": article.get("year")})
    ty_key = (ty or "").strip().lower()
    if ty_key and ty_key in by_title_year:
        return by_title_year[ty_key], "title_year"

    return None, "unmatched"


def _load_articles(store: GraphStore) -> list[dict[str, Any]]:
    with store.driver.session() as session:
        rows = session.run(
            """
            MATCH (a:Article)
            RETURN a.id AS id,
                   a.title AS title,
                   a.year AS year,
                   a.doi AS doi,
                   a.source_path AS source_path,
                   a.zotero_item_key AS zotero_item_key,
                   a.zotero_attachment_key AS zotero_attachment_key,
                   a.zotero_library_id AS zotero_library_id,
                   a.zotero_persistent_id AS zotero_persistent_id
            """
        )
        return [dict(r) for r in rows]


def _apply_updates(store: GraphStore, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with store.driver.session() as session:
        session.run(
            """
            UNWIND $rows AS row
            MATCH (a:Article {id: row.id})
            SET a.zotero_item_key = row.zotero_item_key,
                a.zotero_attachment_key = row.zotero_attachment_key,
                a.zotero_library_id = row.zotero_library_id,
                a.zotero_persistent_id = row.zotero_persistent_id
            """,
            rows=rows,
        )
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Zotero persistent identifiers into Neo4j Article nodes.")
    parser.add_argument("--apply", action="store_true", help="Write updates to Neo4j (default is dry-run).")
    parser.add_argument(
        "--report-json",
        default="logs/zotero_identifier_backfill_report.json",
        help="Path for JSON report output.",
    )
    parser.add_argument(
        "--missing-csv",
        default="logs/neo4j_pdfs_missing_zotero_identifier.csv",
        help="CSV output for Neo4j PDFs missing Zotero identifier after backfill.",
    )
    args = parser.parse_args()

    settings = Settings()
    db_path = _discover_zotero_db_path(settings)
    if not db_path or not db_path.exists():
        raise SystemExit("Zotero DB not found. Set ZOTERO_DB_PATH or place zotero.sqlite in a discoverable location.")
    storage_root = _resolve_storage_root(settings, db_path)
    entries = _load_zotero_entries(db_path, storage_root)
    if not entries:
        raise SystemExit("No Zotero PDF entries found.")

    by_path = _unique_map(entries, lambda e: _norm_path(e.attachment_path))
    by_doi = _unique_map(entries, lambda e: e.doi)
    by_title_year = _unique_map(entries, lambda e: e.title_year_key or "")
    by_item_key = _unique_map(entries, lambda e: e.item_key)

    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    try:
        articles = _load_articles(store)

        updates: list[dict[str, Any]] = []
        match_method_counts: dict[str, int] = {}
        for a in articles:
            entry, method = _choose_entry(
                a,
                by_path=by_path,
                by_doi=by_doi,
                by_title_year=by_title_year,
                by_item_key=by_item_key,
            )
            if not entry:
                continue

            match_method_counts[method] = match_method_counts.get(method, 0) + 1
            current_item_key = str(a.get("zotero_item_key") or "").strip()
            current_attachment_key = str(a.get("zotero_attachment_key") or "").strip()
            current_library_id = a.get("zotero_library_id")
            current_persistent = str(a.get("zotero_persistent_id") or "").strip()

            target_persistent = entry.persistent_id
            if (
                current_item_key == entry.item_key
                and current_attachment_key == entry.attachment_key
                and str(current_library_id or "") == str(entry.library_id)
                and current_persistent == target_persistent
            ):
                continue

            updates.append(
                {
                    "id": a["id"],
                    "zotero_item_key": entry.item_key,
                    "zotero_attachment_key": entry.attachment_key,
                    "zotero_library_id": int(entry.library_id),
                    "zotero_persistent_id": target_persistent,
                }
            )

        updated = _apply_updates(store, updates) if args.apply else 0

        refreshed = _load_articles(store)
        missing = []
        for a in refreshed:
            source_path = str(a.get("source_path") or "")
            if not source_path.lower().endswith(".pdf"):
                continue
            if str(a.get("zotero_persistent_id") or "").strip():
                continue
            missing.append(
                {
                    "id": a.get("id"),
                    "title": a.get("title"),
                    "year": a.get("year"),
                    "doi": a.get("doi"),
                    "source_path": source_path,
                }
            )
    finally:
        store.close()

    report = {
        "apply": bool(args.apply),
        "zotero_db_path": str(db_path),
        "zotero_storage_root": str(storage_root),
        "zotero_entries": len(entries),
        "articles_total": len(articles),
        "matched_articles": sum(match_method_counts.values()),
        "match_method_counts": match_method_counts,
        "updated_articles": updated,
        "missing_after_backfill_count": len(missing),
        "missing_after_backfill_sample": missing[:30],
    }

    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    csv_path = Path(args.missing_csv)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "title", "year", "doi", "source_path"])
        writer.writeheader()
        writer.writerows(missing)

    print(json.dumps(report, indent=2))
    print(f"Wrote JSON report: {report_path}")
    print(f"Wrote missing CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
