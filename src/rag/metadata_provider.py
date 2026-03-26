from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any
import unicodedata

from .path_utils import resolve_input_path
from .paperpile_metadata import find_metadata_for_pdf as paperpile_find_metadata_for_pdf
from .paperpile_metadata import iter_pdf_files
from .paperpile_metadata import load_paperpile_index
from .paperpile_metadata import normalize_filename_key
from .zotero_metadata import load_zotero_entries


@dataclass
class MetadataIndex:
    backend: str
    by_basename: dict[str, dict[str, Any]]
    by_normalized: dict[str, dict[str, Any]]
    by_path_normalized: dict[str, dict[str, Any]]


def _score(meta: dict[str, Any]) -> int:
    keys = [
        "title",
        "year",
        "citekey",
        "paperpile_id",
        "doi",
        "journal",
        "publisher",
        "zotero_item_key",
        "zotero_attachment_key",
    ]
    return sum(1 for k in keys if meta.get(k)) + len(meta.get("authors") or [])


def _norm_path(path_str: str | None) -> str:
    raw = (path_str or "").strip()
    if not raw:
        return ""
    # Normalize cross-platform path separators and case for lookup only.
    return str(Path(raw)).replace("\\", "/").lower()


def _build_index(backend: str, entries: list[dict[str, Any]]) -> MetadataIndex:
    by_basename: dict[str, dict[str, Any]] = {}
    by_normalized: dict[str, dict[str, Any]] = {}
    by_path_normalized: dict[str, dict[str, Any]] = {}

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        meta = dict(entry)

        attach_path = (meta.get("attachment_path") or "").strip()
        basename = Path(attach_path).name if attach_path else ""
        if not basename:
            raw = (meta.get("attachment_path_raw") or "").strip()
            if raw:
                basename = Path(raw.split(":", 1)[-1]).name

        if basename:
            key = basename.lower()
            existing = by_basename.get(key)
            if existing is None or _score(meta) > _score(existing):
                by_basename[key] = meta

            nkey = normalize_filename_key(basename)
            if nkey:
                existing_n = by_normalized.get(nkey)
                if existing_n is None or _score(meta) > _score(existing_n):
                    by_normalized[nkey] = meta

        pkey = _norm_path(attach_path)
        if pkey:
            existing_p = by_path_normalized.get(pkey)
            if existing_p is None or _score(meta) > _score(existing_p):
                by_path_normalized[pkey] = meta

    return MetadataIndex(
        backend=backend,
        by_basename=by_basename,
        by_normalized=by_normalized,
        by_path_normalized=by_path_normalized,
    )


def _paperpile_entries(path: str) -> list[dict[str, Any]]:
    # Reuse existing attachment->metadata logic, but convert to entry list.
    index = load_paperpile_index(path)
    out: list[dict[str, Any]] = []
    for key, meta in index.items():
        if key.startswith("norm::"):
            continue
        item = dict(meta)
        item["attachment_path"] = key
        item["metadata_source"] = "paperpile"
        out.append(item)
    return out


def _discover_zotero_db_path() -> str:
    candidates: list[Path] = [Path.home() / "Zotero" / "zotero.sqlite"]
    user = os.getenv("USER", "").strip()
    if user:
        candidates.append(Path("/mnt/c/Users") / user / "Zotero" / "zotero.sqlite")
    try:
        candidates.extend(sorted(Path("/mnt/c/Users").glob("*/Zotero/zotero.sqlite")))
    except Exception:
        pass
    for p in candidates:
        try:
            if p.exists():
                return str(p)
        except Exception:
            continue
    return ""


def _resolved_zotero_paths(settings) -> tuple[str, str]:
    raw_db = (settings.zotero_db_path or "").strip()
    if raw_db:
        db = str(resolve_input_path(raw_db))
    else:
        db = _discover_zotero_db_path()

    raw_storage = (settings.zotero_storage_root or "").strip()
    if raw_storage:
        storage = str(resolve_input_path(raw_storage))
    elif db:
        storage = str(Path(db).parent / "storage")
    else:
        storage = ""
    return db, storage


def load_metadata_index(settings, backend_override: str | None = None) -> MetadataIndex:
    backend = (backend_override or settings.metadata_backend or "zotero").strip().lower()
    if backend == "paperpile":
        return _build_index("paperpile", _paperpile_entries(settings.paperpile_json))

    db_path, storage_root = _resolved_zotero_paths(settings)
    if not db_path:
        # Preserve prior behavior when no Zotero DB is available.
        return _build_index("paperpile", _paperpile_entries(settings.paperpile_json))
    entries = load_zotero_entries(db_path, storage_root)
    return _build_index("zotero", entries)


def find_metadata_for_pdf(index: MetadataIndex, filename: str, path_hint: str | None = None) -> dict[str, Any] | None:
    if index.backend == "paperpile":
        # Preserve original matching behavior.
        found = paperpile_find_metadata_for_pdf(index.by_basename, filename)
        if found:
            out = dict(found)
            out.setdefault("metadata_source", "paperpile")
            return out
        return None

    pkey = _norm_path(path_hint)
    if pkey:
        path_match = index.by_path_normalized.get(pkey)
        if path_match:
            return dict(path_match)

    base = Path(filename).name.lower()
    direct = index.by_basename.get(base)
    if direct:
        return dict(direct)

    nkey = normalize_filename_key(base)
    if nkey:
        norm = index.by_normalized.get(nkey)
        if norm:
            return dict(norm)

    return None


def find_unmatched_pdfs(pdf_root: str | Path, metadata_index: MetadataIndex) -> list[Path]:
    return [p for p in iter_pdf_files(pdf_root) if not find_metadata_for_pdf(metadata_index, p.name, str(p))]


def metadata_title_year_key(meta: dict[str, Any] | None) -> str | None:
    if not meta:
        return None
    title = (meta.get("title") or "").strip()
    year = meta.get("year")
    if not title or year is None:
        return None
    # Fold accents/diacritics so equivalent titles compare as the same key.
    folded = unicodedata.normalize("NFKD", title)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    ntitle = " ".join(re.findall(r"[a-z0-9]+", folded.lower())).strip()
    if not ntitle:
        return None
    try:
        y = int(str(year))
    except Exception:
        return None
    return f"{ntitle}|{y}"
