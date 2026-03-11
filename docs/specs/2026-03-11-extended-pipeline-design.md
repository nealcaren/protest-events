# Extended Protest Event Pipeline Design

## Overview

Extend the current four-stage pipeline (embed → search → classify → report) with three new stages: structured extraction, deduplication, and campaign clustering. The goal is to produce a relational protest event dataset following the Oliver et al. framework, adapted for African American newspapers 1905-1929.

Design assumes new data will arrive incrementally (~10K more papers coming) and all stages must be resumable.

## Pipeline Stages

```
embed → search → classify → EXTRACT → DEDUPLICATE → CLUSTER → report
                 (existing)   (new)      (new)        (new)   (enhanced)
```

All stages read/write the shared SQLite database (`data/protest_events.db`). Each is independently runnable and resumable.

## Stage 4: Extract (`extract.py`)

Runs a rich structured extraction prompt on confirmed protest events (where `events.is_protest = true`). Writes to a new `event_details` table.

### Prompt Design

Input: the event's source text, paper name, publication city, and date. The publication city provides context but the prompt must explicitly instruct the LLM: "Do NOT assume the event took place in the publication city. Many articles report on events from around the country. Only assign a location if the text explicitly states where the event occurred. If unclear, set location fields to null."

Output JSON:

```json
{
  "issue_primary": "anti_lynching",
  "issue_secondary": "government_discrimination" or null,
  "organizations": ["NAACP", "Anti-Lynching Crusaders"],
  "individuals": ["Ida B. Wells", "Walter White"],
  "target": "Congress" or null,
  "size_min": null,
  "size_max": null,
  "size_text": "thousands" or null,
  "tactics": ["mass_meeting", "petition"],
  "campaign_name": "Dyer Anti-Lynching Bill" or null,
  "actor_type": "black_protest",
  "actor_race_explicit": false,
  "location_city": "Washington",
  "location_state": "DC"
}
```

### Issue Taxonomy (15 categories)

| Code | Label | Description |
|------|-------|-------------|
| `anti_lynching` | Anti-lynching / anti-mob violence | Campaigns against lynching, mob violence, race massacres |
| `segregation_public` | Segregation & public accommodations | Jim Crow transit, parks, theaters, restaurants, public facilities |
| `education` | Education equity | Segregated schools, Black teachers/principals, school funding |
| `voting_rights` | Voting rights & political representation | Disenfranchisement, white primaries, political appointments |
| `labor` | Labor & economic rights | Strikes, unions, wage disputes, workplace discrimination, peonage |
| `criminal_justice` | Criminal justice & policing | Police brutality, prisoner advocacy, clemency, wrongful prosecution |
| `military` | Military & veterans' rights | Black officers, soldier mistreatment, court-martial clemency |
| `government_discrimination` | Government discrimination | Segregation in federal/state agencies, discriminatory officials |
| `housing` | Housing & residential segregation | Ordinances, restrictive covenants, home defense, tenant rights |
| `healthcare` | Healthcare discrimination | Hospital staffing, segregated medical facilities |
| `cultural_media` | Cultural & media protest | Opposition to racist films, newspapers, speeches, symbols |
| `civil_rights_organizing` | Civil rights organizing | NAACP/NERL/Niagara conferences, broad campaigns, org founding |
| `pan_african` | Pan-African & international solidarity | UNIA, Pan-African Congress, international racial solidarity |
| `womens_organizing` | Women's rights & organizing | Suffrage, women's clubs, gender-specific racial claims |
| `migration` | Migration as collective action | Great Migration framed as protest against Southern conditions |

### Actor Type (cross-cutting flag)

- `black_protest` — Black people protesting for rights
- `anti_black` — White counter-protest, KKK actions, events opposing Black advancement
- `mixed` — Coalition events, ambiguous actor composition

### Actor Race Inference

- `actor_race_explicit`: `true` / `false` — whether the text explicitly identifies the race of the actors
- Important because these are Black newspapers writing for a Black audience. Authors often do not state that participants are Black — the audience would know. Similarly, white actors may not be labeled as white. The LLM should flag whether race identification is stated in the text or inferred from context (publication, topic, audience). This supports transparency about what is in the source vs. what is interpreted.

### Tactics (multiple allowed)

`march`, `rally`, `mass_meeting`, `petition`, `boycott`, `strike`, `delegation`, `demonstration`, `parade`, `legal_action`, `riot`, `self_defense`, `verbal_statement`, `organizational_founding`, `voter_mobilization`, `other`

### Size Estimation

- `size_min` / `size_max`: integer estimates when text provides numbers
- `size_text`: the raw descriptor from the text ("thousands," "a crowd," "packed the hall," "twelve men")
- All three can be null if no size information is present

### Database Schema Addition

```sql
CREATE TABLE IF NOT EXISTS event_details (
    event_id INTEGER PRIMARY KEY REFERENCES events(id),
    issue_primary TEXT,
    issue_secondary TEXT,
    organizations TEXT,  -- JSON array
    individuals TEXT,    -- JSON array
    target TEXT,
    size_min INTEGER,
    size_max INTEGER,
    size_text TEXT,
    tactics TEXT,        -- JSON array
    campaign_name TEXT,
    actor_type TEXT,
    actor_race_explicit INTEGER,  -- 0/1: whether race is explicitly stated in text
    location_city TEXT,
    location_state TEXT
);

-- Track which events have been through extraction
CREATE TABLE IF NOT EXISTS extracted (
    event_id INTEGER PRIMARY KEY REFERENCES events(id)
);
```

### Newspaper Publication Locations

A lookup dict in `config.py` maps paper slugs to publication cities, provided as context to the extraction prompt:

```python
PAPER_LOCATIONS = {
    "amsterdam-news": "New York, NY",
    "athens-republique": "Athens, GA",
    "baltimore-afro-american": "Baltimore, MD",
    "broad-ax": "Chicago, IL",
    "chicago-defender": "Chicago, IL",
    "chicago-whip": "Chicago, IL",
    "cleveland-gazette": "Cleveland, OH",
    "colorado-statesman": "Denver, CO",
    "dallas-express": "Dallas, TX",
    "denver-star": "Denver, CO",
    "houston-informer": "Houston, TX",
    "indianapolis-freeman": "Indianapolis, IN",
    "iowa-bystander": "Des Moines, IA",
    "kansas-city-advocate": "Kansas City, MO",
    "kansas-city-sun": "Kansas City, MO",
    "metropolis-weekly-gazette": "Metropolis, IL",
    "montana-plaindealer": "Helena, MT",
    "muskogee-cimeter": "Muskogee, OK",
    "nashville-globe": "Nashville, TN",
    "negro-world": "New York, NY",
    "new-york-age": "New York, NY",
    "omaha-monitor": "Omaha, NE",
    "phoenix-tribune": "Phoenix, AZ",
    "pittsburgh-courier": "Pittsburgh, PA",
    "portland-new-age": "Portland, OR",
    "raleigh-independent": "Raleigh, NC",
    "richmond-planet": "Richmond, VA",
    "springfield-forum": "Springfield, IL",
    "st-louis-argus": "St. Louis, MO",
    "st-paul-appeal": "St. Paul, MN",
    "tulsa-star": "Tulsa, OK",
    "twin-city-star": "Minneapolis, MN",
    "washington-bee": "Washington, DC",
    "washington-tribune": "Washington, DC",
    "western-outlook": "Oakland, CA",
    "wichita-searchlight": "Wichita, KS",
    "wisconsin-weekly-blade": "Milwaukee, WI",
}
```

### Resumability

Track extracted events via the `extracted` table (same pattern as `classified`). On re-run, skip events already in `extracted`.

### Execution

```bash
uv run extract.py                    # Extract all unprocessed events
uv run extract.py --limit 100       # Test on first 100
uv run extract.py --workers 10      # Parallel API calls
uv run extract.py --dry-run         # Preview without API calls
```

## Stage 5: Deduplicate (`dedup.py`)

Identifies when multiple event records describe the same real-world event. Uses embedding similarity to find candidate pairs, then LLM adjudication to confirm.

### Step 5a: Find Candidate Pairs

Embed event descriptions (using the same nomic model). For each event, find other events within a similarity + constraint window:

- Cosine similarity of descriptions >= 0.80
- Date within 30 days of each other (events can be previewed/recapped weeks apart)
- OR same `campaign_name` (non-null) — always compare these

This produces candidate pairs for adjudication.

### Step 5b: LLM Adjudication

For each candidate pair, send both events' details to the LLM:

```
Event A: [date, paper, location, description, source_text excerpt]
Event B: [date, paper, location, description, source_text excerpt]

Are these the same real-world event? Respond with JSON:
{
  "same_event": true/false,
  "confidence": "high" / "medium" / "low",
  "reasoning": "brief explanation"
}
```

### Step 5c: Build Dedup Groups

Merge confirmed pairs into groups using union-find. Each group gets a canonical event (the one with richest detail or earliest date). Others are marked as duplicates pointing to the canonical.

### Database Schema Addition

```sql
-- Candidate pairs for dedup review
CREATE TABLE IF NOT EXISTS dedup_pairs (
    id INTEGER PRIMARY KEY,
    event_id_a INTEGER REFERENCES events(id),
    event_id_b INTEGER REFERENCES events(id),
    similarity REAL,
    same_event INTEGER,  -- null=unreviewed, 1=same, 0=different
    confidence TEXT,
    reasoning TEXT,
    UNIQUE(event_id_a, event_id_b)
);

-- Dedup groups: maps each event to its canonical event
CREATE TABLE IF NOT EXISTS dedup_groups (
    event_id INTEGER PRIMARY KEY REFERENCES events(id),
    canonical_event_id INTEGER REFERENCES events(id)
);
```

### Execution

```bash
uv run dedup.py                      # Full dedup pipeline
uv run dedup.py --find-pairs         # Only step 5a: find candidate pairs
uv run dedup.py --adjudicate         # Only step 5b: LLM adjudication
uv run dedup.py --build-groups       # Only step 5c: union-find grouping
uv run dedup.py --threshold 0.85     # Tighter similarity threshold
```

## Stage 6: Cluster (`cluster.py`)

Groups deduplicated events into campaigns/episodes. Two mechanisms, with named campaigns taking priority.

### Step 6a: Named Campaign Consolidation

Group events sharing the same non-null `campaign_name` (after normalization — e.g., "Dyer Bill" and "Dyer Anti-Lynching Bill" should merge). Use fuzzy string matching or a short LLM call to normalize campaign names.

### Step 6b: Algorithmic Clustering

For events without a named campaign, cluster by:
- Same `issue_primary`
- Same or nearby `location_city` / `location_state`
- Within a 90-day time window

Use agglomerative clustering on a combined distance metric (issue match + location match + temporal distance). Minimum cluster size: 3 events.

Named campaigns are never overridden or merged by algorithmic clustering.

### Database Schema Addition

```sql
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY,
    name TEXT,              -- named campaign or auto-generated label
    named INTEGER DEFAULT 0, -- 1 if from campaign_name field, 0 if algorithmic
    issue_primary TEXT,
    description TEXT,       -- auto-generated summary
    event_count INTEGER,
    date_start TEXT,
    date_end TEXT
);

CREATE TABLE IF NOT EXISTS event_campaigns (
    event_id INTEGER REFERENCES events(id),
    campaign_id INTEGER REFERENCES campaigns(id),
    PRIMARY KEY (event_id, campaign_id)
);
```

### Execution

```bash
uv run cluster.py                    # Full clustering
uv run cluster.py --named-only      # Only named campaign consolidation
uv run cluster.py --min-cluster 3   # Minimum events for algorithmic clusters
uv run cluster.py --window 90       # Time window in days
```

## Enhanced Report (`report.py`)

Update the HTML report to surface the new data:

- **Event detail columns**: issue category, organizations, individuals, actor type, campaign
- **Filters**: by issue category, by actor type, by campaign, by organization
- **Dedup indicators**: show duplicate count, link to canonical event
- **Campaign view**: group events by campaign, show timeline
- **Summary statistics**: event counts by issue, by year, by paper, by campaign

## Source Linking

Every event must link back to every article/page that covers it — not just the primary chunk. This enables a report where you can see all coverage of an event and click through to the specific page on dangerouspress.org.

### Event-Source Junction Table

```sql
CREATE TABLE IF NOT EXISTS event_sources (
    event_id INTEGER REFERENCES events(id),
    chunk_id INTEGER REFERENCES chunks(id),
    role TEXT DEFAULT 'primary',  -- 'primary' or 'duplicate'
    PRIMARY KEY (event_id, chunk_id)
);
```

Sources accumulate through the pipeline:

1. **Classify stage**: when an event is created from a merged chunk group, all chunk_ids in the group are inserted as `role='primary'`.
2. **Dedup stage**: when events A and B are confirmed as the same event, event B's sources are copied to event A's `event_sources` with `role='duplicate'`. The canonical event now has sources from every article that covered it.

### URL Construction

Each source link is built from the chunks table metadata:

```
{SITE_BASE_URL}/?paper={paper}&date={date}&page={page}
```

Future enhancement: add `#chunk-{chunk_idx}` anchor to jump directly to the relevant text region on the page. This requires the website to support fragment-based scrolling, but we store `chunk_idx` now so the capability is ready.

### Report Display

In the enhanced report, each event shows a "Sources" section listing every article that covered it:

```
Sources (3):
  Chicago Defender, 1922-01-14, p. 1  [link]
  New York Age, 1922-01-21, p. 2      [link]
  Baltimore Afro-American, 1922-01-28, p. 4  [link]
```

This replaces the current single "Source" column.

## New Data Flow

```
chunks table (existing)
  ↓ search
candidates table (existing)
  ↓ classify
events table (existing) + classified table (existing) + event_sources table (new)
  ↓ extract
event_details table (new) + extracted table (new)
  ↓ deduplicate
dedup_pairs table (new) + dedup_groups table (new) → merges event_sources
  ↓ cluster
campaigns table (new) + event_campaigns table (new)
  ↓ report
events.html (enhanced, with multi-source links per event)
```

## Combined Single-Pass Prompt (for future pipeline runs)

For new data arriving in future batches, combine classification + extraction into one prompt to avoid redundant API calls. The prompt returns:

```json
{
  "is_protest": true,
  "event_type": "mass_meeting",
  "description": "...",
  "issue_primary": "anti_lynching",
  "issue_secondary": null,
  "organizations": ["NAACP"],
  "individuals": ["Walter White"],
  "target": "Congress",
  "size_text": "thousands",
  "tactics": ["mass_meeting", "petition"],
  "campaign_name": "Dyer Anti-Lynching Bill",
  "actor_type": "black_protest",
  "actor_race_explicit": false,
  "location_city": "Washington",
  "location_state": "DC",
  "date_mentioned": "June 14, 1922"
}
```

When `is_protest` is false, all other fields are null. This replaces both the classify and extract stages for new data. The `pipeline.py` orchestrator will use this combined prompt.

## Implementation Order

1. **Extract stage** — highest immediate value, enriches existing 10K events
2. **Dedup stage** — needed before meaningful analysis
3. **Cluster stage** — builds on dedup output
4. **Enhanced report** — surfaces everything
5. **Combined prompt** — optimization for future runs
6. **Pipeline integration** — wire into `pipeline.py`

## Cost Estimates (Qwen3 at $0.07/M input, $0.10/M output)

- **Extract**: 10,203 events × ~1K tokens input × ~200 tokens output ≈ $0.90
- **Dedup pairs**: depends on pair count; estimate 5-20K pairs × ~500 tokens ≈ $0.25-1.00
- **Campaign name normalization**: small, < $0.10
- **Combined prompt (future)**: marginal increase over current classify cost

Total for enriching existing data: ~$1-2.
