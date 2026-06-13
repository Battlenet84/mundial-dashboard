from __future__ import annotations

import argparse

from app.db.connection import get_connection, init_db
from app.db.queries import (
    add_player_to_fetch_queue,
    get_players_for_teams,
    get_players_missing_stats,
    get_teams_for_date,
    insert_sync_log,
    update_player_fetch_queue_status,
    upsert_player_season_stat,
    utc_now,
)
from app.normalizers.api_football import normalize_player_season_stats
from app.providers.api_guard import require_explicit_execute
from app.providers.api_football import ApiFootballProvider
from app.providers.rate_limiter import get_budget_summary
from scripts.build_player_features import main as build_player_features


def _positions(text: str | None) -> list[str] | None:
    return [p.strip() for p in text.split(",") if p.strip()] if text else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--max-players", type=int, default=20)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--positions")
    args = parser.parse_args()
    init_db()
    with get_connection() as conn:
        teams = get_teams_for_date(conn, args.date)
        candidates = get_players_for_teams(conn, [row["provider_team_id"] for row in teams], _positions(args.positions))
        missing = candidates if args.force else get_players_missing_stats(conn, candidates, args.season)
        selected = missing[: args.max_players]
        if args.max_requests is not None:
            selected = selected[: args.max_requests]
    print("FETCH PLAYER STATS")
    print(f"Candidatos: {len(candidates)}")
    print(f"Seleccionados: {len(selected)}")
    require_explicit_execute(args.execute)
    if not args.execute:
        print(f"Dry-run. Requests estimados: {len(selected)}.")
        return
    if len(selected) > get_budget_summary()["remaining_today"]:
        raise SystemExit("No hay presupuesto API suficiente.")

    provider = ApiFootballProvider.from_settings(execute=True, force=args.force)
    total_rows = 0
    started = utc_now()
    with get_connection() as conn:
        for player in selected:
            add_player_to_fetch_queue(conn, {
                "provider": player["provider"],
                "provider_player_id": player["provider_player_id"],
                "player_name": player["name"],
                "provider_team_id": player["provider_team_id"],
                "team_name": player["team_name"],
                "match_date_utc": args.date,
                "priority": 1,
                "reason": "matchday player stats",
                "requested_season": args.season,
            })
            try:
                payload = provider.get_player_season_stats(player["provider_player_id"], args.season)
                provider.save_raw_response("player_season_stats", payload, f"player_{player['provider_player_id']}_season_{args.season}")
                rows = []
                for item in payload.get("response", []):
                    rows.extend(normalize_player_season_stats(item, args.season))
                for row in rows:
                    upsert_player_season_stat(conn, row)
                update_player_fetch_queue_status(conn, player["provider_player_id"], args.season, "fetched", f"{len(rows)} rows")
                total_rows += len(rows)
            except Exception as exc:
                update_player_fetch_queue_status(conn, player["provider_player_id"], args.season, "failed", str(exc))
                raise
        insert_sync_log(conn, "player_stats", "OK", "player season stats sincronizados", total_rows, started, utc_now(), estimated_requests=len(selected), actual_requests=len(selected))
    build_player_features()
    print(f"Filas player_season_stats guardadas: {total_rows}")


if __name__ == "__main__":
    main()

