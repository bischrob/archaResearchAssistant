from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .neo4j_store import GraphStore
from .pdf_processing import load_article


@dataclass
class IngestSummary:
    ingested_articles: int
    total_chunks: int
    total_references: int
    selected_pdfs: list[str]
    skipped_existing_pdfs: list[str]
    failed_pdfs: list[dict]


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
    mode: str = "test3",
    source_dir: str = "pdfs",
    explicit_pdfs: list[str] | None = None,
    skip_existing: bool = True,
    settings: Settings | None = None,
) -> list[Path]:
    mode = mode.lower().strip()
    explicit_pdfs = explicit_pdfs or []

    source_root = Path(source_dir)
    all_pdfs = sorted(
        [p for p in source_root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"],
        key=lambda p: str(p).lower(),
    )

    if mode == "custom":
        selected = [_resolve_custom_pdf_path(p, source_dir) for p in explicit_pdfs]
    else:
        if mode == "all":
            selected = all_pdfs
        elif mode == "test3":
            readable = [p for p in all_pdfs if _has_pdf_header(p)]
            selected = readable
        else:
            raise ValueError("Unsupported mode. Use 'test3', 'all', or 'custom'.")

    missing = [p for p in selected if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing PDFs: {', '.join(str(m) for m in missing)}")
    if skip_existing:
        cfg = settings or Settings()
        existing_ids = _get_existing_article_ids(cfg)
        selected = [p for p in selected if p.stem not in existing_ids]

    if mode == "test3":
        selected = selected[:3]

    if not selected:
        if skip_existing:
            raise ValueError(
                "No PDFs found to ingest after skipping already ingested files. "
                "Use override_existing to reprocess."
            )
        raise ValueError("No PDFs found to ingest.")
    return selected


def ingest_pdfs(
    selected_pdfs: list[Path],
    wipe: bool = False,
    settings: Settings | None = None,
    should_cancel=None,
    skip_existing: bool = True,
) -> IngestSummary:
    settings = settings or Settings()
    existing_ids = _get_existing_article_ids(settings) if skip_existing else set()
    skipped_existing = [str(p) for p in selected_pdfs if p.stem in existing_ids]
    selected_pdfs = [p for p in selected_pdfs if p.stem not in existing_ids]

    if not selected_pdfs:
        return IngestSummary(
            ingested_articles=0,
            total_chunks=0,
            total_references=0,
            selected_pdfs=[],
            skipped_existing_pdfs=skipped_existing,
            failed_pdfs=[],
        )

    articles = []
    failures: list[dict] = []
    for p in selected_pdfs:
        if should_cancel and should_cancel():
            raise RuntimeError("Ingest cancelled by user.")
        try:
            articles.append(
                load_article(
                    pdf_path=p,
                    chunk_size_words=settings.chunk_size_words,
                    chunk_overlap_words=settings.chunk_overlap_words,
                )
            )
        except Exception as exc:
            failures.append({"pdf": str(p), "error": str(exc)})

    if not articles:
        raise ValueError("No readable PDFs were ingested. Check source files.")

    store = GraphStore(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        embedding_model=settings.embedding_model,
    )
    try:
        store.setup_schema(vector_dimensions=store.embedding_dimension)
        store.ingest_articles(articles, should_cancel=should_cancel)
    finally:
        store.close()

    return IngestSummary(
        ingested_articles=len(articles),
        total_chunks=sum(len(a.chunks) for a in articles),
        total_references=sum(len(a.citations) for a in articles),
        selected_pdfs=[str(p) for p in selected_pdfs],
        skipped_existing_pdfs=skipped_existing,
        failed_pdfs=failures,
    )
