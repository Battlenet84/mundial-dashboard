from __future__ import annotations

from typing import Any

from app.normalizers.api_football import normalize_fixture, normalize_team


PROVIDER = "api_football"


def normalize_player(item: dict[str, Any]) -> dict[str, Any]:
    player = item.get("player") or {}
    team = item.get("statistics", [{}])[0].get("team", {}) if item.get("statistics") else {}
    birth = player.get("birth") or {}
    return {
        "provider": PROVIDER,
        "provider_player_id": player.get("id"),
        "provider_team_id": team.get("id"),
        "name": player.get("name"),
        "firstname": player.get("firstname"),
        "lastname": player.get("lastname"),
        "age": player.get("age"),
        "birth_date": birth.get("date"),
        "nationality": player.get("nationality"),
        "position": None,
        "height": player.get("height"),
        "weight": player.get("weight"),
        "injured": int(bool(player.get("injured"))) if player.get("injured") is not None else None,
        "photo": player.get("photo"),
    }


def normalize_injury(item: dict[str, Any]) -> dict[str, Any]:
    player = item.get("player") or {}
    team = item.get("team") or {}
    fixture = item.get("fixture") or {}
    return {
        "provider": PROVIDER,
        "provider_player_id": player.get("id"),
        "player_name": player.get("name"),
        "provider_team_id": team.get("id"),
        "team_name": team.get("name"),
        "fixture_provider_id": fixture.get("id"),
        "reason": item.get("reason"),
        "type": item.get("type"),
        "raw_status": item.get("status"),
    }
