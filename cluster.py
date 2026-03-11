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
from datetime import datetime

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
                max_tokens=4000,
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

    return {n: n for n in raw_names}


def create_named_campaigns(conn, name_map: dict):
    """Create campaign records for named campaigns and link events."""
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
    total_linked = sum(len(v) for v in campaigns.values())
    print(f"Created {created} named campaigns linking {total_linked} events")
    return created


def algorithmic_cluster(conn, time_window: int = 90, min_cluster: int = 3):
    """Step 6b: Cluster remaining events by issue + location + time."""
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

    # Group by (issue, state, city)
    groups = defaultdict(list)
    for ev in events:
        key = (ev["issue_primary"], ev["location_state"], ev["location_city"])
        groups[key].append(ev)

    created = 0
    for key, group_events in groups.items():
        issue, state, city = key

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

        # Sliding window clustering
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
