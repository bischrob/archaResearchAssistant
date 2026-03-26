#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.neo4j_store import GraphStore
from src.rag.retrieval import contextual_retrieve


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Re-embed all existing chunk nodes in controlled batches with checkpoints.')
    parser.add_argument('--batch-size', type=int, default=64, help='Number of chunks per embedding/write batch')
    parser.add_argument('--start-offset', type=int, default=0, help='Chunk offset to start from')
    parser.add_argument('--max-chunks', type=int, default=0, help='Optional cap for validation runs; 0 means process through the end')
    parser.add_argument('--checkpoint-file', default='logs/reembed_all_chunks_checkpoint.json', help='Checkpoint/status JSON path')
    parser.add_argument('--progress-log', default='logs/reembed_all_chunks_progress.log', help='Append-only progress log path')
    parser.add_argument('--report-every-seconds', type=int, default=3600, help='Emit progress summary at most once per interval')
    parser.add_argument('--validate-query', default='', help='Optional retrieval query to run at the end')
    parser.add_argument('--dry-run', action='store_true', help='Read and encode batches without writing back')
    return parser.parse_args()


def count_chunks(store: GraphStore) -> int:
    with store.driver.session() as session:
        row = session.run('MATCH (c:Chunk) RETURN count(c) AS n').single()
        return int(row['n'] or 0)


def fetch_batch(store: GraphStore, *, offset: int, limit: int) -> list[dict]:
    with store.driver.session() as session:
        rows = session.run(
            '''
            MATCH (c:Chunk)
            RETURN c.id AS chunk_id, c.text AS chunk_text
            ORDER BY c.id ASC
            SKIP $offset
            LIMIT $limit
            ''',
            offset=max(0, int(offset)),
            limit=max(1, int(limit)),
        )
        return [dict(r) for r in rows]


def write_embeddings(store: GraphStore, rows: list[dict]) -> None:
    payload = [{'id': row['chunk_id'], 'embedding': row['embedding']} for row in rows]
    if not payload:
        return
    with store.driver.session() as session:
        session.run(
            '''
            UNWIND $rows AS row
            MATCH (c:Chunk {id: row.id})
            SET c.embedding = row.embedding
            ''',
            rows=payload,
        )


def append_progress(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as fh:
        fh.write(message + '\n')


def write_checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding='utf-8')


def main() -> None:
    args = parse_args()
    settings = Settings()
    checkpoint_path = (ROOT / args.checkpoint_file).resolve()
    progress_log_path = (ROOT / args.progress_log).resolve()
    start_ts = time.time()
    last_report_ts = 0.0

    store = GraphStore(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        embedding_model=settings.embedding_model,
    )
    try:
        total_chunks = count_chunks(store)
        if total_chunks <= 0:
            msg = f"{utc_now()} | No chunk nodes found. Nothing to re-embed."
            print(msg, flush=True)
            append_progress(progress_log_path, msg)
            write_checkpoint(checkpoint_path, {
                'status': 'completed',
                'processed_chunks': 0,
                'total_chunks': 0,
                'completed_at': utc_now(),
            })
            return

        batch_size = max(1, int(args.batch_size))
        start_offset = max(0, int(args.start_offset))
        offset = start_offset
        max_chunks = max(0, int(args.max_chunks))
        target_end = min(total_chunks, start_offset + max_chunks) if max_chunks else total_chunks
        target_total = max(0, target_end - start_offset)
        processed_in_scope = 0
        total_batches = max(1, (target_total + batch_size - 1) // batch_size) if target_total else 1
        start_msg = (
            f"{utc_now()} | Starting re-embedding from offset {start_offset}. "
            f"Target end={target_end}, total chunks={total_chunks}, batch_size={batch_size}, dry_run={bool(args.dry_run)}"
        )
        print(start_msg, flush=True)
        append_progress(progress_log_path, start_msg)

        batch_index = 0
        while offset < target_end:
            limit = min(batch_size, target_end - offset)
            rows = fetch_batch(store, offset=offset, limit=limit)
            if not rows:
                break
            texts = [str(row.get('chunk_text') or '') for row in rows]
            embeddings = store.embedder.encode(texts)
            for row, emb in zip(rows, embeddings):
                row['embedding'] = emb
            if not args.dry_run:
                write_embeddings(store, rows)

            offset += len(rows)
            processed_in_scope += len(rows)
            batch_index += 1

            now = time.time()
            elapsed = max(1.0, now - start_ts)
            rate = processed_in_scope / elapsed
            pct = (processed_in_scope / target_total) * 100.0 if target_total else 100.0
            checkpoint = {
                'status': 'running' if offset < target_end else 'completed',
                'processed_chunks': offset,
                'processed_in_scope': processed_in_scope,
                'total_chunks': total_chunks,
                'target_end': target_end,
                'target_total': target_total,
                'batch_size': batch_size,
                'batches_completed': batch_index,
                'total_batches_estimate': total_batches,
                'percent_complete': round(pct, 4),
                'chunks_per_second': round(rate, 4),
                'last_offset': offset,
                'updated_at': utc_now(),
                'dry_run': bool(args.dry_run),
            }
            write_checkpoint(checkpoint_path, checkpoint)

            if (now - last_report_ts) >= max(1, int(args.report_every_seconds)) or offset >= target_end:
                report = (
                    f"{utc_now()} | Progress {processed_in_scope}/{target_total or total_chunks} chunks in scope "
                    f"({pct:.2f}%) after {batch_index} batches at ~{rate:.2f} chunks/sec"
                )
                print(report, flush=True)
                append_progress(progress_log_path, report)
                last_report_ts = now

        final_status = {
            'status': 'completed',
            'processed_chunks': offset,
            'processed_in_scope': processed_in_scope,
            'total_chunks': total_chunks,
            'target_end': target_end,
            'target_total': target_total,
            'batch_size': batch_size,
            'batches_completed': batch_index,
            'percent_complete': round((processed_in_scope / target_total) * 100.0, 4) if target_total else 100.0,
            'updated_at': utc_now(),
            'completed_at': utc_now(),
            'dry_run': bool(args.dry_run),
        }

        if args.validate_query:
            rows = contextual_retrieve(store, query=args.validate_query, limit=3)
            final_status['validation_query'] = args.validate_query
            final_status['validation_hits'] = [
                {
                    'rank': idx,
                    'article_title': row.get('article_title'),
                    'chunk_id': row.get('chunk_id'),
                    'score': row.get('combined_score', row.get('rerank_score', 0.0)),
                    'snippet': (row.get('chunk_text') or '')[:240].replace('\n', ' '),
                }
                for idx, row in enumerate(rows, start=1)
            ]
            validation_msg = f"{utc_now()} | Validation query complete: {args.validate_query}"
            append_progress(progress_log_path, validation_msg)
            print(validation_msg, flush=True)

        write_checkpoint(checkpoint_path, final_status)
        done_msg = f"{utc_now()} | Re-embedding completed. Processed {processed_in_scope}/{target_total or total_chunks} chunks in scope."
        print(done_msg, flush=True)
        append_progress(progress_log_path, done_msg)
    finally:
        store.close()


if __name__ == '__main__':
    main()
