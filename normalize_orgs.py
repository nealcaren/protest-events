"""Stage 7: Organization name normalization.

Collects all organization names from event_details, sends them to an LLM
in batches to normalize variants (e.g. "N.A.A.C.P." → "NAACP") and
exclude generic/unresolvable names (e.g. "League", "Association").

Stores the mapping in org_normalizations table for reuse.
"""

import os
import re
import json
import argparse
from collections import defaultdict

from openai import OpenAI

from config import REVIEWER_MODEL, OPENROUTER_BASE_URL
from db import get_connection, init_db


def ensure_org_tables(conn):
    """Create org normalization tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS org_normalizations (
            original_name TEXT PRIMARY KEY,
            canonical_name TEXT,
            excluded INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_org_norm_canonical
            ON org_normalizations(canonical_name);
    """)


def collect_org_names(conn):
    """Get all unique org names from event_details with event counts."""
    rows = conn.execute("""
        SELECT ed.organizations FROM event_details ed
        WHERE ed.organizations IS NOT NULL AND ed.organizations != '[]'
    """).fetchall()

    counts = defaultdict(int)
    for r in rows:
        try:
            orgs = json.loads(r["organizations"])
            for o in orgs:
                o = o.strip()
                if o:
                    counts[o] += 1
        except (json.JSONDecodeError, TypeError):
            continue

    return counts


def get_already_normalized(conn):
    """Get org names that already have normalization entries."""
    rows = conn.execute("SELECT original_name FROM org_normalizations").fetchall()
    return {r["original_name"] for r in rows}


def normalize_batch(client, org_names_with_counts, batch_num, total_batches):
    """Send a batch of org names to the LLM for normalization."""
    lines = []
    for name, count in sorted(org_names_with_counts, key=lambda x: -x[1]):
        lines.append(f"- {name} ({count} events)")

    prompt = f"""Below are organization names extracted from African American newspapers (1905-1929) with their event counts.

Many refer to the same organization with different spellings, abbreviations, or OCR variations.
Some are generic/ambiguous and can't be resolved to a specific organization.

For each name, provide ONE of:
1. A canonical name (the most common/recognizable form of the organization)
2. "EXCLUDE" if the name is too generic/ambiguous to identify (e.g. "League", "Association", "the association", "local branch")

Rules:
- Normalize abbreviations: "N.A.A.C.P." and "N. A. A. C. P." → "NAACP"
- Normalize capitalization variants: "National Association For the Advancement..." → "National Association for the Advancement of Colored People"
- Keep distinct organizations separate (e.g. "National Equal Rights League" ≠ "NAACP")
- When in doubt about whether two names refer to the same org, keep them separate
- Exclude newspaper names that appear as orgs (e.g. "Chicago Defender", "Cleveland Gazette")
- Exclude names that are clearly not organizations (person names, places)
- Use the most widely recognized form as canonical (prefer full name over abbreviation for lesser-known orgs, but "NAACP" and "UNIA" are fine as canonical)

Names (batch {batch_num}/{total_batches}):
{chr(10).join(lines)}

Respond with a JSON object mapping each original name to its canonical form or "EXCLUDE":
{{"original name": "canonical name or EXCLUDE", ...}}

Respond ONLY with the JSON object, no explanation."""

    resp = client.chat.completions.create(
        model=REVIEWER_MODEL,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
    )
    content = resp.choices[0].message.content.strip()

    # Strip thinking tags
    if "<think>" in content:
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    # Strip code fences
    if content.startswith("```"):
        lines = content.split("\n")
        inner = [l for l in lines[1:] if not l.startswith("```")]
        content = "\n".join(inner)

    return json.loads(content)


def main():
    parser = argparse.ArgumentParser(description="Normalize organization names")
    parser.add_argument("--min-events", type=int, default=2,
                        help="Only normalize orgs with this many events (default: 2)")
    parser.add_argument("--batch-size", type=int, default=150,
                        help="Orgs per LLM batch (default: 150)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be normalized without calling LLM")
    parser.add_argument("--reset", action="store_true",
                        help="Clear existing normalizations and redo all")
    args = parser.parse_args()

    conn = get_connection()
    init_db(conn)
    ensure_org_tables(conn)

    if args.reset:
        conn.execute("DELETE FROM org_normalizations")
        conn.commit()
        print("Cleared existing normalizations")

    # Collect all org names
    org_counts = collect_org_names(conn)
    print(f"Total unique org names: {len(org_counts)}")

    # Filter to those with enough events
    to_normalize = {name: count for name, count in org_counts.items()
                    if count >= args.min_events}
    print(f"Orgs with {args.min_events}+ events: {len(to_normalize)}")

    # Skip already-normalized
    already = get_already_normalized(conn)
    to_normalize = {name: count for name, count in to_normalize.items()
                    if name not in already}
    print(f"New orgs to normalize: {len(to_normalize)}")

    if not to_normalize:
        print("Nothing to do")
        _print_summary(conn, org_counts)
        conn.close()
        return

    if args.dry_run:
        print("\nWould normalize:")
        for name, count in sorted(to_normalize.items(), key=lambda x: -x[1]):
            print(f"  {count:4d}  {name}")
        conn.close()
        return

    # Set up LLM client
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        conn.close()
        return

    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)

    # Process in batches
    items = sorted(to_normalize.items(), key=lambda x: -x[1])
    batches = [items[i:i + args.batch_size]
               for i in range(0, len(items), args.batch_size)]
    total_batches = len(batches)

    total_normalized = 0
    total_excluded = 0
    for i, batch in enumerate(batches):
        print(f"\nBatch {i+1}/{total_batches} ({len(batch)} orgs)...")
        try:
            result = normalize_batch(client, batch, i + 1, total_batches)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        for original, canonical in result.items():
            if original not in to_normalize:
                continue
            excluded = 1 if canonical == "EXCLUDE" else 0
            canon = None if excluded else canonical
            conn.execute(
                """INSERT OR REPLACE INTO org_normalizations
                   (original_name, canonical_name, excluded)
                   VALUES (?, ?, ?)""",
                (original, canon, excluded),
            )
            if excluded:
                total_excluded += 1
            else:
                total_normalized += 1

        conn.commit()
        print(f"  Saved {len(result)} mappings")

    # Also auto-map single-event orgs to themselves (unless excluded by pattern)
    # These don't get LLM treatment but should exist in the table
    singleton_names = {name for name, count in org_counts.items()
                       if count < args.min_events and name not in already}
    if singleton_names:
        for name in singleton_names:
            conn.execute(
                """INSERT OR IGNORE INTO org_normalizations
                   (original_name, canonical_name, excluded)
                   VALUES (?, ?, 0)""",
                (name, name),
            )
        conn.commit()
        print(f"\nAuto-mapped {len(singleton_names)} single-event orgs to themselves")

    print(f"\nNormalized: {total_normalized}, Excluded: {total_excluded}")
    _print_summary(conn, org_counts)
    conn.close()


def _print_summary(conn, org_counts):
    """Print summary of normalization state."""
    rows = conn.execute("""
        SELECT canonical_name, COUNT(*) as variant_count
        FROM org_normalizations
        WHERE excluded = 0 AND canonical_name IS NOT NULL
        GROUP BY canonical_name
        ORDER BY variant_count DESC
        LIMIT 20
    """).fetchall()

    if rows:
        print("\nTop canonical orgs (by variant count):")
        for r in rows:
            # Sum event counts across all variants
            variants = conn.execute(
                "SELECT original_name FROM org_normalizations WHERE canonical_name = ?",
                (r["canonical_name"],),
            ).fetchall()
            total_events = sum(org_counts.get(v["original_name"], 0) for v in variants)
            print(f"  {total_events:5d} events  ({r['variant_count']} variants)  {r['canonical_name']}")

    excluded = conn.execute(
        "SELECT COUNT(*) FROM org_normalizations WHERE excluded = 1"
    ).fetchone()[0]
    active = conn.execute(
        "SELECT COUNT(DISTINCT canonical_name) FROM org_normalizations WHERE excluded = 0"
    ).fetchone()[0]
    print(f"\nCanonical orgs: {active}, Excluded names: {excluded}")


if __name__ == "__main__":
    main()
