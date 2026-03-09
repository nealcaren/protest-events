"""Stage 2: Semantic search for protest-related text regions."""

import time
import argparse

import numpy as np
import pandas as pd
import openai

from config import (
    EMBEDDINGS_FILE, METADATA_FILE, CANDIDATES_FILE, EMBEDDING_MODEL,
    SEED_QUERIES, SIMILARITY_THRESHOLD, MAX_CANDIDATES_PER_QUERY, DATA_DIR,
)


def embed_queries(client: openai.OpenAI, queries: list[str], model: str) -> np.ndarray:
    """Embed queries via OpenAI API."""
    resp = client.embeddings.create(input=queries, model=model)
    return np.array([d.embedding for d in resp.data], dtype=np.float32)


def search(queries: list[str], embeddings: np.ndarray, client: openai.OpenAI,
           model: str) -> tuple[np.ndarray, np.ndarray]:
    """Return max similarity and best query index for each region."""
    query_embeddings = embed_queries(client, queries, model)

    # Normalize for cosine similarity
    emb_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    q_norm = query_embeddings / np.linalg.norm(query_embeddings, axis=1, keepdims=True)

    # Similarity: (n_queries, n_regions)
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

    # Load
    print("Loading embeddings and metadata...")
    embeddings = np.load(EMBEDDINGS_FILE)["embeddings"]
    meta = pd.read_csv(METADATA_FILE)
    print(f"Loaded {len(meta)} regions")

    client = openai.OpenAI()

    queries = list(SEED_QUERIES)
    if args.query:
        queries.append(args.query)

    print(f"Searching with {len(queries)} queries, threshold={args.threshold}...")
    t0 = time.time()
    max_sims, best_query_idx = search(queries, embeddings, client, EMBEDDING_MODEL)
    print(f"Search completed in {time.time()-t0:.1f}s")

    if args.explore:
        emb_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
        q_embs = embed_queries(client, queries, EMBEDDING_MODEL)
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

    # Build candidates dataframe
    candidates = meta.iloc[hit_indices].copy()
    candidates["similarity"] = max_sims[hit_indices]
    candidates["matched_query"] = [queries[best_query_idx[i]] for i in hit_indices]
    candidates = candidates.sort_values("similarity", ascending=False)

    # Save
    candidates.to_csv(CANDIDATES_FILE, index=False)
    print(f"Saved to {CANDIDATES_FILE}")

    # Summary
    print(f"\nTop 20 candidates:")
    for _, row in candidates.head(20).iterrows():
        text_preview = str(row["text"])[:100].replace("\n", " ")
        print(f"  [{row['similarity']:.3f}] {row['paper']} {row['date']} p{row['page']}")
        print(f"    query: \"{row['matched_query']}\"")
        print(f"    {text_preview}")
        print()


if __name__ == "__main__":
    main()
