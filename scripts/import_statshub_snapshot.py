from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.db.connection import get_connection, init_db
from app.db.queries import utc_now
from app.external.statshub_snapshot import detect_item_type, find_common_field, iter_arrays, parse_json_if_possible


def best_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    arrays = [(path, items) for path, items in iter_arrays(payload) if items]
    if not arrays:
        return [payload] if isinstance(payload, dict) else []
    return max(arrays, key=lambda pair: len(pair[1]))[1]


def latest_snapshot_id(conn, snapshot_name: str | None, endpoint_name: str) -> int | None:
    if snapshot_name:
        row = conn.execute(
            """
            SELECT id FROM statshub_snapshots
            WHERE snapshot_name = ? AND endpoint_name = ?
            ORDER BY id DESC LIMIT 1
            """,
            (snapshot_name, endpoint_name),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM statshub_snapshots WHERE endpoint_name = ? ORDER BY id DESC LIMIT 1",
            (endpoint_name,),
        ).fetchone()
    return row["id"] if row else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--snapshot-name")
    args = parser.parse_args()
    path = Path(args.file)
    payload = parse_json_if_possible(path.read_text(encoding="utf-8", errors="ignore"))
    print("IMPORT STATSHUB SNAPSHOT")
    print("Este comando no consume API.")
    if payload is None:
        raise SystemExit("El archivo no es JSON valido.")
    item_type = detect_item_type(args.endpoint_name)
    items = best_items(payload)
    imported = 0
    skipped = 0
    init_db()
    with get_connection() as conn:
        snapshot_id = latest_snapshot_id(conn, args.snapshot_name, args.endpoint_name)
        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            conn.execute(
                """
                INSERT INTO statshub_snapshot_items (
                    snapshot_id, endpoint_name, item_type, item_id, player_name,
                    team_name, event_id, stat_type, raw_item_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    args.endpoint_name,
                    item_type,
                    str(find_common_field(item, ["id", "uuid", "fixtureId", "eventId"]) or ""),
                    find_common_field(item, ["player_name", "playerName", "name", "player"]),
                    find_common_field(item, ["team_name", "teamName", "team"]),
                    str(find_common_field(item, ["event_id", "eventId", "fixtureId"]) or ""),
                    find_common_field(item, ["stat_type", "statType", "market", "type"]),
                    json.dumps(item, ensure_ascii=False, sort_keys=True, default=str),
                    utc_now(),
                ),
            )
            imported += 1
    print(f"Items importados: {imported}")
    print(f"Items omitidos: {skipped}")


if __name__ == "__main__":
    main()

