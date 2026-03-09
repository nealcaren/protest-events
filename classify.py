"""Stage 3: Classify candidates using Claude Haiku."""

import json
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import anthropic

from config import CANDIDATES_FILE, EVENTS_FILE, HAIKU_MODEL, DATA_DIR


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


def classify_candidate(client: anthropic.Anthropic, row: dict) -> tuple[dict, dict | None]:
    """Classify a single candidate using Haiku. Returns (row, result)."""
    text = str(row["text"])[:2000]  # cap input length

    try:
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": USER_TEMPLATE.format(
                    paper=row["paper"], date=row["date"], text=text
                ),
            }],
        )
        content = resp.content[0].text.strip()
        # Parse JSON from response
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return row, json.loads(content)
    except (json.JSONDecodeError, IndexError, anthropic.APIError) as e:
        return row, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="Max candidates to classify (0 = all)")
    parser.add_argument("--workers", type=int, default=10,
                        help="Number of parallel API calls")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be classified without calling API")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    candidates = pd.read_csv(CANDIDATES_FILE)
    print(f"Loaded {len(candidates)} candidates")

    if args.limit > 0:
        candidates = candidates.head(args.limit)
        print(f"Limited to {len(candidates)} candidates")

    if args.dry_run:
        for _, row in candidates.head(10).iterrows():
            text_preview = str(row["text"])[:100].replace("\n", " ")
            print(f"  {row['paper']} {row['date']} p{row['page']} [{row['similarity']:.3f}]")
            print(f"    {text_preview}")
            print()
        print(f"Would classify {len(candidates)} candidates")
        return

    # Track already-processed candidates for resume support
    processed_file = DATA_DIR / "classified_keys.txt"
    processed_keys = set()
    if processed_file.exists():
        processed_keys = set(processed_file.read_text().splitlines())
        print(f"Resuming: {len(processed_keys)} already processed")

    # Load existing events if resuming
    events = []
    if EVENTS_FILE.exists() and processed_keys:
        events = pd.read_csv(EVENTS_FILE).to_dict("records")
        print(f"Loaded {len(events)} existing events")

    # Filter to unprocessed candidates
    to_process = []
    for _, row in candidates.iterrows():
        key = f"{row['paper']}|{row['date']}|{row['page']}|{row['chunk_idx']}"
        if key not in processed_keys:
            to_process.append(row.to_dict())

    print(f"Processing {len(to_process)} candidates with {args.workers} workers...")

    client = anthropic.Anthropic()
    t0 = time.time()
    done = 0
    yes_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(classify_candidate, client, row): row
            for row in to_process
        }

        for future in as_completed(futures):
            row, result = future.result()
            key = f"{row['paper']}|{row['date']}|{row['page']}|{row['chunk_idx']}"
            done += 1

            if result and result.get("is_protest"):
                event = {
                    "paper": row["paper"],
                    "date": row["date"],
                    "page": row["page"],
                    "chunk_idx": row["chunk_idx"],
                    "similarity": round(row["similarity"], 3),
                    "matched_query": row["matched_query"],
                    "event_type": result.get("event_type"),
                    "description": result.get("description"),
                    "location": result.get("location"),
                    "participants": result.get("participants"),
                    "date_mentioned": result.get("date_mentioned"),
                    "source_text": str(row["text"])[:500],
                }
                events.append(event)
                yes_count += 1

            processed_keys.add(key)

            # Progress update every 50
            if done % 50 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(to_process) - done) / rate if rate > 0 else 0
                print(f"  [{done}/{len(to_process)}] {yes_count} events found | {rate:.1f}/s | ETA {eta:.0f}s")
                pd.DataFrame(events).to_csv(EVENTS_FILE, index=False)
                processed_file.write_text("\n".join(processed_keys))

    elapsed = time.time() - t0
    print(f"\nClassified {done} candidates in {elapsed:.0f}s ({done/elapsed:.1f}/s)")
    print(f"Found {yes_count} new + {len(events)-yes_count} existing = {len(events)} total events")

    if events:
        pd.DataFrame(events).to_csv(EVENTS_FILE, index=False)
        processed_file.write_text("\n".join(processed_keys))
        print(f"Saved to {EVENTS_FILE}")


if __name__ == "__main__":
    main()
