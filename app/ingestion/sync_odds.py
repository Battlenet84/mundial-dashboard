from __future__ import annotations

from app.db.connection import get_connection
from app.db.queries import insert_odds_snapshot, insert_sync_log, utc_now
from app.models.implied_probability import decimal_to_implied_probability
from app.providers.api_football import ApiFootballProvider


def _iter_odds_rows(payload: dict, fixture_id: int):
    for fixture_block in payload.get("response", []):
        for bookmaker in fixture_block.get("bookmakers", []):
            bookmaker_name = bookmaker.get("name")
            for bet in bookmaker.get("bets", []):
                market = bet.get("name")
                for value in bet.get("values", []):
                    odd_text = value.get("odd")
                    try:
                        decimal_odds = float(odd_text)
                        implied = decimal_to_implied_probability(decimal_odds)
                    except (TypeError, ValueError):
                        continue
                    yield {
                        "provider": "api_football",
                        "provider_fixture_id": fixture_id,
                        "bookmaker": bookmaker_name,
                        "market": market,
                        "selection": value.get("value"),
                        "decimal_odds": decimal_odds,
                        "implied_probability": implied,
                    }


def sync_odds(execute: bool = False, force: bool = False, max_fixtures: int | None = None) -> int:
    started = utc_now()
    inserted = 0
    with get_connection() as conn:
        try:
            fixtures = conn.execute(
                """
                SELECT provider_fixture_id
                FROM fixtures
                WHERE status_short IS NULL OR status_short NOT IN ('FT', 'AET', 'PEN', 'CANC', 'PST')
                ORDER BY date_utc
                """
            ).fetchall()
            if max_fixtures is not None:
                fixtures = fixtures[:max_fixtures]
            provider = ApiFootballProvider.from_settings(execute=execute, force=force)
            for fixture in fixtures:
                fixture_id = fixture["provider_fixture_id"]
                payload = provider.get_fixture_odds(fixture_id)
                provider.save_raw_response("odds", payload, f"fixture_{fixture_id}")
                for row in _iter_odds_rows(payload, fixture_id):
                    insert_odds_snapshot(conn, row)
                    inserted += 1
            insert_sync_log(conn, "odds", "OK", "snapshots de cuotas insertados", inserted, started, utc_now())
            return inserted
        except Exception as exc:
            insert_sync_log(conn, "odds", "ERROR", str(exc), inserted, started, utc_now())
            raise


if __name__ == "__main__":
    print(f"Snapshots de cuotas insertados: {sync_odds()}")
