"""SQLite database for the protest event pipeline."""

import sqlite3
from pathlib import Path

from config import DATA_DIR

DB_FILE = DATA_DIR / "protest_events.db"


def get_connection(db_path: Path = DB_FILE) -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY,
            paper TEXT NOT NULL,
            date TEXT NOT NULL,
            page INTEGER NOT NULL,
            chunk_idx INTEGER NOT NULL,
            n_chunks INTEGER NOT NULL,
            text TEXT NOT NULL,
            UNIQUE(paper, date, page, chunk_idx)
        );

        CREATE TABLE IF NOT EXISTS candidates (
            chunk_id INTEGER PRIMARY KEY REFERENCES chunks(id),
            similarity REAL NOT NULL,
            matched_query TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            chunk_id INTEGER NOT NULL REFERENCES chunks(id),
            similarity REAL NOT NULL,
            matched_query TEXT NOT NULL,
            event_type TEXT,
            description TEXT,
            location TEXT,
            participants TEXT,
            date_mentioned TEXT,
            source_text TEXT
        );

        -- Tracks all chunks sent to classifier (protest or not) for resume
        CREATE TABLE IF NOT EXISTS classified (
            chunk_id INTEGER PRIMARY KEY REFERENCES chunks(id)
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_paper_date ON chunks(paper, date);
        CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
        CREATE INDEX IF NOT EXISTS idx_events_date ON events(chunk_id);

        -- Event-source junction table (many-to-many: events ↔ chunks)
        CREATE TABLE IF NOT EXISTS event_sources (
            event_id INTEGER REFERENCES events(id),
            chunk_id INTEGER REFERENCES chunks(id),
            role TEXT DEFAULT 'primary',
            PRIMARY KEY (event_id, chunk_id)
        );

        -- Structured extraction results
        CREATE TABLE IF NOT EXISTS event_details (
            event_id INTEGER PRIMARY KEY REFERENCES events(id),
            issue_primary TEXT,
            issue_secondary TEXT,
            organizations TEXT,
            individuals TEXT,
            target TEXT,
            size_min INTEGER,
            size_max INTEGER,
            size_text TEXT,
            tactics TEXT,
            campaign_name TEXT,
            actor_type TEXT,
            actor_race_explicit INTEGER,
            location_city TEXT,
            location_state TEXT
        );

        -- Tracks events sent through extraction
        CREATE TABLE IF NOT EXISTS extracted (
            event_id INTEGER PRIMARY KEY REFERENCES events(id)
        );

        -- Deduplication candidate pairs
        CREATE TABLE IF NOT EXISTS dedup_pairs (
            id INTEGER PRIMARY KEY,
            event_id_a INTEGER REFERENCES events(id),
            event_id_b INTEGER REFERENCES events(id),
            similarity REAL,
            same_event INTEGER,
            confidence TEXT,
            reasoning TEXT,
            UNIQUE(event_id_a, event_id_b)
        );

        -- Dedup groups: maps each event to its canonical event
        CREATE TABLE IF NOT EXISTS dedup_groups (
            event_id INTEGER PRIMARY KEY REFERENCES events(id),
            canonical_event_id INTEGER REFERENCES events(id)
        );

        -- Campaign/episode records
        CREATE TABLE IF NOT EXISTS campaigns (
            id INTEGER PRIMARY KEY,
            name TEXT,
            named INTEGER DEFAULT 0,
            issue_primary TEXT,
            description TEXT,
            event_count INTEGER,
            date_start TEXT,
            date_end TEXT
        );

        -- Event-campaign junction table
        CREATE TABLE IF NOT EXISTS event_campaigns (
            event_id INTEGER REFERENCES events(id),
            campaign_id INTEGER REFERENCES campaigns(id),
            PRIMARY KEY (event_id, campaign_id)
        );

        CREATE INDEX IF NOT EXISTS idx_event_sources_event ON event_sources(event_id);
        CREATE INDEX IF NOT EXISTS idx_event_sources_chunk ON event_sources(chunk_id);
        CREATE INDEX IF NOT EXISTS idx_dedup_groups_canonical ON dedup_groups(canonical_event_id);
        CREATE INDEX IF NOT EXISTS idx_event_campaigns_campaign ON event_campaigns(campaign_id);
    """)
