# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Protest event extraction pipeline that identifies and catalogs protest actions from African American newspapers (1905-1929). Uses a four-stage pipeline: embedding, semantic search, LLM classification, and HTML report generation.

## Running the Pipeline

```bash
# Full integrated pipeline (resumes from last checkpoint)
uv run pipeline.py --threshold 0.50

# Individual stages
uv run embed.py --max-files 100       # Stage 1: embed OCR pages (resumable via shards)
uv run search.py --threshold 0.50     # Stage 2: semantic search against seed queries
uv run search.py --explore            # Interactive threshold exploration mode
uv run classify.py --workers 10       # Stage 3: classify candidates with Qwen3 via OpenRouter (resumable)
uv run report.py                      # Stage 4: generate interactive HTML report

# Utility
uv run eval_threshold.py              # Evaluate similarity threshold bands
```

All dependencies managed with `uv` (see pyproject.toml). No test suite exists.

## Architecture

**Four-stage pipeline, each stage reads/writes a shared SQLite database (`data/protest_events.db`):**

1. **embed.py** → Extracts text from OCR JSONs, creates page-level chunks with 50% paragraph overlap, embeds locally via `nomic-ai/nomic-embed-text-v1.5`. Writes chunks to `chunks` table. Embeddings stored as `data/shards/*.npy` → `data/embeddings.npz`
2. **search.py** → Cosine similarity search using 79 period-authentic seed queries (defined in `config.py`). Writes hits to `candidates` table
3. **classify.py** → Parallel classification via Qwen3-235b through OpenRouter (OpenAI-compatible API). Writes to `events` table, tracks progress in `classified` table
4. **report.py** → Reads `events` + `chunks` tables, generates sortable/filterable HTML report with links to dangerouspress.org viewer

**Supporting modules:**
- **db.py** — Schema definition, connection helper, and `init_db()`. Tables: `chunks`, `candidates`, `events`, `classified`
- **pipeline.py** — Orchestrates all stages sequentially with resume support
- **config.py** — Central configuration: paths, model names, seed queries, thresholds
- **embed_local.py** — Simpler standalone embedding without shard-based resume

## Data Storage

- **SQLite** (`data/protest_events.db`): All structured data — chunks, candidates, events, classification progress
- **Embeddings** (`data/embeddings.npy`): Float16 numpy array, memory-mappable. Embedding row order matches `chunks` table `ORDER BY id`
- **Shards** (`data/shards/`): Per-batch `.npy` files for resume support during embedding

## Key Design Decisions

- **Nomic embeddings**: Uses `nomic-ai/nomic-embed-text-v1.5` with task prefixes (`search_document:` for chunks, `search_query:` for queries). Chosen for transformers.js compatibility (browser-side search)
- **Resumability**: Embedding resumes via shard files; classification resumes via `classified` table
- **Token-aware chunking**: Uses chonkie TokenChunker (512 tokens, 64 overlap) for adaptive chunk counts per page
- **Seed queries** in config.py use period-authentic language across 17+ event-type categories
- **Similarity threshold** of 0.65 was empirically chosen via eval_threshold.py analysis
- **Qwen3 classifier**: Chosen over Haiku for ~5x cost savings at comparable quality. Handles `<think>` tags in responses

## API Dependencies

- **OpenRouter API**: Used for classification (Qwen3-235b). Requires `OPENROUTER_API_KEY`
- Embeddings are local via sentence-transformers (nomic-embed-text-v1.5), no API key needed
