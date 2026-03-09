# Extracting Protest Events from African American Newspapers, 1905–1929

## Overview

This project extracts mentions of protest actions from OCR'd African American newspapers using a three-stage computational pipeline: semantic embedding, similarity search, and LLM classification. The source corpus consists of 10,092 front pages from 30 newspapers, processed through a separate OCR pipeline (PaddleX layout detection + GLM-OCR text recognition) and stored as structured JSON files.

The current run identified **594 protest events** across the full corpus.

## Pipeline

### Stage 1: Text Extraction and Embedding

Each OCR JSON contains detected text regions in newspaper reading order. Rather than embedding individual regions (which are often single paragraphs or headlines lacking context), we concatenate all regions on a page into a single text and split into approximately 8 overlapping chunks per page. The overlap (50%, using paragraph boundaries) ensures that events spanning multiple regions are captured in at least one chunk.

This produces **79,992 chunks** from 10,092 pages.

Each chunk is embedded using OpenAI's `text-embedding-3-small` model ($0.02/1M tokens, total corpus cost ~$2). Embeddings are saved as shards (one `.npy` file per API batch) for resumability — if interrupted, the pipeline picks up from the last completed shard.

### Stage 2: Semantic Search

We search the embedded chunks using 25 seed queries and retain all chunks with cosine similarity ≥ 0.50 to any query. This produces **2,077 candidates** (2.6% of chunks).

#### Query Development

Initial seed queries used modern phrasing ("protest march through the streets", "boycott of stores") and performed poorly against the chunked text — top similarity scores were only 0.40–0.46.

To improve, we:

1. Sampled 100 chunks from the top 3,000 candidates
2. Sent them to Claude Haiku for binary coding (protest: YES/NO) with key phrase extraction
3. Used the key phrases from YES passages to generate new queries that mirror the actual vocabulary and syntax of the period

For example, instead of "petition signed by citizens," the revised query reads: "committee of graduates written condemning jim crow policy and demanding segregation be discontinued." This pushed top similarity scores to 0.55–0.67 and improved candidate quality.

The 25 final queries cover: collective action and mobilization, anti-lynching campaigns, delegations and petitions, NAACP organizational activity, labor and economic actions, legislative protest, marches and parades, and race riots.

### Stage 3: LLM Classification

Each candidate chunk is sent to Claude Haiku (`claude-haiku-4-5-20251001`) with a structured prompt asking whether the text describes a protest action. The model returns a JSON object with:

- `is_protest`: boolean
- `event_type`: march, rally, mass_meeting, petition, boycott, strike, delegation, demonstration, parade, or other
- `description`: one-sentence summary
- `location`, `participants`, `date_mentioned`: extracted metadata

Classification runs with 10 parallel API workers at ~8.6 candidates/second. The full run (2,077 candidates) completes in about 4 minutes and costs approximately $0.60.

**29% of candidates** (594/2,077) are classified as protest events.

### Stage 4: Report Generation

Results are rendered as a filterable HTML table with sortable columns (date, type, source) and expandable source text. Each event links to the original newspaper page on [dangerouspress.org](https://dangerouspress.org). The report is deployed via GitHub Pages.

## Results Summary

| Metric | Value |
|--------|-------|
| Source pages | 10,092 |
| Newspapers | 30 |
| Date range | 1905–1929 |
| Text chunks | 79,992 |
| Candidates (≥0.50 similarity) | 2,077 |
| Classified protest events | 594 |
| Candidate precision | 29% |

### Events by Type

| Type | Count |
|------|-------|
| Mass meeting | 175 |
| Delegation | 168 |
| Petition | 110 |
| Demonstration | 49 |
| Other | 36 |
| Parade | 16 |
| Strike | 12 |
| Boycott | 12 |

### Top Newspapers by Event Count

| Newspaper | Events |
|-----------|--------|
| Colorado Statesman | 82 |
| Omaha Monitor | 66 |
| Broad Ax | 56 |
| Baltimore Afro-American | 48 |
| New York Age | 43 |
| Dallas Express | 43 |
| Denver Star | 35 |
| St. Louis Argus | 29 |

## Known Limitations

1. **"Protest as rhetoric" vs. "protest as action."** The classifier codes strongly worded letters, proclamations, resolutions, and editorial denunciations as protests. These are distinct from collective public actions (marches, meetings, strikes). A future refinement should distinguish between rhetorical protest and protest events involving physical gatherings or organized collective action.

2. **Front pages only.** The current corpus is limited to page 1 of each issue. Protest coverage often continued on interior pages, and some events were reported only on interior pages.

3. **OCR quality.** The underlying OCR is imperfect, particularly for older issues with degraded print quality. Some events may be missed due to garbled text, and extracted descriptions may contain OCR errors.

4. **Threshold sensitivity.** The 0.50 similarity threshold was chosen to produce a manageable candidate set (~2,000). Lowering to 0.48 would yield ~4,200 candidates and likely capture additional events at the cost of more false positives and higher classification expense.

5. **Duplicate events.** The same event may appear in multiple newspapers or across overlapping chunks from the same page. No deduplication is currently performed.

## Cost

| Component | Cost |
|-----------|------|
| OpenAI embeddings (80K chunks) | ~$2.00 |
| Claude Haiku classification (2,077 calls) | ~$0.60 |
| **Total** | **~$2.60** |

## Reproducing

```bash
# Requires: OPENAI_API_KEY and ANTHROPIC_API_KEY environment variables
# OCR JSONs expected at path configured in config.py

# Full pipeline (embed + search + classify + report)
uv run embed.py                    # ~15 min, resumable
uv run search.py --threshold 0.50  # ~5 sec
uv run classify.py --workers 10    # ~4 min, resumable
uv run report.py                   # instant

# Or use the integrated pipeline script
uv run pipeline.py --threshold 0.50

# Explore queries interactively
uv run search.py --explore --top-n 5

# Evaluate threshold bands
uv run eval_threshold.py
```
