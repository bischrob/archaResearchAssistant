from __future__ import annotations

import csv
import io
import shutil
import subprocess
import tempfile
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


def to_markdown(report: dict[str, Any]) -> str:
    lines = []
    lines.append(f"# RAG Answer Report")
    lines.append("")
    lines.append(f"- Generated: {datetime.now(UTC).isoformat()}")
    lines.append(f"- Question: {report.get('question', '')}")
    lines.append(f"- Model: {report.get('model', '')}")
    lines.append(f"- RAG Results: {report.get('rag_results_count', 0)}")
    audit = report.get("audit") or {}
    lines.append(f"- Risk: {audit.get('risk_label', 'n/a')} ({audit.get('risk_score', 'n/a')})")
    lines.append("")
    lines.append("## Answer")
    lines.append("")
    lines.append(report.get("answer", ""))
    lines.append("")
    lines.append("## Used Citations")
    lines.append("")
    used = report.get("used_citations") or []
    if not used:
        lines.append("- None")
    else:
        for c in used:
            lines.append(
                f"- [{c.get('citation_id')}] {c.get('article_title')} ({c.get('article_year')}) "
                f"| Authors: {', '.join(c.get('authors') or [])} "
                f"| Citekey: {c.get('citekey') or ''} "
                f"| DOI: {c.get('doi') or ''} "
                f"| Pages: {c.get('page_start')}-{c.get('page_end')}"
            )
    return "\n".join(lines)


def citations_to_csv(report: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["citation_id", "article_title", "article_year", "authors", "citekey", "doi", "page_start", "page_end", "chunk_id"]
    )
    for c in report.get("used_citations") or []:
        writer.writerow(
            [
                c.get("citation_id"),
                c.get("article_title"),
                c.get("article_year"),
                "; ".join(c.get("authors") or []),
                c.get("citekey"),
                c.get("doi"),
                c.get("page_start"),
                c.get("page_end"),
                c.get("chunk_id"),
            ]
        )
    return buf.getvalue()


def markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    if not shutil.which("pandoc"):
        raise RuntimeError("Pandoc is not installed or not in PATH.")

    with tempfile.TemporaryDirectory(prefix="rag_report_") as tmpdir:
        tmp = Path(tmpdir)
        md_path = tmp / "report.md"
        pdf_path = tmp / "report.pdf"
        md_path.write_text(markdown_text, encoding="utf-8")

        engine_candidates = [None, "wkhtmltopdf", "weasyprint", "xelatex", "pdflatex"]
        errors: list[str] = []
        for engine in engine_candidates:
            if engine and not shutil.which(engine):
                continue
            cmd = ["pandoc", str(md_path), "-o", str(pdf_path)]
            if engine:
                cmd.extend(["--pdf-engine", engine])
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode == 0 and pdf_path.exists():
                return pdf_path.read_bytes()
            err = (proc.stderr or proc.stdout or "").strip()
            label = engine or "default"
            errors.append(f"{label}: {err[:300]}")

    raise RuntimeError("Failed to generate PDF via pandoc. " + " | ".join(errors))
