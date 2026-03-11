"""Stage 4: Structured extraction on confirmed protest events.

Runs a rich extraction prompt on each event to pull issue categories,
organizations, individuals, targets, size, tactics, campaign names,
and actor type. Writes to the event_details table.
"""

import json
import os
import re
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from config import (
    CLASSIFIER_MODEL, OPENROUTER_BASE_URL, DATA_DIR,
    PAPER_LOCATIONS, ISSUE_CATEGORIES,
)
from db import get_connection, init_db


ISSUE_DESCRIPTIONS = {
    "anti_lynching": "Anti-lynching / anti-mob violence: campaigns against lynching, mob violence, race massacres",
    "segregation_public": "Segregation & public accommodations: Jim Crow transit, parks, theaters, restaurants, public facilities",
    "education": "Education equity: segregated schools, Black teachers/principals, school funding",
    "voting_rights": "Voting rights & political representation: disenfranchisement, white primaries, political appointments",
    "labor": "Labor & economic rights: strikes, unions, wage disputes, workplace discrimination, peonage",
    "criminal_justice": "Criminal justice & policing: police brutality, prisoner advocacy, clemency, wrongful prosecution",
    "military": "Military & veterans' rights: Black officers, soldier mistreatment, court-martial clemency",
    "government_discrimination": "Government discrimination: segregation in federal/state agencies, discriminatory officials",
    "housing": "Housing & residential segregation: ordinances, restrictive covenants, home defense, tenant rights",
    "healthcare": "Healthcare discrimination: hospital staffing, segregated medical facilities",
    "cultural_media": "Cultural & media protest: opposition to racist films, newspapers, speeches, symbols",
    "civil_rights_organizing": "Civil rights organizing: NAACP/NERL/Niagara conferences, broad campaigns, org founding",
    "pan_african": "Pan-African & international solidarity: UNIA, Pan-African Congress, international racial solidarity",
    "womens_organizing": "Women's rights & organizing: suffrage, women's clubs, gender-specific racial claims",
    "migration": "Migration as collective action: Great Migration framed as protest against Southern conditions",
}

EXTRACT_SYSTEM = """You are analyzing protest events from African American newspapers published between 1905 and 1929.
You will be given a text passage that has already been identified as describing a protest action.
Your task is to extract structured information about the event.

IMPORTANT NOTES:
- These newspapers were written for a Black audience. Authors often do NOT explicitly state that
  participants are Black — the audience would know. Similarly, white actors may not be labeled white.
  Set actor_race_explicit to true ONLY if the text explicitly names the race of the actors.
- Do NOT assume the event took place in the newspaper's publication city. Many articles report on
  events from around the country. Only assign a location if the text explicitly states where the
  event occurred. If the location is unclear, set location_city and location_state to null.
- For campaign_name, only provide a name if the event is clearly part of a recognized, named campaign
  or movement (e.g., "Dyer Anti-Lynching Bill campaign", "Brownsville Affair", "Sweet Trial").
  Do not invent campaign names for isolated events."""

EXTRACT_USER = """Extract structured information from this protest event.

Newspaper: {paper_name} (published in {pub_location})
Date: {date}

Text:
{text}

Issue categories (pick one primary, optionally one secondary):
{issue_list}

Respond with a JSON object:
{{
    "issue_primary": "<category_code>",
    "issue_secondary": "<category_code>" or null,
    "organizations": ["org1", "org2"] or [],
    "individuals": ["person1", "person2"] or [],
    "target": "who is being petitioned/opposed" or null,
    "size_min": <integer> or null,
    "size_max": <integer> or null,
    "size_text": "raw size descriptor from text" or null,
    "tactics": ["tactic1", "tactic2"],
    "campaign_name": "name of recognized campaign" or null,
    "actor_type": "black_protest" or "anti_black" or "mixed",
    "actor_race_explicit": true or false,
    "location_city": "city name" or null,
    "location_state": "state abbreviation" or null
}}

Valid tactics: march, rally, mass_meeting, petition, boycott, strike, delegation,
demonstration, parade, legal_action, riot, self_defense, verbal_statement,
organizational_founding, voter_mobilization, other

Respond ONLY with the JSON object, no other text."""


def parse_json_response(content: str) -> dict | None:
    """Extract JSON from a response that might have markdown fences or thinking tags."""
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


def extract_event(client: OpenAI, event: dict) -> tuple[dict, dict | None]:
    """Run extraction prompt on a single event. Returns (event, result)."""
    text = str(event["source_text"])[:3000]
    paper = event["paper"]
    pub_location = PAPER_LOCATIONS.get(paper, "unknown")
    paper_name = paper.replace("-", " ").title()

    issue_list = "\n".join(f"  {code}: {desc}" for code, desc in ISSUE_DESCRIPTIONS.items())

    try:
        resp = client.chat.completions.create(
            model=CLASSIFIER_MODEL,
            max_tokens=500,
            messages=[
                {"role": "system", "content": EXTRACT_SYSTEM},
                {"role": "user", "content": EXTRACT_USER.format(
                    paper_name=paper_name, pub_location=pub_location,
                    date=event["date"], text=text, issue_list=issue_list,
                )},
            ],
        )
        content = resp.choices[0].message.content.strip()
        return event, parse_json_response(content)
    except Exception:
        return event, None


def validate_result(result: dict) -> dict:
    """Normalize and validate extraction result."""
    if result.get("issue_primary") not in ISSUE_CATEGORIES:
        result["issue_primary"] = None
    if result.get("issue_secondary") not in ISSUE_CATEGORIES + [None]:
        result["issue_secondary"] = None

    for field in ("organizations", "individuals", "tactics"):
        if not isinstance(result.get(field), list):
            result[field] = []

    if result.get("actor_type") not in ("black_protest", "anti_black", "mixed"):
        result["actor_type"] = None

    if not isinstance(result.get("actor_race_explicit"), bool):
        result["actor_race_explicit"] = None

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="Max events to extract (0 = all)")
    parser.add_argument("--workers", type=int, default=10,
                        help="Number of parallel API calls")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be extracted without calling API")
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: Set OPENROUTER_API_KEY environment variable")
        return

    conn = get_connection()
    init_db(conn)

    # Load unextracted events
    rows = conn.execute("""
        SELECT e.id as event_id, e.source_text, e.event_type, e.description,
               c.paper, c.date, c.page
        FROM events e
        JOIN chunks c ON c.id = e.chunk_id
        LEFT JOIN extracted ex ON ex.event_id = e.id
        WHERE ex.event_id IS NULL
        ORDER BY e.id
    """).fetchall()

    to_process = [dict(r) for r in rows]
    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    already_done = total_events - len(to_process)

    print(f"Total events: {total_events}")
    if already_done > 0:
        print(f"Already extracted: {already_done}")
    print(f"To extract: {len(to_process)}")

    if args.limit > 0:
        to_process = to_process[:args.limit]
        print(f"Limited to {len(to_process)} events")

    if args.dry_run:
        for ev in to_process[:10]:
            text_preview = str(ev["source_text"] or "")[:100].replace("\n", " ")
            print(f"  [{ev['event_id']}] {ev['paper']} {ev['date']} - {ev['event_type']}")
            print(f"    {text_preview}")
            print()
        print(f"Would extract {len(to_process)} events")
        conn.close()
        return

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)
    t0 = time.time()
    done = 0
    success = 0
    parse_errors = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(extract_event, client, ev): ev
            for ev in to_process
        }

        for future in as_completed(futures):
            event, result = future.result()
            done += 1

            if result is None:
                parse_errors += 1
            else:
                result = validate_result(result)
                conn.execute(
                    """INSERT OR REPLACE INTO event_details
                       (event_id, issue_primary, issue_secondary, organizations,
                        individuals, target, size_min, size_max, size_text,
                        tactics, campaign_name, actor_type, actor_race_explicit,
                        location_city, location_state)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (event["event_id"],
                     result.get("issue_primary"),
                     result.get("issue_secondary"),
                     json.dumps(result.get("organizations", [])),
                     json.dumps(result.get("individuals", [])),
                     result.get("target"),
                     result.get("size_min"),
                     result.get("size_max"),
                     result.get("size_text"),
                     json.dumps(result.get("tactics", [])),
                     result.get("campaign_name"),
                     result.get("actor_type"),
                     1 if result.get("actor_race_explicit") else 0,
                     result.get("location_city"),
                     result.get("location_state")),
                )
                success += 1

            # Mark as extracted regardless of success/failure
            conn.execute(
                "INSERT OR IGNORE INTO extracted (event_id) VALUES (?)",
                (event["event_id"],),
            )

            if done % 50 == 0:
                conn.commit()
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(to_process) - done) / rate if rate > 0 else 0
                print(f"  [{done}/{len(to_process)}] {success} extracted | "
                      f"{parse_errors} errors | {rate:.1f}/s | ETA {eta:.0f}s")

    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print(f"\nExtracted {done} events in {elapsed:.0f}s ({done/elapsed:.1f}/s)")
    print(f"Success: {success} | Parse errors: {parse_errors}")


if __name__ == "__main__":
    main()
