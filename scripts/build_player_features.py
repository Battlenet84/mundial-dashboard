from __future__ import annotations

import argparse

from app.db.connection import get_connection, init_db
from app.db.queries import upsert_player_model_features


def per90(value, minutes):
    return (value or 0) * 90 / minutes if minutes else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int)
    args = parser.parse_args()
    init_db()
    where = "WHERE season = ?" if args.season else ""
    params = (args.season,) if args.season else ()
    count = 0
    with get_connection() as conn:
        players = conn.execute(f"SELECT provider, provider_player_id, player_name, season FROM player_season_stats {where} GROUP BY provider, provider_player_id, season", params).fetchall()
        for player in players:
            rows = conn.execute(
                """
                SELECT * FROM player_season_stats
                WHERE provider = ? AND provider_player_id = ? AND season = ?
                """,
                (player["provider"], player["provider_player_id"], player["season"]),
            ).fetchall()
            def total(column):
                return sum((row[column] or 0) for row in rows)
            minutes = total("minutes")
            cards = total("cards_yellow") + total("cards_red")
            upsert_player_model_features(conn, {
                "provider": player["provider"],
                "provider_player_id": player["provider_player_id"],
                "player_name": player["player_name"],
                "season": player["season"],
                "total_minutes": minutes,
                "total_appearances": total("appearances"),
                "total_goals": total("goals_total"),
                "total_assists": total("goals_assists"),
                "total_shots": total("shots_total"),
                "total_shots_on": total("shots_on"),
                "total_key_passes": total("passes_key"),
                "total_fouls_committed": total("fouls_committed"),
                "total_fouls_drawn": total("fouls_drawn"),
                "total_yellow_cards": total("cards_yellow"),
                "total_red_cards": total("cards_red"),
                "total_tackles": total("tackles_total"),
                "total_interceptions": total("tackles_interceptions"),
                "total_dribble_attempts": total("dribbles_attempts"),
                "total_dribble_success": total("dribbles_success"),
                "shots_per_90": per90(total("shots_total"), minutes),
                "shots_on_per_90": per90(total("shots_on"), minutes),
                "goals_per_90": per90(total("goals_total"), minutes),
                "assists_per_90": per90(total("goals_assists"), minutes),
                "key_passes_per_90": per90(total("passes_key"), minutes),
                "fouls_committed_per_90": per90(total("fouls_committed"), minutes),
                "fouls_drawn_per_90": per90(total("fouls_drawn"), minutes),
                "cards_per_90": per90(cards, minutes),
                "tackles_per_90": per90(total("tackles_total"), minutes),
                "interceptions_per_90": per90(total("tackles_interceptions"), minutes),
            })
            count += 1
    print(f"Player model features recalculadas: {count}. Este comando no consume API.")


if __name__ == "__main__":
    main()

