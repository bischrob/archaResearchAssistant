from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from .pdf_processing import Citation, normalize_title
from .reference_parsing import parse_reference_entries as _parse_reference_entries_shared


YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
ANYSTYLE_BIN = "/usr/local/bundle/bin/anystyle"
TITLE_SPLIT_RE = re.compile(r"\.\s+")


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


def _extract_year_from_text(text: str) -> int | None:
    match = YEAR_RE.search(text or "")
    if not match:
        return None
    try:
        return int(match.group(0))
    except Exception:
        return None


def _extract_doi_from_text(text: str) -> str | None:
    match = DOI_RE.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip(".;,")


def _extract_authors_from_text(text: str) -> list[str]:
    suffix_only = {"jr", "jr.", "sr", "sr.", "ed", "ed.", "eds", "eds.", "ii", "iii", "iv"}
    prefix = (text or "").strip()
    year_match = YEAR_RE.search(prefix)
    if year_match:
        prefix = prefix[: year_match.start()].strip(" .,;:-")
    if not prefix:
        return []
    prefix = re.sub(r"^\s*\[\d+\]\s*", "", prefix)
    prefix = re.split(r"(?i)\bin:\s*", prefix, maxsplit=1)[0].strip(" ,;")
    prefix = re.sub(r"\bet al\.?$", "", prefix, flags=re.IGNORECASE).strip(" ,;")
    authors: list[str] = []

    def _is_name_fragment(value: str) -> bool:
        clean = " ".join((value or "").split()).strip(" ,;")
        if not clean or YEAR_RE.search(clean):
            return False
        tokens = re.findall(r"[A-Za-z][A-Za-z'`.-]*", clean)
        return 1 <= len(tokens) <= 4

    def _looks_like_family_fragment(value: str) -> bool:
        clean = " ".join((value or "").split()).strip(" ,;")
        tokens = re.findall(r"[A-Za-z][A-Za-z'`.-]*", clean)
        return 1 <= len(tokens) <= 2 and not any("." in tok for tok in tokens)

    def _looks_like_given_fragment(value: str) -> bool:
        clean = " ".join((value or "").split()).strip(" ,;")
        tokens = re.findall(r"[A-Za-z][A-Za-z'`.-]*", clean)
        if not tokens or len(tokens) > 3:
            return False
        if len(tokens) == 1:
            return True
        if len(tokens) == 2 and len(tokens[1]) == 1 and tokens[1].isupper():
            return True
        return any("." in tok for tok in tokens)

    def _looks_like_initial_only(value: str) -> bool:
        clean = " ".join((value or "").split()).strip(" ,;")
        tokens = re.findall(r"[A-Za-z][A-Za-z'`.-]*", clean)
        if not tokens:
            return False
        return all(re.fullmatch(r"[A-Z](?:\.[A-Z]+)*\.?", token) for token in tokens)

    def _extract_initials_prefix(value: str) -> str | None:
        clean = " ".join((value or "").split()).strip(" ,;")
        clean = re.sub(r"\s*\((?:eds?|ed\.)\)\s*$", "", clean, flags=re.IGNORECASE).strip(" ,;")
        match = re.match(r"^([A-Z](?:\.[A-Z]+)*\.)", clean)
        if not match:
            return None
        return match.group(1).strip()

    def _looks_like_title_fragment(value: str) -> bool:
        clean = " ".join((value or "").split()).strip(" ,;")
        if not clean:
            return False
        lowered = clean.lower()
        if ":" in clean:
            return True
        words = re.findall(r"[A-Za-z][A-Za-z'`.-]*", clean)
        if len(words) < 2:
            return False
        title_markers = {"and", "of", "for", "in", "on", "the", "a", "an", "to", "with", "from"}
        if any(word.islower() and word in title_markers for word in words[1:]):
            return True
        return lowered.startswith(("on ", "the ", "a ", "an "))

    def _looks_like_non_author_fragment(value: str) -> bool:
        clean = " ".join((value or "").split()).strip(" ,;")
        lowered = clean.lower()
        if not clean:
            return True
        if lowered in {"cambridge", "new york", "london", "berkeley", "boulder", "tucson", "albuquerque", "provo", "austin", "toronto", "oxford"}:
            return True
        if any(token in lowered for token in ("university press", "mit press", "routledge", "int. j.", "journal", "proceedings", "museum informatics")):
            return True
        if ":" in clean and any(token in lowered for token in ("new york", "london", "cambridge", "berkeley", "boulder", "tucson", "albuquerque", "provo", "austin", "toronto", "oxford")):
            return True
        return False

    def _looks_like_inverted_pair(family: str, given: str) -> bool:
        family_tokens = re.findall(r"[A-Za-z][A-Za-z'`.-]*", " ".join((family or "").split()).strip(" ,;"))
        given_tokens = re.findall(r"[A-Za-z][A-Za-z'`.-]*", " ".join((given or "").split()).strip(" ,;"))
        if not family_tokens or not given_tokens or len(family_tokens) > 2:
            return False
        if any("." in tok for tok in family_tokens):
            return False
        if len(given_tokens) == 1:
            return True
        if any("." in tok for tok in given_tokens):
            return True
        return len(family_tokens) == 1 and len(given_tokens) >= 2

    def _extract_leading_direct_name(value: str) -> str | None:
        clean = " ".join((value or "").split()).strip(" ,;")
        if not clean:
            return None
        patterns = [
            r"^([A-Z](?:\.[A-Z]+)*\.\s+[A-Z][A-Za-z'`-]+)\b(?=$|[,:.;])",
            r"^((?:[A-Z](?:\.[A-Z]+)*\.?\s+){1,3}[A-Z][A-Za-z'`-]+(?:\s+[A-Z][A-Za-z'`-]+)?)\b(?=$|[,:.;])",
            r"^([A-Z][A-Za-z'`-]+(?:\s+[A-Z]\.)+\s+[A-Z][A-Za-z'`-]+)\b(?=$|[,:.;])",
        ]
        for pattern in patterns:
            match = re.match(pattern, clean)
            if match:
                return match.group(1).strip()
        return None

    def _parse_author_group(group: str) -> list[str]:
        clean_group = " ".join((group or "").split()).strip(" ,;")
        if not clean_group:
            return []
        direct_name = _extract_leading_direct_name(clean_group)
        comma_parts = [" ".join(part.split()).strip(" ,;") for part in clean_group.split(",") if " ".join(part.split()).strip(" ,;")]
        if direct_name and len(comma_parts) >= 2 and (
            _looks_like_title_fragment(comma_parts[1]) or _looks_like_non_author_fragment(comma_parts[1])
        ):
            return [direct_name]
        if len(comma_parts) >= 4 and len(comma_parts) % 2 == 0 and all(
            _looks_like_family_fragment(comma_parts[idx]) and _looks_like_given_fragment(comma_parts[idx + 1])
            for idx in range(0, len(comma_parts), 2)
        ):
            return [f"{comma_parts[idx + 1]} {comma_parts[idx]}".strip() for idx in range(0, len(comma_parts), 2)]
        if len(comma_parts) == 2 and all(_is_name_fragment(part) for part in comma_parts):
            return [f"{comma_parts[1]} {comma_parts[0]}".strip()]
        if len(comma_parts) >= 2:
            out: list[str] = []
            idx = 0
            paired_any = False
            while idx < len(comma_parts):
                current = comma_parts[idx]
                nxt = comma_parts[idx + 1] if idx + 1 < len(comma_parts) else None
                if out and (_looks_like_title_fragment(current) or _looks_like_non_author_fragment(current)):
                    break
                if paired_any and not _is_name_fragment(current):
                    break
                given_candidate = nxt
                if nxt and _looks_like_family_fragment(current):
                    initials_prefix = _extract_initials_prefix(nxt)
                    if initials_prefix and (
                        not _is_name_fragment(nxt) or not _looks_like_inverted_pair(current, nxt)
                    ) and _looks_like_inverted_pair(current, initials_prefix):
                        given_candidate = initials_prefix
                if given_candidate and _looks_like_family_fragment(current) and _looks_like_inverted_pair(current, given_candidate):
                    out.append(f"{given_candidate} {current}".strip())
                    idx += 2
                    paired_any = True
                    continue
                if _is_name_fragment(current) and not _looks_like_initial_only(current):
                    out.append(current)
                elif paired_any:
                    break
                idx += 1
            if paired_any:
                return [part for part in out if _is_name_fragment(part) and not _looks_like_initial_only(part)]
            if out:
                return [part for part in out if _is_name_fragment(part) and not _looks_like_initial_only(part)]
        if len(comma_parts) >= 3 and all(_is_name_fragment(part) for part in comma_parts[:2]):
            out = [f"{comma_parts[1]} {comma_parts[0]}".strip()]
            out.extend(part for part in comma_parts[2:] if _is_name_fragment(part) and not _looks_like_initial_only(part))
            return [part for part in out if not _looks_like_title_fragment(part) and not _looks_like_non_author_fragment(part)]
        if direct_name:
            return [direct_name]
        if _looks_like_title_fragment(clean_group) or _looks_like_non_author_fragment(clean_group):
            return []
        return [clean_group] if re.search(r"[A-Za-z]", clean_group) else []

    groups = re.split(r"\s+(?:and|&)\s+|;\s*", prefix)
    for group in groups:
        authors.extend(_parse_author_group(group))
    return list(
        dict.fromkeys(
            [
                author
                for author in authors
                if author.strip().lower() not in suffix_only
                and not _looks_like_non_author_fragment(author)
                and not _looks_like_initial_only(author)
                and not _looks_like_title_fragment(author)
            ]
        )
    )


def _extract_author_tokens_from_text(text: str) -> list[str]:
    out: list[str] = []
    for author in _extract_authors_from_text(text):
        tokens = re.findall(r"[A-Za-z][A-Za-z'-]+", author.lower())
        if tokens:
            out.append(tokens[-1])
    return list(dict.fromkeys(out))


def _extract_title_from_text(text: str) -> str:
    clean = " ".join((text or "").split()).strip()
    if not clean:
        return ""
    year_match = YEAR_RE.search(clean)
    if year_match:
        remainder = clean[year_match.end() :].strip(" .,:;")
    else:
        pieces = TITLE_SPLIT_RE.split(clean, maxsplit=2)
        remainder = pieces[1].strip(" .,:;") if len(pieces) > 1 else clean
    remainder = DOI_RE.sub("", remainder).strip(" .,:;")
    pieces = TITLE_SPLIT_RE.split(remainder, maxsplit=1)
    candidate = pieces[0].strip(" .,:;") if pieces else remainder
    if candidate:
        return candidate[:240]
    return clean[:240]


def parse_reference_strings_heuristic(
    references: list[str],
    *,
    article_id: str,
) -> list[Citation]:
    from .config import Settings

    citations, _ = _parse_reference_entries_shared(
        references,
        article_id=article_id,
        settings=Settings(),
        parser_mode="heuristic",
    )
    return citations


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


def parse_reference_entries_resilient(
    references: list[str],
    *,
    article_id: str,
    parser_mode: str = "anystyle",
    compose_service: str = "anystyle",
    timeout_seconds: int = 240,
    use_gpu: bool = False,
    gpu_devices: str = "all",
    gpu_service: str = "anystyle-gpu",
    project_root: Path | None = None,
) -> tuple[list[Citation], list[dict[str, Any]]]:
    from .config import Settings

    mode = (parser_mode or "").strip().lower()
    if mode in {"heuristic", "hybrid_llm", "llm"}:
        return _parse_reference_entries_shared(
            references,
            article_id=article_id,
            settings=Settings(),
            parser_mode=mode,
        )
    citations: list[Citation] = []
    failures: list[dict[str, Any]] = []
    for idx, raw in enumerate(references):
        entry = " ".join((raw or "").split()).strip()
        if not entry:
            continue
        try:
            parsed = parse_reference_strings_with_anystyle_docker(
                [entry],
                article_id=f"{article_id}::entry{idx}",
                compose_service=compose_service,
                timeout_seconds=timeout_seconds,
                use_gpu=use_gpu,
                gpu_devices=gpu_devices,
                gpu_service=gpu_service,
                project_root=project_root,
            )
            if parsed:
                citation = parsed[0]
                citations.append(
                    Citation(
                        citation_id=f"{article_id}::ref::{len(citations)}",
                        raw_text=entry,
                        year=citation.year,
                        title_guess=citation.title_guess,
                        normalized_title=citation.normalized_title,
                        doi=citation.doi,
                        source=citation.source,
                        type_guess=citation.type_guess,
                        author_tokens=citation.author_tokens,
                        quality_score=citation.quality_score,
                        authors=citation.authors,
                        bibtex=citation.bibtex,
                    )
                )
            else:
                failures.append({"index": idx, "raw_text": entry, "error": "empty_anystyle_payload"})
        except Exception as exc:
            failures.append({"index": idx, "raw_text": entry, "error": str(exc)})
    return citations, failures


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
