"""Run the full pipeline: embed → search → classify, processing in batches.

Embeds new batches via OpenAI, then immediately searches and classifies
each batch's candidates before moving to the next embedding batch.
"""

import json
import csv
import time
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import openai
import anthropic

from config import (
    OCR_DIR, DATA_DIR, EMBEDDINGS_FILE, METADATA_FILE, CANDIDATES_FILE,
    EVENTS_FILE, EMBEDDING_MODEL, SEED_QUERIES, SIMILARITY_THRESHOLD,
    HAIKU_MODEL,
)
from embed import extract_regions
from classify import SYSTEM_PROMPT, USER_TEMPLATE

SHARDS_DIR = DATA_DIR / "shards"


def embed_batch_openai(client: openai.OpenAI, texts: list[str], model: str) -> np.ndarray:
    resp = client.embeddings.create(input=texts, model=model)
    return np.array([d.embedding for d in resp.data], dtype=np.float32)


def embed_queries(client: openai.OpenAI, queries: list[str], model: str) -> np.ndarray:
    resp = client.embeddings.create(input=queries, model=model)
    return np.array([d.embedding for d in resp.data], dtype=np.float32)


def search_batch(query_embs: np.ndarray, batch_embs: np.ndarray,
                 queries: list[str], threshold: float,
                 batch_meta: pd.DataFrame) -> pd.DataFrame:
    """Search a batch of embeddings against queries."""
    emb_norm = batch_embs / np.linalg.norm(batch_embs, axis=1, keepdims=True)
    q_norm = query_embs / np.linalg.norm(query_embs, axis=1, keepdims=True)

    sims = q_norm @ emb_norm.T
    max_sims = sims.max(axis=0)
    best_query_idx = sims.argmax(axis=0)

    mask = max_sims >= threshold
    if not mask.any():
        return pd.DataFrame()

    hit_indices = np.where(mask)[0]
    candidates = batch_meta.iloc[hit_indices].copy()
    candidates["similarity"] = max_sims[hit_indices]
    candidates["matched_query"] = [queries[best_query_idx[i]] for i in hit_indices]
    return candidates


def classify_one(client: anthropic.Anthropic, row: dict) -> tuple[dict, dict | None]:
    """Classify a single candidate using Haiku."""
    text = str(row["text"])[:2000]
    try:
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": USER_TEMPLATE.format(
                    paper=row["paper"], date=row["date"], text=text
                ),
            }],
        )
        content = resp.content[0].text.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return row, json.loads(content)
    except (json.JSONDecodeError, IndexError, anthropic.APIError):
        return row, None


def classify_candidates(candidates: pd.DataFrame, anthropic_client: anthropic.Anthropic,
                        workers: int = 10) -> list[dict]:
    """Classify candidates in parallel, return protest events."""
    events = []
    rows = [row.to_dict() for _, row in candidates.iterrows()]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(classify_one, anthropic_client, r): r for r in rows}
        for future in as_completed(futures):
            row, result = future.result()
            if result and result.get("is_protest"):
                events.append({
                    "paper": row["paper"],
                    "date": row["date"],
                    "page": row["page"],
                    "region_idx": row["region_idx"],
                    "similarity": round(row["similarity"], 3),
                    "matched_query": row["matched_query"],
                    "event_type": result.get("event_type"),
                    "description": result.get("description"),
                    "location": result.get("location"),
                    "participants": result.get("participants"),
                    "date_mentioned": result.get("date_mentioned"),
                    "source_text": str(row["text"])[:500],
                })
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--threshold", type=float, default=SIMILARITY_THRESHOLD)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SHARDS_DIR.mkdir(parents=True, exist_ok=True)

    # Extract regions
    print("Extracting regions...")
    t0 = time.time()
    regions = extract_regions(OCR_DIR, max_files=args.max_files)
    print(f"Extracted {len(regions)} regions in {time.time()-t0:.1f}s")

    if not regions:
        print("No regions found.")
        return

    # Save metadata
    with open(METADATA_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["paper", "date", "page", "region_idx", "label", "text"])
        writer.writeheader()
        writer.writerows(regions)

    meta = pd.DataFrame(regions)
    texts = [r["text"][:8000] for r in regions]
    total_batches = (len(texts) + args.batch_size - 1) // args.batch_size

    # Check existing shards
    existing_shards = sorted(SHARDS_DIR.glob("batch_*.npy"))
    start_batch = len(existing_shards)

    # Load existing events
    all_events = []
    processed_file = DATA_DIR / "classified_keys.txt"
    processed_keys = set()
    if EVENTS_FILE.exists():
        all_events = pd.read_csv(EVENTS_FILE).to_dict("records")
        print(f"Loaded {len(all_events)} existing events")
    if processed_file.exists():
        processed_keys = set(processed_file.read_text().splitlines())

    # Clients
    oai_client = openai.OpenAI()
    ant_client = anthropic.Anthropic()

    # Embed queries once
    print("Embedding queries...")
    query_embs = embed_queries(oai_client, SEED_QUERIES, EMBEDDING_MODEL)

    if start_batch > 0:
        print(f"Resuming from batch {start_batch}/{total_batches} ({start_batch * args.batch_size} regions embedded)")

    pipeline_t0 = time.time()

    for batch_num in range(start_batch, total_batches):
        i = batch_num * args.batch_size
        batch_texts = texts[i:i + args.batch_size]
        batch_meta = meta.iloc[i:i + args.batch_size].reset_index(drop=True)
        batch_end = min(i + args.batch_size, len(texts))

        # 1. Embed
        t0 = time.time()
        batch_embs = embed_batch_openai(oai_client, batch_texts, EMBEDDING_MODEL)
        np.save(SHARDS_DIR / f"batch_{batch_num:04d}.npy", batch_embs)
        embed_time = time.time() - t0

        # 2. Search
        candidates = search_batch(query_embs, batch_embs, SEED_QUERIES, args.threshold, batch_meta)

        # Filter already-classified
        if not candidates.empty and processed_keys:
            candidates = candidates[candidates.apply(
                lambda r: f"{r['paper']}|{r['date']}|{r['page']}|{r['region_idx']}" not in processed_keys, axis=1
            )]

        # 3. Classify
        new_events = []
        if not candidates.empty:
            new_events = classify_candidates(candidates, ant_client, workers=args.workers)
            all_events.extend(new_events)

            # Track processed
            for _, r in candidates.iterrows():
                processed_keys.add(f"{r['paper']}|{r['date']}|{r['page']}|{r['region_idx']}")

        # Save checkpoint
        if all_events:
            pd.DataFrame(all_events).to_csv(EVENTS_FILE, index=False)
        processed_file.write_text("\n".join(processed_keys))

        elapsed = time.time() - pipeline_t0
        rate = (batch_end - start_batch * args.batch_size) / elapsed if elapsed > 0 else 0
        remaining = len(texts) - batch_end
        eta = remaining / rate if rate > 0 else 0

        print(f"  Batch {batch_num+1}/{total_batches}: "
              f"embed {embed_time:.1f}s | "
              f"{len(candidates)} candidates → {len(new_events)} events | "
              f"total {len(all_events)} events | "
              f"ETA {eta:.0f}s")

    # Combine shards
    print("\nCombining shards...")
    all_shards = sorted(SHARDS_DIR.glob("batch_*.npy"))
    embeddings = np.concatenate([np.load(s) for s in all_shards])
    np.savez_compressed(EMBEDDINGS_FILE, embeddings=embeddings)

    # Save final candidates
    print(f"\nPipeline complete: {len(all_events)} protest events from {len(regions)} regions")
    print(f"Total time: {time.time()-pipeline_t0:.0f}s")
    print(f"Events saved to {EVENTS_FILE}")

    # Generate report
    from report import generate_html
    if all_events:
        events_df = pd.read_csv(EVENTS_FILE)
        html = generate_html(events_df)
        report_file = DATA_DIR / "events.html"
        report_file.write_text(html)
        print(f"Report saved to {report_file}")


if __name__ == "__main__":
    main()
