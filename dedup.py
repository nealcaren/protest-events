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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--find-pairs", action="store_true", help="Only find candidate pairs")
    parser.add_argument("--adjudicate", action="store_true", help="Only adjudicate pairs")
    parser.add_argument("--build-groups", action="store_true", help="Only build groups")
    parser.add_argument("--threshold", type=float, default=0.80,
                        help="Similarity threshold for candidate pairs (0.80 captures ~1300 true dupes at ~29%% precision, LLM adjudicates)")
    parser.add_argument("--date-window", type=int, default=15,
                        help="Date window in days for candidate pairs")
    parser.add_argument("--workers", type=int, default=10,
                        help="Number of parallel API calls")
    args = parser.parse_args()

    conn = get_connection()
    init_db(conn)

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
