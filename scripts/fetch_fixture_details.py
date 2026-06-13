from __future__ import annotations

import argparse

from app.providers.api_guard import require_explicit_execute
from app.providers.api_football import ApiFootballProvider
from app.providers.rate_limiter import get_budget_summary
from app.db.connection import get_connection, init_db
from app.db.queries import insert_fixture_event, insert_fixture_lineup, insert_fixture_statistic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--fixture-id", type=int)
    parser.add_argument("--dataset", required=True, choices=["lineups", "events", "statistics"])
    parser.add_argument("--max-requests", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    require_explicit_execute(args.execute)
    if not args.execute:
        print(f"Fetch {args.dataset} dry-run. Requests estimados: {args.max_requests}.")
        return
    if not args.fixture_id:
        raise SystemExit("--fixture-id requerido con --execute")
    if args.max_requests > get_budget_summary()["remaining_today"]:
        raise SystemExit("No hay presupuesto API suficiente.")
    init_db()
    provider = ApiFootballProvider.from_settings(execute=True, force=args.force)
    if args.dataset == "lineups":
        payload = provider.get_fixture_lineups(args.fixture_id)
        provider.save_raw_response("lineups", payload, f"fixture_{args.fixture_id}")
        count = _save_lineups(payload, args.fixture_id)
    elif args.dataset == "events":
        payload = provider.get_fixture_events(args.fixture_id)
        provider.save_raw_response("events", payload, f"fixture_{args.fixture_id}")
        count = _save_events(payload, args.fixture_id)
    else:
        payload = provider.get_fixture_statistics(args.fixture_id)
        provider.save_raw_response("statistics", payload, f"fixture_{args.fixture_id}")
        count = _save_statistics(payload, args.fixture_id)
    print(f"{args.dataset} guardado: {count} registros.")


def _save_statistics(payload: dict, fixture_id: int) -> int:
    count = 0
    with get_connection() as conn:
        for block in payload.get("response", []):
            team = block.get("team") or {}
            for stat in block.get("statistics", []):
                insert_fixture_statistic(conn, {
                    "provider": "api_football",
                    "provider_fixture_id": fixture_id,
                    "team_provider_id": team.get("id"),
                    "team_name": team.get("name"),
                    "stat_type": stat.get("type"),
                    "stat_value": str(stat.get("value")),
                })
                count += 1
    return count


def _save_lineups(payload: dict, fixture_id: int) -> int:
    count = 0
    with get_connection() as conn:
        for block in payload.get("response", []):
            team = block.get("team") or {}
            coach = block.get("coach") or {}
            for group, is_starting in [("startXI", 1), ("substitutes", 0)]:
                for item in block.get(group, []):
                    player = item.get("player") or {}
                    insert_fixture_lineup(conn, {
                        "provider": "api_football",
                        "provider_fixture_id": fixture_id,
                        "team_provider_id": team.get("id"),
                        "team_name": team.get("name"),
                        "formation": block.get("formation"),
                        "coach_name": coach.get("name"),
                        "player_provider_id": player.get("id"),
                        "player_name": player.get("name"),
                        "player_number": player.get("number"),
                        "player_position": player.get("pos"),
                        "is_starting": is_starting,
                        "grid": player.get("grid"),
                    })
                    count += 1
    return count


def _save_events(payload: dict, fixture_id: int) -> int:
    count = 0
    with get_connection() as conn:
        for item in payload.get("response", []):
            time = item.get("time") or {}
            team = item.get("team") or {}
            player = item.get("player") or {}
            assist = item.get("assist") or {}
            insert_fixture_event(conn, {
                "provider": "api_football",
                "provider_fixture_id": fixture_id,
                "elapsed": time.get("elapsed"),
                "extra_time": time.get("extra"),
                "team_provider_id": team.get("id"),
                "team_name": team.get("name"),
                "player_provider_id": player.get("id"),
                "player_name": player.get("name"),
                "assist_provider_id": assist.get("id"),
                "assist_name": assist.get("name"),
                "event_type": item.get("type"),
                "detail": item.get("detail"),
                "comments": item.get("comments"),
            })
            count += 1
    return count


if __name__ == "__main__":
    main()
