from __future__ import annotations

import argparse
import csv
import zlib
from pathlib import Path

from app.db.connection import get_connection, init_db
from app.db.queries import insert_manual_import, insert_sync_log, upsert_team, utc_now


def team_id(row: dict[str, str]) -> int:
    return zlib.crc32((row.get("name", "") + "|" + row.get("country", "")).encode("utf-8"))


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
            upsert_team(
                conn,
                {
                    "provider": "manual",
                    "provider_team_id": team_id(row),
                    "name": row.get("name"),
                    "country": row.get("country"),
                    "code": row.get("code"),
                    "logo": row.get("logo"),
                    "source_type": "manual",
                },
            )
            count += 1
        insert_manual_import(conn, {
            "import_name": "manual_teams",
            "source_name": path.name,
            "source_path": str(path),
            "data_type": "teams",
            "records_count": count,
            "notes": "Importacion manual CSV",
        })
        insert_sync_log(conn, "manual_teams", "OK", "equipos manuales importados", count, started, utc_now())
    print(f"Equipos manuales importados: {count}. Este comando no consume API.")


if __name__ == "__main__":
    main()

