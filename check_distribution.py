"""Quick check: similarity distribution with current seed queries."""

import numpy as np
from config import EMBEDDINGS_FILE, EMBEDDING_MODEL, SEED_QUERIES
from embed import load_model

print(f"Loading embeddings from {EMBEDDINGS_FILE}...")
embeddings = np.load(EMBEDDINGS_FILE, mmap_mode="r").astype(np.float32)
print(f"Loaded {len(embeddings)} chunks")

print(f"Loading model {EMBEDDING_MODEL}...")
model = load_model()

print(f"Embedding {len(SEED_QUERIES)} seed queries...")
prefixed = ["search_query: " + q for q in SEED_QUERIES]
q_embs = model.encode(prefixed, normalize_embeddings=True)

# Compute similarities
emb_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
q_norm = q_embs / np.linalg.norm(q_embs, axis=1, keepdims=True)
sims = q_norm @ emb_norm.T
max_sims = sims.max(axis=0)

# Distribution
print(f"\n{'Threshold':<12} {'Count':>8} {'Cumulative':>12} {'% of total':>10}")
print("-" * 45)
total = len(max_sims)
for thresh in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.63, 0.65, 0.67, 0.70, 0.75, 0.80]:
    above = (max_sims >= thresh).sum()
    print(f">= {thresh:.2f}     {above:>8,}     {above:>8,}     {above/total:>8.1%}")

print(f"\nTotal chunks: {total:,}")
print(f"Mean similarity: {max_sims.mean():.3f}")
print(f"Median similarity: {np.median(max_sims):.3f}")
print(f"Std: {max_sims.std():.3f}")

# Band counts
print(f"\n{'Band':<15} {'Count':>8}")
print("-" * 25)
bands = [(0.50, 0.55), (0.55, 0.60), (0.60, 0.63), (0.63, 0.65),
         (0.65, 0.67), (0.67, 0.70), (0.70, 0.75), (0.75, 1.0)]
for low, high in bands:
    count = ((max_sims >= low) & (max_sims < high)).sum()
    print(f"[{low:.2f}-{high:.2f})   {count:>8,}")
