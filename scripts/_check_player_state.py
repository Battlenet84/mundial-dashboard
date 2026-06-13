"""Quick diagnostic: current player confirmation state for all 8 teams."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.betting.odds_driven import connect

TEAMS = ["Qatar","Switzerland","Brazil","Morocco","Haiti","Scotland","Australia","Turkey"]

with connect() as con:
    print("=== Player confirmation state ===")
    print(f"{'team':<15} {'roster':>6} {'confirmed':>9} {'unresolved':>10}")
    for t in TEAMS:
        r = con.execute(
            "SELECT COUNT(*), SUM(CASE WHEN statshub_player_id_status='confirmed' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN statshub_player_id_status='unresolved' THEN 1 ELSE 0 END) "
            "FROM statshub_team_players WHERE team_name=?", (t,)
        ).fetchone()
        print(f"{t:<15} {r[0]:>6} {(r[1] or 0):>9} {(r[2] or 0):>10}")

    print("\n=== StatsHub team IDs ===")
    rows = con.execute(
        "SELECT team_name, statshub_team_id FROM statshub_world_cup_teams "
        "WHERE team_name IN (?,?,?,?,?,?,?,?) ORDER BY team_name", tuple(TEAMS)
    ).fetchall()
    for r in rows:
        print(f"  {r[0]:<15} team_id={r[1]}")

    print("\n=== Performance event counts ===")
    for t in TEAMS:
        r = con.execute(
            "SELECT COUNT(*), SUM(CASE WHEN minutes_played>=15 THEN 1 ELSE 0 END) "
            "FROM statshub_player_performance_events sppe "
            "JOIN statshub_team_players stp ON sppe.player_id=stp.player_id "
            "WHERE stp.team_name=?", (t,)
        ).fetchone()
        print(f"  {t:<15} events={r[0] or 0:>5}  min15={r[1] or 0:>5}")

    print("\n=== Cached raw JSON files ===")
    import os
    raw_dir = ROOT / "data" / "raw" / "statshub"
    if raw_dir.exists():
        for f in sorted(raw_dir.glob("team_*_players*.json")):
            size_kb = f.stat().st_size // 1024
            print(f"  {f.name:<60} {size_kb:>6} KB")
