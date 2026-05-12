from __future__ import annotations

import copy
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from src.rag.answer_audit import audit_answer_support
from src.rag.config import Settings
from src.rag.llm_answer import ask_grounded, gate_rows_for_synthesis, preprocess_search_query
from src.rag.metadata_provider import find_metadata_for_pdf, find_unmatched_pdfs, iter_pdf_files, load_metadata_index
from src.rag.neo4j_store import GraphStore
from src.rag.paperpile_metadata import load_paperpile_index as _legacy_load_paperpile_index
from src.rag.pipeline import choose_pdfs, ingest_pdfs
from src.rag.path_utils import resolve_input_path
from src.rag.zotero_attachment_resolver import ZoteroAttachmentResolver
from src.rag.zotero_metadata import load_zotero_entries
from src.rag.zotero_notes import summarize_mineru_notes_for_rows
from src.rag.zip_pdf_source import collect_source_pdfs
from src.rag.retrieval import article_claim_match, article_claim_match_by_article_id
from src.rag.search_graphrag import graphrag_retrieve
from src.rag.report_export import citations_to_csv, markdown_to_pdf_bytes, to_markdown


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "webapp" / "static"
SYNC_SCRIPT = ROOT / "scripts" / "sync_pdfs_from_gdrive.sh"
DOTENV_PATH = ROOT / ".env"
LOGGER = logging.getLogger(__name__)
DEFAULT_ASK_SCORE_THRESHOLD = float(os.getenv("RA_ASK_SCORE_THRESHOLD", "1.0"))
DEFAULT_ASK_RETRIEVAL_POOL = int(os.getenv("RA_ASK_RETRIEVAL_POOL", "30"))
_ZOTERO_BROWSE_CACHE_TTL_SECONDS = 30.0
_zotero_browse_cache_lock = threading.Lock()
_zotero_browse_cache: dict[tuple[str, str], dict[str, Any]] = {}


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    alias_map = {
        "OpenAPIKey": "OPENAI_API_KEY",
        "OPENAPIKEY": "OPENAI_API_KEY",
    }
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = alias_map.get(k.strip(), k.strip())
        val = v.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv(DOTENV_PATH)


def load_paperpile_index(path: str) -> dict:
    # Backward-compatible import point for tests and legacy workflows.
    return _legacy_load_paperpile_index(path)


def _load_metadata_index_for_settings(settings: Settings):
    backend = (settings.metadata_backend or "").strip().lower()
    if backend == "paperpile":
        legacy = load_paperpile_index(settings.paperpile_json)
        from src.rag.metadata_provider import MetadataIndex

        return MetadataIndex(
            backend="paperpile",
            by_basename=legacy,
            by_normalized={},
            by_path_normalized={},
        )
    return load_metadata_index(settings)


def _default_pdf_source_dir() -> str:
    try:
        return Settings().pdf_source_dir
    except Exception:
        return r"\\192.168.0.37\pooled\media\Books\pdfs"


def _diagnostics_pdf_root() -> Path:
    configured = Path(_default_pdf_source_dir())
    if configured.exists():
        return configured
    legacy = Path("pdfs")
    if legacy.exists():
        return legacy
    return configured


def _openai_api_key_set() -> bool:
    primary = os.getenv("OPENAI_API_KEY", "").strip()
    alias = os.getenv("OpenAPIKey", "").strip()
    return bool(primary or alias)

app = FastAPI(title="archaResearch Asssistant", version="2026.05.12.161211")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(RuntimeError)
async def runtime_error_handler(_request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc) or "Runtime error"})


@app.exception_handler(Exception)
async def unhandled_error_handler(_request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled webapp exception", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": str(exc) or "Internal server error"})


class SyncRequest(BaseModel):
    dry_run: bool = False
    source_dir: str = Field(default_factory=_default_pdf_source_dir)
    source_mode: str = Field(default="zotero_db", pattern="^(filesystem|zotero_db)$")
    run_ingest: bool = True
    ingest_skip_existing: bool = True


class IngestRequest(BaseModel):
    mode: str = Field(default="batch", pattern="^(batch|all|custom|test3)$")
    source_mode: str = Field(default="zotero_db", pattern="^(filesystem|zotero_db)$")
    source_dir: str = Field(default_factory=_default_pdf_source_dir)
    pdfs: list[str] = Field(default_factory=list)
    override_existing: bool = False
    partial_count: int = Field(default=3, ge=1, le=5000)


class QueryRequest(BaseModel):
    query: str
    limit: int = Field(default=20, ge=1, le=20)
    limit_scope: str = Field(default="papers", pattern="^(papers|chunks)$")
    chunks_per_paper: int = Field(default=8, ge=1, le=20)
    score_threshold: float | None = Field(default=None, ge=0.0)


class ArticleLookupRequest(BaseModel):
    citekeys: list[str] = Field(default_factory=list, min_length=1, max_length=500)
    chunk_limit: int = Field(default=3, ge=1, le=20)


class ArticleClaimMatchRequest(BaseModel):
    claim_text: str
    top_k: int = Field(default=3, ge=1, le=10)


class AskRequest(BaseModel):
    question: str
    rag_results: int | None = Field(default=None, ge=1, le=30)
    score_threshold: float | None = Field(default=DEFAULT_ASK_SCORE_THRESHOLD, ge=0.0)
    retrieval_pool: int = Field(default=DEFAULT_ASK_RETRIEVAL_POOL, ge=1, le=100)
    model: str | None = None
    enforce_citations: bool = True
    preprocess_search: bool = True


class AskExportRequest(BaseModel):
    report: dict[str, Any]
    format: str = Field(default="markdown", pattern="^(markdown|csv|pdf)$")


class IngestPreviewRequest(BaseModel):
    mode: str = Field(default="batch", pattern="^(batch|all|custom|test3)$")
    source_mode: str = Field(default="zotero_db", pattern="^(filesystem|zotero_db)$")
    source_dir: str = Field(default_factory=_default_pdf_source_dir)
    pdfs: list[str] = Field(default_factory=list)
    override_existing: bool = False
    partial_count: int = Field(default=3, ge=1, le=5000)

class ZoteroBrowseRequest(BaseModel):
    query: str = ""
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0, le=5000)
    available_only: bool = True


class ZoteroSelectionIngestRequest(BaseModel):
    zotero_persistent_ids: list[str] = Field(default_factory=list, min_length=1, max_length=500)
    reingest: bool = False

    @field_validator("zotero_persistent_ids")
    @classmethod
    def _dedupe_ids(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = (raw or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            cleaned.append(value)
        if not cleaned:
            raise ValueError("At least one Zotero persistent id is required.")
        return cleaned


@dataclass
class JobState:
    name: str
    status: str = "idle"
    terminal_reason: str | None = None
    cancel_requested: bool = False
    stop_state: str | None = None
    request_id: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    progress_percent: float = 0.0
    progress_message: str = "Idle"
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    proc: subprocess.Popen | None = None


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs = {
            "sync": JobState(name="sync"),
            "ingest": JobState(name="ingest"),
            "query": JobState(name="query"),
        }

    def start(self, name: str, runner: Callable[[JobState], dict[str, Any]]) -> dict[str, Any]:
        job = None
        with self._lock:
            job = self._jobs[name]
            if job.status == "running":
                raise HTTPException(status_code=409, detail=f"{name} job is already running.")
            job.status = "running"
            job.terminal_reason = None
            job.cancel_requested = False
            job.stop_state = None
            job.request_id = str(uuid.uuid4())
            job.started_at = time.time()
            job.finished_at = None
            job.error = None
            job.result = None
            job.cancel_event = threading.Event()
            job.proc = None
            job.progress_percent = 0.0
            job.progress_message = "Starting..."

            def wrapped() -> None:
                try:
                    result = runner(job)
                    with self._lock:
                        if job.cancel_event.is_set():
                            job.status = "cancelled"
                            job.terminal_reason = "cancelled"
                        else:
                            job.status = "completed"
                            job.terminal_reason = "completed"
                        job.result = result
                        job.finished_at = time.time()
                except Exception as exc:
                    with self._lock:
                        if job.cancel_event.is_set():
                            job.status = "cancelled"
                            job.terminal_reason = "cancelled"
                        else:
                            job.status = "failed"
                            job.terminal_reason = "failed"
                        job.error = str(exc)
                        job.finished_at = time.time()

            job.thread = threading.Thread(target=wrapped, daemon=True)
            job.thread.start()
        return self.status(name)

    def stop(self, name: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs[name]
            if job.status != "running":
                if job.status == "idle":
                    job.stop_state = "noop_idle"
                else:
                    job.stop_state = "noop_terminal"
            else:
                if job.cancel_requested:
                    job.stop_state = "noop_cancelling"
                else:
                    job.cancel_event.set()
                    job.cancel_requested = True
                    job.stop_state = "accepted"
                    job.progress_message = "Cancellation requested."
                    if job.proc and job.proc.poll() is None:
                        job.proc.terminate()
        return self.status(name)

    def status(self, name: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs[name]
            lifecycle_state = job.status
            if job.status == "running" and job.cancel_requested:
                lifecycle_state = "cancelling"
            return {
                "name": job.name,
                "status": job.status,
                "lifecycle_state": lifecycle_state,
                "terminal_reason": job.terminal_reason,
                "cancel_requested": job.cancel_requested,
                "stop_state": job.stop_state,
                "request_id": job.request_id,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "error": job.error,
                "result": job.result,
                "progress_percent": round(job.progress_percent, 1),
                "progress_message": job.progress_message,
            }

    def set_progress(self, name: str, percent: float, message: str) -> None:
        with self._lock:
            job = self._jobs[name]
            job.progress_percent = max(0.0, min(100.0, float(percent)))
            job.progress_message = message

    def set_result(self, name: str, result: dict[str, Any] | None) -> None:
        with self._lock:
            job = self._jobs[name]
            job.result = copy.deepcopy(result) if result is not None else None


jobs = JobManager()


def _summary_optional_fields(summary: Any) -> dict[str, Any]:
    return {
        "citation_override_pdfs": getattr(summary, "citation_override_pdfs", 0),
        "reference_parse_attempted_pdfs": getattr(summary, "reference_parse_attempted_pdfs", getattr(summary, "anystyle_attempted_pdfs", 0)),
        "reference_parse_applied_pdfs": getattr(summary, "reference_parse_applied_pdfs", getattr(summary, "anystyle_applied_pdfs", 0)),
        "reference_parse_empty_pdfs": getattr(summary, "reference_parse_empty_pdfs", getattr(summary, "anystyle_empty_pdfs", 0)),
        "reference_parse_failed_pdfs": getattr(summary, "reference_parse_failed_pdfs", getattr(summary, "anystyle_failed_pdfs", 0)),
        "reference_parse_disabled_reason": getattr(summary, "reference_parse_disabled_reason", getattr(summary, "anystyle_disabled_reason", None)),
        "reference_parse_failure_samples": list(getattr(summary, "reference_parse_failure_samples", getattr(summary, "anystyle_failure_samples", [])) or []),
        "qwen_attempted_pdfs": getattr(summary, "qwen_attempted_pdfs", 0),
        "qwen_applied_pdfs": getattr(summary, "qwen_applied_pdfs", 0),
        "qwen_empty_pdfs": getattr(summary, "qwen_empty_pdfs", 0),
        "qwen_failed_pdfs": getattr(summary, "qwen_failed_pdfs", 0),
        "qwen_disabled_reason": getattr(summary, "qwen_disabled_reason", None),
        "qwen_failure_samples": list(getattr(summary, "qwen_failure_samples", []) or []),
    }


def _require_api_token(authorization: str | None) -> None:
    expected = os.getenv("API_BEARER_TOKEN", "").strip()
    if not expected:
        return
    header = (authorization or "").strip()
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = header.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid bearer token.")


def _count_local_pdfs(root_dir: str) -> int:
    root = Path(root_dir)
    return sum(1 for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")


def _sample_valid_pdf_headers(root_dir: str, sample_limit: int = 300) -> dict[str, int]:
    root = Path(root_dir)
    checked = 0
    valid = 0
    for p in root.rglob("*"):
        if checked >= sample_limit:
            break
        if not p.is_file() or p.suffix.lower() != ".pdf":
            continue
        checked += 1
        try:
            with open(p, "rb") as f:
                if f.read(4) == b"%PDF":
                    valid += 1
        except Exception:
            pass
    return {"checked": checked, "valid": valid}


def _count_remote_pdfs(remote_path: str) -> int | None:
    try:
        proc = subprocess.run(
            [
                "rclone",
                "lsf",
                remote_path,
                "--recursive",
                "--files-only",
                "--include",
                "*.pdf",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if proc.returncode != 0:
            return None
        lines = [x for x in proc.stdout.splitlines() if x.strip()]
        return len(lines)
    except (subprocess.TimeoutExpired, Exception):
        return None


def _zotero_graph_presence(settings: Settings, persistent_ids: set[str]) -> set[str]:
    if not persistent_ids:
        return set()
    try:
        store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
        try:
            hits = store.existing_identity_hits(
                dois=set(),
                zotero_persistent_ids=set(persistent_ids),
                zotero_item_keys=set(),
                zotero_attachment_keys=set(),
                title_year_keys=set(),
                file_stems=set(),
            )
        finally:
            store.close()
        return set(hits.get("zotero_persistent_id", set()) or set())
    except Exception:
        return set()


def _browse_query_matches(row: dict[str, Any], query_text: str) -> bool:
    if not query_text:
        return True
    fields = [
        row.get("title"),
        row.get("doi"),
        row.get("journal"),
        row.get("publisher"),
        row.get("zotero_persistent_id"),
        row.get("zotero_item_key"),
        row.get("zotero_attachment_key"),
        " ".join(row.get("authors") or []),
    ]
    haystack = "\n".join(str(x or "") for x in fields).lower()
    return query_text in haystack


def _zotero_browse_cache_key(db_path: Path, storage_root: str) -> str:
    try:
        stat = db_path.stat()
        return f"{db_path}:{storage_root}:{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        return f"{db_path}:{storage_root}:missing"


def _get_cached_zotero_rows(cache_key: str) -> list[dict[str, Any]] | None:
    with _zotero_browse_cache_lock:
        entry = _zotero_browse_cache.get(("rows", cache_key))
        if not entry:
            return None
        if (time.time() - float(entry["ts"])) > _ZOTERO_BROWSE_CACHE_TTL_SECONDS:
            _zotero_browse_cache.pop(("rows", cache_key), None)
            return None
        return list(entry["value"])


def _set_cached_zotero_rows(cache_key: str, rows: list[dict[str, Any]]) -> None:
    with _zotero_browse_cache_lock:
        _zotero_browse_cache[("rows", cache_key)] = {"ts": time.time(), "value": list(rows)}


def _get_cached_zotero_resolution(cache_key: str, row: dict[str, Any]) -> Any | None:
    pid = str(row.get("zotero_persistent_id") or "").strip()
    attachment_key = str(row.get("zotero_attachment_key") or "").strip()
    raw_path = str(row.get("attachment_path_raw") or "").strip()
    resolved_path = str(row.get("attachment_path") or "").strip()
    row_key = pid or attachment_key or raw_path or resolved_path
    if not row_key:
        return None
    with _zotero_browse_cache_lock:
        entry = _zotero_browse_cache.get(("resolution", cache_key, row_key))
        if not entry:
            return None
        if entry.get("fingerprint") != (raw_path, resolved_path):
            _zotero_browse_cache.pop(("resolution", cache_key, row_key), None)
            return None
        if (time.time() - float(entry["ts"])) > _ZOTERO_BROWSE_CACHE_TTL_SECONDS:
            _zotero_browse_cache.pop(("resolution", cache_key, row_key), None)
            return None
        return entry["value"]


def _set_cached_zotero_resolution(cache_key: str, row: dict[str, Any], resolution: Any) -> None:
    pid = str(row.get("zotero_persistent_id") or "").strip()
    attachment_key = str(row.get("zotero_attachment_key") or "").strip()
    raw_path = str(row.get("attachment_path_raw") or "").strip()
    resolved_path = str(row.get("attachment_path") or "").strip()
    row_key = pid or attachment_key or raw_path or resolved_path
    if not row_key:
        return
    with _zotero_browse_cache_lock:
        _zotero_browse_cache[("resolution", cache_key, row_key)] = {
            "ts": time.time(),
            "fingerprint": (raw_path, resolved_path),
            "value": resolution,
        }


def _browse_zotero_pdf_items(settings: Settings, *, query: str = "", limit: int = 100, offset: int = 0, available_only: bool = True) -> dict[str, Any]:
    db_path_raw = (settings.zotero_db_path or "").strip()
    if not db_path_raw:
        raise RuntimeError("Zotero browse requires ZOTERO_DB_PATH to be configured.")
    db_path = resolve_input_path(db_path_raw)
    if not db_path.exists():
        raise RuntimeError(f"Zotero DB not found: {db_path}")

    storage_root_raw = (settings.zotero_storage_root or "").strip()
    storage_root = storage_root_raw or str(db_path.parent / "storage")
    cache_key = _zotero_browse_cache_key(db_path, storage_root)
    rows = _get_cached_zotero_rows(cache_key)
    if rows is None:
        rows = load_zotero_entries(str(db_path), storage_root)
        _set_cached_zotero_rows(cache_key, rows)

    query_text = (query or "").strip().lower()
    candidate_rows = [row for row in rows if _browse_query_matches(row, query_text)]

    resolver = ZoteroAttachmentResolver(settings)
    try:
        resolved_rows: list[dict[str, Any]] = []
        for row in candidate_rows:
            resolution = _get_cached_zotero_resolution(cache_key, row)
            if resolution is None:
                resolution = resolver.resolve(row)
                _set_cached_zotero_resolution(cache_key, row, resolution)
            if available_only and resolution.path is None:
                continue
            merged = dict(row)
            merged["resolution"] = resolution
            resolved_rows.append(merged)
    finally:
        resolver.close()

    resolved_rows.sort(key=lambda row: (str(row.get("title") or "").lower(), str(row.get("zotero_persistent_id") or "").lower()))
    total = len(resolved_rows)
    window = resolved_rows[offset : offset + limit]
    present_in_graph = _zotero_graph_presence(
        settings,
        {
            str(row.get("zotero_persistent_id") or "").strip()
            for row in window
            if str(row.get("zotero_persistent_id") or "").strip()
        },
    )

    items: list[dict[str, Any]] = []
    for row in window:
        resolution = row["resolution"]
        persistent_id = str(row.get("zotero_persistent_id") or "").strip()
        items.append(
            {
                "title": row.get("title"),
                "year": row.get("year"),
                "authors": row.get("authors") or [],
                "doi": row.get("doi"),
                "journal": row.get("journal"),
                "publisher": row.get("publisher"),
                "zotero_persistent_id": persistent_id or None,
                "zotero_item_key": row.get("zotero_item_key"),
                "zotero_attachment_key": row.get("zotero_attachment_key"),
                "available": resolution.path is not None,
                "exists_in_graph": persistent_id in present_in_graph if persistent_id else False,
                "path": str(resolution.path) if resolution.path is not None else None,
                "resolver": resolution.resolver or None,
                "acquisition_source": resolution.acquisition_source or None,
                "issue_code": resolution.issue_code or None,
                "issue_detail": resolution.detail or None,
                "provenance": resolution.provenance,
            }
        )

    return {
        "ok": True,
        "query": query,
        "offset": offset,
        "limit": limit,
        "available_only": available_only,
        "total": total,
        "items": items,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.ico", media_type="image/x-icon")


@app.get("/api/version")
def version_info() -> dict[str, str]:
    return {
        "status": "ok",
        "version": app.version,
        "title": app.title,
    }


@app.get("/api/health")
def health() -> dict:
    settings = Settings()
    store = GraphStore(
        settings.neo4j_uri,
        settings.neo4j_user,
        settings.neo4j_password,
        settings.embedding_model,
        load_embedder=False,
    )
    try:
        stats = store.graph_stats()
    finally:
        store.close()
    return {"status": "ok", "version": app.version, "neo4j_uri": settings.neo4j_uri, "stats": stats}


@app.get("/api/diagnostics")
def diagnostics() -> dict:
    settings = Settings()
    diag: dict[str, Any] = {}
    checks: list[dict[str, Any]] = []

    # Config and file checks
    metadata_backend = (settings.metadata_backend or "").strip().lower()
    source_path = settings.paperpile_json if metadata_backend == "paperpile" else settings.zotero_db_path
    metadata_path = Path(source_path) if source_path else None
    checks.append(
        {
            "name": "metadata_source_exists",
            "ok": bool(metadata_path and metadata_path.exists()),
            "details": str(metadata_path) if metadata_path else "Not configured",
        }
    )
    checks.append(
        {
            "name": "sync_script_exists",
            "ok": SYNC_SCRIPT.exists(),
            "details": str(SYNC_SCRIPT),
        }
    )
    checks.append(
        {
            "name": "openai_api_key_set",
            "ok": _openai_api_key_set(),
            "details": "OPENAI_API_KEY present in environment",
        }
    )

    # Metadata coverage checks
    metadata_index = _load_metadata_index_for_settings(settings)
    pdf_root = _diagnostics_pdf_root()
    pdf_files = iter_pdf_files(pdf_root) if pdf_root.exists() else []
    unmatched = find_unmatched_pdfs(pdf_root, metadata_index) if pdf_root.exists() else []
    total_local_pdfs = len(pdf_files)
    with_meta = total_local_pdfs - len(unmatched)
    diag["pdfs_total"] = total_local_pdfs
    diag["pdfs_with_metadata"] = with_meta
    diag["pdfs_unmatched"] = len(unmatched)
    diag["unmatched_sample"] = [str(p) for p in unmatched[:20]]
    checks.append(
        {
            "name": "metadata_coverage_nonzero",
            "ok": with_meta > 0,
            "details": f"{with_meta}/{total_local_pdfs} local PDFs matched to {metadata_index.backend} metadata",
        }
    )
    hdr = _sample_valid_pdf_headers(str(pdf_root), sample_limit=300) if pdf_root.exists() else {"checked": 0, "valid": 0}
    diag["pdf_header_sample"] = hdr
    checks.append(
        {
            "name": "pdf_headers_sample_quality",
            "ok": (hdr["checked"] == 0) or (hdr["valid"] / max(1, hdr["checked"]) >= 0.5),
            "details": f"{hdr['valid']}/{hdr['checked']} sampled PDFs have valid %PDF header",
        }
    )

    # Neo4j connectivity and stats check
    neo4j_ok = False
    neo4j_stats = {}
    try:
        store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
        try:
            neo4j_stats = store.graph_stats()
            neo4j_ok = True
        finally:
            store.close()
    except Exception as exc:
        neo4j_stats = {"error": str(exc)}
    checks.append(
        {
            "name": "neo4j_connectivity",
            "ok": neo4j_ok,
            "details": neo4j_stats,
        }
    )
    diag["neo4j_stats"] = neo4j_stats

    overall_ok = all(bool(c.get("ok")) for c in checks)
    return {
        "ok": overall_ok,
        "checks": checks,
        "details": diag,
    }


@app.post("/api/sync")
def sync_pdfs(req: SyncRequest, authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)

    def run(job: JobState) -> dict:
        jobs.set_progress("sync", 0.0, "Checking local source")
        settings = Settings()
        source_mode = (req.source_mode or "zotero_db").strip().lower() or "zotero_db"
        configured_source = (req.source_dir or "").strip() or settings.pdf_source_dir
        pdf_root = resolve_input_path(configured_source)
        source_stats: dict[str, Any] = {}
        pdf_files: list[Path] = []

        if job.cancel_event.is_set():
            jobs.set_progress("sync", 0.0, "Cancelled")
            return {"ok": False, "cancelled": True}

        if source_mode == "zotero_db":
            # Reserve first 5% for anti-join preprocessing.
            jobs.set_progress("sync", 2.0, "Loading Zotero PDF attachment metadata")
            db_path_raw = (settings.zotero_db_path or "").strip()
            if db_path_raw:
                db_path = resolve_input_path(db_path_raw)
            else:
                candidates = [
                    Path.home() / "Zotero" / "zotero.sqlite",
                    Path("/mnt/c/Users") / os.getenv("USER", "") / "Zotero" / "zotero.sqlite",
                ]
                for p in Path("/mnt/c/Users").glob("*/Zotero/zotero.sqlite"):
                    candidates.append(p)
                db_path = next((p for p in candidates if p and p.exists()), candidates[0])
            if not db_path.exists():
                raise RuntimeError(
                    f"Zotero DB not found: {db_path}. Set ZOTERO_DB_PATH to your zotero.sqlite path."
                )

            storage_root_raw = (settings.zotero_storage_root or "").strip()
            storage_root = storage_root_raw or str(db_path.parent / "storage")
            rows = load_zotero_entries(str(db_path), storage_root)
            total_rows = len(rows)
            jobs.set_progress("sync", 3.0, f"Loaded {total_rows} Zotero PDF attachment rows")
            mineru_note_summary = summarize_mineru_notes_for_rows(rows, zotero_db_path=str(db_path))

            if bool(getattr(settings, "zotero_require_persistent_id", False)):
                missing_pid_rows = [r for r in rows if not str(r.get("zotero_persistent_id") or "").strip()]
                if missing_pid_rows:
                    sample = ", ".join(
                        str(r.get("attachment_path") or r.get("attachment_path_raw") or r.get("title") or "<unknown>")
                        for r in missing_pid_rows[:10]
                    )
                    extra = "" if len(missing_pid_rows) <= 10 else f" (+{len(missing_pid_rows) - 10} more)"
                    raise RuntimeError(
                        "Zotero-first sync requires zotero_persistent_id for every PDF attachment row, but "
                        f"{len(missing_pid_rows)} row(s) were missing it. Fix Zotero parent/attachment linkage first. "
                        f"Examples: {sample}{extra}"
                    )

            jobs.set_progress("sync", 4.0, "Reading existing Zotero identifiers from Neo4j")
            neo4j_zotero_ids: set[str] = set()
            try:
                store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
                try:
                    with store.driver.session() as session:
                        neo4j_zotero_ids = {
                            str(r["pid"])
                            for r in session.run(
                                """
                                MATCH (a:Article)
                                WHERE coalesce(a.zotero_persistent_id, '') <> ''
                                RETURN DISTINCT a.zotero_persistent_id AS pid
                                """
                            )
                            if str(r["pid"] or "").strip()
                        }
                finally:
                    store.close()
            except Exception:
                neo4j_zotero_ids = set()

            zotero_by_pid: dict[str, dict[str, Any]] = {}
            for idx, row in enumerate(rows, start=1):
                pid = str(row.get("zotero_persistent_id") or "").strip()
                if not pid:
                    pid = (
                        str(row.get("attachment_path") or "").strip()
                        or str(row.get("attachment_path_raw") or "").strip()
                        or str(row.get("zotero_attachment_key") or "").strip()
                        or f"row::{idx}"
                    )
                if pid in zotero_by_pid:
                    continue
                zotero_by_pid[pid] = row

            missing_rows = [row for pid, row in zotero_by_pid.items() if pid not in neo4j_zotero_ids]
            initial_missing_count = len(missing_rows)
            jobs.set_progress("sync", 5.0, f"Anti-join complete: {len(missing_rows)} PDFs missing in Neo4j")

            jobs.set_progress("sync", 7.0, f"Reconciling {len(missing_rows)} existing Neo4j articles")
            reconcile_summary: dict[str, Any] | None = None
            if missing_rows and neo4j_zotero_ids:
                try:
                    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
                    try:
                        reconcile_summary = store.reconcile_zotero_persistent_ids(missing_rows)
                    finally:
                        store.close()

                    jobs.set_progress(
                        "sync",
                        10.0,
                        "Reconcile complete: "
                        f"{int(reconcile_summary.get('matched', 0))} matched, "
                        f"{int(reconcile_summary.get('unresolved', 0))} unresolved, "
                        f"{int(reconcile_summary.get('ambiguous', 0))} ambiguous",
                    )

                    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
                    try:
                        with store.driver.session() as session:
                            neo4j_zotero_ids = {
                                str(r["pid"])
                                for r in session.run(
                                    """
                                    MATCH (a:Article)
                                    WHERE coalesce(a.zotero_persistent_id, '') <> ''
                                    RETURN DISTINCT a.zotero_persistent_id AS pid
                                    """
                                )
                                if str(r["pid"] or "").strip()
                            }
                    finally:
                        store.close()

                    missing_rows = [row for pid, row in zotero_by_pid.items() if pid not in neo4j_zotero_ids]
                except Exception:
                    reconcile_summary = None

            ingest_candidates: list[Path] = []
            ingest_candidate_rows_by_path: dict[str, dict[str, Any]] = {}
            path_issue_counts: dict[str, int] = {}
            path_issue_samples: dict[str, list[str]] = {}
            for idx, row in enumerate(missing_rows, start=1):
                if job.cancel_event.is_set():
                    jobs.set_progress("sync", 0.0, "Cancelled")
                    return {"ok": False, "cancelled": True}
                if missing_rows and (idx == 1 or idx % 25 == 0 or idx == len(missing_rows)):
                    progress = 10.0 + ((idx / len(missing_rows)) * 2.0)
                    jobs.set_progress("sync", progress, f"Resolving attachment paths {idx}/{len(missing_rows)}")
                candidate_raw = str(row.get("attachment_path") or "").strip()
                if candidate_raw:
                    try:
                        resolved_candidate = resolve_input_path(candidate_raw)
                        ingest_candidates.append(resolved_candidate)
                        ingest_candidate_rows_by_path.setdefault(str(resolved_candidate), row)
                        continue
                    except Exception as exc:
                        issue_code = "attachment_path_resolution_error"
                        path_issue_counts[issue_code] = path_issue_counts.get(issue_code, 0) + 1
                        bucket = path_issue_samples.setdefault(issue_code, [])
                        if len(bucket) < 10:
                            bucket.append(f"{candidate_raw} :: {exc}")
                else:
                    issue_code = "missing_attachment_path"
                    path_issue_counts[issue_code] = path_issue_counts.get(issue_code, 0) + 1
                    detail = str(row.get("attachment_path_raw") or "").strip()
                    if detail:
                        bucket = path_issue_samples.setdefault(issue_code, [])
                        if len(bucket) < 10:
                            bucket.append(detail)

            dedup: dict[str, Path] = {}
            for p in ingest_candidates:
                dedup[str(p)] = p
            ingest_candidates = sorted(dedup.values(), key=lambda p: str(p).lower())
            ingest_candidate_rows = [ingest_candidate_rows_by_path[str(p)] for p in ingest_candidates if str(p) in ingest_candidate_rows_by_path]
            pdf_files = list(ingest_candidates)
            source_stats = {
                "source_mode": "zotero_db",
                "zotero_db_path": str(db_path),
                "zotero_storage_root": storage_root,
                "zotero_attachment_rows": total_rows,
                "zotero_mineru_notes_rows_checked": mineru_note_summary["rows_checked"],
                "zotero_mineru_notes_attached": mineru_note_summary["mineru_notes_attached"],
                "zotero_mineru_notes_missing": mineru_note_summary["mineru_notes_missing"],
                "zotero_unique_parent_items": len(zotero_by_pid),
                "zotero_missing_detected_initial": initial_missing_count,
                "zotero_missing_in_neo4j": len(missing_rows),
                "zotero_paths_found": len(ingest_candidates),
                "zotero_paths_missing": sum(path_issue_counts.values()),
                "zotero_path_resolver_counts": {"direct_attachment_path": len(ingest_candidates)},
                "zotero_path_issue_counts": path_issue_counts,
                "zotero_path_issue_samples": path_issue_samples,
            }
            if reconcile_summary is not None:
                source_stats["zotero_reconciled_existing"] = int(reconcile_summary.get("matched", 0))
                source_stats["zotero_reconcile_unresolved"] = int(reconcile_summary.get("unresolved", 0))
                source_stats["zotero_reconcile_ambiguous"] = int(reconcile_summary.get("ambiguous", 0))
                source_stats["zotero_reconcile_duration_seconds"] = float(
                    reconcile_summary.get("duration_seconds", 0.0) or 0.0
                )
                source_stats["zotero_reconcile_examples"] = list(reconcile_summary.get("examples", []))
                source_stats["zotero_missing_in_neo4j_after_reconcile"] = len(missing_rows)

            total_attachment_ids = {
                int(row.get("zotero_attachment_item_id") or 0)
                for row in rows
                if int(row.get("zotero_attachment_item_id") or 0) > 0
            }
            total_mineru_attached = int(source_stats["zotero_mineru_notes_attached"])
            ingest_candidate_note_summary = summarize_mineru_notes_for_rows(
                ingest_candidate_rows,
                zotero_db_path=str(db_path),
            )
            source_stats["zotero_mineru_notes_attached_for_ingest_candidates"] = int(
                ingest_candidate_note_summary["mineru_notes_attached"]
            )
            source_stats["zotero_mineru_notes_missing_for_ingest_candidates"] = max(
                0,
                len(ingest_candidate_rows) - int(source_stats["zotero_mineru_notes_attached_for_ingest_candidates"]),
            )
            source_stats["zotero_mineru_notes_coverage_percent"] = round(
                (total_mineru_attached / max(1, len(total_attachment_ids))) * 100.0,
                2,
            )

            ingest_summary: dict[str, Any] | None = None
            ingest_ran = bool(req.run_ingest and not req.dry_run)

            if not ingest_candidates:
                jobs.set_progress("sync", 100.0, "Sync complete (no missing Zotero PDFs to ingest)")
                return {
                    "ok": True,
                    "dry_run": bool(req.dry_run),
                    "metadata_backend": settings.metadata_backend,
                    "source_mode": source_mode,
                    "pdf_source_dir": str(pdf_root),
                    "pdf_source_dir_raw": configured_source,
                    "source_stats": source_stats,
                    "pdfs_total": len(zotero_by_pid),
                    "pdfs_with_metadata": len(ingest_candidates),
                    "pdfs_unmatched": 0,
                    "unmatched_sample": [],
                    "ingest_candidate_count": 0,
                    "ingest_ran": False,
                    "ingest_summary": None,
                    "reconcile_summary": reconcile_summary,
                }

            jobs.set_progress("sync", 10.0, f"{len(ingest_candidates)} PDFs need ingest")
            if ingest_ran:
                jobs.set_progress("sync", 12.0, f"Starting ingest for {len(ingest_candidates)} PDFs")

                def on_ingest_progress(percent: float, message: str) -> None:
                    # Map ingest 0..100 to sync 12..99 after detection + reconcile.
                    mapped = 12.0 + (max(0.0, min(100.0, float(percent))) * 0.87)
                    jobs.set_progress("sync", mapped, f"Ingest: {message}")

                summary = ingest_pdfs(
                    selected_pdfs=ingest_candidates,
                    wipe=False,
                    settings=settings,
                    should_cancel=lambda: job.cancel_event.is_set(),
                    skip_existing=bool(req.ingest_skip_existing),
                    progress_callback=on_ingest_progress,
                )
                ingest_summary = {
                    "ingested_articles": summary.ingested_articles,
                    "total_chunks": summary.total_chunks,
                    "total_references": summary.total_references,
                    "selected_pdfs": summary.selected_pdfs,
                    "skipped_existing_pdfs": summary.skipped_existing_pdfs,
                    "skipped_no_metadata_pdfs": summary.skipped_no_metadata_pdfs,
                    "failed_pdfs": summary.failed_pdfs,
                    **_summary_optional_fields(summary),
                }
                try:
                    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
                    try:
                        with store.driver.session() as session:
                            neo4j_zotero_ids = {
                                str(r["pid"])
                                for r in session.run(
                                    """
                                    MATCH (a:Article)
                                    WHERE coalesce(a.zotero_persistent_id, '') <> ''
                                    RETURN DISTINCT a.zotero_persistent_id AS pid
                                    """
                                )
                                if str(r["pid"] or "").strip()
                            }
                    finally:
                        store.close()
                    source_stats["zotero_missing_in_neo4j_after_ingest"] = sum(
                        1 for pid in zotero_by_pid.keys() if pid not in neo4j_zotero_ids
                    )
                except Exception:
                    source_stats["zotero_missing_in_neo4j_after_ingest"] = None

            jobs.set_progress("sync", 100.0, "Sync complete")
            return {
                "ok": True,
                "dry_run": bool(req.dry_run),
                "metadata_backend": settings.metadata_backend,
                "source_mode": source_mode,
                "pdf_source_dir": str(pdf_root),
                "pdf_source_dir_raw": configured_source,
                "source_stats": source_stats,
                "pdfs_total": len(zotero_by_pid),
                "pdfs_with_metadata": len(ingest_candidates),
                "pdfs_unmatched": 0,
                "unmatched_sample": [],
                "ingest_candidate_count": len(ingest_candidates),
                "ingest_ran": ingest_ran,
                "ingest_summary": ingest_summary,
                "reconcile_summary": reconcile_summary,
            }

        # Filesystem mode keeps the broader scan + match flow.
        jobs.set_progress("sync", 4.0, "Loading metadata index")
        metadata_index = _load_metadata_index_for_settings(settings)
        if job.cancel_event.is_set():
            jobs.set_progress("sync", 4.0, "Cancelled")
            return {"ok": False, "cancelled": True}

        if source_mode != "zotero_db":
            if not pdf_root.exists():
                raise RuntimeError(f"PDF source directory not found: {pdf_root}")

            jobs.set_progress("sync", 6.0, "Collecting PDFs and ZIP sources")
            cache_root = resolve_input_path(settings.zip_pdf_cache_dir)

            def on_zip_progress(i: int, n: int, msg: str) -> None:
                if n <= 0:
                    jobs.set_progress("sync", 10.0, msg)
                    return
                jobs.set_progress("sync", 6.0 + ((i / n) * 4.0), msg)

            pdf_files, source_stats = collect_source_pdfs(
                source_root=pdf_root,
                cache_root=cache_root,
                include_zip=bool(settings.zip_pdf_enable),
                progress_cb=on_zip_progress,
            )
            source_stats["source_mode"] = "filesystem"

        jobs.set_progress("sync", 10.0, "Scanning PDFs for metadata matches")
        total_files = len(pdf_files)
        unmatched: list[Path] = []

        if total_files == 0:
            jobs.set_progress("sync", 100.0, "Sync complete (no PDFs found)")
            return {
                "ok": True,
                "dry_run": bool(req.dry_run),
                "metadata_backend": metadata_index.backend,
                "source_mode": source_mode,
                "pdf_source_dir": str(pdf_root),
                "pdf_source_dir_raw": configured_source,
                "source_stats": source_stats,
                "pdfs_total": 0,
                "pdfs_with_metadata": 0,
                "pdfs_unmatched": 0,
                "unmatched_sample": [],
                "ingest_ran": False,
                "ingest_summary": None,
            }

        for idx, p in enumerate(pdf_files, start=1):
            if job.cancel_event.is_set():
                jobs.set_progress("sync", 0.0, "Cancelled")
                return {"ok": False, "cancelled": True}

            if not find_metadata_for_pdf(metadata_index, p.name, str(p)):
                unmatched.append(p)

            # Reserve 10-40% for per-file scan progress and include current filename.
            progress = 10.0 + ((idx / total_files) * 30.0)
            jobs.set_progress("sync", progress, f"Scanning {idx}/{total_files}: {p.name}")

        matched = total_files - len(unmatched)
        unmatched_set = {str(p) for p in unmatched}
        ingest_summary: dict[str, Any] | None = None
        ingest_ran = bool(req.run_ingest and not req.dry_run)

        if ingest_ran:
            jobs.set_progress("sync", 42.0, "Starting ingest into Neo4j")

            def on_ingest_progress(percent: float, message: str) -> None:
                # Map ingest 0..100 to sync 42..99
                mapped = 42.0 + (max(0.0, min(100.0, float(percent))) * 0.57)
                jobs.set_progress("sync", mapped, f"Ingest: {message}")

            # In strict metadata mode, avoid re-processing known unmatched files.
            ingest_candidates = (
                [p for p in pdf_files if str(p) not in unmatched_set]
                if bool(getattr(settings, "metadata_require_match", False))
                else list(pdf_files)
            )
            summary = ingest_pdfs(
                selected_pdfs=ingest_candidates,
                wipe=False,
                settings=settings,
                should_cancel=lambda: job.cancel_event.is_set(),
                skip_existing=bool(req.ingest_skip_existing),
                progress_callback=on_ingest_progress,
            )
            ingest_summary = {
                "ingested_articles": summary.ingested_articles,
                "total_chunks": summary.total_chunks,
                "total_references": summary.total_references,
                "selected_pdfs": summary.selected_pdfs,
                "skipped_existing_pdfs": summary.skipped_existing_pdfs,
                "skipped_no_metadata_pdfs": summary.skipped_no_metadata_pdfs,
                "failed_pdfs": summary.failed_pdfs,
                **_summary_optional_fields(summary),
            }

        jobs.set_progress("sync", 100.0, "Sync complete")
        return {
            "ok": True,
            "dry_run": bool(req.dry_run),
            "metadata_backend": metadata_index.backend,
            "source_mode": source_mode,
            "pdf_source_dir": str(pdf_root),
            "pdf_source_dir_raw": configured_source,
            "source_stats": source_stats,
            "pdfs_total": total_files,
            "pdfs_with_metadata": matched,
            "pdfs_unmatched": len(unmatched),
            "unmatched_sample": [str(p) for p in unmatched[:30]],
            "ingest_ran": ingest_ran,
            "ingest_summary": ingest_summary,
        }

    return jobs.start("sync", run)


@app.get("/api/sync/status")
def sync_status(authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)
    return jobs.status("sync")


@app.post("/api/sync/stop")
def sync_stop(authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)
    return jobs.stop("sync")


@app.post("/api/zotero/items/search")
def zotero_items_search(req: ZoteroBrowseRequest, authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)
    settings = Settings()
    return _browse_zotero_pdf_items(
        settings,
        query=req.query,
        limit=req.limit,
        offset=req.offset,
        available_only=req.available_only,
    )


@app.post("/api/zotero/items/ingest")
def zotero_items_ingest(req: ZoteroSelectionIngestRequest, authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)

    def run(job: JobState) -> dict:
        settings = Settings()
        jobs.set_progress("ingest", 0.0, "Loading Zotero PDF items")
        browse = _browse_zotero_pdf_items(settings, query="", limit=5000, offset=0, available_only=False)
        by_pid = {
            str(item.get("zotero_persistent_id") or "").strip(): item
            for item in browse["items"]
            if str(item.get("zotero_persistent_id") or "").strip()
        }

        selected_items: list[dict[str, Any]] = []
        missing_ids: list[str] = []
        unavailable_ids: list[str] = []
        for idx, pid in enumerate(req.zotero_persistent_ids, start=1):
            if job.cancel_event.is_set():
                raise RuntimeError("Ingest cancelled by user.")
            jobs.set_progress(
                "ingest",
                min(20.0, idx / max(1, len(req.zotero_persistent_ids)) * 20.0),
                f"Resolving Zotero item {idx}/{len(req.zotero_persistent_ids)}",
            )
            item = by_pid.get(pid)
            if item is None:
                missing_ids.append(pid)
                continue
            if not item.get("available") or not item.get("path"):
                unavailable_ids.append(pid)
                continue
            selected_items.append(item)

        if missing_ids:
            raise RuntimeError(f"Unknown Zotero persistent id(s): {', '.join(missing_ids[:10])}")
        if not selected_items:
            raise RuntimeError("No selected Zotero PDF items were available for ingest.")

        selected_pdfs = [Path(str(item["path"])) for item in selected_items]
        live_selected_items = [
            {
                "zotero_persistent_id": item.get("zotero_persistent_id"),
                "title": item.get("title"),
                "path": item.get("path"),
                "exists_in_graph": item.get("exists_in_graph"),
                "resolver": item.get("resolver"),
                "acquisition_source": item.get("acquisition_source"),
                "job_state": "queued",
                "article_id": None,
                "chunk_count": None,
                "reference_count": None,
                "error": None,
                "last_message": "Queued",
            }
            for item in selected_items
        ]
        item_by_path = {
            str(item.get("path") or ""): item
            for item in live_selected_items
            if str(item.get("path") or "")
        }
        live_summary: dict[str, Any] = {
            "ingested_articles": 0,
            "total_chunks": 0,
            "total_references": 0,
            "selected_pdfs": [],
            "skipped_existing_pdfs": [],
            "skipped_no_metadata_pdfs": [],
            "failed_pdfs": [],
            "parsed_pdfs": 0,
            "uploaded_pdfs": 0,
            "current_pdf": None,
            "current_stage": "queued",
        }
        live_result: dict[str, Any] = {
            "ok": True,
            "source_mode": "zotero_db",
            "selection_count": len(req.zotero_persistent_ids),
            "resolved_selection_count": len(selected_items),
            "reingest": bool(req.reingest),
            "unavailable_ids": unavailable_ids,
            "selected_items": live_selected_items,
            "summary": live_summary,
        }
        jobs.set_result("ingest", live_result)

        def persist_live_result() -> None:
            jobs.set_result("ingest", live_result)

        def on_ingest_progress(percent: float, message: str) -> None:
            jobs.set_progress("ingest", 20.0 + (max(0.0, min(100.0, float(percent))) * 0.8), message)
            live_summary["last_progress_message"] = message
            persist_live_result()

        def on_ingest_event(event: dict[str, Any]) -> None:
            pdf_path = str(event.get("pdf") or "")
            entry = item_by_path.get(pdf_path) if pdf_path else None
            event_name = str(event.get("event") or "").strip()
            message = str(event.get("message") or "").strip() or None
            if pdf_path:
                live_summary["current_pdf"] = pdf_path
            if event_name:
                live_summary["current_stage"] = event_name

            if entry is not None:
                if message:
                    entry["last_message"] = message
                article_id = event.get("article_id")
                if article_id:
                    entry["article_id"] = article_id
                if event.get("chunk_count") is not None:
                    entry["chunk_count"] = event.get("chunk_count")
                if event.get("reference_count") is not None:
                    entry["reference_count"] = event.get("reference_count")

            if event_name == "skipped_existing":
                if entry is not None:
                    entry["job_state"] = "skipped_existing"
                if pdf_path and pdf_path not in live_summary["skipped_existing_pdfs"]:
                    live_summary["skipped_existing_pdfs"].append(pdf_path)
            elif event_name == "skipped_no_metadata":
                if entry is not None:
                    entry["job_state"] = "skipped_no_metadata"
                if pdf_path and pdf_path not in live_summary["skipped_no_metadata_pdfs"]:
                    live_summary["skipped_no_metadata_pdfs"].append(pdf_path)
            elif event_name == "parse_started":
                if entry is not None:
                    entry["job_state"] = "parsing"
            elif event_name == "parse_succeeded":
                if entry is not None:
                    entry["job_state"] = "parsed"
                live_summary["parsed_pdfs"] = sum(1 for item in live_selected_items if item["job_state"] in {"parsed", "uploaded"})
            elif event_name == "parse_failed":
                if entry is not None:
                    entry["job_state"] = "failed"
                    entry["error"] = str(event.get("error") or "Unknown error")
                live_summary["failed_pdfs"] = [
                    {
                        "pdf": item["path"],
                        "error": item["error"],
                    }
                    for item in live_selected_items
                    if item.get("job_state") == "failed" and item.get("error")
                ]
            elif event_name == "upload_started":
                live_summary["current_stage"] = "uploading"
            elif event_name == "upload_succeeded":
                if entry is not None:
                    entry["job_state"] = "uploaded"
                if pdf_path and pdf_path not in live_summary["selected_pdfs"]:
                    live_summary["selected_pdfs"].append(pdf_path)
                live_summary["uploaded_pdfs"] = sum(1 for item in live_selected_items if item["job_state"] == "uploaded")
                live_summary["ingested_articles"] = live_summary["uploaded_pdfs"]
                live_summary["total_chunks"] = sum(int(item.get("chunk_count") or 0) for item in live_selected_items if item.get("job_state") == "uploaded")
                live_summary["total_references"] = sum(int(item.get("reference_count") or 0) for item in live_selected_items if item.get("job_state") == "uploaded")
            elif event_name == "ingest_complete":
                live_summary["current_stage"] = "completed"

            persist_live_result()

        summary = ingest_pdfs(
            selected_pdfs=selected_pdfs,
            wipe=False,
            settings=settings,
            should_cancel=lambda: job.cancel_event.is_set(),
            skip_existing=not req.reingest,
            progress_callback=on_ingest_progress,
            event_callback=on_ingest_event,
        )
        jobs.set_progress("ingest", 100.0, "Zotero selection ingest complete")
        return {
            "ok": True,
            "source_mode": "zotero_db",
            "selection_count": len(req.zotero_persistent_ids),
            "resolved_selection_count": len(selected_items),
            "reingest": bool(req.reingest),
            "unavailable_ids": unavailable_ids,
            "selected_items": live_selected_items,
            "summary": {
                "ingested_articles": summary.ingested_articles,
                "total_chunks": summary.total_chunks,
                "total_references": summary.total_references,
                "selected_pdfs": summary.selected_pdfs,
                "skipped_existing_pdfs": summary.skipped_existing_pdfs,
                "skipped_no_metadata_pdfs": summary.skipped_no_metadata_pdfs,
                "failed_pdfs": summary.failed_pdfs,
                **_summary_optional_fields(summary),
            },
        }

    return jobs.start("ingest", run)


@app.post("/api/ingest")
def ingest(req: IngestRequest, authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)

    def run(job: JobState) -> dict:
        mode = "batch" if req.mode == "test3" else req.mode
        jobs.set_progress("ingest", 0.0, "Selecting files")
        selected = choose_pdfs(
            mode=mode,
            source_mode=req.source_mode,
            source_dir=req.source_dir,
            explicit_pdfs=req.pdfs,
            skip_existing=not req.override_existing,
            require_metadata=True,
            partial_count=req.partial_count,
        )
        settings = Settings()
        batch_size = max(1, int(req.partial_count))
        all_batch_summaries: list[dict[str, Any]] = []
        agg = {
            "ingested_articles": 0,
            "total_chunks": 0,
            "total_references": 0,
            "selected_pdfs": [],
            "skipped_existing_pdfs": [],
            "skipped_no_metadata_pdfs": [],
            "failed_pdfs": [],
            "citation_override_pdfs": 0,
            "reference_parse_attempted_pdfs": 0,
            "reference_parse_applied_pdfs": 0,
            "reference_parse_empty_pdfs": 0,
            "reference_parse_failed_pdfs": 0,
            "reference_parse_disabled_reason": None,
            "reference_parse_failure_samples": [],
            "qwen_attempted_pdfs": 0,
            "qwen_applied_pdfs": 0,
            "qwen_empty_pdfs": 0,
            "qwen_failed_pdfs": 0,
            "qwen_disabled_reason": None,
            "qwen_failure_samples": [],
        }

        if mode == "all":
            batches = [selected[i : i + batch_size] for i in range(0, len(selected), batch_size)]
        else:
            batches = [selected]

        total_batches = max(1, len(batches))
        for idx, batch in enumerate(batches, start=1):
            if job.cancel_event.is_set():
                raise RuntimeError("Ingest cancelled by user.")

            def on_batch_progress(percent: float, message: str) -> None:
                overall = ((idx - 1) + (percent / 100.0)) / total_batches * 100.0
                jobs.set_progress("ingest", overall, f"Batch {idx}/{total_batches} - {message}")

            summary = ingest_pdfs(
                selected_pdfs=batch,
                wipe=False,
                settings=settings,
                should_cancel=lambda: job.cancel_event.is_set(),
                skip_existing=not req.override_existing,
                progress_callback=on_batch_progress,
            )
            optional = _summary_optional_fields(summary)
            all_batch_summaries.append(
                {
                    "batch_number": idx,
                    "batch_total": total_batches,
                    "input_pdfs": len(batch),
                    "ingested_articles": summary.ingested_articles,
                    "total_chunks": summary.total_chunks,
                    "total_references": summary.total_references,
                    "failed_count": len(summary.failed_pdfs),
                    "skipped_existing_count": len(summary.skipped_existing_pdfs),
                    "skipped_no_metadata_count": len(summary.skipped_no_metadata_pdfs),
                    **{k: v for k, v in optional.items() if k not in {"reference_parse_disabled_reason", "reference_parse_failure_samples", "qwen_disabled_reason", "qwen_failure_samples"}},
                }
            )
            agg["ingested_articles"] += summary.ingested_articles
            agg["total_chunks"] += summary.total_chunks
            agg["total_references"] += summary.total_references
            agg["selected_pdfs"].extend(summary.selected_pdfs)
            agg["skipped_existing_pdfs"].extend(summary.skipped_existing_pdfs)
            agg["skipped_no_metadata_pdfs"].extend(summary.skipped_no_metadata_pdfs)
            agg["failed_pdfs"].extend(summary.failed_pdfs)
            agg["citation_override_pdfs"] += optional["citation_override_pdfs"]
            agg["reference_parse_attempted_pdfs"] += optional["reference_parse_attempted_pdfs"]
            agg["reference_parse_applied_pdfs"] += optional["reference_parse_applied_pdfs"]
            agg["reference_parse_empty_pdfs"] += optional["reference_parse_empty_pdfs"]
            agg["reference_parse_failed_pdfs"] += optional["reference_parse_failed_pdfs"]
            if optional["reference_parse_disabled_reason"] and not agg["reference_parse_disabled_reason"]:
                agg["reference_parse_disabled_reason"] = optional["reference_parse_disabled_reason"]
            if optional["reference_parse_failure_samples"]:
                agg["reference_parse_failure_samples"].extend(optional["reference_parse_failure_samples"])
            agg["qwen_attempted_pdfs"] += optional["qwen_attempted_pdfs"]
            agg["qwen_applied_pdfs"] += optional["qwen_applied_pdfs"]
            agg["qwen_empty_pdfs"] += optional["qwen_empty_pdfs"]
            agg["qwen_failed_pdfs"] += optional["qwen_failed_pdfs"]
            if optional["qwen_disabled_reason"] and not agg["qwen_disabled_reason"]:
                agg["qwen_disabled_reason"] = optional["qwen_disabled_reason"]
            if optional["qwen_failure_samples"]:
                agg["qwen_failure_samples"].extend(optional["qwen_failure_samples"])
            partial_summary = {
                "mode": mode,
                "source_mode": req.source_mode,
                "batch_size": batch_size,
                "batch_total": total_batches,
                "batch_results": list(all_batch_summaries),
                "ingested_articles": agg["ingested_articles"],
                "total_chunks": agg["total_chunks"],
                "total_references": agg["total_references"],
                "selected_pdfs": list(agg["selected_pdfs"]),
                "skipped_existing_pdfs": list(agg["skipped_existing_pdfs"]),
                "skipped_no_metadata_pdfs": list(agg["skipped_no_metadata_pdfs"]),
                "failed_pdfs": list(agg["failed_pdfs"]),
                "citation_override_pdfs": agg["citation_override_pdfs"],
                "reference_parse_attempted_pdfs": agg["reference_parse_attempted_pdfs"],
                "reference_parse_applied_pdfs": agg["reference_parse_applied_pdfs"],
                "reference_parse_empty_pdfs": agg["reference_parse_empty_pdfs"],
                "reference_parse_failed_pdfs": agg["reference_parse_failed_pdfs"],
                "reference_parse_disabled_reason": agg["reference_parse_disabled_reason"],
                "reference_parse_failure_samples": list(agg["reference_parse_failure_samples"])[:30],
                "qwen_attempted_pdfs": agg["qwen_attempted_pdfs"],
                "qwen_applied_pdfs": agg["qwen_applied_pdfs"],
                "qwen_empty_pdfs": agg["qwen_empty_pdfs"],
                "qwen_failed_pdfs": agg["qwen_failed_pdfs"],
                "qwen_disabled_reason": agg["qwen_disabled_reason"],
                "qwen_failure_samples": list(agg["qwen_failure_samples"])[:30],
            }
            with jobs._lock:
                job.result = {"ok": True, "summary": partial_summary}
            jobs.set_progress(
                "ingest",
                (idx / total_batches) * 100.0,
                (
                    f"Completed batch {idx}/{total_batches}: "
                    f"ingested {summary.ingested_articles}, failed {len(summary.failed_pdfs)}"
                ),
            )

        jobs.set_progress("ingest", 100.0, "Ingest complete")
        return {
            "ok": True,
            "summary": {
                "mode": mode,
                "batch_size": batch_size,
                "batch_total": total_batches,
                "batch_results": all_batch_summaries,
                "ingested_articles": agg["ingested_articles"],
                "total_chunks": agg["total_chunks"],
                "total_references": agg["total_references"],
                "selected_pdfs": agg["selected_pdfs"],
                "skipped_existing_pdfs": agg["skipped_existing_pdfs"],
                "skipped_no_metadata_pdfs": agg["skipped_no_metadata_pdfs"],
                "failed_pdfs": agg["failed_pdfs"],
                "citation_override_pdfs": agg["citation_override_pdfs"],
                "reference_parse_attempted_pdfs": agg["reference_parse_attempted_pdfs"],
                "reference_parse_applied_pdfs": agg["reference_parse_applied_pdfs"],
                "reference_parse_empty_pdfs": agg["reference_parse_empty_pdfs"],
                "reference_parse_failed_pdfs": agg["reference_parse_failed_pdfs"],
                "reference_parse_disabled_reason": agg["reference_parse_disabled_reason"],
                "reference_parse_failure_samples": agg["reference_parse_failure_samples"][:30],
                "qwen_attempted_pdfs": agg["qwen_attempted_pdfs"],
                "qwen_applied_pdfs": agg["qwen_applied_pdfs"],
                "qwen_empty_pdfs": agg["qwen_empty_pdfs"],
                "qwen_failed_pdfs": agg["qwen_failed_pdfs"],
                "qwen_disabled_reason": agg["qwen_disabled_reason"],
                "qwen_failure_samples": agg["qwen_failure_samples"][:30],
            },
        }

    return jobs.start("ingest", run)


@app.post("/api/ingest/preview")
def ingest_preview(req: IngestPreviewRequest, authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)
    try:
        mode = "batch" if req.mode == "test3" else req.mode
        settings = Settings()
        resolved = choose_pdfs(
            mode=mode,
            source_mode=req.source_mode,
            source_dir=req.source_dir,
            explicit_pdfs=req.pdfs,
            skip_existing=not req.override_existing,
            require_metadata=False,
            settings=settings,
            partial_count=req.partial_count,
        )
        try:
            selected_for_ingest = choose_pdfs(
                mode=mode,
                source_mode=req.source_mode,
                source_dir=req.source_dir,
                explicit_pdfs=req.pdfs,
                skip_existing=not req.override_existing,
                require_metadata=True,
                settings=settings,
                partial_count=req.partial_count,
            )
        except Exception:
            selected_for_ingest = []
        selected_set = {str(p.resolve()) for p in selected_for_ingest}

        store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
        try:
            existing_ids = store.existing_article_ids()
        finally:
            store.close()
        metadata_index = _load_metadata_index_for_settings(settings)

        max_rows = 300
        rows = []
        for p in resolved[:max_rows]:
            meta = find_metadata_for_pdf(metadata_index, p.name, str(p)) or {}
            rows.append(
                {
                    "path": str(p),
                    "file": p.name,
                    "article_id": p.stem,
                    "exists_in_graph": p.stem in existing_ids,
                    "will_ingest": str(p.resolve()) in selected_set,
                    "metadata_found": bool(meta),
                    "title": meta.get("title"),
                    "year": meta.get("year"),
                    "citekey": meta.get("citekey"),
                    "authors": meta.get("authors") or [],
                }
            )
        return {
            "ok": True,
            "summary": {
                "total_resolved": len(resolved),
                "total_previewed": len(rows),
                "truncated": len(resolved) > max_rows,
                "will_ingest_count": sum(1 for r in rows if r["will_ingest"]),
                "existing_count": sum(1 for r in rows if r["exists_in_graph"]),
                "metadata_found_count": sum(1 for r in rows if r["metadata_found"]),
            },
            "rows": rows,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/ingest/status")
def ingest_status(authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)
    return jobs.status("ingest")


@app.post("/api/ingest/stop")
def ingest_stop(authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)
    return jobs.stop("ingest")


@app.get("/api/article/{citekey}")
def article_by_citekey(citekey: str, chunk_limit: int = 3) -> dict:
    key = (citekey or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Citekey cannot be empty.")
    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    try:
        article = store.article_by_citekey(key, chunk_limit=max(1, min(int(chunk_limit), 20)))
    finally:
        store.close()
    if not article:
        raise HTTPException(status_code=404, detail=f"Article not found for citekey: {key}")
    return {"ok": True, "article": article}


@app.post("/api/articles/by-citekeys")
def articles_by_citekeys(req: ArticleLookupRequest) -> dict:
    cleaned = []
    seen = set()
    for raw in req.citekeys:
        key = (raw or "").strip()
        if not key:
            continue
        lower = key.lower()
        if lower in seen:
            continue
        seen.add(lower)
        cleaned.append(key)
    if not cleaned:
        raise HTTPException(status_code=400, detail="No valid citekeys provided.")

    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    try:
        rows = store.articles_by_citekeys(cleaned, chunk_limit=req.chunk_limit)
    finally:
        store.close()

    found = {str(r.get("article_citekey", "")).lower() for r in rows}
    missing = [k for k in cleaned if k.lower() not in found]
    return {
        "ok": True,
        "requested_count": len(cleaned),
        "found_count": len(rows),
        "missing_citekeys": missing,
        "articles": rows,
    }


@app.post("/api/article/{citekey}/claim-match")
def article_claim_match_endpoint(citekey: str, req: ArticleClaimMatchRequest) -> dict:
    key = (citekey or "").strip()
    claim = (req.claim_text or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Citekey cannot be empty.")
    if not claim:
        raise HTTPException(status_code=400, detail="Claim text cannot be empty.")

    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    try:
        result = article_claim_match(store, key, claim, top_k=req.top_k)
    finally:
        store.close()
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or f"Article not found for citekey: {key}")
    return result


@app.post("/api/article-id/{article_id}/claim-match")
def article_claim_match_by_id_endpoint(article_id: str, req: ArticleClaimMatchRequest) -> dict:
    key = (article_id or "").strip()
    claim = (req.claim_text or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Article id cannot be empty.")
    if not claim:
        raise HTTPException(status_code=400, detail="Claim text cannot be empty.")

    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    try:
        result = article_claim_match_by_article_id(store, key, claim, top_k=req.top_k)
    finally:
        store.close()
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or f"Article not found for id: {key}")
    return result


@app.post("/api/query")
def query(req: QueryRequest, authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    def run(job: JobState) -> dict:
        if job.cancel_event.is_set():
            raise RuntimeError("Query cancelled by user.")
        jobs.set_progress("query", 10.0, "Encoding and querying")
        settings = Settings()
        store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
        try:
            rows = graphrag_retrieve(
                store,
                req.query,
                limit=req.limit,
                limit_scope=req.limit_scope,
                chunks_per_paper=req.chunks_per_paper,
                score_threshold=req.score_threshold,
            )
        finally:
            store.close()
        if job.cancel_event.is_set():
            raise RuntimeError("Query cancelled by user.")
        jobs.set_progress("query", 100.0, "Query complete")
        return {
            "ok": True,
            "query": req.query,
            "limit": req.limit,
            "limit_scope": req.limit_scope,
            "chunks_per_paper": req.chunks_per_paper,
            "results": rows,
            "score_threshold": req.score_threshold,
        }

    return jobs.start("query", run)


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    settings = Settings()
    search_query_used = question
    preprocess_meta: dict[str, Any] = {
        "enabled": req.preprocess_search,
        "method": "identity",
        "backend": settings.query_preprocess_backend,
        "error": None,
    }
    if req.preprocess_search:
        try:
            rewritten = preprocess_search_query(question, model=req.model).strip()
            if rewritten:
                search_query_used = rewritten
                preprocess_meta["method"] = "llm_rewrite"
            else:
                preprocess_meta["method"] = "fallback_original"
        except Exception as exc:
            preprocess_meta["method"] = "fallback_original"
            preprocess_meta["error"] = str(exc)

    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    try:
        retrieval_limit = req.rag_results or max(1, int(req.retrieval_pool))
        retrieval_threshold = None if req.rag_results is not None else req.score_threshold
        # Ask keeps chunk-mode retrieval for richer grounding context.
        rag_rows = graphrag_retrieve(
            store,
            search_query_used,
            limit=retrieval_limit,
            limit_scope="chunks",
            chunks_per_paper=1,
            score_threshold=retrieval_threshold,
        )
    finally:
        store.close()

    usable_rows, excluded_rows, gate_summary = gate_rows_for_synthesis(question, rag_rows)

    try:
        llm = ask_grounded(
            question=question,
            rows=usable_rows,
            model=req.model,
            enforce_citations=req.enforce_citations,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit = audit_answer_support(llm.get("answer", ""), llm.get("used_citations", []))

    report = {
        "ok": True,
        "question": question,
        "search_query_used": search_query_used,
        "query_preprocess": preprocess_meta,
        "retrieval_mode": "fixed_top_n" if req.rag_results is not None else "score_threshold",
        "retrieval_pool": retrieval_limit,
        "score_threshold": retrieval_threshold,
        "rag_results_count": len(rag_rows),
        "rag_results": rag_rows,
        "usable_rag_results_count": len(usable_rows),
        "usable_rag_results": usable_rows,
        "excluded_rag_results_count": len(excluded_rows),
        "excluded_rag_results": excluded_rows,
        "model": llm.get("model"),
        "answer": llm.get("answer"),
        "citation_enforced": llm.get("citation_enforced"),
        "answer_method": llm.get("method"),
        "synthesis_status": llm.get("synthesis_status"),
        "fallback_reason": llm.get("fallback_reason"),
        "agent_error": llm.get("agent_error"),
        "evidence_snippets": llm.get("evidence_snippets", []),
        "relevance_summary": llm.get("relevance_summary") or gate_summary,
        "audit": audit,
        "used_citations": llm.get("used_citations", []),
        "relevant_citations": llm.get("relevant_citations", []),
        "excluded_citations": llm.get("excluded_citations", []),
        "all_citations": llm.get("all_citations", []),
    }
    return report


@app.post("/api/ask/export")
def ask_export(req: AskExportRequest):
    report = req.report or {}
    if req.format == "markdown":
        text = to_markdown(report)
        return PlainTextResponse(text, media_type="text/markdown")
    if req.format == "csv":
        csv_text = citations_to_csv(report)
        return PlainTextResponse(csv_text, media_type="text/csv")
    try:
        pdf_bytes = markdown_to_pdf_bytes(to_markdown(report))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=rag_answer_report.pdf"},
    )


@app.get("/api/query/status")
def query_status(authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)
    return jobs.status("query")


@app.post("/api/query/stop")
def query_stop(authorization: str | None = Header(default=None)) -> dict:
    _require_api_token(authorization)
    return jobs.stop("query")
