from __future__ import annotations

from app.db.connection import get_connection
from app.db.queries import insert_sync_log, upsert_team, utc_now
from app.ingestion.normalizers import normalize_team
from app.providers.api_football import ApiFootballProvider


def sync_teams(execute: bool = False, force: bool = False) -> int:
    started = utc_now()
    with get_connection() as conn:
        try:
            provider = ApiFootballProvider.from_settings(execute=execute, force=force)
            payload = provider.get_teams()
            provider.save_raw_response("teams", payload)
            rows = [normalize_team(item) for item in payload.get("response", [])]
            for row in rows:
                if row.get("provider_team_id") and row.get("name"):
                    upsert_team(conn, row)
            insert_sync_log(conn, "teams", "OK", "equipos sincronizados", len(rows), started, utc_now())
            return len(rows)
        except Exception as exc:
            insert_sync_log(conn, "teams", "ERROR", str(exc), 0, started, utc_now())
            raise


if __name__ == "__main__":
    print(f"Equipos sincronizados: {sync_teams()}")
