"""Evaluate similarity thresholds by sampling candidates and asking Claude to judge relevance."""

import json
import time
import argparse

import numpy as np
import pandas as pd
import openai
import anthropic

from config import (
    EMBEDDINGS_FILE, METADATA_FILE, EMBEDDING_MODEL,
    SEED_QUERIES, HAIKU_MODEL, DATA_DIR,
)

EVAL_PROMPT = """You are evaluating whether newspaper text passages are relevant candidates
for protest event extraction. Rate each passage on whether it MIGHT describe or mention
a protest action (march, rally, boycott, petition, strike, demonstration, mass meeting,
delegation, or similar collective political action).

Rate each passage: YES (clearly about protest/collective action), MAYBE (mentions related
topics but unclear), or NO (unrelated).

Passages:
{passages}

Respond with a JSON array of objects: [{{"id": 0, "rating": "YES/MAYBE/NO"}}]
Respond ONLY with the JSON array."""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=20,
                        help="Samples per threshold band")
    args = parser.parse_args()

    print("Loading embeddings and metadata...")
    embeddings = np.load(EMBEDDINGS_FILE)["embeddings"]
    meta = pd.read_csv(METADATA_FILE)
    print(f"Loaded {len(meta)} chunks")

    oai = openai.OpenAI()
    ant = anthropic.Anthropic()

    # Embed queries
    resp = oai.embeddings.create(input=SEED_QUERIES, model=EMBEDDING_MODEL)
    q_embs = np.array([d.embedding for d in resp.data], dtype=np.float32)

    # Compute similarities
    emb_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    q_norm = q_embs / np.linalg.norm(q_embs, axis=1, keepdims=True)
    sims = q_norm @ emb_norm.T
    max_sims = sims.max(axis=0)

    # Evaluate threshold bands
    bands = [
        (0.30, 0.35),
        (0.35, 0.40),
        (0.40, 0.45),
        (0.45, 0.50),
        (0.50, 0.55),
        (0.55, 0.60),
    ]

    print(f"\nEvaluating {len(bands)} threshold bands with {args.samples} samples each\n")

    results = []
    for low, high in bands:
        mask = (max_sims >= low) & (max_sims < high)
        indices = np.where(mask)[0]
        count = len(indices)

        if count == 0:
            print(f"  [{low:.2f}-{high:.2f}] No candidates")
            continue

        # Sample
        n = min(args.samples, count)
        sample_idx = np.random.choice(indices, n, replace=False)

        passages = ""
        for j, idx in enumerate(sample_idx):
            text = str(meta.iloc[idx]["text"])[:300].replace("\n", " ")
            passages += f"\n[{j}] {text}\n"

        # Ask Claude to evaluate
        try:
            resp = ant.messages.create(
                model=HAIKU_MODEL,
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": EVAL_PROMPT.format(passages=passages),
                }],
            )
            content = resp.content[0].text.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            ratings = json.loads(content)

            yes = sum(1 for r in ratings if r.get("rating") == "YES")
            maybe = sum(1 for r in ratings if r.get("rating") == "MAYBE")
            no = sum(1 for r in ratings if r.get("rating") == "NO")

            print(f"  [{low:.2f}-{high:.2f}] {count:,} candidates | "
                  f"sample {n}: YES={yes} MAYBE={maybe} NO={no} | "
                  f"precision={(yes+maybe)/n:.0%}")

            results.append({
                "low": low, "high": high, "total": count,
                "yes": yes, "maybe": maybe, "no": no,
                "precision": (yes + maybe) / n,
            })
        except Exception as e:
            print(f"  [{low:.2f}-{high:.2f}] Error: {e}")

    # Recommendation
    print("\n" + "=" * 60)
    if results:
        # Find lowest threshold where precision >= 50%
        for r in results:
            if r["precision"] >= 0.5:
                print(f"RECOMMENDED THRESHOLD: {r['low']:.2f}")
                print(f"  {r['total']:,} candidates, ~{r['precision']:.0%} relevant")
                print(f"  (lowest band with ≥50% precision)")
                break
        else:
            best = max(results, key=lambda r: r["precision"])
            print(f"RECOMMENDED THRESHOLD: {best['low']:.2f}")
            print(f"  Best precision found: {best['precision']:.0%}")


if __name__ == "__main__":
    main()
