from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.db.connection import get_connection, init_db
from app.db.queries import utc_now
from app.external.statshub_snapshot import detect_item_type, extract_ids, find_common_field, iter_arrays, parse_json_if_possible


def best_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    arrays = [(path, items) for path, items in iter_arrays(payload) if items]
    if not arrays:
        return [payload] if isinstance(payload, dict) else []
    return max(arrays, key=lambda pair: len(pair[1]))[1]


def raw(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def endpoint_table(endpoint: str) -> str:
    name = endpoint.lower()
    if name.startswith("player_") and name.endswith("_tournaments"):
        return "statshub_raw_player_tournaments"
    if name.startswith("team_") and name.endswith("_tournaments"):
        return "statshub_raw_team_tournaments"
    if "referees" in name:
        return "statshub_raw_referees"
    if "players_from_screener" in name or "from-screener" in name:
        return "statshub_raw_players"
    if "performance" in name:
        return "statshub_raw_player_performance"
    if "team_events" in name or "/events" in name:
        return "statshub_raw_team_events"
    if "lineup" in name:
        return "statshub_raw_lineups"
    if "extra" in name:
        return "statshub_raw_event_extra_stats"
    return "statshub_raw_events"


def error_payload(item: dict[str, Any]) -> bool:
    return set(item.keys()) <= {"error", "message", "statusCode", "status"} and ("error" in item or "message" in item)


def insert_snapshot_item(conn, endpoint_name: str, snapshot_name: str, item: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO statshub_snapshot_items (
            snapshot_id, endpoint_name, item_type, item_id, player_name, team_name,
            event_id, stat_type, raw_item_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            None,
            endpoint_name,
            detect_item_type(endpoint_name),
            str(find_common_field(item, ["id", "uuid", "fixtureId", "eventId"]) or ""),
            find_common_field(item, ["playerName", "player_name", "name", "player"]),
            find_common_field(item, ["teamName", "team_name", "team"]),
            str(find_common_field(item, ["eventId", "event_id", "fixtureId"]) or ""),
            find_common_field(item, ["statType", "stat_type", "market", "type"]),
            raw(item),
            utc_now(),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--snapshot-name", required=True)
    args = parser.parse_args()
    path = Path(args.file)
    payload = parse_json_if_possible(path.read_text(encoding="utf-8", errors="ignore"))
    if payload is None:
        raise SystemExit("JSON invalido.")
    if isinstance(payload, dict) and error_payload(payload):
        raise SystemExit("Payload de error; no se importa como performance real.")
    items = [item for item in best_items(payload) if isinstance(item, dict) and not error_payload(item)]
    table = endpoint_table(args.endpoint_name)
    counts: dict[str, int] = {}
    init_db()
    imported_at = utc_now()
    with get_connection() as conn:
        for item in items:
            insert_snapshot_item(conn, args.endpoint_name, args.snapshot_name, item)
            if table == "statshub_raw_player_tournaments":
                player_id = args.endpoint_name.split("_")[1] if args.endpoint_name.startswith("player_") else find_common_field(item, ["playerId"])
                conn.execute(
                    "INSERT INTO statshub_raw_player_tournaments (player_id, player_name, team_id, team_name, endpoint_name, snapshot_name, raw_json, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (player_id, find_common_field(item, ["playerName", "name"]), find_common_field(item, ["teamId"]), find_common_field(item, ["teamName"]), args.endpoint_name, args.snapshot_name, raw(item), imported_at),
                )
            elif table == "statshub_raw_team_tournaments":
                team_id = args.endpoint_name.split("_")[1] if args.endpoint_name.startswith("team_") else find_common_field(item, ["teamId"])
                conn.execute(
                    "INSERT INTO statshub_raw_team_tournaments (team_id, team_name, endpoint_name, snapshot_name, raw_json, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (team_id, find_common_field(item, ["teamName", "name"]), args.endpoint_name, args.snapshot_name, raw(item), imported_at),
                )
            elif table == "statshub_raw_referees":
                conn.execute(
                    "INSERT INTO statshub_raw_referees (referee_id, referee_name, next_game_id, endpoint_name, snapshot_name, raw_json, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (find_common_field(item, ["refereeId", "id"]), find_common_field(item, ["refereeName", "name"]), find_common_field(item, ["nextGameId", "next_game_id", "eventId"]), args.endpoint_name, args.snapshot_name, raw(item), imported_at),
                )
            elif table == "statshub_raw_players":
                conn.execute(
                    "INSERT INTO statshub_raw_players (player_id, player_name, team_id, team_name, event_id, endpoint_name, snapshot_name, raw_json, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (find_common_field(item, ["playerId", "id"]), find_common_field(item, ["playerName", "name"]), find_common_field(item, ["teamId"]), find_common_field(item, ["teamName"]), find_common_field(item, ["eventId"]), args.endpoint_name, args.snapshot_name, raw(item), imported_at),
                )
            elif table == "statshub_raw_player_performance":
                conn.execute(
                    "INSERT INTO statshub_raw_player_performance (player_id, player_name, team_id, team_name, tournament_id, endpoint_name, snapshot_name, raw_json, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (find_common_field(item, ["playerId", "id"]), find_common_field(item, ["playerName", "name"]), find_common_field(item, ["teamId"]), find_common_field(item, ["teamName"]), find_common_field(item, ["tournamentId"]), args.endpoint_name, args.snapshot_name, raw(item), imported_at),
                )
                conn.execute(
                    "INSERT INTO statshub_raw_worldcup_player_performance (player_id, player_name, team_id, team_name, tournament_id, tournament_name, season_id, endpoint_name, snapshot_name, raw_json, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (find_common_field(item, ["playerId", "id"]), find_common_field(item, ["playerName", "name"]), find_common_field(item, ["teamId"]), find_common_field(item, ["teamName"]), find_common_field(item, ["tournamentId"]), find_common_field(item, ["tournamentName"]), find_common_field(item, ["seasonId"]), args.endpoint_name, args.snapshot_name, raw(item), imported_at),
                )
            elif table == "statshub_raw_lineups":
                conn.execute(
                    "INSERT INTO statshub_raw_lineups (event_id, team_id, player_id, player_name, lineup_type, endpoint_name, snapshot_name, raw_json, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (find_common_field(item, ["eventId"]), find_common_field(item, ["teamId"]), find_common_field(item, ["playerId", "id"]), find_common_field(item, ["playerName", "name"]), args.endpoint_name, args.endpoint_name, args.snapshot_name, raw(item), imported_at),
                )
            elif table == "statshub_raw_team_events":
                conn.execute(
                    "INSERT INTO statshub_raw_team_events (team_id, event_id, endpoint_name, snapshot_name, raw_json, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (find_common_field(item, ["teamId"]), find_common_field(item, ["eventId", "id"]), args.endpoint_name, args.snapshot_name, raw(item), imported_at),
                )
            elif table == "statshub_raw_event_extra_stats":
                conn.execute(
                    "INSERT INTO statshub_raw_event_extra_stats (event_id, endpoint_name, snapshot_name, raw_json, imported_at) VALUES (?, ?, ?, ?, ?)",
                    (find_common_field(item, ["eventId"]), args.endpoint_name, args.snapshot_name, raw(item), imported_at),
                )
            else:
                conn.execute(
                    "INSERT INTO statshub_raw_events (event_id, endpoint_name, snapshot_name, raw_json, imported_at) VALUES (?, ?, ?, ?, ?)",
                    (find_common_field(item, ["eventId", "id", "fixtureId"]), args.endpoint_name, args.snapshot_name, raw(item), imported_at),
                )
                ids = extract_ids(item)
                for team in ids["teams"].values():
                    conn.execute(
                        "INSERT INTO statshub_raw_teams (team_id, team_name, endpoint_name, snapshot_name, raw_json, imported_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (team.get("team_id"), team.get("team_name"), args.endpoint_name, args.snapshot_name, raw(team.get("raw") or team), imported_at),
                    )
            counts[table] = counts.get(table, 0) + 1
    print("IMPORT STATSHUB RAW SNAPSHOT")
    print("Este comando no consume API.")
    for name, count in counts.items():
        print(f"{name}: {count}")


if __name__ == "__main__":
    main()
