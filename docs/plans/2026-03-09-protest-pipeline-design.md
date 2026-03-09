# Protest Event Pipeline Design

## Goal

Extract protest events (marches, demonstrations, petitions, mass meetings, etc.) from OCR'd African American newspapers (1905-1929) and produce a browsable dataset linking back to source pages.

## Architecture

Four-stage pipeline. Each stage saves output so downstream steps can re-run independently.

```
Stage 1: Embed        Stage 2: Search         Stage 3: Classify
OCR JSONs ──→ embeddings.npz ──→ candidates.csv ──→ events.csv ──→ events.html
              + metadata.csv      (similarity        (Haiku confirms,
              (region text,        filter)            extracts fields)
               paper, date,
               page, idx)
```

## Stages

### Stage 1: Embed (`embed.py`)
- Read ~10K OCR JSONs from local copy
- Extract every region's text + metadata (paper, date, page, region_idx, label)
- Embed with `sentence-transformers` using `bge-small-en-v1.5` (local, free)
- Output: `data/embeddings.npz` + `data/metadata.csv`
- Run once, reuse across experiments

### Stage 2: Search (`search.py`)
- Iterative exploration phase
- Start with broad seed queries, examine hits, discover period-specific language
- Cosine similarity against all region embeddings
- Configurable threshold
- Output: `data/candidates.csv`
- Fast to re-run with different queries/thresholds

### Stage 3: Classify (`classify.py`)
- Send candidates to Claude Haiku with structured prompt
- Extract: event_type, date_mentioned, location, participants, description
- Filter false positives
- Output: `data/events.csv`

### Stage 4: Report (`report.py`)
- Generate `data/events.html` from events.csv
- Each event links to `dangerouspress.org/?paper=X&date=Y&page=Z`
- Sortable/browsable view

## Data Source

- ~10K front page OCR JSONs (from Longleaf zip)
- Each JSON has regions with bbox, label, text, status
- Located at `/tmp/longleaf-ocr-results/`

## Tech Stack

- Python, managed with `uv`
- `sentence-transformers` (local embeddings)
- `anthropic` SDK (Haiku classification)
- `pandas` (data wrangling)
- `numpy` (embeddings storage)

## Project Location

- Repo: `nealcaren/protest-events`
- All data files in `data/` (gitignored)
