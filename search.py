"""Stage 2: Semantic search for protest-related text regions."""

import time
import argparse

import numpy as np
import pandas as pd

from config import (
    EMBEDDINGS_FILE, EMBEDDING_MODEL,
    SEED_QUERIES, SIMILARITY_THRESHOLD, DATA_DIR,
)
from db import get_connection, init_db
from embed import load_model


def embed_queries(model, queries: list[str]) -> np.ndarray:
    """Embed queries using the local model with query prefix."""
    prefixed = ["search_query: " + q for q in queries]
    return model.encode(prefixed, normalize_embeddings=True)


def search(queries: list[str], embeddings: np.ndarray,
           model) -> tuple[np.ndarray, np.ndarray]:
    """Return max similarity and best query index for each chunk."""
    query_embeddings = embed_queries(model, queries)

    emb_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    q_norm = query_embeddings / np.linalg.norm(query_embeddings, axis=1, keepdims=True)

    sims = q_norm @ emb_norm.T

    max_sims = sims.max(axis=0)
    best_query_idx = sims.argmax(axis=0)

    return max_sims, best_query_idx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD)
    parser.add_argument("--query", type=str, help="Add a single custom query")
    parser.add_argument("--explore", action="store_true",
                        help="Show top hits per query for exploration")
    parser.add_argument("--top-n", type=int, default=10,
                        help="Number of top hits to show in explore mode")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Load embeddings and chunk metadata from DB
    print("Loading embeddings and metadata...")
    embeddings = np.load(EMBEDDINGS_FILE, mmap_mode="r").astype(np.float32)

    conn = get_connection()
    init_db(conn)
    rows = conn.execute("SELECT id, paper, date, page, chunk_idx, text FROM chunks ORDER BY id").fetchall()
    conn.close()
    meta = pd.DataFrame(rows, columns=["id", "paper", "date", "page", "chunk_idx", "text"])
    print(f"Loaded {len(meta)} chunks")

    print(f"Loading model {EMBEDDING_MODEL}...")
    model = load_model()

    queries = list(SEED_QUERIES)
    if args.query:
        queries.append(args.query)

    print(f"Searching with {len(queries)} queries, threshold={args.threshold}...")
    t0 = time.time()
    max_sims, best_query_idx = search(queries, embeddings, model)
    print(f"Search completed in {time.time()-t0:.1f}s")

    if args.explore:
        emb_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        q_embs = embed_queries(model, queries)
        q_norm = q_embs / np.linalg.norm(q_embs, axis=1, keepdims=True)

        for qi, q in enumerate(queries):
            sims = (q_norm[qi:qi+1] @ emb_norm.T)[0]
            top_idx = np.argsort(sims)[-args.top_n:][::-1]

            print(f"\n{'='*80}")
            print(f"QUERY: \"{q}\"")
            print(f"{'='*80}")
            for rank, idx in enumerate(top_idx, 1):
                row = meta.iloc[idx]
                text_preview = str(row["text"])[:150].replace("\n", " ")
                print(f"  {rank}. [{sims[idx]:.3f}] {row['paper']} {row['date']} p{row['page']}")
                print(f"     {text_preview}")
                print()
        return

    # Filter above threshold
    mask = max_sims >= args.threshold
    hit_indices = np.where(mask)[0]

    print(f"Found {len(hit_indices)} candidates above threshold {args.threshold}")

    # Write candidates to database
    conn = get_connection()
    conn.execute("DELETE FROM candidates")  # fresh search results
    for idx in hit_indices:
        chunk_id = int(meta.iloc[idx]["id"])
        conn.execute(
            "INSERT OR REPLACE INTO candidates (chunk_id, similarity, matched_query) VALUES (?, ?, ?)",
            (chunk_id, float(max_sims[idx]), queries[best_query_idx[idx]]),
        )
    conn.commit()
    print(f"Saved {len(hit_indices)} candidates to database")

    # Summary
    candidates = meta.iloc[hit_indices].copy()
    candidates["similarity"] = max_sims[hit_indices]
    candidates["matched_query"] = [queries[best_query_idx[i]] for i in hit_indices]
    candidates = candidates.sort_values("similarity", ascending=False)

    print(f"\nTop 20 candidates:")
    for _, row in candidates.head(20).iterrows():
        text_preview = str(row["text"])[:100].replace("\n", " ")
        print(f"  [{row['similarity']:.3f}] {row['paper']} {row['date']} p{row['page']}")
        print(f"    query: \"{row['matched_query']}\"")
        print(f"    {text_preview}")
        print()

    conn.close()


if __name__ == "__main__":
    main()
