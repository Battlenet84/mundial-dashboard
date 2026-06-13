from __future__ import annotations

from app.db.connection import get_connection


MISSING_COLUMNS = {
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


def apply_migrations() -> None:
    with get_connection() as conn:
        for table, columns in MISSING_COLUMNS.items():
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            for name, definition in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def main() -> None:
    from app.db.connection import init_db

    init_db()
    apply_migrations()
    print("Migraciones locales aplicadas sin destruir datos.")


if __name__ == "__main__":
    main()
