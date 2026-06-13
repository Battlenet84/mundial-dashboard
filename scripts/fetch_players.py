from __future__ import annotations

import argparse

from app.providers.api_guard import require_explicit_execute
from app.providers.rate_limiter import get_budget_summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-requests", type=int, default=1)
    parser.add_argument("--team-id", type=int)
    parser.add_argument("--limit-teams", type=int)
    args = parser.parse_args()
    require_explicit_execute(args.execute)
    if not args.execute:
        print(f"Fetch players dry-run. Requests estimados: {args.max_requests}.")
        return
    if args.max_requests > get_budget_summary()["remaining_today"]:
        raise SystemExit("No hay presupuesto API suficiente.")
    from app.ingestion.sync_players import sync_players

    print(f"Jugadores sincronizados: {sync_players(execute=True, force=args.force, max_pages=args.max_requests)}")


if __name__ == "__main__":
    main()
