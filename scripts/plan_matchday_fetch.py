from __future__ import annotations

import argparse
import json

from app.db.connection import get_connection, init_db
from app.db.queries import get_api_budget_summary, get_matchday_plan_summary, get_teams_for_date, get_teams_missing_squads_for_date, insert_matchday_plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int)
    parser.add_argument("--max-players", type=int)
    args = parser.parse_args()
    init_db()
    with get_connection() as conn:
        summary = get_matchday_plan_summary(conn, args.date, args.max_players, args.season)
        teams = get_teams_for_date(conn, args.date)
        missing = get_teams_missing_squads_for_date(conn, args.date)
        insert_matchday_plan(conn, {
            "plan_date": args.date,
            "status": "planned",
            **{k: summary[k] for k in summary if k.endswith("_count") or k.startswith("estimated_")},
            "raw_plan_json": json.dumps(summary, ensure_ascii=False),
        })
    budget = get_api_budget_summary()
    print("PLAN MATCHDAY FETCH")
    print(f"Fecha: {args.date}")
    print(f"Partidos: {summary['fixtures_count']}")
    print("Equipos involucrados:")
    for team in teams:
        print(f"- {team['team_name']} ({team['provider_team_id']})")
    print("Equipos sin squad local:")
    for team in missing:
        print(f"- {team['team_name']} ({team['provider_team_id']})")
    if not missing:
        print("- Ninguno")
    print(f"Requests squads estimados: {summary['estimated_squad_requests']}")
    print(f"Requests stats jugadores estimados: {summary['estimated_player_stats_requests']}")
    print(f"Requests totales estimados: {summary['estimated_total_requests']}")
    print(f"Requests restantes hoy: {budget['remaining_today']}")
    print(f"Siguiente comando: python -m scripts.fetch_matchday_squads --date {args.date} --execute")
    print("Este comando no consume API.")


if __name__ == "__main__":
    main()

