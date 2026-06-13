from __future__ import annotations

import argparse

from app.db.connection import get_connection, init_db
from app.db.queries import insert_sync_log, update_sync_state, upsert_fixture, upsert_team, utc_now
from app.normalizers.api_football import normalize_fixture, normalize_team
from app.providers.api_guard import require_explicit_execute
from app.providers.api_football import ApiFootballProvider
from app.providers.rate_limiter import get_budget_summary


def _payload_context(payload: dict) -> str:
    return (
        f"params={payload.get('parameters')} "
        f"errors={payload.get('errors')} "
        f"results={payload.get('results')}"
    )


def _store_core_response(conn, sync_name: str, payload: dict, rows: list[dict], required_fields: tuple[str, ...], upsert_func, started: str) -> int:
    response = payload.get("response", [])
    if not isinstance(response, list):
        message = f"response invalido; {_payload_context(payload)}"
        print(f"{sync_name}: ERROR - {message}")
        insert_sync_log(conn, sync_name, "ERROR", message, 0, started, utc_now(), estimated_requests=1, actual_requests=1)
        return 0
    if not response:
        message = f"response vacio; {_payload_context(payload)}"
        print(f"{sync_name}: WARNING - {message}")
        insert_sync_log(conn, sync_name, "WARNING", message, 0, started, utc_now(), estimated_requests=1, actual_requests=1)
        return 0

    upserted = 0
    skipped = 0
    for row in rows:
        if all(row.get(field) for field in required_fields):
            upsert_func(conn, row)
            upserted += 1
        else:
            skipped += 1
    if upserted > 0:
        message = f"{sync_name} sincronizados; skipped={skipped}"
        insert_sync_log(conn, sync_name, "OK", message, upserted, started, utc_now(), estimated_requests=1, actual_requests=1)
        update_sync_state(conn, {"sync_name": sync_name, "last_success_at": utc_now(), "records_count": upserted, "freshness_hours": 24, "next_recommended_sync": None, "status": "OK", "message": "core fetch"})
        return upserted

    message = f"normalizer inserto 0 registros con response length={len(response)}; skipped={skipped}; {_payload_context(payload)}"
    print(f"{sync_name}: ERROR - {message}")
    insert_sync_log(conn, sync_name, "ERROR", message, 0, started, utc_now(), estimated_requests=1, actual_requests=1)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-coverage", action="store_true")
    parser.add_argument("--skip-teams", action="store_true")
    parser.add_argument("--skip-fixtures", action="store_true")
    args = parser.parse_args()

    tasks = [
        ("coverage", not args.skip_coverage),
        ("teams", not args.skip_teams),
        ("fixtures", not args.skip_fixtures),
    ]
    estimated = sum(1 for _, enabled in tasks if enabled)
    require_explicit_execute(args.execute)
    if not args.execute:
        print(f"Core fetch dry-run. Requests estimados: {estimated}.")
        print("No se consumio API.")
        return
    if estimated > get_budget_summary()["remaining_today"]:
        raise SystemExit("No hay presupuesto API suficiente.")

    init_db()
    provider = ApiFootballProvider.from_settings(execute=True, force=args.force)
    started = utc_now()
    with get_connection() as conn:
        if not args.skip_coverage:
            payload = provider.get_worldcup_coverage()
            provider.save_raw_response("coverage", payload)
            insert_sync_log(conn, "coverage", "OK", "coverage guardado raw", 0, started, utc_now(), estimated_requests=1, actual_requests=1)
        if not args.skip_teams:
            payload = provider.get_worldcup_teams()
            provider.save_raw_response("teams", payload)
            rows = [normalize_team(item) for item in payload.get("response", [])]
            _store_core_response(conn, "teams", payload, rows, ("provider_team_id", "name"), upsert_team, started)
        if not args.skip_fixtures:
            payload = provider.get_worldcup_fixtures()
            provider.save_raw_response("fixtures", payload)
            rows = [normalize_fixture(item) for item in payload.get("response", [])]
            _store_core_response(conn, "fixtures", payload, rows, ("provider_fixture_id",), upsert_fixture, started)
    print("Core fetch ejecutado.")


if __name__ == "__main__":
    main()
