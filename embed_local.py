"""Stage 1 (standalone): Extract text from OCR JSONs and create embeddings without sharding."""

import time
import argparse

import numpy as np

from config import OCR_DIR, DATA_DIR, EMBEDDINGS_FILE, EMBEDDING_MODEL
from db import get_connection, init_db
from embed import extract_page_texts, load_model, embed_texts, save_chunks_to_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-files", type=int, default=0,
                        help="Max JSON files to process (0 = all)")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Extract
    print("Extracting page chunks from OCR JSONs...")
    t0 = time.time()
    chunks = extract_page_texts(OCR_DIR, max_files=args.max_files)
    print(f"Extracted {len(chunks)} chunks in {time.time()-t0:.1f}s")

    if not chunks:
        print("No chunks found. Check OCR_DIR in config.py")
        return

    # Save to database
    conn = get_connection()
    init_db(conn)
    print("Saving chunks to database...")
    save_chunks_to_db(conn, chunks)
    print(f"Database has {conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]} chunks")
    conn.close()

    # Embed
    texts = [c["text"] for c in chunks]
    print(f"Loading embedding model: {EMBEDDING_MODEL}...")
    model = load_model()

    print(f"Embedding {len(texts)} chunks...")
    t0 = time.time()
    embeddings = embed_texts(model, texts)
    print(f"Embedded in {time.time()-t0:.1f}s")

    # Save
    np.savez_compressed(EMBEDDINGS_FILE, embeddings=embeddings)
    print(f"Saved embeddings to {EMBEDDINGS_FILE} ({EMBEDDINGS_FILE.stat().st_size / 1024 / 1024:.1f} MB)")
    print("Done.")


if __name__ == "__main__":
    main()
