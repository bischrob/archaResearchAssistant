#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ["docker", "compose", "-f", str(ROOT / "docker-compose.yml")]
AUTH = ["exec", "-T", "neo4j", "cypher-shell", "--format", "plain", "--non-interactive", "-u", "neo4j", "-p", "archaResearchAssistant", "-f", "/dev/stdin"]

YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
REF_START_RE = re.compile(r"(?:^|\s)(references cited|references|bibliography|works cited)(?:\s|$)", re.I)
LINE_START_RE = re.compile(r"^(?:[A-Z][A-Za-z'`.-]+(?:,?\s+(?:[A-Z]\.)+)?|[A-Z][A-Za-z'`.-]+,\s+[A-Z])")


def cypher_rows(query: str) -> list[Any]:
    proc = subprocess.run(COMPOSE + AUTH, input=query, cwd=ROOT, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "cypher-shell failed").strip())
    lines = [line for line in (proc.stdout or "").splitlines() if line.strip()]
    data_lines = lines[1:] if lines and lines[0].strip().lower() == 'json' else lines
    rows: list[Any] = []
    for line in data_lines:
        text = line.strip()
        if text.startswith('"') and text.endswith('"'):
            text = bytes(text[1:-1], 'utf-8').decode('unicode_escape')
        rows.append(json.loads(text))
    return rows


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def guess_reference_start(chunks: list[dict[str, Any]]) -> int:
    for chunk in chunks:
        if REF_START_RE.search(chunk.get("text", "")):
            return int(chunk["idx"])
    for chunk in reversed(chunks):
        if len(re.findall(r"\b\d{4}\b", chunk.get("text", ""))) >= 8:
            return int(chunk["idx"])
    return max(0, len(chunks) - 6)


def extract_reference_block(chunks: list[dict[str, Any]], start_idx: int) -> str:
    tail = [c for c in chunks if int(c["idx"]) >= start_idx]
    joined = "\n\n".join(normalize_ws(c.get("text", "")) for c in tail)
    m = REF_START_RE.search(joined)
    if m:
        joined = joined[m.start():]
    joined = re.sub(r"\bReceived\b.*$", "", joined, flags=re.I | re.S)
    joined = re.sub(r"\bAccepted\b.*$", "", joined, flags=re.I | re.S)
    return joined.strip()


def split_reference_block(block: str) -> list[str]:
    text = normalize_ws(block)
    text = re.sub(r"^(References Cited|References|Bibliography|Works Cited)\s+", "", text, flags=re.I)
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl")
    candidates = re.split(r"(?=(?:[A-Z][A-Za-z'`.-]+,\s+[A-Z]|[A-Z][A-Za-z'`.-]+\s+[A-Z]\.)[^\n]{0,60}?\b(?:19|20)\d{2}\b)", text)
    cleaned: list[str] = []
    buf = ""
    for part in candidates:
        part = normalize_ws(part)
        if not part:
            continue
        if YEAR_RE.search(part) and (LINE_START_RE.match(part) or part[:1].isupper()):
            if buf:
                cleaned.append(buf)
            buf = part
        else:
            buf = f"{buf} {part}".strip() if buf else part
    if buf:
        cleaned.append(buf)
    return [c for c in (normalize_ws(x) for x in cleaned) if c]


def export_article(article_id: str, output_dir: Path) -> None:
    article_rows = cypher_rows(f"MATCH (a:Article {{id: '{article_id}'}}) RETURN apoc.convert.toJson(a {{.id, .title, .source_path, .year, .doi}}) AS json")
    chunk_rows = cypher_rows(f"MATCH (:Article {{id: '{article_id}'}})<-[:IN_ARTICLE]-(c:Chunk) RETURN apoc.convert.toJson(c {{idx:c.index, p1:c.page_start, p2:c.page_end, text:c.text}}) AS json ORDER BY c.index")
    article = article_rows[0] if article_rows else None
    chunks = chunk_rows
    if not chunks:
        raise SystemExit(f"No chunks found for article: {article_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    start_idx = guess_reference_start(chunks)
    block = extract_reference_block(chunks, start_idx)
    draft_lines = split_reference_block(block)
    stem = article_id
    (output_dir / f"{stem}.article.json").write_text(json.dumps(article, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / f"{stem}.chunks.references.json").write_text(json.dumps([c for c in chunks if c['idx'] >= start_idx], indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / f"{stem}.references.block.txt").write_text(block + "\n", encoding="utf-8")
    (output_dir / f"{stem}.references.draft.txt").write_text("\n".join(draft_lines) + "\n", encoding="utf-8")
    print(json.dumps({"article_id": article_id, "start_chunk": start_idx, "draft_reference_count": len(draft_lines), "output_dir": str(output_dir)}, indent=2))


def import_references(article_id: str, refs_path: Path, article_id_out: str | None, dry_run: bool, parse_with_anystyle: bool) -> None:
    target_id = article_id_out or article_id
    refs = [normalize_ws(line) for line in refs_path.read_text(encoding='utf-8').splitlines()]
    refs = [line for line in refs if line]
    if not refs:
        raise SystemExit(f"No references found in {refs_path}")
    if parse_with_anystyle:
        from src.rag.anystyle_refs import parse_reference_strings_with_anystyle_docker
        citations = parse_reference_strings_with_anystyle_docker(refs, article_id=target_id, project_root=ROOT)
        payload = [{"id": c.citation_id, "raw_text": c.raw_text, "year": c.year, "title_guess": c.title_guess, "title_norm": c.normalized_title, "doi": c.doi, "source": "manual_reference_lines+anystyle", "type_guess": c.type_guess, "author_tokens": c.author_tokens or [], "quality_score": c.quality_score, "reference_source_path": str(refs_path)} for c in citations]
    else:
        payload = [{"id": f"{target_id}::ref::{i}", "raw_text": ref, "year": int(YEAR_RE.search(ref).group(0)) if YEAR_RE.search(ref) else None, "title_guess": ref[:120], "title_norm": re.sub(r"[^a-z0-9]+", " ", ref.lower()).strip(), "doi": None, "source": "manual_reference_lines", "type_guess": None, "author_tokens": [], "quality_score": None, "reference_source_path": str(refs_path)} for i, ref in enumerate(refs)]
    if dry_run:
        print(json.dumps({"target_article_id": target_id, "count": len(payload), "sample": payload[:5]}, indent=2, ensure_ascii=False))
        return
    query = f"""
MATCH (src:Article {{id: '{article_id}'}})
MERGE (dst:Article {{id: '{target_id}'}})
ON CREATE SET dst.title = src.title,
              dst.title_norm = src.title_norm,
              dst.year = src.year,
              dst.source_path = src.source_path,
              dst.source_path_norm = src.source_path_norm,
              dst.source_filename_stem_norm = src.source_filename_stem_norm,
              dst.citekey = src.citekey,
              dst.paperpile_id = src.paperpile_id,
              dst.zotero_persistent_id = src.zotero_persistent_id,
              dst.zotero_item_key = src.zotero_item_key,
              dst.zotero_item_key_norm = src.zotero_item_key_norm,
              dst.zotero_attachment_key = src.zotero_attachment_key,
              dst.zotero_attachment_key_norm = src.zotero_attachment_key_norm,
              dst.doi = src.doi,
              dst.doi_norm = src.doi_norm,
              dst.journal = src.journal,
              dst.publisher = src.publisher,
              dst.title_year_key = src.title_year_key,
              dst.title_year_key_norm = src.title_year_key_norm,
              dst.metadata_source = src.metadata_source,
              dst.reference_demo_of = src.id;
MATCH (dst:Article {{id: '{target_id}'}})
OPTIONAL MATCH (dst)-[oldc:CITES]->(:Article)
DELETE oldc;
MATCH (dst:Article {{id: '{target_id}'}})
OPTIONAL MATCH (dst)-[:CITES_REFERENCE]->(oldr:Reference)
WHERE oldr.id STARTS WITH '{target_id}::ref::'
DETACH DELETE oldr;
"""
    for row in payload:
        query += f"""
MATCH (dst:Article {{id: {json.dumps(target_id)} }})
MERGE (r:Reference {{id: {json.dumps(row['id'])} }})
SET r.raw_text = {json.dumps(row['raw_text'])},
    r.year = {('null' if row['year'] is None else row['year'])},
    r.title_guess = {json.dumps(row['title_guess'])},
    r.title_norm = {json.dumps(row['title_norm'])},
    r.author_tokens = {json.dumps(row['author_tokens'])},
    r.doi = {('null' if row['doi'] is None else json.dumps(row['doi']))},
    r.source = {json.dumps(row['source'])},
    r.type_guess = {('null' if row['type_guess'] is None else json.dumps(row['type_guess']))},
    r.quality_score = {('null' if row['quality_score'] is None else row['quality_score'])},
    r.reference_source_path = {json.dumps(row['reference_source_path'])},
    r.reference_import_method = 'manual_reference_roundtrip'
MERGE (dst)-[:CITES_REFERENCE]->(r);
"""
    query += f"MATCH (:Article {{id: '{target_id}'}})-[:CITES_REFERENCE]->(r:Reference) RETURN count(r) AS imported;"
    proc = subprocess.run(COMPOSE + AUTH, input=query, cwd=ROOT, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    print(proc.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description='Export reference-section chunks from Neo4j and reimport cleaned references.')
    sub = parser.add_subparsers(dest='cmd', required=True)
    ex = sub.add_parser('export')
    ex.add_argument('article_id')
    ex.add_argument('--output-dir', default='.cache/reference_roundtrip')
    im = sub.add_parser('import')
    im.add_argument('article_id')
    im.add_argument('references_txt')
    im.add_argument('--article-id-out', default='')
    im.add_argument('--dry-run', action='store_true')
    im.add_argument('--parse-with-anystyle', action='store_true')
    args = parser.parse_args()
    if args.cmd == 'export':
        export_article(args.article_id, (ROOT / args.output_dir).resolve())
    else:
        import_references(args.article_id, Path(args.references_txt).resolve(), args.article_id_out or None, args.dry_run, args.parse_with_anystyle)


if __name__ == '__main__':
    main()
