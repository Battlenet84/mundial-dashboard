from __future__ import annotations

import argparse
import json

from app.db.connection import get_connection, init_db
from app.db.queries import utc_now
from app.external.statshub_snapshot import find_common_field, iter_arrays


def combo_rows(raw_json: str, season_filter: str | None):
    payload = json.loads(raw_json)
    records = [payload] if isinstance(payload, dict) else []
    if isinstance(payload, dict):
        for _, items in iter_arrays(payload):
            records.extend(item for item in items if isinstance(item, dict))
    elif isinstance(payload, list):
        records.extend(item for item in payload if isinstance(item, dict))
    for item in records:
        team_id = find_common_field(item, ["teamId", "team_id"])
        tournament_id = find_common_field(item, ["tournamentId", "tournament_id", "id"])
        season_id = find_common_field(item, ["seasonId", "season_id"])
        name = str(find_common_field(item, ["seasonName", "name", "tournamentName"]) or "")
        if season_filter and season_filter.lower() not in name.lower():
            continue
        if team_id is not None and tournament_id is not None:
            yield str(team_id), str(tournament_id), str(season_id) if season_id is not None else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-name", required=True)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--max-players", type=int, default=25)
    parser.add_argument("--max-requests", type=int, default=50)
    parser.add_argument("--season-current-only", action="store_true", default=False)
    parser.add_argument("--season-name-contains")
    parser.add_argument("--dedupe", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    init_db()
    season_filter = args.season_name_contains if not args.season_current_only else "current"
    seen = set()
    items = []
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM statshub_raw_player_tournaments ORDER BY id LIMIT ?",
            (args.max_players,),
        ).fetchall()
        for row in rows:
            for team_id, tournament_id, season_id in combo_rows(row["raw_json"], season_filter):
                key = (team_id, tournament_id)
                if args.dedupe and key in seen:
                    continue
                seen.add(key)
                endpoint = f"team_{team_id}_tournament_{tournament_id}_performance"
                url = f"https://www.statshub.com/api/team/{team_id}/players/performance?tournamentId={tournament_id}&limit=50&location=both"
                items.append((endpoint, url, f"player {row['player_id']} team/tournament performance"))
                if len(items) >= args.max_requests:
                    break
            if len(items) >= args.max_requests:
                break
        conn.execute("DELETE FROM statshub_download_plan_items WHERE plan_name = ?", (args.plan_name,))
        for idx, (endpoint, url, reason) in enumerate(items, start=1):
            conn.execute(
                "INSERT INTO statshub_download_plan_items (plan_name, snapshot_name, endpoint_name, url, method, priority, source_reason, status, created_at) VALUES (?, ?, ?, ?, 'GET', ?, ?, 'planned', ?)",
                (args.plan_name, args.snapshot_name, endpoint, url, idx, reason, utc_now()),
            )
    print("PLAN WORLDCUP PERFORMANCE")
    print("Este comando no consume API.")
    print(f"Player tournament rows leidas: {len(rows)}")
    print(f"Team/tournament pairs dedupe: {len(seen)}")
    print(f"Requests planificados: {len(items)}")


if __name__ == "__main__":
    main()

