from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config.settings import DB_PATH, get_settings


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or get_settings().database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    with get_connection(db_path or DB_PATH) as conn:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        _apply_missing_columns(conn)


def _apply_missing_columns(conn: sqlite3.Connection) -> None:
    missing_columns = {
        "teams": {
            "national": "INTEGER",
            "founded": "INTEGER",
            "venue_id": "INTEGER",
            "venue_name": "TEXT",
            "venue_city": "TEXT",
            "source_type": "TEXT DEFAULT 'api'",
            "raw_json": "TEXT",
        },
        "players": {
            "team_name": "TEXT",
            "birth_place": "TEXT",
            "birth_country": "TEXT",
            "position": "TEXT",
            "number": "INTEGER",
            "source_type": "TEXT DEFAULT 'api'",
            "raw_json": "TEXT",
        },
        "fixtures": {
            "group_name": "TEXT",
            "timezone": "TEXT",
            "venue_id": "INTEGER",
            "referee_raw": "TEXT",
            "score_halftime_home": "INTEGER",
            "score_halftime_away": "INTEGER",
            "score_fulltime_home": "INTEGER",
            "score_fulltime_away": "INTEGER",
            "score_extratime_home": "INTEGER",
            "score_extratime_away": "INTEGER",
            "score_penalty_home": "INTEGER",
            "score_penalty_away": "INTEGER",
            "source_type": "TEXT DEFAULT 'api'",
            "raw_json": "TEXT",
        },
        "injuries": {"source_type": "TEXT DEFAULT 'api'"},
        "odds_snapshots": {"raw_payload_hash": "TEXT"},
        "sync_logs": {
            "estimated_requests": "INTEGER DEFAULT 0",
            "actual_requests": "INTEGER DEFAULT 0",
        },
    }
    for table, columns in missing_columns.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
