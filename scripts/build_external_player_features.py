from __future__ import annotations

from app.db.connection import get_connection, init_db
from app.db.queries import utc_now


def per90(value, minutes):
    return (value or 0) * 90 / minutes if minutes else None


def build_features() -> int:
    init_db()
    count = 0
    with get_connection() as conn:
        groups = conn.execute(
            """
            SELECT source_name, season, player_name, normalized_player_name, team_name
            FROM external_player_stats
            GROUP BY source_name, season, player_name, team_name
            """
        ).fetchall()
        for group in groups:
            rows = conn.execute(
                """
                SELECT * FROM external_player_stats
                WHERE source_name = ? AND season = ? AND player_name = ?
                  AND COALESCE(team_name, '') = COALESCE(?, '')
                """,
                (group["source_name"], group["season"], group["player_name"], group["team_name"]),
            ).fetchall()
            def total(column):
                return sum((row[column] or 0) for row in rows)
            minutes = total("minutes")
            cards = total("yellow_cards") + total("red_cards")
            data = {
                "source_name": group["source_name"],
                "season": group["season"],
                "player_name": group["player_name"],
                "normalized_player_name": group["normalized_player_name"],
                "team_name": group["team_name"],
                "total_minutes": minutes,
                "total_appearances": total("appearances"),
                "total_goals": total("goals"),
                "total_assists": total("assists"),
                "total_shots": total("shots_total"),
                "total_shots_on": total("shots_on"),
                "total_key_passes": total("passes_key"),
                "total_fouls_committed": total("fouls_committed"),
                "total_fouls_drawn": total("fouls_drawn"),
                "total_yellow_cards": total("yellow_cards"),
                "total_red_cards": total("red_cards"),
                "total_tackles": total("tackles"),
                "total_interceptions": total("interceptions"),
                "total_xg": total("xg"),
                "total_xa": total("xa"),
                "shots_per_90": per90(total("shots_total"), minutes),
                "shots_on_per_90": per90(total("shots_on"), minutes),
                "goals_per_90": per90(total("goals"), minutes),
                "assists_per_90": per90(total("assists"), minutes),
                "key_passes_per_90": per90(total("passes_key"), minutes),
                "fouls_committed_per_90": per90(total("fouls_committed"), minutes),
                "fouls_drawn_per_90": per90(total("fouls_drawn"), minutes),
                "cards_per_90": per90(cards, minutes),
                "tackles_per_90": per90(total("tackles"), minutes),
                "interceptions_per_90": per90(total("interceptions"), minutes),
                "xg_per_90": per90(total("xg"), minutes),
                "xa_per_90": per90(total("xa"), minutes),
                "updated_at": utc_now(),
            }
            columns = list(data.keys())
            updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column not in {"source_name", "season", "player_name", "team_name"})
            conn.execute(
                f"""
                INSERT INTO external_player_model_features ({', '.join(columns)})
                VALUES ({', '.join(':' + column for column in columns)})
                ON CONFLICT(source_name, season, player_name, team_name)
                DO UPDATE SET {updates}
                """,
                data,
            )
            count += 1
    return count


def main() -> None:
    count = build_features()
    print(f"External player features generadas: {count}. Este comando no consume API.")


if __name__ == "__main__":
    main()

