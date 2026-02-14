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
from src.rag.llm_answer import ask_openai_grounded
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

app = FastAPI(title="Research Assistant RAG UI", version="0.1.0")
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
    mode: str = Field(default="test3", pattern="^(test3|all|custom)$")
    source_dir: str = "pdfs"
    pdfs: list[str] = Field(default_factory=list)
    override_existing: bool = False
    partial_count: int = Field(default=3, ge=1, le=5000)


class QueryRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)


class AskRequest(BaseModel):
    question: str
    rag_results: int = Field(default=8, ge=1, le=30)
    model: str | None = None
    enforce_citations: bool = True


class AskExportRequest(BaseModel):
    report: dict[str, Any]
    format: str = Field(default="markdown", pattern="^(markdown|csv|pdf)$")


class IngestPreviewRequest(BaseModel):
    mode: str = Field(default="test3", pattern="^(test3|all|custom)$")
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
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return None
        lines = [x for x in proc.stdout.splitlines() if x.strip()]
        return len(lines)
    except Exception:
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

        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with jobs._lock:
            job.proc = proc
        while proc.poll() is None:
            if job.cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                jobs.set_progress("sync", job.progress_percent, "Cancelled")
                return {"ok": False, "cancelled": True}
            if total_remote and total_remote > 0:
                local_count = _count_local_pdfs(str(ROOT / local_dir))
                pct = min(99.0, (local_count / total_remote) * 100.0)
                jobs.set_progress("sync", pct, f"Local PDFs: {local_count}/{total_remote}")
            else:
                jobs.set_progress("sync", 50.0, "Sync in progress")
            time.sleep(0.2)
        out, err = proc.communicate()
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
        jobs.set_progress("ingest", 0.0, "Selecting files")
        selected = choose_pdfs(
            mode=req.mode,
            source_dir=req.source_dir,
            explicit_pdfs=req.pdfs,
            skip_existing=not req.override_existing,
            require_metadata=True,
            partial_count=req.partial_count,
        )
        summary = ingest_pdfs(
            selected_pdfs=selected,
            wipe=False,
            settings=Settings(),
            should_cancel=lambda: job.cancel_event.is_set(),
            skip_existing=not req.override_existing,
            progress_callback=lambda percent, message: jobs.set_progress("ingest", percent, message),
        )
        jobs.set_progress("ingest", 100.0, "Ingest complete")
        return {
            "ok": True,
            "summary": {
                "ingested_articles": summary.ingested_articles,
                "total_chunks": summary.total_chunks,
                "total_references": summary.total_references,
                "selected_pdfs": summary.selected_pdfs,
                "skipped_existing_pdfs": summary.skipped_existing_pdfs,
                "skipped_no_metadata_pdfs": summary.skipped_no_metadata_pdfs,
                "failed_pdfs": summary.failed_pdfs,
            },
        }

    return jobs.start("ingest", run)


@app.post("/api/ingest/preview")
def ingest_preview(req: IngestPreviewRequest) -> dict:
    try:
        settings = Settings()
        resolved = choose_pdfs(
            mode=req.mode,
            source_dir=req.source_dir,
            explicit_pdfs=req.pdfs,
            skip_existing=not req.override_existing,
            require_metadata=False,
            settings=settings,
            partial_count=req.partial_count,
        )
        try:
            selected_for_ingest = choose_pdfs(
                mode=req.mode,
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

    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    try:
        rag_rows = contextual_retrieve(store, question, limit=req.rag_results)
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
