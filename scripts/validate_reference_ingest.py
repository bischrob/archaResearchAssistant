#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.neo4j_store import GraphStore
from src.rag.pipeline import IngestSummary, ingest_pdfs


def _log(message: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{now}] {message}", flush=True)


def _make_store(settings: Settings) -> GraphStore:
    return GraphStore(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        embedding_model=settings.embedding_model,
    )


def _cleanup_selected_articles(settings: Settings, article_ids: list[str]) -> None:
    if not article_ids:
        return
    store = _make_store(settings)
    try:
        with store.driver.session() as session:
            session.run(
                """
                UNWIND $article_ids AS article_id
                MATCH (a:Article {id: article_id})
                OPTIONAL MATCH (a)<-[:IN_ARTICLE]-(c:Chunk)
                DETACH DELETE c
                WITH a
                OPTIONAL MATCH (a)-[:CITES_REFERENCE]->(r:Reference)
                WHERE r.id STARTS WITH (a.id + '::ref::')
                DETACH DELETE r
                WITH a
                DETACH DELETE a
                """,
                article_ids=article_ids,
            )
            session.run("MATCH (t:Token) WHERE NOT ()-[:MENTIONS]->(t) DETACH DELETE t")
            session.run("MATCH (au:Author) WHERE NOT (au)-[:WROTE]->() DETACH DELETE au")
    finally:
        store.close()


def _collect_references(settings: Settings, article_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    rows_by_article: dict[str, list[dict[str, Any]]] = {article_id: [] for article_id in article_ids}
    if not article_ids:
        return rows_by_article

    store = _make_store(settings)
    try:
        with store.driver.session() as session:
            rows = session.run(
                """
                MATCH (a:Article)-[:CITES_REFERENCE]->(r:Reference)
                WHERE a.id IN $article_ids
                RETURN a.id AS article_id,
                       r.id AS ref_id,
                       coalesce(r.title_guess, '') AS title_guess,
                       coalesce(r.title_norm, '') AS title_norm,
                       r.year AS year,
                       coalesce(r.doi, '') AS doi,
                       coalesce(r.source, '') AS source,
                       coalesce(r.raw_text, '') AS raw_text
                ORDER BY article_id, ref_id
                """,
                article_ids=article_ids,
            )
            for row in rows:
                rows_by_article.setdefault(row["article_id"], []).append(dict(row))
    finally:
        store.close()
    return rows_by_article


def _normalize_ws(text: str) -> str:
    return " ".join((text or "").split())


def _fingerprint(ref: dict[str, Any]) -> str:
    title_norm = _normalize_ws(str(ref.get("title_norm") or "")).lower()
    year = str(ref.get("year") or "").strip()
    doi = _normalize_ws(str(ref.get("doi") or "")).lower()
    raw = _normalize_ws(str(ref.get("raw_text") or "")).lower()[:280]
    return "|".join([title_norm, year, doi, raw])


def _to_samples(items: list[dict[str, Any]], limit: int = 8) -> list[str]:
    out: list[str] = []
    for item in items[:limit]:
        title = str(item.get("title_guess") or "").strip()
        year = item.get("year")
        doi = str(item.get("doi") or "").strip()
        raw = _normalize_ws(str(item.get("raw_text") or "")).strip()
        raw_short = raw[:180] + ("..." if len(raw) > 180 else "")
        out.append(f"title={title!r}; year={year!r}; doi={doi!r}; raw={raw_short!r}")
    return out


def _diff_references(
    before: dict[str, list[dict[str, Any]]],
    after: dict[str, list[dict[str, Any]]],
    article_ids: list[str],
) -> dict[str, Any]:
    per_article: dict[str, Any] = {}
    total_before = 0
    total_after = 0
    total_added = 0
    total_removed = 0

    for article_id in article_ids:
        before_rows = before.get(article_id, [])
        after_rows = after.get(article_id, [])
        total_before += len(before_rows)
        total_after += len(after_rows)

        before_map = {_fingerprint(r): r for r in before_rows}
        after_map = {_fingerprint(r): r for r in after_rows}
        added_keys = sorted(set(after_map) - set(before_map))
        removed_keys = sorted(set(before_map) - set(after_map))
        kept = len(set(before_map) & set(after_map))

        total_added += len(added_keys)
        total_removed += len(removed_keys)

        per_article[article_id] = {
            "before_count": len(before_rows),
            "after_count": len(after_rows),
            "kept_count": kept,
            "added_count": len(added_keys),
            "removed_count": len(removed_keys),
            "added_samples": _to_samples([after_map[k] for k in added_keys]),
            "removed_samples": _to_samples([before_map[k] for k in removed_keys]),
        }

    return {
        "totals": {
            "before_count": total_before,
            "after_count": total_after,
            "kept_count": total_before - total_removed,
            "added_count": total_added,
            "removed_count": total_removed,
        },
        "per_article": per_article,
    }


def _summary_to_dict(summary: IngestSummary) -> dict[str, Any]:
    return asdict(summary)


def _write_markdown_report(
    output_path: Path,
    *,
    pdf_paths: list[Path],
    baseline_summary: dict[str, Any],
    rerun_summary: dict[str, Any],
    diff: dict[str, Any],
    config: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.append("# Ingest Reference Validation")
    lines.append("")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- PDFs: {', '.join(str(p) for p in pdf_paths)}")
    lines.append("")
    lines.append("## Config")
    lines.append("")
    for key, value in config.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Totals")
    lines.append("")
    totals = diff["totals"]
    lines.append(f"- Before references: {totals['before_count']}")
    lines.append(f"- After references: {totals['after_count']}")
    lines.append(f"- Kept: {totals['kept_count']}")
    lines.append(f"- Added: {totals['added_count']}")
    lines.append(f"- Removed: {totals['removed_count']}")
    lines.append("")
    lines.append("## Per Article")
    lines.append("")
    for article_id, details in diff["per_article"].items():
        lines.append(f"### {article_id}")
        lines.append("")
        lines.append(f"- Before: {details['before_count']}")
        lines.append(f"- After: {details['after_count']}")
        lines.append(f"- Kept: {details['kept_count']}")
        lines.append(f"- Added: {details['added_count']}")
        lines.append(f"- Removed: {details['removed_count']}")
        if details["added_samples"]:
            lines.append("- Added samples:")
            for sample in details["added_samples"]:
                lines.append(f"  - {sample}")
        if details["removed_samples"]:
            lines.append("- Removed samples:")
            for sample in details["removed_samples"]:
                lines.append(f"  - {sample}")
        lines.append("")
    lines.append("## Baseline Ingest Summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(baseline_summary, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    lines.append("## Rerun Ingest Summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(rerun_summary, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Small ingest validation: compare references before vs after rerun parser."
    )
    parser.add_argument(
        "--pdf",
        action="append",
        required=True,
        help=r"Relative path to PDF (repeatable). Example: --pdf \\192.168.0.37\pooled\media\Books\pdfs\file.pdf",
    )
    parser.add_argument(
        "--qwen-model-path",
        default="",
        help="Qwen model path. Falls back to Settings/QWEN3_MODEL_PATH if omitted.",
    )
    parser.add_argument(
        "--qwen-citation-adapter-path",
        default="",
        help="LoRA adapter path for citation extraction.",
    )
    parser.add_argument("--qwen-device", default="cuda:0")
    parser.add_argument("--qwen-dtype", default="fp16")
    parser.add_argument("--qwen-citation-batch-size", type=int, default=8)
    parser.add_argument("--qwen-citation-max-new-tokens", type=int, default=128)
    parser.add_argument(
        "--anystyle-use-gpu",
        action="store_true",
        help="Run Anystyle docker compose commands with `--gpus`.",
    )
    parser.add_argument(
        "--anystyle-gpu-devices",
        default="all",
        help="Docker `--gpus` value (for example: all, device=0).",
    )
    parser.add_argument(
        "--anystyle-gpu-service",
        default="anystyle-gpu",
        help="Docker compose service used for GPU Anystyle runs.",
    )
    parser.add_argument(
        "--rerun-parser",
        default="qwen",
        help=(
            "Citation parser for rerun ingest "
            "(e.g., qwen, qwen_refsplit_anystyle, anystyle, heuristic)."
        ),
    )
    parser.add_argument(
        "--output-json",
        default="data/ingest_reference_validation_report.json",
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--output-md",
        default="data/ingest_reference_validation_report.md",
        help="Output Markdown report path.",
    )
    parser.add_argument(
        "--clear-qwen-cache",
        action="store_true",
        help="Delete .cache/qwen_refs before rerun.",
    )
    return parser.parse_args()


def _resolve_pdfs(raw_paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in raw_paths:
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / p
        p = p.resolve()
        if not p.exists():
            raise FileNotFoundError(f"PDF not found: {p}")
        out.append(p)
    return out


def _progress(prefix: str):
    def _inner(pct: float, msg: str) -> None:
        _log(f"{prefix} {pct:6.2f}% | {msg}")

    return _inner


def main() -> None:
    args = parse_args()
    pdf_paths = _resolve_pdfs(args.pdf)
    article_ids = [p.stem for p in pdf_paths]
    rerun_parser = (args.rerun_parser or "qwen").strip().lower()

    cfg_base = Settings()
    requires_qwen = rerun_parser.startswith("qwen")
    qwen_model_path = args.qwen_model_path or cfg_base.qwen_model_path
    qwen_adapter_path = args.qwen_citation_adapter_path or cfg_base.qwen_citation_adapter_path
    if requires_qwen and not qwen_model_path:
        raise RuntimeError("Qwen model path missing. Pass --qwen-model-path or set QWEN3_MODEL_PATH.")
    if requires_qwen and not qwen_adapter_path:
        raise RuntimeError(
            "Qwen citation adapter path missing. Pass --qwen-citation-adapter-path or set QWEN3_CITATION_ADAPTER_PATH."
        )

    _log(f"Selected PDFs ({len(pdf_paths)}): {', '.join(str(p) for p in pdf_paths)}")
    _log(f"Target article IDs: {', '.join(article_ids)}")
    _log("Cleaning selected article subgraph before baseline ingest")
    _cleanup_selected_articles(cfg_base, article_ids)

    baseline_cfg = replace(Settings(), citation_parser="heuristic")

    _log("Running baseline ingest with citation_parser=heuristic")
    baseline_summary = ingest_pdfs(
        selected_pdfs=pdf_paths,
        wipe=False,
        settings=baseline_cfg,
        skip_existing=False,
        progress_callback=_progress("baseline"),
    )
    before_refs = _collect_references(baseline_cfg, article_ids)
    _log("Baseline ingest complete")

    if args.clear_qwen_cache:
        qwen_cache_dirs = [
            ROOT / ".cache" / "qwen_refs",
            ROOT / ".cache" / "qwen_structured_refs",
        ]
        for qwen_cache_dir in qwen_cache_dirs:
            if qwen_cache_dir.exists():
                _log(f"Clearing cache directory: {qwen_cache_dir}")
                shutil.rmtree(qwen_cache_dir)

    rerun_cfg = replace(
        Settings(),
        citation_parser=rerun_parser,
        qwen_model_path=qwen_model_path or "",
        qwen_citation_model_path=qwen_model_path or "",
        qwen_citation_adapter_path=qwen_adapter_path or "",
        qwen_device=args.qwen_device,
        qwen_dtype=args.qwen_dtype,
        qwen_citation_batch_size=max(1, int(args.qwen_citation_batch_size)),
        qwen_citation_max_new_tokens=max(16, int(args.qwen_citation_max_new_tokens)),
        anystyle_use_gpu=bool(args.anystyle_use_gpu),
        anystyle_gpu_devices=(args.anystyle_gpu_devices or "all").strip() or "all",
        anystyle_gpu_service=(args.anystyle_gpu_service or "anystyle-gpu").strip() or "anystyle-gpu",
        qwen_require_success=True,
    )

    _log(
        f"Running rerun ingest with citation_parser={rerun_cfg.citation_parser} "
        f"(device={rerun_cfg.qwen_device}, dtype={rerun_cfg.qwen_dtype}, batch={rerun_cfg.qwen_citation_batch_size})"
    )
    rerun_summary = ingest_pdfs(
        selected_pdfs=pdf_paths,
        wipe=False,
        settings=rerun_cfg,
        skip_existing=False,
        progress_callback=_progress("rerun"),
    )
    after_refs = _collect_references(rerun_cfg, article_ids)
    _log("Rerun ingest complete")

    diff = _diff_references(before_refs, after_refs, article_ids)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pdfs": [str(p) for p in pdf_paths],
        "article_ids": article_ids,
        "config": {
            "baseline_parser": "heuristic",
            "rerun_parser": rerun_cfg.citation_parser,
            "qwen_model_path": str(qwen_model_path or ""),
            "qwen_citation_adapter_path": str(qwen_adapter_path or ""),
            "qwen_device": rerun_cfg.qwen_device,
            "qwen_dtype": rerun_cfg.qwen_dtype,
            "qwen_citation_batch_size": rerun_cfg.qwen_citation_batch_size,
            "qwen_citation_max_new_tokens": rerun_cfg.qwen_citation_max_new_tokens,
            "anystyle_use_gpu": rerun_cfg.anystyle_use_gpu,
            "anystyle_gpu_devices": rerun_cfg.anystyle_gpu_devices,
            "anystyle_gpu_service": rerun_cfg.anystyle_gpu_service,
            "clear_qwen_cache": bool(args.clear_qwen_cache),
        },
        "baseline_summary": _summary_to_dict(baseline_summary),
        "rerun_summary": _summary_to_dict(rerun_summary),
        "before_references": before_refs,
        "after_references": after_refs,
        "diff": diff,
    }

    output_json = Path(args.output_json)
    if not output_json.is_absolute():
        output_json = (ROOT / output_json).resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    output_md = Path(args.output_md)
    if not output_md.is_absolute():
        output_md = (ROOT / output_md).resolve()
    output_md.parent.mkdir(parents=True, exist_ok=True)
    _write_markdown_report(
        output_md,
        pdf_paths=pdf_paths,
        baseline_summary=_summary_to_dict(baseline_summary),
        rerun_summary=_summary_to_dict(rerun_summary),
        diff=diff,
        config=report["config"],
    )

    _log(f"Wrote JSON report: {output_json}")
    _log(f"Wrote Markdown report: {output_md}")
    _log(
        "Totals: before={before}, after={after}, kept={kept}, added={added}, removed={removed}".format(
            before=diff["totals"]["before_count"],
            after=diff["totals"]["after_count"],
            kept=diff["totals"]["kept_count"],
            added=diff["totals"]["added_count"],
            removed=diff["totals"]["removed_count"],
        )
    )


if __name__ == "__main__":
    main()
