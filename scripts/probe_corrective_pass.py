"""
Corrective pass for today_canada_bosnia_usa_paraguay_probe.

Tasks:
  1. Fix player appearances — re-parse 43 cached raw files with corrected field mapping
  2. Smarter player ID mapping — Canada probable→confirm, USA/Paraguay unresolved/ambiguous
  3. Download performance for newly confirmed players only
  4. Retry USA vs Paraguay referee (lineups, statistics endpoints)
  5. Regenerate Excel (review + corrected copy)
  6. Final report + health checks

Usage:
  python -m scripts.probe_corrective_pass             # dry-run (no live calls)
  python -m scripts.probe_corrective_pass --execute   # live calls
  python -m scripts.probe_corrective_pass --execute --task 2   # single task
"""
from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
import requests

from app.config.settings import ROOT_DIR
from app.db.connection import get_connection, init_db
from app.db.queries import utc_now
from app.external.statshub_snapshot import classify_response, rows_detected, top_keys

# ── constants (same snapshot as original probe) ────────────────────────────────

SNAPSHOT_NAME = "today_canada_bosnia_usa_paraguay_probe"
BASE          = "https://www.statshub.com"
RAW_DIR       = ROOT_DIR / "data" / "raw" / "statshub" / "snapshots" / SNAPSHOT_NAME
OUTPUT_FILE   = ROOT_DIR / "data" / "processed" / "statshub" / "today_canada_bosnia_usa_paraguay_review.xlsx"
CORRECTED_FILE = ROOT_DIR / "data" / "processed" / "statshub" / "today_canada_bosnia_usa_paraguay_review_corrected.xlsx"
TODAY         = "2026-06-12"

TEAMS = [
    {"team_id": "4752", "team_name": "Canada",                 "country_slug": "canada"},
    {"team_id": "4479", "team_name": "Bosnia and Herzegovina", "country_slug": "bosnia-and-herzegovina"},
    {"team_id": "4724", "team_name": "United States",          "country_slug": "usa"},
    {"team_id": "4789", "team_name": "Paraguay",               "country_slug": "paraguay"},
]
TEAM_IDS = {t["team_id"] for t in TEAMS}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.statshub.com/",
}

USA_PARAGUAY_EVENT_ID = "15186873"

# Common display names for USA — FIFA full name → preferred search name(s)
USA_DISPLAY: dict[str, list[str]] = {
    "Alejandro ZENDEJAS SAAVEDRA":   ["Alejandro Zendejas"],
    "Alexander Michael FREEMAN":      ["Alex Freeman", "Alexander Freeman"],
    "Auston Levi-Jesaiah TRUSTY":     ["Auston Trusty"],
    "Brenden Russell AARONSON":       ["Brenden Aaronson"],
    "Christian Mate PULISIC":         ["Christian Pulisic", "Pulisic"],
    "Christopher Jeffrey RICHARDS":   ["Chris Richards", "Christopher Richards"],
    "Christopher Keith BRADY":        ["Chris Brady", "Christopher Brady"],
    "Folarin Jolaoluwa BALOGUN":      ["Folarin Balogun", "Balogun"],
    "Giovanni Alejandro REYNA":       ["Gio Reyna", "Giovanni Reyna"],
    "Haji Amir WRIGHT":               ["Haji Wright"],
    "Joseph Michael SCALLY":          ["Joe Scally", "Joseph Scally"],
    "Malik Leon TILLMAN":             ["Malik Tillman"],
    "Mark Alexander MCKENZIE":        ["Mark McKenzie"],
    "Matthew Andrew Geary FREESE":    ["Matt Freese", "Matthew Freese"],
    "Matthew Charles TURNER":         ["Matt Turner", "Matthew Turner"],
    "Maximilian Michael ARFSTEN":     ["Max Arfsten", "Maximilian Arfsten"],
    "Miles Gordon ROBINSON":          ["Miles Robinson"],
    "Ricardo Daniel PEPI":            ["Ricardo Pepi", "Pepi"],
    "Sebastian Matthew BERHALTER":    ["Sebastian Berhalter"],
    "Sergiño Gianni DEST":            ["Sergino Dest", "Dest"],
    "Timothy Michael REAM":           ["Tim Ream", "Timothy Ream"],
    "Timothy Tarpeh WEAH":            ["Tim Weah", "Timothy Weah"],
    "Tyler Shaan ADAMS":              ["Tyler Adams"],
    "Weston James Earl MC KENNIE":    ["Weston McKennie", "McKennie"],
}

# Paraguay display name overrides (FIFA long name → common name)
PAR_DISPLAY: dict[str, list[str]] = {
    "Alejandro Sebastian ROMERO GAMARRA":   ["Alejandro Romero", "Kaku"],
    "Alex Adrian ARCE BARRIOS":             ["Alex Arce"],
    "Arnaldo Antonio SANABRIA AYALA":       ["Antonio Sanabria", "Arnaldo Sanabria"],
    "Braian Oscar OJEDA RODRIGUEZ":         ["Braian Ojeda"],
    "Damián Josue BOBADILLA BENITEZ":       ["Damian Bobadilla"],
    "Diego Alexander GOMEZ AMARILLA":       ["Diego Gomez"],
    "Fabián Cornelio BALBUENA GONZÁLEZ":    ["Fabian Balbuena"],
    "Gastón Hernán OLVEIRA ECHEVERRIA":     ["Gaston Olveira"],
    "Gustavo Raul GÓMEZ PORTILLO":          ["Gustavo Gomez"],
    "Gustavo Ruben CABALLERO GONZALEZ":     ["Gustavo Caballero"],
    "Isidro Miguel PITTA SALDIVAR":         ["Isidro Pitta"],
    "Jose Maria CANALE DOMINGUEZ":          ["Jose Canale"],
    "Juan Jose CACERES":                    ["Juan Caceres"],
    "Júnior Osmar Ignacio ALONSO MUJICA":   ["Junior Alonso"],
    "Mauricio MAGALHAES PRADO":             ["Mauricio Prado", "Mauricio Magalhaes"],
    "Miguel Angel ALMIRON REJALA":          ["Miguel Almiron", "Almiron"],
    "Omar Federico ALDERETE FERNANDEZ":     ["Omar Alderete"],
    "Orlando Daniel GILL NOLDIN":           ["Orlando Gill"],
    "Roberto Junior FERNANDEZ TORRES":      ["Roberto Fernandez"],
    "Victor Gustavo VELAZQUEZ RAMOS":       ["Victor Velazquez"],
}

# ── helpers ────────────────────────────────────────────────────────────────────

def norm(v: str | None) -> str:
    if not v:
        return ""
    t = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()

def token_sort(v: str | None) -> str:
    return " ".join(sorted(norm(v).split()))

def raw_file(endpoint: str, suffix: str = "json") -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR / f"{endpoint}.{suffix}"

def fetch(url: str, endpoint: str, min_delay: float = 7.0, execute: bool = True) -> tuple[Any | None, dict]:
    target = raw_file(endpoint)
    if target.exists():
        try:
            p = json.loads(target.read_text(encoding="utf-8"))
            return p, {"endpoint": endpoint, "url": url, "status_code": "cached",
                       "raw_file": str(target), "status": "cached", "rows": rows_detected(p)}
        except Exception:
            pass
    if not execute:
        return None, {"endpoint": endpoint, "url": url, "status_code": "dry_run",
                      "raw_file": str(target), "status": "dry_run", "rows": 0}
    time.sleep(min_delay)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        text = r.text
        p = None
        try:
            p = json.loads(text)
        except Exception:
            pass
        suffix = "json" if p is not None else "txt"
        target = raw_file(endpoint, suffix)
        target.write_text(text, encoding="utf-8")
        status = classify_response(r.status_code, r.headers.get("content-type", ""), text, p)
        meta = {"endpoint": endpoint, "url": url, "status_code": r.status_code,
                "raw_file": str(target), "status": status, "rows": rows_detected(p) if p else 0}
        _record_raw_source(endpoint, url, meta, p)
        return p, meta
    except Exception as exc:
        target = raw_file(endpoint, "txt")
        target.write_text(f"error: {exc}", encoding="utf-8")
        return None, {"endpoint": endpoint, "url": url, "status_code": None,
                      "raw_file": str(target), "status": "error", "rows": 0}

def _record_raw_source(endpoint: str, url: str, meta: dict, payload: Any) -> None:
    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM statshub_raw_sources WHERE snapshot_name=? AND endpoint_name=?",
            (SNAPSHOT_NAME, endpoint)
        ).fetchone()
        if not exists:
            conn.execute("""
                INSERT INTO statshub_raw_sources
                    (snapshot_name, entity_type, endpoint_name, url, status_code,
                     content_type, response_size, top_keys, rows_detected, raw_file,
                     classification_status, notes, imported_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (SNAPSHOT_NAME, "corrective", endpoint, url,
                  str(meta.get("status_code", "")), "",
                  len(json.dumps(payload).encode()) if payload else 0,
                  ",".join(top_keys(payload)) if payload else "",
                  meta.get("rows", 0), meta.get("raw_file", ""),
                  meta.get("status", ""), "corrective_pass", utc_now()))

def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

# ── fixed player perf parser (unwraps player_statistics_event) ─────────────────

def _parse_player_perf(payload: Any, player_id: str, player_name: str,
                        team_name: str, endpoint: str) -> list[dict]:
    rows = []
    if not payload:
        return rows
    items = payload if isinstance(payload, list) else payload.get("data", payload.get("events", []))
    if not isinstance(items, list):
        return rows
    for item in items:
        if not isinstance(item, dict):
            continue
        stats = item.get("player_statistics_event") or item
        evt   = item.get("events") or {}
        row_pid = str(stats.get("playerId") or stats.get("player_id") or "")
        if row_pid and row_pid != str(player_id):
            continue
        ts = evt.get("startTimestamp")
        if ts:
            date_v = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            date_v = evt.get("date") or item.get("date") or item.get("matchDate") or ""
        tourn = evt.get("tournament") or item.get("tournament") or {}
        tournament_name = tourn.get("name", "") if isinstance(tourn, dict) else str(tourn or "")
        rows.append({
            "player_id": player_id, "player_name": player_name, "team_name": team_name,
            "endpoint_name": endpoint, "event_date": str(date_v)[:10],
            "tournament_name": tournament_name,
            "minutes_played":  stats.get("minutesPlayed") or stats.get("minutes"),
            "goals":           stats.get("goals") or stats.get("goalsScored"),
            "assists":         stats.get("goalAssist") or stats.get("assists"),
            "shots":           stats.get("shots") or stats.get("totalShots"),
            "shots_on_target": stats.get("onTargetScoringAttempt") or stats.get("shotsOnTarget") or stats.get("shotsOnGoal"),
            "fouls":           stats.get("fouls") or stats.get("foulsCommitted"),
            "was_fouled":      stats.get("wasFouled") or stats.get("foulsSuffered"),
            "yellow_cards":    stats.get("yellowCard") or stats.get("yellowCards"),
            "red_cards":       stats.get("redCard") or stats.get("redCards"),
            "xG":              _to_float(stats.get("expectedGoals") or stats.get("xG")),
            "xA":              _to_float(stats.get("expectedAssists") or stats.get("xA")),
            "key_passes":      stats.get("keyPass") or stats.get("keyPasses"),
            "passes":          stats.get("totalPass") or stats.get("passes") or stats.get("totalPasses"),
            "accurate_passes": stats.get("accuratePass") or stats.get("accuratePasses"),
            "tackles":         stats.get("totalTackle") or stats.get("tackles"),
            "possession_lost": stats.get("possessionLostCtrl") or stats.get("possessionLost") or stats.get("dispossessed"),
            "raw_json": json.dumps(item)[:1000],
        })
    return rows

def _aggregate_player_perf(rows: list[dict], player_id: str, player_name: str,
                             team_name: str, endpoint: str, raw_f: str) -> dict:
    def s(vals: list) -> float | None:
        clean = [v for v in vals if v is not None]
        return sum(clean) if clean else None

    apps  = sum(1 for r in rows if (r["minutes_played"] or 0) > 0)
    dates = [r["event_date"] for r in rows if r["event_date"]]
    comps: set[str] = set()
    for r in rows:
        if r.get("tournament_name"):
            comps.add(r["tournament_name"])

    return {
        "player_id": player_id, "player_name": player_name, "team_name": team_name,
        "endpoint_name": endpoint, "raw_file": raw_f,
        "source_rows":      len(rows),
        "appearances":      apps,
        "minutes":          s([r["minutes_played"] for r in rows]),
        "goals":            s([r["goals"] for r in rows]),
        "assists":          s([r["assists"] for r in rows]),
        "shots":            s([r["shots"] for r in rows]),
        "shots_on_target":  s([r["shots_on_target"] for r in rows]),
        "fouls":            s([r["fouls"] for r in rows]),
        "was_fouled":       s([r["was_fouled"] for r in rows]),
        "yellow_cards":     s([r["yellow_cards"] for r in rows]),
        "red_cards":        s([r["red_cards"] for r in rows]),
        "xG":               s([r["xG"] for r in rows]),
        "xA":               s([r["xA"] for r in rows]),
        "key_passes":       s([r["key_passes"] for r in rows]),
        "passes":           s([r["passes"] for r in rows]),
        "accurate_passes":  s([r["accurate_passes"] for r in rows]),
        "tackles":          s([r["tackles"] for r in rows]),
        "possession_lost":  s([r["possession_lost"] for r in rows]),
        "date_min":         min(dates) if dates else None,
        "date_max":         max(dates) if dates else None,
        "competitions_detected": json.dumps(sorted(comps)),
    }

# ── player update helper ───────────────────────────────────────────────────────

def _update_player(row_id: int, result: dict) -> None:
    with get_connection() as conn:
        conn.execute("""
            UPDATE statshub_team_players
            SET player_id = COALESCE(?, player_id),
                statshub_player_id_status = ?,
                player_id_confidence_score = ?,
                player_id_match_source = ?,
                player_id_match_method = ?,
                player_id_match_query = ?,
                player_id_match_notes = ?,
                candidate_ids = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            result.get("player_id"),
            result.get("player_id_status"),
            result.get("confidence_score"),
            result.get("match_source"),
            result.get("match_method"),
            result.get("match_query"),
            result.get("notes"),
            result.get("candidate_ids"),
            utc_now(),
            row_id,
        ))

# ── search + classify helpers ──────────────────────────────────────────────────

def _candidate_score(player: dict, candidate: dict) -> tuple[float, list[str]]:
    score: float = 0.0
    evidence: list[str] = []
    pname = norm(player.get("player_name", ""))
    cname = norm(candidate.get("name", ""))
    if pname and cname:
        if pname == cname:
            score += 80; evidence.append("exact")
        elif token_sort(player.get("player_name")) == token_sort(candidate.get("name")):
            score += 65; evidence.append("token-sort")
        elif pname in cname or cname in pname:
            score += 45; evidence.append("partial")
        elif any(t in cname for t in pname.split() if len(t) > 3):
            score += 25; evidence.append("token-overlap")
    team_n = norm(player.get("team_name", ""))
    country_slug = norm(candidate.get("countrySlug", ""))
    cand_team    = norm(candidate.get("teamName", "") or candidate.get("team", ""))
    if team_n and (team_n == country_slug or team_n in country_slug or country_slug in team_n):
        score += 15; evidence.append("country~team")
    if team_n and (team_n == cand_team or team_n in cand_team or cand_team in team_n):
        score += 10; evidence.append("team~cand_team")
    if candidate.get("id"):
        score += 5; evidence.append("has_id")
    return score, evidence

def _classify(player: dict, candidates: list[dict], query: str, raw_f: str) -> dict:
    scored = []
    for c in candidates:
        s, ev = _candidate_score(player, c)
        if s >= 45:
            scored.append((s, c, ev))
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return {"player_id": None, "player_id_status": "unresolved",
                "confidence_score": 0, "match_method": "statshub_search",
                "match_query": query, "match_source": raw_f,
                "candidate_ids": "", "notes": "No usable candidate."}

    best_s, best, best_ev = scored[0]
    second_s = scored[1][0] if len(scored) > 1 else 0
    ids = [str(x[1].get("id")) for x in scored if x[1].get("id")]

    if best_s >= 75 and (best_s - second_s) >= 10:
        status = "confirmed"
    elif best_s >= 65 and len(scored) == 1:
        status = "confirmed"
    elif best_s >= 60:
        status = "probable"
    elif len(scored) > 1 and (best_s - second_s) < 10:
        status = "ambiguous"
    else:
        status = "probable" if best_s >= 45 else "unresolved"

    pid = str(best.get("id")) if status in ("confirmed", "probable") and best.get("id") else None
    return {
        "player_id":        pid,
        "player_id_status": status,
        "confidence_score": best_s,
        "match_method":     "statshub_search",
        "match_query":      query,
        "match_source":     raw_f,
        "candidate_ids":    json.dumps(ids[:5]),
        "notes":            f"best={best_s} second={second_s} gap={best_s - second_s:.0f} evidence=[{'; '.join(best_ev)}]",
    }

def _do_search(query: str, execute: bool, min_delay: float) -> tuple[Any, dict]:
    digest = hashlib.sha1(query.encode()).hexdigest()[:10]
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", norm(query))[:40].strip("_")
    ep  = f"player_search_{prefix}_{digest}"
    url = f"{BASE}/api/search?q={quote_plus(query)}"
    return fetch(url, ep, min_delay=min_delay, execute=execute)

def _profile_validate(player_id: str, player: dict, execute: bool, min_delay: float) -> dict | None:
    """Fetch /api/player/{id} and check if name matches. Returns updated result or None."""
    ep  = f"player_profile_{player_id}_corrective"
    url = f"{BASE}/api/player/{player_id}"
    payload, meta = fetch(url, ep, min_delay=min_delay, execute=execute)
    if not payload or not isinstance(payload, dict):
        return None
    # Profile may be nested under 'player' key
    profile = payload.get("player") or payload
    api_name = profile.get("name") or profile.get("fullName") or ""
    if not api_name:
        return None
    s, ev = _candidate_score(player, {"name": api_name, "id": player_id,
                                       "countrySlug": player.get("country_slug", ""),
                                       "teamName": player.get("team_name", "")})
    if s >= 60:
        status = "confirmed" if s >= 75 else "probable"
        return {
            "player_id":        player_id,
            "player_id_status": status,
            "confidence_score": s,
            "match_method":     "profile_validation",
            "match_query":      f"/api/player/{player_id}",
            "match_source":     meta["raw_file"],
            "candidate_ids":    json.dumps([player_id]),
            "notes":            f"profile api_name={api_name!r} score={s} evidence=[{'; '.join(ev)}]",
        }
    return None

def _smarter_variants(player_name: str, team_name: str,
                       display_map: dict[str, list[str]] | None = None) -> list[str]:
    """Generate up to 8 search query variants, display-name-first if available."""
    seen: list[str] = []
    def add(q: str) -> None:
        q = q.strip()
        if q and q not in seen and len(seen) < 8:
            seen.append(q)

    # Display name overrides first
    if display_map and player_name in display_map:
        for dn in display_map[player_name]:
            add(dn)
            add(f"{dn} {team_name}")

    parts = norm(player_name).split()
    raw_parts = player_name.split()

    add(player_name)
    if len(raw_parts) >= 2:
        add(f"{raw_parts[0]} {raw_parts[-1]}")       # first + last
    n = norm(player_name)
    add(n)
    if len(parts) >= 2:
        add(f"{parts[0]} {parts[-1]}")                # normalized first+last
        add(f"{parts[0]} {parts[-1]} {norm(team_name)}")
    if len(parts) >= 3:
        add(f"{parts[0]} {parts[1]}")                 # first two tokens
    if len(parts) >= 2:
        add(parts[-1])                                # last name only

    return seen[:8]

# ── Task 1: fix appearances ────────────────────────────────────────────────────

def task1_fix_appearances() -> dict:
    print("\n=== TASK 1: Fix player appearances (re-parse cached raw files) ===")
    init_db()

    with get_connection() as conn:
        confirmed = [dict(r) for r in conn.execute("""
            SELECT id, team_id, team_name, player_id, player_name, statshub_player_id_status
            FROM statshub_team_players
            WHERE team_id IN ({})
              AND statshub_player_id_status IN ('confirmed','skipped_existing')
              AND player_id IS NOT NULL AND player_id != ''
            ORDER BY team_name, player_name
        """.format(",".join("?" * len(TEAM_IDS))), list(TEAM_IDS)).fetchall()]

    print(f"  Confirmed players to re-aggregate: {len(confirmed)}")
    fixed = 0
    sample_rows: list[dict] = []

    for p in confirmed:
        pid   = p["player_id"]
        pname = p["player_name"]
        tname = p["team_name"]
        ep    = f"player_{pid}_performance_limit50_today_probe"
        rf    = raw_file(ep)

        if not rf.exists():
            print(f"  SKIP {pname} — raw file missing: {ep}.json")
            continue

        payload = json.loads(rf.read_text(encoding="utf-8"))
        rows = _parse_player_perf(payload, pid, pname, tname, ep)
        agg  = _aggregate_player_perf(rows, pid, pname, tname, ep, str(rf))
        agg["snapshot_name"] = SNAPSHOT_NAME

        with get_connection() as conn:
            conn.execute("""
                UPDATE statshub_player_performance_aggregates
                SET appearances = ?,
                    minutes = ?,
                    goals = ?,
                    assists = ?,
                    shots = ?,
                    shots_on_target = ?,
                    fouls = ?,
                    was_fouled = ?,
                    yellow_cards = ?,
                    red_cards = ?,
                    xG = ?,
                    xA = ?,
                    key_passes = ?,
                    passes = ?,
                    accurate_passes = ?,
                    tackles = ?,
                    possession_lost = ?,
                    date_min = ?,
                    date_max = ?,
                    competitions_detected = ?
                WHERE player_id = ? AND snapshot_name = ?
            """, (
                agg["appearances"], agg["minutes"],
                agg["goals"], agg["assists"],
                agg["shots"], agg["shots_on_target"],
                agg["fouls"], agg["was_fouled"],
                agg["yellow_cards"], agg["red_cards"],
                agg["xG"], agg["xA"],
                agg["key_passes"], agg["passes"], agg["accurate_passes"],
                agg["tackles"], agg["possession_lost"],
                agg["date_min"], agg["date_max"],
                agg["competitions_detected"],
                pid, SNAPSHOT_NAME,
            ))
        fixed += 1
        if len(sample_rows) < 5 and agg["appearances"] and agg["appearances"] > 0:
            sample_rows.append({
                "player": pname, "team": tname,
                "source_rows": agg["source_rows"],
                "appearances": agg["appearances"],
                "minutes": agg["minutes"],
                "goals": agg["goals"],
                "assists": agg["assists"],
                "shots_on_target": agg["shots_on_target"],
            })

    print(f"  Re-aggregated: {fixed}")
    if sample_rows:
        print("  Sample players (appearances > 0):")
        for s in sample_rows:
            print(f"    {s['player']} ({s['team']}): rows={s['source_rows']} apps={s['appearances']} "
                  f"min={s['minutes']} g={s['goals']} a={s['assists']} sot={s['shots_on_target']}")
    else:
        print("  WARN: No players with appearances > 0 found — minutesPlayed may be 0 in all rows")

    return {"fixed": fixed, "sample": sample_rows}

# ── Task 2: smarter player ID mapping ─────────────────────────────────────────

def task2_player_id_mapping(execute: bool, min_delay: float) -> dict:
    print("\n=== TASK 2: Smarter player ID mapping (Canada/USA/Paraguay) ===")
    SKIP_TEAMS = {"4479"}  # Bosnia already 25/26 — only retry single unresolved

    with get_connection() as conn:
        players = [dict(r) for r in conn.execute("""
            SELECT id, team_id, team_name, player_id, player_name,
                   statshub_player_id_status, player_id_confidence_score, candidate_ids
            FROM statshub_team_players
            WHERE team_id IN ({})
            ORDER BY team_name, CAST(jersey_number AS INTEGER)
        """.format(",".join("?" * len(TEAM_IDS))), list(TEAM_IDS)).fetchall()]

    searches = 0
    newly_confirmed = 0
    newly_probable  = 0

    for p in players:
        tid    = p["team_id"]
        tname  = p["team_name"]
        pname  = p["player_name"]
        existing_id     = p.get("player_id")
        existing_status = p.get("statshub_player_id_status") or ""

        # Bosnia: only process the single unresolved
        if tid in SKIP_TEAMS and existing_status not in ("unresolved",):
            continue

        # Already confirmed — skip
        if existing_status in ("confirmed", "skipped_existing"):
            continue

        display_map = None
        if tname == "United States":
            display_map = USA_DISPLAY
        elif tname == "Paraguay":
            display_map = PAR_DISPLAY

        # For Canada/Bosnia probable players: first try profile validation
        if existing_id and existing_status == "probable":
            result = _profile_validate(existing_id, p, execute, min_delay)
            if result:
                _update_player(p["id"], result)
                if result["player_id_status"] == "confirmed":
                    newly_confirmed += 1
                    print(f"  CONFIRM (profile) {pname} ({tname}): id={existing_id} score={result['confidence_score']}")
                else:
                    print(f"  PROBABLE (profile) {pname} ({tname}): id={existing_id} score={result['confidence_score']}")
                continue

        # Generate variants (display-name-aware)
        variants = _smarter_variants(pname, tname, display_map)

        best_result: dict | None = None
        got_any_payload = False

        for query in variants:
            payload, meta = _do_search(query, execute=execute, min_delay=min_delay)
            if payload and isinstance(payload, dict):
                got_any_payload = True
                candidates = payload.get("players", [])
                result = _classify(p, candidates, query, meta["raw_file"])
                searches += 1
                if best_result is None or result["confidence_score"] > best_result["confidence_score"]:
                    best_result = result
                if result["player_id_status"] == "confirmed":
                    break

        if not got_any_payload:
            continue

        if best_result is None:
            continue

        # Don't downgrade existing probable/ambiguous to unresolved
        if (best_result["player_id_status"] == "unresolved"
                and existing_id
                and existing_status in ("probable", "ambiguous")):
            best_result["player_id_status"] = existing_status
            best_result["player_id"]        = existing_id

        prev_status = existing_status
        _update_player(p["id"], best_result)
        new_status = best_result["player_id_status"]

        if new_status == "confirmed" and prev_status != "confirmed":
            newly_confirmed += 1
            print(f"  CONFIRM {pname} ({tname}): id={best_result['player_id']} score={best_result['confidence_score']}")
        elif new_status == "probable" and prev_status == "unresolved":
            newly_probable += 1
            print(f"  PROBABLE {pname} ({tname}): id={best_result['player_id']} score={best_result['confidence_score']}")
        elif new_status == prev_status:
            pass  # no change, silent
        else:
            print(f"  {prev_status}→{new_status} {pname} ({tname}): score={best_result['confidence_score']}")

    print(f"\n  Searches made: {searches} | Newly confirmed: {newly_confirmed} | Newly probable: {newly_probable}")

    with get_connection() as conn:
        print("\n  Coverage after Task 2:")
        for t in TEAMS:
            rows = conn.execute("SELECT statshub_player_id_status FROM statshub_team_players WHERE team_id=?",
                                (t["team_id"],)).fetchall()
            statuses = [r[0] or "" for r in rows]
            conf  = sum(1 for s in statuses if s in ("confirmed", "skipped_existing"))
            prob  = sum(1 for s in statuses if s == "probable")
            ambig = sum(1 for s in statuses if s == "ambiguous")
            unres = len(statuses) - conf - prob - ambig
            print(f"    {t['team_name']}: {conf}/26 confirmed | {prob} probable | {ambig} ambiguous | {unres} unresolved")

    return {"searches": searches, "newly_confirmed": newly_confirmed, "newly_probable": newly_probable}

# ── Task 3: download performance for newly confirmed players ───────────────────

def task3_new_player_performance(execute: bool, min_delay: float) -> dict:
    print("\n=== TASK 3: Download performance for newly confirmed players ===")

    with get_connection() as conn:
        confirmed = [dict(r) for r in conn.execute("""
            SELECT tp.id, tp.team_id, tp.team_name, tp.player_id, tp.player_name
            FROM statshub_team_players tp
            WHERE tp.team_id IN ({})
              AND tp.statshub_player_id_status IN ('confirmed','skipped_existing')
              AND tp.player_id IS NOT NULL AND tp.player_id != ''
              AND NOT EXISTS (
                SELECT 1 FROM statshub_player_performance_aggregates pa
                WHERE pa.player_id = tp.player_id AND pa.snapshot_name = ?
              )
            ORDER BY tp.team_name, tp.player_name
        """.format(",".join("?" * len(TEAM_IDS))), list(TEAM_IDS) + [SNAPSHOT_NAME]).fetchall()]

    print(f"  New confirmed players without performance: {len(confirmed)}")
    downloaded = 0
    aggregates: list[dict] = []

    for p in confirmed:
        pid   = p["player_id"]
        pname = p["player_name"]
        tname = p["team_name"]
        ep    = f"player_{pid}_performance_limit50_today_probe"
        url   = f"{BASE}/api/player/{pid}/performance?limit=50"

        payload, meta = fetch(url, ep, min_delay=min_delay, execute=execute)
        rows = _parse_player_perf(payload, pid, pname, tname, ep) if payload else []
        agg  = _aggregate_player_perf(rows, pid, pname, tname, ep, meta["raw_file"])
        agg["snapshot_name"] = SNAPSHOT_NAME

        with get_connection() as conn:
            conn.execute("DELETE FROM statshub_player_performance_events WHERE player_id=? AND endpoint_name=?",
                         (pid, ep))
            for row in rows:
                conn.execute("""
                    INSERT INTO statshub_player_performance_events
                        (snapshot_name, player_id, player_name, team_name, endpoint_name,
                         event_date, tournament_name, minutes_played, goals, assists,
                         shots, shots_on_target, fouls, was_fouled, yellow_cards, red_cards,
                         xG, xA, key_passes, passes, accurate_passes, tackles,
                         possession_lost, raw_json, imported_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (SNAPSHOT_NAME, pid, pname, tname, ep,
                      row["event_date"], row["tournament_name"], row["minutes_played"],
                      row["goals"], row["assists"], row["shots"], row["shots_on_target"],
                      row["fouls"], row["was_fouled"], row["yellow_cards"], row["red_cards"],
                      row["xG"], row["xA"], row["key_passes"], row["passes"],
                      row["accurate_passes"], row["tackles"], row["possession_lost"],
                      row["raw_json"], utc_now()))
            conn.execute("DELETE FROM statshub_player_performance_aggregates WHERE player_id=? AND snapshot_name=?",
                         (pid, SNAPSHOT_NAME))
            conn.execute("""
                INSERT INTO statshub_player_performance_aggregates
                    (snapshot_name, player_id, player_name, team_name, endpoint_name,
                     source_rows, appearances, minutes, goals, assists,
                     shots, shots_on_target, fouls, was_fouled, yellow_cards, red_cards,
                     xG, xA, key_passes, passes, accurate_passes, tackles, possession_lost,
                     date_min, date_max, competitions_detected, raw_file, imported_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (SNAPSHOT_NAME, pid, pname, tname, ep,
                  agg["source_rows"], agg["appearances"], agg["minutes"],
                  agg["goals"], agg["assists"], agg["shots"], agg["shots_on_target"],
                  agg["fouls"], agg["was_fouled"], agg["yellow_cards"], agg["red_cards"],
                  agg["xG"], agg["xA"], agg["key_passes"], agg["passes"],
                  agg["accurate_passes"], agg["tackles"], agg["possession_lost"],
                  agg["date_min"], agg["date_max"], agg["competitions_detected"],
                  agg["raw_file"], utc_now()))

        downloaded += 1
        print(f"  {pname} ({tname}): status={meta['status']} rows={agg['source_rows']} apps={agg['appearances']}")
        aggregates.append(agg)

    if not downloaded:
        print("  All confirmed players already have performance data.")

    return {"downloaded": downloaded, "aggregates": aggregates}

# ── Task 4: referee retry ──────────────────────────────────────────────────────

def task4_referee_retry(execute: bool, min_delay: float) -> dict:
    print(f"\n=== TASK 4: USA vs Paraguay referee retry (event_id={USA_PARAGUAY_EVENT_ID}) ===")

    event_id = USA_PARAGUAY_EVENT_ID
    endpoints = [
        (f"event_{event_id}_corrective_base",      f"/api/event/{event_id}"),
        (f"event_{event_id}_corrective_lineups",   f"/api/event/{event_id}/lineups"),
        (f"event_{event_id}_corrective_statistics",f"/api/event/{event_id}/statistics"),
        (f"event_{event_id}_corrective_details",   f"/api/event/{event_id}/details"),
        (f"event_{event_id}_corrective_summary",   f"/api/event/{event_id}/summary"),
    ]

    ref_name = None
    ref_id   = None
    found_ep = None

    for ep_name, path in endpoints:
        url = f"{BASE}{path}"
        # Skip if already cached and returned nothing useful before
        # Use a _corrective_ prefix so we don't re-use stale 404 cache
        payload, meta = fetch(url, ep_name, min_delay=min_delay, execute=execute)
        if payload and isinstance(payload, dict):
            # Referee field search — check all common locations
            r_name = (
                payload.get("refereeName")
                or payload.get("referee")
                or (payload.get("event") or {}).get("refereeName")
                or (payload.get("event") or {}).get("referee")
            )
            r_id = (
                payload.get("refereeId")
                or (payload.get("event") or {}).get("refereeId")
            )
            # Check officials / matchOfficials arrays or dicts
            for officials_key in ("officials", "matchOfficials", "referees"):
                officials = payload.get(officials_key) or (payload.get("event") or {}).get(officials_key)
                if isinstance(officials, list):
                    for off in officials:
                        if isinstance(off, dict):
                            r_name = r_name or off.get("name") or off.get("fullName")
                            r_id   = r_id   or str(off.get("id", "")) or None
                elif isinstance(officials, dict):
                    # StatsHub returns referees as a single dict, not a list
                    r_name = r_name or officials.get("name") or officials.get("fullName")
                    r_id   = r_id   or (str(officials["id"]) if officials.get("id") else None)
            # Check lineups for referee
            lineups = payload.get("lineups") or {}
            if isinstance(lineups, dict):
                r_name = r_name or lineups.get("refereeName")
                r_id   = r_id   or lineups.get("refereeId")
            print(f"  {ep_name}: status={meta['status_code']} ref_name={r_name} ref_id={r_id}")
            print(f"    top keys: {list(payload.keys())[:10]}")
            if r_name:
                ref_name = r_name
                ref_id   = str(r_id) if r_id else None
                found_ep = ep_name
                break
        else:
            print(f"  {ep_name}: no payload (status={meta.get('status','')}/{meta.get('status_code','')})")

    if ref_name:
        print(f"  FOUND referee: {ref_name} (id={ref_id}) via {found_ep}")
        ref_status = "found"
    else:
        print(f"  USA vs Paraguay referee: not_available_yet_or_not_exposed")
        ref_status = "not_available_yet_or_not_exposed"

    # Update DB
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM statshub_match_referees WHERE snapshot_name=? AND event_id=?",
            (SNAPSHOT_NAME, event_id)
        ).fetchone()
        if existing:
            conn.execute("""
                UPDATE statshub_match_referees
                SET referee_name=?, referee_id=?, referee_endpoint_status=?,
                    source_endpoint=?, notes=?
                WHERE snapshot_name=? AND event_id=?
            """, (ref_name, ref_id, ref_status, found_ep or "none",
                  f"corrective_pass_{ref_status}", SNAPSHOT_NAME, event_id))
        else:
            conn.execute("""
                INSERT INTO statshub_match_referees
                    (snapshot_name, event_id, match_name, referee_id, referee_name,
                     source_endpoint, raw_file, referee_endpoint_status,
                     available_referee_metrics, notes, imported_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (SNAPSHOT_NAME, event_id, "United States vs Paraguay",
                  ref_id, ref_name, found_ep or "none", "",
                  ref_status, "[]", f"corrective_pass_{ref_status}", utc_now()))

    return {"ref_name": ref_name, "ref_id": ref_id, "status": ref_status}

# ── Task 5: regenerate Excel ───────────────────────────────────────────────────

def task5_regenerate_excel() -> None:
    print(f"\n=== TASK 5: Regenerate Excel ===")

    with get_connection() as conn:
        today_matches = [dict(r) for r in conn.execute(
            "SELECT * FROM statshub_today_matches WHERE snapshot_name=?", (SNAPSHOT_NAME,)
        ).fetchall()]
        team_map = [dict(r) for r in conn.execute(
            "SELECT * FROM statshub_world_cup_teams WHERE team_id IN ({}) AND world_cup_year=2026".format(
                ",".join("?" * len(TEAM_IDS))), list(TEAM_IDS)
        ).fetchall()]
        team_stats = [dict(r) for r in conn.execute(
            "SELECT * FROM statshub_team_performance_aggregates WHERE team_id IN ({}) ORDER BY team_id".format(
                ",".join("?" * len(TEAM_IDS))), list(TEAM_IDS)
        ).fetchall()]
        player_map = [dict(r) for r in conn.execute("""
            SELECT tp.team_name, tp.player_name, tp.position, tp.jersey_number,
                   tp.player_id, tp.statshub_player_id_status AS player_id_status,
                   tp.player_id_confidence_score AS confidence_score,
                   tp.player_id_match_query AS match_query,
                   tp.candidate_ids, tp.player_id_match_notes AS notes
            FROM statshub_team_players tp
            WHERE tp.team_id IN ({})
            ORDER BY tp.team_name, CAST(tp.jersey_number AS INTEGER)
        """.format(",".join("?" * len(TEAM_IDS))), list(TEAM_IDS)
        ).fetchall()]
        player_perf = [dict(r) for r in conn.execute("""
            SELECT pa.player_id, pa.player_name, pa.team_name, pa.source_rows,
                   pa.appearances, pa.minutes, pa.goals, pa.assists, pa.shots,
                   pa.shots_on_target, pa.fouls, pa.was_fouled, pa.yellow_cards,
                   pa.red_cards, pa.xG, pa.xA, pa.key_passes, pa.passes,
                   pa.accurate_passes, pa.tackles, pa.possession_lost,
                   pa.date_min, pa.date_max, pa.competitions_detected,
                   tp.position
            FROM statshub_player_performance_aggregates pa
            LEFT JOIN statshub_team_players tp
                   ON tp.player_id = pa.player_id AND tp.team_id IN ({})
            WHERE pa.snapshot_name=?
            ORDER BY pa.team_name, pa.player_name
        """.format(",".join("?" * len(TEAM_IDS))), list(TEAM_IDS) + [SNAPSHOT_NAME]
        ).fetchall()]
        unresolved = [dict(r) for r in conn.execute("""
            SELECT team_name, player_name, position, jersey_number,
                   statshub_player_id_status AS status,
                   player_id_match_query AS queries_tried,
                   candidate_ids, player_id_match_notes AS notes
            FROM statshub_team_players
            WHERE team_id IN ({})
              AND (statshub_player_id_status NOT IN ('confirmed','skipped_existing')
                   OR statshub_player_id_status IS NULL)
            ORDER BY team_name, CAST(jersey_number AS INTEGER)
        """.format(",".join("?" * len(TEAM_IDS))), list(TEAM_IDS)
        ).fetchall()]
        ref_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM statshub_match_referees WHERE snapshot_name=?", (SNAPSHOT_NAME,)
        ).fetchall()]
        raw_sources = [dict(r) for r in conn.execute(
            "SELECT * FROM statshub_raw_sources WHERE snapshot_name=? ORDER BY id", (SNAPSHOT_NAME,)
        ).fetchall()]

    # Enrich today_matches with referee data
    ref_by_event = {r["event_id"]: r for r in ref_rows}
    for row in today_matches:
        ref = ref_by_event.get(row.get("event_id"), {})
        row["referee_name"]         = ref.get("referee_name", "")
        row["referee_id"]           = ref.get("referee_id", "")
        row["referee_stats_status"] = ref.get("referee_endpoint_status", "")

    data_dict = [
        {"sheet": "today_matches",                "column": "event_id",        "description": "StatsHub event ID"},
        {"sheet": "today_matches",                "column": "referee_name",    "description": "Referee name (inline or endpoint)"},
        {"sheet": "player_id_mapping_4_teams",    "column": "player_id_status","description": "confirmed/probable/ambiguous/unresolved"},
        {"sheet": "player_id_mapping_4_teams",    "column": "confidence_score","description": "0–100 name match score"},
        {"sheet": "player_stats_confirmed_limit50","column": "appearances",    "description": "Rows where minutesPlayed > 0 (FIXED in corrective pass)"},
        {"sheet": "player_stats_confirmed_limit50","column": "source_rows",    "description": "Total API rows"},
        {"sheet": "referee_review",               "column": "referee_endpoint_status", "description": "Status after corrective retry"},
    ]

    sheets = {
        "today_matches":                  pd.DataFrame(today_matches),
        "team_id_mapping":                pd.DataFrame(team_map),
        "team_stats_limit50":             pd.DataFrame(team_stats),
        "player_id_mapping_4_teams":      pd.DataFrame(player_map),
        "player_stats_confirmed_limit50": pd.DataFrame(player_perf),
        "unresolved_players_4_teams":     pd.DataFrame(unresolved),
        "referee_review":                 pd.DataFrame(ref_rows),
        "raw_sources":                    pd.DataFrame(raw_sources),
        "data_dictionary":                pd.DataFrame(data_dict),
    }

    for out_path in [OUTPUT_FILE, CORRECTED_FILE]:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            for name, df in sheets.items():
                if df.empty:
                    df = pd.DataFrame([{"note": f"No data for {name}"}])
                df.to_excel(writer, sheet_name=name[:31], index=False)
        print(f"  OK Saved: {out_path}")

# ── Task 6: final report ───────────────────────────────────────────────────────

def task6_final_report(t1: dict, t2: dict, t3: dict, t4: dict) -> None:
    print("\n" + "=" * 60)
    print("TASK 6: FINAL REPORT")
    print("=" * 60)
    print(f"Snapshot: {SNAPSHOT_NAME}  Date: {TODAY}")

    # A. Player ID coverage before vs after
    print("\n--- A. Player ID coverage ---")
    with get_connection() as conn:
        before = {
            "Canada": (10, 15, 0, 1),
            "Bosnia and Herzegovina": (25, 0, 0, 1),
            "United States": (2, 0, 0, 24),
            "Paraguay": (6, 7, 6, 7),
        }
        for t in TEAMS:
            rows = conn.execute(
                "SELECT statshub_player_id_status FROM statshub_team_players WHERE team_id=?",
                (t["team_id"],)
            ).fetchall()
            statuses = [r[0] or "" for r in rows]
            conf  = sum(1 for s in statuses if s in ("confirmed","skipped_existing"))
            prob  = sum(1 for s in statuses if s == "probable")
            ambig = sum(1 for s in statuses if s == "ambiguous")
            unres = len(statuses) - conf - prob - ambig
            b = before.get(t["team_name"], (0,0,0,0))
            delta = conf - b[0]
            arrow = f"+{delta}" if delta > 0 else str(delta)
            print(f"  {t['team_name']}: {conf}/26 confirmed ({arrow} new) | {prob} probable | {ambig} ambiguous | {unres} unresolved")

    # B. Player performance coverage
    print("\n--- B. Player performance coverage ---")
    with get_connection() as conn:
        for t in TEAMS:
            n_conf = conn.execute("""
                SELECT COUNT(*) FROM statshub_team_players
                WHERE team_id=? AND statshub_player_id_status IN ('confirmed','skipped_existing')
            """, (t["team_id"],)).fetchone()[0]
            n_perf = conn.execute("""
                SELECT COUNT(*) FROM statshub_player_performance_aggregates pa
                JOIN statshub_team_players tp ON tp.player_id = pa.player_id
                WHERE tp.team_id=? AND pa.snapshot_name=?
            """, (t["team_id"], SNAPSHOT_NAME)).fetchone()[0]
            print(f"  {t['team_name']}: confirmed={n_conf} | perf_downloaded={n_perf}")

    # C. Appearances fix
    print("\n--- C. Appearances fix ---")
    if t1.get("sample"):
        print("  Sample players (appearances > 0 after fix):")
        for s in t1["sample"][:3]:
            print(f"    {s['player']} ({s['team']}): source_rows={s['source_rows']} "
                  f"apps={s['appearances']} min={s['minutes']} g={s['goals']} a={s['assists']} sot={s['shots_on_target']}")
    else:
        with get_connection() as conn:
            r = conn.execute("""
                SELECT player_name, team_name, source_rows, appearances, minutes, goals, assists, shots_on_target
                FROM statshub_player_performance_aggregates
                WHERE snapshot_name=? AND appearances > 0
                ORDER BY appearances DESC LIMIT 3
            """, (SNAPSHOT_NAME,)).fetchall()
        if r:
            print("  Sample players (appearances > 0 from DB):")
            for row in r:
                print(f"    {row[0]} ({row[1]}): source_rows={row[2]} apps={row[3]} min={row[4]} g={row[5]} a={row[6]} sot={row[7]}")
        else:
            print("  WARN: Still no players with appearances > 0 in DB — check minutesPlayed in raw data")
    total_apps = sum((s.get("appearances") or 0) for s in (t1.get("sample") or []))
    print(f"  Appearances no longer all-zero: {'YES' if t1.get('sample') else 'UNCERTAIN — check DB'}")

    # D. Referee
    print("\n--- D. Referee coverage ---")
    with get_connection() as conn:
        for row in conn.execute("SELECT match_name, referee_name, referee_endpoint_status FROM statshub_match_referees WHERE snapshot_name=?", (SNAPSHOT_NAME,)).fetchall():
            status_str = "OK" if row["referee_name"] else "NOT FOUND"
            print(f"  {row['match_name']}: {status_str} {row['referee_name'] or ''} | endpoint={row['referee_endpoint_status']}")

    # E. Decision
    print("\n--- E. Decision ---")
    with get_connection() as conn:
        for t in TEAMS:
            rows = conn.execute(
                "SELECT statshub_player_id_status FROM statshub_team_players WHERE team_id=?",
                (t["team_id"],)
            ).fetchall()
            statuses = [r[0] or "" for r in rows]
            conf  = sum(1 for s in statuses if s in ("confirmed","skipped_existing"))
            n_perf = conn.execute("""
                SELECT COUNT(*) FROM statshub_player_performance_aggregates pa
                JOIN statshub_team_players tp ON tp.player_id = pa.player_id
                WHERE tp.team_id=? AND pa.snapshot_name=?
            """, (t["team_id"], SNAPSHOT_NAME)).fetchone()[0]
            pct = conf / 26 * 100
            if pct >= 75:
                verdict = "READY for player props"
            elif pct >= 40:
                verdict = "PARTIAL — usable with caveats"
            else:
                verdict = "INCOMPLETE — player props not reliable"
            print(f"  {t['team_name']}: {conf}/26 confirmed ({pct:.0f}%) perf={n_perf} → {verdict}")

    print(f"\n  Excel files:")
    print(f"    {OUTPUT_FILE}")
    print(f"    {CORRECTED_FILE}")
    print(f"  Both files: {'OK' if OUTPUT_FILE.exists() and CORRECTED_FILE.exists() else 'MISSING'}")

# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Corrective pass for today's probe")
    parser.add_argument("--execute",      action="store_true", help="Enable live API calls")
    parser.add_argument("--min-delay",    type=float, default=7.0)
    parser.add_argument("--search-delay", type=float, default=3.0)
    parser.add_argument("--task",         type=int,   default=0,
                        help="0=all, 1-6=single task")
    args = parser.parse_args()
    execute     = args.execute
    min_delay   = args.min_delay
    srch_delay  = args.search_delay
    run_all     = args.task == 0

    init_db()

    t1 = t2 = t3 = t4 = {}

    if run_all or args.task == 1:
        t1 = task1_fix_appearances()

    if run_all or args.task == 2:
        t2 = task2_player_id_mapping(execute=execute, min_delay=srch_delay)

    if run_all or args.task == 3:
        t3 = task3_new_player_performance(execute=execute, min_delay=min_delay)

    if run_all or args.task == 4:
        t4 = task4_referee_retry(execute=execute, min_delay=min_delay)

    if run_all or args.task == 5:
        task5_regenerate_excel()

    if run_all or args.task == 6:
        task6_final_report(t1 or {}, t2 or {}, t3 or {}, t4 or {})


if __name__ == "__main__":
    main()
