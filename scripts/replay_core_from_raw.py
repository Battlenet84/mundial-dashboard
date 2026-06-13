from __future__ import annotations

from app.db.connection import get_connection, init_db
from app.db.queries import insert_sync_log, update_sync_state, upsert_fixture, upsert_team, utc_now
from app.normalizers.api_football import normalize_fixture, normalize_team
from scripts.raw_core_utils import latest_json_file, load_json


def _replay_dataset(conn, category: str, normalizer, upsert_func, required_fields: tuple[str, ...]) -> tuple[int, int, str, str]:
    started = utc_now()
    path = latest_json_file(category)
    if path is None:
        message = f"raw {category} faltante"
        insert_sync_log(conn, category, "ERROR", message, 0, started, utc_now())
        return 0, 0, "ERROR", message
    try:
        payload = load_json(path)
    except Exception as exc:
        message = f"raw {category} malformado: {exc}"
        insert_sync_log(conn, category, "ERROR", message, 0, started, utc_now())
        return 0, 0, "ERROR", message

    response = payload.get("response", [])
    if not isinstance(response, list):
        message = f"raw {category} response no es lista"
        insert_sync_log(conn, category, "ERROR", message, 0, started, utc_now())
        return 0, 0, "ERROR", message
    if not response:
        message = f"raw {category} existe pero response esta vacio; results={payload.get('results')} errors={payload.get('errors')}"
        insert_sync_log(conn, category, "WARNING", message, 0, started, utc_now())
        return 0, 0, "WARNING", message

    upserted = 0
    skipped = 0
    for item in response:
        row = normalizer(item)
        if all(row.get(field) for field in required_fields):
            upsert_func(conn, row)
            upserted += 1
        else:
            skipped += 1
    if upserted > 0:
        message = f"replay desde raw OK; skipped={skipped}"
        insert_sync_log(conn, category, "OK", message, upserted, started, utc_now())
        update_sync_state(conn, {"sync_name": category, "last_success_at": utc_now(), "records_count": upserted, "freshness_hours": 24, "next_recommended_sync": None, "status": "OK", "message": "replay raw"})
        return len(response), upserted, "OK", message
    message = f"raw {category} tenia {len(response)} registros pero normalizacion inserto 0; skipped={skipped}"
    insert_sync_log(conn, category, "ERROR", message, 0, started, utc_now())
    return len(response), 0, "ERROR", message


def main() -> None:
    init_db()
    print("REPLAY CORE DESDE RAW - MUNDIAL 2026")
    print("Este comando no consume API.")
    with get_connection() as conn:
        teams_raw, teams_upserted, teams_status, teams_message = _replay_dataset(
            conn,
            "teams",
            normalize_team,
            upsert_team,
            ("provider_team_id", "name"),
        )
        fixtures_raw, fixtures_upserted, fixtures_status, fixtures_message = _replay_dataset(
            conn,
            "fixtures",
            normalize_fixture,
            upsert_fixture,
            ("provider_fixture_id",),
        )
    print(f"Teams raw response count: {teams_raw}")
    print(f"Teams upserted count: {teams_upserted}")
    print(f"Teams status: {teams_status} - {teams_message}")
    print(f"Fixtures raw response count: {fixtures_raw}")
    print(f"Fixtures upserted count: {fixtures_upserted}")
    print(f"Fixtures status: {fixtures_status} - {fixtures_message}")


if __name__ == "__main__":
    main()

