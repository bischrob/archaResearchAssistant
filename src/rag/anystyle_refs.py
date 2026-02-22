from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Any

from .pdf_processing import Citation, normalize_title


YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _string_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    out.append(cleaned)
        return out
    return []


def _extract_year(entry: dict[str, Any]) -> int | None:
    candidates = _string_values(entry.get("date")) + _string_values(entry.get("year"))
    text = " ".join(candidates)
    match = YEAR_RE.search(text)
    if not match:
        return None
    return int(match.group(0))


def _extract_title(entry: dict[str, Any]) -> str:
    for key in ("title", "container-title", "note"):
        values = _string_values(entry.get(key))
        if values:
            return values[0]
    return ""


def _extract_doi(entry: dict[str, Any]) -> str | None:
    for key in ("DOI", "doi"):
        values = _string_values(entry.get(key))
        if values:
            doi = values[0].strip().rstrip(".;,")
            return doi or None
    haystack = " ".join(
        _string_values(entry.get("note")) + _string_values(entry.get("title")) + _string_values(entry.get("container-title"))
    )
    match = DOI_RE.search(haystack)
    if not match:
        return None
    return match.group(0).rstrip(".;,")


def _extract_author_tokens(entry: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key in ("author", "editor", "translator"):
        values = entry.get(key)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict):
                family = (item.get("family") or "").strip()
                literal = (item.get("literal") or "").strip()
                candidate = family or literal
            elif isinstance(item, str):
                candidate = item.strip()
            else:
                continue
            if not candidate:
                continue
            tokens = re.findall(r"[A-Za-z][A-Za-z'-]+", candidate.lower())
            if tokens:
                out.append(tokens[-1])
    return list(dict.fromkeys(out))


def parse_anystyle_json_payload(payload: list[Any], article_id: str) -> list[Citation]:
    citations: list[Citation] = []
    for idx, row in enumerate(payload):
        if not isinstance(row, dict):
            continue
        title_guess = _extract_title(row)
        raw_text = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if not title_guess:
            title_guess = raw_text[:120]
        citations.append(
            Citation(
                citation_id=f"{article_id}::ref::{idx}",
                raw_text=raw_text,
                year=_extract_year(row),
                title_guess=title_guess,
                normalized_title=normalize_title(title_guess),
                doi=_extract_doi(row),
                source="anystyle",
                type_guess=(str(row.get("type")).strip() if row.get("type") is not None else None),
                author_tokens=_extract_author_tokens(row),
            )
        )
    return citations


def extract_citations_with_anystyle_docker(
    pdf_path: Path,
    *,
    compose_service: str = "anystyle",
    timeout_seconds: int = 240,
    project_root: Path | None = None,
) -> list[Citation]:
    root = (project_root or _project_root()).resolve()
    resolved_pdf = pdf_path.resolve()
    try:
        rel_pdf = resolved_pdf.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"PDF path must be inside project root {root}: {resolved_pdf}") from exc

    container_pdf = f"/workspace/{rel_pdf.as_posix()}"
    cmd = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "-v",
        f"{root}:/workspace",
        compose_service,
        "anystyle",
        "--stdout",
        "-f",
        "json",
        "find",
        container_pdf,
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout_seconds)),
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Docker CLI is not installed or not available in PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Anystyle timed out after {timeout_seconds}s for {pdf_path.name}.") from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(
            f"Anystyle failed for {pdf_path.name} with exit code {proc.returncode}: {stderr[-500:]}"
        )

    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Anystyle returned non-JSON output for {pdf_path.name}.") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"Anystyle returned unexpected payload type for {pdf_path.name}: {type(payload)!r}")

    return parse_anystyle_json_payload(payload, article_id=pdf_path.stem)
