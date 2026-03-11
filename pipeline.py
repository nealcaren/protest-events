"""Run the full pipeline: embed → search → classify, processing in batches.

Embeds new batches locally via nomic-embed-text, then immediately searches
and classifies each batch's candidates before moving to the next embedding batch.
"""

import os
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from openai import OpenAI

from config import (
    OCR_DIR, DATA_DIR, EMBEDDINGS_FILE, EMBEDDING_MODEL,
    SEED_QUERIES, SIMILARITY_THRESHOLD, CLASSIFIER_MODEL, OPENROUTER_BASE_URL,
)
from db import get_connection, init_db
from embed import extract_page_texts, load_model, embed_texts, save_chunks_to_db
from classify import SYSTEM_PROMPT, USER_TEMPLATE, classify_group, group_adjacent_chunks

SHARDS_DIR = DATA_DIR / "shards"


def embed_queries(model, queries: list[str]) -> np.ndarray:
    """Embed queries with the query task prefix."""
    prefixed = ["search_query: " + q for q in queries]
    return model.encode(prefixed, normalize_embeddings=True)


def search_batch(query_embs: np.ndarray, batch_embs: np.ndarray,
                 queries: list[str], threshold: float,
                 batch_chunk_ids: list[int]) -> list[tuple[int, float, str]]:
    """Search a batch of embeddings against queries. Returns (chunk_id, similarity, query) tuples."""
    emb_norm = batch_embs / np.linalg.norm(batch_embs, axis=1, keepdims=True)
    q_norm = query_embs / np.linalg.norm(query_embs, axis=1, keepdims=True)

    sims = q_norm @ emb_norm.T
    max_sims = sims.max(axis=0)
    best_query_idx = sims.argmax(axis=0)

    hits = []
    for i in range(len(batch_chunk_ids)):
        if max_sims[i] >= threshold:
            hits.append((batch_chunk_ids[i], float(max_sims[i]), queries[best_query_idx[i]]))
    return hits


def classify_candidates(conn, candidate_rows: list[dict],
                        client: OpenAI,
                        workers: int = 10) -> int:
    """Classify candidates in parallel (with adjacent merging). Returns count of new events."""
    groups = group_adjacent_chunks(candidate_rows)
    new_events = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(classify_group, client, g): g for g in groups}
        for future in as_completed(futures):
            group, result = future.result()

            if result and result.get("is_protest"):
                primary_id = group["chunk_ids"][0]
                conn.execute(
                    """INSERT INTO events
                       (chunk_id, similarity, matched_query, event_type, description,
                        location, participants, date_mentioned, source_text)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (primary_id, round(group["similarity"], 3), group["matched_query"],
                     result.get("event_type"), result.get("description"),
                     result.get("location"), result.get("participants"),
                     result.get("date_mentioned"), str(group["text"])[:3000]),
                )
                new_events += 1

            for cid in group["chunk_ids"]:
                conn.execute("INSERT OR IGNORE INTO classified (chunk_id) VALUES (?)", (cid,))

    conn.commit()
    return new_events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY environment variable")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SHARDS_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize database
    conn = get_connection()
    init_db(conn)

    # Extract regions
    print("Extracting regions...")
    t0 = time.time()
    chunks = extract_page_texts(OCR_DIR, max_files=args.max_files)
    print(f"Created {len(chunks)} chunks in {time.time()-t0:.1f}s")

    if not chunks:
        print("No chunks found.")
        conn.close()
        return

    # Save chunks to database
    print("Saving chunks to database...")
    chunk_ids = save_chunks_to_db(conn, chunks)
    texts = [c["text"][:8000] for c in chunks]
    total_batches = (len(texts) + args.batch_size - 1) // args.batch_size

    # Check existing shards
    existing_shards = sorted(SHARDS_DIR.glob("batch_*.npy"))
    start_batch = len(existing_shards)

    existing_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    if existing_events > 0:
        print(f"Loaded {existing_events} existing events")

    # Load embedding model once
    print(f"Loading model {EMBEDDING_MODEL}...")
    model = load_model()

    # OpenRouter client for classification
    or_client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)

    # Embed queries once
    print("Embedding queries...")
    query_embs = embed_queries(model, SEED_QUERIES)

    if start_batch > 0:
        print(f"Resuming from batch {start_batch}/{total_batches} ({start_batch * args.batch_size} regions embedded)")

    pipeline_t0 = time.time()

    for batch_num in range(start_batch, total_batches):
        i = batch_num * args.batch_size
        batch_texts = texts[i:i + args.batch_size]
        batch_chunk_ids = chunk_ids[i:i + args.batch_size]
        batch_end = min(i + args.batch_size, len(texts))

        # 1. Embed
        t0 = time.time()
        batch_embs = embed_texts(model, batch_texts)
        np.save(SHARDS_DIR / f"batch_{batch_num:04d}.npy", batch_embs)
        embed_time = time.time() - t0

        # 2. Search
        hits = search_batch(query_embs, batch_embs, SEED_QUERIES, args.threshold, batch_chunk_ids)

        # Write candidates to DB
        for chunk_id, similarity, matched_query in hits:
            conn.execute(
                "INSERT OR REPLACE INTO candidates (chunk_id, similarity, matched_query) VALUES (?, ?, ?)",
                (chunk_id, similarity, matched_query),
            )
        conn.commit()

        # Filter already-classified
        classified_ids = set(
            r[0] for r in conn.execute("SELECT chunk_id FROM classified").fetchall()
        )
        unclassified_hits = [h for h in hits if h[0] not in classified_ids]

        # Load full row data for classification
        candidate_rows = []
        for chunk_id, similarity, matched_query in unclassified_hits:
            row = conn.execute(
                "SELECT id as chunk_id, paper, date, page, chunk_idx, text FROM chunks WHERE id=?",
                (chunk_id,),
            ).fetchone()
            candidate_rows.append({
                **dict(row),
                "similarity": similarity,
                "matched_query": matched_query,
            })

        # 3. Classify
        new_events = 0
        if candidate_rows:
            new_events = classify_candidates(conn, candidate_rows, or_client, workers=args.workers)

        total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

        elapsed = time.time() - pipeline_t0
        rate = (batch_end - start_batch * args.batch_size) / elapsed if elapsed > 0 else 0
        remaining = len(texts) - batch_end
        eta = remaining / rate if rate > 0 else 0

        print(f"  Batch {batch_num+1}/{total_batches}: "
              f"embed {embed_time:.1f}s | "
              f"{len(hits)} candidates → {new_events} events | "
              f"total {total_events} events | "
              f"ETA {eta:.0f}s")

    # Combine shards
    print("\nCombining shards...")
    all_shards = sorted(SHARDS_DIR.glob("batch_*.npy"))
    embeddings = np.concatenate([np.load(s) for s in all_shards])
    np.save(EMBEDDINGS_FILE, embeddings.astype(np.float16))

    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    print(f"\nPipeline complete: {total_events} protest events from {len(chunks)} chunks")
    print(f"Total time: {time.time()-pipeline_t0:.0f}s")

    # Generate report
    from report import generate_html, load_events
    events_df = load_events(conn)
    if not events_df.empty:
        html = generate_html(events_df)
        report_file = DATA_DIR / "events.html"
        report_file.write_text(html)
        print(f"Report saved to {report_file}")

    conn.close()


if __name__ == "__main__":
    main()
