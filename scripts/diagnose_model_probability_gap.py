from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


DB_PATH = Path("data/mundial.db")
PLAYER_FIELDS = {
    "player_total_shots": "shots",
    "player_shots_on_target": "shots_on_target",
    "player_fouled": "was_fouled",
    "player_tackles": "tackles",
    "player_passes": "passes",
    "player_cards": "yellow_cards",
}
TEAM_FIELDS = {
    "team_corners": "corners",
    "team_cards": "yellow_cards",
    "team_tackles": "total_tackles",
    "goalkeeper_saves": "goalkeeper_saves",
}
MATCH_TEAM_FIELDS = {
    "over_under_goals": ("goals_for", "goals_against"),
    "total_corners": ("corners",),
    "total_cards": ("yellow_cards", "red_cards"),
}


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def columns(con: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(con, table):
        return set()
    return {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}


def rows(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in con.execute(sql, params).fetchall()]


def scalar(con: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    row = con.execute(sql, params).fetchone()
    return int(row[0] or 0) if row else 0


def like_match_names(con: sqlite3.Connection, table: str, match: str) -> list[dict[str, Any]]:
    cols = columns(con, table)
    if "match_name" not in cols:
        return []
    terms = [part.strip() for part in match.replace(" vs ", "|").split("|") if part.strip()]
    where = " OR ".join(["match_name LIKE ?"] * len(terms))
    params = tuple(f"%{term}%" for term in terms)
    return rows(
        con,
        f"SELECT match_name, COUNT(*) AS rows FROM {table} WHERE {where} GROUP BY match_name ORDER BY rows DESC",
        params,
    )


def team_names(match: str) -> tuple[str, str] | tuple[None, None]:
    if " vs " not in match:
        return None, None
    home, away = match.split(" vs ", 1)
    return home.strip(), away.strip()


def player_source_count(con: sqlite3.Connection, player_id: str | None, field: str | None) -> int:
    if not player_id or not field:
        return 0
    cols = columns(con, "statshub_player_performance_events")
    if field not in cols:
        return 0
    return scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM statshub_player_performance_events
        WHERE player_id=?
          AND COALESCE(minutes_played,0) >= 15
          AND {field} IS NOT NULL
        """,
        (str(player_id),),
    )


def team_source_count(con: sqlite3.Connection, team: str | None, field: str | None) -> int:
    if not team or not field:
        return 0
    cols = columns(con, "statshub_team_performance_events")
    if field not in cols:
        return 0
    return scalar(
        con,
        f"""
        SELECT COUNT(*)
        FROM statshub_team_performance_events
        WHERE team_name=? AND {field} IS NOT NULL
        """,
        (team,),
    )


def diagnose_row(con: sqlite3.Connection, row: sqlite3.Row, home: str | None, away: str | None) -> str:
    if row["market_mapping_status"] != "OK":
        return f"market_mapping:{row['market_mapping_status']}"
    if row["exact_market_match"] != 1:
        return "exact_market_match_false"
    if row["normalized_status"] != "ok":
        return f"normalized_status:{row['normalized_status']}"
    if row["data_completeness_status"] != "COMPLETE":
        return f"data_completeness:{row['data_completeness_status']}"
    if row["model_uses_proxy"]:
        return "model_uses_proxy"
    if row["field_mapping_status"] in ("WRONG", "MISSING_FIELD"):
        return f"field_mapping:{row['field_mapping_status']}"
    if row["side_line_status"] != "OK":
        return f"side_line:{row['side_line_status']}"

    market_type = row["market_type"]
    if market_type.startswith("player_"):
        if not row["player_id"]:
            return "player_missing_player_id"
        field = PLAYER_FIELDS.get(market_type) or row["statshub_field_used"]
        if not field or player_source_count(con, row["player_id"], field) == 0:
            return f"player_source_missing:{field or 'unknown_field'}"
        return "runtime_model_candidate"

    if market_type in TEAM_FIELDS:
        field = TEAM_FIELDS[market_type]
        if not row["team_name"]:
            return "team_missing_team_name"
        if team_source_count(con, row["team_name"], field) == 0:
            return f"team_source_missing:{field}"
        return "runtime_model_candidate"

    if market_type in MATCH_TEAM_FIELDS:
        first_field = MATCH_TEAM_FIELDS[market_type][0]
        if team_source_count(con, home, first_field) == 0 or team_source_count(con, away, first_field) == 0:
            return f"match_team_source_missing:{first_field}"
        return "runtime_model_candidate"

    return "no_runtime_calculator_for_market_type"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--match", default="Qatar vs Switzerland")
    args = parser.parse_args()
    match = args.match
    home, away = team_names(match)

    with connect() as con:
        out: dict[str, Any] = {"match_name": match}

        out["available_match_names"] = {
            "betting_odds_normalized": like_match_names(con, "betting_odds_normalized", match),
            "betting_value_scores_new": like_match_names(con, "betting_value_scores_new", match),
            "betting_model_probabilities": like_match_names(con, "betting_model_probabilities", match),
        }

        out["source_tables"] = {
            table: {
                "exists": table_exists(con, table),
                "rows": scalar(con, f"SELECT COUNT(*) FROM {table}") if table_exists(con, table) else 0,
                "match_rows": scalar(con, f"SELECT COUNT(*) FROM {table} WHERE match_name=?", (match,))
                if "match_name" in columns(con, table) else None,
            }
            for table in [
                "betting_model_probabilities",
                "betting_value_scores_new",
                "betting_odds_normalized",
                "statshub_player_performance_events",
                "statshub_team_performance_events",
            ]
        }

        out["team_source_rows"] = rows(
            con,
            """
            SELECT team_name, COUNT(*) AS rows
            FROM statshub_team_performance_events
            WHERE team_name IN (?, ?)
            GROUP BY team_name
            ORDER BY team_name
            """,
            (home, away),
        ) if home and away and table_exists(con, "statshub_team_performance_events") else []

        out["player_source_rows"] = rows(
            con,
            """
            SELECT team_name, COUNT(*) AS rows,
                   COUNT(DISTINCT player_id) AS players
            FROM statshub_player_performance_events
            WHERE team_name IN (?, ?)
            GROUP BY team_name
            ORDER BY team_name
            """,
            (home, away),
        ) if home and away and table_exists(con, "statshub_player_performance_events") else []

        out["odds_summary"] = {
            "normalized_total": scalar(con, "SELECT COUNT(*) FROM betting_odds_normalized WHERE match_name=?", (match,)),
            "ok_market_mapping": scalar(con, "SELECT COUNT(*) FROM betting_odds_normalized WHERE match_name=? AND market_mapping_status='OK'", (match,)),
            "player_props": scalar(con, "SELECT COUNT(*) FROM betting_odds_normalized WHERE match_name=? AND market_type LIKE 'player_%'", (match,)),
            "player_props_with_player_id": scalar(
                con,
                """
                SELECT COUNT(*) FROM betting_odds_normalized
                WHERE match_name=? AND market_type LIKE 'player_%'
                  AND player_id IS NOT NULL AND player_id != ''
                """,
                (match,),
            ),
        }

        out["score_summary"] = {
            "score_rows": scalar(con, "SELECT COUNT(*) FROM betting_value_scores_new WHERE match_name=?", (match,)),
            "model_probability_rows": scalar(con, "SELECT COUNT(*) FROM betting_value_scores_new WHERE match_name=? AND model_probability IS NOT NULL", (match,)),
            "ev_rows": scalar(con, "SELECT COUNT(*) FROM betting_value_scores_new WHERE match_name=? AND expected_value IS NOT NULL", (match,)),
            "value_rows": scalar(con, "SELECT COUNT(*) FROM betting_value_scores_new WHERE match_name=? AND verdict='VALUE'", (match,)),
        }

        out["counts_by_market_type"] = rows(
            con,
            """
            SELECT market_type, COUNT(*) AS odds_rows,
                   SUM(player_id IS NOT NULL AND player_id != '') AS rows_with_player_id
            FROM betting_odds_normalized
            WHERE match_name=?
            GROUP BY market_type
            ORDER BY odds_rows DESC
            """,
            (match,),
        )
        out["counts_by_market_mapping_status"] = rows(
            con,
            """
            SELECT market_mapping_status, COUNT(*) AS rows
            FROM betting_odds_normalized
            WHERE match_name=?
            GROUP BY market_mapping_status
            ORDER BY rows DESC
            """,
            (match,),
        )
        out["counts_by_probability_status"] = rows(
            con,
            """
            SELECT probability_status, normalized_status, data_quality_status, verdict, COUNT(*) AS rows
            FROM betting_value_scores_new
            WHERE match_name=?
            GROUP BY probability_status, normalized_status, data_quality_status, verdict
            ORDER BY rows DESC
            """,
            (match,),
        )

        persisted_join = 0
        if table_exists(con, "betting_model_probabilities"):
            persisted_join = scalar(
                con,
                """
                SELECT COUNT(*)
                FROM betting_odds_normalized n
                JOIN betting_model_probabilities p
                  ON p.match_name=n.match_name
                 AND p.market_type=n.market_type
                 AND COALESCE(p.player_id,'')=COALESCE(n.player_id,'')
                 AND COALESCE(p.team_name,'')=COALESCE(n.team_name,'')
                 AND COALESCE(p.line,-999999)=COALESCE(n.line,-999999)
                WHERE n.match_name=?
                """,
                (match,),
            )

        normalized = con.execute(
            """
            SELECT *
            FROM betting_odds_normalized
            WHERE match_name=?
            """,
            (match,),
        ).fetchall()
        reason_counts = Counter(diagnose_row(con, row, home, away) for row in normalized)
        out["join_candidate_count"] = {
            "persisted_betting_model_probabilities_join": persisted_join,
            "runtime_model_candidates_after_all_guardrails": reason_counts.get("runtime_model_candidate", 0),
            "runtime_candidates_if_data_completeness_ignored": scalar(
                con,
                """
                SELECT COUNT(*)
                FROM betting_odds_normalized
                WHERE match_name=?
                  AND market_mapping_status='OK'
                  AND exact_market_match=1
                  AND normalized_status='ok'
                """,
                (match,),
            ),
        }
        out["unmatched_reason_counts"] = dict(reason_counts.most_common())

        out["conclusion"] = (
            "Qatar vs Switzerland has odds and StatHub source rows, but strict EV currently "
            "marks the match data_completeness_status=PARTIAL. calculate_probability returns "
            "INCOMPLETE_DATA before reading team/player histories, so model_probability stays NULL."
        )

    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
