from __future__ import annotations

import argparse

from app.providers.api_guard import require_explicit_execute
from app.providers.rate_limiter import get_budget_summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-requests", type=int, default=1)
    args = parser.parse_args()
    require_explicit_execute(args.execute)
    if not args.execute:
        print(f"Fetch injuries dry-run. Requests estimados: {args.max_requests}.")
        return
    if args.max_requests > get_budget_summary()["remaining_today"]:
        raise SystemExit("No hay presupuesto API suficiente.")
    from app.ingestion.sync_injuries import sync_injuries

    print(f"Lesiones sincronizadas: {sync_injuries(execute=True, force=args.force)}")


if __name__ == "__main__":
    main()
