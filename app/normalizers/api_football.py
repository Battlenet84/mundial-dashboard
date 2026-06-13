from __future__ import annotations

import hashlib
import json
from typing import Any


PROVIDER = "api_football"


def _raw(item: dict[str, Any]) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)


def _hash(item: dict[str, Any]) -> str:
    return hashlib.sha256(_raw(item).encode("utf-8")).hexdigest()


def normalize_team(payload_item: dict[str, Any]) -> dict[str, Any]:
    team = payload_item.get("team") or payload_item
    venue = payload_item.get("venue") or {}
    return {
        "provider": PROVIDER,
        "provider_team_id": team.get("id"),
        "name": team.get("name"),
        "country": team.get("country"),
        "code": team.get("code"),
        "national": int(bool(team.get("national"))) if team.get("national") is not None else None,
        "founded": team.get("founded"),
        "logo": team.get("logo"),
        "venue_id": venue.get("id"),
        "venue_name": venue.get("name"),
        "venue_city": venue.get("city"),
        "source_type": "api",
        "raw_json": _raw(payload_item),
    }


def normalize_fixture(payload_item: dict[str, Any]) -> dict[str, Any]:
    fixture = payload_item.get("fixture") or {}
    status = fixture.get("status") or {}
    venue = fixture.get("venue") or {}
    teams = payload_item.get("teams") or {}
    goals = payload_item.get("goals") or {}
    score = payload_item.get("score") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    return {
        "provider": PROVIDER,
        "provider_fixture_id": fixture.get("id"),
        "date_utc": fixture.get("date"),
        "round": (payload_item.get("league") or {}).get("round"),
        "group_name": (payload_item.get("league") or {}).get("name"),
        "timezone": fixture.get("timezone"),
        "venue_id": venue.get("id"),
        "status_short": status.get("short"),
        "status_long": status.get("long"),
        "elapsed": status.get("elapsed"),
        "venue_name": venue.get("name"),
        "venue_city": venue.get("city"),
        "referee_raw": fixture.get("referee"),
        "home_team_provider_id": home.get("id"),
        "away_team_provider_id": away.get("id"),
        "home_team_name": home.get("name"),
        "away_team_name": away.get("name"),
        "home_goals": goals.get("home"),
        "away_goals": goals.get("away"),
        "score_halftime_home": (score.get("halftime") or {}).get("home"),
        "score_halftime_away": (score.get("halftime") or {}).get("away"),
        "score_fulltime_home": (score.get("fulltime") or {}).get("home"),
        "score_fulltime_away": (score.get("fulltime") or {}).get("away"),
        "score_extratime_home": (score.get("extratime") or {}).get("home"),
        "score_extratime_away": (score.get("extratime") or {}).get("away"),
        "score_penalty_home": (score.get("penalty") or {}).get("home"),
        "score_penalty_away": (score.get("penalty") or {}).get("away"),
        "source_type": "api",
        "raw_json": _raw(payload_item),
    }


def normalize_squad_player(team_payload: dict[str, Any], player_item: dict[str, Any]) -> dict[str, Any]:
    team = team_payload.get("team") or {}
    return {
        "provider": PROVIDER,
        "provider_player_id": player_item.get("id"),
        "provider_team_id": team.get("id"),
        "team_name": team.get("name"),
        "name": player_item.get("name"),
        "firstname": None,
        "lastname": None,
        "age": player_item.get("age"),
        "birth_date": None,
        "birth_place": None,
        "birth_country": None,
        "nationality": None,
        "position": player_item.get("position"),
        "number": player_item.get("number"),
        "height": None,
        "weight": None,
        "injured": None,
        "photo": player_item.get("photo"),
        "source_type": "api",
        "raw_json": _raw({"team": team, "player": player_item}),
    }


def normalize_player_season_stats(payload_item: dict[str, Any], season: int) -> list[dict[str, Any]]:
    player = payload_item.get("player") or {}
    rows = []
    for stat in payload_item.get("statistics", []) or []:
        team = stat.get("team") or {}
        league = stat.get("league") or {}
        games = stat.get("games") or {}
        substitutes = stat.get("substitutes") or {}
        shots = stat.get("shots") or {}
        goals = stat.get("goals") or {}
        passes = stat.get("passes") or {}
        tackles = stat.get("tackles") or {}
        duels = stat.get("duels") or {}
        dribbles = stat.get("dribbles") or {}
        fouls = stat.get("fouls") or {}
        cards = stat.get("cards") or {}
        penalty = stat.get("penalty") or {}
        raw = {"player": player, "statistics": stat}
        rows.append({
            "provider": PROVIDER,
            "provider_player_id": player.get("id"),
            "player_name": player.get("name"),
            "season": season,
            "provider_team_id": team.get("id"),
            "team_name": team.get("name"),
            "league_id": league.get("id"),
            "league_name": league.get("name"),
            "league_country": league.get("country"),
            "league_season": league.get("season"),
            "league_type": league.get("type"),
            "league_logo": league.get("logo"),
            "appearances": games.get("appearences") or games.get("appearances"),
            "lineups": games.get("lineups"),
            "minutes": games.get("minutes"),
            "number": games.get("number"),
            "position": games.get("position"),
            "rating": float(games["rating"]) if games.get("rating") not in (None, "") else None,
            "captain": int(bool(games.get("captain"))) if games.get("captain") is not None else None,
            "substitutes_in": substitutes.get("in"),
            "substitutes_out": substitutes.get("out"),
            "substitutes_bench": substitutes.get("bench"),
            "shots_total": shots.get("total"),
            "shots_on": shots.get("on"),
            "goals_total": goals.get("total"),
            "goals_conceded": goals.get("conceded"),
            "goals_assists": goals.get("assists"),
            "goals_saves": goals.get("saves"),
            "passes_total": passes.get("total"),
            "passes_key": passes.get("key"),
            "passes_accuracy": passes.get("accuracy"),
            "tackles_total": tackles.get("total"),
            "tackles_blocks": tackles.get("blocks"),
            "tackles_interceptions": tackles.get("interceptions"),
            "duels_total": duels.get("total"),
            "duels_won": duels.get("won"),
            "dribbles_attempts": dribbles.get("attempts"),
            "dribbles_success": dribbles.get("success"),
            "dribbles_past": dribbles.get("past"),
            "fouls_drawn": fouls.get("drawn"),
            "fouls_committed": fouls.get("committed"),
            "cards_yellow": cards.get("yellow"),
            "cards_yellowred": cards.get("yellowred"),
            "cards_red": cards.get("red"),
            "penalty_won": penalty.get("won"),
            "penalty_committed": penalty.get("commited") or penalty.get("committed"),
            "penalty_scored": penalty.get("scored"),
            "penalty_missed": penalty.get("missed"),
            "penalty_saved": penalty.get("saved"),
            "raw_json": _raw(raw),
            "raw_payload_hash": _hash(raw),
        })
    return rows

