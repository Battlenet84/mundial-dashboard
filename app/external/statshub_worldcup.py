from __future__ import annotations

import json
from typing import Any

from app.external.statshub_snapshot import find_common_field, iter_arrays


def raw(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def is_worldcup_event(item: dict[str, Any]) -> bool:
    unique_id = find_common_field(item, ["uniqueTournamentId", "unique_tournament_id"])
    if str(unique_id) == "16":
        return True
    for key in ["uniqueTournament", "tournament", "league"]:
        value = item.get(key)
        if isinstance(value, dict):
            name = str(value.get("name") or "")
            if "fifa world cup" in name.lower():
                return True
    name = str(find_common_field(item, ["uniqueTournamentName", "tournamentName", "leagueName"]) or "")
    return "fifa world cup" in name.lower()


def event_id(item: dict[str, Any]) -> str | None:
    value = find_common_field(item, ["eventId", "event_id", "fixtureId", "id"])
    return str(value) if value is not None else None


def event_teams(item: dict[str, Any]) -> list[dict[str, Any]]:
    teams = []
    for key in ["homeTeam", "awayTeam", "home", "away"]:
        value = item.get(key)
        if isinstance(value, dict):
            team_id = find_common_field(value, ["id", "teamId"])
            team_name = find_common_field(value, ["name", "teamName"])
            if team_id is not None:
                teams.append({"team_id": str(team_id), "team_name": team_name, "raw": value})
    for key in ["teams", "participants"]:
        value = item.get(key)
        if isinstance(value, list):
            for team in value:
                if isinstance(team, dict):
                    team_id = find_common_field(team, ["id", "teamId"])
                    team_name = find_common_field(team, ["name", "teamName"])
                    if team_id is not None:
                        teams.append({"team_id": str(team_id), "team_name": team_name, "raw": team})
    return teams


def event_players_from_raw(player_rows, worldcup_team_ids: set[str]) -> list[dict[str, Any]]:
    players = []
    for row in player_rows:
        team_id = str(row["team_id"] or "")
        if team_id in worldcup_team_ids:
            players.append({
                "player_id": row["player_id"],
                "player_name": row["player_name"],
                "team_id": row["team_id"],
                "team_name": row["team_name"],
                "event_id": row["event_id"],
                "raw_json": row["raw_json"],
            })
    return players


def find_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    arrays = [(path, items) for path, items in iter_arrays(payload) if items]
    if arrays:
        return [item for item in max(arrays, key=lambda pair: len(pair[1]))[1] if isinstance(item, dict)]
    return [payload] if isinstance(payload, dict) else []

