from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.rag.config import Settings
from src.rag.neo4j_store import GraphStore
from src.rag.pipeline import choose_pdfs, ingest_pdfs
from src.rag.retrieval import contextual_retrieve


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "webapp" / "static"
SYNC_SCRIPT = ROOT / "scripts" / "sync_pdfs_from_gdrive.sh"

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


class QueryRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)


@dataclass
class JobState:
    name: str
    status: str = "idle"
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
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
            }


jobs = JobManager()


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


@app.post("/api/sync")
def sync_pdfs(req: SyncRequest) -> dict:
    def run(job: JobState) -> dict:
        if not SYNC_SCRIPT.exists():
            raise RuntimeError(f"Sync script not found: {SYNC_SCRIPT}")
        cmd = [str(SYNC_SCRIPT)]
        if req.dry_run:
            cmd.append("--dry-run")
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
                return {"ok": False, "cancelled": True}
            time.sleep(0.2)
        out, err = proc.communicate()
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
        selected = choose_pdfs(
            mode=req.mode,
            source_dir=req.source_dir,
            explicit_pdfs=req.pdfs,
            skip_existing=not req.override_existing,
        )
        summary = ingest_pdfs(
            selected_pdfs=selected,
            wipe=False,
            settings=Settings(),
            should_cancel=lambda: job.cancel_event.is_set(),
            skip_existing=not req.override_existing,
        )
        return {
            "ok": True,
            "summary": {
                "ingested_articles": summary.ingested_articles,
                "total_chunks": summary.total_chunks,
                "total_references": summary.total_references,
                "selected_pdfs": summary.selected_pdfs,
                "skipped_existing_pdfs": summary.skipped_existing_pdfs,
                "failed_pdfs": summary.failed_pdfs,
            },
        }

    return jobs.start("ingest", run)


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
        settings = Settings()
        store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
        try:
            rows = contextual_retrieve(store, req.query, req.limit)
        finally:
            store.close()
        if job.cancel_event.is_set():
            raise RuntimeError("Query cancelled by user.")
        return {"ok": True, "query": req.query, "results": rows}

    return jobs.start("query", run)


@app.get("/api/query/status")
def query_status() -> dict:
    return jobs.status("query")


@app.post("/api/query/stop")
def query_stop() -> dict:
    return jobs.stop("query")
