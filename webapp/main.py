from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.rag.answer_audit import audit_answer_support
from src.rag.config import Settings
from src.rag.llm_answer import ask_openai_grounded, preprocess_search_query
from src.rag.neo4j_store import GraphStore
from src.rag.paperpile_metadata import find_metadata_for_pdf, find_unmatched_pdfs, iter_pdf_files, load_paperpile_index
from src.rag.pipeline import choose_pdfs, ingest_pdfs
from src.rag.retrieval import contextual_retrieve
from src.rag.report_export import citations_to_csv, markdown_to_pdf_bytes, to_markdown


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "webapp" / "static"
SYNC_SCRIPT = ROOT / "scripts" / "sync_pdfs_from_gdrive.sh"
DOTENV_PATH = ROOT / ".env"


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


def _openai_api_key_set() -> bool:
    primary = os.getenv("OPENAI_API_KEY", "").strip()
    alias = os.getenv("OpenAPIKey", "").strip()
    return bool(primary or alias)

app = FastAPI(title="Research Assistant RAG UI", version="2026.02.22.033455")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class SyncRequest(BaseModel):
    dry_run: bool = False


class IngestRequest(BaseModel):
    mode: str = Field(default="batch", pattern="^(batch|all|custom|test3)$")
    source_dir: str = "pdfs"
    pdfs: list[str] = Field(default_factory=list)
    override_existing: bool = False
    partial_count: int = Field(default=3, ge=1, le=5000)


class QueryRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)


class ArticleLookupRequest(BaseModel):
    citekeys: list[str] = Field(default_factory=list, min_length=1, max_length=500)
    chunk_limit: int = Field(default=3, ge=1, le=20)


class AskRequest(BaseModel):
    question: str
    rag_results: int = Field(default=8, ge=1, le=30)
    model: str | None = None
    enforce_citations: bool = True
    preprocess_search: bool = True


class AskExportRequest(BaseModel):
    report: dict[str, Any]
    format: str = Field(default="markdown", pattern="^(markdown|csv|pdf)$")


class IngestPreviewRequest(BaseModel):
    mode: str = Field(default="batch", pattern="^(batch|all|custom|test3)$")
    source_dir: str = "pdfs"
    pdfs: list[str] = Field(default_factory=list)
    override_existing: bool = False
    partial_count: int = Field(default=3, ge=1, le=5000)


@dataclass
class JobState:
    name: str
    status: str = "idle"
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
                        else:
                            job.status = "completed"
                        job.result = result
                        job.finished_at = time.time()
                except Exception as exc:
                    with self._lock:
                        if job.cancel_event.is_set():
                            job.status = "cancelled"
                        else:
                            job.status = "failed"
                        job.error = str(exc)
                        job.finished_at = time.time()

            job.thread = threading.Thread(target=wrapped, daemon=True)
            job.thread.start()
        return self.status(name)

    def stop(self, name: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs[name]
            if job.status != "running":
                pass
            else:
                job.cancel_event.set()
                if job.proc and job.proc.poll() is None:
                    job.proc.terminate()
        return self.status(name)

    def status(self, name: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs[name]
            return {
                "name": job.name,
                "status": job.status,
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


jobs = JobManager()


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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    try:
        stats = store.graph_stats()
    finally:
        store.close()
    return {"status": "ok", "neo4j_uri": settings.neo4j_uri, "stats": stats}


@app.get("/api/diagnostics")
def diagnostics() -> dict:
    settings = Settings()
    diag: dict[str, Any] = {}
    checks: list[dict[str, Any]] = []

    # Config and file checks
    paperpile_path = Path(settings.paperpile_json)
    checks.append(
        {
            "name": "paperpile_json_exists",
            "ok": paperpile_path.exists(),
            "details": str(paperpile_path),
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
    metadata_index = load_paperpile_index(settings.paperpile_json)
    pdf_root = Path("pdfs")
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
            "details": f"{with_meta}/{total_local_pdfs} local PDFs matched to metadata",
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
def sync_pdfs(req: SyncRequest) -> dict:
    def run(job: JobState) -> dict:
        if not SYNC_SCRIPT.exists():
            raise RuntimeError(f"Sync script not found: {SYNC_SCRIPT}")
        cmd = [str(SYNC_SCRIPT)]
        if req.dry_run:
            cmd.append("--dry-run")

        remote_path = "gdrive:Library/Paperpile/allPapers"
        local_dir = "pdfs"
        total_remote = _count_remote_pdfs(remote_path)
        jobs.set_progress("sync", 0.0, "Starting sync")

        stdout_buf: list[str] = []
        stderr_buf: list[str] = []
        max_log_lines = 4000

        def _drain_output(stream: Any, sink: list[str]) -> None:
            for line in iter(stream.readline, ""):
                sink.append(line)
                if len(sink) > max_log_lines:
                    del sink[: len(sink) - max_log_lines]
            stream.close()

        def _log_tail() -> tuple[str, str]:
            return ("".join(stdout_buf)[-12000:], "".join(stderr_buf)[-12000:])

        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if proc.stdout is None or proc.stderr is None:
            raise RuntimeError("Failed to capture sync process output streams.")
        out_thread = threading.Thread(target=_drain_output, args=(proc.stdout, stdout_buf), daemon=True)
        err_thread = threading.Thread(target=_drain_output, args=(proc.stderr, stderr_buf), daemon=True)
        out_thread.start()
        err_thread.start()
        with jobs._lock:
            job.proc = proc
        while proc.poll() is None:
            if job.cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                out_thread.join(timeout=2)
                err_thread.join(timeout=2)
                out, err = _log_tail()
                jobs.set_progress("sync", job.progress_percent, "Cancelled")
                return {"ok": False, "cancelled": True, "stdout": out, "stderr": err}
            if total_remote and total_remote > 0:
                local_count = _count_local_pdfs(str(ROOT / local_dir))
                pct = min(99.0, (local_count / total_remote) * 100.0)
                jobs.set_progress("sync", pct, f"Local PDFs: {local_count}/{total_remote}")
            else:
                jobs.set_progress("sync", 50.0, "Sync in progress")
            time.sleep(0.2)
        out_thread.join(timeout=2)
        err_thread.join(timeout=2)
        out, err = _log_tail()
        if proc.returncode != 0:
            jobs.set_progress("sync", 100.0, f"Sync failed (exit {proc.returncode})")
            error_detail = (err or out).strip()[-800:]
            if error_detail:
                raise RuntimeError(f"Sync failed (exit {proc.returncode}): {error_detail}")
            raise RuntimeError(f"Sync failed (exit {proc.returncode}).")
        jobs.set_progress("sync", 100.0, "Sync complete")
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": out[-12000:],
            "stderr": err[-12000:],
        }

    return jobs.start("sync", run)


@app.get("/api/sync/status")
def sync_status() -> dict:
    return jobs.status("sync")


@app.post("/api/sync/stop")
def sync_stop() -> dict:
    return jobs.stop("sync")


@app.post("/api/ingest")
def ingest(req: IngestRequest) -> dict:
    def run(job: JobState) -> dict:
        mode = "batch" if req.mode == "test3" else req.mode
        jobs.set_progress("ingest", 0.0, "Selecting files")
        selected = choose_pdfs(
            mode=mode,
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
            "anystyle_attempted_pdfs": 0,
            "anystyle_applied_pdfs": 0,
            "anystyle_empty_pdfs": 0,
            "anystyle_failed_pdfs": 0,
            "anystyle_disabled_reason": None,
            "anystyle_failure_samples": [],
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
                    "citation_override_pdfs": summary.citation_override_pdfs,
                    "anystyle_attempted_pdfs": summary.anystyle_attempted_pdfs,
                    "anystyle_applied_pdfs": summary.anystyle_applied_pdfs,
                    "anystyle_empty_pdfs": summary.anystyle_empty_pdfs,
                    "anystyle_failed_pdfs": summary.anystyle_failed_pdfs,
                }
            )
            agg["ingested_articles"] += summary.ingested_articles
            agg["total_chunks"] += summary.total_chunks
            agg["total_references"] += summary.total_references
            agg["selected_pdfs"].extend(summary.selected_pdfs)
            agg["skipped_existing_pdfs"].extend(summary.skipped_existing_pdfs)
            agg["skipped_no_metadata_pdfs"].extend(summary.skipped_no_metadata_pdfs)
            agg["failed_pdfs"].extend(summary.failed_pdfs)
            agg["citation_override_pdfs"] += summary.citation_override_pdfs
            agg["anystyle_attempted_pdfs"] += summary.anystyle_attempted_pdfs
            agg["anystyle_applied_pdfs"] += summary.anystyle_applied_pdfs
            agg["anystyle_empty_pdfs"] += summary.anystyle_empty_pdfs
            agg["anystyle_failed_pdfs"] += summary.anystyle_failed_pdfs
            if summary.anystyle_disabled_reason and not agg["anystyle_disabled_reason"]:
                agg["anystyle_disabled_reason"] = summary.anystyle_disabled_reason
            if summary.anystyle_failure_samples:
                agg["anystyle_failure_samples"].extend(summary.anystyle_failure_samples)
            partial_summary = {
                "mode": mode,
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
                "anystyle_attempted_pdfs": agg["anystyle_attempted_pdfs"],
                "anystyle_applied_pdfs": agg["anystyle_applied_pdfs"],
                "anystyle_empty_pdfs": agg["anystyle_empty_pdfs"],
                "anystyle_failed_pdfs": agg["anystyle_failed_pdfs"],
                "anystyle_disabled_reason": agg["anystyle_disabled_reason"],
                "anystyle_failure_samples": list(agg["anystyle_failure_samples"])[:30],
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
                "anystyle_attempted_pdfs": agg["anystyle_attempted_pdfs"],
                "anystyle_applied_pdfs": agg["anystyle_applied_pdfs"],
                "anystyle_empty_pdfs": agg["anystyle_empty_pdfs"],
                "anystyle_failed_pdfs": agg["anystyle_failed_pdfs"],
                "anystyle_disabled_reason": agg["anystyle_disabled_reason"],
                "anystyle_failure_samples": agg["anystyle_failure_samples"][:30],
            },
        }

    return jobs.start("ingest", run)


@app.post("/api/ingest/preview")
def ingest_preview(req: IngestPreviewRequest) -> dict:
    try:
        mode = "batch" if req.mode == "test3" else req.mode
        settings = Settings()
        resolved = choose_pdfs(
            mode=mode,
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
        paperpile = load_paperpile_index(settings.paperpile_json)

        max_rows = 300
        rows = []
        for p in resolved[:max_rows]:
            meta = find_metadata_for_pdf(paperpile, p.name) or {}
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
def ingest_status() -> dict:
    return jobs.status("ingest")


@app.post("/api/ingest/stop")
def ingest_stop() -> dict:
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


@app.post("/api/query")
def query(req: QueryRequest) -> dict:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    def run(job: JobState) -> dict:
        if job.cancel_event.is_set():
            raise RuntimeError("Query cancelled by user.")
        jobs.set_progress("query", 10.0, "Encoding and querying")
        settings = Settings()
        store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
        try:
            rows = contextual_retrieve(store, req.query, req.limit)
        finally:
            store.close()
        if job.cancel_event.is_set():
            raise RuntimeError("Query cancelled by user.")
        jobs.set_progress("query", 100.0, "Query complete")
        return {"ok": True, "query": req.query, "results": rows}

    return jobs.start("query", run)


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    search_query_used = question
    preprocess_meta: dict[str, Any] = {
        "enabled": req.preprocess_search,
        "method": "identity",
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

    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    try:
        rag_rows = contextual_retrieve(store, search_query_used, limit=req.rag_results)
    finally:
        store.close()

    try:
        llm = ask_openai_grounded(
            question=question,
            rows=rag_rows,
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
        "rag_results_count": len(rag_rows),
        "rag_results": rag_rows,
        "model": llm.get("model"),
        "answer": llm.get("answer"),
        "citation_enforced": llm.get("citation_enforced"),
        "audit": audit,
        "used_citations": llm.get("used_citations", []),
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
def query_status() -> dict:
    return jobs.status("query")


@app.post("/api/query/stop")
def query_stop() -> dict:
    return jobs.stop("query")
