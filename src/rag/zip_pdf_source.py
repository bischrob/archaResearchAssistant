from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from pathlib import PurePosixPath


def _safe_member_parts(member_name: str) -> list[str]:
    parts = []
    for part in PurePosixPath(member_name).parts:
        if not part or part in {".", ".."}:
            continue
        if part.startswith("/"):
            continue
        parts.append(part)
    return parts


def _zip_signature(zip_path: Path) -> str:
    st = zip_path.stat()
    raw = f"{zip_path.resolve()}::{st.st_mtime_ns}::{st.st_size}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _zip_cache_dir(cache_root: Path, zip_path: Path) -> Path:
    raw = str(zip_path.resolve())
    zip_id = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return cache_root / zip_id


def _read_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def materialize_zip_pdfs(
    source_root: Path,
    cache_root: Path,
    progress_cb=None,
) -> tuple[list[Path], dict]:
    zip_files = sorted(
        [p for p in source_root.rglob("*") if p.is_file() and p.suffix.lower() == ".zip"],
        key=lambda p: str(p).lower(),
    )

    cache_root.mkdir(parents=True, exist_ok=True)

    extracted_pdfs: list[Path] = []
    zip_count = len(zip_files)
    extracted_members = 0
    skipped_unchanged = 0
    failed_zips: list[dict] = []

    for idx, zip_path in enumerate(zip_files, start=1):
        if progress_cb:
            progress_cb(idx, zip_count, f"Inspecting ZIP {idx}/{zip_count}: {zip_path.name}")

        zip_sig = _zip_signature(zip_path)
        zcache = _zip_cache_dir(cache_root, zip_path)
        manifest_path = zcache / ".manifest.json"
        manifest = _read_manifest(manifest_path)

        if manifest.get("signature") == zip_sig and manifest.get("pdf_members"):
            members = [zcache / rel for rel in manifest["pdf_members"]]
            extracted_pdfs.extend([p for p in members if p.exists()])
            skipped_unchanged += 1
            continue

        if zcache.exists():
            shutil.rmtree(zcache, ignore_errors=True)
        zcache.mkdir(parents=True, exist_ok=True)

        pdf_members: list[str] = []
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    if not member.filename.lower().endswith(".pdf"):
                        continue
                    safe_parts = _safe_member_parts(member.filename)
                    if not safe_parts:
                        continue
                    target = zcache.joinpath(*safe_parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member, "r") as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    pdf_members.append(str(Path(*safe_parts)))
                    extracted_pdfs.append(target)
                    extracted_members += 1
        except Exception as exc:
            failed_zips.append({"zip": str(zip_path), "error": str(exc)})
            continue

        _write_manifest(
            manifest_path,
            {
                "source_zip": str(zip_path),
                "signature": zip_sig,
                "pdf_members": pdf_members,
            },
        )

    return extracted_pdfs, {
        "zip_files_total": zip_count,
        "zip_files_unchanged": skipped_unchanged,
        "zip_extract_failures": failed_zips,
        "zip_pdf_members_extracted": extracted_members,
        "zip_cache_dir": str(cache_root),
    }


def collect_source_pdfs(
    source_root: Path,
    cache_root: Path,
    include_zip: bool = True,
    progress_cb=None,
) -> tuple[list[Path], dict]:
    direct_pdfs = sorted(
        [p for p in source_root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"],
        key=lambda p: str(p).lower(),
    )

    if not include_zip:
        return direct_pdfs, {
            "direct_pdf_count": len(direct_pdfs),
            "zip_enabled": False,
            "zip_files_total": 0,
            "zip_files_unchanged": 0,
            "zip_extract_failures": [],
            "zip_pdf_members_extracted": 0,
            "zip_cache_dir": str(cache_root),
        }

    zip_pdfs, zip_stats = materialize_zip_pdfs(source_root, cache_root, progress_cb=progress_cb)
    combined = sorted({str(p): p for p in [*direct_pdfs, *zip_pdfs]}.values(), key=lambda p: str(p).lower())
    return combined, {
        "direct_pdf_count": len(direct_pdfs),
        "zip_enabled": True,
        **zip_stats,
        "total_pdf_candidates": len(combined),
    }

