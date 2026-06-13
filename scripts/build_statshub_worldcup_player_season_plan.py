from __future__ import annotations

import argparse

from app.db.connection import get_connection, init_db
from app.db.queries import utc_now


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-name", required=True)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--max-players", type=int, default=25)
    parser.add_argument("--max-requests", type=int, default=25)
    args = parser.parse_args()
    limit = min(args.max_players, args.max_requests)
    init_db()
    with get_connection() as conn:
        players = conn.execute(
            """
            SELECT player_id, MIN(player_name) AS player_name
            FROM statshub_worldcup_players
            WHERE player_id IS NOT NULL AND player_id != ''
            GROUP BY player_id
            ORDER BY player_name
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.execute("DELETE FROM statshub_download_plan_items WHERE plan_name = ?", (args.plan_name,))
        for idx, player in enumerate(players, start=1):
            conn.execute(
                "INSERT INTO statshub_download_plan_items (plan_name, snapshot_name, endpoint_name, url, method, priority, source_reason, status, created_at) VALUES (?, ?, ?, ?, 'GET', ?, ?, 'planned', ?)",
                (
                    args.plan_name,
                    args.snapshot_name,
                    f"player_{player['player_id']}_tournaments",
                    f"https://www.statshub.com/api/player/{player['player_id']}/tournaments-and-seasons",
                    idx,
                    "world cup player season discovery",
                    utc_now(),
                ),
            )
    print("PLAN WORLDCUP PLAYER SEASONS")
    print("Este comando no consume API.")
    print(f"Players disponibles: {len(players)}")
    print(f"Requests planificados: {len(players)}")


if __name__ == "__main__":
    main()
