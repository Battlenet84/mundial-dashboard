"""
Use Playwright to render StatsHub fixture pages and intercept XHR/fetch requests.
Captures all network responses containing player data for the 4 target teams.

Fixtures:
  Canada vs Bosnia and Herzegovina  https://www.statshub.com/es/fixture/canada-vs-bosnia-and-herzegovina-mqazwx/157343
  USA vs Paraguay                   https://www.statshub.com/es/fixture/usa-vs-paraguay-mqazwt/157344

Strategy:
  1. Launch headless Chromium via Playwright
  2. Intercept all XHR/fetch responses
  3. Parse any JSON response containing player-like objects (id + name + position)
  4. Cross-match extracted players to DB rosters
  5. Update statshub_team_players for newly confirmed players
  6. Download performance for newly confirmed
  7. Regenerate Excel
"""
import sys, json, time, re, pathlib, sqlite3, requests, io
from collections import defaultdict
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─── Config ────────────────────────────────────────────────────────────────────
DB_PATH  = pathlib.Path("data/mundial.db")
RAW_BASE = pathlib.Path("data/raw/statshub/snapshots")
SNAPSHOT = "today_playwright_fixture_players_probe"
BASE_URL = "https://www.statshub.com/api"

FIXTURES = [
    {
        "match":    "Canada vs Bosnia and Herzegovina",
        "url":      "https://www.statshub.com/es/fixture/canada-vs-bosnia-and-herzegovina-mqazwx/157343",
        "home":     {"team_name": "Canada",              "team_id_db": "Canada"},
        "away":     {"team_name": "Bosnia & Herzegovina","team_id_db": "Bosnia and Herzegovina"},
    },
    {
        "match":    "USA vs Paraguay",
        "url":      "https://www.statshub.com/es/fixture/usa-vs-paraguay-mqazwt/157344",
        "home":     {"team_name": "USA",                 "team_id_db": "United States"},
        "away":     {"team_name": "Paraguay",            "team_id_db": "Paraguay"},
    },
]

RATE_DELAY = 1.5

# StatsHub API headers for follow-up fetches
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.statshub.com/",
}

# ─── DB helpers ────────────────────────────────────────────────────────────────
def get_con():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def _now():
    return datetime.now(timezone.utc).isoformat()

# ─── Player extraction ─────────────────────────────────────────────────────────
_PLAYER_KEYS = {"position", "jerseyNumber", "nationality", "dateOfBirth",
                "height", "contractUntil", "birthdate", "age", "shortName"}

def extract_players(obj, depth=0, max_depth=12):
    """Recursively find player dicts {id, name, position...} in JSON."""
    if depth > max_depth:
        return []
    results = []
    if isinstance(obj, list):
        for item in obj:
            results.extend(extract_players(item, depth + 1, max_depth))
    elif isinstance(obj, dict):
        pid   = obj.get("id") or obj.get("playerId")
        pname = obj.get("name") or obj.get("playerName") or obj.get("shortName")
        if (pid and pname and isinstance(pid, int) and isinstance(pname, str)
                and any(k in obj for k in _PLAYER_KEYS)):
            results.append({
                "player_id":    str(pid),
                "player_name":  pname,
                "jersey":       obj.get("jerseyNumber"),
                "position":     obj.get("position"),
            })
        for v in obj.values():
            if isinstance(v, (dict, list)):
                results.extend(extract_players(v, depth + 1, max_depth))
    return results

def _dedup(players):
    seen = {}
    for p in players:
        if p["player_id"] not in seen:
            seen[p["player_id"]] = p
    return list(seen.values())

# ─── Playwright intercept ──────────────────────────────────────────────────────
def scrape_fixture(fixture, snap_dir):
    """Load fixture URL with Playwright, intercept all JSON responses."""
    from playwright.sync_api import sync_playwright

    captured = []   # list of {url, payload}
    api_calls = []  # all api URLs seen

    def on_response(response):
        url = response.url
        ct  = response.headers.get("content-type", "")
        if "json" not in ct:
            return
        # Only capture statshub API responses
        if "statshub.com/api" not in url and "statshub.com/_next" not in url:
            return
        api_calls.append(url)
        try:
            payload = response.json()
            captured.append({"url": url, "payload": payload})
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        page = ctx.new_page()
        page.on("response", on_response)

        print(f"  Loading: {fixture['url']}")
        try:
            page.goto(fixture["url"], wait_until="networkidle", timeout=45000)
        except Exception as e:
            print(f"  Warning: goto timeout/error: {e}")

        # Extra wait to catch lazy-loaded XHR
        page.wait_for_timeout(5000)

        # Try scrolling to trigger any lazy loads
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(2000)

        browser.close()

    print(f"  API calls intercepted: {len(api_calls)}")
    for u in api_calls:
        print(f"    {u}")

    # Save all captured responses
    for i, item in enumerate(captured):
        fname = snap_dir / f"{fixture['match'].replace(' ', '_').replace('&','and')}_{i:03d}.json"
        try:
            fname.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    return captured, api_calls

# ─── Follow-up on discovered endpoints ────────────────────────────────────────
def follow_up_fetch(url, snap_dir, label):
    """Fetch a discovered API endpoint and cache it."""
    fpath = snap_dir / f"followup_{re.sub(r'[^a-zA-Z0-9]', '_', label)[:60]}.json"
    existing = list(snap_dir.glob(f"followup_{re.sub(r'[^a-zA-Z0-9]', '_', label)[:60]}*.json"))
    if existing:
        try:
            return json.loads(existing[0].read_text(encoding="utf-8"))
        except Exception:
            pass

    time.sleep(RATE_DELAY)
    try:
        r = requests.get(url, headers=API_HEADERS, timeout=20)
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            payload = r.json()
            fpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload
    except Exception as e:
        print(f"  follow-up error {url}: {e}")
    return None

# ─── Performance download ──────────────────────────────────────────────────────
def download_performance(player_id, player_name, snap_dir):
    """Download player performance from StatsHub."""
    url = f"{BASE_URL}/player/{player_id}/performance?limit=50"
    fpath = snap_dir / f"perf_{player_id}.json"
    if fpath.exists():
        try:
            return json.loads(fpath.read_text(encoding="utf-8")), "cache"
        except Exception:
            pass
    time.sleep(RATE_DELAY)
    try:
        r = requests.get(url, headers=API_HEADERS, timeout=20)
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            payload = r.json()
            fpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload, "fetched"
    except Exception as e:
        print(f"  perf error {player_id}: {e}")
    return None, "error"

def _to_xfloat(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def parse_performance(payload, player_id, player_name, team_name):
    """Parse StatsHub performance payload into aggregate stats."""
    if not isinstance(payload, dict):
        return None
    items = payload.get("playerStatisticsEvents") or payload.get("events") or []
    if not items:
        return None
    apps = minutes = goals = assists = sot = xg = xa = 0
    key_passes = passes = acc_passes = tackles = poss_lost = yellows = reds = 0
    dates = []
    for item in items:
        stats = item.get("player_statistics_event") or item
        mp = stats.get("minutesPlayed") or stats.get("minutes_played") or 0
        try:
            mp = int(mp)
        except Exception:
            mp = 0
        if mp > 0:
            apps    += 1
            minutes += mp
        goals     += stats.get("goals")       or stats.get("goal") or 0
        assists   += stats.get("goalAssist")  or stats.get("assists") or 0
        sot       += stats.get("onTargetScoringAttempt") or stats.get("shots_on_target") or 0
        key_passes += stats.get("keyPass") or 0
        passes     += stats.get("totalPass") or 0
        acc_passes += stats.get("accuratePass") or 0
        tackles    += stats.get("totalTackle") or 0
        poss_lost  += stats.get("possessionLostCtrl") or 0
        yellows    += stats.get("yellowCard") or 0
        reds       += stats.get("redCard") or 0
        xg += _to_xfloat(stats.get("expectedGoals")) or 0.0
        xa += _to_xfloat(stats.get("expectedAssists")) or 0.0
        ev = item.get("events") or {}
        ts = ev.get("startTimestamp")
        if ts:
            try:
                from datetime import datetime, timezone
                dates.append(datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d"))
            except Exception:
                pass
    dates.sort()
    return {
        "player_id": player_id, "player_name": player_name, "team_name": team_name,
        "source_rows": len(items), "appearances": apps, "minutes": minutes,
        "goals": goals, "assists": assists, "shots_on_target": sot,
        "xg": round(xg, 4) if xg else None, "xa": round(xa, 4) if xa else None,
        "key_passes": key_passes, "total_passes": passes, "accurate_passes": acc_passes,
        "tackles": tackles, "possession_lost": poss_lost,
        "yellow_cards": yellows, "red_cards": reds,
        "date_min": dates[0] if dates else None, "date_max": dates[-1] if dates else None,
    }

# ─── Excel generation ──────────────────────────────────────────────────────────
def generate_excel(con, out_path):
    import openpyxl
    wb = openpyxl.Workbook()

    teams = ["Canada", "Bosnia and Herzegovina", "United States", "Paraguay"]
    cur = con.cursor()

    ws = wb.active
    ws.title = "coverage_summary"
    ws.append(["Team", "Confirmed", "Probable", "Ambiguous", "Unresolved", "Total", "Pct", "Decision"])
    for tname in teams:
        cur.execute("""
            SELECT statshub_player_id_status as id_status, COUNT(*) cnt
            FROM statshub_team_players sp
            JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
            WHERE wt.team_name = ?
            GROUP BY statshub_player_id_status
        """, (tname,))
        stats = {r[0]: r[1] for r in cur.fetchall()}
        total     = sum(stats.values())
        confirmed = stats.get("confirmed", 0)
        probable  = stats.get("probable", 0)
        ambiguous = stats.get("ambiguous", 0)
        unresolved= stats.get("unresolved", 0)
        pct = round(100 * confirmed / total, 1) if total else 0
        decision = "READY" if pct >= 80 else "INCOMPLETE"
        ws.append([tname, confirmed, probable, ambiguous, unresolved, total, pct, decision])

    # Per-team detail sheets
    for tname in teams:
        short = tname[:20].replace(" ", "_")
        ws2 = wb.create_sheet(short)
        ws2.append(["player_name","jersey","position","id_status","statshub_player_id",
                    "appearances","minutes","goals","assists","shots_on_target","xg","xa"])
        cur.execute("""
            SELECT sp.player_name, sp.jersey_number, sp.position,
                   sp.statshub_player_id_status as id_status,
                   sp.player_id as pid
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
                    SELECT appearances, minutes, goals, assists,
                           shots_on_target, xG, xA
                    FROM statshub_player_performance_aggregates
                    WHERE player_id = ?
                """, (str(pid),))
                agg = cur.fetchone()
            ws2.append([
                p[0], p[1], p[2], p[3], pid,
                agg[0] if agg else None,
                agg[1] if agg else None,
                agg[2] if agg else None,
                agg[3] if agg else None,
                agg[4] if agg else None,
                agg[5] if agg else None,
                agg[6] if agg else None,
            ])

    wb.save(out_path)
    print(f"  OK Saved: {out_path}")

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    snap_dir = RAW_BASE / SNAPSHOT
    snap_dir.mkdir(parents=True, exist_ok=True)

    con = get_con()
    cur = con.cursor()

    # Load roster
    cur.execute("""
        SELECT sp.id as row_id, sp.player_name, sp.jersey_number, sp.position,
               sp.statshub_player_id_status as id_status,
               COALESCE(sp.player_id, '') as statshub_player_id,
               wt.team_name
        FROM statshub_team_players sp
        JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
        WHERE wt.team_name IN ('Canada','Bosnia and Herzegovina','United States','Paraguay')
        ORDER BY wt.team_name, sp.player_name
    """)
    roster_rows = [dict(r) for r in cur.fetchall()]
    roster_by_team = defaultdict(list)
    for r in roster_rows:
        roster_by_team[r["team_name"]].append(r)

    # player_id → roster row lookup
    pid_to_roster = {}
    for r in roster_rows:
        if r["statshub_player_id"]:
            pid_to_roster[str(r["statshub_player_id"])] = r

    print("=== TASK 1: Playwright fixture page scrape ===")
    all_extracted = {}   # player_id -> {player_name, team_hint, source_url}
    discovered_api_urls = set()

    for fixture in FIXTURES:
        print(f"\n  [{fixture['match']}]")
        captured, api_calls = scrape_fixture(fixture, snap_dir)
        discovered_api_urls.update(api_calls)

        fixture_players = []
        for item in captured:
            players = extract_players(item["payload"])
            for p in players:
                p["source_url"] = item["url"]
                fixture_players.append(p)

        fixture_players = _dedup(fixture_players)
        print(f"  Players extracted: {len(fixture_players)}")
        for p in fixture_players[:10]:
            print(f"    id={p['player_id']} name={p['player_name']} pos={p.get('position')} src={p['source_url'][:80]}")

        for p in fixture_players:
            all_extracted[p["player_id"]] = {
                "player_name": p["player_name"],
                "jersey": p.get("jersey"),
                "position": p.get("position"),
                "source_url": p.get("source_url"),
                "team_name": None,   # will try to match
            }

    print(f"\n  Total unique extracted players: {len(all_extracted)}")

    # ─── Discover new API patterns from intercepted calls ─────────────────────
    print("\n=== TASK 2: Analyze intercepted API calls ===")
    player_api_urls = []
    for url in sorted(discovered_api_urls):
        # Look for player/squad/lineup URLs
        if any(k in url for k in ["/player/", "/lineup", "/squad", "/players", "/statistics"]):
            player_api_urls.append(url)
            print(f"  PLAYER API: {url}")

    # Follow up on any squad/player-list URLs not yet cached
    for url in player_api_urls:
        label = re.sub(r"[^a-zA-Z0-9]+", "_", url)[:60]
        payload = follow_up_fetch(url, snap_dir, label)
        if payload:
            new_players = extract_players(payload)
            for p in new_players:
                if p["player_id"] not in all_extracted:
                    all_extracted[p["player_id"]] = {
                        "player_name": p["player_name"],
                        "jersey": p.get("jersey"),
                        "position": p.get("position"),
                        "source_url": url,
                        "team_name": None,
                    }
            if new_players:
                print(f"  Follow-up {url[:60]}: +{len(new_players)} players")

    print(f"  Total after follow-ups: {len(all_extracted)}")

    # ─── Cross-match to rosters ────────────────────────────────────────────────
    print("\n=== TASK 3: Cross-match to DB rosters ===")
    newly_confirmed = []

    for pid, pdata in all_extracted.items():
        # Check if this player_id already in roster
        if pid in pid_to_roster:
            rp = pid_to_roster[pid]
            if rp["id_status"] not in ("confirmed", "skipped_existing"):
                print(f"  [confirm by ID] {rp['player_name']} ({rp['team_name']}): id={pid}")
                cur.execute("""
                    UPDATE statshub_team_players
                    SET player_id=?, statshub_player_id_status='confirmed',
                        player_id_match_source='playwright_fixture'
                    WHERE id=?
                """, (pid, rp["row_id"]))
                newly_confirmed.append({
                    "player_name": rp["player_name"], "player_id": pid,
                    "team_name": rp["team_name"]
                })
            continue

        # Try name-match within rosters
        pname_lower = pdata["player_name"].lower().strip()
        matched = False
        for team_name, roster in roster_by_team.items():
            for rp in roster:
                rname_lower = rp["player_name"].lower().strip()
                # Exact match or last-name match
                if pname_lower == rname_lower:
                    print(f"  [confirm by name-exact] {rp['player_name']} ({team_name}): id={pid}")
                    cur.execute("""
                        UPDATE statshub_team_players
                        SET player_id=?, statshub_player_id_status='confirmed',
                            player_id_match_source='playwright_fixture_name'
                        WHERE id=?
                    """, (pid, rp["row_id"]))
                    newly_confirmed.append({
                        "player_name": rp["player_name"], "player_id": pid,
                        "team_name": team_name
                    })
                    pid_to_roster[pid] = rp
                    matched = True
                    break
            if matched:
                break

    con.commit()
    print(f"  Newly confirmed: {len(newly_confirmed)}")

    # ─── Download performance for newly confirmed ─────────────────────────────
    print("\n=== TASK 4: Download performance for newly confirmed players ===")
    for p in newly_confirmed:
        pid = p["player_id"]
        # Check if already downloaded
        cur.execute("SELECT id FROM statshub_player_performance_aggregates WHERE player_id=?", (pid,))
        if cur.fetchone():
            print(f"  Already have perf: {p['player_name']}")
            continue
        payload, src = download_performance(pid, p["player_name"], snap_dir)
        if payload:
            agg = parse_performance(payload, pid, p["player_name"], p["team_name"])
            if agg:
                cur.execute("""
                    INSERT OR REPLACE INTO statshub_player_performance_aggregates
                        (player_id, player_name, team_name, source_rows, appearances,
                         minutes, goals, assists, shots_on_target,
                         xG, xA, key_passes, passes, accurate_passes,
                         tackles, possession_lost, yellow_cards, red_cards,
                         date_min, date_max, imported_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    pid, p["player_name"], p["team_name"],
                    agg["source_rows"], agg["appearances"], agg["minutes"],
                    agg["goals"], agg["assists"], agg["shots_on_target"],
                    agg["xg"], agg["xa"], agg["key_passes"], agg["total_passes"],
                    agg["accurate_passes"], agg["tackles"], agg["possession_lost"],
                    agg["yellow_cards"], agg["red_cards"],
                    agg["date_min"], agg["date_max"], _now()
                ))
                con.commit()
                print(f"  {p['player_name']}: apps={agg['appearances']} min={agg['minutes']}")

    # ─── Coverage summary ─────────────────────────────────────────────────────
    print("\n=== TASK 5: Coverage summary ===")
    for tname_db in ["Canada", "Bosnia and Herzegovina", "United States", "Paraguay"]:
        cur.execute("""
            SELECT statshub_player_id_status as id_status, COUNT(*) cnt
            FROM statshub_team_players sp
            JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
            WHERE wt.team_name = ?
            GROUP BY statshub_player_id_status
        """, (tname_db,))
        stats = {r[0]: r[1] for r in cur.fetchall()}
        total     = sum(stats.values())
        confirmed = stats.get("confirmed", 0)
        probable  = stats.get("probable", 0)
        print(f"  {tname_db}: {confirmed}/{total} confirmed | {probable} probable")

    # ─── Excel ────────────────────────────────────────────────────────────────
    print("\n=== TASK 6: Regenerate Excel ===")
    out_dir = pathlib.Path("data/processed/statshub")
    out_dir.mkdir(parents=True, exist_ok=True)
    generate_excel(con, out_dir / "today_playwright_fixture_review.xlsx")

    # ─── Final report ─────────────────────────────────────────────────────────
    print("\n============================================================")
    print("FINAL REPORT")
    print("============================================================")
    print(f"Playwright intercepted API calls: {len(discovered_api_urls)}")
    print(f"Total unique players extracted: {len(all_extracted)}")
    print(f"Newly confirmed: {len(newly_confirmed)}")
    if newly_confirmed:
        for p in newly_confirmed:
            print(f"  + {p['player_name']} ({p['team_name']}): id={p['player_id']}")

    print("\nCoverage:")
    for tname_db in ["Canada", "Bosnia and Herzegovina", "United States", "Paraguay"]:
        cur.execute("""
            SELECT statshub_player_id_status as id_status, COUNT(*) cnt
            FROM statshub_team_players sp
            JOIN statshub_world_cup_teams wt ON sp.team_id = wt.statshub_team_id
            WHERE wt.team_name = ?
            GROUP BY statshub_player_id_status
        """, (tname_db,))
        stats = {r[0]: r[1] for r in cur.fetchall()}
        total     = sum(stats.values())
        confirmed = stats.get("confirmed", 0)
        pct = round(100 * confirmed / total, 1) if total else 0
        decision = "READY" if pct >= 80 else "INCOMPLETE"
        print(f"  {tname_db}: {confirmed}/{total} ({pct}%) → {decision}")

    print()
    if len(all_extracted) > 0:
        print("→ Playwright extracted player data — see above for coverage improvement")
    else:
        print("→ NO player data extracted via Playwright")
        print("  Possible causes:")
        print("  - Player data loaded via separate authenticated API calls")
        print("  - Geo-blocking or bot detection")
        print("  - Need to interact with page elements (click on lineups tab etc.)")
        print()
        print("  Recommended next step: Manual approach or alternative data source")

    con.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
