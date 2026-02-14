#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.neo4j_store import GraphStore
from src.rag.pdf_processing import load_article


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Neo4j graph for PDF-based RAG testing.")
    parser.add_argument(
        "--pdf-dir",
        default="pdf2epub/input",
        help="Directory containing candidate PDFs.",
    )
    parser.add_argument(
        "--pdf",
        action="append",
        default=[],
        help="Specific PDF path(s). If omitted, first 3 PDFs from --pdf-dir are used.",
    )
    parser.add_argument("--num-pdfs", type=int, default=3, help="Number of PDFs when using --pdf-dir.")
    parser.add_argument("--wipe", action="store_true", help="Delete existing RAG labels before ingest.")
    return parser.parse_args()


def choose_pdfs(args: argparse.Namespace) -> list[Path]:
    if args.pdf:
        selected = [Path(p) for p in args.pdf]
    else:
        all_pdfs = sorted(Path(args.pdf_dir).glob("*.pdf"))
        selected = all_pdfs[: args.num_pdfs]
    missing = [p for p in selected if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing PDFs: {', '.join(str(m) for m in missing)}")
    if len(selected) < 1:
        raise ValueError("No PDFs found to ingest.")
    return selected


def main() -> None:
    args = parse_args()
    settings = Settings()
    pdfs = choose_pdfs(args)

    print("Selected PDFs:")
    for p in pdfs:
        print(f" - {p}")

    articles = [
        load_article(
            pdf_path=p,
            chunk_size_words=settings.chunk_size_words,
            chunk_overlap_words=settings.chunk_overlap_words,
        )
        for p in pdfs
    ]

    store = GraphStore(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        embedding_model=settings.embedding_model,
    )
    try:
        if args.wipe:
            print("Clearing existing RAG graph labels...")
            store.clear_graph()
        print("Creating schema/indexes...")
        store.setup_schema(vector_dimensions=store.embedding_dimension)
        print("Ingesting articles, chunks, tokens, and citations...")
        store.ingest_articles(articles)
    finally:
        store.close()

    print("Done.")
    print(f"Ingested articles: {len(articles)}")
    print(f"Total chunks: {sum(len(a.chunks) for a in articles)}")
    print(f"Total extracted references: {sum(len(a.citations) for a in articles)}")


if __name__ == "__main__":
    main()
