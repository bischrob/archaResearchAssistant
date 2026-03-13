#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.pipeline import IngestSummary, choose_pdfs, ingest_pdfs


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _wiki_link(index_file: Path, target_file: Path) -> str:
    rel = target_file.relative_to(index_file.parent)
    return rel.with_suffix("").as_posix()


def ensure_status_linked(index_file: Path, status_file: Path) -> None:
    text = index_file.read_text(encoding="utf-8")
    link_line = f"- [[{_wiki_link(index_file, status_file)}]]"
    if link_line in text:
        return

    lines = text.splitlines()
    start = None
    end = None
    for idx, line in enumerate(lines):
        if line.strip() == "## Project Context":
            start = idx
            continue
        if start is not None and idx > start and line.startswith("## "):
            end = idx
            break
    if start is None:
        lines.append("")
        lines.append("## Project Context")
        lines.append(link_line)
    else:
        insert_at = end if end is not None else len(lines)
        lines.insert(insert_at, link_line)

    index_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_status(
    *,
    run_id: str,
    state: str,
    phase: str,
    sync_status: str,
    citation_parser: str,
    report_every: int,
    ingest_batch_size: int,
    total_selected: int,
    processed: int,
    ingested_articles: int,
    total_chunks: int,
    total_references: int,
    anystyle_attempted: int,
    anystyle_applied: int,
    anystyle_empty: int,
    anystyle_failed: int,
    progress_lines: list[str],
    failure_lines: list[str],
    log_file: str | None,
    error: str | None = None,
) -> str:
    remaining = max(0, total_selected - processed)
    out: list[str] = []
    out.append("# Ingest Status Tracker")
    out.append("")
    out.append(f"Last updated: {utc_now()}")
    out.append(f"Run ID: {run_id}")
    out.append(f"State: {state}")
    out.append(f"Phase: {phase}")
    out.append(f"Sync status: {sync_status}")
    out.append(f"Citation parser: {citation_parser}")
    out.append(f"Report interval (PDFs): {report_every}")
    out.append(f"Ingest batch size (PDFs): {ingest_batch_size}")
    out.append(f"Total selected PDFs: {total_selected}")
    out.append(f"Processed PDFs: {processed}")
    out.append(f"Remaining PDFs: {remaining}")
    out.append(f"Ingested articles (this run): {ingested_articles}")
    out.append(f"Total chunks (this run): {total_chunks}")
    out.append(f"Total references (this run): {total_references}")
    out.append(
        "Anystyle attempted/applied/empty/failed: "
        f"{anystyle_attempted}/{anystyle_applied}/{anystyle_empty}/{anystyle_failed}"
    )
    if log_file:
        out.append(f"Background log: `{log_file}`")
    if error:
        out.append(f"Error: `{error}`")

    out.append("")
    out.append("## Batch Updates")
    if progress_lines:
        for line in progress_lines[-200:]:
            out.append(f"- {line}")
    else:
        out.append("- No progress updates yet.")

    out.append("")
    out.append("## Failed PDFs")
    if failure_lines:
        for line in failure_lines[-200:]:
            out.append(f"- {line}")
    else:
        out.append("- None recorded.")

    out.append("")
    return "\n".join(out)


def write_status(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def run_sync() -> int:
    cmd = ["bash", str(ROOT / "scripts" / "sync_pdfs_from_gdrive.sh")]
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"[sync] {line.rstrip()}", flush=True)
    return proc.wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resync PDFs then re-ingest all with Anystyle in 100-PDF batches and Vault progress updates."
    )
    parser.add_argument("--pdf-dir", default="pdfs", help="PDF source directory.")
    parser.add_argument(
        "--report-every",
        type=int,
        default=100,
        help="Write a Vault progress checkpoint every N processed PDFs.",
    )
    parser.add_argument(
        "--ingest-batch-size",
        type=int,
        default=10,
        help="Internal ingest batch size to control memory use.",
    )
    parser.add_argument(
        "--status-file",
        default="Vault/00_Project/07_ingest_status.md",
        help="Vault markdown status file path.",
    )
    parser.add_argument(
        "--log-file",
        default="",
        help="Path to background log file for display in status note.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_every = max(1, int(args.report_every))
    ingest_batch_size = max(1, int(args.ingest_batch_size))
    status_file = (ROOT / args.status_file).resolve()
    index_file = ROOT / "Vault" / "Index.md"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = args.log_file.strip() or None

    ensure_status_linked(index_file, status_file)

    state = "running"
    phase = "initializing"
    sync_status = "pending"
    progress_lines: list[str] = []
    failure_lines: list[str] = []

    total_selected = 0
    processed = 0
    ingested_articles = 0
    total_chunks = 0
    total_references = 0
    anystyle_attempted = 0
    anystyle_applied = 0
    anystyle_empty = 0
    anystyle_failed = 0
    error: str | None = None
    parser_mode = "anystyle"

    def _persist() -> None:
        write_status(
            status_file,
            render_status(
                run_id=run_id,
                state=state,
                phase=phase,
                sync_status=sync_status,
                citation_parser=parser_mode,
                report_every=report_every,
                ingest_batch_size=ingest_batch_size,
                total_selected=total_selected,
                processed=processed,
                ingested_articles=ingested_articles,
                total_chunks=total_chunks,
                total_references=total_references,
                anystyle_attempted=anystyle_attempted,
                anystyle_applied=anystyle_applied,
                anystyle_empty=anystyle_empty,
                anystyle_failed=anystyle_failed,
                progress_lines=progress_lines,
                failure_lines=failure_lines,
                log_file=log_file,
                error=error,
            ),
        )

    _persist()
    try:
        phase = "sync"
        sync_status = "running"
        progress_lines.append(f"{utc_now()} | Starting PDF sync from Google Drive with rclone.")
        _persist()

        sync_rc = run_sync()
        if sync_rc != 0:
            state = "failed"
            sync_status = f"failed (exit {sync_rc})"
            phase = "sync"
            error = f"sync failed with exit code {sync_rc}"
            progress_lines.append(f"{utc_now()} | Sync failed with exit code {sync_rc}.")
            _persist()
            return sync_rc

        sync_status = "completed"
        progress_lines.append(f"{utc_now()} | Sync completed successfully.")
        _persist()

        phase = "selecting"
        settings = replace(Settings(), citation_parser="anystyle")
        parser_mode = settings.citation_parser
        selected = choose_pdfs(
            mode="all",
            source_dir=args.pdf_dir,
            explicit_pdfs=[],
            skip_existing=False,
            require_metadata=True,
            settings=settings,
            partial_count=ingest_batch_size,
        )
        total_selected = len(selected)
        progress_lines.append(f"{utc_now()} | Selected {total_selected} PDFs for re-ingest.")
        _persist()

        if total_selected == 0:
            state = "completed"
            phase = "complete"
            progress_lines.append(f"{utc_now()} | No PDFs matched ingest selection.")
            _persist()
            return 0

        phase = "ingest"
        progress_lines.append(f"{utc_now()} | Ingest started.")
        _persist()
        total_batches = (total_selected + ingest_batch_size - 1) // ingest_batch_size
        next_report = report_every
        for idx in range(total_batches):
            start = idx * ingest_batch_size
            batch = selected[start : start + ingest_batch_size]
            batch_number = idx + 1
            summary: IngestSummary = ingest_pdfs(
                selected_pdfs=batch,
                wipe=False,
                settings=settings,
                skip_existing=False,
            )

            processed += len(batch)
            ingested_articles += summary.ingested_articles
            total_chunks += summary.total_chunks
            total_references += summary.total_references
            anystyle_attempted += summary.anystyle_attempted_pdfs
            anystyle_applied += summary.anystyle_applied_pdfs
            anystyle_empty += summary.anystyle_empty_pdfs
            anystyle_failed += summary.anystyle_failed_pdfs

            for item in summary.failed_pdfs[:100]:
                failure_lines.append(f"{item['pdf']}: {item['error']}")

            remaining = max(0, total_selected - processed)
            if processed >= next_report or processed == total_selected:
                progress_lines.append(
                    f"{utc_now()} | Batch {batch_number}/{total_batches} complete. "
                    f"Processed {processed}/{total_selected}. Remaining {remaining}. "
                    f"Ingested {summary.ingested_articles}/{len(batch)}. "
                    f"Anystyle applied {summary.anystyle_applied_pdfs}, "
                    f"empty {summary.anystyle_empty_pdfs}, failed {summary.anystyle_failed_pdfs}."
                )
                while next_report <= processed:
                    next_report += report_every
                _persist()

        state = "completed"
        phase = "complete"
        progress_lines.append(f"{utc_now()} | Re-ingest completed.")
        _persist()
        return 0
    except Exception as exc:  # pragma: no cover - operational runner
        state = "failed"
        phase = "failed"
        error = str(exc)
        progress_lines.append(f"{utc_now()} | Run failed: {exc}")
        failure_lines.append(traceback.format_exc())
        _persist()
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
