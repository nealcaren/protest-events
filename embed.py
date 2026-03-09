"""Stage 1: Extract text from OCR JSONs, chunk by page, and create embeddings via OpenAI API."""

import json
import csv
import time
import random
import argparse
from pathlib import Path
from collections import defaultdict

import numpy as np
import openai

from config import OCR_DIR, DATA_DIR, EMBEDDINGS_FILE, METADATA_FILE, EMBEDDING_MODEL

SHARDS_DIR = DATA_DIR / "shards"

# Chunking config
TARGET_CHUNKS_PER_PAGE = 8
OVERLAP_FRACTION = 0.5  # 50% overlap between consecutive chunks


def extract_page_texts(ocr_dir: Path, max_files: int = 0) -> list[dict]:
    """Extract text from OCR JSONs, concatenate by page in reading order,
    then split into overlapping chunks."""
    json_files = sorted(ocr_dir.rglob("*.json"))
    print(f"Found {len(json_files)} JSON files")

    if max_files > 0 and max_files < len(json_files):
        random.shuffle(json_files)
        json_files = json_files[:max_files]
        print(f"Sampling {max_files} files")

    chunks = []

    for jf in json_files:
        try:
            data = json.loads(jf.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        # Parse path
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

        # Collect all text regions in order (already in reading order from OCR pipeline)
        region_texts = []
        for region in data.get("regions", []):
            text = region.get("text", "").strip()
            if not text:
                continue
            if region.get("status") != "ok":
                continue
            region_texts.append(text)

        if not region_texts:
            continue

        # Concatenate all regions into full page text
        full_text = "\n\n".join(region_texts)

        # Split into overlapping chunks
        page_chunks = make_chunks(full_text, TARGET_CHUNKS_PER_PAGE, OVERLAP_FRACTION)

        for i, chunk_text in enumerate(page_chunks):
            if len(chunk_text.strip()) < 20:
                continue
            chunks.append({
                "paper": paper,
                "date": date,
                "page": page_num,
                "chunk_idx": i,
                "n_chunks": len(page_chunks),
                "text": chunk_text,
            })

    return chunks


def make_chunks(text: str, target_chunks: int, overlap: float) -> list[str]:
    """Split text into approximately target_chunks overlapping chunks.

    Uses paragraph boundaries where possible for cleaner splits.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    if len(paragraphs) <= 1:
        # Too short to chunk meaningfully
        return [text]

    # If fewer paragraphs than target chunks, each paragraph is a chunk
    # with overlap by including neighbor paragraphs
    if len(paragraphs) <= target_chunks:
        chunks = []
        for i in range(len(paragraphs)):
            # Include previous paragraph for context (overlap)
            start = max(0, i - 1)
            chunk = "\n\n".join(paragraphs[start:i + 1])
            chunks.append(chunk)
        return chunks

    # More paragraphs than target chunks: group paragraphs into windows
    step = max(1, len(paragraphs) // target_chunks)
    window = max(step, int(step / (1 - overlap))) if overlap < 1 else step

    chunks = []
    i = 0
    while i < len(paragraphs):
        end = min(i + window, len(paragraphs))
        chunk = "\n\n".join(paragraphs[i:end])
        chunks.append(chunk)
        i += step
        if end == len(paragraphs):
            break

    return chunks


MAX_TOKENS_PER_REQUEST = 250_000  # stay under OpenAI's 300K limit


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def embed_texts(client: openai.OpenAI, texts: list[str], model: str) -> np.ndarray:
    """Embed texts, automatically splitting into sub-batches to stay under token limits."""
    all_embeddings = []
    batch = []
    batch_tokens = 0

    for text in texts:
        t = estimate_tokens(text)
        if batch and batch_tokens + t > MAX_TOKENS_PER_REQUEST:
            resp = client.embeddings.create(input=batch, model=model)
            all_embeddings.extend([d.embedding for d in resp.data])
            batch = []
            batch_tokens = 0
        batch.append(text)
        batch_tokens += t

    if batch:
        resp = client.embeddings.create(input=batch, model=model)
        all_embeddings.extend([d.embedding for d in resp.data])

    return np.array(all_embeddings, dtype=np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-files", type=int, default=0,
                        help="Max JSON files to process (0 = all)")
    parser.add_argument("--batch-size", type=int, default=1000,
                        help="Texts per API call")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SHARDS_DIR.mkdir(parents=True, exist_ok=True)

    # Extract and chunk
    print("Extracting and chunking page texts...")
    t0 = time.time()
    chunks = extract_page_texts(OCR_DIR, max_files=args.max_files)
    print(f"Created {len(chunks)} chunks from {args.max_files or 'all'} files in {time.time()-t0:.1f}s")

    if not chunks:
        print("No chunks created. Check OCR_DIR in config.py")
        return

    # Save metadata
    print(f"Saving metadata to {METADATA_FILE}...")
    with open(METADATA_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["paper", "date", "page", "chunk_idx", "n_chunks", "text"])
        writer.writeheader()
        writer.writerows(chunks)

    # Check existing shards for resume
    existing_shards = sorted(SHARDS_DIR.glob("batch_*.npy"))
    start_batch = len(existing_shards)
    start_idx = start_batch * args.batch_size

    if start_idx >= len(chunks):
        print(f"All {len(chunks)} chunks already embedded in {len(existing_shards)} shards.")
    else:
        if start_batch > 0:
            print(f"Resuming from batch {start_batch} ({start_idx} chunks already done)")

        texts = [c["text"][:8000] for c in chunks]
        client = openai.OpenAI()
        total_batches = (len(texts) + args.batch_size - 1) // args.batch_size

        print(f"Embedding {len(texts) - start_idx} remaining chunks with {EMBEDDING_MODEL}...")
        t0 = time.time()

        for batch_num in range(start_batch, total_batches):
            i = batch_num * args.batch_size
            batch = texts[i:i + args.batch_size]
            embs = embed_texts(client, batch, EMBEDDING_MODEL)

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
