from __future__ import annotations

import csv
import io
from datetime import datetime, UTC
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

