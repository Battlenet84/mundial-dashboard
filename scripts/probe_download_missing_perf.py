"""
Download performance for confirmed players who are missing it, then regenerate Excel.
Only touches Canada, Bosnia, USA, Paraguay.
"""
import sys, json, time, pathlib, sqlite3, requests
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH  = pathlib.Path("data/mundial.db")
RAW_BASE = pathlib.Path("data/raw/statshub/snapshots/today_playwright_fixture_players_probe")
RAW_BASE.mkdir(parents=True, exist_ok=True)
BASE_URL = "https://www.statshub.com/api"
RATE_DELAY = 1.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, */*",
    "Referer": "https://www.statshub.com/",
}

def _now():
    return datetime.now(timezone.utc).isoformat()

def _to_float(v):
    if v is None: return None
    try: return float(v)
    except: return None

def fetch_perf(player_id):
    fpath = RAW_BASE / f"perf_{player_id}.json"
    if fpath.exists():
        try:
            return json.loads(fpath.read_text(encoding="utf-8")), "cache"
        except Exception:
            pass
    time.sleep(RATE_DELAY)
    try:
        r = requests.get(f"{BASE_URL}/player/{player_id}/performance?limit=50",
                         headers=HEADERS, timeout=20)
        if r.status_code == 200 and "json" in r.headers.get("content-type",""):
            payload = r.json()
            fpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload, "fetched"
        return None, f"http_{r.status_code}"
    except Exception as e:
        return None, f"error_{e}"

def parse_perf(payload, player_id, player_name, team_name):
    if not isinstance(payload, dict): return None
    items = (payload.get("playerStatisticsEvents") or payload.get("events")
             or payload.get("data") or [])
    if not items: return None
    apps=minutes=goals=assists=sot=kp=tp=ap=tac=pl=yc=rc=0
    xg=xa=0.0; dates=[]
    for item in items:
        stats = item.get("player_statistics_event") or item
        mp = stats.get("minutesPlayed") or stats.get("minutes_played") or 0
        try: mp = int(mp)
        except: mp = 0
        if mp > 0:
            apps += 1; minutes += mp
        goals   += stats.get("goals") or stats.get("goal") or 0
        assists += stats.get("goalAssist") or stats.get("assists") or 0
        sot     += stats.get("onTargetScoringAttempt") or stats.get("shots_on_target") or 0
        kp  += stats.get("keyPass") or 0
        tp  += stats.get("totalPass") or 0
        ap  += stats.get("accuratePass") or 0
        tac += stats.get("totalTackle") or 0
        pl  += stats.get("possessionLostCtrl") or 0
        yc  += stats.get("yellowCard") or 0
        rc  += stats.get("redCard") or 0
        xg  += _to_float(stats.get("expectedGoals")) or 0.0
        xa  += _to_float(stats.get("expectedAssists")) or 0.0
        ev = item.get("events") or {}
        ts = ev.get("startTimestamp")
        if ts:
            try:
                dates.append(datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d"))
            except: pass
    dates.sort()
    return dict(
        player_id=player_id, player_name=player_name, team_name=team_name,
        source_rows=len(items), appearances=apps, minutes=minutes,
        goals=goals, assists=assists, shots_on_target=sot,
        xG=round(xg,4) if xg else None, xA=round(xa,4) if xa else None,
        key_passes=kp, passes=tp, accurate_passes=ap,
        tackles=tac, possession_lost=pl, yellow_cards=yc, red_cards=rc,
        date_min=dates[0] if dates else None, date_max=dates[-1] if dates else None,
    )

def main():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    TARGET_TEAMS = ('Canada','Bosnia and Herzegovina','United States','Paraguay')
    CONFIRMED_STATUSES = ('confirmed', 'skipped_existing')

    # Find all confirmed players without performance
    cur.execute(f"""
        SELECT sp.player_id, sp.player_name, wt.team_name
        FROM statshub_team_players sp
        JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
        WHERE wt.team_name IN {TARGET_TEAMS!r}
          AND sp.statshub_player_id_status IN {CONFIRMED_STATUSES!r}
          AND sp.player_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM statshub_player_performance_aggregates a
              WHERE a.player_id = sp.player_id
          )
    """)
    to_download = [dict(r) for r in cur.fetchall()]
    print(f"Confirmed players missing performance: {len(to_download)}")

    downloaded = 0
    for p in to_download:
        pid    = p["player_id"]
        pname  = p["player_name"]
        tname  = p["team_name"]
        payload, src = fetch_perf(pid)
        if not payload:
            print(f"  SKIP {pname}: {src}")
            continue
        agg = parse_perf(payload, pid, pname, tname)
        if not agg:
            print(f"  NO_DATA {pname}: rows=0")
            continue
        cur.execute("""
            INSERT OR REPLACE INTO statshub_player_performance_aggregates
                (player_id, player_name, team_name, source_rows, appearances,
                 minutes, goals, assists, shots_on_target,
                 xG, xA, key_passes, passes, accurate_passes,
                 tackles, possession_lost, yellow_cards, red_cards,
                 date_min, date_max, imported_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            pid, pname, tname,
            agg["source_rows"], agg["appearances"], agg["minutes"],
            agg["goals"], agg["assists"], agg["shots_on_target"],
            agg["xG"], agg["xA"], agg["key_passes"], agg["passes"],
            agg["accurate_passes"], agg["tackles"], agg["possession_lost"],
            agg["yellow_cards"], agg["red_cards"],
            agg["date_min"], agg["date_max"], _now()
        ))
        con.commit()
        print(f"  OK {pname} ({tname}): src={src} rows={agg['source_rows']} apps={agg['appearances']} min={agg['minutes']}")
        downloaded += 1

    print(f"\nDownloaded: {downloaded}/{len(to_download)}")

    # ── Regenerate Excel ────────────────────────────────────────────────────────
    print("\nRegenerating Excel...")
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "coverage_summary"
    ws.append(["Team","Confirmed","Probable","Ambiguous","Unresolved","Total","Pct_confirmed","Decision"])

    teams_order = ["Canada","Bosnia and Herzegovina","United States","Paraguay"]
    for tname in teams_order:
        cur.execute("""
            SELECT statshub_player_id_status, COUNT(*) cnt
            FROM statshub_team_players sp
            JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
            WHERE wt.team_name = ?
            GROUP BY statshub_player_id_status
        """, (tname,))
        s = {r[0]: r[1] for r in cur.fetchall()}
        total     = sum(s.values())
        confirmed = s.get("confirmed",0) + s.get("skipped_existing",0)
        probable  = s.get("probable",0)
        ambiguous = s.get("ambiguous",0)
        unresolved= s.get("unresolved",0)
        pct = round(100*confirmed/total,1) if total else 0
        decision  = "READY" if pct >= 80 else "INCOMPLETE"
        ws.append([tname, confirmed, probable, ambiguous, unresolved, total, pct, decision])

    for tname in teams_order:
        safe = tname[:20].replace(" ","_")
        ws2 = wb.create_sheet(safe)
        ws2.append(["player_name","jersey","position","id_status","player_id",
                    "appearances","minutes","goals","assists","shots_on_target","xG","xA",
                    "key_passes","passes","tackles","possession_lost","yellow_cards","red_cards",
                    "date_min","date_max"])
        cur.execute("""
            SELECT sp.player_name, sp.jersey_number, sp.position,
                   sp.statshub_player_id_status, sp.player_id
            FROM statshub_team_players sp
            JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
            WHERE wt.team_name = ?
            ORDER BY sp.position, sp.player_name
        """, (tname,))
        players = cur.fetchall()
        for p in players:
            pid = p[4]
            agg = None
            if pid:
                cur.execute("""
                    SELECT appearances, minutes, goals, assists, shots_on_target,
                           xG, xA, key_passes, passes, tackles, possession_lost,
                           yellow_cards, red_cards, date_min, date_max
                    FROM statshub_player_performance_aggregates
                    WHERE player_id = ?
                """, (str(pid),))
                agg = cur.fetchone()
            ws2.append([
                p[0], p[1], p[2], p[3], pid,
                *(agg[i] if agg else None for i in range(15)),
            ])

    out = pathlib.Path("data/processed/statshub/today_playwright_final_review.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"  OK Saved: {out}")

    # ── Final report ────────────────────────────────────────────────────────────
    print("\n============================================================")
    print("FINAL REPORT — 2026-06-12")
    print("============================================================")
    for tname in teams_order:
        cur.execute("""
            SELECT statshub_player_id_status, COUNT(*) cnt
            FROM statshub_team_players sp
            JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
            WHERE wt.team_name = ?
            GROUP BY statshub_player_id_status
        """, (tname,))
        s = {r[0]: r[1] for r in cur.fetchall()}
        total     = sum(s.values())
        confirmed = s.get("confirmed",0) + s.get("skipped_existing",0)
        probable  = s.get("probable",0)
        unresolved= s.get("unresolved",0)
        pct       = round(100*confirmed/total,1) if total else 0

        cur.execute("""
            SELECT COUNT(*) FROM statshub_player_performance_aggregates a
            WHERE EXISTS (
                SELECT 1 FROM statshub_team_players sp
                JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
                WHERE wt.team_name = ? AND sp.player_id = a.player_id
                AND sp.statshub_player_id_status IN ('confirmed','skipped_existing')
            )
        """, (tname,))
        perf_cnt = cur.fetchone()[0]

        decision = "READY" if pct >= 80 else "INCOMPLETE"
        print(f"  {tname}: {confirmed}/{total} ({pct}%) confirmed | {probable} probable | perf={perf_cnt} → {decision}")

    con.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
