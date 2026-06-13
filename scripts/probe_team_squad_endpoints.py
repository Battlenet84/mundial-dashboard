"""
Probe additional StatsHub endpoints for team squad/player data.

Tests these patterns (NOT tried in previous probe):
  1. /api/event/{internalId}/players         (use internalId=157344 not large event_id)
  2. /api/team/{teamId}/players
  3. /api/team/{teamId}/squad
  4. /api/unique-tournament/16/season/58210/squad/{teamId}
  5. /api/unique-tournament/16/season/58210/top-players/{teamId}
  6. /api/tournament/{tournamentId}/season/58210/squads
  7. /api/team/{teamId}/season/58210/players
  8. /api/team/{teamId}/season/58210/squad
  9. /api/team/{teamId}/statistics/season/58210

DO NOT use Playwright. DO NOT hit any endpoint not in the list above.
"""
import sys, json, time, pathlib, sqlite3, re, requests
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─── Config ────────────────────────────────────────────────────────────────────
DB_PATH    = pathlib.Path("data/mundial.db")
RAW_BASE   = pathlib.Path("data/raw/statshub/snapshots")
SNAPSHOT   = "today_squad_endpoint_probe"
BASE_URL   = "https://www.statshub.com/api"
RATE_DELAY = 1.5   # seconds between requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.statshub.com/",
    "Origin": "https://www.statshub.com",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# ─── Teams ─────────────────────────────────────────────────────────────────────
TEAMS = [
    {"name": "Canada",              "team_id": 4752, "internal_id": 1293},
    {"name": "Bosnia & Herzegovina","team_id": 4479, "internal_id": 1214},
    {"name": "USA",                 "team_id": 4724, "internal_id": 1266},
    {"name": "Paraguay",            "team_id": 4789, "internal_id": 1330},
]

SEASON_ID           = 58210
UNIQUE_TOURNAMENT   = 16
TOURNAMENT_GRP_B    = 3955   # Canada/Bosnia group
TOURNAMENT_GRP_D    = 3957   # USA/Paraguay group

EVENTS = [
    {"match": "Canada vs Bosnia",   "event_id": 15186836, "internal_id": 157343,
     "home_team_id": 4752, "away_team_id": 4479},
    {"match": "USA vs Paraguay",    "event_id": 15186873, "internal_id": 157344,
     "home_team_id": 4724, "away_team_id": 4789},
]

# ─── DB helpers ────────────────────────────────────────────────────────────────
def get_con():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def _ensure_snapshot_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS statshub_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_name TEXT, endpoint_name TEXT, url TEXT, method TEXT,
            status_code INTEGER, content_type TEXT, response_size INTEGER,
            looks_json INTEGER, json_top_keys TEXT, rows_detected INTEGER,
            raw_file_path TEXT, status TEXT, message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

def _save_snapshot(cur, endpoint_name, url, status_code, content_type,
                   raw_file_path, status, message, json_top_keys="", rows=0):
    cur.execute("""
        INSERT INTO statshub_snapshots
            (snapshot_name, endpoint_name, url, method, status_code, content_type,
             response_size, looks_json, json_top_keys, rows_detected, raw_file_path,
             status, message, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        SNAPSHOT, endpoint_name, url, "GET", status_code, content_type,
        0, 1 if json_top_keys else 0, json_top_keys, rows,
        str(raw_file_path), status, message,
        datetime.now(timezone.utc).isoformat()
    ))

# ─── HTTP ──────────────────────────────────────────────────────────────────────
def _ts():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def fetch(endpoint_name, url, snap_dir):
    """Fetch URL, cache result, return (status_code, payload_dict_or_None, content_type)."""
    # cache check
    existing = list(snap_dir.glob(f"{endpoint_name}_*.json"))
    if existing:
        try:
            data = json.loads(existing[0].read_text(encoding="utf-8"))
            print(f"    [cache] {endpoint_name}")
            return 200, data, "application/json"
        except Exception:
            pass

    time.sleep(RATE_DELAY)
    try:
        r = SESSION.get(url, timeout=20)
    except Exception as e:
        print(f"    [error] {endpoint_name}: {e}")
        return -1, None, ""

    ct = r.headers.get("content-type", "")
    fpath = snap_dir / f"{endpoint_name}_{_ts()}.json"

    if r.status_code == 200 and "json" in ct:
        try:
            payload = r.json()
            fpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return 200, payload, ct
        except Exception:
            pass

    # non-JSON or non-200
    try:
        fpath.write_text(r.text[:5000], encoding="utf-8")
    except Exception:
        pass
    return r.status_code, None, ct

# ─── Player extraction ─────────────────────────────────────────────────────────
def extract_players(payload):
    """Walk JSON recursively for player objects with id + name. Returns list of dicts."""
    results = []
    if not isinstance(payload, (dict, list)):
        return results

    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            pid = obj.get("id") or obj.get("playerId")
            pname = obj.get("name") or obj.get("playerName") or obj.get("shortName")
            # Heuristic: if this dict looks like a player node
            if pid and pname and isinstance(pid, int) and isinstance(pname, str):
                # Avoid team/event objects by checking for player-typical keys
                if any(k in obj for k in ["position", "jerseyNumber", "nationality",
                                           "dateOfBirth", "height", "contractUntil",
                                           "birthdate", "age"]):
                    results.append({"player_id": str(pid), "player_name": pname,
                                    "jersey": obj.get("jerseyNumber"),
                                    "position": obj.get("position"),
                                    "raw": obj})
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    walk(v)

    walk(payload)
    return results

# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    snap_dir = RAW_BASE / SNAPSHOT
    snap_dir.mkdir(parents=True, exist_ok=True)

    con = get_con()
    cur = con.cursor()
    _ensure_snapshot_table(cur)
    con.commit()

    all_players = {}   # player_id -> {player_name, team_name, source}
    results = []       # list of endpoint result dicts

    print("\n=== TASK 1: Test event internalId endpoints ===")
    for ev in EVENTS:
        iid = ev["internal_id"]
        for suffix in ["players", "lineups", "statistics"]:
            ename = f"event_internal_{iid}_{suffix}"
            url   = f"{BASE_URL}/event/{iid}/{suffix}"
            sc, payload, ct = fetch(ename, url, snap_dir)
            players = extract_players(payload) if payload else []
            top_keys = ",".join(list(payload.keys())[:8]) if isinstance(payload, dict) else ""
            print(f"  {ev['match']} /event/{iid}/{suffix}: HTTP={sc} players={len(players)} keys={top_keys[:60]}")
            results.append({"endpoint": ename, "url": url, "sc": sc, "players": len(players), "top_keys": top_keys})
            for p in players:
                all_players[p["player_id"]] = {**p, "team_name": None, "source": ename}
            _save_snapshot(cur, ename, url, sc, ct, snap_dir / f"{ename}.json",
                           "ok" if sc == 200 else "error", str(sc), top_keys, len(players))
        con.commit()

    print("\n=== TASK 2: Test team squad endpoints ===")
    team_endpoint_patterns = [
        ("players",               lambda tid, iid: f"{BASE_URL}/team/{tid}/players"),
        ("squad",                 lambda tid, iid: f"{BASE_URL}/team/{tid}/squad"),
        ("season_players",        lambda tid, iid: f"{BASE_URL}/team/{tid}/season/{SEASON_ID}/players"),
        ("season_squad",          lambda tid, iid: f"{BASE_URL}/team/{tid}/season/{SEASON_ID}/squad"),
        ("unique_tournament_squad", lambda tid, iid: f"{BASE_URL}/unique-tournament/{UNIQUE_TOURNAMENT}/season/{SEASON_ID}/squad/{tid}"),
        ("unique_tournament_top",   lambda tid, iid: f"{BASE_URL}/unique-tournament/{UNIQUE_TOURNAMENT}/season/{SEASON_ID}/top-players/{tid}"),
        ("wc_squad_by_internal",  lambda tid, iid: f"{BASE_URL}/team/{iid}/season/{SEASON_ID}/squad"),
    ]

    for team in TEAMS:
        tid  = team["team_id"]
        iid  = team["internal_id"]
        tname = team["name"]
        print(f"\n  --- {tname} (team_id={tid} internal={iid}) ---")
        for suffix, url_fn in team_endpoint_patterns:
            ename = f"team_{tid}_{suffix}"
            url   = url_fn(tid, iid)
            sc, payload, ct = fetch(ename, url, snap_dir)
            players = extract_players(payload) if payload else []
            top_keys = ",".join(list(payload.keys())[:8]) if isinstance(payload, dict) else ""
            print(f"    {suffix}: HTTP={sc} players={len(players)} keys={top_keys[:60]}")
            results.append({"endpoint": ename, "url": url, "sc": sc, "players": len(players), "top_keys": top_keys})
            for p in players:
                if p["player_id"] not in all_players:
                    all_players[p["player_id"]] = {**p, "team_name": tname, "source": ename}
            _save_snapshot(cur, ename, url, sc, ct, snap_dir / f"{ename}.json",
                           "ok" if sc == 200 else "error", str(sc), top_keys, len(players))
        con.commit()

    print("\n=== TASK 3: Test tournament squad endpoints ===")
    tournament_patterns = [
        ("grp_b_squads", f"{BASE_URL}/tournament/{TOURNAMENT_GRP_B}/season/{SEASON_ID}/squads"),
        ("grp_d_squads", f"{BASE_URL}/tournament/{TOURNAMENT_GRP_D}/season/{SEASON_ID}/squads"),
        ("wc_squads",    f"{BASE_URL}/unique-tournament/{UNIQUE_TOURNAMENT}/season/{SEASON_ID}/squads"),
        ("wc_top_players", f"{BASE_URL}/unique-tournament/{UNIQUE_TOURNAMENT}/season/{SEASON_ID}/top-players"),
    ]
    for ename, url in tournament_patterns:
        sc, payload, ct = fetch(ename, url, snap_dir)
        players = extract_players(payload) if payload else []
        top_keys = ",".join(list(payload.keys())[:8]) if isinstance(payload, dict) else ""
        print(f"  {ename}: HTTP={sc} players={len(players)} keys={top_keys[:60]}")
        results.append({"endpoint": ename, "url": url, "sc": sc, "players": len(players), "top_keys": top_keys})
        for p in players:
            if p["player_id"] not in all_players:
                all_players[p["player_id"]] = {**p, "team_name": None, "source": ename}
        _save_snapshot(cur, ename, url, sc, ct, snap_dir / f"{ename}.json",
                       "ok" if sc == 200 else "error", str(sc), top_keys, len(players))
    con.commit()

    # ─── Cross-match with DB rosters ──────────────────────────────────────────
    print("\n=== TASK 4: Cross-match extracted players to DB rosters ===")
    cur.execute("""
        SELECT sp.player_id, sp.player_name, sp.position, sp.jersey_number,
               sp.statshub_player_id, sp.id_status, t.team_name
        FROM statshub_team_players sp
        JOIN statshub_world_cup_teams t ON sp.team_id = t.statshub_team_id
        WHERE t.team_name IN ('Canada','Bosnia and Herzegovina','United States','Paraguay')
    """)
    roster_rows = cur.fetchall()

    # Build lookup by team
    from collections import defaultdict
    roster_by_team = defaultdict(list)
    for row in roster_rows:
        roster_by_team[row["team_name"]].append(dict(row))

    newly_confirmed = []

    if all_players:
        print(f"  Total extracted players: {len(all_players)}")
        for pid, pdata in list(all_players.items())[:20]:
            print(f"    id={pid} name={pdata['player_name']} team={pdata['team_name']} src={pdata['source']}")

        # Try to match extracted players to roster by ID or name
        for pid, pdata in all_players.items():
            # exact player_id match
            match = None
            for team_name, roster in roster_by_team.items():
                for rp in roster:
                    if str(rp["statshub_player_id"]) == str(pid):
                        match = (rp, team_name)
                        break
                if match:
                    break

            if match:
                rp, team_name = match
                if rp["id_status"] != "confirmed":
                    print(f"  [auto-confirm] {rp['player_name']} ({team_name}): id={pid}")
                    cur.execute("""
                        UPDATE statshub_team_players
                        SET statshub_player_id=?, id_status='confirmed', id_source='squad_endpoint'
                        WHERE id=?
                    """, (pid, rp["id"]))
                    newly_confirmed.append({"player_name": rp["player_name"], "player_id": pid,
                                            "team_name": team_name})
        con.commit()
        print(f"  Newly confirmed from squad endpoint: {len(newly_confirmed)}")
    else:
        print("  No players extracted from any endpoint.")

    # ─── Coverage summary ─────────────────────────────────────────────────────
    print("\n=== TASK 5: Coverage summary ===")
    for tname_db in ["Canada", "Bosnia and Herzegovina", "United States", "Paraguay"]:
        cur.execute("""
            SELECT id_status, COUNT(*) as cnt
            FROM statshub_team_players sp
            JOIN statshub_world_cup_teams t ON sp.team_id = t.statshub_team_id
            WHERE t.team_name = ?
            GROUP BY id_status
        """, (tname_db,))
        rows = cur.fetchall()
        stats = {r["id_status"]: r["cnt"] for r in rows}
        total = sum(stats.values())
        confirmed = stats.get("confirmed", 0)
        probable  = stats.get("probable", 0)
        print(f"  {tname_db}: {confirmed}/{total} confirmed | {probable} probable")

    # ─── Final report ─────────────────────────────────────────────────────────
    print("\n============================================================")
    print("FINAL REPORT")
    print("============================================================")

    useful = [r for r in results if r["sc"] == 200 and r["players"] > 0]
    all_200 = [r for r in results if r["sc"] == 200]
    print(f"Endpoints tested: {len(results)}")
    print(f"HTTP 200: {len(all_200)}")
    print(f"HTTP 200 with players: {len(useful)}")
    print()

    if useful:
        print("Useful endpoints (returned player data):")
        for r in useful:
            print(f"  {r['endpoint']}: {r['players']} players")
        print(f"\nTotal unique players extracted: {len(all_players)}")
        print(f"Newly confirmed in DB: {len(newly_confirmed)}")
        print("\n→ SQUAD DATA FOUND — update coverage with these players")
    else:
        print("No endpoint returned player data.")
        print("All 200 responses (no player data):")
        for r in all_200:
            print(f"  {r['endpoint']}: keys={r['top_keys'][:80]}")
        print()
        print("→ PLAYWRIGHT WARRANTED — all direct API approaches exhausted")

    con.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
