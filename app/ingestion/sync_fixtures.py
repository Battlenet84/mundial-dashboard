from __future__ import annotations

from app.db.connection import get_connection
from app.db.queries import insert_sync_log, upsert_fixture, utc_now
from app.ingestion.normalizers import normalize_fixture
from app.providers.api_football import ApiFootballProvider


def sync_fixtures(execute: bool = False, force: bool = False) -> int:
    started = utc_now()
    with get_connection() as conn:
        try:
            provider = ApiFootballProvider.from_settings(execute=execute, force=force)
            payload = provider.get_fixtures()
            provider.save_raw_response("fixtures", payload)
            rows = [normalize_fixture(item) for item in payload.get("response", [])]
            for row in rows:
                if row.get("provider_fixture_id"):
                    upsert_fixture(conn, row)
            insert_sync_log(conn, "fixtures", "OK", "fixtures sincronizados", len(rows), started, utc_now())
            return len(rows)
        except Exception as exc:
            insert_sync_log(conn, "fixtures", "ERROR", str(exc), 0, started, utc_now())
            raise


if __name__ == "__main__":
    print(f"Fixtures sincronizados: {sync_fixtures()}")
