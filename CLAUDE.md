# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Protest event extraction pipeline that identifies and catalogs protest actions from African American newspapers (1905-1929). Uses a seven-stage pipeline: embedding, semantic search, LLM classification, structured extraction, deduplication, campaign clustering, and HTML report generation. Follows the Oliver et al. relational framework for protest event data.

## Running the Pipeline

```bash
# Full integrated pipeline (resumes from last checkpoint)
uv run pipeline.py --threshold 0.70

# Individual stages
uv run embed.py --max-files 100       # Stage 1: embed OCR pages (resumable via shards)
uv run search.py --threshold 0.70     # Stage 2: semantic search against seed queries
uv run search.py --explore            # Interactive threshold exploration mode
uv run classify.py --workers 10       # Stage 3: classify candidates with Qwen3 via OpenRouter (resumable)
uv run extract.py --workers 10        # Stage 4: structured extraction on confirmed events (resumable)
uv run dedup.py                       # Stage 5: deduplicate events (find pairs → adjudicate → group)
uv run dedup.py --find-pairs          #   Step 5a only: find candidate pairs
uv run dedup.py --adjudicate          #   Step 5b only: LLM adjudication
uv run dedup.py --build-groups        #   Step 5c only: build dedup groups
uv run cluster.py                     # Stage 6: campaign clustering
uv run cluster.py --named-only        #   Only named campaign consolidation
uv run report.py                      # Stage 7: generate interactive HTML report

# Utility
uv run eval_threshold.py              # Evaluate similarity threshold bands
```

All dependencies managed with `uv` (see pyproject.toml). No test suite exists.

## Architecture

**Seven-stage pipeline, each stage reads/writes a shared SQLite database (`data/protest_events.db`):**

1. **embed.py** → Extracts text from OCR JSONs, creates page-level chunks with token-aware chunking, embeds locally via `nomic-ai/nomic-embed-text-v1.5`. Writes chunks to `chunks` table. Embeddings stored as `data/shards/*.npy` → `data/embeddings.npy`
2. **search.py** → Cosine similarity search using 79 period-authentic seed queries (defined in `config.py`). Writes hits to `candidates` table
3. **classify.py** → Parallel classification via Qwen3-235b through OpenRouter (OpenAI-compatible API). Groups adjacent chunks before classifying. Writes to `events` and `event_sources` tables, tracks progress in `classified` table
4. **extract.py** → Rich structured extraction on confirmed events: issue categories (15-category taxonomy), organizations, individuals, targets, size estimates, tactics, campaign names, actor type. Writes to `event_details` table, tracks progress in `extracted` table
5. **dedup.py** → Deduplication via embedding similarity + LLM adjudication + union-find grouping. Writes to `dedup_pairs` and `dedup_groups` tables. Merges `event_sources` for canonical events
6. **cluster.py** → Campaign clustering: named campaigns consolidated via LLM normalization, then algorithmic clustering by issue + location + time window. Writes to `campaigns` and `event_campaigns` tables
7. **report.py** → Reads all tables, generates sortable/filterable HTML report with issue categories, multi-source links, campaign badges, and links to dangerouspress.org viewer

**Supporting modules:**
- **db.py** — Schema definition, connection helper, and `init_db()`. Tables: `chunks`, `candidates`, `events`, `classified`, `event_sources`, `event_details`, `extracted`, `dedup_pairs`, `dedup_groups`, `campaigns`, `event_campaigns`
- **pipeline.py** — Orchestrates all stages sequentially with resume support
- **config.py** — Central configuration: paths, model names, seed queries, thresholds, paper locations, issue taxonomy

## Data Storage

- **SQLite** (`data/protest_events.db`): All structured data — chunks, candidates, events, extraction details, dedup groups, campaigns
- **Embeddings** (`data/embeddings.npy`): Float16 numpy array, memory-mappable. Embedding row order matches `chunks` table `ORDER BY id`
- **Shards** (`data/shards/`): Per-batch `.npy` files for resume support during embedding

## Issue Taxonomy (15 categories)

`anti_lynching`, `segregation_public`, `education`, `voting_rights`, `labor`, `criminal_justice`, `military`, `government_discrimination`, `housing`, `healthcare`, `cultural_media`, `civil_rights_organizing`, `pan_african`, `womens_organizing`, `migration`

## Key Design Decisions

- **Nomic embeddings**: Uses `nomic-ai/nomic-embed-text-v1.5` with task prefixes (`search_document:` for chunks, `search_query:` for queries). Chosen for transformers.js compatibility (browser-side search)
- **Resumability**: Embedding resumes via shard files; classification via `classified` table; extraction via `extracted` table
- **Token-aware chunking**: Uses chonkie TokenChunker (512 tokens, 64 overlap) for adaptive chunk counts per page
- **Seed queries** in config.py use period-authentic language across 17+ event-type categories
- **Similarity threshold** of 0.70 balances recall (11% candidate rate) against precision
- **Qwen3 classifier**: Chosen over Haiku for ~5x cost savings at comparable quality. Handles `<think>` tags in responses
- **Relational data model**: Events link to multiple source chunks via `event_sources` (many-to-many). Dedup merges sources from duplicate events into canonical events. Follows Oliver et al. framework.
- **Actor race inference**: `actor_race_explicit` flag distinguishes explicit race identification from contextual inference (important for Black newspapers writing for Black audiences)
- **Publication location context**: Paper locations provided to extraction prompt but LLM instructed not to default event location to publication city
- **Campaign clustering**: Named campaigns (from LLM extraction) take priority; algorithmic clustering (issue + location + time window) fills gaps but never overrides

## API Dependencies

- **OpenRouter API**: Used for classification, extraction, deduplication, and campaign normalization (Qwen3-235b). Requires `OPENROUTER_API_KEY`
- Embeddings are local via sentence-transformers (nomic-embed-text-v1.5), no API key needed
