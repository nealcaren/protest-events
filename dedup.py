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
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from openai import OpenAI

from config import CLASSIFIER_MODEL, REVIEWER_MODEL, OPENROUTER_BASE_URL, EMBEDDING_MODEL
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


def parse_date(d):
    """Parse a date string, returning None on failure."""
    try:
        return datetime.strptime(str(d), "%Y-%m-%d")
    except (ValueError, TypeError):
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

    # Parse dates for window comparison
    event_dates = [parse_date(e["date"]) for e in events]

    # Find candidate pairs (batched to manage memory)
    print("Finding candidate pairs...")
    pairs_found = 0
    batch_size = 500

    for start in range(0, len(events), batch_size):
        end = min(start + batch_size, len(events))
        batch_embs = embs[start:end]

        # Compare this batch against all later events
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
        if start > 0 and start % 1000 == 0:
            print(f"  Processed {start}/{len(events)} events, {pairs_found} pairs found")

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


def _build_union_find(conn):
    """Build union-find from already-confirmed pairs."""
    confirmed = conn.execute(
        "SELECT event_id_a, event_id_b FROM dedup_pairs WHERE same_event = 1"
    ).fetchall()
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            if ra > rb:
                ra, rb = rb, ra
            parent[rb] = ra

    for row in confirmed:
        union(row[0], row[1])

    return parent, find


def adjudicate(conn, client: OpenAI, workers: int = 10, batch_size: int = 200):
    """Step 5b: LLM adjudication of unadjudicated pairs.

    Processes in batches. Between batches, skips pairs where both events
    are already connected via confirmed pairs (saves LLM calls).
    """
    t0 = time.time()
    done = 0
    same_count = 0
    skipped = 0
    parse_errors = 0

    while True:
        # Build union-find from all confirmed pairs so far
        uf_parent, uf_find = _build_union_find(conn)

        # Load next batch of unadjudicated pairs
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
            LIMIT ?
        """, (batch_size * 2,)).fetchall()  # fetch extra to account for skips

        if not rows:
            break

        # Filter out pairs already connected via union-find
        batch = []
        for r in rows:
            r = dict(r)
            if uf_find(r["event_id_a"]) == uf_find(r["event_id_b"]):
                # Already connected — mark as same without LLM call
                conn.execute(
                    "UPDATE dedup_pairs SET same_event=1, confidence='transitive', reasoning='Already connected via other confirmed pairs' WHERE id=?",
                    (r["id"],),
                )
                skipped += 1
            else:
                batch.append(r)
                if len(batch) >= batch_size:
                    break

        conn.commit()

        if not batch:
            if not rows:
                break
            continue  # all were skipped, fetch next batch

        if done == 0:
            total_remaining = conn.execute(
                "SELECT COUNT(*) FROM dedup_pairs WHERE same_event IS NULL"
            ).fetchone()[0]
            print(f"Pairs to adjudicate: {total_remaining + len(batch)} (skipped {skipped} already-connected)")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(adjudicate_pair, client, p): p
                for p in batch
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
                    remaining = conn.execute(
                        "SELECT COUNT(*) FROM dedup_pairs WHERE same_event IS NULL"
                    ).fetchone()[0]
                    eta = remaining / rate if rate > 0 else 0
                    print(f"  [{done} adjudicated, {skipped} skipped] {same_count} same | "
                          f"{parse_errors} errors | {rate:.1f}/s | ~{remaining} remaining | ETA {eta:.0f}s")

        conn.commit()

    elapsed = time.time() - t0
    print(f"\nAdjudicated {done} pairs in {elapsed:.0f}s (skipped {skipped} already-connected)")
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
    unique = conn.execute("SELECT COUNT(DISTINCT canonical_event_id) FROM dedup_groups").fetchone()[0]
    print(f"Unique events after dedup: {unique}")

    # Flag oversized groups for review
    oversized = {c: g for c, g in groups.items() if len(g) >= 10}
    if oversized:
        print(f"\n{len(oversized)} groups with 10+ members flagged for review")


SPLIT_PROMPT = """You are reviewing a group of protest event descriptions that were automatically merged
as duplicates. Some may genuinely be the same event reported by different newspapers, but others may
be DIFFERENT events that got chained together because they share similar language or topic.

Your task: split this group into sub-groups where each sub-group is truly the SAME real-world event.
Consider: specific dates mentioned, specific locations, specific participants, specific actions taken.
Events from the same broad campaign (e.g., multiple Dyer Bill petitions in different cities) are
DIFFERENT events even if they use similar language.

Events in this group:
{events_text}

Respond with a JSON object mapping each event ID to a sub-group number (starting from 1):
{{"event_id": sub_group_number, ...}}

Events with the same sub-group number are the same real-world event.
Events with different sub-group numbers are different events.

Respond ONLY with the JSON object."""


def review_oversized_groups(conn, client: OpenAI, max_group_size: int = 10,
                            max_date_span: int = 15, workers: int = 5):
    """Step 5d: Review and split oversized dedup groups."""
    # Find groups that are too large or span too many days
    rows = conn.execute("""
        SELECT canonical_event_id, COUNT(*) as cnt
        FROM dedup_groups
        GROUP BY canonical_event_id
        HAVING cnt >= ?
    """, (max_group_size,)).fetchall()

    # Also find groups spanning too many days
    span_rows = conn.execute("""
        SELECT dg.canonical_event_id,
               COUNT(*) as cnt,
               MIN(c.date) as date_start,
               MAX(c.date) as date_end
        FROM dedup_groups dg
        JOIN events e ON e.id = dg.event_id
        JOIN chunks c ON c.id = e.chunk_id
        GROUP BY dg.canonical_event_id
        HAVING cnt >= 3
    """).fetchall()

    oversized_ids = set(r[0] for r in rows)
    for r in span_rows:
        try:
            d1 = datetime.strptime(r["date_start"], "%Y-%m-%d")
            d2 = datetime.strptime(r["date_end"], "%Y-%m-%d")
            if (d2 - d1).days > max_date_span:
                oversized_ids.add(r[0])
        except (ValueError, TypeError):
            pass

    if not oversized_ids:
        print("No oversized groups to review")
        return

    print(f"Reviewing {len(oversized_ids)} oversized groups...")

    splits_made = 0
    for canonical_id in oversized_ids:
        # Get all events in this group
        members = conn.execute(
            "SELECT event_id FROM dedup_groups WHERE canonical_event_id = ?",
            (canonical_id,),
        ).fetchall()
        member_ids = [r[0] for r in members]

        # Load event details
        event_rows = conn.execute("""
            SELECT e.id, e.description, c.paper, c.date,
                   ed.location_city, ed.location_state
            FROM events e
            JOIN chunks c ON c.id = e.chunk_id
            LEFT JOIN event_details ed ON ed.event_id = e.id
            WHERE e.id IN ({})
            ORDER BY c.date
        """.format(",".join("?" * len(member_ids))), member_ids).fetchall()

        # Build prompt
        events_text = ""
        for r in event_rows:
            loc = f"{r['location_city']}, {r['location_state']}" if r['location_city'] else "not stated"
            events_text += f"\n[{r['id']}] {r['date']} | {r['paper']} | {loc} | {r['description']}\n"

        try:
            resp = client.chat.completions.create(
                model=REVIEWER_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": SPLIT_PROMPT.format(events_text=events_text)}],
            )
            content = resp.choices[0].message.content.strip()
            result = parse_json_response(content)

            if result is None:
                continue

            # Parse sub-groups
            sub_groups = {}
            for eid_str, group_num in result.items():
                eid = int(eid_str)
                sub_groups.setdefault(group_num, []).append(eid)

            if len(sub_groups) <= 1:
                continue  # LLM says it's all one event, keep as is

            # Rebuild: delete old group entries for these events
            for eid in member_ids:
                conn.execute("DELETE FROM dedup_groups WHERE event_id = ?", (eid,))

            # Create new sub-groups
            for group_num, eids in sub_groups.items():
                new_canonical = min(eids)
                for eid in eids:
                    conn.execute(
                        "INSERT OR REPLACE INTO dedup_groups (event_id, canonical_event_id) VALUES (?, ?)",
                        (eid, new_canonical),
                    )

            splits_made += 1
            old_size = len(member_ids)
            new_sizes = [len(g) for g in sub_groups.values()]
            print(f"  Split group of {old_size} into {len(sub_groups)} sub-groups: {sorted(new_sizes, reverse=True)}")

        except Exception as e:
            print(f"  Error reviewing group {canonical_id}: {e}")

    conn.commit()
    print(f"\nSplit {splits_made} oversized groups")

    # Rebuild event_sources for affected groups
    # (clear duplicate-role sources and re-merge)
    conn.execute("DELETE FROM event_sources WHERE role = 'duplicate'")
    all_groups = conn.execute(
        "SELECT event_id, canonical_event_id FROM dedup_groups"
    ).fetchall()
    for r in all_groups:
        if r[0] != r[1]:
            conn.execute("""
                INSERT OR IGNORE INTO event_sources (event_id, chunk_id, role)
                SELECT ?, chunk_id, 'duplicate'
                FROM event_sources WHERE event_id = ?
            """, (r[1], r[0]))
    conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--find-pairs", action="store_true", help="Only find candidate pairs")
    parser.add_argument("--adjudicate", action="store_true", help="Only adjudicate pairs")
    parser.add_argument("--build-groups", action="store_true", help="Only build groups")
    parser.add_argument("--review", action="store_true", help="Only review oversized groups")
    parser.add_argument("--max-group-size", type=int, default=10,
                        help="Groups with this many+ members get reviewed")
    parser.add_argument("--max-date-span", type=int, default=15,
                        help="Groups spanning this many+ days get reviewed")
    parser.add_argument("--threshold", type=float, default=0.80,
                        help="Similarity threshold for candidate pairs (0.80 captures ~1300 true dupes at ~29%% precision, LLM adjudicates)")
    parser.add_argument("--date-window", type=int, default=15,
                        help="Date window in days for candidate pairs")
    parser.add_argument("--workers", type=int, default=10,
                        help="Number of parallel API calls")
    args = parser.parse_args()

    conn = get_connection()
    init_db(conn)

    run_all = not (args.find_pairs or args.adjudicate or args.build_groups or args.review)

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

    if run_all or args.review:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            print("ERROR: Set OPENROUTER_API_KEY environment variable")
            conn.close()
            return
        client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
        review_oversized_groups(conn, client,
                                max_group_size=args.max_group_size,
                                max_date_span=args.max_date_span)

    conn.close()


if __name__ == "__main__":
    main()
