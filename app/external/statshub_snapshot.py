from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

from app.config.settings import ROOT_DIR


ALLOWED_HOSTS = {"statshub.com", "www.statshub.com"}
SENSITIVE_PARAMS = {"token", "session", "auth", "key", "secret", "cf_clearance"}


def validate_statshub_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Solo se permite HTTPS.")
    if parsed.netloc.lower() not in ALLOWED_HOSTS:
        raise ValueError("Host no permitido para StatsHub.")
    params = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    blocked = params & SENSITIVE_PARAMS
    if blocked:
        raise ValueError(f"Parametros sensibles no permitidos: {sorted(blocked)}")


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def cache_path(url: str) -> Path:
    return ROOT_DIR / "data" / "raw" / "statshub" / "cache" / f"{url_hash(url)}.json"


def snapshot_path(snapshot_name: str, endpoint_name: str, timestamp: str, suffix: str) -> Path:
    safe_snapshot = re.sub(r"[^A-Za-z0-9_.-]+", "_", snapshot_name)
    safe_endpoint = re.sub(r"[^A-Za-z0-9_.-]+", "_", endpoint_name)
    return ROOT_DIR / "data" / "raw" / "statshub" / "snapshots" / safe_snapshot / f"{safe_endpoint}_{timestamp}.{suffix}"


def looks_like_json_text(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")


def parse_json_if_possible(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def top_keys(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return sorted(str(key) for key in payload.keys())
    return []


def iter_arrays(payload: Any, path: str = "$"):
    if isinstance(payload, list):
        yield path, payload
        for index, item in enumerate(payload[:20]):
            yield from iter_arrays(item, f"{path}[{index}]")
    elif isinstance(payload, dict):
        for key, value in payload.items():
            yield from iter_arrays(value, f"{path}.{key}")


def rows_detected(payload: Any) -> int:
    arrays = list(iter_arrays(payload))
    if isinstance(payload, list):
        return len(payload)
    return max((len(value) for _, value in arrays), default=0)


def classify_response(status_code: int | None, content_type: str, text: str, payload: Any | None) -> str:
    lower = text[:1000].lower()
    if status_code in {401, 403, 429} or (payload is None and ("cloudflare" in lower or "challenge" in lower)):
        return "blocked"
    if status_code == 503:
        return "unstable"
    if payload is None:
        return "not_json"
    if status_code == 200:
        return "ok"
    return "error"


def detect_item_type(endpoint_name: str) -> str:
    name = endpoint_name.lower()
    if "referees" in name:
        return "referee"
    if "event_by_date" in name or "by-date" in name:
        return "event"
    if "player_trends" in name or "player-trends" in name:
        return "prop_trend"
    if "screener" in name:
        return "prop_screener"
    if "performance" in name:
        return "player_performance"
    if "player_odds" in name or "player-odds" in name:
        return "player_odds"
    if "kickoff" in name:
        return "world_cup_info"
    if "tournament" in name:
        return "tournament_or_fixture"
    return "unknown"


def find_common_field(item: dict[str, Any], names: list[str]) -> Any:
    lower = {str(key).lower(): key for key in item.keys()}
    for name in names:
        if name.lower() in lower:
            return item[lower[name.lower()]]
    for value in item.values():
        if isinstance(value, dict):
            found = find_common_field(value, names)
            if found is not None:
                return found
    return None


def extract_ids(payload: Any) -> dict[str, dict[str, dict[str, Any]]]:
    found = {
        "events": {},
        "teams": {},
        "players": {},
        "referees": {},
        "tournaments": {},
        "seasons": {},
    }

    def visit(value: Any):
        if isinstance(value, dict):
            event_id = find_common_field(value, ["eventId", "event_id", "fixtureId", "gameId", "id"])
            if event_id is not None and any(key.lower() in {"hometeam", "awayteam", "starttime", "timestamp", "eventid"} for key in value.keys()):
                found["events"][str(event_id)] = {"event_id": str(event_id), "raw": value}

            for prefix in ["home", "away", "team"]:
                obj = value.get(prefix) or value.get(f"{prefix}Team")
                if isinstance(obj, dict):
                    team_id = find_common_field(obj, ["id", "teamId"])
                    team_name = find_common_field(obj, ["name", "teamName"])
                    if team_id is not None:
                        found["teams"][str(team_id)] = {"team_id": str(team_id), "team_name": team_name, "raw": obj}

            team_id = find_common_field(value, ["teamId", "team_id"])
            team_name = find_common_field(value, ["teamName", "team_name"])
            if team_id is not None:
                found["teams"][str(team_id)] = {"team_id": str(team_id), "team_name": team_name, "raw": value}

            player_id = find_common_field(value, ["playerId", "player_id"])
            player_name = find_common_field(value, ["playerName", "player_name", "player"])
            if player_id is not None or player_name is not None:
                key = str(player_id or player_name)
                found["players"][key] = {"player_id": str(player_id) if player_id is not None else None, "player_name": player_name, "team_id": str(team_id) if team_id is not None else None, "team_name": team_name, "raw": value}

            referee_id = find_common_field(value, ["refereeId", "referee_id"])
            referee_name = find_common_field(value, ["refereeName", "referee_name", "referee"])
            if referee_id is not None or referee_name is not None:
                key = str(referee_id or referee_name)
                found["referees"][key] = {"referee_id": str(referee_id) if referee_id is not None else None, "referee_name": referee_name, "raw": value}

            tournament_id = find_common_field(value, ["tournamentId", "tournament_id"])
            if tournament_id is not None:
                found["tournaments"][str(tournament_id)] = {"tournament_id": str(tournament_id), "raw": value}

            season_id = find_common_field(value, ["seasonId", "season_id"])
            if season_id is not None:
                found["seasons"][str(season_id)] = {"season_id": str(season_id), "raw": value}

            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return found
