from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.rag.zotero_notes import load_mineru_child_note_for_attachment
from src.rag.zotero_notes import summarize_mineru_notes_for_rows


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT);
            CREATE TABLE itemNotes (itemID INTEGER PRIMARY KEY, parentItemID INTEGER, note TEXT);
            CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
            CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
            CREATE TABLE itemData (itemID INTEGER, fieldID INTEGER, valueID INTEGER);
            """
        )
        conn.execute("INSERT INTO fields(fieldID, fieldName) VALUES (1, 'title')")
        conn.execute("INSERT INTO items(itemID, key) VALUES (10, 'ATTACHKEY')")
        conn.execute("INSERT INTO items(itemID, key) VALUES (11, 'NOTEKEY')")
        conn.execute(
            "INSERT INTO itemNotes(itemID, parentItemID, note) VALUES (11, 10, ?)",
            ("<p># Intro</p><p>- bullet</p><p>| h | v |</p><p>" + ("body text " * 40) + "</p>",),
        )
        conn.execute("INSERT INTO itemDataValues(valueID, value) VALUES (1, 'MinerU Markdown Note')")
        conn.execute("INSERT INTO itemData(itemID, fieldID, valueID) VALUES (11, 1, 1)")
        conn.commit()
    finally:
        conn.close()


def test_load_mineru_child_note_for_attachment_success(tmp_path: Path) -> None:
    db = tmp_path / "zotero.sqlite"
    _init_db(db)
    row = {"zotero_attachment_item_id": 10, "zotero_attachment_key": "ATTACHKEY", "zotero_item_key": "PARENTKEY"}
    note = load_mineru_child_note_for_attachment(row, zotero_db_path=str(db))
    assert note.note_item_key == "NOTEKEY"
    assert note.note_title == "MinerU Markdown Note"
    assert "# Intro" in note.markdown_text
    assert note.source_hash


def test_load_mineru_child_note_for_attachment_missing_note_hard_failure(tmp_path: Path) -> None:
    db = tmp_path / "zotero.sqlite"
    _init_db(db)
    row = {"zotero_attachment_item_id": 999}
    with pytest.raises(RuntimeError, match="Missing MinerU child note"):
        load_mineru_child_note_for_attachment(row, zotero_db_path=str(db))


def test_load_mineru_child_note_for_attachment_malformed_note_hard_failure(tmp_path: Path) -> None:
    db = tmp_path / "zotero.sqlite"
    _init_db(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute("UPDATE itemDataValues SET value='Random Note' WHERE valueID=1")
        conn.execute("UPDATE itemNotes SET note='<p>plain text</p>' WHERE itemID=11")
        conn.commit()
    finally:
        conn.close()
    row = {"zotero_attachment_item_id": 10}
    with pytest.raises(RuntimeError, match="Malformed or non-MinerU child note"):
        load_mineru_child_note_for_attachment(row, zotero_db_path=str(db))


def test_load_mineru_child_note_for_parent_item_with_body_marker(tmp_path: Path) -> None:
    db = tmp_path / "zotero.sqlite"
    conn = sqlite3.connect(db)
    try:
        conn.executescript(
            """
            CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT);
            CREATE TABLE itemNotes (itemID INTEGER PRIMARY KEY, parentItemID INTEGER, note TEXT);
            CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
            CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
            CREATE TABLE itemData (itemID INTEGER, fieldID INTEGER, valueID INTEGER);
            """
        )
        conn.execute("INSERT INTO fields(fieldID, fieldName) VALUES (1, 'title')")
        conn.execute("INSERT INTO items(itemID, key) VALUES (20, 'PARENTKEY')")
        conn.execute("INSERT INTO items(itemID, key) VALUES (21, 'ATTACHKEY')")
        conn.execute("INSERT INTO items(itemID, key) VALUES (22, 'NOTEKEY')")
        note_body = (
            "<p>LLM_FOR_ZOTERO_MINERU_NOTE_V1</p>"
            "<p>attachment_id=21</p>"
            "<p>parent_item_id=20</p>"
            "<p># Abstract</p>"
            f"<p>{'body text ' * 40}</p>"
            "<p>- bullet</p>"
            "<p>| h | v |</p>"
        )
        conn.execute(
            "INSERT INTO itemNotes(itemID, parentItemID, note) VALUES (22, 20, ?)",
            (note_body,),
        )
        conn.execute("INSERT INTO itemDataValues(valueID, value) VALUES (1, 'Child Note')")
        conn.execute("INSERT INTO itemData(itemID, fieldID, valueID) VALUES (22, 1, 1)")
        conn.commit()
    finally:
        conn.close()
    row = {
        "zotero_attachment_item_id": 21,
        "zotero_parent_item_id": 20,
        "zotero_attachment_key": "ATTACHKEY",
        "zotero_item_key": "PARENTKEY",
    }
    note = load_mineru_child_note_for_attachment(row, zotero_db_path=str(db))
    assert note.note_item_key == "NOTEKEY"
    assert "LLM_FOR_ZOTERO_MINERU_NOTE_V1" in note.markdown_text


def test_summarize_mineru_notes_for_rows_counts_attached_notes(tmp_path: Path) -> None:
    db = tmp_path / "zotero.sqlite"
    _init_db(db)
    rows = [
        {"zotero_attachment_item_id": 10, "zotero_attachment_key": "ATTACHKEY", "zotero_item_key": "PARENTKEY"},
        {"zotero_attachment_item_id": 999, "zotero_attachment_key": "OTHERATTACH", "zotero_item_key": "OTHERPARENT"},
    ]

    summary = summarize_mineru_notes_for_rows(rows, zotero_db_path=str(db))

    assert summary["rows_checked"] == 2
    assert summary["attachments_checked"] == 2
    assert summary["mineru_notes_attached"] == 1
    assert summary["mineru_notes_missing"] == 1
