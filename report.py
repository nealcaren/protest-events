"""Stage 4: Generate HTML report from events database."""

import argparse
from html import escape

import pandas as pd

from config import REPORT_FILE, SITE_BASE_URL, DATA_DIR
from db import get_connection, init_db


def make_viewer_url(paper: str, date: str, page: int) -> str:
    """Build a dangerouspress.org viewer URL."""
    return f"{SITE_BASE_URL}/?paper={paper}&date={date}&page={page}"


def load_events(conn) -> pd.DataFrame:
    """Load events joined with chunk metadata."""
    rows = conn.execute("""
        SELECT c.paper, c.date, c.page, c.chunk_idx,
               e.similarity, e.matched_query, e.event_type, e.description,
               e.location, e.participants, e.date_mentioned, e.source_text
        FROM events e
        JOIN chunks c ON c.id = e.chunk_id
        ORDER BY c.date, c.paper
    """).fetchall()
    return pd.DataFrame(rows, columns=[
        "paper", "date", "page", "chunk_idx", "similarity", "matched_query",
        "event_type", "description", "location", "participants",
        "date_mentioned", "source_text",
    ])


def generate_html(events: pd.DataFrame) -> str:
    """Generate an HTML report from events dataframe."""
    events = events.sort_values(["date", "paper"])

    event_types = sorted(events["event_type"].dropna().unique())
    papers = sorted(events["paper"].unique())

    rows_html = []
    for _, ev in events.iterrows():
        url = make_viewer_url(ev["paper"], ev["date"], ev["page"])
        paper_display = ev["paper"].replace("-", " ").title()
        desc = escape(str(ev.get("description", "") or ""))
        location = escape(str(ev.get("location", "") or ""))
        participants = escape(str(ev.get("participants", "") or ""))
        event_type = escape(str(ev.get("event_type", "") or ""))
        date_mentioned = escape(str(ev.get("date_mentioned", "") or ""))
        source_preview = escape(str(ev.get("source_text", "")))

        rows_html.append(f"""
        <tr class="event-row" data-type="{event_type}" data-paper="{ev['paper']}">
            <td class="date-col">{ev['date']}</td>
            <td><span class="event-badge">{event_type}</span></td>
            <td>
                <div class="event-desc">{desc}</div>
                <div class="event-meta">
                    {f'<span>Location: {location}</span>' if location else ''}
                    {f'<span>Participants: {participants}</span>' if participants else ''}
                    {f'<span>Event date: {date_mentioned}</span>' if date_mentioned else ''}
                </div>
                <details class="source-toggle">
                    <summary>Source text</summary>
                    <div class="source-text">{source_preview}</div>
                </details>
            </td>
            <td>
                <a href="{url}" target="_blank" class="source-link">
                    {paper_display}<br>
                    <small>p. {ev['page']}</small>
                </a>
            </td>
        </tr>""")

    type_options = "".join(f'<option value="{t}">{t}</option>' for t in event_types)
    paper_options = "".join(
        f'<option value="{p}">{p.replace("-", " ").title()}</option>' for p in papers
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
        .container {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px; }}
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
                    <th data-col="date" onclick="sortTable('date')">Date <span class="sort-arrow">▲</span></th>
                    <th data-col="type" onclick="sortTable('type')">Type <span class="sort-arrow"></span></th>
                    <th>Event</th>
                    <th data-col="paper" onclick="sortTable('paper')">Source <span class="sort-arrow"></span></th>
                </tr>
            </thead>
            <tbody id="events-body">
                {''.join(rows_html)}
            </tbody>
        </table>
    </div>

    <script>
        const typeFilter = document.getElementById('type-filter');
        const paperFilter = document.getElementById('paper-filter');
        const textSearch = document.getElementById('text-search');
        const countEl = document.getElementById('count');
        const rows = document.querySelectorAll('.event-row');

        function filterRows() {{
            const type = typeFilter.value;
            const paper = paperFilter.value;
            const text = textSearch.value.toLowerCase();
            let visible = 0;
            rows.forEach(row => {{
                const matchType = !type || row.dataset.type === type;
                const matchPaper = !paper || row.dataset.paper === paper;
                const matchText = !text || row.textContent.toLowerCase().includes(text);
                const show = matchType && matchPaper && matchText;
                row.style.display = show ? '' : 'none';
                if (show) visible++;
            }});
            countEl.textContent = visible + ' events';
        }}

        typeFilter.addEventListener('change', filterRows);
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
            if (th) th.querySelector('.sort-arrow').textContent = sortAsc ? '▲' : '▼';
        }}
    </script>
</body>
</html>"""


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    init_db(conn)
    events = load_events(conn)
    conn.close()

    print(f"Loaded {len(events)} events")

    html = generate_html(events)
    REPORT_FILE.write_text(html)
    print(f"Report saved to {REPORT_FILE}")
    print(f"Open: file://{REPORT_FILE.resolve()}")


if __name__ == "__main__":
    main()
