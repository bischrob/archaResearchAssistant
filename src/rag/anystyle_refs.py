from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from .pdf_processing import Citation, normalize_title


YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
ANYSTYLE_BIN = "/usr/local/bundle/bin/anystyle"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_compose_service(
    compose_service: str,
    *,
    use_gpu: bool,
    gpu_service: str,
) -> str:
    if use_gpu:
        return (gpu_service or "").strip() or "anystyle-gpu"
    return (compose_service or "").strip() or "anystyle"


def _compose_run_env(*, use_gpu: bool, gpu_devices: str) -> dict[str, str] | None:
    if not use_gpu:
        return None
    env = dict(os.environ)
    env["ANYSTYLE_GPU_DEVICES"] = (gpu_devices or "all").strip() or "all"
    return env


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


def _extract_author_names(entry: dict[str, Any]) -> list[str]:
    out: list[str] = []
    values = entry.get("author")
    if not isinstance(values, list):
        return out
    for item in values:
        if isinstance(item, dict):
            given = (item.get("given") or "").strip()
            family = (item.get("family") or "").strip()
            literal = (item.get("literal") or "").strip()
            candidate = " ".join(part for part in (given, family) if part) or literal
        elif isinstance(item, str):
            candidate = item.strip()
        else:
            continue
        if candidate:
            out.append(candidate)
    return list(dict.fromkeys(out))


def _extract_author_tokens(entry: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for candidate in _extract_author_names(entry):
        tokens = re.findall(r"[A-Za-z][A-Za-z'-]+", candidate.lower())
        if tokens:
            out.append(tokens[-1])
    return list(dict.fromkeys(out))


def _bibtex_escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _bibtex_entry_type(type_guess: str | None) -> str:
    kind = str(type_guess or "").strip().lower()
    mapping = {
        "article-journal": "article",
        "article-magazine": "article",
        "article-newspaper": "article",
        "paper-conference": "inproceedings",
        "chapter": "incollection",
        "book": "book",
        "report": "techreport",
        "thesis": "phdthesis",
        "webpage": "misc",
        "web": "misc",
    }
    return mapping.get(kind, "misc")


def _bibtex_key(entry: dict[str, Any], citation_id: str, year: int | None, title_guess: str) -> str:
    author_tokens = _extract_author_tokens(entry)
    first_author = author_tokens[0] if author_tokens else "ref"
    year_part = str(year) if year is not None else "nd"
    title_tokens = re.findall(r"[A-Za-z0-9]+", title_guess.lower())
    title_part = title_tokens[0] if title_tokens else "entry"
    raw = f"{first_author}_{year_part}_{title_part}_{citation_id}"
    cleaned = re.sub(r"[^A-Za-z0-9_:-]+", "_", raw).strip("_")
    return cleaned or re.sub(r"[^A-Za-z0-9_:-]+", "_", citation_id)


def _build_bibtex(entry: dict[str, Any], *, citation_id: str, year: int | None, title_guess: str, doi: str | None) -> str:
    entry_type = _bibtex_entry_type(entry.get("type"))
    key = _bibtex_key(entry, citation_id, year, title_guess)
    authors = _extract_author_names(entry)
    fields: list[tuple[str, str]] = []
    if authors:
        fields.append(("author", " and ".join(authors)))
    if title_guess:
        fields.append(("title", title_guess))
    if year is not None:
        fields.append(("year", str(year)))

    container = _string_values(entry.get("container-title"))
    publisher = _string_values(entry.get("publisher"))
    volume = _string_values(entry.get("volume"))
    number = _string_values(entry.get("issue")) or _string_values(entry.get("number"))
    pages = _string_values(entry.get("page")) or _string_values(entry.get("pages"))
    url = _string_values(entry.get("URL")) or _string_values(entry.get("url"))
    note = _string_values(entry.get("note"))

    if container:
        fields.append((("journal" if entry_type == "article" else "booktitle"), container[0]))
    if publisher:
        fields.append(("publisher", publisher[0]))
    if volume:
        fields.append(("volume", volume[0]))
    if number:
        fields.append(("number", number[0]))
    if pages:
        fields.append(("pages", pages[0]))
    if doi:
        fields.append(("doi", doi))
    if url:
        fields.append(("url", url[0]))
    if note:
        fields.append(("note", note[0]))

    body = ",\n".join(f"  {name} = {{{_bibtex_escape(value)}}}" for name, value in fields if value)
    return f"@{entry_type}{{{key},\n{body}\n}}"


def parse_anystyle_json_payload(
    payload: list[Any],
    article_id: str,
    *,
    raw_references: list[str] | None = None,
) -> list[Citation]:
    citations: list[Citation] = []
    for idx, row in enumerate(payload):
        if not isinstance(row, dict):
            continue
        citation_id = f"{article_id}::ref::{idx}"
        title_guess = _extract_title(row)
        if raw_references is not None and idx < len(raw_references):
            raw_text = str(raw_references[idx] or "").strip()
        else:
            raw_text = json.dumps(row, ensure_ascii=False, sort_keys=True)
        if not title_guess:
            title_guess = raw_text[:120]
        year = _extract_year(row)
        doi = _extract_doi(row)
        authors = _extract_author_names(row)
        citations.append(
            Citation(
                citation_id=citation_id,
                raw_text=raw_text,
                year=year,
                title_guess=title_guess,
                normalized_title=normalize_title(title_guess),
                doi=doi,
                source="anystyle",
                type_guess=(str(row.get("type")).strip() if row.get("type") is not None else None),
                author_tokens=_extract_author_tokens(row),
                authors=authors,
                bibtex=_build_bibtex(row, citation_id=citation_id, year=year, title_guess=title_guess, doi=doi),
            )
        )
    return citations


def parse_reference_strings_with_anystyle_docker(
    references: list[str],
    *,
    article_id: str,
    compose_service: str = "anystyle",
    timeout_seconds: int = 240,
    use_gpu: bool = False,
    gpu_devices: str = "all",
    gpu_service: str = "anystyle-gpu",
    project_root: Path | None = None,
) -> list[Citation]:
    cleaned = [" ".join((x or "").split()).strip() for x in references]
    cleaned = [x for x in cleaned if x]
    if not cleaned:
        return []

    root = (project_root or _project_root()).resolve()
    cache_dir = (root / ".cache" / "anystyle_refs")
    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".txt",
        prefix="anystyle_refs_",
        dir=cache_dir,
        delete=False,
    ) as f:
        for row in cleaned:
            f.write(row.replace("\n", " ").strip() + "\n")
        input_path = Path(f.name).resolve()

    try:
        rel_input = input_path.relative_to(root)
    except ValueError as exc:
        try:
            input_path.unlink(missing_ok=True)
        finally:
            raise ValueError(f"Temporary input path must be inside project root {root}: {input_path}") from exc

    container_input = f"/workspace/{rel_input.as_posix()}"
    service_name = _resolve_compose_service(
        compose_service,
        use_gpu=use_gpu,
        gpu_service=gpu_service,
    )
    cmd = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "-v",
        f"{root}:/workspace",
        service_name,
        ANYSTYLE_BIN,
        "--stdout",
        "-f",
        "json",
        "parse",
        container_input,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            env=_compose_run_env(use_gpu=use_gpu, gpu_devices=gpu_devices),
            timeout=max(1, int(timeout_seconds)),
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Docker CLI is not installed or not available in PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Anystyle parse timed out after {timeout_seconds}s.") from exc
    finally:
        input_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(f"Anystyle parse failed with exit code {proc.returncode}: {stderr[-500:]}")

    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Anystyle parse returned non-JSON output.") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"Anystyle parse returned unexpected payload type: {type(payload)!r}")

    return parse_anystyle_json_payload(payload, article_id=article_id, raw_references=cleaned)


def extract_citations_with_anystyle_docker(
    pdf_path: Path,
    *,
    compose_service: str = "anystyle",
    timeout_seconds: int = 240,
    use_gpu: bool = False,
    gpu_devices: str = "all",
    gpu_service: str = "anystyle-gpu",
    project_root: Path | None = None,
) -> list[Citation]:
    root = (project_root or _project_root()).resolve()
    resolved_pdf = pdf_path.resolve()
    try:
        rel_pdf = resolved_pdf.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"PDF path must be inside project root {root}: {resolved_pdf}") from exc

    container_pdf = f"/workspace/{rel_pdf.as_posix()}"
    service_name = _resolve_compose_service(
        compose_service,
        use_gpu=use_gpu,
        gpu_service=gpu_service,
    )
    cmd = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "-v",
        f"{root}:/workspace",
        service_name,
        ANYSTYLE_BIN,
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
            env=_compose_run_env(use_gpu=use_gpu, gpu_devices=gpu_devices),
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
