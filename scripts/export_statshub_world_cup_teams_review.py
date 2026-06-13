from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.config.settings import ROOT_DIR
from app.db.connection import get_connection, init_db
from app.db.queries import utc_now


SNAPSHOT_NAME = "world_cup_teams_limit50_probe"
OUTPUT_FILE = Path("data/processed/statshub/world_cup_teams_limit50_review.xlsx")

METRIC_MAP = {
    "expectedGoals": "expected_goals",
    "totalShotsOnGoal": "shots",
    "shotsOnGoal": "shots_on_target",
    "shotsOffGoal": "shots_off_target",
    "bigChanceCreated": "big_chances",
    "fouls": "fouls",
    "yellowCards": "yellow_cards",
    "redCards": "red_cards",
    "totalTackle": "total_tackles",
    "accuratePasses": "accurate_passes",
    "passes": "total_passes",
    "pass_accuracy": "pass_accuracy",
    "ballPossession": "possession_average",
    "cornerKicks": "corners",
    "goalkeeperSaves": "goalkeeper_saves",
    "finalThirdEntries": "final_third_entries",
}


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8", errors="ignore"))


def maybe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def event_ts(row: dict[str, Any]) -> int | None:
    event = row.get("event") or row.get("events") or {}
    try:
        return int(event.get("timeStartTimestamp") or event.get("startTimestamp"))
    except (TypeError, ValueError):
        return None


def iso_date(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def ensure_tables() -> None:
    init_db()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS statshub_world_cup_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT,
                team_id TEXT,
                team_name TEXT,
                country TEXT,
                slug TEXT,
                source TEXT,
                confidence_status TEXT,
                raw_json TEXT,
                imported_at TEXT
            );

            CREATE TABLE IF NOT EXISTS statshub_team_performance_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT,
                endpoint_name TEXT,
                team_id TEXT,
                team_name TEXT,
                event_id TEXT,
                event_date TEXT,
                competition TEXT,
                opponent_team_id TEXT,
                opponent_team_name TEXT,
                home_away TEXT,
                raw_file TEXT,
                raw_row_json TEXT,
                goals_for REAL,
                goals_against REAL,
                expected_goals REAL,
                expected_goals_against REAL,
                shots REAL,
                shots_on_target REAL,
                shots_off_target REAL,
                big_chances REAL,
                fouls REAL,
                yellow_cards REAL,
                red_cards REAL,
                total_tackles REAL,
                accurate_passes REAL,
                total_passes REAL,
                pass_accuracy REAL,
                possession_average REAL,
                corners REAL,
                goalkeeper_saves REAL,
                final_third_entries REAL,
                imported_at TEXT
            );

            CREATE TABLE IF NOT EXISTS statshub_team_performance_aggregates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT,
                endpoint_name TEXT,
                team_id TEXT,
                team_name TEXT,
                source_rows INTEGER,
                date_min TEXT,
                date_max TEXT,
                competitions_detected TEXT,
                matches_in_window INTEGER,
                raw_file TEXT,
                goals_for REAL,
                goals_against REAL,
                expected_goals REAL,
                expected_goals_against REAL,
                shots REAL,
                shots_on_target REAL,
                shots_off_target REAL,
                big_chances REAL,
                fouls REAL,
                yellow_cards REAL,
                red_cards REAL,
                total_tackles REAL,
                accurate_passes REAL,
                total_passes REAL,
                pass_accuracy REAL,
                possession_average REAL,
                corners REAL,
                goalkeeper_saves REAL,
                final_third_entries REAL,
                opponent_expected_goals REAL,
                opponent_shots REAL,
                opponent_shots_on_target REAL,
                opponent_fouls REAL,
                opponent_yellow_cards REAL,
                opponent_red_cards REAL,
                raw_fields_json TEXT,
                imported_at TEXT
            );

            CREATE TABLE IF NOT EXISTS statshub_team_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT,
                team_id TEXT,
                team_name TEXT,
                player_id TEXT,
                player_name TEXT,
                player_slug TEXT,
                position TEXT,
                jersey_number TEXT,
                nationality TEXT,
                source_endpoint TEXT,
                raw_file TEXT,
                confidence_status TEXT,
                raw_json TEXT,
                imported_at TEXT
            );

            CREATE TABLE IF NOT EXISTS statshub_raw_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT,
                entity_type TEXT,
                team_id TEXT,
                team_name TEXT,
                endpoint_name TEXT,
                url TEXT,
                status_code INTEGER,
                content_type TEXT,
                response_size INTEGER,
                top_keys TEXT,
                rows_detected INTEGER,
                raw_file TEXT,
                classification_status TEXT,
                useful_performance_metrics_found TEXT,
                date_min TEXT,
                date_max TEXT,
                competitions_detected TEXT,
                imported_at TEXT
            );
            """
        )


def source_worldcup_teams() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT team_id, team_name, raw_json, source_event_id
            FROM statshub_worldcup_teams
            WHERE team_id IS NOT NULL AND team_id != ''
            ORDER BY team_name
            """
        ).fetchall()
    teams = []
    for row in rows:
        raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
        teams.append(
            {
                "team_id": str(row["team_id"]),
                "team_name": row["team_name"],
                "country": raw.get("countrySlug"),
                "slug": raw.get("slug"),
                "source": f"statshub_worldcup_teams/source_event_id={row['source_event_id']}",
                "confidence_status": "confirmed_statshub_worldcup_event",
                "raw_json": row["raw_json"],
            }
        )
    return teams


def latest_snapshot(endpoint_name: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM statshub_snapshots
            WHERE snapshot_name = ? AND endpoint_name = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (SNAPSHOT_NAME, endpoint_name),
        ).fetchone()
    return dict(row) if row else None


def performance_rows(source: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not source or not source.get("raw_file_path"):
        return []
    path = Path(source["raw_file_path"])
    if path.suffix != ".json" or not path.exists():
        return []
    payload = load_json(path)
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def competition(row: dict[str, Any]) -> str | None:
    league = row.get("league")
    if isinstance(league, dict):
        return league.get("name") or league.get("slug")
    event = row.get("events") or row.get("event") or {}
    return str(event.get("uniqueTournamentId")) if event.get("uniqueTournamentId") is not None else None


def opponent(row: dict[str, Any], team_id: str) -> tuple[str | None, str | None, str | None]:
    home = row.get("homeTeam") or {}
    away = row.get("awayTeam") or {}
    if str(home.get("id")) == team_id:
        return str(away.get("id")) if away.get("id") is not None else None, away.get("name"), "home"
    if str(away.get("id")) == team_id:
        return str(home.get("id")) if home.get("id") is not None else None, home.get("name"), "away"
    return None, None, None


def score(row: dict[str, Any], team_id: str) -> tuple[float | None, float | None]:
    event = row.get("event") or {}
    score_obj = event.get("score") or {}
    home = row.get("homeTeam") or {}
    away = row.get("awayTeam") or {}
    home_score = maybe_float(score_obj.get("home"))
    away_score = maybe_float(score_obj.get("away"))
    if str(home.get("id")) == team_id:
        return home_score, away_score
    if str(away.get("id")) == team_id:
        return away_score, home_score
    return None, None


def event_record(team: dict[str, Any], source: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    team_id = team["team_id"]
    stats = row.get("statistics") or {}
    opp_stats = row.get("opponentStatistics") or {}
    event = row.get("event") or {}
    opp_id, opp_name, home_away = opponent(row, team_id)
    goals_for, goals_against = score(row, team_id)
    record = {
        "snapshot_name": SNAPSHOT_NAME,
        "endpoint_name": source["endpoint_name"],
        "team_id": team_id,
        "team_name": team["team_name"],
        "event_id": str(event.get("id")) if event.get("id") is not None else None,
        "event_date": iso_date(event_ts(row)),
        "competition": competition(row),
        "opponent_team_id": opp_id,
        "opponent_team_name": opp_name,
        "home_away": home_away,
        "raw_file": source["raw_file_path"],
        "raw_row_json": json.dumps(row, ensure_ascii=False),
        "goals_for": goals_for,
        "goals_against": goals_against,
        "expected_goals": maybe_float(stats.get("expectedGoals")),
        "expected_goals_against": maybe_float(opp_stats.get("expectedGoals")),
    }
    for original, alias in METRIC_MAP.items():
        if alias not in record:
            record[alias] = maybe_float(stats.get(original))
    return record


def aggregate_records(team: dict[str, Any], source: dict[str, Any] | None, events: list[dict[str, Any]]) -> dict[str, Any]:
    rows = len(events)
    dates = [event["event_date"] for event in events if event.get("event_date")]
    comps = sorted({event["competition"] for event in events if event.get("competition")})
    agg = {
        "snapshot_name": SNAPSHOT_NAME,
        "endpoint_name": source["endpoint_name"] if source else f"team_{team['team_id']}_performance_limit50",
        "team_id": team["team_id"],
        "team_name": team["team_name"],
        "source_rows": rows,
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "competitions_detected": json.dumps(comps, ensure_ascii=False),
        "matches_in_window": rows,
        "raw_file": source["raw_file_path"] if source else None,
    }
    sum_fields = [
        "goals_for",
        "goals_against",
        "expected_goals",
        "expected_goals_against",
        "shots",
        "shots_on_target",
        "shots_off_target",
        "big_chances",
        "fouls",
        "yellow_cards",
        "red_cards",
        "total_tackles",
        "accurate_passes",
        "total_passes",
        "corners",
        "goalkeeper_saves",
        "final_third_entries",
    ]
    avg_fields = ["pass_accuracy", "possession_average"]
    for field in sum_fields:
        values = [event[field] for event in events if event.get(field) is not None]
        agg[field] = sum(values) if values else None
    for field in avg_fields:
        values = [event[field] for event in events if event.get(field) is not None]
        agg[field] = sum(values) / len(values) if values else None
    if source:
        raw_rows = performance_rows(source)
        raw_fields = sorted({key for row in raw_rows for key in ((row.get("statistics") or {}).keys())})
        agg["raw_fields_json"] = json.dumps(raw_fields, ensure_ascii=False)
    else:
        agg["raw_fields_json"] = "[]"
    return agg


def players_for_team(team: dict[str, Any]) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT player_id, player_name, team_id, team_name, raw_json
            FROM statshub_worldcup_players
            WHERE team_id = ?
            ORDER BY player_name
            """,
            (team["team_id"],),
        ).fetchall()
    out = []
    for row in rows:
        raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
        out.append(
            {
                "snapshot_name": SNAPSHOT_NAME,
                "team_id": team["team_id"],
                "team_name": team["team_name"],
                "player_id": str(row["player_id"]) if row["player_id"] is not None else None,
                "player_name": row["player_name"],
                "player_slug": raw.get("slug") or raw.get("playerSlug"),
                "position": raw.get("position"),
                "jersey_number": raw.get("jerseyNumber") or raw.get("shirtNumber"),
                "nationality": raw.get("nationality"),
                "source_endpoint": "statshub_worldcup_players_seed",
                "raw_file": None,
                "confidence_status": "derived_from_local_worldcup_seed",
                "raw_json": row["raw_json"],
            }
        )
    return out


def raw_sources(teams_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT endpoint_name, url, status_code, content_type, response_size, json_top_keys,
                   rows_detected, raw_file_path, status
            FROM statshub_snapshots
            WHERE snapshot_name = ?
            ORDER BY id
            """,
            (SNAPSHOT_NAME,),
        ).fetchall()
    out = []
    for row in rows:
        endpoint = row["endpoint_name"]
        team_id = None
        for part in endpoint.split("_"):
            if part.isdigit() and part in teams_by_id:
                team_id = part
                break
        team = teams_by_id.get(team_id or "", {})
        perf_rows = performance_rows(dict(row)) if "performance" in endpoint else []
        dates = [iso_date(ts) for ts in (event_ts(item) for item in perf_rows) if ts is not None]
        comps = sorted({competition(item) for item in perf_rows if competition(item)})
        out.append(
            {
                "snapshot_name": SNAPSHOT_NAME,
                "entity_type": "team" if team_id else "source",
                "team_id": team_id,
                "team_name": team.get("team_name"),
                "endpoint_name": endpoint,
                "url": row["url"],
                "status_code": row["status_code"],
                "content_type": row["content_type"],
                "response_size": row["response_size"],
                "top_keys": row["json_top_keys"],
                "rows_detected": row["rows_detected"],
                "raw_file": row["raw_file_path"],
                "classification_status": row["status"],
                "useful_performance_metrics_found": "yes" if perf_rows and any((item.get("statistics") or {}) for item in perf_rows) else "no",
                "date_min": min(dates) if dates else None,
                "date_max": max(dates) if dates else None,
                "competitions_detected": json.dumps(comps, ensure_ascii=False),
            }
        )
    return out


def insert_rows(table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys()) + ["imported_at"]
    marks = ",".join("?" for _ in cols)
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({marks})"
    now = utc_now()
    with get_connection() as conn:
        for row in rows:
            conn.execute(sql, [row.get(col) if col != "imported_at" else now for col in cols])


def flatten_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "text"


def data_dictionary(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    meanings = {
        "team_id": "StatsHub team id",
        "team_name": "team display name",
        "status": "overall local coverage status",
        "source_rows": "performance rows in limit=50 response",
        "date_min": "oldest event date in selected response",
        "date_max": "newest event date in selected response",
        "players_detected": "players linked to team from local squad seed",
        "performance_status": "team performance download status",
        "squad_status": "team player-list source status",
        "goals_for": "sum of team goals in window",
        "goals_against": "sum of opponent goals in window",
        "expected_goals": "sum of team expected goals in window",
        "expected_goals_against": "sum of opponent expected goals in window",
    }
    rows = []
    for sheet_name, df in sheets.items():
        if sheet_name == "data_dictionary":
            continue
        for column in df.columns:
            non_null = df[column].dropna()
            rows.append(
                {
                    "sheet_name": sheet_name,
                    "column_name": column,
                    "original_json_path": column if "__" in column else "",
                    "inferred_type": "null" if non_null.empty else flatten_type(non_null.iloc[0]),
                    "meaning": meanings.get(column, "unknown"),
                    "notes": "" if column in meanings else "unknown; preserved for review",
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    args = parser.parse_args()

    ensure_tables()
    teams = source_worldcup_teams()
    teams_by_id = {team["team_id"]: team for team in teams}

    team_rows = []
    event_rows = []
    aggregate_rows = []
    player_rows = []
    summary_rows = []
    for team in teams:
        endpoint = f"team_{team['team_id']}_performance_limit50"
        source = latest_snapshot(endpoint)
        rows = performance_rows(source)
        events = [event_record(team, source, row) for row in rows] if source else []
        players = players_for_team(team)
        aggregate = aggregate_records(team, source, events)
        performance_status = source["status"] if source else "missing"
        squad_status = "derived_from_local_worldcup_seed" if players else "missing"
        team_rows.append(team)
        event_rows.extend(events)
        aggregate_rows.append(aggregate)
        player_rows.extend(players)
        summary_rows.append(
            {
                "team_id": team["team_id"],
                "team_name": team["team_name"],
                "status": "partial" if squad_status.startswith("derived") else "missing_squad",
                "source_rows": len(rows),
                "date_min": aggregate["date_min"],
                "date_max": aggregate["date_max"],
                "competitions_detected": aggregate["competitions_detected"],
                "players_detected": len(players),
                "performance_status": performance_status,
                "squad_status": squad_status,
                "best_performance_raw_file": source["raw_file_path"] if source else None,
                "best_squad_raw_file": None,
                "notes": "World Cup registry source currently confirms only these teams. Squad endpoint not confirmed; players derived from local seed.",
            }
        )

    raw_source_rows = raw_sources(teams_by_id)

    with get_connection() as conn:
        for table in [
            "statshub_world_cup_teams",
            "statshub_team_performance_events",
            "statshub_team_performance_aggregates",
            "statshub_team_players",
            "statshub_raw_sources",
        ]:
            conn.execute(f"DELETE FROM {table} WHERE snapshot_name = ?", (SNAPSHOT_NAME,))
    insert_rows("statshub_world_cup_teams", team_rows)
    insert_rows("statshub_team_performance_events", event_rows)
    insert_rows("statshub_team_performance_aggregates", aggregate_rows)
    insert_rows("statshub_team_players", player_rows)
    insert_rows("statshub_raw_sources", raw_source_rows)

    sheets = {
        "teams_summary": pd.DataFrame(summary_rows),
        "team_performance_aggregates": pd.DataFrame(aggregate_rows),
        "team_players": pd.DataFrame(player_rows),
        "raw_sources": pd.DataFrame(raw_source_rows),
    }
    sheets["data_dictionary"] = data_dictionary(sheets)

    output = ROOT_DIR / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name in ["teams_summary", "team_performance_aggregates", "team_players", "raw_sources", "data_dictionary"]:
            sheets[sheet_name].to_excel(writer, sheet_name=sheet_name, index=False)

    missing_perf = sum(1 for row in summary_rows if row["source_rows"] == 0)
    missing_squad = sum(1 for row in summary_rows if row["players_detected"] == 0)
    print(f"Output file: {output}")
    for name, df in sheets.items():
        print(f"- {name}: rows={len(df)} columns={len(df.columns)}")
    print("Coverage")
    print(f"- expected_world_cup_teams_from_local_source: {len(teams)}")
    print(f"- confirmed_statshub_team_id: {len([t for t in teams if t['team_id']])}")
    print(f"- performance_downloaded: {len([r for r in summary_rows if r['source_rows'] > 0])}")
    print(f"- squad_player_list_available: {len([r for r in summary_rows if r['players_detected'] > 0])}")
    print(f"- missing_team_id: 0")
    print(f"- missing_performance: {missing_perf}")
    print(f"- missing_squad: {missing_squad}")
    print("Team performance")
    for row in summary_rows:
        print(f"- {row['team_name']} ({row['team_id']}): rows={row['source_rows']} dates={row['date_min']}..{row['date_max']} status={row['performance_status']}")
    print("Squads")
    for row in summary_rows:
        print(f"- {row['team_name']} ({row['team_id']}): players={row['players_detected']} source={row['squad_status']}")
    print("Decision")
    print("- move_forward_full_world_cup_database: partial")
    print("- team_performance_limit50_scalable: yes for confirmed team IDs")
    print("- squad_player_list_scalable: partial; direct squad endpoints not confirmed")
    print("- still_missing: full World Cup team registry and confirmed squad endpoint pattern")


if __name__ == "__main__":
    main()
