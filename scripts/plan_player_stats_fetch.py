from __future__ import annotations

import argparse

from app.db.connection import get_connection, init_db
from app.db.queries import get_api_budget_summary, get_players_for_teams, get_players_missing_stats, get_teams_for_date


def _positions(text: str | None) -> list[str] | None:
    return [p.strip() for p in text.split(",") if p.strip()] if text else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--max-players", type=int, default=20)
    parser.add_argument("--positions")
    parser.add_argument("--priority-mode", default="simple")
    args = parser.parse_args()
    init_db()
    with get_connection() as conn:
        teams = get_teams_for_date(conn, args.date)
        team_ids = [row["provider_team_id"] for row in teams]
        candidates = get_players_for_teams(conn, team_ids, _positions(args.positions))
        missing = get_players_missing_stats(conn, candidates, args.season)
        selected = missing[: args.max_players]
    budget = get_api_budget_summary()
    print("PLAN PLAYER STATS FETCH")
    print(f"Fecha: {args.date}")
    print(f"Temporada: {args.season}")
    print(f"Candidatos: {len(candidates)}")
    print(f"Ya tienen stats: {len(candidates) - len(missing)}")
    print(f"Seleccionados: {len(selected)}")
    for player in selected:
        print(f"- {player['name']} | {player['team_name']} | {player['position']}")
    print(f"Requests estimados: {len(selected)}")
    print(f"Requests restantes hoy: {budget['remaining_today']}")
    print(f"Comando recomendado: python -m scripts.fetch_player_stats --date {args.date} --season {args.season} --max-players {args.max_players} --execute")
    print("Este comando no consume API.")


if __name__ == "__main__":
    main()

