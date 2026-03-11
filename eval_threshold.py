"""Evaluate similarity thresholds by sampling candidates and asking Qwen3 to judge relevance."""

import json
import os
import re
import time
import argparse

import numpy as np
import pandas as pd
from openai import OpenAI

from config import (
    EMBEDDINGS_FILE, EMBEDDING_MODEL,
    SEED_QUERIES, CLASSIFIER_MODEL, OPENROUTER_BASE_URL, DATA_DIR,
)
from db import get_connection, init_db
from embed import load_model

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


def parse_json_array(content: str) -> list | None:
    """Extract JSON array from response that might have thinking tags or fences."""
    content = content.strip()
    if "<think>" in content:
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if content.startswith("```"):
        lines = content.split("\n")
        inner = []
        started = False
        for line in lines:
            if line.startswith("```") and not started:
                started = True
                continue
            elif line.startswith("```") and started:
                break
            elif started:
                inner.append(line)
        content = "\n".join(inner)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=20,
                        help="Samples per threshold band")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY environment variable")
        return

    print("Loading embeddings and metadata...")
    embeddings = np.load(EMBEDDINGS_FILE, mmap_mode="r").astype(np.float32)
    conn = get_connection()
    init_db(conn)
    rows = conn.execute("SELECT id, paper, date, page, chunk_idx, text FROM chunks ORDER BY id").fetchall()
    meta = pd.DataFrame(rows, columns=["id", "paper", "date", "page", "chunk_idx", "text"])
    conn.close()
    print(f"Loaded {len(meta)} chunks")

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)

    # Embed queries
    print(f"Loading model {EMBEDDING_MODEL}...")
    model = load_model()
    prefixed = ["search_query: " + q for q in SEED_QUERIES]
    q_embs = model.encode(prefixed, normalize_embeddings=True)

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

        try:
            resp = client.chat.completions.create(
                model=CLASSIFIER_MODEL,
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": EVAL_PROMPT.format(passages=passages),
                }],
            )
            content = resp.choices[0].message.content.strip()
            ratings = parse_json_array(content)

            if ratings is None:
                print(f"  [{low:.2f}-{high:.2f}] Parse error")
                continue

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
