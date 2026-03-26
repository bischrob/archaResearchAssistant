from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .path_utils import resolve_input_path

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _extract_year(raw: str | None) -> int | None:
    if not raw:
        return None
    m = YEAR_RE.search(str(raw))
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None


def _normalize_author(first: str | None, last: str | None) -> str | None:
    first = (first or "").strip()
    last = (last or "").strip()
    full = " ".join(x for x in [first, last] if x)
    return full or None


def _resolve_attachment_path(raw_path: str | None, attachment_key: str, storage_root: str | None) -> str | None:
    path_raw = (raw_path or "").strip()
    if not path_raw:
        return None

    # Zotero-managed file path relative to storage directory.
    if path_raw.lower().startswith("storage:"):
        rel = path_raw.split(":", 1)[1].strip().lstrip("/\\")
        if storage_root:
            base = resolve_input_path(storage_root)
            return str(base / attachment_key / rel)
        return rel

    # Linked attachment absolute/relative path.
    return str(resolve_input_path(path_raw))


def _attachment_is_pdf(path_raw: str | None, content_type: str | None = None) -> bool:
    raw = (path_raw or "").strip()
    if not raw:
        return (content_type or "").strip().lower() == "application/pdf"
    lowered = raw.lower()
    if lowered.startswith("storage:"):
        rel = lowered.split(":", 1)[1].strip().lstrip("/\\")
        return bool(rel) and rel.endswith(".pdf")
    return lowered.endswith(".pdf")


def load_zotero_entries(zotero_db_path: str, storage_root: str | None = None) -> list[dict]:
    db_path = Path(zotero_db_path)
    if not db_path.exists():
        return []

    # Prefer immutable mode so reads succeed while Zotero has the DB open.
    uri = f"file:{db_path}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        # Fallback for environments that do not support immutable query parameter.
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        try:
            rows = conn.execute(
                """
                SELECT
                  ai.itemID AS attachment_item_id,
                  ai.parentItemID AS parent_item_id,
                  ai.path AS attachment_path_raw,
                  ai.contentType AS content_type,
                  att.key AS attachment_key,
                  parent.key AS parent_key,
                  parent.libraryID AS library_id
                FROM itemAttachments ai
                JOIN items att ON att.itemID = ai.itemID
                LEFT JOIN items parent ON parent.itemID = ai.parentItemID
                WHERE ai.parentItemID IS NOT NULL
                  AND (
                    lower(coalesce(ai.contentType, '')) = 'application/pdf'
                    OR lower(coalesce(ai.path, '')) LIKE '%.pdf%'
                  )
                ORDER BY ai.parentItemID ASC, ai.itemID ASC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute(
                """
                SELECT
                  ai.itemID AS attachment_item_id,
                  ai.parentItemID AS parent_item_id,
                  ai.path AS attachment_path_raw,
                  ai.contentType AS content_type,
                  att.key AS attachment_key,
                  parent.key AS parent_key,
                  1 AS library_id
                FROM itemAttachments ai
                JOIN items att ON att.itemID = ai.itemID
                LEFT JOIN items parent ON parent.itemID = ai.parentItemID
                WHERE ai.parentItemID IS NOT NULL
                  AND (
                    lower(coalesce(ai.contentType, '')) = 'application/pdf'
                    OR lower(coalesce(ai.path, '')) LIKE '%.pdf%'
                  )
                ORDER BY ai.parentItemID ASC, ai.itemID ASC
                """
            ).fetchall()

        if not rows:
            return []

        parent_ids = sorted({int(r["parent_item_id"]) for r in rows if r["parent_item_id"] is not None})
        if not parent_ids:
            return []

        placeholders = ",".join("?" for _ in parent_ids)
        field_rows = conn.execute(
            f"""
            SELECT
              id.itemID AS item_id,
              f.fieldName AS field_name,
              idv.value AS field_value
            FROM itemData id
            JOIN fields f ON f.fieldID = id.fieldID
            JOIN itemDataValues idv ON idv.valueID = id.valueID
            WHERE id.itemID IN ({placeholders})
              AND f.fieldName IN ('title', 'DOI', 'date', 'publicationTitle', 'publisher')
            """,
            parent_ids,
        ).fetchall()

        try:
            # Older Zotero schemas expose names via creatorData
            creators_rows = conn.execute(
                f"""
                SELECT
                  ic.itemID AS item_id,
                  ic.orderIndex AS order_index,
                  cd.firstName AS first_name,
                  cd.lastName AS last_name
                FROM itemCreators ic
                JOIN creators c ON c.creatorID = ic.creatorID
                JOIN creatorData cd ON cd.creatorDataID = c.creatorDataID
                WHERE ic.itemID IN ({placeholders})
                ORDER BY ic.itemID ASC, ic.orderIndex ASC
                """,
                parent_ids,
            ).fetchall()
        except sqlite3.OperationalError:
            # Zotero 8 schema stores first/last name directly on creators
            creators_rows = conn.execute(
                f"""
                SELECT
                  ic.itemID AS item_id,
                  ic.orderIndex AS order_index,
                  c.firstName AS first_name,
                  c.lastName AS last_name
                FROM itemCreators ic
                JOIN creators c ON c.creatorID = ic.creatorID
                WHERE ic.itemID IN ({placeholders})
                ORDER BY ic.itemID ASC, ic.orderIndex ASC
                """,
                parent_ids,
            ).fetchall()

        by_item: dict[int, dict] = {pid: {} for pid in parent_ids}
        for row in field_rows:
            item_id = int(row["item_id"])
            by_item.setdefault(item_id, {})[str(row["field_name"])] = row["field_value"]

        authors_by_item: dict[int, list[str]] = {pid: [] for pid in parent_ids}
        for row in creators_rows:
            item_id = int(row["item_id"])
            name = _normalize_author(row["first_name"], row["last_name"])
            if name:
                authors_by_item.setdefault(item_id, []).append(name)

        out: list[dict] = []
        for row in rows:
            parent_item_id = int(row["parent_item_id"])
            path_raw = (row["attachment_path_raw"] or "").strip() or None
            content_type = row["content_type"]
            if not _attachment_is_pdf(path_raw, content_type):
                continue
            field_map = by_item.get(parent_item_id, {})
            title = (field_map.get("title") or "").strip() or None
            doi = (field_map.get("DOI") or "").strip() or None
            year = _extract_year(field_map.get("date"))
            journal = (field_map.get("publicationTitle") or "").strip() or None
            publisher = (field_map.get("publisher") or "").strip() or None

            attachment_key = (row["attachment_key"] or "").strip() or None
            parent_key = (row["parent_key"] or "").strip() or None
            library_id = int(row["library_id"]) if row["library_id"] is not None else 1
            source_path = _resolve_attachment_path(path_raw, attachment_key or "", storage_root)

            out.append(
                {
                    "title": title,
                    "year": year,
                    "citekey": None,
                    "paperpile_id": None,
                    "doi": doi,
                    "journal": journal,
                    "publisher": publisher,
                    "authors": authors_by_item.get(parent_item_id, []),
                    "zotero_item_key": parent_key,
                    "zotero_library_id": library_id,
                    "zotero_persistent_id": (f"{library_id}:{parent_key}" if parent_key else None),
                    "zotero_attachment_key": attachment_key,
                    "zotero_parent_item_id": parent_item_id,
                    "zotero_attachment_item_id": int(row["attachment_item_id"]),
                    "attachment_path": source_path,
                    "attachment_path_raw": path_raw,
                    "metadata_source": "zotero",
                }
            )
        return out
    finally:
        conn.close()
