"""Stage 3: Classify candidates using Qwen3 via OpenRouter.

Groups adjacent chunks from the same page before classifying, so the
model sees full context when an event spans chunk boundaries.
"""

import json
import os
import re
import time
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from config import CLASSIFIER_MODEL, OPENROUTER_BASE_URL, DATA_DIR
from db import get_connection, init_db


SYSTEM_PROMPT = """You are analyzing text from African American newspapers published between 1905 and 1929.
Your task is to determine if a text passage describes a political protest action — broadly defined as
collective public action aimed at expressing grievance or demanding change.

This includes: protests, marches, parades (political), demonstrations, mass meetings, rallies,
petitions, boycotts, strikes, delegations to officials, indignation meetings, citizens' assemblies,
and similar collective political actions.

This does NOT include: regular church services, social gatherings, club meetings (unless they involve
protest planning), sports events, advertisements, obituaries, or routine political coverage (elections,
legislation) unless it describes a specific protest action."""

USER_TEMPLATE = """Analyze this newspaper text and determine if it describes a protest action.

Paper: {paper}
Date: {date}
Text:
{text}

Respond with a JSON object:
{{
    "is_protest": true/false,
    "event_type": "march|rally|mass_meeting|petition|boycott|strike|delegation|demonstration|parade|other" or null,
    "description": "One sentence describing the event" or null,
    "location": "City or place mentioned" or null,
    "participants": "Who was involved (brief)" or null,
    "date_mentioned": "Date of the event if mentioned in text" or null
}}

Respond ONLY with the JSON object, no other text."""


def parse_json_response(content: str) -> dict | None:
    """Extract JSON from a response that might have markdown fences or thinking tags."""
    content = content.strip()
    # Strip <think>...</think> blocks (Qwen/DeepSeek reasoning)
    if "<think>" in content:
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    # Strip markdown fences
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
        match = re.search(r'\{[^{}]*"is_protest"[^{}]*\}', content)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None


def group_adjacent_chunks(rows: list[dict]) -> list[dict]:
    """Group adjacent candidate chunks from the same page into merged groups.

    Each returned dict has:
      - chunk_ids: list of chunk_ids in the group
      - paper, date, page: from the first chunk
      - text: concatenated text of all chunks in order
      - similarity: max similarity across chunks
      - matched_query: query from the highest-similarity chunk
    """
    # Index by (paper, date, page)
    by_page = defaultdict(list)
    for row in rows:
        key = (row["paper"], row["date"], row["page"])
        by_page[key].append(row)

    groups = []
    for key, page_rows in by_page.items():
        page_rows.sort(key=lambda r: r["chunk_idx"])

        # Find runs of consecutive chunk_idx values
        runs = []
        current_run = [page_rows[0]]
        for i in range(1, len(page_rows)):
            if page_rows[i]["chunk_idx"] == current_run[-1]["chunk_idx"] + 1:
                current_run.append(page_rows[i])
            else:
                runs.append(current_run)
                current_run = [page_rows[i]]
        runs.append(current_run)

        for run in runs:
            best = max(run, key=lambda r: r["similarity"])
            merged_text = "\n\n".join(str(r["text"]) for r in run)
            groups.append({
                "chunk_ids": [r["chunk_id"] for r in run],
                "paper": run[0]["paper"],
                "date": run[0]["date"],
                "page": run[0]["page"],
                "text": merged_text,
                "similarity": best["similarity"],
                "matched_query": best["matched_query"],
                "n_chunks": len(run),
            })

    return groups


def classify_group(client: OpenAI, group: dict) -> tuple[dict, dict | None]:
    """Classify a merged chunk group. Returns (group, result)."""
    text = str(group["text"])[:3000]  # slightly larger budget for merged chunks

    try:
        resp = client.chat.completions.create(
            model=CLASSIFIER_MODEL,
            max_tokens=300,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_TEMPLATE.format(
                    paper=group["paper"], date=group["date"], text=text
                )},
            ],
        )
        content = resp.choices[0].message.content.strip()
        return group, parse_json_response(content)
    except Exception:
        return group, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="Max groups to classify (0 = all)")
    parser.add_argument("--workers", type=int, default=10,
                        help="Number of parallel API calls")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be classified without calling API")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY environment variable")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    init_db(conn)

    # Load unclassified candidates
    rows = conn.execute("""
        SELECT c.id as chunk_id, c.paper, c.date, c.page, c.chunk_idx, c.text,
               cand.similarity, cand.matched_query
        FROM candidates cand
        JOIN chunks c ON c.id = cand.chunk_id
        LEFT JOIN classified cl ON cl.chunk_id = cand.chunk_id
        WHERE cl.chunk_id IS NULL
        ORDER BY cand.similarity DESC
    """).fetchall()

    to_process = [dict(r) for r in rows]
    total_candidates = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    already_done = total_candidates - len(to_process)

    print(f"Total candidates: {total_candidates}")
    if already_done > 0:
        print(f"Already classified: {already_done}")
    print(f"Unclassified chunks: {len(to_process)}")

    # Group adjacent chunks
    groups = group_adjacent_chunks(to_process)
    solo = sum(1 for g in groups if g["n_chunks"] == 1)
    merged = len(groups) - solo
    print(f"Grouped into {len(groups)} classification units "
          f"({solo} solo + {merged} merged from {len(to_process) - solo} chunks)")

    if args.limit > 0:
        groups = groups[:args.limit]
        print(f"Limited to {len(groups)} groups")

    if args.dry_run:
        for group in groups[:10]:
            text_preview = str(group["text"])[:100].replace("\n", " ")
            print(f"  {group['paper']} {group['date']} p{group['page']} "
                  f"[{group['similarity']:.3f}] {group['n_chunks']} chunks")
            print(f"    {text_preview}")
            print()
        print(f"Would classify {len(groups)} groups ({sum(g['n_chunks'] for g in groups)} chunks)")
        conn.close()
        return

    existing_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
    t0 = time.time()
    done = 0
    yes_count = 0
    parse_errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(classify_group, client, group): group
            for group in groups
        }

        for future in as_completed(futures):
            group, result = future.result()
            done += 1

            if result is None:
                parse_errors += 1
            elif result.get("is_protest"):
                # Record event against the first chunk_id
                primary_id = group["chunk_ids"][0]
                conn.execute(
                    """INSERT INTO events
                       (chunk_id, similarity, matched_query, event_type, description,
                        location, participants, date_mentioned, source_text)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (primary_id, round(group["similarity"], 3), group["matched_query"],
                     result.get("event_type"), result.get("description"),
                     result.get("location"), result.get("participants"),
                     result.get("date_mentioned"), str(group["text"])[:3000]),
                )
                yes_count += 1

            # Mark ALL chunks in group as classified
            for cid in group["chunk_ids"]:
                conn.execute("INSERT OR IGNORE INTO classified (chunk_id) VALUES (?)", (cid,))

            # Checkpoint every 50
            if done % 50 == 0:
                conn.commit()
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(groups) - done) / rate if rate > 0 else 0
                print(f"  [{done}/{len(groups)}] {yes_count} events | "
                      f"{parse_errors} errors | {rate:.1f}/s | ETA {eta:.0f}s")

    conn.commit()
    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()

    elapsed = time.time() - t0
    print(f"\nClassified {done} groups in {elapsed:.0f}s ({done/elapsed:.1f}/s)")
    print(f"Found {yes_count} new + {existing_events} existing = {total_events} total events")
    if parse_errors:
        print(f"Parse errors: {parse_errors}")


if __name__ == "__main__":
    main()
