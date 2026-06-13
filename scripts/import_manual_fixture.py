from __future__ import annotations

import argparse
import csv
import zlib
from pathlib import Path

from app.db.connection import get_connection, init_db
from app.db.queries import insert_manual_import, insert_sync_log, upsert_fixture, utc_now


def fixture_id(row: dict[str, str]) -> int:
    key = "|".join([row.get("date_utc", ""), row.get("home_team_name", ""), row.get("away_team_name", "")])
    return zlib.crc32(key.encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()
    path = Path(args.csv)
    init_db()
    started = utc_now()
    count = 0
    with path.open(newline="", encoding="utf-8") as handle, get_connection() as conn:
        for row in csv.DictReader(handle):
            upsert_fixture(
                conn,
                {
                    "provider": "manual",
                    "provider_fixture_id": fixture_id(row),
                    "date_utc": row.get("date_utc"),
                    "round": row.get("round"),
                    "group_name": row.get("group_name"),
                    "status_short": "NS",
                    "status_long": "Not Started",
                    "elapsed": None,
                    "venue_name": row.get("venue_name"),
                    "venue_city": row.get("venue_city"),
                    "home_team_provider_id": None,
                    "away_team_provider_id": None,
                    "home_team_name": row.get("home_team_name"),
                    "away_team_name": row.get("away_team_name"),
                    "home_goals": None,
                    "away_goals": None,
                    "source_type": "manual",
                },
            )
            count += 1
        insert_manual_import(conn, {
            "import_name": "manual_fixtures",
            "source_name": path.name,
            "source_path": str(path),
            "data_type": "fixtures",
            "records_count": count,
            "notes": "Importacion manual CSV",
        })
        insert_sync_log(conn, "manual_fixtures", "OK", "fixtures manuales importados", count, started, utc_now())
    print(f"Fixtures manuales importados: {count}. Este comando no consume API.")


if __name__ == "__main__":
    main()

