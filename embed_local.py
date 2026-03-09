"""Stage 1: Extract text from OCR JSONs and create embeddings."""

import json
import csv
import time
import random
import argparse
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from config import OCR_DIR, DATA_DIR, EMBEDDINGS_FILE, METADATA_FILE, EMBEDDING_MODEL


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
        # Skip leading "ocr-results" directory if present
        if parts[0] == "ocr-results":
            parts = parts[1:]
        if len(parts) < 4:
            continue
        paper = parts[0]
        date = parts[2]
        page = jf.stem  # e.g. "page_01"
        page_num = int(page.split("_")[1]) if "_" in page else 1

        for i, region in enumerate(data.get("regions", [])):
            text = region.get("text", "").strip()
            if not text or len(text) < 20:  # skip tiny fragments
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-files", type=int, default=0,
                        help="Max JSON files to process (0 = all)")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

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

    # Embed
    texts = [r["text"] for r in regions]
    print(f"Loading embedding model: {EMBEDDING_MODEL}...")
    model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")

    print(f"Embedding {len(texts)} regions...")
    t0 = time.time()
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=256, normalize_embeddings=True)
    print(f"Embedded in {time.time()-t0:.1f}s")

    # Save
    np.savez_compressed(EMBEDDINGS_FILE, embeddings=embeddings)
    print(f"Saved embeddings to {EMBEDDINGS_FILE} ({EMBEDDINGS_FILE.stat().st_size / 1024 / 1024:.1f} MB)")
    print("Done.")


if __name__ == "__main__":
    main()
