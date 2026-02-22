from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from .anystyle_refs import extract_citations_with_anystyle_docker
from .config import Settings
from .neo4j_store import GraphStore
from .paperpile_metadata import find_metadata_for_pdf, load_paperpile_index
from .pdf_processing import ArticleDoc, Chunk, Citation, filter_citations, load_article


@dataclass
class IngestSummary:
    ingested_articles: int
    total_chunks: int
    total_references: int
    selected_pdfs: list[str]
    skipped_existing_pdfs: list[str]
    skipped_no_metadata_pdfs: list[str]
    failed_pdfs: list[dict]
    citation_override_pdfs: int = 0
    anystyle_attempted_pdfs: int = 0
    anystyle_applied_pdfs: int = 0
    anystyle_empty_pdfs: int = 0
    anystyle_failed_pdfs: int = 0
    anystyle_disabled_reason: str | None = None
    anystyle_failure_samples: list[str] = field(default_factory=list)


def _cache_dir() -> Path:
    p = Path(".cache") / "rag_articles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_key(pdf_path: Path, settings: Settings, metadata: dict | None) -> str:
    stat = pdf_path.stat()
    md = json.dumps(metadata or {}, sort_keys=True, ensure_ascii=False)
    raw = "|".join(
        [
            str(pdf_path.resolve()),
            str(stat.st_mtime_ns),
            str(stat.st_size),
            str(settings.chunk_size_words),
            str(settings.chunk_overlap_words),
            str(int(settings.chunk_strip_page_noise)),
            md,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _anystyle_cache_dir() -> Path:
    p = Path(".cache") / "anystyle_refs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _anystyle_cache_key(pdf_path: Path, settings: Settings) -> str:
    stat = pdf_path.stat()
    raw = "|".join(
        [
            str(pdf_path.resolve()),
            str(stat.st_mtime_ns),
            str(stat.st_size),
            settings.anystyle_service,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _deserialize_citations(items: list[dict]) -> list[Citation]:
    return [Citation(**item) for item in items]


def _load_anystyle_citations_cached(pdf_path: Path, settings: Settings) -> list[Citation]:
    key = _anystyle_cache_key(pdf_path, settings)
    cache_file = _anystyle_cache_dir() / f"{key}.json"
    if cache_file.exists():
        with cache_file.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, list):
            return _deserialize_citations(payload)

    citations = extract_citations_with_anystyle_docker(
        pdf_path,
        compose_service=settings.anystyle_service,
        timeout_seconds=settings.anystyle_timeout_seconds,
    )
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump([asdict(c) for c in citations], f, ensure_ascii=False)
    return citations


def _use_anystyle(settings: Settings) -> bool:
    mode = (settings.citation_parser or "").strip().lower()
    return mode not in {"heuristic", "builtin", "built-in", "default"}


def _is_global_anystyle_failure(msg: str) -> bool:
    text = (msg or "").lower()
    markers = (
        "docker cli is not installed",
        "cannot connect to the docker daemon",
        "is the docker daemon running",
        "permission denied while trying to connect to the docker daemon",
        "no such service",
        "no configuration file provided",
    )
    return any(marker in text for marker in markers)


def _deserialize_article(obj: dict) -> ArticleDoc:
    chunks = [Chunk(**c) for c in obj.get("chunks", [])]
    citations = [Citation(**c) for c in obj.get("citations", [])]
    return ArticleDoc(
        article_id=obj["article_id"],
        title=obj["title"],
        normalized_title=obj["normalized_title"],
        year=obj.get("year"),
        author=obj.get("author"),
        authors=obj.get("authors", []),
        citekey=obj.get("citekey"),
        paperpile_id=obj.get("paperpile_id"),
        doi=obj.get("doi"),
        journal=obj.get("journal"),
        publisher=obj.get("publisher"),
        source_path=obj["source_path"],
        chunks=chunks,
        citations=citations,
    )


def _load_article_cached(pdf_path: Path, settings: Settings, metadata: dict | None) -> ArticleDoc:
    key = _cache_key(pdf_path, settings, metadata)
    cache_file = _cache_dir() / f"{key}.pkl"
    if cache_file.exists():
        with cache_file.open("rb") as f:
            return _deserialize_article(pickle.load(f))

    article = load_article(
        pdf_path=pdf_path,
        chunk_size_words=settings.chunk_size_words,
        chunk_overlap_words=settings.chunk_overlap_words,
        metadata=metadata,
        strip_page_noise=settings.chunk_strip_page_noise,
    )
    with cache_file.open("wb") as f:
        pickle.dump(asdict(article), f)
    return article


def _has_pdf_header(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"%PDF"
    except Exception:
        return False


def _resolve_custom_pdf_path(path_str: str, source_dir: str) -> Path:
    raw = path_str.strip().strip('"').strip("'")
    cleaned = raw.replace("{", "").replace("}", "")
    source_root = Path(source_dir)

    primary = Path(raw)
    fallback = Path(cleaned)

    candidates: list[Path] = [primary]
    if fallback != primary:
        candidates.append(fallback)

    for base in (primary, fallback):
        if not base.is_absolute():
            candidates.append(source_root / base)

    seen: set[str] = set()
    for c in candidates:
        key = str(c)
        if key in seen:
            continue
        seen.add(key)
        if c.exists():
            return c

    # Return cleaned form for clearer missing-file messages.
    return fallback


def _get_existing_article_ids(settings: Settings) -> set[str]:
    try:
        store = GraphStore(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            embedding_model=settings.embedding_model,
        )
        try:
            return store.existing_article_ids()
        finally:
            store.close()
    except Exception:
        # If DB isn't reachable, fall back to no-skip behavior.
        return set()


def choose_pdfs(
    mode: str = "batch",
    source_dir: str = "pdfs",
    explicit_pdfs: list[str] | None = None,
    skip_existing: bool = True,
    require_metadata: bool = True,
    settings: Settings | None = None,
    partial_count: int = 3,
) -> list[Path]:
    mode = mode.lower().strip()
    if mode == "test3":
        mode = "batch"
    explicit_pdfs = explicit_pdfs or []

    source_root = Path(source_dir)
    all_pdfs = sorted(
        [p for p in source_root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"],
        key=lambda p: str(p).lower(),
    )

    partial_n = max(1, int(partial_count))

    if mode == "custom":
        selected = [_resolve_custom_pdf_path(p, source_dir) for p in explicit_pdfs]
    else:
        if mode == "all":
            selected = all_pdfs
        elif mode == "batch":
            readable = [p for p in all_pdfs if _has_pdf_header(p)]
            selected = readable
        else:
            raise ValueError("Unsupported mode. Use 'batch', 'all', or 'custom'.")

    missing = [p for p in selected if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing PDFs: {', '.join(str(m) for m in missing)}")
    cfg = settings or Settings()

    if skip_existing:
        existing_ids = _get_existing_article_ids(cfg)
        selected = [p for p in selected if p.stem not in existing_ids]

    if require_metadata:
        paperpile_index = load_paperpile_index(cfg.paperpile_json)
        selected = [p for p in selected if find_metadata_for_pdf(paperpile_index, p.name)]

    if mode == "batch":
        selected = selected[:partial_n]

    if not selected:
        if skip_existing:
            raise ValueError(
                "No PDFs found to ingest after filtering (existing/no-metadata). "
                "Use override_existing to reprocess existing files."
            )
        raise ValueError("No PDFs found to ingest.")
    return selected


def ingest_pdfs(
    selected_pdfs: list[Path],
    wipe: bool = False,
    settings: Settings | None = None,
    should_cancel=None,
    skip_existing: bool = True,
    progress_callback=None,
    citation_overrides: dict[str, list[Citation]] | None = None,
) -> IngestSummary:
    settings = settings or Settings()
    use_anystyle = _use_anystyle(settings)
    paperpile_index = load_paperpile_index(settings.paperpile_json)
    existing_ids = _get_existing_article_ids(settings) if skip_existing else set()
    skipped_existing = [str(p) for p in selected_pdfs if p.stem in existing_ids]
    selected_pdfs = [p for p in selected_pdfs if p.stem not in existing_ids]
    skipped_no_metadata = [str(p) for p in selected_pdfs if not find_metadata_for_pdf(paperpile_index, p.name)]
    selected_pdfs = [p for p in selected_pdfs if find_metadata_for_pdf(paperpile_index, p.name)]

    if not selected_pdfs:
        if progress_callback:
            progress_callback(100.0, "Nothing to ingest (all selected PDFs already exist).")
        return IngestSummary(
            ingested_articles=0,
            total_chunks=0,
            total_references=0,
            selected_pdfs=[],
            skipped_existing_pdfs=skipped_existing,
            skipped_no_metadata_pdfs=skipped_no_metadata,
            failed_pdfs=[],
        )

    articles = []
    failures: list[dict] = []
    citation_override_pdfs = 0
    anystyle_attempted = 0
    anystyle_applied = 0
    anystyle_empty = 0
    anystyle_failed = 0
    anystyle_failure_samples: list[str] = []
    anystyle_disabled_reason: str | None = None
    total_steps = max(1, len(selected_pdfs) * 2)
    parse_done = 0
    for p in selected_pdfs:
        if should_cancel and should_cancel():
            raise RuntimeError("Ingest cancelled by user.")
        if progress_callback:
            progress_callback((parse_done / total_steps) * 100.0, f"Parsing {p.name}")
        try:
            article = _load_article_cached(
                pdf_path=p,
                settings=settings,
                metadata=find_metadata_for_pdf(paperpile_index, p.name),
            )
            if citation_overrides and article.article_id in citation_overrides:
                article.citations = citation_overrides[article.article_id]
                citation_override_pdfs += 1
            elif use_anystyle and not anystyle_disabled_reason:
                anystyle_attempted += 1
                try:
                    extracted = _load_anystyle_citations_cached(p, settings)
                    if extracted:
                        article.citations = extracted
                        anystyle_applied += 1
                    else:
                        anystyle_empty += 1
                except Exception as exc:
                    anystyle_failed += 1
                    err = str(exc)
                    if len(anystyle_failure_samples) < 10:
                        anystyle_failure_samples.append(f"{p.name}: {err}")
                    if settings.anystyle_require_success:
                        raise
                    if _is_global_anystyle_failure(err):
                        anystyle_disabled_reason = err
            article.citations = filter_citations(
                article.citations,
                min_score=settings.citation_min_quality,
            )
            articles.append(article)
        except Exception as exc:
            failures.append({"pdf": str(p), "error": str(exc)})
        parse_done += 1
        if progress_callback:
            progress_callback((parse_done / total_steps) * 100.0, f"Parsed {parse_done}/{len(selected_pdfs)} files")

    if not articles:
        if failures:
            preview = "; ".join(f"{Path(x['pdf']).name}: {x['error']}" for x in failures[:5])
            raise ValueError(f"No readable PDFs were ingested. Failed files: {preview}")
        raise ValueError("No readable PDFs were ingested. Check source files.")

    store = GraphStore(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        embedding_model=settings.embedding_model,
    )
    try:
        store.setup_schema(vector_dimensions=store.embedding_dimension)
        if progress_callback:
            progress_callback((parse_done / total_steps) * 100.0, "Uploading parsed data to Neo4j")

        def on_article_upload(idx: int, total_articles: int, message: str) -> None:
            if progress_callback:
                pct = ((parse_done + idx) / total_steps) * 100.0
                progress_callback(pct, message)

        store.ingest_articles(
            articles,
            should_cancel=should_cancel,
            article_progress_callback=on_article_upload,
        )
    finally:
        store.close()

    if progress_callback:
        progress_callback(100.0, "Ingest complete")

    return IngestSummary(
        ingested_articles=len(articles),
        total_chunks=sum(len(a.chunks) for a in articles),
        total_references=sum(len(a.citations) for a in articles),
        selected_pdfs=[str(p) for p in selected_pdfs],
        skipped_existing_pdfs=skipped_existing,
        skipped_no_metadata_pdfs=skipped_no_metadata,
        failed_pdfs=failures,
        citation_override_pdfs=citation_override_pdfs,
        anystyle_attempted_pdfs=anystyle_attempted,
        anystyle_applied_pdfs=anystyle_applied,
        anystyle_empty_pdfs=anystyle_empty,
        anystyle_failed_pdfs=anystyle_failed,
        anystyle_disabled_reason=anystyle_disabled_reason,
        anystyle_failure_samples=anystyle_failure_samples,
    )
