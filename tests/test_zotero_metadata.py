import sqlite3
from pathlib import Path

from src.rag.zotero_metadata import load_zotero_entries


def _build_zotero_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT);
            CREATE TABLE itemAttachments (
                itemID INTEGER PRIMARY KEY,
                parentItemID INTEGER,
                path TEXT,
                contentType TEXT
            );
            CREATE TABLE itemData (
                itemID INTEGER,
                fieldID INTEGER,
                valueID INTEGER
            );
            CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
            CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
            CREATE TABLE itemCreators (itemID INTEGER, creatorID INTEGER, orderIndex INTEGER);
            CREATE TABLE creators (creatorID INTEGER PRIMARY KEY, creatorDataID INTEGER);
            CREATE TABLE creatorData (creatorDataID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT);
            """
        )

        conn.execute("INSERT INTO items(itemID, key) VALUES (1, 'PARENT1')")
        conn.execute("INSERT INTO items(itemID, key) VALUES (2, 'ATTACH1')")
        conn.execute("INSERT INTO items(itemID, key) VALUES (3, 'ATTACH2')")
        conn.execute(
            "INSERT INTO itemAttachments(itemID, parentItemID, path, contentType) VALUES (2, 1, 'storage:paper.pdf', 'application/pdf')"
        )
        conn.execute(
            "INSERT INTO itemAttachments(itemID, parentItemID, path, contentType) VALUES (3, 1, 'storage:manifest', 'application/pdf')"
        )

        conn.execute("INSERT INTO fields(fieldID, fieldName) VALUES (1, 'title')")
        conn.execute("INSERT INTO fields(fieldID, fieldName) VALUES (2, 'DOI')")
        conn.execute("INSERT INTO fields(fieldID, fieldName) VALUES (3, 'date')")
        conn.execute("INSERT INTO fields(fieldID, fieldName) VALUES (4, 'publicationTitle')")
        conn.execute("INSERT INTO fields(fieldID, fieldName) VALUES (5, 'publisher')")

        conn.execute("INSERT INTO itemDataValues(valueID, value) VALUES (1, 'Example Zotero Paper')")
        conn.execute("INSERT INTO itemDataValues(valueID, value) VALUES (2, '10.1000/XYZ')")
        conn.execute("INSERT INTO itemDataValues(valueID, value) VALUES (3, '2021-02-03')")
        conn.execute("INSERT INTO itemDataValues(valueID, value) VALUES (4, 'Journal X')")
        conn.execute("INSERT INTO itemDataValues(valueID, value) VALUES (5, 'Publisher Y')")

        conn.execute("INSERT INTO itemData(itemID, fieldID, valueID) VALUES (1, 1, 1)")
        conn.execute("INSERT INTO itemData(itemID, fieldID, valueID) VALUES (1, 2, 2)")
        conn.execute("INSERT INTO itemData(itemID, fieldID, valueID) VALUES (1, 3, 3)")
        conn.execute("INSERT INTO itemData(itemID, fieldID, valueID) VALUES (1, 4, 4)")
        conn.execute("INSERT INTO itemData(itemID, fieldID, valueID) VALUES (1, 5, 5)")

        conn.execute("INSERT INTO creatorData(creatorDataID, firstName, lastName) VALUES (1, 'Jane', 'Doe')")
        conn.execute("INSERT INTO creators(creatorID, creatorDataID) VALUES (1, 1)")
        conn.execute("INSERT INTO itemCreators(itemID, creatorID, orderIndex) VALUES (1, 1, 0)")
        conn.commit()
    finally:
        conn.close()


def test_load_zotero_entries_reads_basic_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / 'zotero.sqlite'
    _build_zotero_db(db_path)

    entries = load_zotero_entries(str(db_path), storage_root=str(tmp_path / 'storage'))
    assert len(entries) == 1
    row = entries[0]
    assert row['title'] == 'Example Zotero Paper'
    assert row['doi'] == '10.1000/XYZ'
    assert row['year'] == 2021
    assert row['journal'] == 'Journal X'
    assert row['publisher'] == 'Publisher Y'
    assert row['zotero_item_key'] == 'PARENT1'
    assert row['zotero_attachment_key'] == 'ATTACH1'
    assert row['authors'] == ['Jane Doe']
    assert row['attachment_path'].endswith('storage/ATTACH1/paper.pdf')


def test_load_zotero_entries_excludes_non_pdf_storage_artifacts(tmp_path: Path) -> None:
    db_path = tmp_path / 'zotero.sqlite'
    _build_zotero_db(db_path)

    entries = load_zotero_entries(str(db_path), storage_root=str(tmp_path / 'storage'))
    assert len(entries) == 1
    assert entries[0]['attachment_path_raw'] == 'storage:paper.pdf'
