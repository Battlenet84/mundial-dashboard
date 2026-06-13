"""
Bounded StatsHub probe for today's matches only.
  - Canada vs Bosnia and Herzegovina
  - United States vs Paraguay

Snapshot: today_canada_bosnia_usa_paraguay_probe

Usage:
  python -m scripts.probe_today_canada_bosnia_usa_paraguay            # dry-run plan
  python -m scripts.probe_today_canada_bosnia_usa_paraguay --execute  # live downloads
  python -m scripts.probe_today_canada_bosnia_usa_paraguay --execute --phase 5   # single phase
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
from collections import defaultdict
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

SNAPSHOT_NAME = "today_canada_bosnia_usa_paraguay_probe"
BASE = "https://www.statshub.com"
RAW_DIR = ROOT_DIR / "data" / "raw" / "statshub" / "snapshots" / SNAPSHOT_NAME
OUTPUT_FILE = ROOT_DIR / "data" / "processed" / "statshub" / "today_canada_bosnia_usa_paraguay_review.xlsx"
TODAY = "2026-06-12"

# June 12 2026 UTC unix timestamps (June 11 start=1781136000, +86400 each day)
TODAY_START_TS = 1781136000 + 86400   # 1781222400
TODAY_END_TS   = TODAY_START_TS + 86399  # 1781308799

TEAMS = [
    {"team_id": "4752", "team_name": "Canada",                  "aliases": ["Canada", "CAN"],                     "country_slug": "canada"},
    {"team_id": "4479", "team_name": "Bosnia and Herzegovina",  "aliases": ["Bosnia", "Bosnia and Herzegovina", "BIH"], "country_slug": "bosnia-and-herzegovina"},
    {"team_id": "4724", "team_name": "United States",           "aliases": ["United States", "USA", "USMNT"],     "country_slug": "usa"},
    {"team_id": "4789", "team_name": "Paraguay",                "aliases": ["Paraguay", "PAR"],                   "country_slug": "paraguay"},
]
TEAM_IDS  = {t["team_id"] for t in TEAMS}
TEAM_BY_ID = {t["team_id"]: t for t in TEAMS}

TARGET_MATCHES = [
    {"home": "4752", "away": "4479", "label": "Canada vs Bosnia and Herzegovina"},
    {"home": "4724", "away": "4789", "label": "United States vs Paraguay"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.statshub.com/",
}

# ── helpers ────────────────────────────────────────────────────────────────────

def norm(v: str | None) -> str:
    if not v:
        return ""
    t = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()

def token_sort(v: str | None) -> str:
    return " ".join(sorted(norm(v).split()))

def _to_xfloat(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def safe(v: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", v)

def raw_file(endpoint: str, suffix: str = "json") -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR / f"{endpoint}.{suffix}"

def fetch(url: str, endpoint: str, min_delay: float = 7.0, execute: bool = True) -> tuple[Any | None, dict]:
    """Fetch URL and save raw file. Returns (payload, meta)."""
    target = raw_file(endpoint)
    # Return cached file if exists (idempotent re-runs)
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
            """, (SNAPSHOT_NAME, "probe", endpoint, url,
                  str(meta.get("status_code", "")), "",
                  len(json.dumps(payload).encode()) if payload else 0,
                  ",".join(top_keys(payload)) if payload else "",
                  meta.get("rows", 0), meta.get("raw_file", ""),
                  meta.get("status", ""), "", utc_now()))

def ensure_tables() -> None:
    init_db()
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS statshub_today_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT,
                event_id TEXT,
                match_label TEXT,
                event_date TEXT,
                event_time TEXT,
                home_team_id TEXT,
                home_team_name TEXT,
                away_team_id TEXT,
                away_team_name TEXT,
                tournament TEXT,
                status TEXT,
                source_endpoint TEXT,
                raw_file TEXT,
                confidence TEXT,
                notes TEXT,
                imported_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS statshub_match_referees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT,
                event_id TEXT,
                match_name TEXT,
                referee_id TEXT,
                referee_name TEXT,
                source_endpoint TEXT,
                raw_file TEXT,
                referee_endpoint_status TEXT,
                available_referee_metrics TEXT,
                notes TEXT,
                imported_at TEXT
            )
        """)
        # Add world_cup_tournament_id column to statshub_team_players if not present
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(statshub_team_players)").fetchall()}
        for col, typ in [
            ("player_id_confidence_score", "REAL"),
            ("player_id_match_source", "TEXT"),
            ("player_id_match_method", "TEXT"),
            ("player_id_match_query", "TEXT"),
            ("player_id_match_notes", "TEXT"),
            ("candidate_ids", "TEXT"),
            ("updated_at", "TEXT"),
        ]:
            if col not in cols:
                conn.execute(f"ALTER TABLE statshub_team_players ADD COLUMN {col} {typ}")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS statshub_player_id_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT, world_cup_year INTEGER,
                team_name TEXT, statshub_team_id TEXT,
                player_name TEXT, player_name_canonical TEXT,
                position TEXT, jersey_number TEXT,
                candidate_player_id TEXT, candidate_name TEXT,
                candidate_team TEXT, candidate_country TEXT,
                score REAL, evidence TEXT, source_query TEXT,
                raw_file TEXT, status TEXT, imported_at TEXT
            )
        """)
        # team_performance tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS statshub_team_performance_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT, team_id TEXT, team_name TEXT,
                endpoint_name TEXT, event_date TEXT, opponent_name TEXT,
                goals_for REAL, goals_against REAL, xG REAL, xGA REAL,
                shots REAL, shots_on_target REAL, fouls REAL,
                yellow_cards REAL, red_cards REAL, passes REAL,
                accurate_passes REAL, possession REAL, corners REAL,
                raw_json TEXT, imported_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS statshub_team_performance_aggregates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT, endpoint_name TEXT,
                team_id TEXT, team_name TEXT,
                source_rows INTEGER, date_min TEXT, date_max TEXT,
                competitions_detected TEXT, matches_in_window INTEGER,
                raw_file TEXT,
                goals_for REAL, goals_against REAL,
                expected_goals REAL, expected_goals_against REAL,
                shots REAL, shots_on_target REAL, shots_off_target REAL,
                big_chances REAL, fouls REAL, yellow_cards REAL,
                red_cards REAL, passes REAL, accurate_passes REAL,
                possession_avg REAL, corners REAL,
                goalkeeper_saves REAL, final_third_entries REAL,
                imported_at TEXT
            )
        """)
        # player performance tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS statshub_player_performance_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT, player_id TEXT, player_name TEXT,
                team_name TEXT, endpoint_name TEXT, event_date TEXT,
                tournament_name TEXT, minutes_played REAL,
                goals REAL, assists REAL, shots REAL, shots_on_target REAL,
                fouls REAL, was_fouled REAL, yellow_cards REAL, red_cards REAL,
                xG REAL, xA REAL, key_passes REAL,
                passes REAL, accurate_passes REAL, tackles REAL,
                possession_lost REAL, raw_json TEXT, imported_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS statshub_player_performance_aggregates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT, player_id TEXT, player_name TEXT,
                team_name TEXT, endpoint_name TEXT,
                source_rows INTEGER, appearances INTEGER,
                minutes REAL, goals REAL, assists REAL,
                shots REAL, shots_on_target REAL, fouls REAL,
                was_fouled REAL, yellow_cards REAL, red_cards REAL,
                xG REAL, xA REAL, key_passes REAL,
                passes REAL, accurate_passes REAL, tackles REAL,
                possession_lost REAL,
                date_min TEXT, date_max TEXT, competitions_detected TEXT,
                raw_file TEXT, imported_at TEXT
            )
        """)

# ── Phase 1: confirm team IDs ──────────────────────────────────────────────────

def phase1_confirm_teams() -> list[dict]:
    print("\n=== PHASE 1: Confirm team IDs ===")
    results = []
    with get_connection() as conn:
        for t in TEAMS:
            row = conn.execute("""
                SELECT statshub_team_id, statshub_team_slug, statshub_match_status, notes, source
                FROM statshub_world_cup_teams
                WHERE statshub_team_id = ? AND world_cup_year = 2026
                LIMIT 1
            """, (t["team_id"],)).fetchone()
            if row:
                results.append({
                    "team_name": t["team_name"],
                    "team_name_canonical": norm(t["team_name"]),
                    "statshub_team_id": row["statshub_team_id"],
                    "statshub_team_slug": row["statshub_team_slug"],
                    "match_status": row["statshub_match_status"] or "confirmed",
                    "source": row["source"] or "local_db",
                    "notes": row["notes"] or "",
                })
                print(f"  OK {t['team_name']}: id={t['team_id']} status={row['statshub_match_status']}")
            else:
                results.append({
                    "team_name": t["team_name"],
                    "team_name_canonical": norm(t["team_name"]),
                    "statshub_team_id": t["team_id"],
                    "statshub_team_slug": t.get("country_slug", ""),
                    "match_status": "confirmed_hardcoded",
                    "source": "hardcoded_from_prior_session",
                    "notes": "Not found in statshub_world_cup_teams; using hardcoded ID.",
                })
                print(f"  ⚠ {t['team_name']}: id={t['team_id']} (hardcoded – DB row missing)")
    return results

# ── Phase 2: find today's match event IDs ─────────────────────────────────────

def _parse_event(ev: dict) -> dict | None:
    """Extract match info from a StatsHub event dict.

    StatsHub event_by_date format: the outer item is an event-group wrapper that
    carries homeTeam/awayTeam/referee at the top level but stores the actual event
    object (with id/startTimestamp) under the key 'events' (a dict, not a list).
    We fall back to the wrapper itself if 'events' sub-key is absent.
    """
    # Unwrap nested event dict if present (event_by_date format)
    inner = ev.get("events")
    if isinstance(inner, dict) and inner.get("id"):
        base = inner
    else:
        base = ev
    eid = str(base.get("id") or base.get("eventId") or base.get("event_id") or "")
    if not eid:
        return None
    home = ev.get("homeTeam") or base.get("homeTeam") or {}
    away = ev.get("awayTeam") or base.get("awayTeam") or {}
    home_id = str(home.get("id") or "")
    away_id = str(away.get("id") or "")
    ts = base.get("startTimestamp") or ev.get("startTimestamp")
    date_str = ""
    time_str = ""
    if ts:
        try:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            date_str = dt.strftime("%Y-%m-%d")
            time_str = dt.strftime("%H:%M UTC")
        except Exception:
            pass
    tournament = ""
    for k in ["uniqueTournament", "tournament", "league"]:
        v = ev.get(k)
        if isinstance(v, dict) and v.get("name"):
            tournament = v["name"]
            break
    status_v = ev.get("status")
    status_str = status_v.get("type") if isinstance(status_v, dict) else str(status_v or "")
    return {
        "event_id": eid,
        "home_id": home_id,
        "home_name": home.get("name", ""),
        "away_id": away_id,
        "away_name": away.get("name", ""),
        "date": date_str,
        "time": time_str,
        "tournament": tournament,
        "status": status_str,
        "referee_name": ev.get("refereeName") or base.get("refereeName") or ev.get("referee") or "",
        "referee_yellow": ev.get("refereeYellowCards") or base.get("refereeYellowCards"),
        "referee_red": ev.get("refereeRedCards") or base.get("refereeRedCards"),
        "referee_games": ev.get("refereeGames") or base.get("refereeGames"),
        "referee_avg_cards": ev.get("refereeAvgCards") or base.get("refereeAvgCards"),
    }

def _events_from_payload(payload: Any) -> list[dict]:
    """Flatten events from various payload shapes."""
    events = []
    if isinstance(payload, list):
        events = payload
    elif isinstance(payload, dict):
        for k in ["data", "events", "fixtures", "results"]:
            v = payload.get(k)
            if isinstance(v, list):
                events = v
                break
        # event_by_date format: data is list of event-wrappers
        if not events and "data" in payload:
            raw_data = payload["data"]
            if isinstance(raw_data, list):
                for item in raw_data:
                    if isinstance(item, dict):
                        # Each item might have nested events
                        for subk in ["events", "event"]:
                            sv = item.get(subk)
                            if isinstance(sv, list):
                                events.extend(sv)
                        # Or it might BE the event
                        if item.get("id") or item.get("eventId"):
                            events.append(item)
    return events

def phase2_find_today_matches(execute: bool, min_delay: float) -> list[dict]:
    print(f"\n=== PHASE 2: Find today's match event IDs (date={TODAY}) ===")
    found: dict[str, dict] = {}  # event_id -> match_info
    raw_sources: list[dict] = []

    # --- 2a: event_by_date for June 12 ---
    ep = f"event_by_date_{TODAY.replace('-', '_')}"
    url = f"{BASE}/api/event/by-date?startOfDay={TODAY_START_TS}&endOfDay={TODAY_END_TS}"
    payload, meta = fetch(url, ep, min_delay=min_delay, execute=execute)
    raw_sources.append({**meta, "endpoint_name": ep, "url": url})
    if payload:
        events = _events_from_payload(payload)
        # event_by_date returns top-level list of event wrappers
        if isinstance(payload, dict) and "data" in payload:
            data = payload["data"]
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        parsed = _parse_event(item)
                        if parsed and (parsed["home_id"] in TEAM_IDS or parsed["away_id"] in TEAM_IDS):
                            found[parsed["event_id"]] = {**parsed, "source_endpoint": ep, "raw_file": meta["raw_file"]}
        for ev in events:
            if isinstance(ev, dict):
                parsed = _parse_event(ev)
                if parsed and (parsed["home_id"] in TEAM_IDS or parsed["away_id"] in TEAM_IDS):
                    found[parsed["event_id"]] = {**parsed, "source_endpoint": ep, "raw_file": meta["raw_file"]}
        print(f"  event_by_date: {len(events)} total events, found {len(found)} with our teams")
    else:
        print(f"  event_by_date: no payload (status={meta['status']})")

    # --- 2b: team events for each of the 4 teams ---
    for t in TEAMS:
        tid = t["team_id"]
        for status_filter in ["", "notstarted", "scheduled"]:
            if len([e for e in found.values() if e.get("home_id") == tid or e.get("away_id") == tid]) > 0:
                break  # already found this team's match
            params = f"?limit=20"
            if status_filter:
                params += f"&status={status_filter}"
            ep_name = f"team_{tid}_events_upcoming{'_' + status_filter if status_filter else ''}"
            team_url = f"{BASE}/api/team/{tid}/events{params}"
            p, m = fetch(team_url, ep_name, min_delay=min_delay, execute=execute)
            raw_sources.append({**m, "endpoint_name": ep_name, "url": team_url})
            if p:
                evs = _events_from_payload(p)
                for ev in evs:
                    if isinstance(ev, dict):
                        parsed = _parse_event(ev)
                        if parsed and (parsed["home_id"] in TEAM_IDS or parsed["away_id"] in TEAM_IDS):
                            if parsed["event_id"] not in found:
                                found[parsed["event_id"]] = {**parsed, "source_endpoint": ep_name, "raw_file": m["raw_file"]}
                print(f"  {ep_name}: {len(evs)} events in response")
            else:
                print(f"  {ep_name}: no payload (status={m['status']})")

    # --- store results ---
    match_results = []
    for match_spec in TARGET_MATCHES:
        home_id = match_spec["home"]
        away_id = match_spec["away"]
        label   = match_spec["label"]
        candidate = None
        for eid, ev in found.items():
            if ev["home_id"] == home_id and ev["away_id"] == away_id:
                candidate = ev
                break
        if candidate is None:
            # also check reversed (in case API returns away/home swapped)
            for eid, ev in found.items():
                if (ev["home_id"] == home_id or ev["away_id"] == home_id) and \
                   (ev["home_id"] == away_id or ev["away_id"] == away_id):
                    candidate = ev
                    break
        if candidate:
            print(f"  OK {label}: event_id={candidate['event_id']} date={candidate['date']} {candidate['time']}")
            match_results.append({
                "snapshot_name": SNAPSHOT_NAME,
                "event_id": candidate["event_id"],
                "match_label": label,
                "event_date": candidate["date"] or TODAY,
                "event_time": candidate["time"],
                "home_team_id": candidate["home_id"],
                "home_team_name": candidate["home_name"] or TEAM_BY_ID.get(home_id, {}).get("team_name", ""),
                "away_team_id": candidate["away_id"],
                "away_team_name": candidate["away_name"] or TEAM_BY_ID.get(away_id, {}).get("team_name", ""),
                "tournament": candidate["tournament"],
                "status": candidate["status"],
                "source_endpoint": candidate["source_endpoint"],
                "raw_file": candidate["raw_file"],
                "confidence": "confirmed",
                "notes": f"referee_name_inline={candidate.get('referee_name','')}",
                "referee_name_inline": candidate.get("referee_name", ""),
                "referee_yellow": candidate.get("referee_yellow"),
                "referee_red": candidate.get("referee_red"),
                "referee_games": candidate.get("referee_games"),
                "referee_avg_cards": candidate.get("referee_avg_cards"),
            })
        else:
            print(f"  FAIL {label}: NOT FOUND")
            match_results.append({
                "snapshot_name": SNAPSHOT_NAME,
                "event_id": "missing_event_id",
                "match_label": label,
                "event_date": TODAY,
                "event_time": "",
                "home_team_id": home_id,
                "home_team_name": TEAM_BY_ID.get(home_id, {}).get("team_name", ""),
                "away_team_id": away_id,
                "away_team_name": TEAM_BY_ID.get(away_id, {}).get("team_name", ""),
                "tournament": "",
                "status": "not_found",
                "source_endpoint": "all_tried",
                "raw_file": "",
                "confidence": "missing",
                "notes": "Not found in event_by_date or team events endpoints.",
                "referee_name_inline": "",
                "referee_yellow": None,
                "referee_red": None,
                "referee_games": None,
                "referee_avg_cards": None,
            })

    # persist to DB
    with get_connection() as conn:
        conn.execute("DELETE FROM statshub_today_matches WHERE snapshot_name=?", (SNAPSHOT_NAME,))
        for m in match_results:
            conn.execute("""
                INSERT INTO statshub_today_matches
                    (snapshot_name, event_id, match_label, event_date, event_time,
                     home_team_id, home_team_name, away_team_id, away_team_name,
                     tournament, status, source_endpoint, raw_file, confidence, notes, imported_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (SNAPSHOT_NAME, m["event_id"], m["match_label"], m["event_date"], m["event_time"],
                  m["home_team_id"], m["home_team_name"], m["away_team_id"], m["away_team_name"],
                  m["tournament"], m["status"], m["source_endpoint"], m["raw_file"],
                  m["confidence"], m["notes"], utc_now()))

    return match_results

# ── Phase 3: referee data ──────────────────────────────────────────────────────

def phase3_referee_data(matches: list[dict], execute: bool, min_delay: float) -> list[dict]:
    print("\n=== PHASE 3: Referee data ===")
    referee_results = []

    for match in matches:
        event_id = match["event_id"]
        label    = match["match_label"]

        # If referee name already in inline event data, use it
        inline_ref = match.get("referee_name_inline", "")
        inline_ref_stats = {
            "yellow_cards": match.get("referee_yellow"),
            "red_cards": match.get("referee_red"),
            "games": match.get("referee_games"),
            "avg_cards": match.get("referee_avg_cards"),
        }

        if event_id == "missing_event_id":
            print(f"  FAIL {label}: no event_id – skipping")
            referee_results.append({
                "event_id": event_id, "match_name": label,
                "referee_id": None, "referee_name": None,
                "source_endpoint": "n/a", "raw_file": "",
                "referee_endpoint_status": "skipped_no_event_id",
                "available_referee_metrics": "",
                "notes": "No event_id found in Phase 2.",
            })
            continue

        ref_id   = None
        ref_name = inline_ref or None
        ref_metrics: list[str] = []
        best_raw_file = match.get("raw_file", "")
        best_source   = match.get("source_endpoint", "event_by_date_inline")
        ref_ep_status = "not_attempted"

        if inline_ref:
            print(f"  OK {label}: referee={inline_ref} (inline in event)")
            ref_metrics = [k for k, v in inline_ref_stats.items() if v is not None]
            ref_ep_status = "inline_in_event"

        # Try event detail endpoints to get referee_id
        for ep_suffix in ["", "/details", "/summary"]:
            ep_name = f"event_{event_id}{ep_suffix.replace('/', '_') or '_base'}"
            url     = f"{BASE}/api/event/{event_id}{ep_suffix}"
            p, m    = fetch(url, ep_name, min_delay=min_delay, execute=execute)
            if p and isinstance(p, dict):
                for ref_key in ["refereeId", "referee_id", "mainRefereeId"]:
                    v = p.get(ref_key) or (p.get("referee") or {}).get("id") if isinstance(p.get("referee"), dict) else None
                    if v:
                        ref_id = str(v)
                        break
                if not ref_name:
                    for rk in ["refereeName", "referee_name", "mainRefereeName"]:
                        v = p.get(rk)
                        if v:
                            ref_name = str(v)
                            break
                    officials = p.get("matchOfficials") or p.get("officials") or []
                    if isinstance(officials, list) and officials:
                        for off in officials:
                            if isinstance(off, dict) and off.get("type") in ("main", "center", "referee", None):
                                ref_name = ref_name or off.get("name", "")
                                ref_id   = ref_id or str(off.get("id", ""))
                ref_ep_status = f"ok:{m['status_code']}"
                best_raw_file = m["raw_file"]
                best_source   = ep_name
                metrics_found = [k for k in ["startTimestamp", "refereeName", "refereeId", "statistics", "lineups"] if k in p]
                ref_metrics = list(set(ref_metrics + metrics_found))
                print(f"  {ep_name}: status={m['status_code']} ref_id={ref_id} ref_name={ref_name}")
                if ref_id:
                    break
            else:
                print(f"  {ep_name}: no payload (status={m.get('status', '')} code={m.get('status_code', '')})")
                ref_ep_status = f"no_payload:{m.get('status_code', '')}"

        # If we have a referee_id, try referee stats endpoints
        ref_stats_status = "not_attempted"
        ref_stats_metrics: list[str] = []
        if ref_id:
            for ref_ep in [
                f"referee_{ref_id}",
                f"referee_{ref_id}_statistics",
                f"referee_{ref_id}_performance",
            ]:
                path_map = {
                    f"referee_{ref_id}": f"/api/referee/{ref_id}",
                    f"referee_{ref_id}_statistics": f"/api/referee/{ref_id}/statistics",
                    f"referee_{ref_id}_performance": f"/api/referee/{ref_id}/performance",
                }
                r_url = f"{BASE}{path_map[ref_ep]}"
                rp, rm = fetch(r_url, ref_ep, min_delay=min_delay, execute=execute)
                if rp and isinstance(rp, dict):
                    ref_stats_status = f"ok:{rm['status_code']}"
                    ref_stats_metrics = list(rp.keys())[:15]
                    print(f"  {ref_ep}: ok – keys={ref_stats_metrics[:8]}")
                    break
                else:
                    ref_stats_status = f"no_payload:{rm.get('status_code', '')}"
                    print(f"  {ref_ep}: {ref_stats_status}")
        elif not ref_id and not ref_name:
            ref_stats_status = "no_referee_id_found"

        referee_results.append({
            "event_id": event_id,
            "match_name": label,
            "referee_id": ref_id,
            "referee_name": ref_name,
            "source_endpoint": best_source,
            "raw_file": best_raw_file,
            "referee_endpoint_status": ref_ep_status,
            "available_referee_metrics": json.dumps(ref_metrics),
            "referee_stats_status": ref_stats_status,
            "referee_stats_metrics": json.dumps(ref_stats_metrics),
            "notes": f"inline_stats={json.dumps(inline_ref_stats)}" if inline_ref else "",
        })

    # persist
    with get_connection() as conn:
        conn.execute("DELETE FROM statshub_match_referees WHERE snapshot_name=?", (SNAPSHOT_NAME,))
        for r in referee_results:
            conn.execute("""
                INSERT INTO statshub_match_referees
                    (snapshot_name, event_id, match_name, referee_id, referee_name,
                     source_endpoint, raw_file, referee_endpoint_status,
                     available_referee_metrics, notes, imported_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (SNAPSHOT_NAME, r["event_id"], r["match_name"], r["referee_id"], r["referee_name"],
                  r["source_endpoint"], r["raw_file"], r["referee_endpoint_status"],
                  r["available_referee_metrics"], r["notes"], utc_now()))

    return referee_results

# ── Phase 4: player ID mapping ────────────────────────────────────────────────

def _name_variants(player_name: str, team_name: str) -> list[str]:
    """Generate up to 8 query variants for a player."""
    parts = norm(player_name).split()
    seen: list[str] = []
    def add(q: str) -> None:
        q = q.strip()
        if q and q not in seen:
            seen.append(q)

    add(player_name)                               # 1. exact
    add(f"{player_name} {team_name}")             # 2. name + team
    n = norm(player_name)
    add(n)                                         # 3. normalized (no accents)
    add(f"{n} {norm(team_name)}")                 # 4. normalized + team
    if len(parts) >= 2:
        add(f"{parts[0]} {parts[-1]}")            # 5. first + last
        add(f"{parts[-1]} {team_name}")           # 6. last + team
    if len(parts) >= 3:
        add(f"{parts[0]} {parts[1]}")             # 7. first two tokens
    if len(parts) >= 2:
        add(parts[-1])                            # 8. last name only (fallback)
    return seen[:8]

def _candidate_score(player: dict, candidate: dict) -> tuple[float, list[str]]:
    score: float = 0.0
    evidence: list[str] = []
    pname = norm(player.get("player_name", ""))
    cname = norm(candidate.get("name", ""))
    if pname and cname:
        if pname == cname:
            score += 80
            evidence.append("exact name match")
        elif token_sort(player.get("player_name")) == token_sort(candidate.get("name")):
            score += 65
            evidence.append("token-sort name match")
        elif pname in cname or cname in pname:
            score += 45
            evidence.append("partial name match")
        elif any(t in cname for t in pname.split() if len(t) > 3):
            score += 25
            evidence.append("token overlap")
    team_n = norm(player.get("team_name", ""))
    country_slug = norm(candidate.get("countrySlug", ""))
    cand_team = norm(candidate.get("teamName", "") or candidate.get("team", ""))
    if team_n and (team_n == country_slug or team_n in country_slug or country_slug in team_n):
        score += 15
        evidence.append("country slug ~ team")
    if team_n and (team_n == cand_team or team_n in cand_team or cand_team in team_n):
        score += 10
        evidence.append("team name ~ candidate team")
    if candidate.get("id"):
        score += 5
        evidence.append("has id")
    return score, evidence

def _classify(player: dict, candidates: list[dict], query: str, raw_f: str) -> tuple[dict, list[dict]]:
    scored = []
    for c in candidates:
        s, ev = _candidate_score(player, c)
        if s >= 45:
            scored.append((s, c, ev))
    scored.sort(key=lambda x: x[0], reverse=True)

    cand_rows = []
    for s, c, ev in scored[:10]:
        cand_rows.append({
            "snapshot_name": SNAPSHOT_NAME, "world_cup_year": 2026,
            "team_name": player["team_name"],
            "statshub_team_id": player.get("team_id"),
            "player_name": player["player_name"],
            "player_name_canonical": norm(player["player_name"]),
            "position": player.get("position"), "jersey_number": player.get("jersey_number"),
            "candidate_player_id": str(c.get("id")) if c.get("id") else None,
            "candidate_name": c.get("name"),
            "candidate_team": c.get("teamName") or c.get("team"),
            "candidate_country": c.get("countrySlug"),
            "score": s, "evidence": "; ".join(ev),
            "source_query": query, "raw_file": raw_f, "status": "candidate",
        })

    if not scored:
        return {
            "player_id": None, "player_id_status": "unresolved",
            "confidence_score": 0, "match_method": "statshub_search",
            "match_query": query, "match_source": raw_f,
            "candidate_ids": "", "notes": "No usable candidate.",
        }, cand_rows

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

    return {
        "player_id": str(best.get("id")) if status in ("confirmed", "probable") and best.get("id") else None,
        "player_id_status": status,
        "confidence_score": best_s,
        "match_method": "statshub_search",
        "match_query": query,
        "match_source": raw_f,
        "candidate_ids": json.dumps(ids[:5]),
        "notes": f"best={best_s} second={second_s} gap={best_s-second_s:.0f} evidence=[{'; '.join(best_ev)}]",
    }, cand_rows

def _do_search(query: str, execute: bool, min_delay: float) -> tuple[Any, dict]:
    digest = hashlib.sha1(query.encode()).hexdigest()[:10]
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", norm(query))[:40].strip("_")
    ep = f"player_search_{prefix}_{digest}"
    url = f"{BASE}/api/search?q={quote_plus(query)}"
    return fetch(url, ep, min_delay=min_delay, execute=execute)

def phase4_player_id_mapping(execute: bool, min_delay: float, search_delay: float = 3.0) -> list[dict]:
    print("\n=== PHASE 4: Player ID mapping for 4 teams ===")
    target_team_ids = {t["team_id"] for t in TEAMS}

    with get_connection() as conn:
        players = [dict(r) for r in conn.execute("""
            SELECT id, team_id, team_name, player_name, player_name_canonical,
                   position, jersey_number, player_id, statshub_player_id_status,
                   player_id_confidence_score, candidate_ids
            FROM statshub_team_players
            WHERE team_id IN ({})
            ORDER BY team_name, CAST(jersey_number AS INTEGER)
        """.format(",".join("?" * len(target_team_ids))), list(target_team_ids)).fetchall()]

    print(f"  Total players in 4 teams: {len(players)}")

    searches = 0
    newly_confirmed = 0

    for p in players:
        existing_id = p.get("player_id")
        existing_status = p.get("statshub_player_id_status") or ""

        # Keep confirmed IDs (always)
        if existing_id and existing_status in ("confirmed", "skipped_existing"):
            _update_player(p["id"], {
                "player_id": existing_id,
                "player_id_status": "skipped_existing",
                "confidence_score": 100,
                "match_method": "existing",
                "match_query": "",
                "match_source": "existing statshub_team_players.player_id",
                "candidate_ids": json.dumps([existing_id]),
                "notes": "Existing confirmed player_id preserved.",
            })
            continue

        # In dry-run mode, also preserve probable/ambiguous (can't improve without API)
        if not execute and existing_id and existing_status in ("probable", "ambiguous"):
            continue

        # Try name variants up to 8 queries, stop on confirmed
        variants = _name_variants(p["player_name"], p["team_name"])
        best_result = None
        all_candidates = []
        queries_tried = []
        got_any_payload = False

        for query in variants:
            if best_result and best_result["player_id_status"] == "confirmed":
                break
            payload, meta = _do_search(query, execute=execute, min_delay=search_delay)
            searches += 1
            queries_tried.append(query)
            candidates_raw = []
            if payload and isinstance(payload, dict):
                got_any_payload = True
                candidates_raw = [c for c in (payload.get("players") or []) if isinstance(c, dict)]
            result, cand_rows = _classify(p, candidates_raw, query, meta["raw_file"])
            all_candidates.extend(cand_rows)
            if best_result is None or result["confidence_score"] > best_result["confidence_score"]:
                best_result = result

        # Don't degrade existing mapping if we got no real API responses
        if not got_any_payload:
            continue

        if best_result is None:
            best_result = {
                "player_id": None, "player_id_status": "unresolved",
                "confidence_score": 0, "match_method": "statshub_search",
                "match_query": "", "match_source": "",
                "candidate_ids": "", "notes": "No queries returned usable results.",
            }

        # Don't downgrade to unresolved if existing mapping was ambiguous/probable and new result is worse
        if (best_result["player_id_status"] == "unresolved"
                and existing_id
                and existing_status in ("ambiguous", "probable")):
            best_result["player_id_status"] = existing_status
            best_result["player_id"] = existing_id
            best_result["notes"] = (best_result.get("notes", "") or "") + " [kept existing status; new search produced no improvement]"

        best_result["match_query"] = " | ".join(queries_tried[:3])
        _update_player(p["id"], best_result)
        _insert_candidates(all_candidates)

        if best_result["player_id_status"] == "confirmed":
            newly_confirmed += 1

        if searches % 20 == 0:
            print(f"  searches done: {searches}")

    print(f"  Searches made: {searches}, newly confirmed: {newly_confirmed}")

    # Return summary per team
    with get_connection() as conn:
        summary = []
        for t in TEAMS:
            rows = [dict(r) for r in conn.execute("""
                SELECT player_name, position, jersey_number, player_id,
                       statshub_player_id_status, player_id_confidence_score,
                       player_id_match_query, candidate_ids, player_id_match_notes
                FROM statshub_team_players WHERE team_id=?
                ORDER BY CAST(jersey_number AS INTEGER)
            """, (t["team_id"],)).fetchall()]
            confirmed = sum(1 for r in rows if (r["statshub_player_id_status"] or "").lower() in ("confirmed", "skipped_existing"))
            probable  = sum(1 for r in rows if (r["statshub_player_id_status"] or "").lower() == "probable")
            ambig     = sum(1 for r in rows if (r["statshub_player_id_status"] or "").lower() == "ambiguous")
            unresolv  = len(rows) - confirmed - probable - ambig
            print(f"  {t['team_name']}: confirmed={confirmed} probable={probable} ambiguous={ambig} unresolved={unresolv}")
            for r in rows:
                summary.append({
                    "team_name": t["team_name"],
                    "statshub_team_id": t["team_id"],
                    **r,
                })
    return summary

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

def _insert_candidates(rows: list[dict]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(statshub_player_id_candidates)").fetchall()]
        for row in rows:
            insert_cols = [c for c in cols if c in row or c == "imported_at"]
            sql = f"INSERT INTO statshub_player_id_candidates ({','.join(insert_cols)}) VALUES ({','.join('?' * len(insert_cols))})"
            conn.execute(sql, [row.get(c) if c != "imported_at" else utc_now() for c in insert_cols])

# ── Phase 5: team performance ──────────────────────────────────────────────────

def _parse_team_perf_rows(payload: Any, team_id: str, team_name: str, endpoint: str) -> list[dict]:
    rows = []
    if not payload:
        return rows
    items = payload if isinstance(payload, list) else payload.get("data", payload.get("players", []))
    if not isinstance(items, list):
        return rows
    for item in items:
        if not isinstance(item, dict):
            continue
        date_v = item.get("date") or item.get("matchDate") or item.get("startDate") or ""
        rows.append({
            "team_id": team_id, "team_name": team_name, "endpoint_name": endpoint,
            "event_date": str(date_v)[:10],
            "opponent_name": (item.get("opponent") or {}).get("name", "") if isinstance(item.get("opponent"), dict) else str(item.get("opponent") or ""),
            "goals_for":       item.get("goalsFor") or item.get("goals") or item.get("goalsScored"),
            "goals_against":   item.get("goalsAgainst") or item.get("goalsConceded"),
            "xG":              item.get("xG") or item.get("expectedGoals"),
            "xGA":             item.get("xGA") or item.get("expectedGoalsAgainst"),
            "shots":           item.get("shots") or item.get("totalShots"),
            "shots_on_target": item.get("shotsOnTarget") or item.get("shotsOnGoal"),
            "fouls":           item.get("fouls") or item.get("foulsCommitted"),
            "yellow_cards":    item.get("yellowCards"),
            "red_cards":       item.get("redCards"),
            "passes":          item.get("passes") or item.get("totalPasses"),
            "accurate_passes": item.get("accuratePasses"),
            "possession":      item.get("possession") or item.get("ballPossession"),
            "corners":         item.get("corners") or item.get("cornerKicks"),
            "raw_json": json.dumps(item)[:2000],
        })
    return rows

def _aggregate_team_perf(perf_rows: list[dict], team_id: str, team_name: str, endpoint: str, raw_f: str) -> dict:
    def _safe_avg(vals: list) -> float | None:
        clean = [v for v in vals if v is not None]
        return round(sum(clean) / len(clean), 3) if clean else None

    dates = [r["event_date"] for r in perf_rows if r["event_date"]]
    competitions: set[str] = set()

    return {
        "team_id": team_id, "team_name": team_name,
        "endpoint_name": endpoint, "raw_file": raw_f,
        "source_rows": len(perf_rows),
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "competitions_detected": json.dumps(sorted(competitions)),
        "matches_in_window": len(perf_rows),
        "goals_for":        _safe_avg([r["goals_for"] for r in perf_rows]),
        "goals_against":    _safe_avg([r["goals_against"] for r in perf_rows]),
        "expected_goals":   _safe_avg([r["xG"] for r in perf_rows]),
        "expected_goals_against": _safe_avg([r["xGA"] for r in perf_rows]),
        "shots":            _safe_avg([r["shots"] for r in perf_rows]),
        "shots_on_target":  _safe_avg([r["shots_on_target"] for r in perf_rows]),
        "shots_off_target": None,
        "big_chances":      None,
        "fouls":            _safe_avg([r["fouls"] for r in perf_rows]),
        "yellow_cards":     _safe_avg([r["yellow_cards"] for r in perf_rows]),
        "red_cards":        _safe_avg([r["red_cards"] for r in perf_rows]),
        "passes":           _safe_avg([r["passes"] for r in perf_rows]),
        "accurate_passes":  _safe_avg([r["accurate_passes"] for r in perf_rows]),
        "possession_avg":   _safe_avg([r["possession"] for r in perf_rows]),
        "corners":          _safe_avg([r["corners"] for r in perf_rows]),
        "goalkeeper_saves": None,
        "final_third_entries": None,
    }

def phase5_team_performance(execute: bool, min_delay: float) -> list[dict]:
    print("\n=== PHASE 5: Team performance (limit=50) ===")
    results = []

    for t in TEAMS:
        tid  = t["team_id"]
        tname = t["team_name"]
        ep = f"team_{tid}_performance_limit50_today_probe"
        url = f"{BASE}/api/team/{tid}/performance?limit=50"

        # Check if already have aggregate data
        with get_connection() as conn:
            existing = conn.execute("""
                SELECT source_rows, date_min, date_max
                FROM statshub_team_performance_aggregates
                WHERE team_id=?
                LIMIT 1
            """, (tid,)).fetchone()

        if existing and existing["source_rows"] and existing["source_rows"] > 0:
            print(f"  {tname}: using existing aggregate (rows={existing['source_rows']} {existing['date_min']}..{existing['date_max']})")
            with get_connection() as conn:
                agg = dict(conn.execute("""
                    SELECT * FROM statshub_team_performance_aggregates WHERE team_id=? LIMIT 1
                """, (tid,)).fetchone())
            results.append(agg)
            continue

        payload, meta = fetch(url, ep, min_delay=min_delay, execute=execute)
        print(f"  {tname}: status={meta['status']} rows={meta['rows']}")

        if payload:
            perf_rows = _parse_team_perf_rows(payload, tid, tname, ep)
            agg = _aggregate_team_perf(perf_rows, tid, tname, ep, meta["raw_file"])
            agg["snapshot_name"] = SNAPSHOT_NAME

            with get_connection() as conn:
                conn.execute("DELETE FROM statshub_team_performance_events WHERE team_id=? AND endpoint_name=?", (tid, ep))
                for row in perf_rows:
                    conn.execute("""
                        INSERT INTO statshub_team_performance_events
                            (snapshot_name, team_id, team_name, endpoint_name, event_date,
                             opponent_team_name, goals_for, goals_against, expected_goals, expected_goals_against,
                             shots, shots_on_target, fouls, yellow_cards, red_cards,
                             total_passes, accurate_passes, possession_average, corners, raw_row_json, imported_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (SNAPSHOT_NAME, tid, tname, ep, row["event_date"],
                          row["opponent_name"], row["goals_for"], row["goals_against"],
                          row["xG"], row["xGA"], row["shots"], row["shots_on_target"],
                          row["fouls"], row["yellow_cards"], row["red_cards"],
                          row["passes"], row["accurate_passes"], row["possession"],
                          row["corners"], row["raw_json"], utc_now()))
                conn.execute("""
                    INSERT INTO statshub_team_performance_aggregates
                        (snapshot_name, endpoint_name, team_id, team_name,
                         source_rows, date_min, date_max, competitions_detected,
                         matches_in_window, raw_file,
                         goals_for, goals_against, expected_goals, expected_goals_against,
                         shots, shots_on_target, shots_off_target, big_chances,
                         fouls, yellow_cards, red_cards, total_passes, accurate_passes,
                         possession_average, corners, goalkeeper_saves, final_third_entries, imported_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (SNAPSHOT_NAME, ep, tid, tname,
                      agg["source_rows"], agg["date_min"], agg["date_max"],
                      agg["competitions_detected"], agg["matches_in_window"], agg["raw_file"],
                      agg["goals_for"], agg["goals_against"],
                      agg["expected_goals"], agg["expected_goals_against"],
                      agg["shots"], agg["shots_on_target"], agg["shots_off_target"],
                      agg["big_chances"], agg["fouls"], agg["yellow_cards"],
                      agg["red_cards"], agg["passes"], agg["accurate_passes"],
                      agg["possession_avg"], agg["corners"],
                      agg["goalkeeper_saves"], agg["final_third_entries"], utc_now()))
            results.append(agg)
        else:
            results.append({
                "team_id": tid, "team_name": tname,
                "source_rows": 0, "date_min": None, "date_max": None,
                "snapshot_name": SNAPSHOT_NAME,
                "notes": f"No payload: {meta['status']}",
            })

    return results

# ── Phase 6: player performance (confirmed only) ───────────────────────────────

def _parse_player_perf(payload: Any, player_id: str, player_name: str, team_name: str, endpoint: str) -> list[dict]:
    rows = []
    if not payload:
        return rows
    items = payload if isinstance(payload, list) else payload.get("data", payload.get("events", []))
    if not isinstance(items, list):
        return rows
    for item in items:
        if not isinstance(item, dict):
            continue
        # StatsHub wraps per-match stats under player_statistics_event; fall back to item
        stats = item.get("player_statistics_event") or item
        evt   = item.get("events") or {}
        # Validate player ID
        row_pid = str(stats.get("playerId") or stats.get("player_id") or "")
        if row_pid and row_pid != str(player_id):
            continue
        # Extract date from event startTimestamp (unix) or fallback strings
        ts = evt.get("startTimestamp")
        if ts:
            date_v = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            date_v = evt.get("date") or item.get("date") or item.get("matchDate") or ""
        # Tournament name
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
            "xG":              _to_xfloat(stats.get("expectedGoals") or stats.get("xG")),
            "xA":              _to_xfloat(stats.get("expectedAssists") or stats.get("xA")),
            "key_passes":      stats.get("keyPass") or stats.get("keyPasses"),
            "passes":          stats.get("totalPass") or stats.get("passes") or stats.get("totalPasses"),
            "accurate_passes": stats.get("accuratePass") or stats.get("accuratePasses"),
            "tackles":         stats.get("totalTackle") or stats.get("tackles"),
            "possession_lost": stats.get("possessionLostCtrl") or stats.get("possessionLost") or stats.get("dispossessed"),
            "raw_json": json.dumps(item)[:1000],
        })
    return rows

def _aggregate_player_perf(rows: list[dict], player_id: str, player_name: str, team_name: str, endpoint: str, raw_f: str) -> dict:
    def s(vals: list) -> float | None:
        clean = [v for v in vals if v is not None]
        return sum(clean) if clean else None

    apps = sum(1 for r in rows if (r["minutes_played"] or 0) > 0)
    dates = [r["event_date"] for r in rows if r["event_date"]]
    comps: set[str] = set()
    for r in rows:
        if r.get("tournament_name"):
            comps.add(r["tournament_name"])

    return {
        "player_id": player_id, "player_name": player_name, "team_name": team_name,
        "endpoint_name": endpoint, "raw_file": raw_f,
        "source_rows": len(rows),
        "appearances": apps,
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
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "competitions_detected": json.dumps(sorted(comps)),
    }

def phase6_player_performance(execute: bool, min_delay: float) -> dict:
    print("\n=== PHASE 6: Player performance (confirmed players only) ===")
    target_team_ids = {t["team_id"] for t in TEAMS}

    with get_connection() as conn:
        confirmed_players = [dict(r) for r in conn.execute("""
            SELECT team_id, team_name, player_id, player_name, statshub_player_id_status
            FROM statshub_team_players
            WHERE team_id IN ({})
              AND statshub_player_id_status IN ('confirmed', 'skipped_existing')
              AND player_id IS NOT NULL AND player_id != ''
            ORDER BY team_name, player_name
        """.format(",".join("?" * len(target_team_ids))), list(target_team_ids)).fetchall()]

    print(f"  Confirmed players to download: {len(confirmed_players)}")

    aggregates = []
    downloaded = 0
    skipped_cache = 0

    for p in confirmed_players:
        pid   = p["player_id"]
        pname = p["player_name"]
        tname = p["team_name"]
        ep    = f"player_{pid}_performance_limit50_today_probe"
        url   = f"{BASE}/api/player/{pid}/performance?limit=50"

        payload, meta = fetch(url, ep, min_delay=min_delay, execute=execute)
        if meta["status"] == "cached":
            skipped_cache += 1
        else:
            downloaded += 1

        if payload:
            perf_rows = _parse_player_perf(payload, pid, pname, tname, ep)
            agg = _aggregate_player_perf(perf_rows, pid, pname, tname, ep, meta["raw_file"])
            agg["snapshot_name"] = SNAPSHOT_NAME

            with get_connection() as conn:
                conn.execute("DELETE FROM statshub_player_performance_events WHERE player_id=? AND endpoint_name=?", (pid, ep))
                for row in perf_rows:
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
            aggregates.append(agg)
            print(f"  {pname} ({tname}): rows={agg['source_rows']} apps={agg['appearances']} goals={agg['goals']}")
        else:
            print(f"  {pname} ({tname}): no payload (status={meta['status']})")

    print(f"  Downloaded: {downloaded} | Cache hits: {skipped_cache}")
    return {"aggregates": aggregates, "downloaded": downloaded, "skipped_cache": skipped_cache}

# ── Phase 7: Excel export ──────────────────────────────────────────────────────

def phase7_excel(team_id_results, match_results, referee_results,
                  team_perf_results, player_mapping_results, player_perf_results) -> None:
    print(f"\n=== PHASE 7: Excel export → {OUTPUT_FILE} ===")
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    target_team_ids = {t["team_id"] for t in TEAMS}

    with get_connection() as conn:
        # today_matches
        today_matches_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM statshub_today_matches WHERE snapshot_name=?", (SNAPSHOT_NAME,)
        ).fetchall()]

        # team_id_mapping
        team_map_rows = team_id_results

        # team_stats
        team_stats_rows = []
        for t in TEAMS:
            agg = conn.execute("""
                SELECT * FROM statshub_team_performance_aggregates WHERE team_id=? LIMIT 1
            """, (t["team_id"],)).fetchone()
            if agg:
                row = dict(agg)
                row["team_name"] = t["team_name"]
                row["statshub_team_id"] = t["team_id"]
                team_stats_rows.append(row)
            else:
                team_stats_rows.append({
                    "team_name": t["team_name"], "statshub_team_id": t["team_id"],
                    "source_rows": 0, "notes": "no data",
                })

        # player mapping
        player_map_rows = [dict(r) for r in conn.execute("""
            SELECT tp.team_name, tp.player_name, tp.position, tp.jersey_number,
                   tp.player_id, tp.statshub_player_id_status AS player_id_status,
                   tp.player_id_confidence_score AS confidence_score,
                   tp.player_id_match_query AS match_query,
                   tp.candidate_ids, tp.player_id_match_notes AS notes
            FROM statshub_team_players tp
            WHERE tp.team_id IN ({})
            ORDER BY tp.team_name, CAST(tp.jersey_number AS INTEGER)
        """.format(",".join("?" * len(target_team_ids))), list(target_team_ids)).fetchall()]

        # player performance (confirmed)
        player_perf_rows = [dict(r) for r in conn.execute("""
            SELECT pa.*, tp.position
            FROM statshub_player_performance_aggregates pa
            LEFT JOIN statshub_team_players tp ON tp.player_id = pa.player_id AND tp.team_id IN ({})
            WHERE pa.snapshot_name=?
            ORDER BY pa.team_name, pa.player_name
        """.format(",".join("?" * len(target_team_ids))), list(target_team_ids) + [SNAPSHOT_NAME]).fetchall()]

        # unresolved players
        unresolved_rows = [dict(r) for r in conn.execute("""
            SELECT team_name, player_name, position, jersey_number,
                   statshub_player_id_status AS status,
                   player_id_match_query AS queries_tried,
                   candidate_ids, player_id_match_notes AS notes
            FROM statshub_team_players
            WHERE team_id IN ({})
              AND (statshub_player_id_status NOT IN ('confirmed','skipped_existing') OR statshub_player_id_status IS NULL)
            ORDER BY team_name, CAST(jersey_number AS INTEGER)
        """.format(",".join("?" * len(target_team_ids))), list(target_team_ids)).fetchall()]

        # referee review
        ref_rows = referee_results if referee_results else []

        # raw sources
        raw_sources_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM statshub_raw_sources WHERE snapshot_name=? ORDER BY id", (SNAPSHOT_NAME,)
        ).fetchall()]

    # today_matches sheet – add referee cols from referee_results
    ref_by_event = {r["event_id"]: r for r in (referee_results or [])}
    for row in today_matches_rows:
        ref = ref_by_event.get(row.get("event_id"), {})
        row["referee_name"]        = ref.get("referee_name", "")
        row["referee_id"]          = ref.get("referee_id", "")
        row["referee_stats_status"] = ref.get("referee_stats_status", "")

    data_dict = [
        {"sheet": "today_matches",                "column": "event_id",        "description": "StatsHub event ID for the match"},
        {"sheet": "today_matches",                "column": "match_label",     "description": "Human-readable match name"},
        {"sheet": "today_matches",                "column": "referee_name",    "description": "Referee name from inline event data or event endpoint"},
        {"sheet": "today_matches",                "column": "referee_stats_status", "description": "Status of referee stats endpoint call"},
        {"sheet": "team_id_mapping",              "column": "statshub_team_id","description": "Confirmed StatsHub team ID"},
        {"sheet": "team_id_mapping",              "column": "match_status",    "description": "confirmed / ambiguous / unresolved"},
        {"sheet": "player_id_mapping_4_teams",    "column": "player_id_status","description": "confirmed/probable/ambiguous/unresolved"},
        {"sheet": "player_id_mapping_4_teams",    "column": "confidence_score","description": "0–100 scoring from name matching logic"},
        {"sheet": "player_stats_confirmed_limit50","column": "appearances",    "description": "Rows where minutesPlayed > 0"},
        {"sheet": "player_stats_confirmed_limit50","column": "source_rows",    "description": "Total rows in API response (not appearances)"},
        {"sheet": "referee_review",               "column": "referee_endpoint_status", "description": "HTTP status / result of event endpoint call"},
        {"sheet": "referee_review",               "column": "available_referee_metrics", "description": "JSON list of fields found in response"},
    ]

    sheets = {
        "today_matches":                 pd.DataFrame(today_matches_rows),
        "team_id_mapping":               pd.DataFrame(team_map_rows),
        "team_stats_limit50":            pd.DataFrame(team_stats_rows),
        "player_id_mapping_4_teams":     pd.DataFrame(player_map_rows),
        "player_stats_confirmed_limit50": pd.DataFrame(player_perf_rows),
        "unresolved_players_4_teams":    pd.DataFrame(unresolved_rows),
        "referee_review":                pd.DataFrame(ref_rows),
        "raw_sources":                   pd.DataFrame(raw_sources_rows),
        "data_dictionary":               pd.DataFrame(data_dict),
    }

    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        for name, df in sheets.items():
            if df.empty:
                df = pd.DataFrame([{"note": f"No data for {name}"}])
            df.to_excel(writer, sheet_name=name[:31], index=False)

    print(f"  OK Saved: {OUTPUT_FILE}")

# ── Phase 8: final report ──────────────────────────────────────────────────────

def phase8_report(match_results, referee_results, team_id_results) -> None:
    print("\n" + "=" * 60)
    print("PHASE 8: FINAL REPORT")
    print("=" * 60)
    print(f"Snapshot: {SNAPSHOT_NAME}")
    print(f"Date:     {TODAY}")

    print("\n--- A. Match coverage ---")
    for m in match_results:
        found = m["event_id"] != "missing_event_id"
        print(f"  {m['match_label']}: event_id={'OK ' + m['event_id'] if found else 'FAIL NOT FOUND'}")

    print("\n--- B. Referee coverage ---")
    for r in referee_results or []:
        ref_found = bool(r.get("referee_name"))
        stats_ok  = "ok" in str(r.get("referee_stats_status", ""))
        print(f"  {r['match_name']}: ref={'OK ' + str(r['referee_name']) if ref_found else 'FAIL not found'} | stats={'OK' if stats_ok else 'FAIL'}")

    print("\n--- C. Team coverage ---")
    with get_connection() as conn:
        for t in TEAMS:
            agg = conn.execute("""
                SELECT source_rows, date_min, date_max
                FROM statshub_team_performance_aggregates WHERE team_id=? LIMIT 1
            """, (t["team_id"],)).fetchone()
            if agg and agg["source_rows"]:
                print(f"  {t['team_name']} (id={t['team_id']}): OK {agg['source_rows']} rows {agg['date_min']}..{agg['date_max']}")
            else:
                print(f"  {t['team_name']} (id={t['team_id']}): FAIL no performance data")

    print("\n--- D. Player ID coverage ---")
    with get_connection() as conn:
        for t in TEAMS:
            rows = conn.execute("""
                SELECT statshub_player_id_status
                FROM statshub_team_players WHERE team_id=?
            """, (t["team_id"],)).fetchall()
            statuses = [r[0] or "" for r in rows]
            confirmed = sum(1 for s in statuses if s.lower() in ("confirmed", "skipped_existing"))
            probable  = sum(1 for s in statuses if s.lower() == "probable")
            ambig     = sum(1 for s in statuses if s.lower() == "ambiguous")
            unresolv  = len(statuses) - confirmed - probable - ambig
            print(f"  {t['team_name']}: {confirmed}/26 confirmed | {probable} probable | {ambig} ambiguous | {unresolv} unresolved")

    print("\n--- E. Player stats coverage ---")
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

    print("\n--- F. Decision ---")
    with get_connection() as conn:
        total_confirmed = conn.execute("""
            SELECT COUNT(*) FROM statshub_team_players
            WHERE team_id IN ({})
              AND statshub_player_id_status IN ('confirmed','skipped_existing')
        """.format(",".join(["?"] * len(TEAMS))), [t["team_id"] for t in TEAMS]).fetchone()[0]
        total_perf = conn.execute("""
            SELECT COUNT(*) FROM statshub_player_performance_aggregates WHERE snapshot_name=?
        """, (SNAPSHOT_NAME,)).fetchone()[0]

    all_events_found = all(m["event_id"] != "missing_event_id" for m in match_results)
    any_ref = any(r.get("referee_name") for r in (referee_results or []))
    ref_stats = any("ok" in str(r.get("referee_stats_status", "")) for r in (referee_results or []))

    print(f"  Teams ready for stats review:  {'YES' if total_confirmed >= 10 else 'PARTIAL' if total_confirmed > 0 else 'NO'} ({total_confirmed}/104 players confirmed)")
    print(f"  Player stats usable:           {'YES' if total_perf >= 5 else 'PARTIAL' if total_perf > 0 else 'NO'} ({total_perf} player perf rows)")
    print(f"  Match event IDs found:         {'YES' if all_events_found else 'PARTIAL'}")
    print(f"  Referee data available:        {'YES' if any_ref else 'NO'}")
    print(f"  Referee stats endpoint:        {'YES' if ref_stats else 'NOT AVAILABLE'}")
    print(f"\n  Missing before use for betting/props:")
    if not all_events_found:
        print("    FAIL Event IDs not found – retry team events endpoints closer to match time")
    if total_confirmed < 60:
        print(f"    FAIL Player ID coverage low ({total_confirmed}/104) – manual disambiguation needed for probable/ambiguous")
    if total_perf == 0:
        print("    FAIL No player performance data – rerun Phase 6 after Phase 4 improves coverage")
    if not any_ref:
        print("    FAIL No referee data – may appear in event closer to kickoff")
    if total_confirmed >= 60 and total_perf >= 30 and all_events_found:
        print("    OK Core data sufficient for squad-level props analysis")

# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded StatsHub probe for today's 4-team matches.")
    parser.add_argument("--execute", action="store_true", help="Make live HTTP requests")
    parser.add_argument("--force", action="store_true",  help="Re-download even if cached")
    parser.add_argument("--min-delay", type=float, default=7.0, help="Seconds between requests for main endpoints (default 7)")
    parser.add_argument("--search-delay", type=float, default=3.0, help="Seconds between player search requests (default 3)")
    parser.add_argument("--phase", type=int, default=0, help="Run only a specific phase (1-8), 0=all")
    args = parser.parse_args()

    if not args.execute:
        print("DRY-RUN MODE – no HTTP requests will be made. Pass --execute to run live.")
        print(f"Snapshot: {SNAPSHOT_NAME}")
        print(f"RAW_DIR:  {RAW_DIR}")
        print(f"OUTPUT:   {OUTPUT_FILE}")
        print(f"Targets:  {[t['team_name'] for t in TEAMS]}")
        print(f"Today:    {TODAY}  startTS={TODAY_START_TS}  endTS={TODAY_END_TS}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ensure_tables()

    run_all = args.phase == 0

    # Phase 1
    team_id_results = []
    if run_all or args.phase == 1:
        team_id_results = phase1_confirm_teams()

    # Phase 2
    match_results = []
    if run_all or args.phase == 2:
        match_results = phase2_find_today_matches(args.execute, args.min_delay)

    # Phase 3
    referee_results = []
    if run_all or args.phase == 3:
        if not match_results:
            with get_connection() as conn:
                match_results = [dict(r) for r in conn.execute(
                    "SELECT * FROM statshub_today_matches WHERE snapshot_name=?", (SNAPSHOT_NAME,)
                ).fetchall()]
        referee_results = phase3_referee_data(match_results, args.execute, args.min_delay)

    # Phase 4
    player_mapping_results = []
    if run_all or args.phase == 4:
        player_mapping_results = phase4_player_id_mapping(args.execute, args.min_delay, args.search_delay)

    # Phase 5
    team_perf_results = []
    if run_all or args.phase == 5:
        team_perf_results = phase5_team_performance(args.execute, args.min_delay)

    # Phase 6
    player_perf_results: dict = {}
    if run_all or args.phase == 6:
        player_perf_results = phase6_player_performance(args.execute, args.min_delay)

    # Phase 7
    if run_all or args.phase == 7:
        if not match_results:
            with get_connection() as conn:
                match_results = [dict(r) for r in conn.execute(
                    "SELECT * FROM statshub_today_matches WHERE snapshot_name=?", (SNAPSHOT_NAME,)
                ).fetchall()]
        if not referee_results:
            with get_connection() as conn:
                referee_results = [dict(r) for r in conn.execute(
                    "SELECT * FROM statshub_match_referees WHERE snapshot_name=?", (SNAPSHOT_NAME,)
                ).fetchall()]
        if not team_id_results:
            team_id_results = phase1_confirm_teams()
        phase7_excel(team_id_results, match_results, referee_results,
                     team_perf_results, player_mapping_results, player_perf_results)

    # Phase 8
    if run_all or args.phase == 8:
        if not match_results:
            with get_connection() as conn:
                match_results = [dict(r) for r in conn.execute(
                    "SELECT * FROM statshub_today_matches WHERE snapshot_name=?", (SNAPSHOT_NAME,)
                ).fetchall()]
        if not referee_results:
            with get_connection() as conn:
                referee_results = [dict(r) for r in conn.execute(
                    "SELECT * FROM statshub_match_referees WHERE snapshot_name=?", (SNAPSHOT_NAME,)
                ).fetchall()]
        if not team_id_results:
            team_id_results = phase1_confirm_teams()
        phase8_report(match_results, referee_results, team_id_results)

if __name__ == "__main__":
    main()
