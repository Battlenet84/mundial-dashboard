"""
Finish Paraguay player ID mapping for today's dataset.
Validates and confirms 3 weak mappings (Olveira, Mauricio, Velázquez) using
the endpoint-native team player performance data, then regenerates Excel.
"""
import sys, json, time, pathlib, sqlite3, requests
from datetime import datetime, timezone
import openpyxl

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH  = pathlib.Path("data/mundial.db")
RAW_BASE = pathlib.Path("data/raw/statshub/snapshots/today_playwright_fixture_players_probe")
SNAP_DIR = pathlib.Path("data/raw/statshub/snapshots/today_final_match_stats_probe")
BASE_URL = "https://www.statshub.com/api"
HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, */*",
    "Referer": "https://www.statshub.com/",
}

PARAGUAY_TEAM_ID  = "4789"
FIXTURE_ID        = "15186873"

# From endpoint: display name → (id, official_roster_name)
ENDPOINT_FIXES = [
    # (db_row_id, official_name, endpoint_player_id, jersey, endpoint_display)
    (7212, "Gastón Hernán OLVEIRA ECHEVERRIA", "339135", "22", "Gastón Olveira"),
    (7201, "Mauricio MAGALHAES PRADO",         "986233", "11", "Mauricio"),
    (7192, "Victor Gustavo VELAZQUEZ RAMOS",   "805427",  "2", "Gustavo Velázquez"),
]

NOW = datetime.now(timezone.utc).isoformat()


def _to_float(v):
    try: return float(v)
    except: return None


def fetch_endpoint_players():
    """Fetch Paraguay WC squad from endpoint (cached ok)."""
    cache = RAW_BASE / "followup_https_www_statshub_com_api_team_4789_players_performance_tou.json"
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
        players = data.get("data", [])
        print(f"  Loaded {len(players)} Paraguay players from cache")
        return {str(p["id"]): p for p in players}
    # Re-fetch if missing
    time.sleep(1.5)
    url = (f"{BASE_URL}/team/{PARAGUAY_TEAM_ID}/players/performance"
           f"?tournamentId=16&location=both&fixtureId={FIXTURE_ID}")
    r = requests.get(url, headers=HEADERS, timeout=20)
    if r.status_code == 200:
        payload = r.json()
        cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        players = payload.get("data", [])
        print(f"  Fetched {len(players)} Paraguay players from API")
        return {str(p["id"]): p for p in players}
    raise RuntimeError(f"Endpoint returned {r.status_code}")


def validate_profile(pid):
    """Fetch player profile to confirm identity."""
    cache_paths = [
        SNAP_DIR / f"profile_{pid}.json",
        RAW_BASE / f"profile_{pid}.json",
    ]
    for cp in cache_paths:
        if cp.exists():
            try: return json.loads(cp.read_text(encoding="utf-8")), "cache"
            except: pass
    time.sleep(1.5)
    r = requests.get(f"{BASE_URL}/player/{pid}", headers=HEADERS, timeout=20)
    if r.status_code == 200 and "json" in r.headers.get("content-type",""):
        payload = r.json()
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        (SNAP_DIR / f"profile_{pid}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload, "fetched"
    return None, f"http_{r.status_code}"


def fetch_performance(pid):
    """Download performance data; checks all snapshot dirs."""
    for snap in ["today_final_match_stats_probe",
                 "today_playwright_fixture_players_probe",
                 "today_browser_endpoint_replay_probe"]:
        d = pathlib.Path("data/raw/statshub/snapshots") / snap
        hits = list(d.glob(f"perf_{pid}*.json")) if d.exists() else []
        if hits:
            try: return json.loads(hits[0].read_text(encoding="utf-8")), "cache"
            except: pass
    time.sleep(1.5)
    r = requests.get(f"{BASE_URL}/player/{pid}/performance?limit=50",
                     headers=HEADERS, timeout=20)
    if r.status_code == 200 and "json" in r.headers.get("content-type",""):
        payload = r.json()
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        (SNAP_DIR / f"perf_{pid}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload, "fetched"
    return None, f"http_{r.status_code}"


def parse_and_upsert(cur, pid, name, team_name, payload):
    items = (payload.get("playerStatisticsEvents") or
             payload.get("events") or payload.get("data") or [])
    apps=minutes=goals=assists=sot=kp=tp=ap=tac=pl=yc=rc=0
    xg=xa=0.0; dates=[]
    for item in items:
        stats = item.get("player_statistics_event") or item
        mp = int(stats.get("minutesPlayed") or stats.get("minutes_played") or 0)
        if mp > 0: apps += 1; minutes += mp
        goals   += stats.get("goals") or 0
        assists += stats.get("goalAssist") or stats.get("assists") or 0
        sot     += stats.get("onTargetScoringAttempt") or 0
        kp  += stats.get("keyPass") or 0
        tp  += stats.get("totalPass") or 0
        ap  += stats.get("accuratePass") or 0
        tac += stats.get("totalTackle") or 0
        pl  += stats.get("possessionLostCtrl") or 0
        yc  += stats.get("yellowCard") or 0
        rc  += stats.get("redCard") or 0
        xg  += _to_float(stats.get("expectedGoals")) or 0.0
        xa  += _to_float(stats.get("expectedAssists")) or 0.0
        ts = (item.get("events") or {}).get("startTimestamp")
        if ts:
            try: dates.append(datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d"))
            except: pass
    dates.sort()
    cur.execute("""
        INSERT OR REPLACE INTO statshub_player_performance_aggregates
            (player_id, player_name, team_name, source_rows, appearances,
             minutes, goals, assists, shots_on_target,
             xG, xA, key_passes, passes, accurate_passes,
             tackles, possession_lost, yellow_cards, red_cards,
             date_min, date_max, imported_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (pid, name, team_name,
          len(items), apps, minutes, goals, assists, sot,
          round(xg,4) if xg else None, round(xa,4) if xa else None,
          kp, tp, ap, tac, pl, yc, rc,
          dates[0] if dates else None, dates[-1] if dates else None, NOW))
    return apps, minutes, goals, assists


def generate_excel(cur):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "coverage_summary"
    ws.append(["Team","Confirmed","Probable","Ambiguous","Unresolved","Total","Pct_confirmed","Decision"])

    teams = ["Canada","Bosnia and Herzegovina","United States","Paraguay"]
    for tname in teams:
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

    for tname in teams:
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
            ORDER BY CAST(sp.jersey_number AS INTEGER)
        """, (tname,))
        for p in cur.fetchall():
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

    out = pathlib.Path("data/processed/statshub/today_final_match_stats_review_corrected_paraguay.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out


def main():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # ── Step 1: Load endpoint player list ────────────────────────────────────
    print("=== Step 1: Load endpoint player list ===")
    endpoint_players = fetch_endpoint_players()

    # ── Step 2: Validate each fix against endpoint ────────────────────────────
    print("\n=== Step 2: Validate fixes against endpoint ===")
    confirmed_fixes = []
    for row_id, official_name, pid, jersey, display_name in ENDPOINT_FIXES:
        ep = endpoint_players.get(str(pid))
        if ep:
            ep_name = ep.get("name", "")
            print(f"  #{jersey} {official_name}")
            print(f"    Endpoint match: id={pid} → '{ep_name}' ✓")
            # Optional profile validation for name cross-check
            profile, src = validate_profile(pid)
            if profile:
                pdata = profile.get("player") or profile
                prof_name = pdata.get("name","") or pdata.get("shortName","")
                nationality = (pdata.get("country") or {}).get("name","")
                print(f"    Profile: '{prof_name}' ({nationality}) [{src}]")
            confirmed_fixes.append((row_id, official_name, pid, jersey))
        else:
            print(f"  #{jersey} {official_name}: pid={pid} NOT in endpoint — skipping")

    # ── Step 3: Apply DB updates ──────────────────────────────────────────────
    print("\n=== Step 3: Apply DB corrections ===")
    for row_id, official_name, pid, jersey in confirmed_fixes:
        # Check for duplicate before writing
        cur.execute("""
            SELECT sp.id, sp.player_name FROM statshub_team_players sp
            JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
            WHERE wt.team_name = 'Paraguay' AND sp.player_id = ? AND sp.id != ?
        """, (pid, row_id))
        dup = cur.fetchone()
        if dup:
            print(f"  #{jersey} SKIP — id={pid} already assigned to row {dup[0]} ({dup[1]})")
            continue
        cur.execute("""
            UPDATE statshub_team_players
            SET player_id = ?,
                statshub_player_id_status = 'confirmed',
                player_id_match_source = 'official_roster_plus_statshub_profile'
            WHERE id = ?
        """, (pid, row_id))
        print(f"  #{jersey} {official_name} → id={pid}  confirmed ✓")
    con.commit()

    # Verify no duplicates
    cur.execute("""
        SELECT player_id, COUNT(*) cnt FROM statshub_team_players sp
        JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
        WHERE wt.team_name = 'Paraguay' AND player_id IS NOT NULL
        GROUP BY player_id HAVING cnt > 1
    """)
    dups = cur.fetchall()
    print("  Duplicate player_ids:", [dict(r) for r in dups] if dups else "none ✓")

    # ── Step 4: Download performance for newly confirmed ──────────────────────
    print("\n=== Step 4: Download performance ===")
    for row_id, official_name, pid, jersey in confirmed_fixes:
        payload, src = fetch_performance(pid)
        if not payload:
            print(f"  #{jersey} {official_name}: FETCH FAILED ({src})")
            continue
        apps, minutes, goals, assists = parse_and_upsert(cur, pid, official_name, "Paraguay", payload)
        con.commit()
        print(f"  #{jersey} {official_name} (id={pid}): src={src} apps={apps} min={minutes} G={goals} A={assists}")

    # ── Step 5: Paraguay coverage ─────────────────────────────────────────────
    print("\n=== Step 5: Paraguay coverage ===")
    cur.execute("""
        SELECT statshub_player_id_status, COUNT(*) cnt
        FROM statshub_team_players sp
        JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
        WHERE wt.team_name = 'Paraguay'
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
        WHERE wt.team_name = 'Paraguay'
        ORDER BY CAST(sp.jersey_number AS INTEGER)
    """)
    for r in cur.fetchall():
        marker = "✓" if r[2] in ("confirmed","skipped_existing") else "?"
        print(f"  {marker} #{r[0]:>2}  {r[1]:<45}  [{r[2]}]  id={r[3]}")

    # ── Step 6: Regenerate Excel ──────────────────────────────────────────────
    print("\n=== Step 6: Regenerate Excel ===")
    out = generate_excel(cur)
    print(f"  Saved: {out}")

    # ── Final summary ─────────────────────────────────────────────────────────
    print("\n============================================================")
    print("FINAL REPORT — 2026-06-12  (corrected Paraguay)")
    print("============================================================")
    teams = ["Canada","Bosnia and Herzegovina","United States","Paraguay"]
    for tname in teams:
        cur.execute("""
            SELECT statshub_player_id_status, COUNT(*) cnt
            FROM statshub_team_players sp
            JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
            WHERE wt.team_name = ?
            GROUP BY statshub_player_id_status
        """, (tname,))
        s = {r[0]: r[1] for r in cur.fetchall()}
        total = sum(s.values())
        conf  = s.get("confirmed",0) + s.get("skipped_existing",0)
        prob  = s.get("probable",0)
        unres = s.get("unresolved",0)
        pct   = round(100*conf/total,1) if total else 0
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
        print(f"  {tname}: {conf}/{total} ({pct}%) confirmed | {prob} probable | {unres} unresolved | perf={perf_cnt} → {decision}")

    con.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
