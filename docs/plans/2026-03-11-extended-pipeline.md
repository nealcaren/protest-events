# Extended Protest Event Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the pipeline with structured extraction, deduplication, and campaign clustering to produce a relational protest event dataset from 10K+ African American newspaper pages (1905-1929).

**Architecture:** Three new pipeline stages (extract → dedup → cluster) that each read/write the shared SQLite database, following the same resumable pattern as existing stages. Each stage is a standalone script runnable via `uv run`. A combined prompt replaces classify+extract for future data. The HTML report is enhanced to surface all new fields.

**Tech Stack:** Python, SQLite, OpenAI SDK (pointed at OpenRouter/Qwen3-235b), nomic-embed-text-v1.5 via sentence-transformers, numpy.

**Spec:** `docs/specs/2026-03-11-extended-pipeline-design.md`

**Note on testing:** This project has no test suite. Steps marked "test" mean running the script with `--limit` or `--dry-run` and inspecting output manually, or querying the database to verify results.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `config.py` | Modify | Add `PAPER_LOCATIONS` dict, `ISSUE_CATEGORIES` list |
| `db.py` | Modify | Add new tables: `event_details`, `extracted`, `event_sources`, `dedup_pairs`, `dedup_groups`, `campaigns`, `event_campaigns` |
| `extract.py` | Create | Stage 4: structured extraction on confirmed events |
| `dedup.py` | Create | Stage 5: find candidate pairs, LLM adjudicate, build groups |
| `cluster.py` | Create | Stage 6: named campaign consolidation + algorithmic clustering |
| `classify.py` | Modify | Populate `event_sources` table when creating events |
| `report.py` | Modify | Enhanced report with issue categories, sources, campaigns |
| `pipeline.py` | Modify | Wire in new stages, add combined prompt for future runs |

---

## Chunk 1: Schema and Config Foundation

### Task 1: Add paper locations and issue taxonomy to config.py

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add PAPER_LOCATIONS dict to config.py**

Add after `SITE_BASE_URL`:

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

ISSUE_CATEGORIES = [
    "anti_lynching",
    "segregation_public",
    "education",
    "voting_rights",
    "labor",
    "criminal_justice",
    "military",
    "government_discrimination",
    "housing",
    "healthcare",
    "cultural_media",
    "civil_rights_organizing",
    "pan_african",
    "womens_organizing",
    "migration",
]
```

- [ ] **Step 2: Verify config loads**

Run: `uv run python -c "from config import PAPER_LOCATIONS, ISSUE_CATEGORIES; print(len(PAPER_LOCATIONS), 'papers,', len(ISSUE_CATEGORIES), 'categories')"`

Expected: `37 papers, 15 categories`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "Add paper locations and issue taxonomy to config"
```

### Task 2: Extend database schema

**Files:**
- Modify: `db.py`

- [ ] **Step 1: Add new tables to init_db()**

Add to the `conn.executescript(...)` block in `init_db()`, after the existing table definitions:

```sql
CREATE TABLE IF NOT EXISTS event_sources (
    event_id INTEGER REFERENCES events(id),
    chunk_id INTEGER REFERENCES chunks(id),
    role TEXT DEFAULT 'primary',
    PRIMARY KEY (event_id, chunk_id)
);

CREATE TABLE IF NOT EXISTS event_details (
    event_id INTEGER PRIMARY KEY REFERENCES events(id),
    issue_primary TEXT,
    issue_secondary TEXT,
    organizations TEXT,
    individuals TEXT,
    target TEXT,
    size_min INTEGER,
    size_max INTEGER,
    size_text TEXT,
    tactics TEXT,
    campaign_name TEXT,
    actor_type TEXT,
    actor_race_explicit INTEGER,
    location_city TEXT,
    location_state TEXT
);

CREATE TABLE IF NOT EXISTS extracted (
    event_id INTEGER PRIMARY KEY REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS dedup_pairs (
    id INTEGER PRIMARY KEY,
    event_id_a INTEGER REFERENCES events(id),
    event_id_b INTEGER REFERENCES events(id),
    similarity REAL,
    same_event INTEGER,
    confidence TEXT,
    reasoning TEXT,
    UNIQUE(event_id_a, event_id_b)
);

CREATE TABLE IF NOT EXISTS dedup_groups (
    event_id INTEGER PRIMARY KEY REFERENCES events(id),
    canonical_event_id INTEGER REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY,
    name TEXT,
    named INTEGER DEFAULT 0,
    issue_primary TEXT,
    description TEXT,
    event_count INTEGER,
    date_start TEXT,
    date_end TEXT
);

CREATE TABLE IF NOT EXISTS event_campaigns (
    event_id INTEGER REFERENCES events(id),
    campaign_id INTEGER REFERENCES campaigns(id),
    PRIMARY KEY (event_id, campaign_id)
);

CREATE INDEX IF NOT EXISTS idx_event_sources_event ON event_sources(event_id);
CREATE INDEX IF NOT EXISTS idx_event_sources_chunk ON event_sources(chunk_id);
CREATE INDEX IF NOT EXISTS idx_dedup_groups_canonical ON dedup_groups(canonical_event_id);
CREATE INDEX IF NOT EXISTS idx_event_campaigns_campaign ON event_campaigns(campaign_id);
```

- [ ] **Step 2: Run init_db to verify tables create without error**

Run: `uv run python -c "from db import get_connection, init_db; conn = get_connection(); init_db(conn); print('OK'); conn.close()"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add db.py
git commit -m "Add schema for event_details, event_sources, dedup, and campaigns"
```

### Task 3: Backfill event_sources from existing events

The existing 10K events each have a single `chunk_id`. We need to populate `event_sources` with these links so the report can use the junction table consistently.

**Files:**
- No new files; database migration via one-off script

- [ ] **Step 1: Backfill event_sources from existing events**

Run:

```bash
uv run python -c "
from db import get_connection, init_db
conn = get_connection()
init_db(conn)
count = conn.execute('''
    INSERT OR IGNORE INTO event_sources (event_id, chunk_id, role)
    SELECT id, chunk_id, 'primary' FROM events
''').rowcount
conn.commit()
print(f'Backfilled {count} event_sources rows')
conn.close()
"
```

Expected: `Backfilled 10203 event_sources rows`

- [ ] **Step 2: Verify**

Run: `uv run python -c "from db import get_connection; c = get_connection(); print(c.execute('SELECT COUNT(*) FROM event_sources').fetchone()[0]); c.close()"`

Expected: `10203`

- [ ] **Step 3: Commit**

No code change to commit here — this is a data migration. The schema change in Task 2 covers it.

### Task 4: Update classify.py to populate event_sources

When classify creates a new event from a merged chunk group, it should insert all chunk_ids into `event_sources`, not just store the first one in `events.chunk_id`.

**Files:**
- Modify: `classify.py:236-249` (the block that inserts events)

- [ ] **Step 1: Add event_sources inserts after event creation**

In `classify.py`, in the main loop where events are inserted (around line 238-248), after the `INSERT INTO events` statement, add code to insert all chunk_ids into `event_sources`:

```python
            if result and result.get("is_protest"):
                primary_id = group["chunk_ids"][0]
                cursor = conn.execute(
                    """INSERT INTO events
                       (chunk_id, similarity, matched_query, event_type, description,
                        location, participants, date_mentioned, source_text)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (primary_id, round(group["similarity"], 3), group["matched_query"],
                     result.get("event_type"), result.get("description"),
                     result.get("location"), result.get("participants"),
                     result.get("date_mentioned"), str(group["text"])[:3000]),
                )
                event_id = cursor.lastrowid
                for cid in group["chunk_ids"]:
                    conn.execute(
                        "INSERT OR IGNORE INTO event_sources (event_id, chunk_id, role) VALUES (?, ?, 'primary')",
                        (event_id, cid),
                    )
                yes_count += 1
```

The key changes: capture `cursor` from the insert to get `lastrowid`, then loop over all chunk_ids to insert into `event_sources`.

Apply the same change in `pipeline.py:classify_candidates()` (around line 64-75) which has a parallel event insertion block.

- [ ] **Step 2: Verify the change compiles**

Run: `uv run python -c "import classify; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add classify.py pipeline.py
git commit -m "Populate event_sources junction table when creating events"
```

---

## Chunk 2: Extract Stage

### Task 5: Create extract.py

**Files:**
- Create: `extract.py`

- [ ] **Step 1: Write extract.py**

```python
"""Stage 4: Structured extraction on confirmed protest events.

Runs a rich extraction prompt on each event to pull issue categories,
organizations, individuals, targets, size, tactics, campaign names,
and actor type. Writes to the event_details table.
"""

import json
import os
import re
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from config import (
    CLASSIFIER_MODEL, OPENROUTER_BASE_URL, DATA_DIR,
    PAPER_LOCATIONS, ISSUE_CATEGORIES,
)
from db import get_connection, init_db


ISSUE_DESCRIPTIONS = {
    "anti_lynching": "Anti-lynching / anti-mob violence: campaigns against lynching, mob violence, race massacres",
    "segregation_public": "Segregation & public accommodations: Jim Crow transit, parks, theaters, restaurants, public facilities",
    "education": "Education equity: segregated schools, Black teachers/principals, school funding",
    "voting_rights": "Voting rights & political representation: disenfranchisement, white primaries, political appointments",
    "labor": "Labor & economic rights: strikes, unions, wage disputes, workplace discrimination, peonage",
    "criminal_justice": "Criminal justice & policing: police brutality, prisoner advocacy, clemency, wrongful prosecution",
    "military": "Military & veterans' rights: Black officers, soldier mistreatment, court-martial clemency",
    "government_discrimination": "Government discrimination: segregation in federal/state agencies, discriminatory officials",
    "housing": "Housing & residential segregation: ordinances, restrictive covenants, home defense, tenant rights",
    "healthcare": "Healthcare discrimination: hospital staffing, segregated medical facilities",
    "cultural_media": "Cultural & media protest: opposition to racist films, newspapers, speeches, symbols",
    "civil_rights_organizing": "Civil rights organizing: NAACP/NERL/Niagara conferences, broad campaigns, org founding",
    "pan_african": "Pan-African & international solidarity: UNIA, Pan-African Congress, international racial solidarity",
    "womens_organizing": "Women's rights & organizing: suffrage, women's clubs, gender-specific racial claims",
    "migration": "Migration as collective action: Great Migration framed as protest against Southern conditions",
}

EXTRACT_SYSTEM = """You are analyzing protest events from African American newspapers published between 1905 and 1929.
You will be given a text passage that has already been identified as describing a protest action.
Your task is to extract structured information about the event.

IMPORTANT NOTES:
- These newspapers were written for a Black audience. Authors often do NOT explicitly state that
  participants are Black — the audience would know. Similarly, white actors may not be labeled white.
  Set actor_race_explicit to true ONLY if the text explicitly names the race of the actors.
- Do NOT assume the event took place in the newspaper's publication city. Many articles report on
  events from around the country. Only assign a location if the text explicitly states where the
  event occurred. If the location is unclear, set location_city and location_state to null.
- For campaign_name, only provide a name if the event is clearly part of a recognized, named campaign
  or movement (e.g., "Dyer Anti-Lynching Bill campaign", "Brownsville Affair", "Sweet Trial").
  Do not invent campaign names for isolated events."""

EXTRACT_USER = """Extract structured information from this protest event.

Newspaper: {paper_name} (published in {pub_location})
Date: {date}

Text:
{text}

Issue categories (pick one primary, optionally one secondary):
{issue_list}

Respond with a JSON object:
{{
    "issue_primary": "<category_code>",
    "issue_secondary": "<category_code>" or null,
    "organizations": ["org1", "org2"] or [],
    "individuals": ["person1", "person2"] or [],
    "target": "who is being petitioned/opposed" or null,
    "size_min": <integer> or null,
    "size_max": <integer> or null,
    "size_text": "raw size descriptor from text" or null,
    "tactics": ["tactic1", "tactic2"],
    "campaign_name": "name of recognized campaign" or null,
    "actor_type": "black_protest" or "anti_black" or "mixed",
    "actor_race_explicit": true or false,
    "location_city": "city name" or null,
    "location_state": "state abbreviation" or null
}}

Valid tactics: march, rally, mass_meeting, petition, boycott, strike, delegation,
demonstration, parade, legal_action, riot, self_defense, verbal_statement,
organizational_founding, voter_mobilization, other

Respond ONLY with the JSON object, no other text."""


def parse_json_response(content: str) -> dict | None:
    """Extract JSON from a response that might have markdown fences or thinking tags."""
    content = content.strip()
    if "<think>" in content:
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if content.startswith("```"):
        lines = content.split("\n")
        inner = []
        started = False
        for line in lines:
            if line.startswith("```") and not started:
                started = True
                continue
            elif line.startswith("```") and started:
                break
            elif started:
                inner.append(line)
        content = "\n".join(inner)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None


def extract_event(client: OpenAI, event: dict) -> tuple[dict, dict | None]:
    """Run extraction prompt on a single event. Returns (event, result)."""
    text = str(event["source_text"])[:3000]
    paper = event["paper"]
    pub_location = PAPER_LOCATIONS.get(paper, "unknown")
    paper_name = paper.replace("-", " ").title()

    issue_list = "\n".join(f"  {code}: {desc}" for code, desc in ISSUE_DESCRIPTIONS.items())

    try:
        resp = client.chat.completions.create(
            model=CLASSIFIER_MODEL,
            max_tokens=500,
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": EXTRACT_USER.format(
                    paper_name=paper_name, pub_location=pub_location,
                    date=event["date"], text=text, issue_list=issue_list,
                )},
            ],
        )
        content = resp.choices[0].message.content.strip()
        return event, parse_json_response(content)
    except Exception:
        return event, None


def validate_result(result: dict) -> dict:
    """Normalize and validate extraction result."""
    # Validate issue_primary
    if result.get("issue_primary") not in ISSUE_CATEGORIES:
        result["issue_primary"] = None
    if result.get("issue_secondary") not in ISSUE_CATEGORIES + [None]:
        result["issue_secondary"] = None

    # Ensure lists
    for field in ("organizations", "individuals", "tactics"):
        if not isinstance(result.get(field), list):
            result[field] = []

    # Validate actor_type
    if result.get("actor_type") not in ("black_protest", "anti_black", "mixed"):
        result["actor_type"] = None

    # Validate actor_race_explicit
    if not isinstance(result.get("actor_race_explicit"), bool):
        result["actor_race_explicit"] = None

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="Max events to extract (0 = all)")
    parser.add_argument("--workers", type=int, default=10,
                        help="Number of parallel API calls")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be extracted without calling API")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY environment variable")
        return

    conn = get_connection()
    init_db(conn)

    # Load unextracted events
    rows = conn.execute("""
        SELECT e.id as event_id, e.source_text, e.event_type, e.description,
               c.paper, c.date, c.page
        FROM events e
        JOIN chunks c ON c.id = e.chunk_id
        LEFT JOIN extracted ex ON ex.event_id = e.id
        WHERE ex.event_id IS NULL
        ORDER BY e.id
    """).fetchall()

    to_process = [dict(r) for r in rows]
    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    already_done = total_events - len(to_process)

    print(f"Total events: {total_events}")
    if already_done > 0:
        print(f"Already extracted: {already_done}")
    print(f"To extract: {len(to_process)}")

    if args.limit > 0:
        to_process = to_process[:args.limit]
        print(f"Limited to {len(to_process)} events")

    if args.dry_run:
        for ev in to_process[:10]:
            text_preview = str(ev["source_text"] or "")[:100].replace("\n", " ")
            print(f"  [{ev['event_id']}] {ev['paper']} {ev['date']} - {ev['event_type']}")
            print(f"    {text_preview}")
            print()
        print(f"Would extract {len(to_process)} events")
        conn.close()
        return

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
    t0 = time.time()
    done = 0
    success = 0
    parse_errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(extract_event, client, ev): ev
            for ev in to_process
        }

        for future in as_completed(futures):
            event, result = future.result()
            done += 1

            if result is None:
                parse_errors += 1
            else:
                result = validate_result(result)
                conn.execute(
                    """INSERT OR REPLACE INTO event_details
                       (event_id, issue_primary, issue_secondary, organizations,
                        individuals, target, size_min, size_max, size_text,
                        tactics, campaign_name, actor_type, actor_race_explicit,
                        location_city, location_state)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (event["event_id"],
                     result.get("issue_primary"),
                     result.get("issue_secondary"),
                     json.dumps(result.get("organizations", [])),
                     json.dumps(result.get("individuals", [])),
                     result.get("target"),
                     result.get("size_min"),
                     result.get("size_max"),
                     result.get("size_text"),
                     json.dumps(result.get("tactics", [])),
                     result.get("campaign_name"),
                     result.get("actor_type"),
                     1 if result.get("actor_race_explicit") else 0,
                     result.get("location_city"),
                     result.get("location_state")),
                )
                success += 1

            # Mark as extracted regardless of success/failure
            conn.execute(
                "INSERT OR IGNORE INTO extracted (event_id) VALUES (?)",
                (event["event_id"],),
            )

            if done % 50 == 0:
                conn.commit()
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(to_process) - done) / rate if rate > 0 else 0
                print(f"  [{done}/{len(to_process)}] {success} extracted | "
                      f"{parse_errors} errors | {rate:.1f}/s | ETA {eta:.0f}s")

    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print(f"\nExtracted {done} events in {elapsed:.0f}s ({done/elapsed:.1f}/s)")
    print(f"Success: {success} | Parse errors: {parse_errors}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it loads and dry-run works**

Run: `uv run extract.py --dry-run --limit 5`

Expected: prints 5 events with previews and "Would extract 5 events"

- [ ] **Step 3: Test on a small batch**

Run: `uv run extract.py --limit 20 --workers 5`

Expected: extracts 20 events, prints progress, no crashes

- [ ] **Step 4: Spot-check results in database**

Run:
```bash
uv run python -c "
from db import get_connection
import json
conn = get_connection()
rows = conn.execute('SELECT * FROM event_details LIMIT 5').fetchall()
for r in rows:
    print(f'Event {r[\"event_id\"]}: {r[\"issue_primary\"]} | orgs={r[\"organizations\"]} | campaign={r[\"campaign_name\"]} | actor={r[\"actor_type\"]} | race_explicit={r[\"actor_race_explicit\"]}')
conn.close()
"
```

Verify: issue categories are from the valid set, organizations are JSON arrays, actor_type is one of the three valid values.

- [ ] **Step 5: Commit**

```bash
git add extract.py
git commit -m "Add extract stage for structured event extraction"
```

- [ ] **Step 6: Run full extraction on all 10K events**

Run: `uv run extract.py --workers 10`

This will take ~45-60 minutes at 3.5/s. Can run in background.

- [ ] **Step 7: Verify extraction results**

Run:
```bash
uv run python -c "
from db import get_connection
conn = get_connection()
total = conn.execute('SELECT COUNT(*) FROM event_details').fetchone()[0]
by_issue = conn.execute('SELECT issue_primary, COUNT(*) as n FROM event_details GROUP BY issue_primary ORDER BY n DESC').fetchall()
print(f'Total extracted: {total}')
print()
for r in by_issue:
    print(f'  {r[\"n\"]:>5}  {r[\"issue_primary\"]}')
conn.close()
"
```

- [ ] **Step 8: Commit after full run**

```bash
git add -A
git commit -m "Complete extraction of all events with structured fields"
```

---

## Chunk 3: Deduplication Stage

### Task 6: Create dedup.py

**Files:**
- Create: `dedup.py`

- [ ] **Step 1: Write dedup.py**

```python
"""Stage 5: Deduplicate events.

Three steps:
  5a: Find candidate pairs via embedding similarity + date proximity
  5b: LLM adjudication of candidate pairs
  5c: Build dedup groups via union-find
"""

import json
import os
import re
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from openai import OpenAI

from config import CLASSIFIER_MODEL, OPENROUTER_BASE_URL, EMBEDDING_MODEL
from db import get_connection, init_db
from embed import load_model


DEDUP_PROMPT = """You are comparing two protest events extracted from African American newspapers (1905-1929).
Determine if they describe the SAME real-world event or two DIFFERENT events.

Events can be the same even if reported by different newspapers on different dates —
newspapers often cover events days or weeks after they happen, or preview upcoming events.

Event A:
  Paper: {paper_a} ({date_a})
  Description: {desc_a}
  Location: {loc_a}
  Text excerpt: {text_a}

Event B:
  Paper: {paper_b} ({date_b})
  Description: {desc_b}
  Location: {loc_b}
  Text excerpt: {text_b}

Respond with JSON:
{{
    "same_event": true or false,
    "confidence": "high" or "medium" or "low",
    "reasoning": "brief explanation"
}}

Respond ONLY with the JSON object."""


def parse_json_response(content: str) -> dict | None:
    """Extract JSON from response."""
    content = content.strip()
    if "<think>" in content:
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if content.startswith("```"):
        lines = content.split("\n")
        inner = []
        started = False
        for line in lines:
            if line.startswith("```") and not started:
                started = True
                continue
            elif line.startswith("```") and started:
                break
            elif started:
                inner.append(line)
        content = "\n".join(inner)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None


def find_pairs(conn, threshold: float = 0.80, date_window: int = 30):
    """Step 5a: Find candidate duplicate pairs using embedding similarity."""
    print("Loading events for dedup...")
    rows = conn.execute("""
        SELECT e.id, e.description, e.source_text, e.chunk_id,
               c.paper, c.date,
               ed.location_city, ed.location_state, ed.campaign_name
        FROM events e
        JOIN chunks c ON c.id = e.chunk_id
        LEFT JOIN event_details ed ON ed.event_id = e.id
        ORDER BY e.id
    """).fetchall()

    events = [dict(r) for r in rows]
    print(f"Loaded {len(events)} events")

    if len(events) < 2:
        print("Not enough events to deduplicate")
        return 0

    # Embed descriptions
    print(f"Loading embedding model {EMBEDDING_MODEL}...")
    model = load_model()
    descriptions = [f"search_document: {e['description'] or ''}" for e in events]
    print("Embedding event descriptions...")
    embs = model.encode(descriptions, normalize_embeddings=True, show_progress_bar=True)

    # Compute pairwise similarities (batched to avoid memory issues)
    print("Finding candidate pairs...")
    id_to_idx = {e["id"]: i for i, e in enumerate(events)}
    pairs_found = 0

    # Parse dates for window comparison
    from datetime import datetime, timedelta

    def parse_date(d):
        try:
            return datetime.strptime(str(d), "%Y-%m-%d")
        except (ValueError, TypeError):
            return None

    event_dates = [parse_date(e["date"]) for e in events]

    batch_size = 500
    for start in range(0, len(events), batch_size):
        end = min(start + batch_size, len(events))
        batch_embs = embs[start:end]

        # Compare this batch against all events
        sims = batch_embs @ embs.T

        for i_local in range(end - start):
            i = start + i_local
            for j in range(i + 1, len(events)):
                sim = float(sims[i_local, j])

                if sim < threshold:
                    continue

                # Check date window
                d_i, d_j = event_dates[i], event_dates[j]
                if d_i and d_j:
                    if abs((d_i - d_j).days) > date_window:
                        continue

                # Check if pair already exists
                existing = conn.execute(
                    "SELECT id FROM dedup_pairs WHERE event_id_a=? AND event_id_b=?",
                    (events[i]["id"], events[j]["id"]),
                ).fetchone()
                if existing:
                    continue

                conn.execute(
                    "INSERT INTO dedup_pairs (event_id_a, event_id_b, similarity) VALUES (?, ?, ?)",
                    (events[i]["id"], events[j]["id"], round(sim, 4)),
                )
                pairs_found += 1

        conn.commit()
        if start % 1000 == 0 and start > 0:
            print(f"  Processed {start}/{len(events)} events, {pairs_found} pairs found")

    # Also add pairs with matching campaign names
    campaign_pairs = conn.execute("""
        SELECT DISTINCT ed1.event_id, ed2.event_id
        FROM event_details ed1
        JOIN event_details ed2 ON ed1.campaign_name = ed2.campaign_name
            AND ed1.event_id < ed2.event_id
            AND ed1.campaign_name IS NOT NULL
            AND ed1.campaign_name != ''
        LEFT JOIN dedup_pairs dp ON dp.event_id_a = ed1.event_id
            AND dp.event_id_b = ed2.event_id
        WHERE dp.id IS NULL
    """).fetchall()

    for row in campaign_pairs:
        conn.execute(
            "INSERT INTO dedup_pairs (event_id_a, event_id_b, similarity) VALUES (?, ?, ?)",
            (row[0], row[1], 0.0),  # similarity=0 indicates campaign-name match
        )
        pairs_found += 1

    conn.commit()
    print(f"Found {pairs_found} candidate pairs")
    return pairs_found


def adjudicate_pair(client: OpenAI, pair: dict) -> tuple[dict, dict | None]:
    """LLM adjudication for a single pair."""
    try:
        resp = client.chat.completions.create(
            model=CLASSIFIER_MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": DEDUP_PROMPT.format(
                paper_a=pair["paper_a"], date_a=pair["date_a"],
                desc_a=pair["desc_a"], loc_a=pair["loc_a"] or "not stated",
                text_a=(pair["text_a"] or "")[:500],
                paper_b=pair["paper_b"], date_b=pair["date_b"],
                desc_b=pair["desc_b"], loc_b=pair["loc_b"] or "not stated",
                text_b=(pair["text_b"] or "")[:500],
            )}],
        )
        content = resp.choices[0].message.content.strip()
        return pair, parse_json_response(content)
    except Exception:
        return pair, None


def adjudicate(conn, client: OpenAI, workers: int = 10):
    """Step 5b: LLM adjudication of unadjudicated pairs."""
    rows = conn.execute("""
        SELECT dp.id, dp.event_id_a, dp.event_id_b, dp.similarity,
               e1.description as desc_a, e1.source_text as text_a,
               c1.paper as paper_a, c1.date as date_a,
               ed1.location_city as loc_a,
               e2.description as desc_b, e2.source_text as text_b,
               c2.paper as paper_b, c2.date as date_b,
               ed2.location_city as loc_b
        FROM dedup_pairs dp
        JOIN events e1 ON e1.id = dp.event_id_a
        JOIN events e2 ON e2.id = dp.event_id_b
        JOIN chunks c1 ON c1.id = e1.chunk_id
        JOIN chunks c2 ON c2.id = e2.chunk_id
        LEFT JOIN event_details ed1 ON ed1.event_id = dp.event_id_a
        LEFT JOIN event_details ed2 ON ed2.event_id = dp.event_id_b
        WHERE dp.same_event IS NULL
        ORDER BY dp.similarity DESC
    """).fetchall()

    to_process = [dict(r) for r in rows]
    print(f"Pairs to adjudicate: {len(to_process)}")

    if not to_process:
        return

    t0 = time.time()
    done = 0
    same_count = 0
    parse_errors = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(adjudicate_pair, client, p): p
            for p in to_process
        }

        for future in as_completed(futures):
            pair, result = future.result()
            done += 1

            if result is None:
                parse_errors += 1
            else:
                same = 1 if result.get("same_event") else 0
                conn.execute(
                    "UPDATE dedup_pairs SET same_event=?, confidence=?, reasoning=? WHERE id=?",
                    (same, result.get("confidence"), result.get("reasoning"), pair["id"]),
                )
                if same:
                    same_count += 1

            if done % 50 == 0:
                conn.commit()
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(to_process) - done) / rate if rate > 0 else 0
                print(f"  [{done}/{len(to_process)}] {same_count} same | "
                      f"{parse_errors} errors | {rate:.1f}/s | ETA {eta:.0f}s")

    conn.commit()
    elapsed = time.time() - t0
    print(f"\nAdjudicated {done} pairs in {elapsed:.0f}s")
    print(f"Same event: {same_count} | Different: {done - same_count - parse_errors} | Errors: {parse_errors}")


def build_groups(conn):
    """Step 5c: Build dedup groups using union-find."""
    confirmed = conn.execute(
        "SELECT event_id_a, event_id_b FROM dedup_pairs WHERE same_event = 1"
    ).fetchall()

    if not confirmed:
        print("No confirmed duplicate pairs")
        return

    # Union-find
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            # Keep the lower ID as canonical (earlier event)
            if ra > rb:
                ra, rb = rb, ra
            parent[rb] = ra

    for row in confirmed:
        union(row[0], row[1])

    # Build groups
    groups = {}
    all_event_ids = set()
    for row in confirmed:
        all_event_ids.add(row[0])
        all_event_ids.add(row[1])

    for eid in all_event_ids:
        canonical = find(eid)
        groups.setdefault(canonical, set()).add(eid)

    # Clear and rebuild
    conn.execute("DELETE FROM dedup_groups")
    for canonical, members in groups.items():
        for eid in members:
            conn.execute(
                "INSERT OR REPLACE INTO dedup_groups (event_id, canonical_event_id) VALUES (?, ?)",
                (eid, canonical),
            )

    # Merge event_sources: copy sources from duplicate events to canonical
    for canonical, members in groups.items():
        for eid in members:
            if eid != canonical:
                conn.execute("""
                    INSERT OR IGNORE INTO event_sources (event_id, chunk_id, role)
                    SELECT ?, chunk_id, 'duplicate'
                    FROM event_sources WHERE event_id = ?
                """, (canonical, eid))

    conn.commit()

    multi = sum(1 for g in groups.values() if len(g) > 1)
    total_dupes = sum(len(g) - 1 for g in groups.values())
    print(f"Built {multi} dedup groups covering {total_dupes} duplicate events")
    print(f"Unique events after dedup: {conn.execute('SELECT COUNT(DISTINCT canonical_event_id) FROM dedup_groups').fetchone()[0]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--find-pairs", action="store_true", help="Only find candidate pairs")
    parser.add_argument("--adjudicate", action="store_true", help="Only adjudicate pairs")
    parser.add_argument("--build-groups", action="store_true", help="Only build groups")
    parser.add_argument("--threshold", type=float, default=0.80,
                        help="Similarity threshold for candidate pairs")
    parser.add_argument("--date-window", type=int, default=30,
                        help="Date window in days for candidate pairs")
    parser.add_argument("--workers", type=int, default=10,
                        help="Number of parallel API calls")
    args = parser.parse_args()

    conn = get_connection()
    init_db(conn)

    # If no specific step requested, run all
    run_all = not (args.find_pairs or args.adjudicate or args.build_groups)

    if run_all or args.find_pairs:
        find_pairs(conn, threshold=args.threshold, date_window=args.date_window)

    if run_all or args.adjudicate:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            print("ERROR: Set OPENROUTER_API_KEY environment variable")
            conn.close()
            return
        client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
        adjudicate(conn, client, workers=args.workers)

    if run_all or args.build_groups:
        build_groups(conn)

    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it loads**

Run: `uv run python -c "import dedup; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add dedup.py
git commit -m "Add dedup stage for event deduplication"
```

- [ ] **Step 4: Test pair finding on extracted events**

Run: `uv run dedup.py --find-pairs`

Check output for number of candidate pairs found. If zero, the threshold may need lowering. If thousands, that's expected.

- [ ] **Step 5: Test adjudication on a small batch**

Run:
```bash
uv run python -c "
from db import get_connection
conn = get_connection()
n = conn.execute('SELECT COUNT(*) FROM dedup_pairs WHERE same_event IS NULL').fetchone()[0]
print(f'{n} pairs to adjudicate')
conn.close()
"
```

Then: `uv run dedup.py --adjudicate --workers 5`

- [ ] **Step 6: Build groups**

Run: `uv run dedup.py --build-groups`

- [ ] **Step 7: Verify dedup results**

Run:
```bash
uv run python -c "
from db import get_connection
conn = get_connection()
pairs = conn.execute('SELECT COUNT(*) FROM dedup_pairs').fetchone()[0]
same = conn.execute('SELECT COUNT(*) FROM dedup_pairs WHERE same_event=1').fetchone()[0]
groups = conn.execute('SELECT COUNT(DISTINCT canonical_event_id) FROM dedup_groups').fetchone()[0]
print(f'Pairs: {pairs}, Same: {same}, Dedup groups: {groups}')
conn.close()
"
```

- [ ] **Step 8: Commit**

```bash
git add dedup.py
git commit -m "Run dedup on extracted events"
```

---

## Chunk 4: Campaign Clustering Stage

### Task 7: Create cluster.py

**Files:**
- Create: `cluster.py`

- [ ] **Step 1: Write cluster.py**

```python
"""Stage 6: Campaign clustering.

Groups deduplicated events into campaigns/episodes.
Step 6a: Named campaign consolidation (from campaign_name field)
Step 6b: Algorithmic clustering (issue + location + time window)
Named campaigns are never overridden by algorithmic clustering.
"""

import os
import re
import json
import argparse
from collections import defaultdict
from datetime import datetime, timedelta

from openai import OpenAI

from config import CLASSIFIER_MODEL, OPENROUTER_BASE_URL
from db import get_connection, init_db


def normalize_campaign_names(conn, client: OpenAI | None = None):
    """Step 6a: Group events by campaign_name, normalizing similar names."""
    rows = conn.execute("""
        SELECT DISTINCT ed.campaign_name
        FROM event_details ed
        WHERE ed.campaign_name IS NOT NULL AND ed.campaign_name != ''
    """).fetchall()

    raw_names = [r[0] for r in rows]
    if not raw_names:
        print("No named campaigns found")
        return {}

    print(f"Found {len(raw_names)} distinct campaign names")

    # Use LLM to normalize names if we have many
    if len(raw_names) > 5 and client:
        prompt = f"""Below are campaign names extracted from protest events in African American newspapers (1905-1929).
Many refer to the same campaign with slightly different wording. Group them into canonical names.

Names:
{chr(10).join(f'- {n}' for n in sorted(raw_names))}

Respond with a JSON object mapping each original name to its canonical form:
{{"original name": "canonical name", ...}}

Respond ONLY with the JSON object."""

        try:
            resp = client.chat.completions.create(
                model=CLASSIFIER_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.choices[0].message.content.strip()
            if "<think>" in content:
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            if content.startswith("```"):
                lines = content.split("\n")
                inner = [l for l in lines[1:] if not l.startswith("```")]
                content = "\n".join(inner)
            name_map = json.loads(content)
            print(f"Normalized {len(raw_names)} names into {len(set(name_map.values()))} canonical names")
            return name_map
        except Exception as e:
            print(f"LLM normalization failed ({e}), using exact names")

    # Fallback: use exact names
    return {n: n for n in raw_names}


def create_named_campaigns(conn, name_map: dict):
    """Create campaign records for named campaigns and link events."""
    # Group events by canonical campaign name
    campaigns = defaultdict(list)
    for original, canonical in name_map.items():
        event_ids = conn.execute(
            "SELECT event_id FROM event_details WHERE campaign_name = ?",
            (original,),
        ).fetchall()
        for r in event_ids:
            campaigns[canonical].append(r[0])

    created = 0
    for name, event_ids in campaigns.items():
        if not event_ids:
            continue

        # Get date range and issue
        meta = conn.execute("""
            SELECT MIN(c.date) as date_start, MAX(c.date) as date_end,
                   ed.issue_primary
            FROM events e
            JOIN chunks c ON c.id = e.chunk_id
            JOIN event_details ed ON ed.event_id = e.id
            WHERE e.id IN ({})
            GROUP BY ed.issue_primary
            ORDER BY COUNT(*) DESC
            LIMIT 1
        """.format(",".join("?" * len(event_ids))), event_ids).fetchone()

        cursor = conn.execute(
            """INSERT INTO campaigns (name, named, issue_primary, event_count, date_start, date_end)
               VALUES (?, 1, ?, ?, ?, ?)""",
            (name, meta["issue_primary"] if meta else None,
             len(event_ids),
             meta["date_start"] if meta else None,
             meta["date_end"] if meta else None),
        )
        campaign_id = cursor.lastrowid

        for eid in event_ids:
            conn.execute(
                "INSERT OR IGNORE INTO event_campaigns (event_id, campaign_id) VALUES (?, ?)",
                (eid, campaign_id),
            )
        created += 1

    conn.commit()
    print(f"Created {created} named campaigns linking {sum(len(v) for v in campaigns.values())} events")
    return created


def algorithmic_cluster(conn, time_window: int = 90, min_cluster: int = 3):
    """Step 6b: Cluster remaining events by issue + location + time."""
    # Get events NOT already in a named campaign
    rows = conn.execute("""
        SELECT e.id, c.date, ed.issue_primary, ed.location_city, ed.location_state
        FROM events e
        JOIN chunks c ON c.id = e.chunk_id
        LEFT JOIN event_details ed ON ed.event_id = e.id
        LEFT JOIN event_campaigns ec ON ec.event_id = e.id
        LEFT JOIN campaigns camp ON camp.id = ec.campaign_id AND camp.named = 1
        WHERE camp.id IS NULL
          AND ed.issue_primary IS NOT NULL
        ORDER BY c.date
    """).fetchall()

    events = [dict(r) for r in rows]
    print(f"Events available for algorithmic clustering: {len(events)}")

    if len(events) < min_cluster:
        print("Not enough events to cluster")
        return 0

    # Group by (issue, state, city) — city can be null
    groups = defaultdict(list)
    for ev in events:
        key = (ev["issue_primary"], ev["location_state"], ev["location_city"])
        groups[key].append(ev)

    # Within each group, find temporal clusters
    created = 0
    for key, group_events in groups.items():
        issue, state, city = key

        # Sort by date and find time-windowed clusters
        dated = []
        for ev in group_events:
            try:
                dt = datetime.strptime(ev["date"], "%Y-%m-%d")
                dated.append((dt, ev))
            except (ValueError, TypeError):
                continue

        if len(dated) < min_cluster:
            continue

        dated.sort(key=lambda x: x[0])

        # Simple sliding window clustering
        clusters = []
        current = [dated[0]]
        for i in range(1, len(dated)):
            if (dated[i][0] - current[-1][0]).days <= time_window:
                current.append(dated[i])
            else:
                if len(current) >= min_cluster:
                    clusters.append(current)
                current = [dated[i]]
        if len(current) >= min_cluster:
            clusters.append(current)

        for cluster in clusters:
            event_ids = [ev["id"] for _, ev in cluster]
            date_start = cluster[0][0].strftime("%Y-%m-%d")
            date_end = cluster[-1][0].strftime("%Y-%m-%d")

            loc = f"{city}, {state}" if city else (state or "various")
            name = f"{issue} — {loc} ({date_start[:7]})"

            cursor = conn.execute(
                """INSERT INTO campaigns (name, named, issue_primary, event_count, date_start, date_end)
                   VALUES (?, 0, ?, ?, ?, ?)""",
                (name, issue, len(event_ids), date_start, date_end),
            )
            campaign_id = cursor.lastrowid

            for eid in event_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO event_campaigns (event_id, campaign_id) VALUES (?, ?)",
                    (eid, campaign_id),
                )
            created += 1

    conn.commit()
    print(f"Created {created} algorithmic clusters")
    return created


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--named-only", action="store_true",
                        help="Only consolidate named campaigns")
    parser.add_argument("--min-cluster", type=int, default=3,
                        help="Minimum events for algorithmic clusters")
    parser.add_argument("--window", type=int, default=90,
                        help="Time window in days for algorithmic clustering")
    args = parser.parse_args()

    conn = get_connection()
    init_db(conn)

    # Clear existing campaigns for rebuild
    conn.execute("DELETE FROM event_campaigns")
    conn.execute("DELETE FROM campaigns")
    conn.commit()

    # Step 6a: Named campaigns
    client = None
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)

    name_map = normalize_campaign_names(conn, client)
    if name_map:
        create_named_campaigns(conn, name_map)

    # Step 6b: Algorithmic clustering
    if not args.named_only:
        algorithmic_cluster(conn, time_window=args.window, min_cluster=args.min_cluster)

    # Summary
    total = conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0]
    named = conn.execute("SELECT COUNT(*) FROM campaigns WHERE named=1").fetchone()[0]
    algo = total - named
    linked = conn.execute("SELECT COUNT(DISTINCT event_id) FROM event_campaigns").fetchone()[0]
    print(f"\nTotal campaigns: {total} ({named} named, {algo} algorithmic)")
    print(f"Events in campaigns: {linked}")

    conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it loads**

Run: `uv run python -c "import cluster; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cluster.py
git commit -m "Add campaign clustering stage"
```

- [ ] **Step 4: Run clustering**

Run: `uv run cluster.py`

- [ ] **Step 5: Verify results**

Run:
```bash
uv run python -c "
from db import get_connection
conn = get_connection()
named = conn.execute('SELECT name, event_count FROM campaigns WHERE named=1 ORDER BY event_count DESC LIMIT 15').fetchall()
algo = conn.execute('SELECT COUNT(*) FROM campaigns WHERE named=0').fetchone()[0]
print('Top named campaigns:')
for r in named:
    print(f'  {r[\"event_count\"]:>4} events  {r[\"name\"]}')
print(f'\nAlgorithmic clusters: {algo}')
conn.close()
"
```

- [ ] **Step 6: Commit**

```bash
git add cluster.py
git commit -m "Run campaign clustering on extracted events"
```

---

## Chunk 5: Enhanced Report

### Task 8: Update report.py

**Files:**
- Modify: `report.py`

- [ ] **Step 1: Update load_events to join new tables**

Replace the `load_events` function to pull from `event_details`, `event_sources`, `dedup_groups`, and `event_campaigns`. Return a richer dataframe. Also add a `load_event_sources` function that returns a dict mapping event_id to list of source dicts.

Key changes:
- Join `event_details` for issue category, organizations, actor_type, campaign_name
- Join `dedup_groups` to identify canonical events and duplicate counts
- Load `event_sources` separately for multi-source display
- Add `load_campaigns` to get campaign data

- [ ] **Step 2: Update generate_html with new columns and filters**

Add to the HTML report:
- Issue category column with filter dropdown
- Organizations display (parsed from JSON)
- Actor type badge
- Campaign name (linked to campaign filter)
- Sources section showing all articles covering the event (from `event_sources` + `chunks`)
- Dedup indicator showing "N sources" count
- Filter by issue category, actor type, campaign
- Summary stats at top: events by issue, by year

- [ ] **Step 3: Test report generation**

Run: `uv run report.py`

Open `data/events.html` and verify:
- Issue categories display and filter correctly
- Multiple sources show for deduplicated events
- Campaign names appear
- Filters work

- [ ] **Step 4: Commit**

```bash
git add report.py
git commit -m "Enhanced report with issue categories, sources, and campaigns"
```

---

## Chunk 6: Combined Prompt and Pipeline Integration

### Task 9: Add combined classify+extract prompt

**Files:**
- Modify: `classify.py`

- [ ] **Step 1: Add combined prompt constants**

Add new `COMBINED_SYSTEM` and `COMBINED_USER` prompt templates to `classify.py` that merge the classification and extraction into a single LLM call. The combined prompt returns the full JSON with `is_protest` plus all extraction fields. When `is_protest` is false, other fields are null.

- [ ] **Step 2: Add classify_and_extract_group function**

New function that uses the combined prompt and writes to both `events` and `event_details` tables in one pass. Also populates `event_sources`.

- [ ] **Step 3: Add --combined flag to classify.py**

When `--combined` is passed, use the new function instead of `classify_group`. Default behavior remains the simple binary classification for backwards compatibility.

- [ ] **Step 4: Test combined prompt on small batch**

Run: `uv run classify.py --combined --limit 10 --workers 3`

Verify both `events` and `event_details` are populated.

- [ ] **Step 5: Commit**

```bash
git add classify.py
git commit -m "Add combined classify+extract prompt for future pipeline runs"
```

### Task 10: Update pipeline.py

**Files:**
- Modify: `pipeline.py`

- [ ] **Step 1: Add extract, dedup, cluster stages to pipeline**

After the classify loop completes, add calls to:
1. `extract.py` logic (import and call)
2. `dedup.py` logic (import and call)
3. `cluster.py` logic (import and call)

- [ ] **Step 2: Add --combined flag to pipeline**

When `--combined` is passed, pipeline uses the combined classify+extract prompt, skipping the separate extract stage.

- [ ] **Step 3: Update report generation**

Ensure the pipeline calls the enhanced `report.py` which now surfaces all new fields.

- [ ] **Step 4: Test end-to-end with --max-files 10**

Run: `uv run pipeline.py --max-files 10 --combined`

Verify all stages run and report is generated.

- [ ] **Step 5: Commit**

```bash
git add pipeline.py
git commit -m "Wire extract, dedup, and cluster stages into pipeline"
```

### Task 11: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update documentation**

Update the Running the Pipeline section, Architecture section, and Key Design Decisions to reflect the new stages, combined prompt, and enriched schema.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Update CLAUDE.md with extended pipeline documentation"
```

### Task 12: Final commit and push

- [ ] **Step 1: Verify everything works**

Run:
```bash
uv run python -c "
from db import get_connection, init_db
conn = get_connection()
init_db(conn)
events = conn.execute('SELECT COUNT(*) FROM events').fetchone()[0]
details = conn.execute('SELECT COUNT(*) FROM event_details').fetchone()[0]
sources = conn.execute('SELECT COUNT(*) FROM event_sources').fetchone()[0]
campaigns = conn.execute('SELECT COUNT(*) FROM campaigns').fetchone()[0]
print(f'Events: {events}')
print(f'Event details: {details}')
print(f'Event sources: {sources}')
print(f'Campaigns: {campaigns}')
conn.close()
"
```

- [ ] **Step 2: Final commit and push**

```bash
git add -A
git commit -m "Extended pipeline: extraction, deduplication, and campaign clustering"
git push
```
