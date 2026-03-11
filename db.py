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
    """)
