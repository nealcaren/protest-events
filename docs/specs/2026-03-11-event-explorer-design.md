# Protest Events Explorer — Design Spec

**Date:** 2026-03-11
**Goal:** A modern, editorial-style client-side web app for browsing 7,600+ protest events from African American newspapers (1905-1929).

---

## Tech Stack

- **Framework:** Svelte + Vite
- **Data:** Static JSON files exported by Python (`report.py`)
- **Search:** Fuse.js (client-side fuzzy search)
- **Charts:** Chart.js or hand-rolled SVG
- **Routing:** svelte-routing or SvelteKit (SPA mode)
- **Location:** `site/` subdirectory of this repo
- **Hosting:** GitHub Pages or any static host

## Data Export

`report.py` generates three JSON files to `site/public/data/`:

### `events.json`
Array of deduplicated events (canonical events only — non-canonical duplicates are folded into their canonical event's sources). Each event object:

```json
{
  "id": 123,
  "description": "Mass meeting held at Bethel AME...",
  "event_type": "mass_meeting",
  "date": "1922-01-14",
  "location": "Chicago, IL",
  "location_city": "Chicago",
  "location_state": "IL",
  "issue_primary": "anti_lynching",
  "issue_secondary": null,
  "organizations": ["NAACP", "Bethel AME Church"],
  "individuals": ["Ida B. Wells"],
  "target": "U.S. Congress",
  "size_text": "over 3,000",
  "tactics": ["mass_meeting", "petition"],
  "actor_type": "black_protest",
  "campaign_ids": [45],
  "sources": [
    {
      "paper": "chicago-defender",
      "date": "1922-01-14",
      "page": 1,
      "chunk_idx": 3,
      "source_text": "Full OCR text of this chunk...",
      "role": "primary"
    },
    {
      "paper": "new-york-age",
      "date": "1922-01-21",
      "page": 2,
      "chunk_idx": 1,
      "source_text": "Full OCR text from this paper...",
      "role": "duplicate"
    }
  ]
}
```

### `campaigns.json`
Array of campaigns:

```json
{
  "id": 45,
  "name": "Dyer Anti-Lynching Bill",
  "named": true,
  "issue_primary": "anti_lynching",
  "event_count": 14,
  "date_start": "1921-06-15",
  "date_end": "1922-12-04",
  "event_ids": [123, 456, 789]
}
```

### `meta.json`
Summary statistics:

```json
{
  "total_events": 7623,
  "total_campaigns": 757,
  "total_newspapers": 37,
  "date_range": ["1905-01-07", "1929-12-28"],
  "issue_counts": {"anti_lynching": 1496, ...},
  "newspaper_list": [{"slug": "chicago-defender", "name": "Chicago Defender", "location": "Chicago, IL"}, ...]
}
```

## Views

### 1. Dashboard (`/`)

Landing page and entry point.

- **Hero header:** Title "Protest Events in the African American Press, 1905–1929" with a brief project description
- **Stat cards:** Total events, campaigns, newspapers, date span
- **Issue breakdown:** Horizontal bar chart showing event counts by issue category
- **Top campaigns:** List of largest named campaigns with event counts, linked to campaign pages
- **Entry points:** Prominent links to Browse and Campaigns views

Design: Modern editorial (Marshall Project / ProPublica style). Bold typography, clean whitespace, strong visual hierarchy.

### 2. Browse / Search (`/events`)

Main exploration interface.

- **Faceted sidebar:**
  - Issue category (checkbox list)
  - Newspaper (searchable dropdown)
  - Date range (range slider, 1905–1929)
  - Tactic (checkbox list)
  - Actor type (radio: all / black protest / anti-black)
  - Campaign membership (has campaign / no campaign)
- **Text search:** Fuse.js fuzzy search across description, organizations, individuals
- **Results:** Card-based layout, 50 per page with pagination
  - Each card: date, description, issue badge, source count badge, campaign badge, newspaper names
  - Click card → Event Detail page
- **Active filters shown as removable chips**
- **Result count displayed**

### 3. Event Detail (`/events/:id`)

Full event page for verification and exploration.

- **Header:** Date, event type badge, issue badge(s)
- **Description:** Full event description, prominently displayed
- **Extracted fields:** Two-column layout
  - Organizations, Individuals, Target, Tactics, Size, Actor type, Location
- **Campaign membership:** Linked badge(s) to campaign page(s)
- **Source articles:** For EACH source (primary + duplicates):
  - Newspaper name, date, page number
  - Link to dangerouspress.org viewer (`?paper=X&date=Y&page=Z#chunk-N`)
  - **Full raw OCR text displayed** in a styled block — not behind a toggle, since this is used for verification
- **Related events:** Other events from the same campaign (if any)

### 4. Campaigns (`/campaigns` and `/campaigns/:id`)

**Campaign list** (`/campaigns`):
- Sortable table/list: name, event count, date range, issue category
- Filter by named vs. algorithmic
- Search by name

**Campaign detail** (`/campaigns/:id`):
- Campaign name, date range, issue category
- Events listed chronologically as cards (same format as Browse)
- Participating newspapers
- Key organizations and individuals across all events in campaign

## Architecture

### Data flow
```
SQLite DB → report.py → JSON files → site/public/data/ → Svelte app
```

### API abstraction layer
All data access goes through `site/src/lib/api.js`:

```javascript
export async function loadEvents() { ... }
export async function loadEvent(id) { ... }
export async function loadCampaigns() { ... }
export async function loadCampaign(id) { ... }
export async function loadMeta() { ... }
```

Initial implementation: fetch static JSON files.
Future: swap to FastAPI endpoints with no component changes.

### File structure
```
site/
  public/
    data/
      events.json
      campaigns.json
      meta.json
  src/
    lib/
      api.js              # data access abstraction
      search.js           # Fuse.js search setup
      utils.js            # formatters, URL builders
    components/
      EventCard.svelte
      EventDetail.svelte
      FacetSidebar.svelte
      IssueChart.svelte
      CampaignCard.svelte
      SourceBlock.svelte   # OCR text + dangerouspress link
      StatCard.svelte
      Pagination.svelte
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

## dangerouspress.org Integration

Source links follow the scheme from `docs/memo-web-linking.md`:

```
https://dangerouspress.org/?paper={paper}&date={date}&page={page}#chunk-{chunk_idx}
```

Built by a `makeViewerUrl()` utility in `utils.js`.

## Raw OCR Text Display

Each event's source articles include the full `source_text` from the chunks table. The event detail page displays ALL source texts (not just the canonical event's text) so users can:
- Read every newspaper's coverage of the event
- Compare how different papers reported the same event
- Verify the extraction is correct

Source texts are displayed in styled blockquotes with newspaper attribution, not hidden behind toggles.

## Design Language

- **Style:** Modern editorial (Marshall Project / ProPublica)
- **Typography:** Bold sans-serif headings, readable body text
- **Color:** Strong accent color for interactive elements, muted backgrounds
- **Badges:** Issue categories get consistent color coding across all views
- **Responsive:** Mobile-friendly, sidebar collapses to top filters on small screens
