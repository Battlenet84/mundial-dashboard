from __future__ import annotations

import argparse

from app.db.connection import get_connection, init_db
from app.db.queries import get_api_budget_summary, get_counts


EXPENSIVE = {"players", "lineups", "events", "statistics"}


def estimate_requests(args: argparse.Namespace) -> int:
    if args.dataset == "odds":
        return args.max_fixtures or (1 if args.fixture_id else 3)
    if args.dataset in {"lineups", "events", "statistics"}:
        return args.max_fixtures or (1 if args.fixture_id else 3)
    if args.dataset == "players":
        return args.limit_teams or (1 if args.team_id else 5)
    return 1


def build_execute_command(args: argparse.Namespace) -> str:
    if args.dataset == "players":
        command = "python -m scripts.fetch_players --execute"
        if args.team_id:
            command += f" --team-id {args.team_id}"
        if args.limit_teams:
            command += f" --limit-teams {args.limit_teams}"
        return command
    if args.dataset == "injuries":
        return "python -m scripts.fetch_injuries --execute"
    if args.dataset == "odds":
        command = "python -m scripts.fetch_odds --execute"
        if args.days:
            command += f" --days {args.days}"
        if args.max_fixtures:
            command += f" --max-fixtures {args.max_fixtures}"
        return command
    if args.dataset in {"lineups", "events", "statistics"}:
        command = f"python -m scripts.fetch_fixture_details --execute --dataset {args.dataset}"
        if args.fixture_id:
            command += f" --fixture-id {args.fixture_id}"
        return command
    return f"python -m app.ingestion.sync_{args.dataset} --execute"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, choices=["players", "injuries", "odds", "teams", "fixtures", "lineups", "events", "statistics"])
    parser.add_argument("--days", type=int)
    parser.add_argument("--max-fixtures", type=int)
    parser.add_argument("--fixture-id", type=int)
    parser.add_argument("--team-id", type=int)
    parser.add_argument("--limit-teams", type=int)
    args = parser.parse_args()

    init_db()
    with get_connection() as conn:
        counts = get_counts(conn)
    budget = get_api_budget_summary()
    estimated = estimate_requests(args)

    print("PLAN DE FETCH API - MUNDIAL 2026")
    print(f"Dataset: {args.dataset}")
    print(f"Datos locales actuales: {counts.get(args.dataset, 0)}")
    print(f"Requests estimados: {estimated}")
    print(f"Requests disponibles hoy: {budget['remaining_today']}")
    print(f"Entra en presupuesto: {'si' if estimated <= budget['remaining_today'] else 'no'}")
    if args.dataset in EXPENSIVE:
        print("Warning: dataset potencialmente caro; limitar alcance antes de ejecutar.")
    print("Comando para ejecutar luego:")
    print(build_execute_command(args))
    print("Este comando no consume API.")


if __name__ == "__main__":
    main()

