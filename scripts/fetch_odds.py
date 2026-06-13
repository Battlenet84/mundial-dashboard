from __future__ import annotations

import argparse

from app.providers.api_guard import require_explicit_execute
from app.providers.rate_limiter import get_budget_summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--days", type=int)
    parser.add_argument("--fixture-id", type=int)
    parser.add_argument("--max-fixtures", type=int, default=1)
    parser.add_argument("--max-requests", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    require_explicit_execute(args.execute)
    if not args.execute:
        print(f"Fetch odds dry-run. Requests estimados: {args.max_requests}.")
        return
    if args.max_requests > get_budget_summary()["remaining_today"]:
        raise SystemExit("No hay presupuesto API suficiente.")
    from app.ingestion.sync_odds import sync_odds

    print(f"Snapshots de cuotas insertados: {sync_odds(execute=True, force=args.force, max_fixtures=args.max_fixtures)}")


if __name__ == "__main__":
    main()
