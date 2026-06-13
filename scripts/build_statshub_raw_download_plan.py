from __future__ import annotations

import argparse
from pathlib import Path

from app.db.connection import get_connection, init_db
from app.db.queries import utc_now
from app.external.statshub_snapshot import extract_ids, parse_json_if_possible


def add_item(items, endpoint_name, url, priority, reason):
    blocked = ["props/screener", "props/player-trends", "player-odds"]
    if any(part in url for part in blocked):
        return
    items.append((endpoint_name, url, priority, reason))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-name", required=True)
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--from-event-file", required=True)
    parser.add_argument("--date")
    parser.add_argument("--include-players", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-team-performance", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-referees", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--include-lineups", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-team-events", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--include-extra-stats", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--max-events", type=int, default=8)
    parser.add_argument("--max-teams", type=int, default=16)
    parser.add_argument("--max-requests", type=int, default=30)
    args = parser.parse_args()
    payload = parse_json_if_possible(Path(args.from_event_file).read_text(encoding="utf-8", errors="ignore"))
    if payload is None:
        raise SystemExit("JSON invalido.")
    ids = extract_ids(payload)
    event_ids = list(ids["events"].keys())[: args.max_events]
    team_ids = list(ids["teams"].keys())[: args.max_teams]
    tournament_ids = list(ids["tournaments"].keys())
    tournament_id = tournament_ids[0] if tournament_ids else ""
    items = []
    if args.include_players and event_ids:
        add_item(items, "players_from_screener", "https://www.statshub.com/api/players/from-screener?eventIds=" + ",".join(event_ids), 10, "players from event ids")
    if args.include_team_performance and tournament_id:
        for team_id in team_ids:
            add_item(items, f"team_{team_id}_performance", f"https://www.statshub.com/api/team/{team_id}/players/performance?tournamentId={tournament_id}&limit=50&location=both", 20, "team player performance")
    if args.include_lineups and event_ids:
        add_item(items, "lineup_status", "https://www.statshub.com/api/event/lineup-status?ids=" + ",".join(event_ids), 30, "lineup status")
        for event_id in event_ids:
            add_item(items, f"event_{event_id}_predicted_lineup", f"https://www.statshub.com/api/event/{event_id}/predicted-teams-lineup", 31, "predicted lineup")
            for team_id in team_ids[:2]:
                add_item(items, f"event_{event_id}_team_{team_id}_lineup", f"https://www.statshub.com/api/event/{event_id}/team-lineup?teamId={team_id}&startingLineup=true", 32, "team lineup")
    if args.include_team_events:
        for team_id in team_ids:
            add_item(items, f"team_{team_id}_events", f"https://www.statshub.com/api/team/{team_id}/events?status=finished&limit=20", 40, "team history")
    if args.include_extra_stats:
        for event_id in event_ids:
            add_item(items, f"event_{event_id}_extra_stats", f"https://www.statshub.com/api/event/extra-stats?eventId={event_id}", 50, "event extra stats")
    items = items[: args.max_requests]
    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM statshub_download_plan_items WHERE plan_name = ?", (args.plan_name,))
        for endpoint_name, url, priority, reason in items:
            conn.execute(
                "INSERT INTO statshub_download_plan_items (plan_name, snapshot_name, endpoint_name, url, method, priority, source_reason, status, created_at) VALUES (?, ?, ?, ?, 'GET', ?, ?, 'planned', ?)",
                (args.plan_name, args.snapshot_name, endpoint_name, url, priority, reason, utc_now()),
            )
    print("PLAN RAW STATSHUB")
    print("Este comando no consume API.")
    print(f"Eventos encontrados: {len(event_ids)}")
    print(f"Teams encontrados: {len(team_ids)}")
    print(f"Torneos encontrados: {len(tournament_ids)}")
    print(f"Requests planificados: {len(items)}")
    for endpoint_name, url, priority, reason in items:
        print(f"- {priority} {endpoint_name}: {url} ({reason})")
    print(f"Siguiente comando: python -m scripts.run_statshub_raw_download_plan --plan-name {args.plan_name} --max-requests {args.max_requests} --execute")


if __name__ == "__main__":
    main()

