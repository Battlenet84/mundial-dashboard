from __future__ import annotations

import argparse

from app.db.connection import init_db
from app.ingestion.sync_fixtures import sync_fixtures
from app.ingestion.sync_injuries import sync_injuries
from app.ingestion.sync_odds import sync_odds
from app.ingestion.sync_players import sync_players
from app.ingestion.sync_teams import sync_teams


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--include-expensive", action="store_true")
    args = parser.parse_args()

    init_db()
    if not args.execute:
        print("Modo dry-run: sync_all no hizo llamadas reales de API.")
        print("Un sync completo puede consumir muchos requests. Usa scripts de planificacion primero:")
        print("python -m scripts.plan_data_sources")
        print("python -m scripts.plan_api_fetch --dataset players")
        print("Para ejecutar luego: python -m app.ingestion.sync_all --execute")
        return

    print("Advertencia: sync_all real puede consumir muchos requests de API.")
    steps = [
        ("teams", sync_teams),
        ("fixtures", sync_fixtures),
        ("injuries", sync_injuries),
        ("odds", sync_odds),
    ]
    if args.include_expensive:
        steps.insert(2, ("players", sync_players))
    for name, func in steps:
        try:
            count = func(execute=True)
            print(f"{name}: OK ({count})")
        except Exception as exc:
            print(f"{name}: ERROR - {exc}")


if __name__ == "__main__":
    main()
