from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

import openpyxl


DB_PATH = Path("data/mundial.db")
OUT_XLSX = Path("data/processed/betting/model_coverage_audit_all_teams.xlsx")

MIN_ROSTER_COVERAGE_PCT = 80.0
MIN_MODEL_READY_PLAYERS = 14
MIN_REQUIRED_STATS_PLAYERS = 14
MIN_PLAYER_PERFORMANCE_ROWS = 300
MIN_PLAYERS_WITH_MINUTES = 8
MIN_TEAM_PERFORMANCE_ROWS = 30
MIN_EXPECTED_ROSTER_FALLBACK = 26

REQUIRED_PLAYER_STAT_COLS = (
    "shots",
    "shots_on_target",
    "was_fouled",
    "tackles",
    "passes",
    "yellow_cards",
)


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def scalar(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def rows(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return con.execute(sql, params).fetchall()


def dict_rows(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in rows(con, sql, params)]


def match_teams(match_name: str) -> tuple[str | None, str | None]:
    if " vs " not in match_name:
        return None, None
    home, away = match_name.split(" vs ", 1)
    return home.strip(), away.strip()


def teams_from_current_odds(con: sqlite3.Connection) -> list[str]:
    names: set[str] = set()
    for row in rows(
        con,
        "SELECT DISTINCT match_name FROM betting_odds_normalized WHERE match_name IS NOT NULL",
    ):
        home, away = match_teams(row["match_name"])
        if home:
            names.add(home)
        if away:
            names.add(away)
    return sorted(names)


def matches_from_current_odds(con: sqlite3.Connection) -> list[str]:
    return [
        row["match_name"]
        for row in rows(
            con,
            """
            SELECT match_name, COUNT(*) AS rows
            FROM betting_odds_normalized
            WHERE match_name IS NOT NULL
            GROUP BY match_name
            ORDER BY match_name
            """,
        )
    ]


def roster_rows(con: sqlite3.Connection, team: str) -> list[sqlite3.Row]:
    if not table_exists(con, "statshub_team_players"):
        return []
    return rows(
        con,
        """
        SELECT *
        FROM statshub_team_players
        WHERE team_name=?
        ORDER BY CAST(COALESCE(jersey_number, '999') AS INTEGER), player_name
        """,
        (team,),
    )


def performance_summary(con: sqlite3.Connection, player_id: str | None) -> dict[str, Any]:
    if not player_id or not table_exists(con, "statshub_player_performance_events"):
        return {
            "rows_extracted": 0,
            "minutes_available": 0,
            "required_stats_available": 0,
        }
    stat_expr = " OR ".join(f"{col} IS NOT NULL" for col in REQUIRED_PLAYER_STAT_COLS)
    row = con.execute(
        f"""
        SELECT COUNT(*) AS rows_extracted,
               SUM(COALESCE(minutes_played,0) >= 15) AS minutes_available,
               SUM((COALESCE(minutes_played,0) >= 15) AND ({stat_expr})) AS required_stats_available
        FROM statshub_player_performance_events
        WHERE player_id=?
        """,
        (str(player_id),),
    ).fetchone()
    return {
        "rows_extracted": int(row["rows_extracted"] or 0),
        "minutes_available": int(row["minutes_available"] or 0),
        "required_stats_available": int(row["required_stats_available"] or 0),
    }


def raw_profile_exists(con: sqlite3.Connection, player_id: str | None) -> bool:
    if not player_id or not table_exists(con, "statshub_raw_players"):
        return False
    return scalar(
        con,
        "SELECT COUNT(*) FROM statshub_raw_players WHERE player_id=?",
        (str(player_id),),
    ) > 0


def player_detail(con: sqlite3.Connection, team: str) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for player in roster_rows(con, team):
        player_id = str(player["player_id"]) if player["player_id"] not in (None, "") else None
        perf = performance_summary(con, player_id)
        resolved = bool(player_id) and str(player["statshub_player_id_status"] or "") in {
            "confirmed",
            "skipped_existing",
            "manual",
            "matched",
        }
        profile_exists = raw_profile_exists(con, player_id)
        performance_exists = perf["rows_extracted"] > 0
        persisted = performance_exists
        required = perf["required_stats_available"] > 0
        minutes = perf["minutes_available"] > 0
        model_ready = bool(resolved and performance_exists and minutes and required)

        failure_reasons: list[str] = []
        if not resolved:
            failure_reasons.append("unresolved_player_id")
        if not profile_exists:
            failure_reasons.append("missing_raw_profile")
        if not performance_exists:
            failure_reasons.append("missing_player_performance")
        if not minutes:
            failure_reasons.append("missing_minutes_min15")
        if not required:
            failure_reasons.append("missing_required_stats")

        details.append({
            "team_name": team,
            "player_name": player["player_name"],
            "player_id": player_id,
            "resolved_status": player["statshub_player_id_status"] or "unresolved",
            "raw_profile_exists": int(profile_exists),
            "performance_endpoint_exists": int(performance_exists),
            "status_code": "db_cached" if performance_exists else "missing_local_data",
            "rows_extracted": perf["rows_extracted"],
            "minutes_available": perf["minutes_available"],
            "required_stats_available": perf["required_stats_available"],
            "persisted_to_db": int(persisted),
            "model_ready_status": "READY" if model_ready else "NOT_READY",
            "failure_reason": ";".join(failure_reasons),
            "raw_file": player["raw_file"],
            "player_id_match_notes": player["player_id_match_notes"],
        })
    return details


def team_perf_rows(con: sqlite3.Connection, team: str) -> int:
    if not table_exists(con, "statshub_team_performance_events"):
        return 0
    return scalar(
        con,
        "SELECT COUNT(*) FROM statshub_team_performance_events WHERE team_name=?",
        (team,),
    )


def summarize_team(con: sqlite3.Connection, team: str, details: list[dict[str, Any]]) -> dict[str, Any]:
    expected_roster = len(details) or MIN_EXPECTED_ROSTER_FALLBACK
    resolved = sum(1 for r in details if r["player_id"])
    roster_pct = round((resolved / expected_roster * 100.0), 2) if expected_roster else 0.0
    with_profile = sum(1 for r in details if r["raw_profile_exists"])
    with_perf = sum(1 for r in details if r["rows_extracted"] > 0)
    with_minutes = sum(1 for r in details if r["minutes_available"] > 0)
    with_required = sum(1 for r in details if r["required_stats_available"] > 0)
    model_ready = sum(1 for r in details if r["model_ready_status"] == "READY")
    perf_rows = sum(int(r["rows_extracted"]) for r in details)
    team_rows = team_perf_rows(con, team)

    failures: list[str] = []
    if roster_pct < MIN_ROSTER_COVERAGE_PCT:
        failures.append(f"roster_coverage_pct {roster_pct} < {MIN_ROSTER_COVERAGE_PCT}")
    if model_ready < MIN_MODEL_READY_PLAYERS:
        failures.append(f"model_ready_players {model_ready} < {MIN_MODEL_READY_PLAYERS}")
    if with_required < MIN_REQUIRED_STATS_PLAYERS:
        failures.append(f"players_with_required_stats {with_required} < {MIN_REQUIRED_STATS_PLAYERS}")
    if perf_rows < MIN_PLAYER_PERFORMANCE_ROWS:
        failures.append(f"player_performance_rows {perf_rows} < {MIN_PLAYER_PERFORMANCE_ROWS}")
    if with_minutes < MIN_PLAYERS_WITH_MINUTES:
        failures.append(f"players_with_minutes {with_minutes} < {MIN_PLAYERS_WITH_MINUTES}")
    if team_rows < MIN_TEAM_PERFORMANCE_ROWS:
        failures.append(f"team_performance_rows {team_rows} < {MIN_TEAM_PERFORMANCE_ROWS}")

    if not failures:
        status = "READY"
    elif team_rows >= MIN_TEAM_PERFORMANCE_ROWS or model_ready > 0:
        status = "PARTIAL"
    else:
        status = "NOT_READY"

    missing_players = "; ".join(r["player_name"] for r in details if not r["player_id"])
    incomplete_players = "; ".join(r["player_name"] for r in details if r["model_ready_status"] != "READY")
    return {
        "team_name": team,
        "expected_roster_count": expected_roster,
        "resolved_roster_players": resolved,
        "roster_coverage_pct": roster_pct,
        "players_with_raw_profile": with_profile,
        "players_with_performance_rows": with_perf,
        "players_with_minutes": with_minutes,
        "players_with_required_stats": with_required,
        "model_ready_players": model_ready,
        "player_performance_rows": perf_rows,
        "team_performance_rows": team_rows,
        "missing_players": missing_players,
        "incomplete_players": incomplete_players,
        "status": status,
        "failure_reason": "; ".join(failures),
    }


def match_summary(con: sqlite3.Connection, match: str, team_summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    home, away = match_teams(match)
    odds_count = scalar(con, "SELECT COUNT(*) FROM betting_odds_normalized WHERE match_name=?", (match,))
    player_props = scalar(
        con,
        "SELECT COUNT(*) FROM betting_odds_normalized WHERE match_name=? AND market_type LIKE 'player_%'",
        (match,),
    )
    player_props_with_id = scalar(
        con,
        """
        SELECT COUNT(*) FROM betting_odds_normalized
        WHERE match_name=? AND market_type LIKE 'player_%'
          AND player_id IS NOT NULL AND player_id != ''
        """,
        (match,),
    )
    ok_markets = scalar(
        con,
        "SELECT COUNT(*) FROM betting_odds_normalized WHERE match_name=? AND market_mapping_status='OK'",
        (match,),
    )
    model_probability_rows = scalar(
        con,
        "SELECT COUNT(*) FROM betting_value_scores_new WHERE match_name=? AND model_probability IS NOT NULL",
        (match,),
    )
    ev_rows = scalar(
        con,
        "SELECT COUNT(*) FROM betting_value_scores_new WHERE match_name=? AND expected_value IS NOT NULL",
        (match,),
    )
    value_rows = scalar(
        con,
        "SELECT COUNT(*) FROM betting_value_scores_new WHERE match_name=? AND verdict='VALUE'",
        (match,),
    )
    home_summary = team_summaries.get(home or "", {})
    away_summary = team_summaries.get(away or "", {})
    home_team_perf = int(home_summary.get("team_performance_rows") or 0)
    away_team_perf = int(away_summary.get("team_performance_rows") or 0)
    team_perf_ready = home_team_perf >= MIN_TEAM_PERFORMANCE_ROWS and away_team_perf >= MIN_TEAM_PERFORMANCE_ROWS
    player_perf_ready = (
        home_summary.get("status") == "READY"
        and away_summary.get("status") == "READY"
    )
    reasons: list[str] = []
    if not team_perf_ready:
        reasons.append("team performance coverage insufficient")
    if not player_perf_ready:
        if home_summary.get("status") != "READY" and home:
            reasons.append(f"{home} player performance coverage insufficient")
        if away_summary.get("status") != "READY" and away:
            reasons.append(f"{away} player performance coverage insufficient")
    if odds_count > 0 and model_probability_rows == 0:
        reasons.append("odds present but model_probability rows = 0")

    if odds_count > 0 and model_probability_rows == 0:
        status = "NOT_READY"
    elif team_perf_ready and player_perf_ready:
        status = "READY"
    elif team_perf_ready or model_probability_rows > 0:
        status = "PARTIAL"
    else:
        status = "NOT_READY"

    return {
        "match_name": match,
        "home_team": home,
        "away_team": away,
        "odds_normalized_count": odds_count,
        "player_props_count": player_props,
        "player_props_with_player_id": player_props_with_id,
        "OK_market_count": ok_markets,
        "team_performance_status_home": "READY" if home_team_perf >= MIN_TEAM_PERFORMANCE_ROWS else "NOT_READY",
        "team_performance_status_away": "READY" if away_team_perf >= MIN_TEAM_PERFORMANCE_ROWS else "NOT_READY",
        "player_performance_status_home": home_summary.get("status", "NOT_READY"),
        "player_performance_status_away": away_summary.get("status", "NOT_READY"),
        "model_probability_rows": model_probability_rows,
        "EV_rows": ev_rows,
        "VALUE_rows": value_rows,
        "status": status,
        "failure_reason": "; ".join(reasons),
    }


def write_sheet(wb: openpyxl.Workbook, name: str, data: list[dict[str, Any]]) -> None:
    ws = wb.create_sheet(name)
    if not data:
        ws.append(["status"])
        ws.append(["no rows"])
        return
    headers = list(data[0].keys())
    ws.append(headers)
    for row in data:
        ws.append([row.get(h) for h in headers])
    for col in ws.columns:
        width = max(len(str(cell.value or "")) for cell in col[:200])
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 12), 80)


def write_workbook(
    team_rows: list[dict[str, Any]],
    match_rows: list[dict[str, Any]],
    all_players: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> None:
    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_sheet(wb, "summary_by_team", team_rows)
    write_sheet(wb, "summary_by_match", match_rows)
    write_sheet(wb, "qatar_player_detail", [r for r in all_players if r["team_name"] == "Qatar"])
    write_sheet(wb, "switzerland_player_detail", [r for r in all_players if r["team_name"] == "Switzerland"])
    write_sheet(wb, "all_players_detail", all_players)
    write_sheet(wb, "missing_or_incomplete_players", [r for r in all_players if r["model_ready_status"] != "READY"])
    write_sheet(wb, "model_readiness_failures", failures)
    wb.save(OUT_XLSX)


def build_report() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    with connect() as con:
        teams = teams_from_current_odds(con)
        matches = matches_from_current_odds(con)
        all_players: list[dict[str, Any]] = []
        team_summaries: dict[str, dict[str, Any]] = {}
        for team in teams:
            details = player_detail(con, team)
            all_players.extend(details)
            team_summaries[team] = summarize_team(con, team, details)

        match_rows = [match_summary(con, match, team_summaries) for match in matches]
        team_rows = [team_summaries[team] for team in teams]

    failures: list[dict[str, Any]] = []
    for team in team_rows:
        if team["status"] != "READY":
            failures.append({
                "scope": "team",
                "name": team["team_name"],
                "status": team["status"],
                "severity": "WARNING",
                "failure_reason": team["failure_reason"],
            })
    for match in match_rows:
        if match["odds_normalized_count"] > 0 and match["status"] != "READY":
            failures.append({
                "scope": "match",
                "name": match["match_name"],
                "status": match["status"],
                "severity": "ERROR" if match["status"] == "NOT_READY" else "WARNING",
                "failure_reason": match["failure_reason"],
            })
    return team_rows, match_rows, all_players, failures


def health_flags(team_rows: list[dict[str, Any]], match_rows: list[dict[str, Any]]) -> dict[str, bool]:
    odds_matches = [row for row in match_rows if row["odds_normalized_count"] > 0]
    return {
        "technical_pass": True,
        "data_coverage_full_pass": all(row["status"] == "READY" for row in team_rows),
        "model_readiness_partial_available": all(
            row["model_probability_rows"] > 0 or row["status"] == "READY"
            for row in odds_matches
        ),
        "actionable_rows_available": any(row["VALUE_rows"] > 0 for row in odds_matches),
    }


def print_report(team_rows: list[dict[str, Any]], match_rows: list[dict[str, Any]], failures: list[dict[str, Any]]) -> None:
    print("MODEL COVERAGE HEALTH CHECK")
    flags = health_flags(team_rows, match_rows)
    print(f"technical_pass: {str(flags['technical_pass']).lower()}")
    print(f"data_coverage_full_pass: {str(flags['data_coverage_full_pass']).lower()}")
    print(f"model_readiness_partial_available: {str(flags['model_readiness_partial_available']).lower()}")
    print(f"actionable_rows_available: {str(flags['actionable_rows_available']).lower()}")
    print(f"export: {OUT_XLSX}")
    print("")
    print("summary_by_team")
    for row in team_rows:
        print(
            f"- {row['team_name']}: {row['status']} | roster={row['resolved_roster_players']}/{row['expected_roster_count']} "
            f"({row['roster_coverage_pct']}%) | model_ready={row['model_ready_players']} | "
            f"required_stats={row['players_with_required_stats']} | perf_rows={row['player_performance_rows']} | "
            f"team_perf={row['team_performance_rows']} | {row['failure_reason']}"
        )
    print("")
    print("summary_by_match")
    for row in match_rows:
        print(
            f"- {row['match_name']}: {row['status']} | odds={row['odds_normalized_count']} | "
            f"player_props={row['player_props_count']} | player_ids={row['player_props_with_player_id']} | "
            f"model_probability={row['model_probability_rows']} | EV={row['EV_rows']} | VALUE={row['VALUE_rows']} | "
            f"{row['failure_reason']}"
        )
    if failures:
        print("")
        print("model_readiness_failures")
        for row in failures:
            print(f"- {row['severity']} {row['name']} {row['status']}: {row['failure_reason']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-exit-fail", action="store_true")
    args = parser.parse_args()
    team_rows, match_rows, all_players, failures = build_report()
    write_workbook(team_rows, match_rows, all_players, failures)
    print_report(team_rows, match_rows, failures)
    flags = health_flags(team_rows, match_rows)
    fatal_failures = [row for row in failures if row.get("severity") == "ERROR"]
    if (fatal_failures or not flags["model_readiness_partial_available"] or not flags["actionable_rows_available"]) and not args.no_exit_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
