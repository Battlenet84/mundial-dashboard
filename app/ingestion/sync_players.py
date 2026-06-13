from __future__ import annotations

from app.db.connection import get_connection
from app.db.queries import insert_sync_log, upsert_player, utc_now
from app.ingestion.normalizers import normalize_player
from app.providers.api_football import ApiFootballProvider


def sync_players(execute: bool = False, force: bool = False, max_pages: int = 100) -> int:
    started = utc_now()
    total = 0
    with get_connection() as conn:
        try:
            provider = ApiFootballProvider.from_settings(execute=execute, force=force)
            for page, payload in provider.iter_players_pages(max_pages=max_pages):
                provider.save_raw_response("players", payload, f"page_{page}")
                response = payload.get("response", [])
                if not response:
                    break
                for item in response:
                    row = normalize_player(item)
                    if row.get("provider_player_id") and row.get("name"):
                        upsert_player(conn, row)
                        total += 1
            insert_sync_log(conn, "players", "OK", "jugadores sincronizados", total, started, utc_now())
            return total
        except Exception as exc:
            insert_sync_log(conn, "players", "ERROR", str(exc), total, started, utc_now())
            raise


if __name__ == "__main__":
    print(f"Jugadores sincronizados: {sync_players()}")
