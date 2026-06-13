from __future__ import annotations

import argparse

from app.db.connection import get_connection, init_db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-name", required=True)
    args = parser.parse_args()
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT endpoint_name, status, priority, url, message FROM statshub_download_plan_items WHERE plan_name = ? ORDER BY priority, id",
            (args.plan_name,),
        ).fetchall()
    print("STATUS PLAN STATSHUB RAW")
    print("Este comando no consume API.")
    print(f"Plan: {args.plan_name}")
    for row in rows:
        print(f"- {row['priority']} {row['endpoint_name']}: {row['status']} {row['message'] or ''}")
    if not rows:
        print("- Sin items")


if __name__ == "__main__":
    main()

