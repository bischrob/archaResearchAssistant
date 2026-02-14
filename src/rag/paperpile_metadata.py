from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path


def _normalize_author(author: dict) -> str:
    formatted = (author.get("formatted") or "").strip()
    if formatted:
        return formatted
    first = (author.get("first") or "").strip()
    last = (author.get("last") or "").strip()
    full = f"{first} {last}".strip()
    return full or "Unknown Author"


def _extract_year(record: dict) -> int | None:
    published = record.get("published")
    if isinstance(published, dict):
        year_raw = published.get("year")
        try:
            return int(str(year_raw))
        except Exception:
            return None
    year_raw = record.get("year")
    try:
        return int(str(year_raw))
    except Exception:
        return None


def _score(meta: dict) -> int:
    keys = ["title", "year", "citekey", "paperpile_id", "doi", "journal", "publisher"]
    return sum(1 for k in keys if meta.get(k)) + len(meta.get("authors") or [])


def normalize_filename_key(filename: str) -> str:
    base = Path(filename).name
    stem = Path(base).stem
    norm = unicodedata.normalize("NFKD", stem)
    norm = "".join(ch for ch in norm if not unicodedata.combining(ch))
    norm = norm.casefold()
    norm = re.sub(r"[^a-z0-9]+", "", norm)
    return norm


def load_paperpile_index(paperpile_json_path: str) -> dict[str, dict]:
    path = Path(paperpile_json_path)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return {}

    by_basename: dict[str, dict] = {}
    by_normalized: dict[str, dict] = {}
    for record in data:
        if not isinstance(record, dict):
            continue
        attachments = record.get("attachments") or []
        if not isinstance(attachments, list):
            continue

        authors_raw = record.get("author") or []
        authors = []
        if isinstance(authors_raw, list):
            authors = [_normalize_author(a) for a in authors_raw if isinstance(a, dict)]
        authors = [a for a in authors if a]

        meta = {
            "title": (record.get("title") or "").strip() or None,
            "year": _extract_year(record),
            "citekey": (record.get("citekey") or "").strip() or None,
            "paperpile_id": (record.get("_id") or "").strip() or None,
            "doi": (record.get("doi") or "").strip() or None,
            "journal": (record.get("journal") or record.get("journalfull") or "").strip() or None,
            "publisher": (record.get("publisher") or "").strip() or None,
            "authors": authors,
        }

        for att in attachments:
            if not isinstance(att, dict):
                continue
            filename = (att.get("filename") or "").strip()
            if not filename:
                continue
            basename = Path(filename).name
            if not basename:
                continue
            key = basename.lower()
            existing = by_basename.get(key)
            if existing is None or _score(meta) > _score(existing):
                by_basename[key] = dict(meta)

            nkey = normalize_filename_key(basename)
            if nkey:
                existing_n = by_normalized.get(nkey)
                if existing_n is None or _score(meta) > _score(existing_n):
                    by_normalized[nkey] = dict(meta)

    # Keep exact basename keys plus normalized aliases.
    for nkey, meta in by_normalized.items():
        by_basename[f"norm::{nkey}"] = meta
    return by_basename


def find_metadata_for_pdf(index: dict[str, dict], filename: str) -> dict | None:
    base = Path(filename).name.lower()
    meta = index.get(base)
    if meta:
        return meta
    nkey = normalize_filename_key(base)
    if not nkey:
        return None
    return index.get(f"norm::{nkey}")
