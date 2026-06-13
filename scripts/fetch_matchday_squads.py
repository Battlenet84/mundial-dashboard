from __future__ import annotations

import argparse

from app.db.connection import get_connection, init_db
from app.db.queries import get_teams_for_date, get_teams_missing_squads_for_date, insert_sync_log, upsert_player, utc_now
from app.normalizers.api_football import normalize_squad_player
from app.providers.api_guard import require_explicit_execute
from app.providers.api_football import ApiFootballProvider
from app.providers.rate_limiter import get_budget_summary
from scripts.build_roster_features import main as build_roster_features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-requests", type=int)
    args = parser.parse_args()
    init_db()
    with get_connection() as conn:
        teams = get_teams_for_date(conn, args.date)
        missing = get_teams_missing_squads_for_date(conn, args.date)
    limit = args.max_requests if args.max_requests is not None else len(missing)
    to_fetch = missing[:limit]
    print("FETCH MATCHDAY SQUADS")
    print("Equipos involucrados:")
    for team in teams:
        print(f"- {team['team_name']} ({team['provider_team_id']})")
    print("Equipos a fetch:")
    for team in to_fetch:
        print(f"- {team['team_name']} ({team['provider_team_id']})")
    if not to_fetch:
        print("- Ninguno")
    require_explicit_execute(args.execute)
    if not args.execute:
        print(f"Dry-run. Requests estimados: {len(to_fetch)}.")
        return
    if len(to_fetch) > get_budget_summary()["remaining_today"]:
        raise SystemExit("No hay presupuesto API suficiente.")

    provider = ApiFootballProvider.from_settings(execute=True, force=args.force)
    total = 0
    started = utc_now()
    with get_connection() as conn:
        for team in to_fetch:
            payload = provider.get_team_squad(team["provider_team_id"])
            provider.save_raw_response("squads", payload, f"team_{team['provider_team_id']}")
            for block in payload.get("response", []):
                for player in block.get("players", []):
                    upsert_player(conn, normalize_squad_player(block, player))
                    total += 1
        insert_sync_log(conn, "matchday_squads", "OK", "squads de matchday sincronizados", total, started, utc_now(), estimated_requests=len(to_fetch), actual_requests=len(to_fetch))
    build_roster_features()
    print(f"Jugadores de squads guardados: {total}")


if __name__ == "__main__":
    main()

