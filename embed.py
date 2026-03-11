"""Stage 1: Extract text from OCR JSONs, chunk by page, and create embeddings."""

import json
import time
import random
import argparse
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from chonkie import TokenChunker

from config import OCR_DIR, DATA_DIR, EMBEDDINGS_FILE, EMBEDDING_MODEL
from db import get_connection, init_db

SHARDS_DIR = DATA_DIR / "shards"

# Chunking config — sized for nomic-embed-text-v1.5 (2048 token context)
CHUNK_SIZE = 512       # tokens per chunk
CHUNK_OVERLAP = 64     # token overlap between consecutive chunks


def get_chunker() -> TokenChunker:
    """Create a token chunker sized for the embedding model."""
    return TokenChunker(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


def extract_page_texts(ocr_dir: Path, max_files: int = 0) -> list[dict]:
    """Extract text from OCR JSONs, concatenate by page in reading order,
    then split into token-aware chunks via chonkie."""
    json_files = sorted(ocr_dir.rglob("*.json"))
    print(f"Found {len(json_files)} JSON files")

    if max_files > 0 and max_files < len(json_files):
        random.shuffle(json_files)
        json_files = json_files[:max_files]
        print(f"Sampling {max_files} files")

    chunker = get_chunker()
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

        # Token-aware chunking via chonkie
        page_chunks = chunker.chunk(full_text)

        for i, chunk in enumerate(page_chunks):
            if len(chunk.text.strip()) < 20:
                continue
            chunks.append({
                "paper": paper,
                "date": date,
                "page": page_num,
                "chunk_idx": i,
                "n_chunks": len(page_chunks),
                "text": chunk.text,
            })

    return chunks


def load_model(model_name: str = EMBEDDING_MODEL) -> SentenceTransformer:
    """Load the embedding model."""
    return SentenceTransformer(model_name, trust_remote_code=True)


def embed_texts(model: SentenceTransformer, texts: list[str], prefix: str = "search_document: ",
                batch_size: int = 32) -> np.ndarray:
    """Embed texts using sentence-transformers with task prefix."""
    prefixed = [prefix + t for t in texts]
    return model.encode(prefixed, show_progress_bar=True, batch_size=batch_size,
                        normalize_embeddings=True)


def save_chunks_to_db(conn, chunks: list[dict]) -> list[int]:
    """Insert chunks into the database, returning their row IDs in order.
    Skips duplicates via INSERT OR IGNORE."""
    cursor = conn.cursor()
    ids = []
    for c in chunks:
        cursor.execute(
            """INSERT OR IGNORE INTO chunks (paper, date, page, chunk_idx, n_chunks, text)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (c["paper"], c["date"], c["page"], c["chunk_idx"], c["n_chunks"], c["text"]),
        )
        # Fetch the id whether we just inserted or it already existed
        cursor.execute(
            "SELECT id FROM chunks WHERE paper=? AND date=? AND page=? AND chunk_idx=?",
            (c["paper"], c["date"], c["page"], c["chunk_idx"]),
        )
        ids.append(cursor.fetchone()[0])
    conn.commit()
    return ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-files", type=int, default=0,
                        help="Max JSON files to process (0 = all)")
    parser.add_argument("--batch-size", type=int, default=1000,
                        help="Chunks per embedding batch")
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

    # Save chunks to database
    conn = get_connection()
    init_db(conn)
    print("Saving chunks to database...")
    chunk_ids = save_chunks_to_db(conn, chunks)
    print(f"Database has {conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]} chunks")
    conn.close()

    # Check existing shards for resume
    existing_shards = sorted(SHARDS_DIR.glob("batch_*.npy"))
    start_batch = len(existing_shards)
    start_idx = start_batch * args.batch_size

    if start_idx >= len(chunks):
        print(f"All {len(chunks)} chunks already embedded in {len(existing_shards)} shards.")
    else:
        if start_batch > 0:
            print(f"Resuming from batch {start_batch} ({start_idx} chunks already done)")

        texts = [c["text"] for c in chunks]
        total_batches = (len(texts) + args.batch_size - 1) // args.batch_size

        print(f"Loading model {EMBEDDING_MODEL}...")
        model = load_model()

        print(f"Embedding {len(texts) - start_idx} remaining chunks...")
        t0 = time.time()

        for batch_num in range(start_batch, total_batches):
            i = batch_num * args.batch_size
            batch = texts[i:i + args.batch_size]
            embs = embed_texts(model, batch)

            shard_path = SHARDS_DIR / f"batch_{batch_num:04d}.npy"
            np.save(shard_path, embs)

            done = min(i + args.batch_size, len(texts))
            elapsed = time.time() - t0
            processed = done - start_idx
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(texts) - done) / rate if rate > 0 else 0
            print(f"  [{done}/{len(texts)}] {rate:.0f}/s | ETA {eta:.0f}s")

        print(f"Embedding done in {time.time()-t0:.1f}s")

    # Combine shards into final file (float16 for compact storage)
    print("Combining shards...")
    all_shards = sorted(SHARDS_DIR.glob("batch_*.npy"))
    embeddings = np.concatenate([np.load(s) for s in all_shards])
    np.save(EMBEDDINGS_FILE, embeddings.astype(np.float16))
    print(f"Saved embeddings to {EMBEDDINGS_FILE} ({EMBEDDINGS_FILE.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"Total: {len(embeddings)} embeddings, {len(all_shards)} shards")
    print("Done.")


if __name__ == "__main__":
    main()
