from __future__ import annotations

import hashlib
import json
import pickle
import re
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from .anystyle_refs import extract_citations_with_anystyle_docker
from .config import Settings
from .metadata_provider import MetadataIndex, find_metadata_for_pdf, load_metadata_index, metadata_title_year_key
from .neo4j_store import GraphStore
from .paperpile_metadata import load_paperpile_index as _legacy_load_paperpile_index
from .path_utils import resolve_input_path
from .zip_pdf_source import collect_source_pdfs
from .pdf_processing import ArticleDoc, Chunk, Citation, Keyword, Section, filter_citations, load_article
from .qwen_structured_refs import StructuredExtraction, extract_structured_chunks_and_citations
from .keyword_extraction import extract_keywords
from .zotero_attachment_resolver import ZoteroAttachmentResolver
from .zotero_metadata import load_zotero_entries

DOI_PREFIX_RE = re.compile(r"^https?://(dx\.)?doi\.org/", re.IGNORECASE)


def load_paperpile_index(path: str) -> dict:
    # Backward-compatible import point for tests and legacy tooling.
    return _legacy_load_paperpile_index(path)


def _load_metadata_index_for_settings(settings: Settings) -> MetadataIndex:
    backend = (settings.metadata_backend or "").strip().lower()
    if backend == "paperpile":
        legacy = load_paperpile_index(settings.paperpile_json)
        return MetadataIndex(
            backend="paperpile",
            by_basename=legacy,
            by_normalized={},
            by_path_normalized={},
        )
    return load_metadata_index(settings)


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
            settings.text_acquisition_policy,
            settings.text_quality_check_backend,
            settings.paddleocr_text_dir,
            settings.paddleocr_text_fallback_dir,
            str(int(settings.paddleocr_auto_generate_missing_text)),
            settings.paddleocr_auto_lang,
            settings.paddleocr_auto_device,
            str(settings.paddleocr_auto_render_dpi),
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
            settings.anystyle_gpu_service,
            str(settings.anystyle_timeout_seconds),
            str(int(settings.anystyle_use_gpu)),
            settings.anystyle_gpu_devices,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _structured_anystyle_cache_dir() -> Path:
    p = Path('.cache') / 'structured_anystyle_refs'
    p.mkdir(parents=True, exist_ok=True)
    return p


def _structured_anystyle_cache_key(pdf_path: Path, settings: Settings) -> str:
    stat = pdf_path.stat()
    raw = "|".join(
        [
            str(pdf_path.resolve()),
            str(stat.st_mtime_ns),
            str(stat.st_size),
            str(settings.chunk_size_words),
            str(settings.chunk_overlap_words),
            str(int(settings.chunk_strip_page_noise)),
            settings.anystyle_service,
            settings.anystyle_gpu_service,
            str(settings.anystyle_timeout_seconds),
            str(int(settings.anystyle_use_gpu)),
            settings.anystyle_gpu_devices,
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
        use_gpu=settings.anystyle_use_gpu,
        gpu_devices=settings.anystyle_gpu_devices,
        gpu_service=settings.anystyle_gpu_service,
    )
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump([asdict(c) for c in citations], f, ensure_ascii=False)
    return citations



def _load_structured_anystyle_cached(
    pdf_path: Path,
    article_id: str,
    settings: Settings,
) -> StructuredExtraction:
    key = _structured_anystyle_cache_key(pdf_path, settings)
    cache_file = _structured_anystyle_cache_dir() / f"{key}.json"
    if cache_file.exists():
        with cache_file.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            chunk_items = payload.get("chunks")
            citation_items = payload.get("citations")
            section_items = payload.get("sections")
            if isinstance(chunk_items, list) and isinstance(citation_items, list) and isinstance(section_items, list):
                return StructuredExtraction(chunks=[Chunk(**x) for x in chunk_items], citations=_deserialize_citations(citation_items), reference_strings=[], sections=[Section(**x) for x in section_items])

    structured = extract_structured_chunks_and_citations(
        pdf_path=pdf_path,
        article_id=article_id,
        settings=settings,
        chunk_size_words=settings.chunk_size_words,
        chunk_overlap_words=settings.chunk_overlap_words,
        strip_page_noise=settings.chunk_strip_page_noise,
    )
    with cache_file.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "chunks": [asdict(c) for c in structured.chunks],
                "citations": [asdict(c) for c in structured.citations],
                "reference_strings_count": len(structured.reference_strings),
                "sections": [asdict(s) for s in structured.sections],
            },
            f,
            ensure_ascii=False,
        )
    return structured


def _citation_parser_mode(settings: Settings) -> str:
    mode = (settings.citation_parser or '').strip().lower()
    if mode in {'heuristic', 'builtin', 'built-in', 'default'}:
        return 'heuristic'
    if mode in {'structured_anystyle', 'section_anystyle', 'anystyle_structured', 'qwen_anystyle', 'qwen_split_anystyle', 'qwen_refsplit_anystyle', 'qwen_section_anystyle', 'qwen_structured_anystyle'}:
        return 'structured_anystyle'
    return 'anystyle'


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
    sections = [Section(**s) for s in obj.get("sections", [])]
    keywords = [Keyword(**k) for k in obj.get("keywords", [])]
    return ArticleDoc(
        article_id=obj["article_id"],
        title=obj["title"],
        normalized_title=obj["normalized_title"],
        year=obj.get("year"),
        author=obj.get("author"),
        authors=obj.get("authors", []),
        citekey=obj.get("citekey"),
        paperpile_id=obj.get("paperpile_id"),
        zotero_persistent_id=obj.get("zotero_persistent_id"),
        zotero_item_key=obj.get("zotero_item_key"),
        zotero_attachment_key=obj.get("zotero_attachment_key"),
        doi=obj.get("doi"),
        journal=obj.get("journal"),
        publisher=obj.get("publisher"),
        title_year_key=obj.get("title_year_key"),
        metadata_source=obj.get("metadata_source"),
        text_acquisition_method=obj.get("text_acquisition_method"),
        text_acquisition_fallback_used=bool(obj.get("text_acquisition_fallback_used", False)),
        text_quality_check_backend=obj.get("text_quality_check_backend"),
        native_text_malformed=bool(obj.get("native_text_malformed", False)),
        native_text_malformed_reason=obj.get("native_text_malformed_reason"),
        native_text_char_count=obj.get("native_text_char_count"),
        paddleocr_text_path=obj.get("paddleocr_text_path"),
        ocr_engine=obj.get("ocr_engine"),
        ocr_model=obj.get("ocr_model"),
        ocr_version=obj.get("ocr_version"),
        ocr_processed_at=obj.get("ocr_processed_at"),
        ocr_quality_summary=obj.get("ocr_quality_summary"),
        source_path=obj["source_path"],
        chunks=chunks,
        citations=citations,
        sections=sections,
        keywords=keywords,
        keyword_extraction_method=obj.get("keyword_extraction_method"),
        keyword_extraction_audit=obj.get("keyword_extraction_audit"),
    )


def _load_article_cached(pdf_path: Path, settings: Settings, metadata: dict | None) -> ArticleDoc:
    key = _cache_key(pdf_path, settings, metadata)
    cache_file = _cache_dir() / f"{key}.pkl"
    if cache_file.exists():
        with cache_file.open("rb") as f:
            return _deserialize_article(pickle.load(f))

    try:
        article = load_article(
            pdf_path=pdf_path,
            chunk_size_words=settings.chunk_size_words,
            chunk_overlap_words=settings.chunk_overlap_words,
            metadata=metadata,
            strip_page_noise=settings.chunk_strip_page_noise,
            settings=settings,
        )
    except TypeError as exc:
        if "unexpected keyword argument 'settings'" not in str(exc):
            raise
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
    source_root = resolve_input_path(source_dir)

    primary = resolve_input_path(raw)
    fallback = resolve_input_path(cleaned)

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


def _normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    cleaned = DOI_PREFIX_RE.sub("", doi.strip().lower())
    return cleaned.rstrip(".;, ")


def _title_year_key_from_metadata(meta: dict | None) -> str:
    return (metadata_title_year_key(meta) or "").strip().lower()


def _prepare_metadata_for_ingest(meta: dict | None) -> dict:
    out = dict(meta or {})
    out["doi"] = _normalize_doi(out.get("doi"))
    out["title_year_key"] = metadata_title_year_key(out)
    out["zotero_persistent_id"] = str(out.get("zotero_persistent_id") or "").strip() or None
    return out


def _require_zotero_persistent_ids(
    settings: Settings,
    metadata_by_pdf: dict[Path, dict | None],
    *,
    scope_label: str,
) -> None:
    if (settings.metadata_backend or "").strip().lower() != "zotero":
        return
    if not bool(settings.zotero_require_persistent_id):
        return

    missing: list[str] = []
    for pdf_path, meta in metadata_by_pdf.items():
        if not meta:
            continue
        persistent_id = str((meta or {}).get("zotero_persistent_id") or "").strip()
        if not persistent_id:
            missing.append(str(pdf_path))

    if missing:
        preview = ", ".join(Path(p).name for p in missing[:10])
        extra = "" if len(missing) <= 10 else f" (+{len(missing) - 10} more)"
        raise ValueError(
            f"{scope_label} requires Zotero persistent IDs, but {len(missing)} PDF(s) matched Zotero metadata without "
            f"zotero_persistent_id. Fix the Zotero metadata/attachment linkage before ingest. Affected files: {preview}{extra}"
        )


def _get_existing_identities(settings: Settings) -> dict[str, set[str]]:
    try:
        store = GraphStore(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            embedding_model=settings.embedding_model,
        )
        try:
            return store.existing_article_identity_sets()
        finally:
            store.close()
    except Exception:
        # If DB isn't reachable, fall back to no-skip behavior.
        return {
            "article_ids": set(),
            "doi": set(),
            "zotero_persistent_id": set(),
            "zotero_item_key": set(),
            "zotero_attachment_key": set(),
            "title_year_key": set(),
            "title_year_key_normalized": set(),
            "file_stem": set(),
        }


def _get_existing_identity_hits_for_candidates(
    settings: Settings,
    selected_pdfs: list[Path],
    metadata_by_pdf: dict[Path, dict | None],
) -> dict[str, set[str]]:
    dois: set[str] = set()
    persistent_ids: set[str] = set()
    item_keys: set[str] = set()
    attachment_keys: set[str] = set()
    title_year_keys: set[str] = set()
    file_stems: set[str] = set()

    for p in selected_pdfs:
        meta = metadata_by_pdf.get(p) or {}
        doi = _normalize_doi(meta.get("doi"))
        if doi:
            dois.add(doi)
        persistent_id = str(meta.get("zotero_persistent_id") or "").strip()
        if persistent_id:
            persistent_ids.add(persistent_id)
        item_key = str(meta.get("zotero_item_key") or "").strip().lower()
        if item_key:
            item_keys.add(item_key)
        attachment_key = str(meta.get("zotero_attachment_key") or "").strip().lower()
        if attachment_key:
            attachment_keys.add(attachment_key)
        title_year_key = _title_year_key_from_metadata(meta)
        if title_year_key:
            title_year_keys.add(title_year_key)
        stem = p.stem.strip().lower()
        if stem:
            file_stems.add(stem)

    if not any([dois, persistent_ids, item_keys, attachment_keys, title_year_keys, file_stems]):
        return {
            "article_ids": set(),
            "doi": set(),
            "zotero_persistent_id": set(),
            "zotero_item_key": set(),
            "zotero_attachment_key": set(),
            "title_year_key": set(),
            "title_year_key_normalized": set(),
            "file_stem": set(),
        }

    try:
        store = GraphStore(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
            embedding_model=settings.embedding_model,
        )
        try:
            hits = store.existing_identity_hits(
                dois=dois,
                zotero_persistent_ids=persistent_ids,
                zotero_item_keys=item_keys,
                zotero_attachment_keys=attachment_keys,
                title_year_keys=title_year_keys,
                file_stems=file_stems,
            )
        finally:
            store.close()
        # Preserve shape expected by _is_existing_pdf.
        hits["article_ids"] = set()
        return hits
    except Exception:
        # If DB isn't reachable, preserve no-skip fallback behavior.
        return {
            "article_ids": set(),
            "doi": set(),
            "zotero_persistent_id": set(),
            "zotero_item_key": set(),
            "zotero_attachment_key": set(),
            "title_year_key": set(),
            "title_year_key_normalized": set(),
            "file_stem": set(),
        }


def _is_existing_pdf(pdf_path: Path, meta: dict | None, existing: dict[str, set[str]]) -> bool:
    doi = _normalize_doi((meta or {}).get("doi"))
    if doi and doi in existing["doi"]:
        return True

    persistent_id = ((meta or {}).get("zotero_persistent_id") or "").strip()
    if persistent_id and persistent_id in existing["zotero_persistent_id"]:
        return True

    item_key = ((meta or {}).get("zotero_item_key") or "").strip().lower()
    if item_key and item_key in existing["zotero_item_key"]:
        return True

    attachment_key = ((meta or {}).get("zotero_attachment_key") or "").strip().lower()
    if attachment_key and attachment_key in existing["zotero_attachment_key"]:
        return True

    title_year_key = _title_year_key_from_metadata(meta)
    if title_year_key and (
        title_year_key in existing["title_year_key"] or title_year_key in existing["title_year_key_normalized"]
    ):
        return True

    stem = pdf_path.stem.lower()
    return stem in existing["file_stem"]


def choose_pdfs(
    mode: str = "batch",
    source_dir: str | None = None,
    explicit_pdfs: list[str] | None = None,
    skip_existing: bool = True,
    require_metadata: bool = True,
    settings: Settings | None = None,
    partial_count: int = 3,
    source_mode: str = "zotero_db",
) -> list[Path]:
    mode = mode.lower().strip()
    if mode == "test3":
        mode = "batch"
    explicit_pdfs = explicit_pdfs or []

    cfg = settings or Settings()
    resolved_source_dir = source_dir or cfg.pdf_source_dir
    partial_n = max(1, int(partial_count))
    source_mode = (source_mode or "zotero_db").strip().lower() or "zotero_db"

    if mode == "custom":
        selected = [_resolve_custom_pdf_path(p, resolved_source_dir) for p in explicit_pdfs]
    elif source_mode == "zotero_db":
        db_path_raw = (cfg.zotero_db_path or "").strip()
        if db_path_raw:
            db_path = resolve_input_path(db_path_raw)
        else:
            raise ValueError("Zotero-first ingest requires ZOTERO_DB_PATH to be configured.")
        if not db_path.exists():
            raise FileNotFoundError(f"Zotero DB not found: {db_path}")
        storage_root_raw = (cfg.zotero_storage_root or "").strip()
        storage_root = storage_root_raw or str(db_path.parent / "storage")
        rows = load_zotero_entries(str(db_path), storage_root)
        if bool(cfg.zotero_require_persistent_id):
            missing_pid_rows = [r for r in rows if not str(r.get("zotero_persistent_id") or "").strip()]
            if missing_pid_rows:
                sample = ", ".join(
                    str(r.get("attachment_path") or r.get("attachment_path_raw") or r.get("title") or "<unknown>")
                    for r in missing_pid_rows[:10]
                )
                extra = "" if len(missing_pid_rows) <= 10 else f" (+{len(missing_pid_rows) - 10} more)"
                raise ValueError(
                    "Zotero-first ingest requires zotero_persistent_id for every PDF attachment row, but "
                    f"{len(missing_pid_rows)} row(s) were missing it. Fix Zotero parent/attachment linkage first. "
                    f"Examples: {sample}{extra}"
                )
        resolver = ZoteroAttachmentResolver(cfg)
        try:
            resolved_candidates: list[Path] = []
            for row in rows:
                resolution = resolver.resolve(row)
                if resolution.path is not None:
                    resolved_candidates.append(resolution.path)
        finally:
            resolver.close()
        dedup: dict[str, Path] = {}
        for p in resolved_candidates:
            dedup[str(p)] = p
        all_pdfs = sorted(dedup.values(), key=lambda p: str(p).lower())
        if mode == "all":
            selected = all_pdfs
        elif mode == "batch":
            readable = [p for p in all_pdfs if _has_pdf_header(p)]
            selected = readable
        else:
            raise ValueError("Unsupported mode. Use 'batch', 'all', or 'custom'.")
    else:
        source_root = resolve_input_path(resolved_source_dir)
        cache_root = resolve_input_path(cfg.zip_pdf_cache_dir)
        all_pdfs, _source_stats = collect_source_pdfs(
            source_root=source_root,
            cache_root=cache_root,
            include_zip=bool(cfg.zip_pdf_enable),
        )
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
    metadata_index = _load_metadata_index_for_settings(cfg) if (skip_existing or require_metadata) else None
    metadata_by_pdf: dict[Path, dict | None] = {}
    if metadata_index is not None:
        for p in selected:
            metadata_by_pdf[p] = find_metadata_for_pdf(metadata_index, p.name, str(p))
        _require_zotero_persistent_ids(cfg, metadata_by_pdf, scope_label="PDF selection")

    if skip_existing:
        existing = _get_existing_identity_hits_for_candidates(cfg, selected, metadata_by_pdf)
        selected = [p for p in selected if not _is_existing_pdf(p, metadata_by_pdf.get(p), existing)]

    if require_metadata:
        selected = [p for p in selected if metadata_by_pdf.get(p)]

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
    parser_mode = _citation_parser_mode(settings)
    metadata_index = _load_metadata_index_for_settings(settings)
    metadata_by_pdf = {p: find_metadata_for_pdf(metadata_index, p.name, str(p)) for p in selected_pdfs}
    _require_zotero_persistent_ids(settings, metadata_by_pdf, scope_label="Ingest")

    existing = _get_existing_identity_hits_for_candidates(settings, selected_pdfs, metadata_by_pdf) if skip_existing else {
        "article_ids": set(),
        "doi": set(),
        "zotero_persistent_id": set(),
        "zotero_item_key": set(),
        "zotero_attachment_key": set(),
        "title_year_key": set(),
        "title_year_key_normalized": set(),
        "file_stem": set(),
    }
    skipped_existing = [str(p) for p in selected_pdfs if _is_existing_pdf(p, metadata_by_pdf.get(p), existing)]
    selected_pdfs = [p for p in selected_pdfs if not _is_existing_pdf(p, metadata_by_pdf.get(p), existing)]

    require_match = bool(settings.metadata_require_match)
    skipped_no_metadata = [str(p) for p in selected_pdfs if require_match and not metadata_by_pdf.get(p)]
    if require_match:
        selected_pdfs = [p for p in selected_pdfs if metadata_by_pdf.get(p)]

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
                metadata=_prepare_metadata_for_ingest(metadata_by_pdf.get(p)),
            )
            if citation_overrides and article.article_id in citation_overrides:
                article.citations = citation_overrides[article.article_id]
                citation_override_pdfs += 1
            elif parser_mode == "anystyle" and not anystyle_disabled_reason:
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
            elif parser_mode == 'structured_anystyle' and not anystyle_disabled_reason:
                anystyle_attempted += 1
                try:
                    structured = _load_structured_anystyle_cached(
                        pdf_path=p,
                        article_id=article.article_id,
                        settings=settings,
                    )
                    if structured.chunks:
                        article.chunks = structured.chunks
                    article.sections = structured.sections
                    if structured.citations:
                        article.citations = structured.citations
                        anystyle_applied += 1
                    else:
                        anystyle_empty += 1
                except Exception as exc:
                    err = str(exc)
                    anystyle_failed += 1
                    if len(anystyle_failure_samples) < 10:
                        anystyle_failure_samples.append(f'{p.name}: {err}')
                    if settings.anystyle_require_success:
                        raise
                    if _is_global_anystyle_failure(err):
                        anystyle_disabled_reason = err
            article.citations = filter_citations(
                article.citations,
                min_score=settings.citation_min_quality,
            )
            keywords, keyword_audit = extract_keywords(article, settings=settings)
            article.keywords = keywords
            article.keyword_extraction_method = str(keyword_audit.get("method") or "unknown")
            article.keyword_extraction_audit = keyword_audit
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
