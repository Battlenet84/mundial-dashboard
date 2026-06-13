from __future__ import annotations

import argparse

from app.db.connection import get_connection, init_db
from app.db.queries import utc_now


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-name", required=True)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--max-teams", type=int, default=32)
    parser.add_argument("--max-requests", type=int, default=50)
    args = parser.parse_args()
    init_db()
    items = []
    with get_connection() as conn:
        teams = conn.execute(
            "SELECT DISTINCT team_id, team_name FROM statshub_worldcup_teams WHERE team_id IS NOT NULL ORDER BY team_name LIMIT ?",
            (args.max_teams,),
        ).fetchall()
        for team in teams:
            items.append((f"team_{team['team_id']}_tournaments", f"https://www.statshub.com/api/team/{team['team_id']}/tournaments-and-seasons", "team tournaments/seasons"))
            items.append((f"team_{team['team_id']}_events", f"https://www.statshub.com/api/team/{team['team_id']}/events?status=finished&limit=50", "team events history"))
            if len(items) >= args.max_requests:
                break
        items = items[: args.max_requests]
        conn.execute("DELETE FROM statshub_download_plan_items WHERE plan_name = ?", (args.plan_name,))
        for idx, (endpoint, url, reason) in enumerate(items, start=1):
            conn.execute(
                "INSERT INTO statshub_download_plan_items (plan_name, snapshot_name, endpoint_name, url, method, priority, source_reason, status, created_at) VALUES (?, ?, ?, ?, 'GET', ?, ?, 'planned', ?)",
                (args.plan_name, args.snapshot_name, endpoint, url, idx, reason, utc_now()),
            )
    print("PLAN WORLDCUP TEAM DATA")
    print("Este comando no consume API.")
    print(f"Teams disponibles: {len(teams)}")
    print(f"Requests planificados: {len(items)}")


if __name__ == "__main__":
    main()

