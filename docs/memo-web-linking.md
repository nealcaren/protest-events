# Memo: Deep Linking to Source Articles from Event Data

**To:** Web designer
**From:** Neal
**Re:** URL scheme for linking from protest event data to the dangerouspress.org viewer

---

## Context

We have a protest event database extracted from ~16,000 pages of African American newspapers (1905-1929). Each event links back to one or more source articles. The HTML report and future front-end need to link users directly to the relevant page — and ideally the relevant *section* of the page — in the dangerouspress.org viewer.

## Current URL Scheme

Links currently follow this pattern:

```
https://dangerouspress.org/?paper={paper}&date={date}&page={page}
```

**Parameters:**
- `paper` — newspaper slug, e.g. `chicago-defender`, `new-york-age`, `pittsburgh-courier`
- `date` — publication date in `YYYY-MM-DD` format, e.g. `1922-01-14`
- `page` — page number (integer), e.g. `1`

**Example:**
```
https://dangerouspress.org/?paper=chicago-defender&date=1922-01-14&page=1
```

This works and doesn't need to change.

## What We Want to Add: Fragment-Based Scrolling

Each page is split into text chunks during our processing pipeline. We store a `chunk_idx` (0-indexed integer) for each chunk on a page. We'd like to add an anchor fragment so the viewer scrolls directly to the relevant section:

```
https://dangerouspress.org/?paper={paper}&date={date}&page={page}#chunk-{chunk_idx}
```

**Example:**
```
https://dangerouspress.org/?paper=chicago-defender&date=1922-01-14&page=1#chunk-3
```

This should scroll the viewer to the 4th text region on that page (0-indexed).

### How Chunks Map to the Page

Each page's OCR text is split into chunks of roughly 512 tokens with some overlap. A typical page has 2-8 chunks. `chunk_idx=0` is the first chunk (top of the page), and they proceed sequentially down the page. The exact chunk boundaries come from the OCR region order in the source JSON files.

### What the Viewer Needs to Do

1. **Parse the fragment** — on page load, check for a `#chunk-{N}` fragment in the URL
2. **Highlight or scroll to the region** — ideally both:
   - Scroll the relevant text region into view
   - Visually highlight it (a brief background flash or a colored border) so the user can find the relevant passage
3. **Graceful fallback** — if the fragment doesn't match a known chunk (e.g., the chunk index is out of range), just show the page normally without scrolling

### Implementation Options

The simplest approach: when rendering OCR text regions on the page, add `id="chunk-0"`, `id="chunk-1"`, etc. to each text block element. The browser handles `#chunk-3` scrolling natively. Then add a small script for the highlight effect.

If the viewer renders text differently (e.g., overlaid on a page image), the anchor elements would go on whatever container wraps each text region.

## Multi-Source Events

Some events are covered by multiple newspapers. The report shows all sources for a given event, each with its own link. For example, a single event might show:

```
Sources (3):
  Chicago Defender, 1922-01-14, p. 1  →  ?paper=chicago-defender&date=1922-01-14&page=1#chunk-3
  New York Age, 1922-01-21, p. 2      →  ?paper=new-york-age&date=1922-01-21&page=2#chunk-1
  Baltimore Afro-American, 1922-01-28, p. 4  →  ?paper=baltimore-afro-american&date=1922-01-28&page=4#chunk-5
```

No special handling needed on the viewer side — each is just a standard page link with a chunk anchor.

## Data We Send

For each source link, we have these fields available:

| Field | Type | Example |
|-------|------|---------|
| `paper` | string (slug) | `chicago-defender` |
| `date` | string (YYYY-MM-DD) | `1922-01-14` |
| `page` | integer | `1` |
| `chunk_idx` | integer (0-indexed) | `3` |

The full list of newspaper slugs is in `config.py` under `PAPER_LOCATIONS` (37 papers currently).

## Timeline

No rush on the chunk anchoring — the page-level links work fine for now. But if you're touching the text rendering code, adding `id="chunk-{N}"` attributes would be a small lift that enables the deep linking whenever we're ready.
