from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .path_utils import resolve_input_path

OCR_SUFFIX = ".ocr.txt"
REFERENCES_SUFFIX = ".references.txt"
ATTACHMENT_ITEM_TYPE_ID = 3
TITLE_FIELD_NAME = "title"
TEXT_PLAIN = "text/plain"


def _utc_now_sql() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat(sep=" ")


def _epoch_ms(path: Path) -> int:
    return int(path.stat().st_mtime_ns // 1_000_000)


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sidecar_name(pdf_path: Path, suffix: str) -> str:
    return f"{pdf_path.stem}{suffix}"


def _storage_root(settings: Settings) -> Path:
    raw = (settings.zotero_storage_root or "").strip()
    if not raw:
        raise RuntimeError("ZOTERO_STORAGE_ROOT is not configured; cannot manage Zotero sidecar attachments.")
    root = resolve_input_path(raw)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _db_path(settings: Settings) -> Path:
    raw = (settings.zotero_db_path or "").strip()
    if not raw:
        raise RuntimeError("ZOTERO_DB_PATH is not configured; cannot manage Zotero sidecar attachments.")
    db = resolve_input_path(raw)
    if not db.exists():
        raise RuntimeError(f"Zotero DB not found: {db}")
    return db


def _connect_rw(settings: Settings) -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path(settings)), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _lookup_field_id(conn: sqlite3.Connection, field_name: str) -> int:
    for table in ("fieldsCombined", "fields"):
        try:
            row = conn.execute(f"SELECT fieldID FROM {table} WHERE fieldName=? LIMIT 1", (field_name,)).fetchone()
        except sqlite3.OperationalError:
            row = None
        if row and row[0] is not None:
            return int(row[0])
    raise RuntimeError(f"Could not find fieldID for Zotero field {field_name!r}")


def _find_parent_row(conn: sqlite3.Connection, metadata: dict[str, Any]) -> sqlite3.Row | None:
    item_key = str(metadata.get("zotero_item_key") or "").strip()
    attachment_key = str(metadata.get("zotero_attachment_key") or "").strip()
    if item_key:
        row = conn.execute("SELECT itemID, libraryID, key FROM items WHERE key=? LIMIT 1", (item_key,)).fetchone()
        if row:
            return row
    if attachment_key:
        row = conn.execute(
            """
            SELECT p.itemID, p.libraryID, p.key
            FROM itemAttachments ia
            JOIN items a ON a.itemID = ia.itemID
            JOIN items p ON p.itemID = ia.parentItemID
            WHERE a.key=?
            LIMIT 1
            """,
            (attachment_key,),
        ).fetchone()
        if row:
            return row
    return None


def _iter_child_attachments(conn: sqlite3.Connection, parent_item_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT i.itemID, i.key, i.libraryID, ia.path, ia.contentType
        FROM itemAttachments ia
        JOIN items i ON i.itemID = ia.itemID
        WHERE ia.parentItemID=?
        ORDER BY ia.itemID ASC
        """,
        (parent_item_id,),
    ).fetchall()


def _resolve_storage_path(storage_root: Path, attachment_key: str, path_raw: str | None) -> Path | None:
    raw = (path_raw or "").strip()
    if not raw:
        return None
    if raw.lower().startswith("storage:"):
        rel = raw.split(":", 1)[1].strip().lstrip("/\\")
        return storage_root / attachment_key / rel
    return resolve_input_path(raw)


def find_attached_sidecar_path(pdf_path: Path, metadata: dict[str, Any] | None, settings: Settings, suffix: str) -> Path | None:
    if not metadata:
        return None
    conn = _connect_rw(settings)
    storage_root = _storage_root(settings)
    filename = _sidecar_name(pdf_path, suffix)
    try:
        parent = _find_parent_row(conn, metadata)
        if not parent:
            return None
        for row in _iter_child_attachments(conn, int(parent["itemID"])):
            candidate = _resolve_storage_path(storage_root, str(row["key"]), row["path"])
            if candidate is None:
                continue
            if candidate.name != filename:
                continue
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        return None
    finally:
        conn.close()


def _generate_attachment_key(conn: sqlite3.Connection) -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    for _ in range(200):
        key = "".join(secrets.choice(alphabet) for _ in range(8))
        row = conn.execute("SELECT 1 FROM items WHERE key=? LIMIT 1", (key,)).fetchone()
        if not row:
            return key
    raise RuntimeError("Unable to generate unique Zotero attachment key.")


def _write_item_title(conn: sqlite3.Connection, item_id: int, title: str) -> None:
    field_id = _lookup_field_id(conn, TITLE_FIELD_NAME)
    row = conn.execute("SELECT valueID FROM itemDataValues WHERE value=? LIMIT 1", (title,)).fetchone()
    if row:
        value_id = int(row[0])
    else:
        cur = conn.execute("INSERT INTO itemDataValues(value) VALUES (?)", (title,))
        value_id = int(cur.lastrowid)
    conn.execute("INSERT INTO itemData(itemID, fieldID, valueID) VALUES (?, ?, ?)", (item_id, field_id, value_id))


def attach_sidecar_to_zotero(pdf_path: Path, metadata: dict[str, Any], settings: Settings, source_path: Path, suffix: str) -> Path:
    source = source_path.resolve()
    if not source.exists() or not source.is_file():
        raise RuntimeError(f"Sidecar source file does not exist: {source}")
    conn = _connect_rw(settings)
    storage_root = _storage_root(settings)
    filename = _sidecar_name(pdf_path, suffix)
    try:
        parent = _find_parent_row(conn, metadata)
        if not parent:
            raise RuntimeError("Could not locate Zotero parent item for sidecar attachment.")
        existing = find_attached_sidecar_path(pdf_path, metadata, settings, suffix)
        if existing is not None:
            return existing

        key = _generate_attachment_key(conn)
        target_dir = storage_root / key
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename
        shutil.copy2(source, target_path)

        now = _utc_now_sql()
        cur = conn.execute(
            "INSERT INTO items(itemTypeID, dateAdded, dateModified, clientDateModified, libraryID, key, version, synced) VALUES (?, ?, ?, ?, ?, ?, 0, 0)",
            (ATTACHMENT_ITEM_TYPE_ID, now, now, now, int(parent["libraryID"]), key),
        )
        item_id = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO itemAttachments(itemID, parentItemID, linkMode, contentType, path, syncState, storageModTime, storageHash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, int(parent["itemID"]), 0, TEXT_PLAIN, f"storage:{filename}", 0, _epoch_ms(target_path), _md5(target_path)),
        )
        _write_item_title(conn, item_id, filename)
        conn.commit()
        if not target_path.exists():
            raise RuntimeError(f"Attached sidecar file missing after Zotero write: {target_path}")
        return target_path.resolve()
    finally:
        conn.close()


def _locate_local_ocr_text(pdf_path: Path, settings: Settings) -> Path | None:
    from .text_acquisition import locate_ocr_text

    path = locate_ocr_text(pdf_path, settings)
    if path and path.exists() and path.is_file():
        return path.resolve()
    return None


def _generate_cpu_ocr_text(pdf_path: Path, settings: Settings) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "reocr_pdfs_paddleocr.py"
    if not script_path.exists():
        raise RuntimeError(f"Missing OCR helper script: {script_path}")

    python_bin = Path(sys.executable).resolve()
    if not python_bin.exists():
        python_bin = Path(os.environ.get("PYTHON_BIN") or shutil.which("python3") or "python3")

    with tempfile.TemporaryDirectory(prefix="zotero_ocr_attach_") as temp_dir:
        tmp_root = Path(temp_dir)
        summary_dir = tmp_root / "summaries"
        env = os.environ.copy()
        env["DISABLE_MODEL_SOURCE_CHECK"] = "True"
        env["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        cmd = [
            str(python_bin),
            str(script_path),
            "--pdf-dir",
            str(pdf_path.parent),
            "--output-dir",
            str(tmp_root),
            "--summary-dir",
            str(summary_dir),
            "--backend",
            "paddleocr-classic",
            "--device",
            "cpu",
            "--limit",
            "1",
            "--overwrite",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1800)
        summary_path = summary_dir / "task_0000.json"
        if not summary_path.exists():
            raise RuntimeError(
                f"OCR helper did not produce a summary for {pdf_path.name}. stdout={proc.stdout[-1200:]} stderr={proc.stderr[-1200:]}"
            )
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        results = summary.get("results") or []
        ok_entry = next((r for r in results if Path(str(r.get("pdf") or "")).name == pdf_path.name), None)
        if proc.returncode != 0:
            raise RuntimeError(
                f"OCR helper failed for {pdf_path.name}. rc={proc.returncode} stdout={proc.stdout[-1200:]} stderr={proc.stderr[-1200:]}"
            )
        if not ok_entry or ok_entry.get("status") != "ok":
            raise RuntimeError(
                f"Failed to generate OCR text for {pdf_path.name} with PaddleOCR CPU. Summary entry: {ok_entry!r}"
            )
        generated = tmp_root / "text" / f"{pdf_path.stem}.txt"
        if not generated.exists():
            raise RuntimeError(f"OCR helper reported success but no text file was created for {pdf_path.name}.")
        stable = tmp_root / _sidecar_name(pdf_path, OCR_SUFFIX)
        shutil.copy2(generated, stable)
        return stable.resolve()


def ensure_zotero_ocr_text_attachment(pdf_path: Path, metadata: dict[str, Any] | None, settings: Settings) -> Path | None:
    if not metadata or not str(metadata.get("zotero_persistent_id") or "").strip():
        return None
    existing = find_attached_sidecar_path(pdf_path, metadata, settings, OCR_SUFFIX)
    if existing is not None:
        return existing
    local = _locate_local_ocr_text(pdf_path, settings)
    source = local if local is not None else _generate_cpu_ocr_text(pdf_path, settings)
    attached = attach_sidecar_to_zotero(pdf_path, metadata, settings, source, OCR_SUFFIX)
    verified = find_attached_sidecar_path(pdf_path, metadata, settings, OCR_SUFFIX)
    if verified is None:
        raise RuntimeError(f"OCR attachment verification failed for {pdf_path.name}; stopping ingest.")
    return verified


def _generate_references_text_from_ocr(pdf_path: Path, ocr_text_path: Path, settings: Settings) -> Path:
    from .qwen_structured_refs import detect_section_plan_details, _reference_block_text, split_reference_strings_for_anystyle
    from .qwen_structured_refs import _extract_lines_with_page_from_ocr_text, _write_references_sidecar

    lines_with_page = _extract_lines_with_page_from_ocr_text(ocr_text_path)
    lines = [line for _, line in lines_with_page]
    _headings, sections, _ = detect_section_plan_details(lines, settings=settings)
    reference_strings: list[str] = []
    for section in sections:
        if section.kind != "references":
            continue
        block = _reference_block_text(lines, section, settings=settings)
        if block:
            reference_strings.extend(split_reference_strings_for_anystyle(block, settings=settings))
    if not reference_strings:
        raise RuntimeError(f"Failed to derive any reference lines from OCR text for {pdf_path.name}.")
    sidecar = _write_references_sidecar(pdf_path, reference_strings)
    if sidecar is None or not sidecar.exists():
        raise RuntimeError(f"Failed to write references sidecar for {pdf_path.name}.")
    return sidecar.resolve()


def ensure_zotero_references_attachment(pdf_path: Path, metadata: dict[str, Any] | None, settings: Settings, ocr_text_path: Path | None) -> Path | None:
    if not metadata or not str(metadata.get("zotero_persistent_id") or "").strip():
        return None
    existing = find_attached_sidecar_path(pdf_path, metadata, settings, REFERENCES_SUFFIX)
    if existing is not None:
        return existing

    if ocr_text_path is None or not ocr_text_path.exists():
        raise RuntimeError(f"OCR text is missing for {pdf_path.name}; cannot generate references sidecar.")
    source = _generate_references_text_from_ocr(pdf_path, ocr_text_path, settings)

    attached = attach_sidecar_to_zotero(pdf_path, metadata, settings, source, REFERENCES_SUFFIX)
    verified = find_attached_sidecar_path(pdf_path, metadata, settings, REFERENCES_SUFFIX)
    if verified is None:
        raise RuntimeError(f"References attachment verification failed for {pdf_path.name}; stopping ingest.")
    return verified


def prepare_zotero_sidecars(pdf_path: Path, metadata: dict[str, Any] | None, settings: Settings) -> dict[str, Any] | None:
    if not metadata:
        return metadata
    out = dict(metadata)
    if not str(out.get("zotero_persistent_id") or "").strip():
        return out

    ocr_path = ensure_zotero_ocr_text_attachment(pdf_path, out, settings)
    if ocr_path is not None:
        out["zotero_ocr_text_path"] = str(ocr_path)
        out["zotero_ocr_text_mtime_ns"] = ocr_path.stat().st_mtime_ns

    refs_path = ensure_zotero_references_attachment(pdf_path, out, settings, ocr_path)
    if refs_path is not None:
        out["zotero_references_path"] = str(refs_path)
        out["zotero_references_mtime_ns"] = refs_path.stat().st_mtime_ns

    return out
