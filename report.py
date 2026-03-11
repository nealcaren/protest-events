"""Generate HTML report from events database with enriched fields."""

import json
import argparse
from pathlib import Path
from html import escape
from collections import defaultdict

import pandas as pd

from config import REPORT_FILE, SITE_BASE_URL, DATA_DIR, ISSUE_CATEGORIES, PAPER_LOCATIONS
from db import get_connection, init_db

SITE_DATA_DIR = Path(__file__).parent / "site" / "public" / "data"


ISSUE_LABELS = {
    "anti_lynching": "Anti-Lynching",
    "segregation_public": "Segregation",
    "education": "Education",
    "voting_rights": "Voting Rights",
    "labor": "Labor",
    "criminal_justice": "Criminal Justice",
    "military": "Military",
    "government_discrimination": "Gov't Discrimination",
    "housing": "Housing",
    "healthcare": "Healthcare",
    "cultural_media": "Cultural/Media",
    "civil_rights_organizing": "Civil Rights Org.",
    "pan_african": "Pan-African",
    "womens_organizing": "Women's Organizing",
    "migration": "Migration",
}


def make_viewer_url(paper: str, date: str, page: int) -> str:
    """Build a dangerouspress.org viewer URL."""
    return f"{SITE_BASE_URL}/?paper={paper}&date={date}&page={page}"


def load_events(conn) -> pd.DataFrame:
    """Load events joined with chunk metadata and event_details."""
    rows = conn.execute("""
        SELECT e.id as event_id, c.paper, c.date, c.page, c.chunk_idx,
               e.event_type, e.description, e.location, e.participants,
               e.date_mentioned, e.source_text,
               ed.issue_primary, ed.issue_secondary,
               ed.organizations, ed.individuals, ed.target,
               ed.size_text, ed.tactics, ed.campaign_name,
               ed.actor_type, ed.actor_race_explicit,
               ed.location_city, ed.location_state
        FROM events e
        JOIN chunks c ON c.id = e.chunk_id
        LEFT JOIN event_details ed ON ed.event_id = e.id
        ORDER BY c.date, c.paper
    """).fetchall()
    columns = [
        "event_id", "paper", "date", "page", "chunk_idx",
        "event_type", "description", "location", "participants",
        "date_mentioned", "source_text",
        "issue_primary", "issue_secondary",
        "organizations", "individuals", "target",
        "size_text", "tactics", "campaign_name",
        "actor_type", "actor_race_explicit",
        "location_city", "location_state",
    ]
    return pd.DataFrame(rows, columns=columns)


def load_event_sources(conn) -> dict:
    """Load all sources per event. Returns {event_id: [{paper, date, page, chunk_idx}, ...]}."""
    rows = conn.execute("""
        SELECT es.event_id, c.paper, c.date, c.page, c.chunk_idx, es.role
        FROM event_sources es
        JOIN chunks c ON c.id = es.chunk_id
        ORDER BY es.event_id, c.date, c.paper
    """).fetchall()
    sources = defaultdict(list)
    for r in rows:
        sources[r["event_id"]].append({
            "paper": r["paper"], "date": r["date"],
            "page": r["page"], "chunk_idx": r["chunk_idx"],
            "role": r["role"],
        })
    return dict(sources)


def load_campaigns(conn) -> dict:
    """Load campaign info. Returns {campaign_id: {name, named, event_count, ...}}."""
    rows = conn.execute("SELECT * FROM campaigns ORDER BY event_count DESC").fetchall()
    return {r["id"]: dict(r) for r in rows}


def load_event_campaign_map(conn) -> dict:
    """Returns {event_id: [campaign_name, ...]}."""
    rows = conn.execute("""
        SELECT ec.event_id, c.name
        FROM event_campaigns ec
        JOIN campaigns c ON c.id = ec.campaign_id
    """).fetchall()
    mapping = defaultdict(list)
    for r in rows:
        mapping[r["event_id"]].append(r["name"])
    return dict(mapping)


def parse_json_field(val):
    """Parse a JSON string field, returning empty list on failure."""
    if not val:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def generate_html(events: pd.DataFrame, event_sources: dict,
                  event_campaigns: dict) -> str:
    """Generate an HTML report from events dataframe."""
    events = events.sort_values(["date", "paper"])

    event_types = sorted(events["event_type"].dropna().unique())
    papers = sorted(events["paper"].unique())
    issues = sorted(events["issue_primary"].dropna().unique())

    rows_html = []
    for _, ev in events.iterrows():
        event_id = ev["event_id"]
        url = make_viewer_url(ev["paper"], ev["date"], ev["page"])
        paper_display = ev["paper"].replace("-", " ").title()
        desc = escape(str(ev.get("description", "") or ""))
        location = escape(str(ev.get("location", "") or ""))
        participants = escape(str(ev.get("participants", "") or ""))
        event_type = escape(str(ev.get("event_type", "") or ""))
        date_mentioned = escape(str(ev.get("date_mentioned", "") or ""))
        source_preview = escape(str(ev.get("source_text", "")))

        # Issue category
        issue = str(ev.get("issue_primary") or "")
        if issue == "nan":
            issue = ""
        issue_label = ISSUE_LABELS.get(issue, issue)

        # Actor type
        actor = str(ev.get("actor_type") or "")
        if actor == "nan":
            actor = ""

        # Organizations and individuals
        orgs = parse_json_field(ev.get("organizations"))
        individuals = parse_json_field(ev.get("individuals"))
        campaign = str(ev.get("campaign_name") or "")
        if campaign == "nan":
            campaign = ""

        # Sources for this event
        sources = event_sources.get(event_id, [])
        if len(sources) > 1:
            source_links = []
            for s in sources:
                s_url = make_viewer_url(s["paper"], s["date"], s["page"])
                s_name = s["paper"].replace("-", " ").title()
                source_links.append(
                    f'<a href="{s_url}" target="_blank" class="source-link">'
                    f'{s_name}, {s["date"]}, p.{s["page"]}</a>'
                )
            sources_html = (
                f'<div class="multi-source">Sources ({len(sources)}):<br>'
                + "<br>".join(source_links)
                + "</div>"
            )
        else:
            sources_html = (
                f'<a href="{url}" target="_blank" class="source-link">'
                f'{paper_display}<br><small>p. {ev["page"]}</small></a>'
            )

        # Campaign badges
        campaigns = event_campaigns.get(event_id, [])
        campaign_html = ""
        if campaigns:
            campaign_html = "".join(
                f'<span class="campaign-badge">{escape(c)}</span>' for c in campaigns
            )

        # Meta line
        meta_parts = []
        if location:
            meta_parts.append(f"<span>Location: {location}</span>")
        if participants:
            meta_parts.append(f"<span>Participants: {participants}</span>")
        if date_mentioned:
            meta_parts.append(f"<span>Event date: {date_mentioned}</span>")
        if orgs:
            meta_parts.append(f"<span>Orgs: {escape(', '.join(orgs))}</span>")
        if individuals:
            meta_parts.append(f"<span>People: {escape(', '.join(individuals[:5]))}</span>")

        rows_html.append(f"""
        <tr class="event-row" data-type="{event_type}" data-paper="{ev['paper']}"
            data-issue="{issue}" data-actor="{actor}"
            data-campaign="{escape(campaign)}">
            <td class="date-col">{ev['date']}</td>
            <td>
                <span class="event-badge">{event_type}</span>
                {f'<br><span class="issue-badge">{escape(issue_label)}</span>' if issue_label else ''}
            </td>
            <td>
                <div class="event-desc">{desc}</div>
                {campaign_html}
                <div class="event-meta">
                    {''.join(meta_parts)}
                </div>
                <details class="source-toggle">
                    <summary>Source text</summary>
                    <div class="source-text">{source_preview}</div>
                </details>
            </td>
            <td>{sources_html}</td>
        </tr>""")

    type_options = "".join(f'<option value="{t}">{t}</option>' for t in event_types)
    paper_options = "".join(
        f'<option value="{p}">{p.replace("-", " ").title()}</option>' for p in papers
    )
    issue_options = "".join(
        f'<option value="{i}">{ISSUE_LABELS.get(i, i)}</option>' for i in issues
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Protest Events in African American Newspapers, 1905-1929</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Georgia', serif;
            background: #f8f5f0;
            color: #2d2420;
            line-height: 1.6;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px; }}
        h1 {{
            font-size: 1.8rem;
            color: #00594C;
            margin-bottom: 4px;
        }}
        .subtitle {{
            color: #666;
            font-size: 0.95rem;
            margin-bottom: 24px;
        }}
        .filters {{
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
            flex-wrap: wrap;
            align-items: center;
        }}
        .filters select, .filters input {{
            padding: 6px 12px;
            border: 1px solid #ccc;
            border-radius: 6px;
            font-size: 0.85rem;
            background: white;
        }}
        .filters input {{ width: 200px; }}
        .count {{ font-size: 0.85rem; color: #888; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        th {{
            background: #00594C;
            color: white;
            padding: 10px 14px;
            text-align: left;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            cursor: pointer;
            user-select: none;
        }}
        th:hover {{ background: #007a66; }}
        th .sort-arrow {{ font-size: 0.6rem; margin-left: 4px; }}
        td {{
            padding: 10px 14px;
            border-bottom: 1px solid #eee;
            font-size: 0.85rem;
            vertical-align: top;
        }}
        tr:hover {{ background: #faf7f2; }}
        .date-col {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
        .event-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            background: #e8f4f4;
            color: #00594C;
            white-space: nowrap;
        }}
        .issue-badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 600;
            background: #f0e8d8;
            color: #8b6914;
            white-space: nowrap;
            margin-top: 2px;
        }}
        .campaign-badge {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.7rem;
            background: #e8e0f4;
            color: #5a3d8a;
            margin-right: 4px;
            margin-bottom: 4px;
        }}
        .event-desc {{ font-weight: 600; margin-bottom: 4px; }}
        .event-meta {{
            font-size: 0.8rem;
            color: #888;
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .source-toggle {{
            margin-top: 6px;
            font-size: 0.8rem;
        }}
        .source-toggle summary {{
            cursor: pointer;
            color: #00594C;
        }}
        .source-text {{
            margin-top: 4px;
            padding: 8px;
            background: #f5f1e8;
            border-radius: 4px;
            font-size: 0.8rem;
            line-height: 1.5;
            font-style: italic;
        }}
        .source-link {{
            color: #00594C;
            text-decoration: none;
            font-weight: 600;
            font-size: 0.85rem;
            white-space: nowrap;
        }}
        .source-link:hover {{ text-decoration: underline; }}
        .source-link small {{
            font-weight: 400;
            color: #888;
        }}
        .multi-source {{
            font-size: 0.8rem;
            line-height: 1.8;
        }}
        .multi-source .source-link {{
            font-size: 0.8rem;
            font-weight: 400;
        }}
        @media (max-width: 768px) {{
            .filters {{ flex-direction: column; }}
            td, th {{ padding: 8px; font-size: 0.8rem; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Protest Events in African American Newspapers</h1>
        <p class="subtitle">1905&ndash;1929 &middot; Extracted from OCR text via semantic search + LLM classification</p>

        <div class="filters">
            <select id="type-filter">
                <option value="">All types</option>
                {type_options}
            </select>
            <select id="issue-filter">
                <option value="">All issues</option>
                {issue_options}
            </select>
            <select id="paper-filter">
                <option value="">All papers</option>
                {paper_options}
            </select>
            <input type="text" id="text-search" placeholder="Search descriptions...">
            <span class="count" id="count">{len(events)} events</span>
        </div>

        <table>
            <thead>
                <tr>
                    <th data-col="date" onclick="sortTable('date')">Date <span class="sort-arrow">&#9650;</span></th>
                    <th data-col="type" onclick="sortTable('type')">Type / Issue <span class="sort-arrow"></span></th>
                    <th>Event</th>
                    <th data-col="paper" onclick="sortTable('paper')">Sources <span class="sort-arrow"></span></th>
                </tr>
            </thead>
            <tbody id="events-body">
                {''.join(rows_html)}
            </tbody>
        </table>
    </div>

    <script>
        const typeFilter = document.getElementById('type-filter');
        const issueFilter = document.getElementById('issue-filter');
        const paperFilter = document.getElementById('paper-filter');
        const textSearch = document.getElementById('text-search');
        const countEl = document.getElementById('count');
        const rows = document.querySelectorAll('.event-row');

        function filterRows() {{
            const type = typeFilter.value;
            const issue = issueFilter.value;
            const paper = paperFilter.value;
            const text = textSearch.value.toLowerCase();
            let visible = 0;
            rows.forEach(row => {{
                const matchType = !type || row.dataset.type === type;
                const matchIssue = !issue || row.dataset.issue === issue;
                const matchPaper = !paper || row.dataset.paper === paper;
                const matchText = !text || row.textContent.toLowerCase().includes(text);
                const show = matchType && matchIssue && matchPaper && matchText;
                row.style.display = show ? '' : 'none';
                if (show) visible++;
            }});
            countEl.textContent = visible + ' events';
        }}

        typeFilter.addEventListener('change', filterRows);
        issueFilter.addEventListener('change', filterRows);
        paperFilter.addEventListener('change', filterRows);
        textSearch.addEventListener('input', filterRows);

        let sortCol = 'date';
        let sortAsc = true;

        function sortTable(col) {{
            if (sortCol === col) {{
                sortAsc = !sortAsc;
            }} else {{
                sortCol = col;
                sortAsc = true;
            }}

            const tbody = document.getElementById('events-body');
            const rowsArr = Array.from(rows);

            rowsArr.sort((a, b) => {{
                let va, vb;
                if (col === 'date') {{
                    va = a.querySelector('.date-col').textContent;
                    vb = b.querySelector('.date-col').textContent;
                }} else if (col === 'type') {{
                    va = a.dataset.type;
                    vb = b.dataset.type;
                }} else if (col === 'paper') {{
                    va = a.dataset.paper;
                    vb = b.dataset.paper;
                }}
                if (va < vb) return sortAsc ? -1 : 1;
                if (va > vb) return sortAsc ? 1 : -1;
                return 0;
            }});

            rowsArr.forEach(r => tbody.appendChild(r));

            document.querySelectorAll('th .sort-arrow').forEach(s => s.textContent = '');
            const th = document.querySelector(`th[data-col="${{col}}"]`);
            if (th) th.querySelector('.sort-arrow').textContent = sortAsc ? '&#9650;' : '&#9660;';
        }}
    </script>
</body>
</html>"""


def load_org_normalizations(conn):
    """Load org normalization map: original_name → canonical_name (or None if excluded)."""
    rows = conn.execute("SELECT original_name, canonical_name, excluded FROM org_normalizations").fetchall()
    norm = {}
    for r in rows:
        if r["excluded"]:
            norm[r["original_name"]] = None
        else:
            norm[r["original_name"]] = r["canonical_name"]
    return norm


def normalize_org_list(orgs, org_norm):
    """Apply normalization to a list of org names. Removes excluded, deduplicates."""
    result = []
    seen = set()
    for o in orgs:
        canonical = org_norm.get(o, o)  # default to original if not in table
        if canonical is None:  # excluded
            continue
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


def export_json():
    """Export deduplicated events, campaigns, and metadata as JSON for the Svelte frontend."""
    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    init_db(conn)

    # Get canonical event IDs from dedup_groups
    canonical_ids = set()
    rows = conn.execute("SELECT DISTINCT canonical_event_id FROM dedup_groups").fetchall()
    for r in rows:
        canonical_ids.add(r["canonical_event_id"])

    # Get singleton events (not in dedup_groups at all)
    all_event_ids = {r["id"] for r in conn.execute("SELECT id FROM events").fetchall()}
    grouped_ids = {r["event_id"] for r in conn.execute("SELECT event_id FROM dedup_groups").fetchall()}
    singleton_ids = all_event_ids - grouped_ids

    export_ids = canonical_ids | singleton_ids
    print(f"Exporting {len(export_ids)} events ({len(canonical_ids)} canonical, {len(singleton_ids)} singletons)")

    # Load org normalization
    org_norm = load_org_normalizations(conn)
    print(f"Loaded {len(org_norm)} org normalization mappings")

    # Load all events in the export set
    events_out = []
    for eid in sorted(export_ids):
        ev = conn.execute("""
            SELECT e.id as event_id, e.chunk_id, e.event_type, e.description,
                   e.location, e.participants, e.date_mentioned, e.source_text,
                   e.similarity, e.matched_query
            FROM events e WHERE e.id = ?
        """, (eid,)).fetchone()
        if ev is None:
            continue

        # Event details
        ed = conn.execute("""
            SELECT issue_primary, issue_secondary, organizations, individuals,
                   target, size_min, size_max, size_text, tactics, campaign_name,
                   actor_type, actor_race_explicit, location_city, location_state
            FROM event_details WHERE event_id = ?
        """, (eid,)).fetchone()

        # Sources with source_text from chunks
        sources_rows = conn.execute("""
            SELECT c.paper, c.date, c.page, c.chunk_idx, c.text as source_text, es.role
            FROM event_sources es
            JOIN chunks c ON c.id = es.chunk_id
            WHERE es.event_id = ?
            ORDER BY c.date, c.paper
        """, (eid,)).fetchall()
        sources = [
            {
                "paper": s["paper"], "date": s["date"], "page": s["page"],
                "chunk_idx": s["chunk_idx"], "source_text": s["source_text"],
                "role": s["role"],
            }
            for s in sources_rows
        ]

        # Campaign IDs
        campaign_rows = conn.execute("""
            SELECT campaign_id FROM event_campaigns WHERE event_id = ?
        """, (eid,)).fetchall()
        campaign_ids = [r["campaign_id"] for r in campaign_rows]

        # Get date from chunk
        chunk_date = conn.execute(
            "SELECT date FROM chunks WHERE id = ?", (ev["chunk_id"],)
        ).fetchone()

        obj = {
            "id": ev["event_id"],
            "date": chunk_date["date"] if chunk_date else (sources[0]["date"] if sources else None),
            "event_type": ev["event_type"],
            "description": ev["description"],
            "sources": sources,
            "campaign_ids": campaign_ids,
        }

        if ed:
            obj.update({
                "issue_primary": ed["issue_primary"],
                "issue_secondary": ed["issue_secondary"],
                "organizations": normalize_org_list(parse_json_field(ed["organizations"]), org_norm),
                "individuals": parse_json_field(ed["individuals"]),
                "target": ed["target"],
                "size_min": ed["size_min"],
                "size_max": ed["size_max"],
                "size_text": ed["size_text"],
                "tactics": parse_json_field(ed["tactics"]),
                "campaign_name": ed["campaign_name"],
                "actor_type": ed["actor_type"],
                "actor_race_explicit": ed["actor_race_explicit"],
                "location_city": ed["location_city"],
                "location_state": ed["location_state"],
            })

        events_out.append(obj)

    # Write events.json
    events_path = SITE_DATA_DIR / "events.json"
    events_path.write_text(json.dumps(events_out, indent=2))
    print(f"Wrote {len(events_out)} events to {events_path}")

    # Campaigns — filter event_ids to export set
    campaigns_rows = conn.execute("SELECT * FROM campaigns ORDER BY event_count DESC").fetchall()
    campaigns_out = []
    for c in campaigns_rows:
        camp = dict(c)
        # Get event_ids for this campaign, filtered to export set
        ce_rows = conn.execute(
            "SELECT event_id FROM event_campaigns WHERE campaign_id = ?", (camp["id"],)
        ).fetchall()
        camp["event_ids"] = [r["event_id"] for r in ce_rows if r["event_id"] in export_ids]
        campaigns_out.append(camp)

    campaigns_path = SITE_DATA_DIR / "campaigns.json"
    campaigns_path.write_text(json.dumps(campaigns_out, indent=2))
    print(f"Wrote {len(campaigns_out)} campaigns to {campaigns_path}")

    # Meta — summary stats
    issue_counts = defaultdict(int)
    for ev in events_out:
        ip = ev.get("issue_primary")
        if ip:
            issue_counts[ip] += 1

    # Date range from sources
    all_dates = [s["date"] for ev in events_out for s in ev.get("sources", []) if s.get("date")]
    date_range = [min(all_dates), max(all_dates)] if all_dates else [None, None]

    newspapers = [
        {"slug": slug, "name": slug.replace("-", " ").title(), "location": loc}
        for slug, loc in sorted(PAPER_LOCATIONS.items())
    ]

    meta = {
        "total_events": len(events_out),
        "total_campaigns": len(campaigns_out),
        "total_newspapers": len(PAPER_LOCATIONS),
        "date_range": date_range,
        "issue_counts": dict(issue_counts),
        "newspaper_list": newspapers,
    }
    meta_path = SITE_DATA_DIR / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"Wrote metadata to {meta_path}")

    # Organizations — aggregate from normalized events
    org_data = defaultdict(lambda: {
        "event_ids": [], "issues": defaultdict(int),
        "dates": [], "papers": set()
    })
    for ev in events_out:
        for org_name in ev.get("organizations", []):
            d = org_data[org_name]
            d["event_ids"].append(ev["id"])
            ip = ev.get("issue_primary")
            if ip:
                d["issues"][ip] += 1
            if ev.get("date"):
                d["dates"].append(ev["date"])
            for s in ev.get("sources", []):
                d["papers"].add(s["paper"])

    orgs_out = []
    for i, (name, d) in enumerate(sorted(org_data.items(), key=lambda x: -len(x[1]["event_ids"]))):
        dates = sorted(d["dates"])
        top_issue = max(d["issues"].items(), key=lambda x: x[1])[0] if d["issues"] else None
        orgs_out.append({
            "id": i + 1,
            "name": name,
            "event_count": len(d["event_ids"]),
            "event_ids": d["event_ids"],
            "date_start": dates[0] if dates else None,
            "date_end": dates[-1] if dates else None,
            "issue_primary": top_issue,
            "issue_counts": dict(d["issues"]),
            "newspapers": sorted(d["papers"]),
        })

    orgs_path = SITE_DATA_DIR / "organizations.json"
    orgs_path.write_text(json.dumps(orgs_out, indent=2))
    print(f"Wrote {len(orgs_out)} organizations to {orgs_path}")

    # Org network — co-occurrence graph for orgs with 3+ events
    cooccur = defaultdict(int)
    for ev in events_out:
        orgs = sorted(set(ev.get("organizations", [])))
        for a_idx, a in enumerate(orgs):
            for b in orgs[a_idx + 1:]:
                cooccur[(a, b)] += 1

    min_events = 3
    min_cooccur = 2
    active_orgs = {o["name"] for o in orgs_out if o["event_count"] >= min_events}
    org_id_map = {o["name"]: o["id"] for o in orgs_out}

    nodes = [{"id": o["id"], "name": o["name"], "event_count": o["event_count"],
              "issue_primary": o["issue_primary"]}
             for o in orgs_out if o["name"] in active_orgs]
    edges = [{"source": org_id_map[a], "target": org_id_map[b], "weight": count}
             for (a, b), count in sorted(cooccur.items(), key=lambda x: -x[1])
             if a in active_orgs and b in active_orgs and count >= min_cooccur]

    network = {"nodes": nodes, "edges": edges}
    network_path = SITE_DATA_DIR / "org_network.json"
    network_path.write_text(json.dumps(network, indent=2))
    print(f"Wrote org network: {len(nodes)} nodes, {len(edges)} edges to {network_path}")

    meta["total_organizations"] = len(orgs_out)

    # Re-write meta with org count
    meta_path.write_text(json.dumps(meta, indent=2))

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Generate report or export JSON")
    parser.add_argument("--json", action="store_true", help="Export JSON for Svelte frontend")
    args = parser.parse_args()

    if args.json:
        export_json()
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    init_db(conn)
    events = load_events(conn)
    event_sources = load_event_sources(conn)
    event_campaigns = load_event_campaign_map(conn)
    conn.close()

    print(f"Loaded {len(events)} events")

    html = generate_html(events, event_sources, event_campaigns)
    REPORT_FILE.write_text(html)
    print(f"Report saved to {REPORT_FILE}")
    print(f"Open: file://{REPORT_FILE.resolve()}")


if __name__ == "__main__":
    main()
