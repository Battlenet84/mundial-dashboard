from __future__ import annotations

from app.db.connection import get_connection
from app.db.queries import insert_injury, insert_sync_log, utc_now
from app.ingestion.normalizers import normalize_injury
from app.providers.api_football import ApiFootballProvider


def sync_injuries(execute: bool = False, force: bool = False) -> int:
    started = utc_now()
    with get_connection() as conn:
        try:
            provider = ApiFootballProvider.from_settings(execute=execute, force=force)
            payload = provider.get_injuries()
            provider.save_raw_response("injuries", payload)
            response = payload.get("response", [])
            if not response:
                insert_sync_log(conn, "injuries", "WARNING", "endpoint sin datos", 0, started, utc_now())
                return 0
            for item in response:
                insert_injury(conn, normalize_injury(item))
            insert_sync_log(conn, "injuries", "OK", "lesiones sincronizadas", len(response), started, utc_now())
            return len(response)
        except Exception as exc:
            insert_sync_log(conn, "injuries", "WARNING", f"endpoint no disponible: {exc}", 0, started, utc_now())
            return 0


if __name__ == "__main__":
    print(f"Lesiones sincronizadas: {sync_injuries()}")
