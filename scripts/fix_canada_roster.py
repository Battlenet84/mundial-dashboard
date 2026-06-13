"""Apply Canada roster corrections: LUMPUNGU→Bombito, DAVID#10→Jonathan, DAVID#24→Promise."""
import sys, json, pathlib, time, requests
from datetime import datetime, timezone
import sqlite3

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = pathlib.Path("data/mundial.db")
RAW_DIR = pathlib.Path("data/raw/statshub/snapshots/today_final_match_stats_probe")
BASE_URL = "https://www.statshub.com/api"
HEADERS  = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
NOW = datetime.now(timezone.utc).isoformat()

FIXES = [
    # (db_row_id, correct_name, statshub_player_id, jersey)
    (6555, "Moise Bombito",   "1469180", "15"),
    (6550, "Jonathan David",  "935564",  "10"),
    (6564, "Promise David",   "1119328", "24"),
]

def _to_float(v):
    try: return float(v)
    except: return None

def fetch_perf(pid):
    for snap in ["today_final_match_stats_probe",
                 "today_playwright_fixture_players_probe",
                 "today_browser_endpoint_replay_probe"]:
        d = pathlib.Path("data/raw/statshub/snapshots") / snap
        hits = list(d.glob(f"perf_{pid}*.json")) if d.exists() else []
        if hits:
            try: return json.loads(hits[0].read_text(encoding="utf-8"))
            except: pass
    time.sleep(1.5)
    r = requests.get(f"{BASE_URL}/player/{pid}/performance?limit=50",
                     headers=HEADERS, timeout=20)
    if r.status_code == 200 and "json" in r.headers.get("content-type",""):
        payload = r.json()
        (RAW_DIR / f"perf_{pid}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    return None

def parse_and_upsert(cur, pid, name, payload):
    items = payload.get("playerStatisticsEvents") or payload.get("data") or []
    apps=minutes=goals=assists=sot=kp=tp=ap=tac=pl=yc=rc=0; xg=xa=0.0; dates=[]
    for item in items:
        stats = item.get("player_statistics_event") or item
        mp = int(stats.get("minutesPlayed") or 0)
        if mp > 0: apps+=1; minutes+=mp
        goals   += stats.get("goals") or 0
        assists += stats.get("goalAssist") or 0
        sot     += stats.get("onTargetScoringAttempt") or 0
        kp      += stats.get("keyPass") or 0
        tp      += stats.get("totalPass") or 0
        ap      += stats.get("accuratePass") or 0
        tac     += stats.get("totalTackle") or 0
        pl      += stats.get("possessionLostCtrl") or 0
        yc      += stats.get("yellowCard") or 0
        rc      += stats.get("redCard") or 0
        xg      += _to_float(stats.get("expectedGoals")) or 0.0
        xa      += _to_float(stats.get("expectedAssists")) or 0.0
        ts = (item.get("events") or {}).get("startTimestamp")
        if ts:
            try: dates.append(datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d"))
            except: pass
    dates.sort()
    cur.execute("""
        INSERT OR REPLACE INTO statshub_player_performance_aggregates
            (snapshot_name, player_id, player_name, team_name, endpoint_name,
             source_rows, appearances, minutes, goals, assists, shots_on_target,
             xG, xA, key_passes, passes, accurate_passes, tackles, possession_lost,
             yellow_cards, red_cards, date_min, date_max, imported_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, ("today_final_match_stats_probe", pid, name, "Canada", "player_performance",
          len(items), apps, minutes, goals, assists, sot,
          round(xg,4) if xg else None, round(xa,4) if xa else None,
          kp, tp, ap, tac, pl, yc, rc,
          dates[0] if dates else None, dates[-1] if dates else None, NOW))
    return apps, minutes, goals, assists

def main():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    print("=== Step 1: Apply roster corrections ===")
    for row_id, name, pid, jersey in FIXES:
        cur.execute("""
            UPDATE statshub_team_players
            SET player_name=?, player_id=?,
                statshub_player_id_status='confirmed',
                player_id_match_source='manual_roster_correction',
                player_id_confidence_score=99.0
            WHERE id=?
        """, (name, pid, row_id))
        print(f"  #{jersey} → {name}  player_id={pid}")
    con.commit()

    # Verify no duplicates
    cur.execute("""
        SELECT player_id, COUNT(*) cnt FROM statshub_team_players sp
        JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
        WHERE wt.team_name = 'Canada' AND player_id IS NOT NULL
        GROUP BY player_id HAVING cnt > 1
    """)
    dups = cur.fetchall()
    print("  Duplicate player_ids:", [dict(r) for r in dups] if dups else "none ✓")

    print("\n=== Step 2: Download / refresh performance ===")
    for _, name, pid, jersey in FIXES:
        payload = fetch_perf(pid)
        if not payload:
            print(f"  #{jersey} {name}: FETCH FAILED")
            continue
        apps, minutes, goals, assists = parse_and_upsert(cur, pid, name, payload)
        con.commit()
        print(f"  #{jersey} {name} (id={pid}): apps={apps} min={minutes} G={goals} A={assists}")

    print("\n=== Step 3: Canada coverage ===")
    cur.execute("""
        SELECT statshub_player_id_status, COUNT(*) cnt
        FROM statshub_team_players sp
        JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
        WHERE wt.team_name = 'Canada'
        GROUP BY statshub_player_id_status
    """)
    s = {r[0]: r[1] for r in cur.fetchall()}
    total = sum(s.values())
    conf  = s.get("confirmed",0) + s.get("skipped_existing",0)
    print(f"  {conf}/{total} confirmed ({round(100*conf/total,1)}%)  breakdown: {s}")
    print()

    cur.execute("""
        SELECT sp.jersey_number, sp.player_name, sp.statshub_player_id_status, sp.player_id
        FROM statshub_team_players sp
        JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
        WHERE wt.team_name = 'Canada'
        ORDER BY CAST(sp.jersey_number AS INTEGER)
    """)
    for r in cur.fetchall():
        marker = "✓" if r[2] in ("confirmed","skipped_existing") else "?"
        print(f"  {marker} #{r[0]:>2}  {r[1]:<35}  [{r[2]}]  id={r[3]}")

    con.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
