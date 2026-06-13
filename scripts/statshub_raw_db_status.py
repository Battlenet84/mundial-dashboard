from __future__ import annotations

from app.db.connection import get_connection, init_db


TABLES = [
    ("raw events", "statshub_raw_events"),
    ("raw teams", "statshub_raw_teams"),
    ("raw players", "statshub_raw_players"),
    ("raw player performance", "statshub_raw_player_performance"),
    ("raw referees", "statshub_raw_referees"),
    ("raw lineups", "statshub_raw_lineups"),
    ("raw team events", "statshub_raw_team_events"),
    ("raw event extra stats", "statshub_raw_event_extra_stats"),
]


def main() -> None:
    init_db()
    with get_connection() as conn:
        counts = {label: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for label, table in TABLES}
        snapshots = conn.execute("SELECT snapshot_name, endpoint_name, status, created_at FROM statshub_snapshots ORDER BY id DESC LIMIT 5").fetchall()
        players = conn.execute("SELECT player_id, player_name, team_name, endpoint_name FROM statshub_raw_players ORDER BY id DESC LIMIT 5").fetchall()
        performance = conn.execute("SELECT player_id, player_name, team_name, tournament_id FROM statshub_raw_player_performance ORDER BY id DESC LIMIT 5").fetchall()
    print("STATUS STATSHUB RAW DB")
    print("Este comando no consume API.")
    for label, count in counts.items():
        print(f"{label}: {count}")
    print("Ultimos snapshots:")
    for row in snapshots:
        print(f"- {row['snapshot_name']} / {row['endpoint_name']}: {row['status']} {row['created_at']}")
    if not snapshots:
        print("- Sin snapshots")
    print("Latest raw players sample:")
    for row in players:
        print(dict(row))
    print("Latest raw performance sample:")
    for row in performance:
        print(dict(row))
    print("Todo dato local. No hay llamadas live desde este comando.")


if __name__ == "__main__":
    main()

