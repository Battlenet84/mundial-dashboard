from __future__ import annotations

import argparse

from app.db.connection import get_connection, init_db
from app.db.queries import utc_now
from app.external.statshub_worldcup import event_players_from_raw, event_teams, is_worldcup_event, raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-name", required=True)
    args = parser.parse_args()
    init_db()
    imported_at = utc_now()
    teams_count = players_count = events_seen = events_wc = 0
    with get_connection() as conn:
        events = conn.execute(
            "SELECT event_id, raw_json FROM statshub_raw_events WHERE snapshot_name = ?",
            (args.snapshot_name,),
        ).fetchall()
        conn.execute("DELETE FROM statshub_worldcup_teams")
        conn.execute("DELETE FROM statshub_worldcup_players")
        wc_team_ids = set()
        seen_teams = set()
        for event in events:
            events_seen += 1
            item = __import__("json").loads(event["raw_json"])
            if not is_worldcup_event(item):
                continue
            events_wc += 1
            source_event_id = event["event_id"]
            for team in event_teams(item):
                if team["team_id"] in seen_teams:
                    continue
                seen_teams.add(team["team_id"])
                wc_team_ids.add(team["team_id"])
                conn.execute(
                    "INSERT INTO statshub_worldcup_teams (team_id, team_name, source_event_id, raw_json, imported_at) VALUES (?, ?, ?, ?, ?)",
                    (team["team_id"], team["team_name"], source_event_id, raw(team["raw"]), imported_at),
                )
                teams_count += 1
        player_rows = conn.execute("SELECT player_id, player_name, team_id, team_name, event_id, raw_json FROM statshub_raw_players").fetchall()
        seen_players = set()
        for player in event_players_from_raw(player_rows, wc_team_ids):
            key = player["player_id"] or f"{player['player_name']}|{player['team_id']}"
            if key in seen_players:
                continue
            seen_players.add(key)
            conn.execute(
                "INSERT INTO statshub_worldcup_players (player_id, player_name, team_id, team_name, source_event_id, raw_json, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (player["player_id"], player["player_name"], player["team_id"], player["team_name"], player["event_id"], player["raw_json"], imported_at),
            )
            players_count += 1
    print("BUILD STATSHUB WORLDCUP SEED")
    print("Este comando no consume API.")
    print(f"Eventos vistos: {events_seen}")
    print(f"Eventos World Cup: {events_wc}")
    print(f"World Cup teams seed: {teams_count}")
    print(f"World Cup players seed: {players_count}")


if __name__ == "__main__":
    main()
