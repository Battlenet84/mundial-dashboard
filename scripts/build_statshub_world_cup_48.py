from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd

from app.config.settings import ROOT_DIR
from app.db.connection import get_connection, init_db
from app.db.queries import utc_now


SNAPSHOT_NAME = "world_cup_48_teams_limit50_probe"
OUTPUT_FILE = Path("data/processed/statshub/world_cup_48_teams_limit50_review.xlsx")
BASE = "https://www.statshub.com"

WORLD_CUP_TEAMS = [
    ("A", "Mexico"),
    ("A", "South Africa"),
    ("A", "South Korea"),
    ("A", "Czechia"),
    ("B", "Canada"),
    ("B", "Bosnia and Herzegovina"),
    ("B", "Qatar"),
    ("B", "Switzerland"),
    ("C", "Brazil"),
    ("C", "Morocco"),
    ("C", "Haiti"),
    ("C", "Scotland"),
    ("D", "United States"),
    ("D", "Paraguay"),
    ("D", "Australia"),
    ("D", "Turkiye"),
    ("E", "Germany"),
    ("E", "Curacao"),
    ("E", "Ivory Coast"),
    ("E", "Ecuador"),
    ("F", "Netherlands"),
    ("F", "Japan"),
    ("F", "Sweden"),
    ("F", "Tunisia"),
    ("G", "Belgium"),
    ("G", "Egypt"),
    ("G", "Iran"),
    ("G", "New Zealand"),
    ("H", "Spain"),
    ("H", "Cape Verde"),
    ("H", "Saudi Arabia"),
    ("H", "Uruguay"),
    ("I", "France"),
    ("I", "Senegal"),
    ("I", "Iraq"),
    ("I", "Norway"),
    ("J", "Argentina"),
    ("J", "Algeria"),
    ("J", "Austria"),
    ("J", "Jordan"),
    ("K", "Portugal"),
    ("K", "Congo DR"),
    ("K", "Uzbekistan"),
    ("K", "Colombia"),
    ("L", "England"),
    ("L", "Croatia"),
    ("L", "Ghana"),
    ("L", "Panama"),
]

ALIASES = {
    "united states": ["USA", "United States"],
    "south korea": ["South Korea", "Korea Republic"],
    "turkiye": ["Turkiye", "Turkey", "Türkiye"],
    "curacao": ["Curacao", "Curaçao"],
    "ivory coast": ["Ivory Coast", "Cote d Ivoire", "Côte d’Ivoire"],
    "czechia": ["Czechia", "Czech Republic"],
    "congo dr": ["Congo DR", "DR Congo", "Democratic Republic of the Congo"],
    "iran": ["Iran", "IR Iran"],
    "saudi arabia": ["Saudi Arabia", "Saudi"],
    "cape verde": ["Cape Verde", "Cabo Verde"],
}

METRIC_MAP = {
    "expectedGoals": "expected_goals",
    "totalShotsOnGoal": "shots",
    "shotsOnGoal": "shots_on_target",
    "shotsOffGoal": "shots_off_target",
    "fouls": "fouls",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "totalTackle": "total_tackles",
    "passes": "total_passes",
    "accuratePasses": "accurate_passes",
    "pass_accuracy": "pass_accuracy",
    "ballPossession": "possession_avg",
    "cornerKicks": "corners",
    "goalkeeperSaves": "goalkeeper_saves",
    "finalThirdEntries": "final_third_entries",
}


def norm(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def url_search(team_name: str) -> str:
    return f"{BASE}/api/search?q={quote_plus(team_name)}"


def url_performance(team_id: str) -> str:
    return f"{BASE}/api/team/{team_id}/performance?limit=50"


def url_team_players(team_id: str) -> str:
    return f"{BASE}/api/team/{team_id}/players"


def run_download(endpoint_name: str, target_url: str, execute: bool) -> None:
    env = os.environ.copy()
    env["STATSHUB_ENABLED"] = "true"
    env.setdefault("STATSHUB_MIN_SECONDS_BETWEEN_REQUESTS", "2")
    env.setdefault("STATSHUB_CACHE_ENABLED", "true")
    env.setdefault("STATSHUB_MAX_REQUESTS_PER_RUN", "1")
    command = [
        sys.executable,
        "-m",
        "scripts.download_statshub_snapshot",
        "--snapshot-name",
        SNAPSHOT_NAME,
        "--endpoint-name",
        endpoint_name,
        "--url",
        target_url,
    ]
    if execute:
        command.append("--execute")
    result = subprocess.run(command, cwd=ROOT_DIR, env=env, capture_output=True, text=True, check=False)
    lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    print(f"{endpoint_name}: code={result.returncode} {' | '.join(lines[-4:])}")


def latest_snapshot(endpoint_name: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM statshub_snapshots
            WHERE snapshot_name = ? AND endpoint_name = ?
            ORDER BY id DESC LIMIT 1
            """,
            (SNAPSHOT_NAME, endpoint_name),
        ).fetchone()
    return dict(row) if row else None


def load_payload(source: dict[str, Any] | None) -> Any | None:
    if not source or not source.get("raw_file_path"):
        return None
    path = Path(source["raw_file_path"])
    if path.suffix != ".json" or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8", errors="ignore"))


def search_endpoint_name(team_name: str) -> str:
    return "search_" + re.sub(r"[^A-Za-z0-9]+", "_", norm(team_name)).strip("_")


def local_candidates() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with get_connection() as conn:
        rows = conn.execute("SELECT team_id, team_name, raw_json, endpoint_name, snapshot_name FROM statshub_raw_teams").fetchall()
    for row in rows:
        raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
        if raw.get("national") is not True:
            continue
        names = {row["team_name"], raw.get("name"), raw.get("shortname"), raw.get("slug"), raw.get("countrySlug")}
        candidate = {
            "team_id": str(row["team_id"]),
            "team_name": row["team_name"],
            "slug": raw.get("slug"),
            "source": f"{row['endpoint_name']}/{row['snapshot_name']}",
        }
        for name in names:
            key = norm(str(name)) if name else ""
            if key:
                out[key].append(candidate)
    return out


def fixture_candidates(team_name: str) -> list[dict[str, Any]]:
    source = latest_snapshot(search_endpoint_name(team_name))
    payload = load_payload(source)
    if not isinstance(payload, dict):
        return []
    wanted = [norm(team_name)] + [norm(alias) for alias in ALIASES.get(norm(team_name), [])]
    found: dict[str, dict[str, Any]] = {}
    for fixture in payload.get("fixtures", []) or []:
        if not isinstance(fixture, dict) or str(fixture.get("tournamentId")) != "16":
            continue
        pairs = [
            (fixture.get("homeTeamName"), fixture.get("homeTeamSlug"), fixture.get("homeTeamId")),
            (fixture.get("awayTeamName"), fixture.get("awayTeamSlug"), fixture.get("awayTeamId")),
        ]
        for name, slug, team_id in pairs:
            if norm(str(name)) in wanted or norm(str(slug)) in wanted:
                found[str(team_id)] = {
                    "team_id": str(team_id),
                    "team_name": str(name),
                    "slug": slug,
                    "source": f"StatsHub search fixture {source['raw_file_path']}",
                }
    return list(found.values())


def team_list_candidates(team_name: str) -> list[dict[str, Any]]:
    source = latest_snapshot(search_endpoint_name(team_name))
    payload = load_payload(source)
    if not isinstance(payload, dict):
        return []
    wanted = [norm(team_name)] + [norm(alias) for alias in ALIASES.get(norm(team_name), [])]
    found = {}
    for item in payload.get("teams", []) or []:
        if not isinstance(item, dict):
            continue
        if norm(str(item.get("name"))) in wanted or norm(str(item.get("slug"))) in wanted:
            found[str(item.get("id"))] = {
                "team_id": str(item.get("id")),
                "team_name": item.get("name"),
                "slug": item.get("slug"),
                "source": f"StatsHub search team {source['raw_file_path']}",
            }
    return list(found.values())


def resolve_team(team_name: str, locals_by_name: dict[str, list[dict[str, Any]]]) -> tuple[str, list[dict[str, Any]]]:
    wanted = [norm(team_name)] + [norm(alias) for alias in ALIASES.get(norm(team_name), [])]
    candidates: dict[str, dict[str, Any]] = {}
    fixture_hits = fixture_candidates(team_name)
    if len(fixture_hits) == 1:
        return "matched", fixture_hits
    if len(fixture_hits) > 1:
        return "ambiguous", fixture_hits
    for candidate in team_list_candidates(team_name):
        if candidate.get("team_id"):
            candidates[candidate["team_id"]] = candidate
    if not candidates:
        for key in wanted:
            for candidate in locals_by_name.get(key, []):
                candidates[candidate["team_id"]] = candidate
    values = list(candidates.values())
    if len(values) == 1:
        return "matched", values
    if len(values) > 1:
        return "ambiguous", values
    return "unresolved", []


def ensure_schema() -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS statshub_world_cup_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT,
                world_cup_year INTEGER,
                team_name TEXT,
                team_name_canonical TEXT,
                country_code TEXT,
                group_name TEXT,
                source TEXT,
                source_confidence TEXT,
                statshub_team_id TEXT,
                statshub_team_slug TEXT,
                statshub_match_status TEXT,
                notes TEXT,
                raw_json TEXT,
                imported_at TEXT
            )
            """
        )
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(statshub_world_cup_teams)").fetchall()}
        required = {
            "world_cup_year": "INTEGER",
            "team_name_canonical": "TEXT",
            "country_code": "TEXT",
            "group_name": "TEXT",
            "source_confidence": "TEXT",
            "statshub_team_id": "TEXT",
            "statshub_team_slug": "TEXT",
            "statshub_match_status": "TEXT",
            "notes": "TEXT",
        }
        for col, typ in required.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE statshub_world_cup_teams ADD COLUMN {col} {typ}")
        player_cols = {row["name"] for row in conn.execute("PRAGMA table_info(statshub_team_players)").fetchall()}
        player_required = {
            "world_cup_year": "INTEGER",
            "player_name_canonical": "TEXT",
            "source": "TEXT",
            "source_confidence": "TEXT",
            "statshub_player_id_status": "TEXT",
            "notes": "TEXT",
        }
        for col, typ in player_required.items():
            if col not in player_cols:
                conn.execute(f"ALTER TABLE statshub_team_players ADD COLUMN {col} {typ}")


def event_timestamp(row: dict[str, Any]) -> int | None:
    event = row.get("event") or row.get("events") or {}
    try:
        return int(event.get("timeStartTimestamp") or event.get("startTimestamp"))
    except (TypeError, ValueError):
        return None


def iso_date(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def maybe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def performance_rows(team_id: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    source = latest_snapshot(f"team_{team_id}_performance_limit50")
    payload = load_payload(source)
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    return source, [row for row in rows if isinstance(row, dict)]


def aggregate(team: dict[str, Any]) -> dict[str, Any]:
    source, rows = performance_rows(team["statshub_team_id"])
    dates = [iso_date(ts) for ts in (event_timestamp(row) for row in rows) if ts is not None]
    comps = sorted({(row.get("league") or {}).get("name") for row in rows if isinstance(row.get("league"), dict) and (row.get("league") or {}).get("name")})
    out = {
        "snapshot_name": SNAPSHOT_NAME,
        "endpoint_name": f"team_{team['statshub_team_id']}_performance_limit50",
        "team_id": team["statshub_team_id"],
        "team_name": team["team_name"],
        "source_rows": len(rows),
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "competitions_detected": json.dumps(comps, ensure_ascii=False),
        "matches_in_window": len(rows),
        "raw_file": source["raw_file_path"] if source else None,
    }
    for original, alias in METRIC_MAP.items():
        values = [maybe_float((row.get("statistics") or {}).get(original)) for row in rows]
        values = [value for value in values if value is not None]
        out[alias] = sum(values) / len(values) if alias in {"pass_accuracy", "possession_avg"} and values else sum(values) if values else None
        opp_values = [maybe_float((row.get("opponentStatistics") or {}).get(original)) for row in rows]
        opp_values = [value for value in opp_values if value is not None]
        out[f"opponent_{alias}"] = sum(opp_values) / len(opp_values) if alias in {"pass_accuracy", "possession_avg"} and opp_values else sum(opp_values) if opp_values else None
    return out


def event_records(team: dict[str, Any]) -> list[dict[str, Any]]:
    source, rows = performance_rows(team["statshub_team_id"])
    out = []
    for row in rows:
        event = row.get("event") or {}
        home = row.get("homeTeam") or {}
        away = row.get("awayTeam") or {}
        stats = row.get("statistics") or {}
        opp_stats = row.get("opponentStatistics") or {}
        team_id = str(team["statshub_team_id"])
        home_away = "home" if str(home.get("id")) == team_id else "away" if str(away.get("id")) == team_id else None
        opponent_obj = away if home_away == "home" else home if home_away == "away" else {}
        score = event.get("score") or {}
        goals_for = score.get("home") if home_away == "home" else score.get("away") if home_away == "away" else None
        goals_against = score.get("away") if home_away == "home" else score.get("home") if home_away == "away" else None
        record = {
            "snapshot_name": SNAPSHOT_NAME,
            "endpoint_name": f"team_{team_id}_performance_limit50",
            "team_id": team_id,
            "team_name": team["team_name"],
            "event_id": str(event.get("id")) if event.get("id") is not None else None,
            "event_date": iso_date(event_timestamp(row)),
            "competition": (row.get("league") or {}).get("name") if isinstance(row.get("league"), dict) else None,
            "opponent_team_id": str(opponent_obj.get("id")) if opponent_obj.get("id") is not None else None,
            "opponent_team_name": opponent_obj.get("name"),
            "home_away": home_away,
            "raw_file": source["raw_file_path"] if source else None,
            "raw_row_json": json.dumps(row, ensure_ascii=False),
            "goals_for": maybe_float(goals_for),
            "goals_against": maybe_float(goals_against),
            "expected_goals": maybe_float(stats.get("expectedGoals")),
            "expected_goals_against": maybe_float(opp_stats.get("expectedGoals")),
        }
        for original, alias in METRIC_MAP.items():
            if alias not in record:
                record[alias] = maybe_float(stats.get(original))
        out.append(record)
    return out


def squad_rows(registry_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with get_connection() as conn:
        seed = conn.execute("SELECT * FROM statshub_worldcup_players").fetchall()
    by_team = defaultdict(list)
    for row in seed:
        by_team[str(row["team_id"])].append(row)
    out = []
    for team in registry_rows:
        team_id = team.get("statshub_team_id")
        for row in by_team.get(str(team_id), []):
            raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
            out.append(
                {
                    "snapshot_name": SNAPSHOT_NAME,
                    "world_cup_year": 2026,
                    "team_id": team_id,
                    "team_name": team["team_name"],
                    "player_id": row["player_id"],
                    "player_name": row["player_name"],
                    "player_name_canonical": norm(row["player_name"]),
                    "position": raw.get("position"),
                    "jersey_number": raw.get("jerseyNumber"),
                    "source": "local statshub_worldcup_players seed",
                    "source_confidence": "partial_seed",
                    "statshub_player_id_status": "confirmed" if row["player_id"] else "missing",
                    "notes": "Identity/roster only; no player performance downloaded.",
                }
            )
    return out


def raw_sources(registry_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names_by_id = {str(row["statshub_team_id"]): row["team_name"] for row in registry_rows if row.get("statshub_team_id")}
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM statshub_snapshots WHERE snapshot_name = ? ORDER BY id", (SNAPSHOT_NAME,)).fetchall()
    out = []
    for row in rows:
        endpoint = row["endpoint_name"]
        team_id = None
        m = re.match(r"team_(\d+)_performance", endpoint)
        if m:
            team_id = m.group(1)
        _, perf_rows = performance_rows(team_id) if team_id else (None, [])
        dates = [iso_date(ts) for ts in (event_timestamp(item) for item in perf_rows) if ts is not None]
        comps = sorted({(item.get("league") or {}).get("name") for item in perf_rows if isinstance(item.get("league"), dict) and (item.get("league") or {}).get("name")})
        out.append(
            {
                "snapshot_name": SNAPSHOT_NAME,
                "endpoint_name": endpoint,
                "URL": row["url"],
                "url": row["url"],
                "status code": row["status_code"],
                "status_code": row["status_code"],
                "content type": row["content_type"],
                "content_type": row["content_type"],
                "response size": row["response_size"],
                "response_size": row["response_size"],
                "top keys": row["json_top_keys"],
                "top_keys": row["json_top_keys"],
                "rows detected": row["rows_detected"],
                "rows_detected": row["rows_detected"],
                "raw file": row["raw_file_path"],
                "raw_file": row["raw_file_path"],
                "classification/status": row["status"],
                "classification_status": row["status"],
                "team_id": team_id,
                "team_name": names_by_id.get(str(team_id)),
                "date_min": min(dates) if dates else None,
                "date_max": max(dates) if dates else None,
                "competitions detected": json.dumps(comps, ensure_ascii=False),
                "competitions_detected": json.dumps(comps, ensure_ascii=False),
                "useful metrics found": "yes" if perf_rows else "no",
                "useful_performance_metrics_found": "yes" if perf_rows else "no",
            }
        )
    return out


def data_dictionary(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    meanings = {
        "world_cup_year": "World Cup edition year",
        "team_name": "FIFA/standings team name",
        "group_name": "World Cup group",
        "statshub_team_id": "StatsHub team identifier",
        "match_status": "matched, unresolved, or ambiguous",
        "source": "registry or mapping source",
        "performance_status": "performance download status",
        "squad_status": "squad/player-list status",
    }
    for sheet_name, df in sheets.items():
        if sheet_name == "data_dictionary":
            continue
        for column in df.columns:
            rows.append(
                {
                    "sheet_name": sheet_name,
                    "column_name": column,
                    "original_json_path": "",
                    "inferred_type": "unknown" if df.empty else str(df[column].dropna().map(type).map(lambda x: x.__name__).head(1).iloc[0]) if not df[column].dropna().empty else "null",
                    "meaning": meanings.get(column, "unknown"),
                    "notes": "" if column in meanings else "unknown; preserved for review",
                }
            )
    return pd.DataFrame(rows)


def insert_common(table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        table_cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        cols = [col for col in table_cols if col in rows[0] or col == "imported_at"]
        if not cols:
            return
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
        now = utc_now()
        for row in rows:
            conn.execute(sql, [row.get(col) if col != "imported_at" else now for col in cols])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    ensure_schema()

    if args.execute:
        for _, team_name in WORLD_CUP_TEAMS:
            run_download(search_endpoint_name(team_name), url_search(team_name), execute=True)

    locals_by_name = local_candidates()
    registry_rows = []
    ambiguous_rows = []
    for group, team_name in WORLD_CUP_TEAMS:
        status, candidates = resolve_team(team_name, locals_by_name)
        selected = candidates[0] if status == "matched" else {}
        if status == "ambiguous":
            for candidate in candidates:
                ambiguous_rows.append({"team_name": team_name, "candidate_team_id": candidate["team_id"], "candidate_name": candidate["team_name"], "source": candidate["source"]})
        registry_rows.append(
            {
                "snapshot_name": SNAPSHOT_NAME,
                "world_cup_year": 2026,
                "team_name": team_name,
                "team_name_canonical": norm(team_name),
                "country_code": None,
                "group_name": group,
                "source": selected.get("source") or "FOX Sports standings + unresolved StatsHub search",
                "source_confidence": "external_standings_plus_statshub_search" if status == "matched" else "external_standings_only",
                "statshub_team_id": selected.get("team_id"),
                "statshub_team_slug": selected.get("slug"),
                "statshub_match_status": status,
                "notes": "" if status == "matched" else json.dumps(candidates, ensure_ascii=False),
                "raw_json": json.dumps(candidates, ensure_ascii=False),
            }
        )

    if args.execute:
        for row in registry_rows:
            if row["statshub_match_status"] == "matched" and row["statshub_team_id"]:
                run_download(f"team_{row['statshub_team_id']}_performance_limit50", url_performance(row["statshub_team_id"]), execute=True)
                run_download(f"team_{row['statshub_team_id']}_players", url_team_players(row["statshub_team_id"]), execute=True)

    aggregate_rows = [aggregate(row) for row in registry_rows if row.get("statshub_team_id") and row["statshub_match_status"] == "matched"]
    event_rows = []
    for row in registry_rows:
        if row.get("statshub_team_id") and row["statshub_match_status"] == "matched":
            event_rows.extend(event_records(row))
    players = squad_rows(registry_rows)
    players_by_team = defaultdict(int)
    for player in players:
        players_by_team[str(player["team_id"])] += 1

    registry_coverage = []
    for row in registry_rows:
        team_id = row.get("statshub_team_id")
        source = latest_snapshot(f"team_{team_id}_performance_limit50") if team_id else None
        registry_coverage.append(
            {
                "world_cup_year": 2026,
                "team_name": row["team_name"],
                "group_name": row["group_name"],
                "statshub_team_id": team_id,
                "match_status": row["statshub_match_status"],
                "source": row["source"],
                "source_confidence": row["source_confidence"],
                "performance_status": source["status"] if source else "missing",
                "squad_status": "available_local_seed" if players_by_team.get(str(team_id), 0) else "missing",
                "notes": row["notes"],
            }
        )

    unresolved = [row for row in registry_coverage if row["match_status"] == "unresolved"]
    raw_source_rows = raw_sources(registry_rows)

    with get_connection() as conn:
        conn.execute("DELETE FROM statshub_world_cup_teams WHERE snapshot_name = ?", (SNAPSHOT_NAME,))
        conn.execute("DELETE FROM statshub_team_performance_aggregates WHERE snapshot_name = ?", (SNAPSHOT_NAME,))
        conn.execute("DELETE FROM statshub_team_performance_events WHERE snapshot_name = ?", (SNAPSHOT_NAME,))
        conn.execute("DELETE FROM statshub_team_players WHERE snapshot_name = ?", (SNAPSHOT_NAME,))
        conn.execute("DELETE FROM statshub_raw_sources WHERE snapshot_name = ?", (SNAPSHOT_NAME,))
        cols = list(registry_rows[0].keys()) + ["imported_at"]
        sql = f"INSERT INTO statshub_world_cup_teams ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
        now = utc_now()
        for row in registry_rows:
            conn.execute(sql, [row.get(col) if col != "imported_at" else now for col in cols])
    insert_common("statshub_team_performance_aggregates", aggregate_rows)
    insert_common("statshub_team_performance_events", event_rows)
    insert_common("statshub_team_players", players)
    insert_common("statshub_raw_sources", raw_source_rows)

    sheets = {
        "registry_coverage": pd.DataFrame(registry_coverage),
        "team_performance_aggregates": pd.DataFrame(aggregate_rows),
        "team_players": pd.DataFrame(players),
        "unresolved_teams": pd.DataFrame(unresolved),
        "ambiguous_team_matches": pd.DataFrame(ambiguous_rows),
        "raw_sources": pd.DataFrame(raw_source_rows),
    }
    sheets["data_dictionary"] = data_dictionary(sheets)

    output = ROOT_DIR / OUTPUT_FILE
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name in ["registry_coverage", "team_performance_aggregates", "team_players", "unresolved_teams", "ambiguous_team_matches", "raw_sources", "data_dictionary"]:
            sheets[name].to_excel(writer, sheet_name=name, index=False)

    mapped = [row for row in registry_coverage if row["match_status"] == "matched"]
    perf = [row for row in registry_coverage if row["performance_status"] in {"ok", "cache_hit"}]
    squads = [row for row in registry_coverage if row["squad_status"] != "missing"]
    print(f"Output file: {output}")
    for name, df in sheets.items():
        print(f"- {name}: rows={len(df)} columns={len(df.columns)}")
    print("Registry coverage")
    print(f"- Expected teams: 48")
    print(f"- Teams found in registry: {len(registry_coverage)}")
    print(f"- Teams mapped to StatsHub team_id: {len(mapped)}")
    print(f"- Unresolved teams: {len(unresolved)}")
    print(f"- Ambiguous teams: {len(ambiguous_rows)}")
    print("Performance coverage")
    print(f"- Teams with performance downloaded: {len(perf)}")
    print(f"- Teams missing performance: {48 - len(perf)}")
    for row in aggregate_rows:
        print(f"- {row['team_name']} ({row['team_id']}): rows={row['source_rows']} dates={row['date_min']}..{row['date_max']}")
    print("Squad coverage")
    print(f"- Teams with squad/player list: {len(squads)}")
    print(f"- Teams missing squad/player list: {48 - len(squads)}")
    print("- Squad source: local seed only where available; direct /team/{id}/players tested for mapped teams")
    print("Decision")
    print("- full_48_registry_complete: yes")
    print(f"- statshub_team_id_mapping_complete: {'yes' if len(mapped) == 48 else 'partial'}")
    print(f"- team_performance_limit50_scalable: {'yes' if len(perf) == len(mapped) and mapped else 'partial'}")
    print("- squad_player_list_scalable: partial")
    print("- move_forward_full_world_cup_database: partial")


if __name__ == "__main__":
    main()
