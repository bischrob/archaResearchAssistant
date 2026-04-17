from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import re
import sqlite3
from pathlib import Path

from .path_utils import resolve_input_path


_HTML_BREAK_RE = re.compile(r"(?i)(<\s*br\s*/?>|<\s*/\s*(p|div|li|h[1-6])\s*>)")
_HTML_TAG_RE = re.compile(r"(?is)<[^>]+>")
_MINERU_TITLE_HINT_RE = re.compile(r"mineru", re.IGNORECASE)
MIN_MINERU_TEXT_LENGTH = 120
_MINERU_MARKDOWN_HINTS = (
    re.compile(r"(?m)^\s{0,3}#{1,6}\s+\S"),
    re.compile(r"(?m)^\s{0,3}[-*+]\s+\S"),
    re.compile(r"(?m)^\s{0,3}\d+\.\s+\S"),
    re.compile(r"(?m)^\s{0,3}```"),
    re.compile(r"(?m)^\s*\|.+\|\s*$"),
)


@dataclass(frozen=True)
class MinerUChildNote:
    attachment_item_id: int
    attachment_key: str | None
    parent_item_key: str | None
    note_item_id: int
    note_item_key: str
    note_title: str | None
    markdown_text: str
    source_hash: str


def _extract_text_from_zotero_note(raw_note: str) -> str:
    expanded = _HTML_BREAK_RE.sub("\n", raw_note or "")
    stripped = _HTML_TAG_RE.sub("", expanded)
    unescaped = html.unescape(stripped)
    lines = [line.rstrip() for line in unescaped.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()


def _looks_like_mineru_markdown(title: str | None, text: str) -> bool:
    title_hit = bool(_MINERU_TITLE_HINT_RE.search((title or "").strip()))
    marker_hits = sum(1 for rx in _MINERU_MARKDOWN_HINTS if rx.search(text or ""))
    return title_hit and marker_hits >= 2 and len((text or "").strip()) >= MIN_MINERU_TEXT_LENGTH


def _lookup_note_titles(conn: sqlite3.Connection, note_item_ids: list[int]) -> dict[int, str]:
    if not note_item_ids:
        return {}
    placeholders = ",".join("?" for _ in note_item_ids)
    try:
        rows = conn.execute(
            f"""
            SELECT id.itemID AS item_id, idv.value AS title
            FROM itemData id
            JOIN fields f ON f.fieldID = id.fieldID
            JOIN itemDataValues idv ON idv.valueID = id.valueID
            WHERE id.itemID IN ({placeholders})
              AND f.fieldName = 'title'
            """,
            note_item_ids,
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    out: dict[int, str] = {}
    for row in rows:
        item_id = int(row["item_id"])
        title = str(row["title"] or "").strip()
        if title:
            out[item_id] = title
    return out


def load_mineru_child_note_for_attachment(row: dict, *, zotero_db_path: str) -> MinerUChildNote:
    attachment_item_id = int(row.get("zotero_attachment_item_id") or 0)
    if attachment_item_id <= 0:
        raise RuntimeError("Attachment row is missing zotero_attachment_item_id; cannot resolve MinerU child note.")

    db_path = resolve_input_path(zotero_db_path)
    if not db_path.exists():
        raise RuntimeError(f"Zotero DB not found: {db_path}")

    uri = f"file:{db_path}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        note_rows = conn.execute(
            """
            SELECT n.itemID AS note_item_id, i.key AS note_item_key, n.note AS note_html
            FROM itemNotes n
            JOIN items i ON i.itemID = n.itemID
            WHERE n.parentItemID = ?
            ORDER BY n.itemID ASC
            """,
            (attachment_item_id,),
        ).fetchall()
        if not note_rows:
            raise RuntimeError(
                f"Missing MinerU child note for attachment itemID={attachment_item_id}; item is not ingestible in note-first mode."
            )

        titles = _lookup_note_titles(conn, [int(r["note_item_id"]) for r in note_rows if r["note_item_id"] is not None])
        for note_row in note_rows:
            note_item_id = int(note_row["note_item_id"])
            note_item_key = str(note_row["note_item_key"] or "").strip()
            if not note_item_key:
                continue
            note_title = titles.get(note_item_id)
            markdown_text = _extract_text_from_zotero_note(str(note_row["note_html"] or ""))
            if not _looks_like_mineru_markdown(note_title, markdown_text):
                continue
            source_hash = hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()
            return MinerUChildNote(
                attachment_item_id=attachment_item_id,
                attachment_key=str(row.get("zotero_attachment_key") or "").strip() or None,
                parent_item_key=str(row.get("zotero_item_key") or "").strip() or None,
                note_item_id=note_item_id,
                note_item_key=note_item_key,
                note_title=note_title,
                markdown_text=markdown_text,
                source_hash=source_hash,
            )
    finally:
        conn.close()

    raise RuntimeError(
        f"Malformed or non-MinerU child note for attachment itemID={attachment_item_id}; item is not ingestible in note-first mode."
    )
