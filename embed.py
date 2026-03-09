"""Stage 1: Extract text from OCR JSONs and create embeddings via OpenAI API."""

import json
import csv
import time
import random
import argparse
from pathlib import Path

import numpy as np
import openai

from config import OCR_DIR, DATA_DIR, EMBEDDINGS_FILE, METADATA_FILE, EMBEDDING_MODEL

SHARDS_DIR = DATA_DIR / "shards"


def extract_regions(ocr_dir: Path, max_files: int = 0) -> list[dict]:
    """Extract all text regions from OCR JSONs with metadata."""
    regions = []
    json_files = sorted(ocr_dir.rglob("*.json"))
    print(f"Found {len(json_files)} JSON files")

    if max_files > 0 and max_files < len(json_files):
        random.shuffle(json_files)
        json_files = json_files[:max_files]
        print(f"Sampling {max_files} files")

    for jf in json_files:
        try:
            data = json.loads(jf.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        # Parse path: paper/year/date/page_XX.json
        # or: ocr-results/paper/year/date/page_XX.json (Longleaf)
        rel = jf.relative_to(ocr_dir)
        parts = rel.parts
        if len(parts) < 4:
            continue
        if parts[0] == "ocr-results":
            parts = parts[1:]
        if len(parts) < 4:
            continue
        paper = parts[0]
        date = parts[2]
        page = jf.stem
        page_num = int(page.split("_")[1]) if "_" in page else 1

        for i, region in enumerate(data.get("regions", [])):
            text = region.get("text", "").strip()
            if not text or len(text) < 20:
                continue
            if region.get("status") != "ok":
                continue

            regions.append({
                "paper": paper,
                "date": date,
                "page": page_num,
                "region_idx": i,
                "label": region.get("label", "text"),
                "text": text,
            })

    return regions


def embed_batch(client: openai.OpenAI, texts: list[str], model: str) -> np.ndarray:
    """Embed a batch of texts via OpenAI API."""
    resp = client.embeddings.create(input=texts, model=model)
    return np.array([d.embedding for d in resp.data], dtype=np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-files", type=int, default=0,
                        help="Max JSON files to process (0 = all)")
    parser.add_argument("--batch-size", type=int, default=2000,
                        help="Texts per API call (max ~8K for OpenAI)")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SHARDS_DIR.mkdir(parents=True, exist_ok=True)

    # Extract
    print("Extracting regions from OCR JSONs...")
    t0 = time.time()
    regions = extract_regions(OCR_DIR, max_files=args.max_files)
    print(f"Extracted {len(regions)} regions in {time.time()-t0:.1f}s")

    if not regions:
        print("No regions found. Check OCR_DIR in config.py")
        return

    # Save metadata
    print(f"Saving metadata to {METADATA_FILE}...")
    with open(METADATA_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["paper", "date", "page", "region_idx", "label", "text"])
        writer.writeheader()
        writer.writerows(regions)

    # Check existing shards for resume
    existing_shards = sorted(SHARDS_DIR.glob("batch_*.npy"))
    start_batch = len(existing_shards)
    start_idx = start_batch * args.batch_size

    if start_idx >= len(regions):
        print(f"All {len(regions)} regions already embedded in {len(existing_shards)} shards.")
    else:
        if start_batch > 0:
            print(f"Resuming from batch {start_batch} ({start_idx} regions already done)")

        # Embed remaining via OpenAI
        texts = [r["text"][:8000] for r in regions]
        client = openai.OpenAI()
        total_batches = (len(texts) + args.batch_size - 1) // args.batch_size

        print(f"Embedding {len(texts) - start_idx} remaining regions with {EMBEDDING_MODEL}...")
        t0 = time.time()

        for batch_num in range(start_batch, total_batches):
            i = batch_num * args.batch_size
            batch = texts[i:i + args.batch_size]
            embs = embed_batch(client, batch, EMBEDDING_MODEL)

            shard_path = SHARDS_DIR / f"batch_{batch_num:04d}.npy"
            np.save(shard_path, embs)

            done = min(i + args.batch_size, len(texts))
            elapsed = time.time() - t0
            processed = done - start_idx
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(texts) - done) / rate if rate > 0 else 0
            print(f"  [{done}/{len(texts)}] {rate:.0f}/s | ETA {eta:.0f}s")

        print(f"Embedding done in {time.time()-t0:.1f}s")

    # Combine shards into final file
    print("Combining shards...")
    all_shards = sorted(SHARDS_DIR.glob("batch_*.npy"))
    embeddings = np.concatenate([np.load(s) for s in all_shards])
    np.savez_compressed(EMBEDDINGS_FILE, embeddings=embeddings)
    print(f"Saved embeddings to {EMBEDDINGS_FILE} ({EMBEDDINGS_FILE.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"Total: {len(embeddings)} embeddings, {len(all_shards)} shards")
    print("Done.")


if __name__ == "__main__":
    main()
