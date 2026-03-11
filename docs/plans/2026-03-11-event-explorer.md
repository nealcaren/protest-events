# Protest Events Explorer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a modern, editorial-style Svelte app for browsing 7,600+ protest events from African American newspapers (1905-1929).

**Architecture:** Python exports deduplicated event data from SQLite to static JSON files. A Svelte/Vite app in `site/` loads these JSON files and provides four views: Dashboard, Browse/Search, Event Detail, and Campaign pages. Data access is abstracted behind an `api.js` module for future API swap.

**Tech Stack:** Svelte 5, Vite, Fuse.js (search), Chart.js (charts), svelte-routing (client-side routing)

**Spec:** `docs/specs/2026-03-11-event-explorer-design.md`

---

## File Structure

### Python (modified)
- `report.py` — Add `export_json()` function that writes `events.json`, `campaigns.json`, `meta.json` to `site/public/data/`

### Svelte App (new: `site/`)
```
site/
  public/
    data/              # JSON files (gitignored, generated)
  src/
    lib/
      api.js           # Data loading abstraction
      search.js        # Fuse.js index setup
      utils.js         # URL builders, formatters
      stores.js        # Svelte stores for shared state
    components/
      EventCard.svelte       # Event card for lists
      SourceBlock.svelte     # OCR text + dangerouspress link
      FacetSidebar.svelte    # Filter sidebar
      IssueChart.svelte      # Horizontal bar chart
      StatCard.svelte        # Dashboard stat card
      Pagination.svelte      # Page navigation
      Badge.svelte           # Issue/campaign/type badges
      Header.svelte          # Site header/nav
    routes/
      Dashboard.svelte
      EventList.svelte
      EventPage.svelte
      CampaignList.svelte
      CampaignPage.svelte
    App.svelte
    main.js
  index.html
  package.json
  vite.config.js
```

---

## Chunk 1: Data Export + Svelte Scaffold

### Task 1: JSON Data Export

**Files:**
- Modify: `report.py`

- [ ] **Step 1: Add `export_json()` to report.py**

Add a function that queries the database and writes three JSON files. This replaces nothing — it's additive alongside the existing HTML report.

```python
import json
from pathlib import Path
from config import PAPER_LOCATIONS, ISSUE_CATEGORIES
from db import get_connection, init_db

SITE_DATA_DIR = Path(__file__).parent / "site" / "public" / "data"

def export_json():
    """Export deduplicated events, campaigns, and metadata as JSON for the frontend."""
    conn = get_connection()
    init_db(conn)

    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # --- events.json ---
    # Get canonical event IDs (deduped) + singletons
    canonical_ids = set()
    dedup_rows = conn.execute("SELECT DISTINCT canonical_event_id FROM dedup_groups").fetchall()
    for r in dedup_rows:
        canonical_ids.add(r[0])

    all_event_ids = set(r[0] for r in conn.execute("SELECT id FROM events").fetchall())
    grouped_event_ids = set(r[0] for r in conn.execute("SELECT event_id FROM dedup_groups").fetchall())
    singleton_ids = all_event_ids - grouped_event_ids

    export_ids = canonical_ids | singleton_ids

    # Load event details
    events_out = []
    for eid in sorted(export_ids):
        ev = conn.execute("""
            SELECT e.id, e.event_type, e.description, e.location, e.participants,
                   e.date_mentioned, c.date, c.paper,
                   ed.issue_primary, ed.issue_secondary, ed.organizations,
                   ed.individuals, ed.target, ed.size_min, ed.size_max,
                   ed.size_text, ed.tactics, ed.actor_type,
                   ed.actor_race_explicit, ed.location_city, ed.location_state
            FROM events e
            JOIN chunks c ON c.id = e.chunk_id
            LEFT JOIN event_details ed ON ed.event_id = e.id
            WHERE e.id = ?
        """, (eid,)).fetchone()

        if not ev:
            continue

        # Sources: all chunks linked to this event (primary + duplicates)
        sources = conn.execute("""
            SELECT c.paper, c.date, c.page, c.chunk_idx, c.text, es.role
            FROM event_sources es
            JOIN chunks c ON c.id = es.chunk_id
            WHERE es.event_id = ?
            ORDER BY c.date, c.paper
        """, (eid,)).fetchall()

        # Campaign IDs
        campaign_ids = [r[0] for r in conn.execute(
            "SELECT campaign_id FROM event_campaigns WHERE event_id = ?", (eid,)
        ).fetchall()]

        def parse_json_field(val):
            if not val:
                return []
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return []

        events_out.append({
            "id": ev["id"],
            "event_type": ev["event_type"],
            "description": ev["description"],
            "date": ev["date"],
            "location_city": ev["location_city"],
            "location_state": ev["location_state"],
            "issue_primary": ev["issue_primary"],
            "issue_secondary": ev["issue_secondary"],
            "organizations": parse_json_field(ev["organizations"]),
            "individuals": parse_json_field(ev["individuals"]),
            "target": ev["target"],
            "size_text": ev["size_text"],
            "tactics": parse_json_field(ev["tactics"]),
            "actor_type": ev["actor_type"],
            "campaign_ids": campaign_ids,
            "sources": [
                {
                    "paper": s["paper"],
                    "date": s["date"],
                    "page": s["page"],
                    "chunk_idx": s["chunk_idx"],
                    "source_text": s["text"],
                    "role": s["role"],
                }
                for s in sources
            ],
        })

    with open(SITE_DATA_DIR / "events.json", "w") as f:
        json.dump(events_out, f)
    print(f"Exported {len(events_out)} events to events.json")

    # --- campaigns.json ---
    campaigns_out = []
    for row in conn.execute("SELECT * FROM campaigns ORDER BY event_count DESC").fetchall():
        event_ids = [r[0] for r in conn.execute(
            "SELECT event_id FROM event_campaigns WHERE campaign_id = ?", (row["id"],)
        ).fetchall()]
        # Only include event IDs that are in our export set
        event_ids = [eid for eid in event_ids if eid in export_ids]
        campaigns_out.append({
            "id": row["id"],
            "name": row["name"],
            "named": bool(row["named"]),
            "issue_primary": row["issue_primary"],
            "event_count": len(event_ids),
            "date_start": row["date_start"],
            "date_end": row["date_end"],
            "event_ids": event_ids,
        })

    with open(SITE_DATA_DIR / "campaigns.json", "w") as f:
        json.dump(campaigns_out, f)
    print(f"Exported {len(campaigns_out)} campaigns to campaigns.json")

    # --- meta.json ---
    issue_counts = {}
    for row in conn.execute("""
        SELECT ed.issue_primary, COUNT(*) as cnt
        FROM event_details ed
        WHERE ed.event_id IN ({}) AND ed.issue_primary IS NOT NULL
        GROUP BY ed.issue_primary ORDER BY cnt DESC
    """.format(",".join("?" * len(export_ids))), sorted(export_ids)).fetchall():
        issue_counts[row[0]] = row[1]

    newspapers = []
    for slug, location in sorted(PAPER_LOCATIONS.items()):
        newspapers.append({
            "slug": slug,
            "name": slug.replace("-", " ").title(),
            "location": location,
        })

    dates = conn.execute("""
        SELECT MIN(c.date), MAX(c.date)
        FROM events e JOIN chunks c ON c.id = e.chunk_id
        WHERE e.id IN ({})
    """.format(",".join("?" * len(export_ids))), sorted(export_ids)).fetchone()

    meta = {
        "total_events": len(events_out),
        "total_campaigns": len(campaigns_out),
        "total_newspapers": len(PAPER_LOCATIONS),
        "date_range": [dates[0], dates[1]],
        "issue_counts": issue_counts,
        "newspaper_list": newspapers,
    }

    with open(SITE_DATA_DIR / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"Exported meta.json")

    conn.close()
```

Add to `main()`:

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Export JSON for frontend")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    init_db(conn)
    events = load_events(conn)
    event_sources = load_event_sources(conn)
    event_campaigns = load_event_campaign_map(conn)
    conn.close()

    print(f"Loaded {len(events)} events")

    if args.json:
        export_json()
    else:
        html = generate_html(events, event_sources, event_campaigns)
        REPORT_FILE.write_text(html)
        print(f"Report saved to {REPORT_FILE}")
        print(f"Open: file://{REPORT_FILE.resolve()}")
```

- [ ] **Step 2: Run the export**

```bash
uv run report.py --json
```

Expected output:
```
Loaded 10203 events
Exported ~7623 events to events.json
Exported 757 campaigns to campaigns.json
Exported meta.json
```

Verify files exist:
```bash
ls -la site/public/data/
python -c "import json; d=json.load(open('site/public/data/events.json')); print(len(d), 'events'); print(d[0].keys())"
```

- [ ] **Step 3: Commit**

```bash
git add report.py site/public/data/.gitkeep
git commit -m "feat: add JSON data export for frontend app"
```

Note: Add `site/public/data/*.json` to `.gitignore` — these are generated files.

---

### Task 2: Svelte Project Scaffold

**Files:**
- Create: `site/package.json`
- Create: `site/vite.config.js`
- Create: `site/index.html`
- Create: `site/src/main.js`
- Create: `site/src/App.svelte`
- Create: `site/.gitignore`

- [ ] **Step 1: Scaffold Svelte project**

```bash
cd site
npm create vite@latest . -- --template svelte
npm install
npm install svelte-routing fuse.js chart.js
```

- [ ] **Step 2: Update `site/vite.config.js`**

```javascript
import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

export default defineConfig({
  plugins: [svelte()],
  base: './',
})
```

- [ ] **Step 3: Create `site/src/main.js`**

```javascript
import App from './App.svelte'

const app = new App({
  target: document.getElementById('app'),
})

export default app
```

- [ ] **Step 4: Create minimal `site/src/App.svelte`**

```svelte
<script>
  import { Router, Route, Link } from 'svelte-routing'
  import Header from './components/Header.svelte'
  import Dashboard from './routes/Dashboard.svelte'
  import EventList from './routes/EventList.svelte'
  import EventPage from './routes/EventPage.svelte'
  import CampaignList from './routes/CampaignList.svelte'
  import CampaignPage from './routes/CampaignPage.svelte'
</script>

<Router>
  <Header />
  <main>
    <Route path="/" component={Dashboard} />
    <Route path="/events" component={EventList} />
    <Route path="/events/:id" let:params>
      <EventPage id={params.id} />
    </Route>
    <Route path="/campaigns" component={CampaignList} />
    <Route path="/campaigns/:id" let:params>
      <CampaignPage id={params.id} />
    </Route>
  </main>
</Router>

<style>
  :global(body) {
    margin: 0;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #fafafa;
    color: #1a1a1a;
    line-height: 1.6;
  }
  main {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 24px 48px;
  }
</style>
```

- [ ] **Step 5: Create `site/src/components/Header.svelte`**

```svelte
<script>
  import { Link } from 'svelte-routing'
</script>

<header>
  <div class="header-inner">
    <Link to="/" class="logo">Protest Events</Link>
    <nav>
      <Link to="/events">Browse</Link>
      <Link to="/campaigns">Campaigns</Link>
    </nav>
  </div>
</header>

<style>
  header {
    background: #1a1a1a;
    color: white;
    padding: 0 24px;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .header-inner {
    max-width: 1200px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
  }
  :global(.logo) {
    color: white !important;
    text-decoration: none;
    font-weight: 700;
    font-size: 1.1rem;
    letter-spacing: -0.02em;
  }
  nav {
    display: flex;
    gap: 24px;
  }
  nav :global(a) {
    color: rgba(255,255,255,0.7);
    text-decoration: none;
    font-size: 0.9rem;
    font-weight: 500;
  }
  nav :global(a:hover) {
    color: white;
  }
</style>
```

- [ ] **Step 6: Create placeholder route components**

Create stub files for all five routes:

`site/src/routes/Dashboard.svelte`:
```svelte
<h1>Dashboard</h1>
<p>Coming soon.</p>
```

`site/src/routes/EventList.svelte`:
```svelte
<h1>Browse Events</h1>
<p>Coming soon.</p>
```

`site/src/routes/EventPage.svelte`:
```svelte
<script>
  export let id
</script>
<h1>Event {id}</h1>
<p>Coming soon.</p>
```

`site/src/routes/CampaignList.svelte`:
```svelte
<h1>Campaigns</h1>
<p>Coming soon.</p>
```

`site/src/routes/CampaignPage.svelte`:
```svelte
<script>
  export let id
</script>
<h1>Campaign {id}</h1>
<p>Coming soon.</p>
```

- [ ] **Step 7: Verify dev server runs**

```bash
cd site && npm run dev
```

Open in browser — should see header with nav, "Dashboard" placeholder. Click Browse, Campaigns links — routing should work.

- [ ] **Step 8: Commit**

```bash
git add site/
echo "site/node_modules/" >> .gitignore
echo "site/public/data/*.json" >> .gitignore
git add .gitignore
git commit -m "feat: scaffold Svelte app with routing and header"
```

---

### Task 3: Data Layer (api.js, utils.js, stores.js)

**Files:**
- Create: `site/src/lib/api.js`
- Create: `site/src/lib/utils.js`
- Create: `site/src/lib/stores.js`
- Create: `site/src/lib/search.js`

- [ ] **Step 1: Create `site/src/lib/utils.js`**

```javascript
const SITE_BASE_URL = 'https://dangerouspress.org'

export const ISSUE_LABELS = {
  anti_lynching: 'Anti-Lynching',
  segregation_public: 'Segregation',
  education: 'Education',
  voting_rights: 'Voting Rights',
  labor: 'Labor',
  criminal_justice: 'Criminal Justice',
  military: 'Military',
  government_discrimination: "Gov't Discrimination",
  housing: 'Housing',
  healthcare: 'Healthcare',
  cultural_media: 'Cultural/Media',
  civil_rights_organizing: 'Civil Rights Org.',
  pan_african: 'Pan-African',
  womens_organizing: "Women's Organizing",
  migration: 'Migration',
}

export const ISSUE_COLORS = {
  anti_lynching: '#c0392b',
  segregation_public: '#2980b9',
  education: '#27ae60',
  voting_rights: '#8e44ad',
  labor: '#d35400',
  criminal_justice: '#2c3e50',
  military: '#16a085',
  government_discrimination: '#7f8c8d',
  housing: '#f39c12',
  healthcare: '#1abc9c',
  cultural_media: '#e74c3c',
  civil_rights_organizing: '#3498db',
  pan_african: '#9b59b6',
  womens_organizing: '#e67e22',
  migration: '#95a5a6',
}

export function makeViewerUrl(paper, date, page, chunkIdx) {
  let url = `${SITE_BASE_URL}/?paper=${paper}&date=${date}&page=${page}`
  if (chunkIdx != null) {
    url += `#chunk-${chunkIdx}`
  }
  return url
}

export function formatPaperName(slug) {
  return slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export function formatLocation(city, state) {
  if (city && state) return `${city}, ${state}`
  if (state) return state
  if (city) return city
  return null
}
```

- [ ] **Step 2: Create `site/src/lib/api.js`**

```javascript
let eventsCache = null
let campaignsCache = null
let metaCache = null

export async function loadEvents() {
  if (!eventsCache) {
    const res = await fetch('./data/events.json')
    eventsCache = await res.json()
  }
  return eventsCache
}

export async function loadEvent(id) {
  const events = await loadEvents()
  return events.find(e => e.id === Number(id)) || null
}

export async function loadCampaigns() {
  if (!campaignsCache) {
    const res = await fetch('./data/campaigns.json')
    campaignsCache = await res.json()
  }
  return campaignsCache
}

export async function loadCampaign(id) {
  const campaigns = await loadCampaigns()
  return campaigns.find(c => c.id === Number(id)) || null
}

export async function loadMeta() {
  if (!metaCache) {
    const res = await fetch('./data/meta.json')
    metaCache = await res.json()
  }
  return metaCache
}
```

- [ ] **Step 3: Create `site/src/lib/stores.js`**

```javascript
import { writable } from 'svelte/store'

// Active filters for the browse view
export const filters = writable({
  issues: [],
  papers: [],
  dateRange: [1905, 1929],
  tactics: [],
  actorType: '',
  searchText: '',
})

export function resetFilters() {
  filters.set({
    issues: [],
    papers: [],
    dateRange: [1905, 1929],
    tactics: [],
    actorType: '',
    searchText: '',
  })
}
```

- [ ] **Step 4: Create `site/src/lib/search.js`**

```javascript
import Fuse from 'fuse.js'

let fuseInstance = null

export function buildSearchIndex(events) {
  fuseInstance = new Fuse(events, {
    keys: [
      { name: 'description', weight: 3 },
      { name: 'organizations', weight: 2 },
      { name: 'individuals', weight: 2 },
      { name: 'target', weight: 1 },
    ],
    threshold: 0.3,
    includeScore: true,
  })
  return fuseInstance
}

export function searchEvents(query) {
  if (!fuseInstance || !query.trim()) return null
  return fuseInstance.search(query).map(r => r.item)
}
```

- [ ] **Step 5: Commit**

```bash
git add site/src/lib/
git commit -m "feat: add data layer — api, search, stores, utils"
```

---

## Chunk 2: Shared Components

### Task 4: Badge and StatCard Components

**Files:**
- Create: `site/src/components/Badge.svelte`
- Create: `site/src/components/StatCard.svelte`

- [ ] **Step 1: Create `site/src/components/Badge.svelte`**

```svelte
<script>
  import { ISSUE_LABELS, ISSUE_COLORS } from '../lib/utils.js'

  export let type = 'issue'  // 'issue', 'event_type', 'campaign', 'tactic'
  export let value = ''

  $: label = type === 'issue' ? (ISSUE_LABELS[value] || value) : value
  $: color = type === 'issue' ? (ISSUE_COLORS[value] || '#666') : null
</script>

{#if value}
  <span
    class="badge badge-{type}"
    style={color ? `--badge-color: ${color}` : ''}
  >
    {label}
  </span>
{/if}

<style>
  .badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 3px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    white-space: nowrap;
  }
  .badge-issue {
    background: color-mix(in srgb, var(--badge-color) 15%, white);
    color: var(--badge-color);
  }
  .badge-event_type {
    background: #f0f0f0;
    color: #444;
  }
  .badge-campaign {
    background: #eee8f5;
    color: #5a3d8a;
  }
  .badge-tactic {
    background: #e8f4e8;
    color: #2d6a2d;
  }
</style>
```

- [ ] **Step 2: Create `site/src/components/StatCard.svelte`**

```svelte
<script>
  export let label = ''
  export let value = 0
  export let format = 'number'  // 'number' or 'text'

  $: display = format === 'number' ? value.toLocaleString() : value
</script>

<div class="stat-card">
  <div class="value">{display}</div>
  <div class="label">{label}</div>
</div>

<style>
  .stat-card {
    background: white;
    border-radius: 8px;
    padding: 24px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  .value {
    font-size: 2.2rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1;
    color: #1a1a1a;
  }
  .label {
    font-size: 0.85rem;
    color: #888;
    margin-top: 6px;
    font-weight: 500;
  }
</style>
```

- [ ] **Step 3: Commit**

```bash
git add site/src/components/Badge.svelte site/src/components/StatCard.svelte
git commit -m "feat: add Badge and StatCard components"
```

---

### Task 5: SourceBlock and EventCard Components

**Files:**
- Create: `site/src/components/SourceBlock.svelte`
- Create: `site/src/components/EventCard.svelte`
- Create: `site/src/components/Pagination.svelte`

- [ ] **Step 1: Create `site/src/components/SourceBlock.svelte`**

Displays one newspaper source with its OCR text and dangerouspress.org link.

```svelte
<script>
  import { makeViewerUrl, formatPaperName } from '../lib/utils.js'

  export let source  // { paper, date, page, chunk_idx, source_text, role }
</script>

<div class="source-block">
  <div class="source-header">
    <a href={makeViewerUrl(source.paper, source.date, source.page, source.chunk_idx)}
       target="_blank" rel="noopener" class="source-link">
      {formatPaperName(source.paper)}
    </a>
    <span class="source-meta">
      {source.date} &middot; p. {source.page}
      {#if source.role === 'duplicate'}
        <span class="role-badge">additional coverage</span>
      {/if}
    </span>
  </div>
  {#if source.source_text}
    <blockquote class="ocr-text">{source.source_text}</blockquote>
  {/if}
</div>

<style>
  .source-block {
    border-left: 3px solid #ddd;
    padding-left: 16px;
    margin-bottom: 20px;
  }
  .source-header {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }
  .source-link {
    font-weight: 700;
    color: #1a1a1a;
    text-decoration: none;
    font-size: 0.95rem;
  }
  .source-link:hover {
    text-decoration: underline;
  }
  .source-meta {
    font-size: 0.8rem;
    color: #888;
  }
  .role-badge {
    background: #f0f0f0;
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 0.7rem;
    color: #666;
    margin-left: 4px;
  }
  .ocr-text {
    margin: 0;
    padding: 12px 16px;
    background: #f8f8f6;
    border-radius: 4px;
    font-size: 0.85rem;
    line-height: 1.7;
    color: #333;
    font-family: 'Georgia', serif;
    white-space: pre-wrap;
  }
</style>
```

- [ ] **Step 2: Create `site/src/components/EventCard.svelte`**

```svelte
<script>
  import { link } from 'svelte-routing'
  import Badge from './Badge.svelte'
  import { formatPaperName, formatLocation } from '../lib/utils.js'

  export let event

  $: location = formatLocation(event.location_city, event.location_state)
  $: sourceCount = event.sources?.length || 0
</script>

<a href="/events/{event.id}" use:link class="event-card">
  <div class="card-top">
    <span class="date">{event.date}</span>
    <div class="badges">
      <Badge type="event_type" value={event.event_type} />
      <Badge type="issue" value={event.issue_primary} />
    </div>
  </div>

  <p class="description">{event.description}</p>

  <div class="card-bottom">
    {#if location}
      <span class="meta">{location}</span>
    {/if}
    {#if sourceCount > 1}
      <span class="meta">{sourceCount} sources</span>
    {:else if event.sources?.[0]}
      <span class="meta">{formatPaperName(event.sources[0].paper)}</span>
    {/if}
    {#if event.campaign_ids?.length > 0}
      <Badge type="campaign" value="Campaign" />
    {/if}
  </div>
</a>

<style>
  .event-card {
    display: block;
    background: white;
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    text-decoration: none;
    color: inherit;
    transition: box-shadow 0.15s;
  }
  .event-card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.12);
  }
  .card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .date {
    font-size: 0.8rem;
    color: #888;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .badges {
    display: flex;
    gap: 6px;
  }
  .description {
    font-size: 0.95rem;
    font-weight: 600;
    line-height: 1.4;
    margin: 0 0 12px;
    color: #1a1a1a;
  }
  .card-bottom {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
  }
  .meta {
    font-size: 0.8rem;
    color: #888;
  }
</style>
```

- [ ] **Step 3: Create `site/src/components/Pagination.svelte`**

```svelte
<script>
  export let currentPage = 1
  export let totalPages = 1
  import { createEventDispatcher } from 'svelte'

  const dispatch = createEventDispatcher()

  function goTo(page) {
    if (page >= 1 && page <= totalPages) {
      dispatch('page', page)
    }
  }

  $: pages = Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
    if (totalPages <= 7) return i + 1
    if (currentPage <= 4) return i + 1
    if (currentPage >= totalPages - 3) return totalPages - 6 + i
    return currentPage - 3 + i
  })
</script>

{#if totalPages > 1}
  <nav class="pagination">
    <button on:click={() => goTo(currentPage - 1)} disabled={currentPage === 1}>
      Prev
    </button>
    {#each pages as p}
      <button class:active={p === currentPage} on:click={() => goTo(p)}>
        {p}
      </button>
    {/each}
    <button on:click={() => goTo(currentPage + 1)} disabled={currentPage === totalPages}>
      Next
    </button>
  </nav>
{/if}

<style>
  .pagination {
    display: flex;
    gap: 4px;
    justify-content: center;
    margin: 32px 0;
  }
  button {
    padding: 8px 14px;
    border: 1px solid #ddd;
    background: white;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.85rem;
  }
  button:hover:not(:disabled) {
    background: #f5f5f5;
  }
  button:disabled {
    opacity: 0.4;
    cursor: default;
  }
  button.active {
    background: #1a1a1a;
    color: white;
    border-color: #1a1a1a;
  }
</style>
```

- [ ] **Step 4: Commit**

```bash
git add site/src/components/SourceBlock.svelte site/src/components/EventCard.svelte site/src/components/Pagination.svelte
git commit -m "feat: add SourceBlock, EventCard, and Pagination components"
```

---

## Chunk 3: Dashboard View

### Task 6: IssueChart Component

**Files:**
- Create: `site/src/components/IssueChart.svelte`

- [ ] **Step 1: Create `site/src/components/IssueChart.svelte`**

Horizontal bar chart showing event counts by issue category.

```svelte
<script>
  import { ISSUE_LABELS, ISSUE_COLORS } from '../lib/utils.js'

  export let issueCounts = {}

  $: sorted = Object.entries(issueCounts)
    .sort((a, b) => b[1] - a[1])
  $: maxCount = sorted.length > 0 ? sorted[0][1] : 1
</script>

<div class="chart">
  {#each sorted as [code, count]}
    <div class="bar-row">
      <span class="bar-label">{ISSUE_LABELS[code] || code}</span>
      <div class="bar-track">
        <div
          class="bar-fill"
          style="width: {(count / maxCount) * 100}%; background: {ISSUE_COLORS[code] || '#666'}"
        ></div>
      </div>
      <span class="bar-count">{count.toLocaleString()}</span>
    </div>
  {/each}
</div>

<style>
  .chart {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .bar-row {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .bar-label {
    font-size: 0.8rem;
    font-weight: 500;
    width: 140px;
    text-align: right;
    flex-shrink: 0;
    color: #555;
  }
  .bar-track {
    flex: 1;
    height: 20px;
    background: #f0f0f0;
    border-radius: 3px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease;
  }
  .bar-count {
    font-size: 0.8rem;
    font-weight: 600;
    width: 48px;
    color: #666;
    font-variant-numeric: tabular-nums;
  }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add site/src/components/IssueChart.svelte
git commit -m "feat: add IssueChart bar chart component"
```

---

### Task 7: Dashboard Route

**Files:**
- Modify: `site/src/routes/Dashboard.svelte`

- [ ] **Step 1: Implement Dashboard**

```svelte
<script>
  import { onMount } from 'svelte'
  import { link } from 'svelte-routing'
  import { loadMeta, loadCampaigns } from '../lib/api.js'
  import StatCard from '../components/StatCard.svelte'
  import IssueChart from '../components/IssueChart.svelte'

  let meta = null
  let topCampaigns = []

  onMount(async () => {
    meta = await loadMeta()
    const campaigns = await loadCampaigns()
    topCampaigns = campaigns
      .filter(c => c.named)
      .sort((a, b) => b.event_count - a.event_count)
      .slice(0, 15)
  })
</script>

<div class="dashboard">
  <section class="hero">
    <h1>Protest Events in the African American Press</h1>
    <p class="subtitle">1905&ndash;1929 &middot; Extracted from OCR text of 37 newspapers via semantic search and LLM classification</p>
    <div class="hero-actions">
      <a href="/events" use:link class="btn btn-primary">Browse Events</a>
      <a href="/campaigns" use:link class="btn btn-secondary">View Campaigns</a>
    </div>
  </section>

  {#if meta}
    <section class="stats">
      <StatCard label="Protest Events" value={meta.total_events} />
      <StatCard label="Campaigns" value={meta.total_campaigns} />
      <StatCard label="Newspapers" value={meta.total_newspapers} />
      <StatCard label="Date Range" value="{meta.date_range[0]?.slice(0,4)}–{meta.date_range[1]?.slice(0,4)}" format="text" />
    </section>

    <section class="two-col">
      <div>
        <h2>Events by Issue</h2>
        <IssueChart issueCounts={meta.issue_counts} />
      </div>

      <div>
        <h2>Top Campaigns</h2>
        <div class="campaign-list">
          {#each topCampaigns as c}
            <a href="/campaigns/{c.id}" use:link class="campaign-row">
              <span class="campaign-name">{c.name}</span>
              <span class="campaign-count">{c.event_count} events</span>
            </a>
          {/each}
        </div>
      </div>
    </section>
  {:else}
    <p>Loading...</p>
  {/if}
</div>

<style>
  .dashboard {
    padding-top: 24px;
  }
  .hero {
    text-align: center;
    padding: 48px 0 40px;
  }
  h1 {
    font-size: 2.4rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1.1;
    margin-bottom: 12px;
  }
  .subtitle {
    color: #666;
    font-size: 1rem;
    margin-bottom: 24px;
  }
  .hero-actions {
    display: flex;
    gap: 12px;
    justify-content: center;
  }
  .btn {
    padding: 10px 24px;
    border-radius: 6px;
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
  }
  .btn-primary {
    background: #1a1a1a;
    color: white;
  }
  .btn-primary:hover { background: #333; }
  .btn-secondary {
    background: #f0f0f0;
    color: #1a1a1a;
  }
  .btn-secondary:hover { background: #e5e5e5; }

  .stats {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 48px;
  }

  .two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 48px;
  }
  h2 {
    font-size: 1.2rem;
    font-weight: 700;
    margin-bottom: 20px;
  }
  .campaign-list {
    display: flex;
    flex-direction: column;
  }
  .campaign-row {
    display: flex;
    justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid #eee;
    text-decoration: none;
    color: inherit;
  }
  .campaign-row:hover { background: #fafafa; }
  .campaign-name {
    font-weight: 500;
    font-size: 0.9rem;
  }
  .campaign-count {
    color: #888;
    font-size: 0.8rem;
    font-variant-numeric: tabular-nums;
  }

  @media (max-width: 768px) {
    .stats { grid-template-columns: repeat(2, 1fr); }
    .two-col { grid-template-columns: 1fr; }
    h1 { font-size: 1.8rem; }
  }
</style>
```

- [ ] **Step 2: Verify in browser**

```bash
cd site && npm run dev
```

Open browser — Dashboard should show stats, issue chart, top campaigns.

- [ ] **Step 3: Commit**

```bash
git add site/src/routes/Dashboard.svelte
git commit -m "feat: implement Dashboard with stats, issues chart, top campaigns"
```

---

## Chunk 4: Browse / Search View

### Task 8: FacetSidebar Component

**Files:**
- Create: `site/src/components/FacetSidebar.svelte`

- [ ] **Step 1: Create `site/src/components/FacetSidebar.svelte`**

```svelte
<script>
  import { ISSUE_LABELS, ISSUE_COLORS } from '../lib/utils.js'
  import { filters, resetFilters } from '../lib/stores.js'

  export let availableIssues = []
  export let availableTactics = []
  export let availablePapers = []

  function toggleIssue(code) {
    filters.update(f => ({
      ...f,
      issues: f.issues.includes(code)
        ? f.issues.filter(i => i !== code)
        : [...f.issues, code]
    }))
  }

  function toggleTactic(t) {
    filters.update(f => ({
      ...f,
      tactics: f.tactics.includes(t)
        ? f.tactics.filter(x => x !== t)
        : [...f.tactics, t]
    }))
  }

  function setPaper(e) {
    filters.update(f => ({
      ...f,
      papers: e.target.value ? [e.target.value] : []
    }))
  }

  function setActorType(e) {
    filters.update(f => ({ ...f, actorType: e.target.value }))
  }

  $: hasFilters = $filters.issues.length > 0 ||
    $filters.papers.length > 0 ||
    $filters.tactics.length > 0 ||
    $filters.actorType !== '' ||
    $filters.searchText !== ''
</script>

<aside class="sidebar">
  {#if hasFilters}
    <button class="clear-btn" on:click={resetFilters}>Clear all filters</button>
  {/if}

  <div class="facet-group">
    <h3>Issue</h3>
    {#each availableIssues as code}
      <label class="checkbox-label">
        <input
          type="checkbox"
          checked={$filters.issues.includes(code)}
          on:change={() => toggleIssue(code)}
        />
        <span class="color-dot" style="background: {ISSUE_COLORS[code] || '#666'}"></span>
        {ISSUE_LABELS[code] || code}
      </label>
    {/each}
  </div>

  <div class="facet-group">
    <h3>Newspaper</h3>
    <select on:change={setPaper} value={$filters.papers[0] || ''}>
      <option value="">All newspapers</option>
      {#each availablePapers as p}
        <option value={p.slug}>{p.name}</option>
      {/each}
    </select>
  </div>

  <div class="facet-group">
    <h3>Actor Type</h3>
    <select on:change={setActorType} value={$filters.actorType}>
      <option value="">All</option>
      <option value="black_protest">Black protest</option>
      <option value="anti_black">Anti-Black</option>
      <option value="mixed">Mixed</option>
    </select>
  </div>

  <div class="facet-group">
    <h3>Tactics</h3>
    {#each availableTactics.slice(0, 10) as t}
      <label class="checkbox-label">
        <input
          type="checkbox"
          checked={$filters.tactics.includes(t)}
          on:change={() => toggleTactic(t)}
        />
        {t.replace(/_/g, ' ')}
      </label>
    {/each}
  </div>
</aside>

<style>
  .sidebar {
    width: 240px;
    flex-shrink: 0;
  }
  .facet-group {
    margin-bottom: 24px;
  }
  h3 {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #888;
    margin-bottom: 8px;
    font-weight: 600;
  }
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.85rem;
    padding: 3px 0;
    cursor: pointer;
  }
  .color-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  select {
    width: 100%;
    padding: 6px 8px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 0.85rem;
    background: white;
  }
  .clear-btn {
    width: 100%;
    padding: 8px;
    background: none;
    border: 1px solid #ddd;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.8rem;
    color: #888;
    margin-bottom: 16px;
  }
  .clear-btn:hover {
    background: #f5f5f5;
    color: #1a1a1a;
  }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add site/src/components/FacetSidebar.svelte
git commit -m "feat: add FacetSidebar with issue, paper, tactic, and actor filters"
```

---

### Task 9: EventList (Browse/Search) Route

**Files:**
- Modify: `site/src/routes/EventList.svelte`

- [ ] **Step 1: Implement EventList**

```svelte
<script>
  import { onMount } from 'svelte'
  import { loadEvents, loadMeta } from '../lib/api.js'
  import { buildSearchIndex, searchEvents } from '../lib/search.js'
  import { filters } from '../lib/stores.js'
  import EventCard from '../components/EventCard.svelte'
  import FacetSidebar from '../components/FacetSidebar.svelte'
  import Pagination from '../components/Pagination.svelte'

  let allEvents = []
  let meta = null
  let currentPage = 1
  const perPage = 50

  onMount(async () => {
    allEvents = await loadEvents()
    meta = await loadMeta()
    buildSearchIndex(allEvents)
  })

  $: availableIssues = [...new Set(allEvents.map(e => e.issue_primary).filter(Boolean))].sort()
  $: availableTactics = [...new Set(allEvents.flatMap(e => e.tactics || []))].sort()
  $: availablePapers = meta?.newspaper_list || []

  $: filtered = (() => {
    let result = allEvents

    // Text search
    if ($filters.searchText) {
      const searched = searchEvents($filters.searchText)
      if (searched) result = searched
    }

    // Issue filter
    if ($filters.issues.length > 0) {
      result = result.filter(e => $filters.issues.includes(e.issue_primary))
    }

    // Paper filter
    if ($filters.papers.length > 0) {
      result = result.filter(e =>
        e.sources?.some(s => $filters.papers.includes(s.paper))
      )
    }

    // Actor type
    if ($filters.actorType) {
      result = result.filter(e => e.actor_type === $filters.actorType)
    }

    // Tactics
    if ($filters.tactics.length > 0) {
      result = result.filter(e =>
        e.tactics?.some(t => $filters.tactics.includes(t))
      )
    }

    return result
  })()

  $: totalPages = Math.ceil(filtered.length / perPage)
  $: pageEvents = filtered.slice((currentPage - 1) * perPage, currentPage * perPage)

  // Reset to page 1 when filters change
  $: if ($filters) currentPage = 1

  function handleSearch(e) {
    filters.update(f => ({ ...f, searchText: e.target.value }))
  }
</script>

<div class="browse">
  <FacetSidebar {availableIssues} {availableTactics} {availablePapers} />

  <div class="results">
    <div class="search-bar">
      <input
        type="text"
        placeholder="Search events..."
        value={$filters.searchText}
        on:input={handleSearch}
        class="search-input"
      />
      <span class="result-count">{filtered.length.toLocaleString()} events</span>
    </div>

    <div class="event-grid">
      {#each pageEvents as event (event.id)}
        <EventCard {event} />
      {/each}
    </div>

    {#if filtered.length === 0}
      <p class="no-results">No events match your filters.</p>
    {/if}

    <Pagination {currentPage} {totalPages} on:page={e => currentPage = e.detail} />
  </div>
</div>

<style>
  .browse {
    display: flex;
    gap: 32px;
    padding-top: 24px;
  }
  .results {
    flex: 1;
    min-width: 0;
  }
  .search-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 20px;
  }
  .search-input {
    flex: 1;
    padding: 10px 16px;
    border: 1px solid #ddd;
    border-radius: 6px;
    font-size: 0.95rem;
    background: white;
  }
  .search-input:focus {
    outline: none;
    border-color: #1a1a1a;
  }
  .result-count {
    font-size: 0.85rem;
    color: #888;
    white-space: nowrap;
    font-weight: 500;
  }
  .event-grid {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .no-results {
    text-align: center;
    color: #888;
    padding: 48px 0;
  }

  @media (max-width: 768px) {
    .browse { flex-direction: column; }
  }
</style>
```

- [ ] **Step 2: Verify in browser**

Navigate to `/events`. Should show faceted sidebar, search, paginated event cards.

- [ ] **Step 3: Commit**

```bash
git add site/src/routes/EventList.svelte
git commit -m "feat: implement Browse/Search view with faceted filtering and pagination"
```

---

## Chunk 5: Event Detail + Campaign Views

### Task 10: Event Detail Route

**Files:**
- Modify: `site/src/routes/EventPage.svelte`

- [ ] **Step 1: Implement EventPage**

```svelte
<script>
  import { onMount } from 'svelte'
  import { link } from 'svelte-routing'
  import { loadEvent, loadCampaigns, loadEvents } from '../lib/api.js'
  import Badge from '../components/Badge.svelte'
  import SourceBlock from '../components/SourceBlock.svelte'
  import EventCard from '../components/EventCard.svelte'
  import { formatLocation } from '../lib/utils.js'

  export let id

  let event = null
  let campaigns = []
  let relatedEvents = []

  onMount(load)
  $: if (id) load()

  async function load() {
    event = await loadEvent(id)
    if (!event) return

    if (event.campaign_ids?.length > 0) {
      const allCampaigns = await loadCampaigns()
      campaigns = allCampaigns.filter(c => event.campaign_ids.includes(c.id))

      // Related events from same campaigns
      const allEvents = await loadEvents()
      const relatedIds = new Set()
      for (const c of campaigns) {
        for (const eid of c.event_ids) {
          if (eid !== event.id) relatedIds.add(eid)
        }
      }
      relatedEvents = allEvents
        .filter(e => relatedIds.has(e.id))
        .sort((a, b) => a.date.localeCompare(b.date))
        .slice(0, 10)
    }
  }

  $: location = event ? formatLocation(event.location_city, event.location_state) : null
</script>

{#if event}
  <article class="event-page">
    <header>
      <div class="meta-row">
        <span class="date">{event.date}</span>
        <Badge type="event_type" value={event.event_type} />
        <Badge type="issue" value={event.issue_primary} />
        {#if event.issue_secondary}
          <Badge type="issue" value={event.issue_secondary} />
        {/if}
      </div>
      <h1>{event.description}</h1>
    </header>

    <div class="two-col">
      <div class="details">
        <h2>Details</h2>
        <dl>
          {#if location}
            <dt>Location</dt><dd>{location}</dd>
          {/if}
          {#if event.organizations?.length > 0}
            <dt>Organizations</dt><dd>{event.organizations.join(', ')}</dd>
          {/if}
          {#if event.individuals?.length > 0}
            <dt>Individuals</dt><dd>{event.individuals.join(', ')}</dd>
          {/if}
          {#if event.target}
            <dt>Target</dt><dd>{event.target}</dd>
          {/if}
          {#if event.tactics?.length > 0}
            <dt>Tactics</dt>
            <dd>
              {#each event.tactics as t}
                <Badge type="tactic" value={t.replace(/_/g, ' ')} />
              {/each}
            </dd>
          {/if}
          {#if event.size_text}
            <dt>Size</dt><dd>{event.size_text}</dd>
          {/if}
          {#if event.actor_type}
            <dt>Actor type</dt><dd>{event.actor_type.replace(/_/g, ' ')}</dd>
          {/if}
        </dl>

        {#if campaigns.length > 0}
          <h3>Campaigns</h3>
          {#each campaigns as c}
            <a href="/campaigns/{c.id}" use:link class="campaign-link">
              {c.name}
            </a>
          {/each}
        {/if}
      </div>

      <div class="sources-col">
        <h2>Source Articles ({event.sources?.length || 0})</h2>
        {#each event.sources || [] as source}
          <SourceBlock {source} />
        {/each}
      </div>
    </div>

    {#if relatedEvents.length > 0}
      <section class="related">
        <h2>Related Events</h2>
        <div class="related-grid">
          {#each relatedEvents as re (re.id)}
            <EventCard event={re} />
          {/each}
        </div>
      </section>
    {/if}
  </article>
{:else}
  <p>Loading...</p>
{/if}

<style>
  .event-page {
    padding-top: 32px;
  }
  header {
    margin-bottom: 32px;
  }
  .meta-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }
  .date {
    font-size: 0.85rem;
    color: #888;
    font-weight: 600;
  }
  h1 {
    font-size: 1.8rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 1.2;
  }
  .two-col {
    display: grid;
    grid-template-columns: 320px 1fr;
    gap: 48px;
  }
  h2 {
    font-size: 1rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #888;
    margin-bottom: 16px;
  }
  h3 {
    font-size: 0.9rem;
    font-weight: 700;
    margin: 20px 0 8px;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px 16px;
    font-size: 0.9rem;
  }
  dt {
    font-weight: 600;
    color: #888;
    white-space: nowrap;
  }
  dd {
    margin: 0;
  }
  .campaign-link {
    display: inline-block;
    padding: 4px 12px;
    background: #eee8f5;
    color: #5a3d8a;
    border-radius: 4px;
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 600;
    margin-right: 8px;
  }
  .campaign-link:hover { background: #ddd0ee; }

  .related {
    margin-top: 48px;
    padding-top: 32px;
    border-top: 1px solid #eee;
  }
  .related-grid {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  @media (max-width: 768px) {
    .two-col { grid-template-columns: 1fr; }
  }
</style>
```

- [ ] **Step 2: Verify in browser**

Click an event card from the browse view. Should show full details, all source texts with dangerouspress links, and related events.

- [ ] **Step 3: Commit**

```bash
git add site/src/routes/EventPage.svelte
git commit -m "feat: implement Event Detail page with sources and related events"
```

---

### Task 11: Campaign List and Detail Routes

**Files:**
- Modify: `site/src/routes/CampaignList.svelte`
- Modify: `site/src/routes/CampaignPage.svelte`

- [ ] **Step 1: Implement CampaignList**

```svelte
<script>
  import { onMount } from 'svelte'
  import { link } from 'svelte-routing'
  import { loadCampaigns } from '../lib/api.js'
  import Badge from '../components/Badge.svelte'

  let campaigns = []
  let sortBy = 'event_count'
  let sortAsc = false
  let filterNamed = ''
  let searchText = ''

  onMount(async () => {
    campaigns = await loadCampaigns()
  })

  $: filtered = campaigns
    .filter(c => {
      if (filterNamed === 'named' && !c.named) return false
      if (filterNamed === 'algorithmic' && c.named) return false
      if (searchText && !c.name.toLowerCase().includes(searchText.toLowerCase())) return false
      return true
    })
    .sort((a, b) => {
      let va = a[sortBy], vb = b[sortBy]
      if (typeof va === 'string') va = va || '', vb = vb || ''
      if (sortAsc) return va > vb ? 1 : -1
      return va < vb ? 1 : -1
    })

  function sort(col) {
    if (sortBy === col) sortAsc = !sortAsc
    else { sortBy = col; sortAsc = false }
  }
</script>

<div class="campaign-list-page">
  <h1>Campaigns</h1>
  <p class="subtitle">{campaigns.length} campaigns grouping related protest events</p>

  <div class="controls">
    <input type="text" placeholder="Search campaigns..." bind:value={searchText} class="search" />
    <select bind:value={filterNamed}>
      <option value="">All campaigns</option>
      <option value="named">Named only</option>
      <option value="algorithmic">Algorithmic only</option>
    </select>
  </div>

  <table>
    <thead>
      <tr>
        <th on:click={() => sort('name')} class="sortable">Campaign</th>
        <th on:click={() => sort('event_count')} class="sortable num">Events</th>
        <th on:click={() => sort('issue_primary')} class="sortable">Issue</th>
        <th on:click={() => sort('date_start')} class="sortable">Date Range</th>
      </tr>
    </thead>
    <tbody>
      {#each filtered as c (c.id)}
        <tr>
          <td>
            <a href="/campaigns/{c.id}" use:link class="name-link">{c.name}</a>
            {#if !c.named}<span class="algo-tag">auto</span>{/if}
          </td>
          <td class="num">{c.event_count}</td>
          <td><Badge type="issue" value={c.issue_primary} /></td>
          <td class="dates">{c.date_start || '?'} &mdash; {c.date_end || '?'}</td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .campaign-list-page { padding-top: 24px; }
  h1 { font-size: 1.8rem; font-weight: 800; margin-bottom: 4px; }
  .subtitle { color: #888; margin-bottom: 24px; }
  .controls {
    display: flex; gap: 12px; margin-bottom: 20px;
  }
  .search {
    flex: 1; padding: 8px 12px; border: 1px solid #ddd;
    border-radius: 6px; font-size: 0.9rem;
  }
  select {
    padding: 8px 12px; border: 1px solid #ddd;
    border-radius: 6px; font-size: 0.85rem; background: white;
  }
  table { width: 100%; border-collapse: collapse; background: white;
    border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  th {
    text-align: left; padding: 10px 14px; font-size: 0.8rem;
    text-transform: uppercase; letter-spacing: 0.04em; color: #888;
    border-bottom: 2px solid #eee; font-weight: 600;
  }
  th.sortable { cursor: pointer; }
  th.sortable:hover { color: #1a1a1a; }
  td { padding: 10px 14px; border-bottom: 1px solid #f0f0f0; font-size: 0.9rem; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .name-link { color: #1a1a1a; font-weight: 600; text-decoration: none; }
  .name-link:hover { text-decoration: underline; }
  .algo-tag {
    font-size: 0.65rem; background: #f0f0f0; padding: 1px 5px;
    border-radius: 3px; color: #888; margin-left: 6px;
  }
  .dates { font-size: 0.8rem; color: #888; white-space: nowrap; }
</style>
```

- [ ] **Step 2: Implement CampaignPage**

```svelte
<script>
  import { onMount } from 'svelte'
  import { loadCampaign, loadEvents } from '../lib/api.js'
  import Badge from '../components/Badge.svelte'
  import EventCard from '../components/EventCard.svelte'
  import { formatPaperName } from '../lib/utils.js'

  export let id

  let campaign = null
  let events = []

  onMount(load)
  $: if (id) load()

  async function load() {
    campaign = await loadCampaign(id)
    if (!campaign) return

    const allEvents = await loadEvents()
    const idSet = new Set(campaign.event_ids)
    events = allEvents
      .filter(e => idSet.has(e.id))
      .sort((a, b) => a.date.localeCompare(b.date))
  }

  $: papers = [...new Set(events.flatMap(e => (e.sources || []).map(s => s.paper)))]
  $: orgs = [...new Set(events.flatMap(e => e.organizations || []))]
  $: individuals = [...new Set(events.flatMap(e => e.individuals || []))]
</script>

{#if campaign}
  <div class="campaign-page">
    <header>
      <Badge type="issue" value={campaign.issue_primary} />
      {#if !campaign.named}<span class="algo-tag">algorithmically detected</span>{/if}
      <h1>{campaign.name}</h1>
      <p class="date-range">{campaign.date_start} &mdash; {campaign.date_end} &middot; {events.length} events</p>
    </header>

    <div class="sidebar-layout">
      <aside>
        {#if papers.length > 0}
          <h3>Newspapers ({papers.length})</h3>
          <ul>
            {#each papers as p}
              <li>{formatPaperName(p)}</li>
            {/each}
          </ul>
        {/if}
        {#if orgs.length > 0}
          <h3>Organizations</h3>
          <ul>
            {#each orgs.slice(0, 15) as o}
              <li>{o}</li>
            {/each}
            {#if orgs.length > 15}<li class="more">+{orgs.length - 15} more</li>{/if}
          </ul>
        {/if}
        {#if individuals.length > 0}
          <h3>Individuals</h3>
          <ul>
            {#each individuals.slice(0, 15) as i}
              <li>{i}</li>
            {/each}
            {#if individuals.length > 15}<li class="more">+{individuals.length - 15} more</li>{/if}
          </ul>
        {/if}
      </aside>

      <div class="events-col">
        <h2>Events</h2>
        {#each events as event (event.id)}
          <EventCard {event} />
        {/each}
      </div>
    </div>
  </div>
{:else}
  <p>Loading...</p>
{/if}

<style>
  .campaign-page { padding-top: 32px; }
  header { margin-bottom: 32px; }
  h1 { font-size: 1.8rem; font-weight: 800; margin: 8px 0 4px; }
  .date-range { color: #888; font-size: 0.9rem; }
  .algo-tag {
    font-size: 0.7rem; background: #f0f0f0; padding: 2px 8px;
    border-radius: 3px; color: #888;
  }
  .sidebar-layout {
    display: grid; grid-template-columns: 240px 1fr; gap: 48px;
  }
  aside h3 {
    font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em;
    color: #888; margin: 20px 0 8px; font-weight: 600;
  }
  aside h3:first-child { margin-top: 0; }
  ul { list-style: none; padding: 0; }
  li { font-size: 0.85rem; padding: 3px 0; }
  .more { color: #888; font-style: italic; }
  h2 {
    font-size: 1rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.04em; color: #888; margin-bottom: 16px;
  }
  .events-col { display: flex; flex-direction: column; gap: 12px; }

  @media (max-width: 768px) {
    .sidebar-layout { grid-template-columns: 1fr; }
  }
</style>
```

- [ ] **Step 3: Verify in browser**

Navigate to `/campaigns`, click a campaign — should show events, newspapers, orgs.

- [ ] **Step 4: Commit**

```bash
git add site/src/routes/CampaignList.svelte site/src/routes/CampaignPage.svelte
git commit -m "feat: implement Campaign list and detail pages"
```

---

## Chunk 6: Polish and Integration

### Task 12: Final Polish

**Files:**
- Modify: `site/index.html` — add Inter font
- Modify: `site/src/App.svelte` — ensure global styles
- Create: `site/public/data/.gitkeep`

- [ ] **Step 1: Update `site/index.html` to load Inter font**

Add to `<head>`:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Create `site/public/data/.gitkeep`**

```bash
touch site/public/data/.gitkeep
```

- [ ] **Step 3: Full end-to-end test**

```bash
# Generate JSON data
uv run report.py --json

# Run dev server
cd site && npm run dev
```

Verify:
1. Dashboard loads with stats and charts
2. Browse view filters and searches work
3. Event detail shows all source texts with dangerouspress links
4. Campaign pages show events and metadata
5. All navigation links work

- [ ] **Step 4: Build for production**

```bash
cd site && npm run build
```

Verify `site/dist/` contains the built app.

- [ ] **Step 5: Final commit**

```bash
git add site/ .gitignore
git commit -m "feat: complete Protest Events Explorer — dashboard, browse, events, campaigns"
```
