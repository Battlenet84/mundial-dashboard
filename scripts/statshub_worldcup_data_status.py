from __future__ import annotations

from app.db.connection import get_connection, init_db


def main() -> None:
    init_db()
    with get_connection() as conn:
        counts = {
            "World Cup seed teams": conn.execute("SELECT COUNT(*) FROM statshub_worldcup_teams").fetchone()[0],
            "World Cup seed players": conn.execute("SELECT COUNT(*) FROM statshub_worldcup_players").fetchone()[0],
            "player tournament raw rows": conn.execute("SELECT COUNT(*) FROM statshub_raw_player_tournaments").fetchone()[0],
            "team tournament raw rows": conn.execute("SELECT COUNT(*) FROM statshub_raw_team_tournaments").fetchone()[0],
            "team season event raw rows": conn.execute("SELECT COUNT(*) FROM statshub_raw_team_season_events").fetchone()[0],
            "world cup player performance raw rows": conn.execute("SELECT COUNT(*) FROM statshub_raw_worldcup_player_performance").fetchone()[0],
        }
        no_tournaments = conn.execute(
            """
            SELECT COUNT(*) FROM statshub_worldcup_players p
            WHERE NOT EXISTS (
                SELECT 1 FROM statshub_raw_player_tournaments t
                WHERE t.player_id = p.player_id
            )
            """
        ).fetchone()[0]
        no_performance = conn.execute(
            """
            SELECT COUNT(*) FROM statshub_worldcup_players p
            WHERE NOT EXISTS (
                SELECT 1 FROM statshub_raw_worldcup_player_performance perf
                WHERE perf.player_id = p.player_id
            )
            """
        ).fetchone()[0]
        players = conn.execute("SELECT player_id, player_name, team_name FROM statshub_worldcup_players LIMIT 5").fetchall()
        teams = conn.execute("SELECT team_id, team_name FROM statshub_worldcup_teams LIMIT 5").fetchall()
        perf = conn.execute("SELECT player_id, player_name, team_name, tournament_id FROM statshub_raw_worldcup_player_performance LIMIT 5").fetchall()
    print("STATUS STATSHUB WORLDCUP DATA")
    print("Este comando no consume API.")
    for label, value in counts.items():
        print(f"{label}: {value}")
    print(f"players with no tournament data: {no_tournaments}")
    print(f"players with no performance data: {no_performance}")
    print("sample players:")
    for row in players:
        print(dict(row))
    print("sample teams:")
    for row in teams:
        print(dict(row))
    print("sample raw performance rows:")
    for row in perf:
        print(dict(row))


if __name__ == "__main__":
    main()

