"""
Probe StatsHub fixture/event endpoints to extract player IDs directly from JSON.

Approach: test /api/fixture/{id}/... and /api/event/{id}/... endpoints plus
          static HTML __NEXT_DATA__ before falling back to Playwright.

Snapshot: today_fixture_endpoint_player_links_probe

Usage:
  python -m scripts.probe_fixture_endpoint_player_links             # dry-run
  python -m scripts.probe_fixture_endpoint_player_links --execute   # live
  python -m scripts.probe_fixture_endpoint_player_links --execute --task 1   # single task
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

# ── constants ──────────────────────────────────────────────────────────────────

SNAPSHOT_NAME = "today_fixture_endpoint_player_links_probe"
BASE          = "https://www.statshub.com"
RAW_DIR       = ROOT_DIR / "data" / "raw" / "statshub" / "snapshots" / SNAPSHOT_NAME
OUTPUT_FILE   = ROOT_DIR / "data" / "processed" / "statshub" / "today_fixture_endpoint_player_links_review.xlsx"

HEADERS_JSON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.statshub.com/",
}
HEADERS_HTML = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.statshub.com/",
}

FIXTURES = [
    {
        "fixture_id":    "157344",
        "event_id":      "15186873",
        "label":         "USA vs Paraguay",
        "home_team_id":  "4724",
        "home_team_name":"United States",
        "away_team_id":  "4789",
        "away_team_name":"Paraguay",
        "slug":          "usa-vs-paraguay-mqazwt",
        "public_url":    "https://www.statshub.com/es/fixture/usa-vs-paraguay-mqazwt/157344",
    },
    {
        "fixture_id":    "157343",
        "event_id":      "15186836",
        "label":         "Canada vs Bosnia and Herzegovina",
        "home_team_id":  "4752",
        "home_team_name":"Canada",
        "away_team_id":  "4479",
        "away_team_name":"Bosnia and Herzegovina",
        "slug":          "canada-vs-bosnia-and-herzegovina-mqazwx",
        "public_url":    "https://www.statshub.com/es/fixture/canada-vs-bosnia-and-herzegovina-mqazwx/157343",
    },
]

TEAM_IDS = {"4724", "4789", "4752", "4479"}

COVERAGE_BEFORE = {
    "Canada":                 {"confirmed": 10, "probable": 15, "ambiguous": 0, "unresolved": 1},
    "Bosnia and Herzegovina": {"confirmed": 25, "probable": 0,  "ambiguous": 0, "unresolved": 1},
    "United States":          {"confirmed": 2,  "probable": 0,  "ambiguous": 0, "unresolved": 24},
    "Paraguay":               {"confirmed": 7,  "probable": 17, "ambiguous": 1, "unresolved": 1},
}

# Endpoint patterns to test per fixture
# Each entry: (name_suffix, path_template) where {fid}=fixture_id, {eid}=event_id
ENDPOINT_PATTERNS_FIXTURE = [
    ("player_statistics",  "/api/fixture/{fid}/player-statistics"),
    ("players",            "/api/fixture/{fid}/players"),
    ("lineups",            "/api/fixture/{fid}/lineups"),
    ("statistics",         "/api/fixture/{fid}/statistics"),
    ("summary",            "/api/fixture/{fid}/summary"),
    ("details",            "/api/fixture/{fid}/details"),
    ("base",               "/api/fixture/{fid}"),
]
ENDPOINT_PATTERNS_EVENT = [
    ("player_statistics",  "/api/event/{eid}/player-statistics"),
    ("players",            "/api/event/{eid}/players"),
    ("lineups",            "/api/event/{eid}/lineups"),
    ("statistics",         "/api/event/{eid}/statistics"),
    ("summary",            "/api/event/{eid}/summary"),
    ("details",            "/api/event/{eid}/details"),
    ("base",               "/api/event/{eid}"),
]

# ── helpers ────────────────────────────────────────────────────────────────────

def norm(v: str | None) -> str:
    if not v:
        return ""
    t = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()

def token_sort(v: str | None) -> str:
    return " ".join(sorted(norm(v).split()))

def to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def raw_file(endpoint: str, suffix: str = "json") -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR / f"{endpoint}.{suffix}"

def fetch_json(url: str, endpoint: str, min_delay: float, execute: bool) -> tuple[Any, dict]:
    target = raw_file(endpoint, "json")
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
        r = requests.get(url, headers=HEADERS_JSON, timeout=20)
        text = r.text
        p = None
        try:
            p = json.loads(text)
        except Exception:
            pass
        suffix = "json" if p is not None else "txt"
        target2 = raw_file(endpoint, suffix)
        target2.write_text(text, encoding="utf-8")
        status = classify_response(r.status_code, r.headers.get("content-type", ""), text, p)
        meta = {"endpoint": endpoint, "url": url, "status_code": r.status_code,
                "raw_file": str(target2), "status": status, "rows": rows_detected(p) if p else 0}
        _record_source(endpoint, url, meta, p)
        return p, meta
    except Exception as exc:
        t2 = raw_file(endpoint, "txt")
        t2.write_text(f"error: {exc}", encoding="utf-8")
        return None, {"endpoint": endpoint, "url": url, "status_code": None,
                      "raw_file": str(t2), "status": "error", "rows": 0}

def fetch_html(url: str, endpoint: str, min_delay: float, execute: bool) -> tuple[str | None, dict]:
    target = raw_file(endpoint, "html")
    if target.exists():
        html = target.read_text(encoding="utf-8", errors="replace")
        return html, {"endpoint": endpoint, "url": url, "status_code": "cached",
                      "raw_file": str(target), "status": "cached",
                      "rows": len(re.findall(r'/player/', html))}
    if not execute:
        return None, {"endpoint": endpoint, "url": url, "status_code": "dry_run",
                      "raw_file": str(target), "status": "dry_run", "rows": 0}
    time.sleep(min_delay)
    try:
        r = requests.get(url, headers=HEADERS_HTML, timeout=30)
        html = r.text
        target.write_text(html, encoding="utf-8")
        status = "ok" if r.status_code == 200 else f"http_{r.status_code}"
        meta = {"endpoint": endpoint, "url": url, "status_code": r.status_code,
                "raw_file": str(target), "status": status,
                "rows": len(re.findall(r'/player/', html))}
        _record_source(endpoint, url, meta, None, content_type=r.headers.get("content-type", ""))
        return html, meta
    except Exception as exc:
        target.write_text(f"error: {exc}", encoding="utf-8")
        return None, {"endpoint": endpoint, "url": url, "status_code": None,
                      "raw_file": str(target), "status": "error", "rows": 0}

def _record_source(endpoint: str, url: str, meta: dict,
                   payload: Any, content_type: str = "") -> None:
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM statshub_raw_sources WHERE snapshot_name=? AND endpoint_name=?",
                        (SNAPSHOT_NAME, endpoint)).fetchone():
            return
        conn.execute("""
            INSERT INTO statshub_raw_sources
                (snapshot_name, entity_type, endpoint_name, url, status_code,
                 content_type, response_size, top_keys, rows_detected, raw_file,
                 classification_status, notes, imported_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (SNAPSHOT_NAME, "fixture_probe", endpoint, url,
              str(meta.get("status_code", "")),
              content_type or (", ".join(top_keys(payload)[:3]) if payload else ""),
              len(json.dumps(payload).encode()) if payload else 0,
              ",".join(top_keys(payload)) if payload and isinstance(payload, dict) else "",
              meta.get("rows", 0), meta.get("raw_file", ""),
              meta.get("status", ""), "", utc_now()))

def _ensure_tables() -> None:
    init_db()
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS statshub_fixture_player_refs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT,
                match_label TEXT,
                public_fixture_id TEXT,
                api_event_id TEXT,
                source_endpoint TEXT,
                source_type TEXT,
                team_id TEXT,
                team_name TEXT,
                player_id TEXT,
                player_name TEXT,
                player_slug TEXT,
                player_href TEXT,
                section TEXT,
                extraction_confidence TEXT,
                raw_file TEXT,
                notes TEXT,
                imported_at TEXT
            )
        """)
        # Add statshub_player_id_status column to statshub_team_players if needed
        cols = {r["name"] for r in conn.execute(
            "PRAGMA table_info(statshub_team_players)").fetchall()}
        for col, typ in [
            ("player_id_confidence_score", "REAL"),
            ("player_id_match_source",     "TEXT"),
            ("player_id_match_method",     "TEXT"),
            ("player_id_match_query",      "TEXT"),
            ("player_id_match_notes",      "TEXT"),
            ("candidate_ids",              "TEXT"),
            ("updated_at",                 "TEXT"),
        ]:
            if col not in cols:
                conn.execute(f"ALTER TABLE statshub_team_players ADD COLUMN {col} {typ}")

# ── player ref extraction ──────────────────────────────────────────────────────

# Player URL patterns to detect in any string value
_PLAYER_URL_RE = re.compile(
    r'(?:https?://[^/]+)?/(?:es/)?(?:football/)?player/([^/"\s]+)/(\d+)', re.I
)

def _collect_player_refs_from_json(
        obj: Any, fixture: dict,
        section: str = "", depth: int = 0,
        home_tid: str | None = None, away_tid: str | None = None,
        current_tid: str | None = None, current_tname: str | None = None,
) -> list[dict]:
    """Recursively walk JSON tree, collecting player-like objects and URLs."""
    refs: list[dict] = []
    if depth > 20:
        return refs

    home_tid  = home_tid  or fixture["home_team_id"]
    away_tid  = away_tid  or fixture["away_team_id"]
    home_name = fixture["home_team_name"]
    away_name = fixture["away_team_name"]

    if isinstance(obj, dict):
        # Determine team context for this dict level
        local_tid   = current_tid
        local_tname = current_tname
        # Explicit team ID in this dict
        if str(obj.get("teamId", "") or obj.get("team_id", "")) == home_tid:
            local_tid, local_tname = home_tid, home_name
        elif str(obj.get("teamId", "") or obj.get("team_id", "")) == away_tid:
            local_tid, local_tname = away_tid, away_name

        # Is this a player-like object?
        pid   = obj.get("id") or obj.get("playerId") or obj.get("player_id")
        pname = obj.get("name") or obj.get("shortName") or obj.get("playerName")
        pslug = obj.get("slug") or obj.get("playerSlug")

        player_path = any(kw in section.lower() for kw in
                          ("player", "stat", "squad", "lineup", "roster", "scorer",
                           "assist", "card", "foul", "shot"))

        if (pid and pname
                and isinstance(pid, int)
                and isinstance(pname, str)
                and len(pname.strip()) > 1
                and player_path):
            refs.append({
                "player_id":   str(pid),
                "player_name": pname.strip(),
                "player_slug": pslug or "",
                "team_id":     local_tid,
                "team_name":   local_tname,
                "section":     section,
                "confidence":  "high" if (local_tid and pslug) else ("medium" if local_tid else "low"),
                "href":        f"/es/player/{pslug}/{pid}" if pslug else f"/player/{pid}",
                "source_type": "json_endpoint",
            })

        # Recurse into values, updating team context based on key names
        for k, v in obj.items():
            child_tid, child_tname = local_tid, local_tname
            lk = k.lower()
            if lk in ("hometeam", "home", "homestat", "homeplayers", "homeplayer"):
                child_tid, child_tname = home_tid, home_name
            elif lk in ("awayteam", "away", "awaystat", "awayplayers", "awayplayer"):
                child_tid, child_tname = away_tid, away_name
            # Detect team object by ID field
            if isinstance(v, dict):
                vid = str(v.get("id", ""))
                if vid == home_tid:
                    child_tid, child_tname = home_tid, home_name
                elif vid == away_tid:
                    child_tid, child_tname = away_tid, away_name
            refs.extend(_collect_player_refs_from_json(
                v, fixture, f"{section}.{k}", depth + 1, home_tid, away_tid,
                child_tid, child_tname))

        # Also check all string values for player URLs
        for k, v in obj.items():
            if isinstance(v, str):
                for m in _PLAYER_URL_RE.finditer(v):
                    slug_part, pid_str = m.group(1), m.group(2)
                    refs.append({
                        "player_id":   pid_str,
                        "player_name": slug_part.replace("-", " ").title(),
                        "player_slug": slug_part,
                        "team_id":     local_tid,
                        "team_name":   local_tname,
                        "section":     f"{section}.{k}[url]",
                        "confidence":  "medium" if local_tid else "low",
                        "href":        m.group(0),
                        "source_type": "url_in_json",
                    })

    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            refs.extend(_collect_player_refs_from_json(
                item, fixture, f"{section}[{i}]", depth + 1,
                home_tid, away_tid, current_tid, current_tname))

    return refs

def _collect_player_refs_from_html(html: str, fixture: dict) -> list[dict]:
    """Parse __NEXT_DATA__ and href patterns from static HTML."""
    refs: list[dict] = []
    if not html:
        return refs

    # 1. __NEXT_DATA__ embedded JSON
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>\s*(\{.*?\})\s*</script>',
        html, re.DOTALL
    )
    if m:
        try:
            nd = json.loads(m.group(1))
            page_props = (nd.get("props") or {}).get("pageProps") or {}
            # The entire pageProps tree may contain player data
            extracted = _collect_player_refs_from_json(
                page_props, fixture, "NEXT_DATA.pageProps")
            for r in extracted:
                r["source_type"] = "embedded_json"
            refs.extend(extracted)
            print(f"    __NEXT_DATA__ parsed: {len(nd)} top keys, "
                  f"pageProps keys={list(page_props.keys())[:8]}, "
                  f"player refs found={len(extracted)}")
        except Exception as e:
            print(f"    __NEXT_DATA__ parse error: {e}")

    # 2. Any other <script> tags with JSON-like content
    for sc in re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
        if '"id"' in sc and '"name"' in sc and 'player' in sc.lower():
            # Try to find JSON blobs
            for blob in re.findall(r'\{[^{}]{50,}\}', sc):
                try:
                    d = json.loads(blob)
                    if isinstance(d, dict) and d.get("id") and d.get("name"):
                        extracted = _collect_player_refs_from_json(d, fixture, "script_json")
                        for r in extracted:
                            r["source_type"] = "embedded_json"
                        refs.extend(extracted)
                except Exception:
                    pass

    # 3. Direct href matches for player URLs
    for m2 in _PLAYER_URL_RE.finditer(html):
        slug_part = m2.group(1)
        pid_str   = m2.group(2)
        full_href = m2.group(0)
        # Try to infer team from surrounding HTML context (50 chars before href)
        ctx_start = max(0, m2.start() - 200)
        ctx = html[ctx_start:m2.start()].lower()
        tid, tname = None, None
        if fixture["home_team_name"].lower() in ctx or fixture["home_team_id"] in ctx:
            tid, tname = fixture["home_team_id"], fixture["home_team_name"]
        elif fixture["away_team_name"].lower() in ctx or fixture["away_team_id"] in ctx:
            tid, tname = fixture["away_team_id"], fixture["away_team_name"]
        refs.append({
            "player_id":   pid_str,
            "player_name": slug_part.replace("-", " ").title(),
            "player_slug": slug_part,
            "team_id":     tid,
            "team_name":   tname,
            "section":     "html_href",
            "confidence":  "medium" if tid else "low",
            "href":        full_href,
            "source_type": "static_html",
        })

    return refs

def _dedup_refs(refs: list[dict]) -> list[dict]:
    """Deduplicate by (player_id, team_id), keeping highest-confidence entry."""
    conf_order = {"high": 3, "medium": 2, "low": 1}
    best: dict[tuple, dict] = {}
    for r in refs:
        key = (r["player_id"], r.get("team_id"))
        existing = best.get(key)
        if existing is None or conf_order.get(r["confidence"], 0) > conf_order.get(existing["confidence"], 0):
            best[key] = r
    return list(best.values())

# ── roster cross-match ─────────────────────────────────────────────────────────

def _candidate_score(player_row: dict, candidate_name: str, candidate_team_id: str | None) -> tuple[float, str]:
    pname = norm(player_row.get("player_name", ""))
    cname = norm(candidate_name)
    score = 0.0
    evidence = []
    if pname and cname:
        if pname == cname:
            score += 80; evidence.append("exact")
        elif token_sort(player_row["player_name"]) == token_sort(candidate_name):
            score += 65; evidence.append("token-sort")
        elif pname in cname or cname in pname:
            score += 45; evidence.append("partial")
        else:
            pparts = [t for t in pname.split() if len(t) > 2]
            cparts = cname.split()
            overlap = sum(1 for t in pparts if t in cparts)
            if overlap >= 1:
                score += 20 + overlap * 10; evidence.append(f"token-overlap({overlap})")
    if candidate_team_id and str(player_row.get("team_id", "")) == str(candidate_team_id):
        score += 15; evidence.append("team_id_match")
    return score, "; ".join(evidence)

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
            utc_now(), row_id,
        ))

# ── player perf helpers (fixed parser) ────────────────────────────────────────

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
        date_v = (datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
                  if ts else evt.get("date") or item.get("date") or "")
        tourn = evt.get("tournament") or item.get("tournament") or {}
        rows.append({
            "player_id": player_id, "player_name": player_name, "team_name": team_name,
            "endpoint_name": endpoint, "event_date": str(date_v)[:10],
            "tournament_name": tourn.get("name", "") if isinstance(tourn, dict) else str(tourn or ""),
            "minutes_played":  stats.get("minutesPlayed") or stats.get("minutes"),
            "goals":           stats.get("goals") or stats.get("goalsScored"),
            "assists":         stats.get("goalAssist") or stats.get("assists"),
            "shots":           stats.get("shots") or stats.get("totalShots"),
            "shots_on_target": stats.get("onTargetScoringAttempt") or stats.get("shotsOnTarget"),
            "fouls":           stats.get("fouls") or stats.get("foulsCommitted"),
            "was_fouled":      stats.get("wasFouled") or stats.get("foulsSuffered"),
            "yellow_cards":    stats.get("yellowCard") or stats.get("yellowCards"),
            "red_cards":       stats.get("redCard") or stats.get("redCards"),
            "xG":              to_float(stats.get("expectedGoals") or stats.get("xG")),
            "xA":              to_float(stats.get("expectedAssists") or stats.get("xA")),
            "key_passes":      stats.get("keyPass") or stats.get("keyPasses"),
            "passes":          stats.get("totalPass") or stats.get("passes"),
            "accurate_passes": stats.get("accuratePass") or stats.get("accuratePasses"),
            "tackles":         stats.get("totalTackle") or stats.get("tackles"),
            "possession_lost": stats.get("possessionLostCtrl") or stats.get("possessionLost"),
            "raw_json":        json.dumps(item)[:1000],
        })
    return rows

def _aggregate_player_perf(rows: list[dict], player_id: str, player_name: str,
                             team_name: str, endpoint: str, raw_f: str) -> dict:
    def s(vals):
        c = [v for v in vals if v is not None]
        return sum(c) if c else None
    dates = [r["event_date"] for r in rows if r["event_date"]]
    comps: set[str] = set()
    for r in rows:
        if r.get("tournament_name"):
            comps.add(r["tournament_name"])
    return {
        "player_id": player_id, "player_name": player_name, "team_name": team_name,
        "endpoint_name": endpoint, "raw_file": raw_f,
        "source_rows":     len(rows),
        "appearances":     sum(1 for r in rows if (r["minutes_played"] or 0) > 0),
        "minutes":         s([r["minutes_played"] for r in rows]),
        "goals":           s([r["goals"] for r in rows]),
        "assists":         s([r["assists"] for r in rows]),
        "shots":           s([r["shots"] for r in rows]),
        "shots_on_target": s([r["shots_on_target"] for r in rows]),
        "fouls":           s([r["fouls"] for r in rows]),
        "was_fouled":      s([r["was_fouled"] for r in rows]),
        "yellow_cards":    s([r["yellow_cards"] for r in rows]),
        "red_cards":       s([r["red_cards"] for r in rows]),
        "xG":              s([r["xG"] for r in rows]),
        "xA":              s([r["xA"] for r in rows]),
        "key_passes":      s([r["key_passes"] for r in rows]),
        "passes":          s([r["passes"] for r in rows]),
        "accurate_passes": s([r["accurate_passes"] for r in rows]),
        "tackles":         s([r["tackles"] for r in rows]),
        "possession_lost": s([r["possession_lost"] for r in rows]),
        "date_min":        min(dates) if dates else None,
        "date_max":        max(dates) if dates else None,
        "competitions_detected": json.dumps(sorted(comps)),
    }

# ── tasks ──────────────────────────────────────────────────────────────────────

def task1_probe_endpoints(execute: bool, min_delay: float) -> list[dict]:
    print("\n=== TASK 1: Probe fixture/event endpoints ===")
    results: list[dict] = []

    for fix in FIXTURES:
        fid, eid = fix["fixture_id"], fix["event_id"]
        label = fix["label"]
        print(f"\n  [{label}] fixture_id={fid} event_id={eid}")

        # Test event endpoints
        for suffix, path_tmpl in ENDPOINT_PATTERNS_EVENT:
            path = path_tmpl.format(eid=eid)
            url  = f"{BASE}{path}"
            ep   = f"event_{eid}_{suffix}"
            payload, meta = fetch_json(url, ep, min_delay, execute)
            useful = payload is not None and isinstance(payload, dict)
            n_keys = len(payload) if useful else 0
            status_str = f"{meta['status_code']}"
            print(f"    event/{eid}/{suffix}: {status_str} keys={n_keys if useful else '-'}")
            results.append({
                "fixture_label": label, "id_type": "event", "id_value": eid,
                "suffix": suffix, "endpoint": ep, "url": url,
                "status_code": meta["status_code"], "status": meta["status"],
                "rows": meta.get("rows", 0), "useful": useful,
                "raw_file": meta["raw_file"], "payload": payload,
                "top_keys": list(payload.keys())[:10] if useful else [],
            })

        # Test fixture endpoints
        for suffix, path_tmpl in ENDPOINT_PATTERNS_FIXTURE:
            path = path_tmpl.format(fid=fid)
            url  = f"{BASE}{path}"
            ep   = f"fixture_{fid}_{suffix}"
            payload, meta = fetch_json(url, ep, min_delay, execute)
            useful = payload is not None and isinstance(payload, dict)
            n_keys = len(payload) if useful else 0
            status_str = f"{meta['status_code']}"
            print(f"    fixture/{fid}/{suffix}: {status_str} keys={n_keys if useful else '-'}")
            results.append({
                "fixture_label": label, "id_type": "fixture", "id_value": fid,
                "suffix": suffix, "endpoint": ep, "url": url,
                "status_code": meta["status_code"], "status": meta["status"],
                "rows": meta.get("rows", 0), "useful": useful,
                "raw_file": meta["raw_file"], "payload": payload,
                "top_keys": list(payload.keys())[:10] if useful else [],
            })

        # Static HTML page
        ep_html = f"public_fixture_{fid}_html"
        html, meta_html = fetch_html(fix["public_url"], ep_html, min_delay, execute)
        useful_html = html is not None and len(html) > 1000
        print(f"    HTML {fix['public_url']}: {meta_html['status_code']} "
              f"size={len(html) if html else 0} player_url_hits={meta_html.get('rows',0)}")
        results.append({
            "fixture_label": label, "id_type": "html", "id_value": fid,
            "suffix": "public_html", "endpoint": ep_html, "url": fix["public_url"],
            "status_code": meta_html["status_code"], "status": meta_html["status"],
            "rows": meta_html.get("rows", 0), "useful": useful_html,
            "raw_file": meta_html["raw_file"], "payload": html,
            "top_keys": [],
        })

    return results

def task2_extract_player_refs(probe_results: list[dict]) -> list[dict]:
    print("\n=== TASK 2: Extract player references ===")
    all_refs: list[dict] = []

    for res in probe_results:
        if not res["useful"] or res["payload"] is None:
            continue
        fixture = next(f for f in FIXTURES if f["label"] == res["fixture_label"])

        if res["id_type"] == "html":
            refs = _collect_player_refs_from_html(res["payload"], fixture)
        else:
            refs = _collect_player_refs_from_json(
                res["payload"], fixture, section=res["suffix"])

        # Attach source metadata
        for r in refs:
            r["match_label"]   = fixture["label"]
            r["fixture_id"]    = fixture["fixture_id"]
            r["event_id"]      = fixture["event_id"]
            r["source_ep"]     = res["endpoint"]
            r["raw_file"]      = res["raw_file"]
            r.setdefault("team_id", None)
            r.setdefault("team_name", None)

        if refs:
            print(f"  {res['endpoint']}: {len(refs)} raw refs")
        all_refs.extend(refs)

    deduped = _dedup_refs(all_refs)
    print(f"\n  Total raw refs: {len(all_refs)} → deduplicated: {len(deduped)}")

    # Show breakdown by fixture and team
    for fix in FIXTURES:
        fix_refs = [r for r in deduped if r["match_label"] == fix["label"]]
        home_refs = [r for r in fix_refs if r.get("team_id") == fix["home_team_id"]]
        away_refs = [r for r in fix_refs if r.get("team_id") == fix["away_team_id"]]
        unassigned = [r for r in fix_refs if not r.get("team_id")]
        print(f"  {fix['label']}: {len(fix_refs)} total "
              f"| {fix['home_team_name']}={len(home_refs)} "
              f"| {fix['away_team_name']}={len(away_refs)} "
              f"| unassigned={len(unassigned)}")

    # Persist to DB
    with get_connection() as conn:
        conn.execute("DELETE FROM statshub_fixture_player_refs WHERE snapshot_name=?",
                     (SNAPSHOT_NAME,))
        for r in deduped:
            conn.execute("""
                INSERT INTO statshub_fixture_player_refs
                    (snapshot_name, match_label, public_fixture_id, api_event_id,
                     source_endpoint, source_type, team_id, team_name,
                     player_id, player_name, player_slug, player_href,
                     section, extraction_confidence, raw_file, notes, imported_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (SNAPSHOT_NAME, r["match_label"], r["fixture_id"], r["event_id"],
                  r["source_ep"], r["source_type"],
                  r.get("team_id"), r.get("team_name"),
                  r["player_id"], r["player_name"], r.get("player_slug", ""),
                  r.get("href", ""), r.get("section", ""),
                  r.get("confidence", ""), r.get("raw_file", ""), "", utc_now()))

    return deduped

def task3_crossmatch_roster(refs: list[dict], execute: bool, min_delay: float) -> list[dict]:
    print("\n=== TASK 3 & 4: Cross-match to roster + update player IDs ===")

    with get_connection() as conn:
        roster = [dict(r) for r in conn.execute("""
            SELECT id, team_id, team_name, player_id, player_name,
                   player_name_canonical, statshub_player_id_status,
                   player_id_confidence_score
            FROM statshub_team_players
            WHERE team_id IN ({})
            ORDER BY team_name, player_name
        """.format(",".join("?" * len(TEAM_IDS))), list(TEAM_IDS)).fetchall()]

    crossmatch_rows: list[dict] = []
    newly_confirmed  = 0
    fixture_only: list[dict] = []

    # For each fixture ref, try to match to a roster player
    for ref in refs:
        if not ref.get("team_id") or not ref.get("player_id"):
            # Unassigned refs — keep for fixture_only
            fixture_only.append({**ref, "reason": "no_team_assignment"})
            continue

        ref_pid   = ref["player_id"]
        ref_name  = ref["player_name"]
        ref_tid   = ref["team_id"]
        ref_label = ref["match_label"]

        # Find candidates in the same team
        team_roster = [p for p in roster if p["team_id"] == ref_tid]
        if not team_roster:
            fixture_only.append({**ref, "reason": "team_not_in_roster"})
            continue

        # Score against all roster players in this team
        scored: list[tuple[float, dict, str]] = []
        for rp in team_roster:
            s, ev = _candidate_score(rp, ref_name, ref_tid)
            if s >= 30:
                scored.append((s, rp, ev))
        scored.sort(key=lambda x: x[0], reverse=True)

        if not scored:
            fixture_only.append({**ref,
                "reason": f"no_roster_match (ref_name={ref_name!r})"})
            continue

        best_s, best_rp, best_ev = scored[0]
        second_s = scored[1][0] if len(scored) > 1 else 0.0

        existing_status = best_rp.get("statshub_player_id_status") or ""

        # Don't overwrite already-confirmed IDs unless clearly wrong
        if existing_status in ("confirmed", "skipped_existing"):
            if best_rp.get("player_id") and best_rp["player_id"] != ref_pid:
                crossmatch_rows.append({
                    "team_name": ref.get("team_name"), "fifa_name": best_rp["player_name"],
                    "fixture_name": ref_name, "player_id": ref_pid,
                    "status": "conflict_existing_confirmed",
                    "method": "fixture_link", "confidence": best_s,
                    "notes": f"existing={best_rp['player_id']} fixture={ref_pid}",
                })
            else:
                crossmatch_rows.append({
                    "team_name": ref.get("team_name"), "fifa_name": best_rp["player_name"],
                    "fixture_name": ref_name, "player_id": ref_pid,
                    "status": "already_confirmed_match",
                    "method": "fixture_link", "confidence": best_s, "notes": best_ev,
                })
            continue

        # Determine new status
        if best_s >= 75 and (best_s - second_s) >= 10:
            new_status = "confirmed"
        elif best_s >= 60 and len(scored) == 1:
            new_status = "confirmed"
        elif best_s >= 55:
            new_status = "probable"
        elif (best_s - second_s) < 10 and len(scored) > 1:
            new_status = "ambiguous"
        else:
            new_status = "probable" if best_s >= 40 else "unresolved"

        crossmatch_rows.append({
            "team_name": ref.get("team_name"), "fifa_name": best_rp["player_name"],
            "fixture_name": ref_name, "player_id": ref_pid,
            "status": new_status, "method": "fixture_link_href",
            "confidence": best_s, "notes": best_ev,
        })

        if new_status == "confirmed":
            _update_player(best_rp["id"], {
                "player_id":        ref_pid,
                "player_id_status": "confirmed",
                "confidence_score": best_s,
                "match_source":     f"fixture_link:{ref_label}",
                "match_method":     "fixture_link_href",
                "match_query":      ref.get("href", ""),
                "notes":            f"fixture_link name={ref_name!r} score={best_s} {best_ev}",
                "candidate_ids":    json.dumps([ref_pid]),
            })
            newly_confirmed += 1
            print(f"  CONFIRM {best_rp['player_name']} ({ref.get('team_name')}): "
                  f"id={ref_pid} score={best_s:.0f} via {ref['source_ep']}")
        elif new_status == "probable" and existing_status != "probable":
            _update_player(best_rp["id"], {
                "player_id":        ref_pid,
                "player_id_status": "probable",
                "confidence_score": best_s,
                "match_source":     f"fixture_link:{ref_label}",
                "match_method":     "fixture_link_href",
                "match_query":      ref.get("href", ""),
                "notes":            f"fixture_link name={ref_name!r} score={best_s} {best_ev}",
                "candidate_ids":    json.dumps([ref_pid]),
            })

    print(f"\n  Crossmatch: {len(crossmatch_rows)} entries | Newly confirmed: {newly_confirmed}")
    print(f"  Fixture-only (unmatched): {len(fixture_only)}")

    return crossmatch_rows, fixture_only, newly_confirmed

def task5_profile_validate(execute: bool, min_delay: float) -> int:
    print("\n=== TASK 5: Profile validation for newly extracted IDs ===")
    # Get recently updated players (updated in this session)
    with get_connection() as conn:
        players = [dict(r) for r in conn.execute("""
            SELECT id, team_id, team_name, player_id, player_name, statshub_player_id_status
            FROM statshub_team_players
            WHERE team_id IN ({})
              AND player_id_match_method = 'fixture_link_href'
              AND statshub_player_id_status IN ('confirmed','probable')
              AND player_id IS NOT NULL
        """.format(",".join("?" * len(TEAM_IDS))), list(TEAM_IDS)).fetchall()]

    print(f"  Players to validate: {len(players)}")
    degraded = 0

    for p in players:
        pid   = p["player_id"]
        pname = p["player_name"]
        ep    = f"player_profile_{pid}_fixture_validate"
        url   = f"{BASE}/api/player/{pid}"

        payload, meta = fetch_json(url, ep, min_delay, execute)
        if not payload or not isinstance(payload, dict):
            continue

        profile = payload.get("player") or payload
        api_name = profile.get("name") or profile.get("fullName") or ""
        if not api_name:
            continue

        s, ev = _candidate_score(p, api_name, p["team_id"])
        if s < 30 and p["statshub_player_id_status"] == "confirmed":
            # Profile strongly contradicts — downgrade
            _update_player(p["id"], {
                "player_id":        pid,
                "player_id_status": "ambiguous",
                "confidence_score": s,
                "match_source":     "profile_validate_contradiction",
                "match_method":     "profile_validation",
                "match_query":      url,
                "notes":            f"CONTRADICTION profile_name={api_name!r} score={s}",
                "candidate_ids":    json.dumps([pid]),
            })
            degraded += 1
            print(f"  DEGRADE {pname}: profile name={api_name!r} score={s:.0f}")
        else:
            print(f"  OK {pname}: profile name={api_name!r} score={s:.0f}")

    print(f"  Validated: {len(players)} | Degraded: {degraded}")
    return degraded

def task6_download_performance(execute: bool, min_delay: float) -> list[dict]:
    print("\n=== TASK 6: Download performance for newly confirmed players ===")
    ORIG_SNAPSHOT = "today_canada_bosnia_usa_paraguay_probe"

    with get_connection() as conn:
        new_players = [dict(r) for r in conn.execute("""
            SELECT tp.id, tp.team_id, tp.team_name, tp.player_id, tp.player_name
            FROM statshub_team_players tp
            WHERE tp.team_id IN ({})
              AND tp.player_id_match_method = 'fixture_link_href'
              AND tp.statshub_player_id_status = 'confirmed'
              AND tp.player_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM statshub_player_performance_aggregates pa
                WHERE pa.player_id = tp.player_id
                  AND pa.snapshot_name IN (?, ?)
              )
        """.format(",".join("?" * len(TEAM_IDS))),
            list(TEAM_IDS) + [ORIG_SNAPSHOT, SNAPSHOT_NAME]).fetchall()]

    print(f"  New confirmed players without performance: {len(new_players)}")
    aggregates: list[dict] = []

    for p in new_players:
        pid, pname, tname = p["player_id"], p["player_name"], p["team_name"]
        ep  = f"player_{pid}_performance_limit50_fixture_probe"
        url = f"{BASE}/api/player/{pid}/performance?limit=50"

        payload, meta = fetch_json(url, ep, min_delay, execute)
        rows = _parse_player_perf(payload, pid, pname, tname, ep) if payload else []
        agg  = _aggregate_player_perf(rows, pid, pname, tname, ep, meta["raw_file"])
        agg["snapshot_name"] = SNAPSHOT_NAME

        with get_connection() as conn:
            conn.execute("DELETE FROM statshub_player_performance_events "
                         "WHERE player_id=? AND endpoint_name=?", (pid, ep))
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
            conn.execute("DELETE FROM statshub_player_performance_aggregates "
                         "WHERE player_id=? AND snapshot_name=?", (pid, SNAPSHOT_NAME))
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
        print(f"  {pname} ({tname}): status={meta['status']} rows={agg['source_rows']} apps={agg['appearances']}")

    if not new_players:
        print("  No new confirmed players to download performance for.")
    return aggregates

def task7_excel(probe_results, all_refs, crossmatch_rows, fixture_only, perf_aggs) -> None:
    print(f"\n=== TASK 7: Generate Excel → {OUTPUT_FILE} ===")

    # Sheet 1: endpoint discovery
    ep_rows = [{
        "endpoint":         r["endpoint"],
        "fixture":          r["fixture_label"],
        "id_type":          r["id_type"],
        "id_value":         r["id_value"],
        "status_code":      r["status_code"],
        "status":           r["status"],
        "rows_detected":    r["rows"],
        "top_keys":         ",".join(r["top_keys"]),
        "useful":           r["useful"],
        "raw_file":         r["raw_file"],
    } for r in probe_results]

    # Sheet 2: fixture player refs
    ref_rows = [{
        "match_name":        r["match_label"],
        "api_event_id":      r["event_id"],
        "public_fixture_id": r["fixture_id"],
        "team_name":         r.get("team_name", ""),
        "team_id":           r.get("team_id", ""),
        "player_name":       r["player_name"],
        "player_id":         r["player_id"],
        "player_slug":       r.get("player_slug", ""),
        "player_href":       r.get("href", ""),
        "source_endpoint":   r.get("source_ep", ""),
        "source_type":       r.get("source_type", ""),
        "section":           r.get("section", ""),
        "confidence":        r.get("confidence", ""),
    } for r in all_refs]

    # Sheet 3: roster crossmatch
    cm_rows = crossmatch_rows or []

    # Sheet 4: updated coverage
    with get_connection() as conn:
        cov_rows = []
        for t_info in [
            ("Canada", "4752"), ("Bosnia and Herzegovina", "4479"),
            ("United States", "4724"), ("Paraguay", "4789"),
        ]:
            tname, tid = t_info
            statuses = [r[0] or "" for r in conn.execute(
                "SELECT statshub_player_id_status FROM statshub_team_players WHERE team_id=?",
                (tid,)).fetchall()]
            conf  = sum(1 for s in statuses if s in ("confirmed","skipped_existing"))
            prob  = sum(1 for s in statuses if s == "probable")
            ambig = sum(1 for s in statuses if s == "ambiguous")
            unres = len(statuses) - conf - prob - ambig
            b = COVERAGE_BEFORE.get(tname, {})
            cov_rows.append({
                "team_name":          tname,
                "confirmed_before":   b.get("confirmed", 0),
                "confirmed_after":    conf,
                "newly_confirmed":    conf - b.get("confirmed", 0),
                "probable":           prob,
                "ambiguous":          ambig,
                "unresolved":         unres,
                "coverage_pct":       f"{conf/26*100:.0f}%",
            })

    # Sheet 5: newly downloaded performance
    perf_rows = [{
        "team_name":       a["team_name"], "player_name": a["player_name"],
        "player_id":       a["player_id"], "source_rows": a["source_rows"],
        "appearances":     a["appearances"], "minutes": a["minutes"],
        "goals":           a["goals"], "assists": a["assists"],
        "shots":           a["shots"], "shots_on_target": a["shots_on_target"],
        "fouls":           a["fouls"], "was_fouled": a["was_fouled"],
        "yellow_cards":    a["yellow_cards"], "red_cards": a["red_cards"],
        "xG":              a["xG"], "xA": a["xA"],
        "date_min":        a["date_min"], "date_max": a["date_max"],
    } for a in (perf_aggs or [])]

    # Sheet 6: fixture-only players
    fo_rows = [{
        "team_name":   r.get("team_name", ""),
        "player_name": r["player_name"],
        "player_id":   r["player_id"],
        "href":        r.get("href", ""),
        "reason":      r.get("reason", ""),
        "notes":       r.get("notes", ""),
    } for r in (fixture_only or [])]

    # Sheet 7: raw sources
    with get_connection() as conn:
        raw_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM statshub_raw_sources WHERE snapshot_name=? ORDER BY id",
            (SNAPSHOT_NAME,)).fetchall()]

    # Sheet 8: data dictionary
    dd = [
        {"sheet": "endpoint_discovery", "column": "useful", "description": "True if response had parseable JSON"},
        {"sheet": "fixture_player_refs", "column": "confidence", "description": "high/medium/low based on team context and slug availability"},
        {"sheet": "roster_crossmatch",   "column": "status", "description": "confirmed/probable/ambiguous/unresolved/already_confirmed_match"},
        {"sheet": "updated_coverage",    "column": "newly_confirmed", "description": "Delta from fixture link extraction in this probe"},
        {"sheet": "fixture_only_players","column": "reason", "description": "Why the player was not matched to FIFA roster"},
    ]

    sheets = {
        "endpoint_discovery":               pd.DataFrame(ep_rows),
        "fixture_player_refs":              pd.DataFrame(ref_rows),
        "roster_crossmatch":                pd.DataFrame(cm_rows),
        "updated_coverage":                 pd.DataFrame(cov_rows),
        "newly_downloaded_player_perf":     pd.DataFrame(perf_rows),
        "fixture_only_players":             pd.DataFrame(fo_rows),
        "raw_sources":                      pd.DataFrame(raw_rows),
        "data_dictionary":                  pd.DataFrame(dd),
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        for name, df in sheets.items():
            if df.empty:
                df = pd.DataFrame([{"note": f"No data for {name}"}])
            df.to_excel(writer, sheet_name=name[:31], index=False)
    print(f"  OK Saved: {OUTPUT_FILE}")

def task8_final_report(probe_results, all_refs, newly_confirmed_count) -> None:
    print("\n" + "=" * 60)
    print("TASK 8: FINAL REPORT")
    print("=" * 60)

    # A. Fixture extraction
    print("\n--- A. Fixture extraction ---")
    for fix in FIXTURES:
        res_for = [r for r in probe_results if r["fixture_label"] == fix["label"]]
        useful  = [r for r in res_for if r["useful"]]
        html_r  = next((r for r in res_for if r["id_type"] == "html"), None)
        print(f"  {fix['label']}:")
        print(f"    Public URL: {fix['public_url']}")
        print(f"    Endpoints tested: {len(res_for)} | Useful JSON: {len(useful)}")
        if html_r:
            print(f"    HTML fetch: {html_r['status_code']} size={html_r['rows']} player_url_hits")
        useful_ep = [r["endpoint"] for r in useful]
        if useful_ep:
            print(f"    Useful endpoints: {', '.join(useful_ep)}")

    print("\n  Player refs per fixture/team:")
    for fix in FIXTURES:
        fix_refs = [r for r in all_refs if r["match_label"] == fix["label"]]
        home_r = [r for r in fix_refs if r.get("team_id") == fix["home_team_id"]]
        away_r = [r for r in fix_refs if r.get("team_id") == fix["away_team_id"]]
        un_r   = [r for r in fix_refs if not r.get("team_id")]
        print(f"  {fix['label']}: {len(fix_refs)} refs "
              f"| {fix['home_team_name']}={len(home_r)} "
              f"| {fix['away_team_name']}={len(away_r)} "
              f"| unassigned={len(un_r)}")

    # B. Coverage
    print("\n--- B. Coverage improvement ---")
    with get_connection() as conn:
        for t_info in [
            ("Canada", "4752"), ("Bosnia and Herzegovina", "4479"),
            ("United States", "4724"), ("Paraguay", "4789"),
        ]:
            tname, tid = t_info
            statuses = [r[0] or "" for r in conn.execute(
                "SELECT statshub_player_id_status FROM statshub_team_players WHERE team_id=?",
                (tid,)).fetchall()]
            conf  = sum(1 for s in statuses if s in ("confirmed","skipped_existing"))
            b = COVERAGE_BEFORE.get(tname, {})
            delta = conf - b.get("confirmed", 0)
            arrow = f"+{delta}" if delta > 0 else str(delta)
            print(f"  {tname}: {b.get('confirmed',0)} → {conf}/26 ({arrow})")

    # C. Newly confirmed
    print(f"\n--- C. Newly confirmed: {newly_confirmed_count} ---")
    if newly_confirmed_count > 0:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT team_name, player_name, player_id
                FROM statshub_team_players
                WHERE team_id IN ({})
                  AND player_id_match_method = 'fixture_link_href'
                  AND statshub_player_id_status = 'confirmed'
                ORDER BY team_name, player_name
            """.format(",".join("?" * len(TEAM_IDS))), list(TEAM_IDS)).fetchall()
            for r in rows:
                print(f"  {r[0]}: {r[1]} → id={r[2]}")

    # D + E. Decision
    print("\n--- D. Performance downloads ---")
    with get_connection() as conn:
        n_perf = conn.execute(
            "SELECT COUNT(*) FROM statshub_player_performance_aggregates WHERE snapshot_name=?",
            (SNAPSHOT_NAME,)).fetchone()[0]
    print(f"  Newly downloaded in this snapshot: {n_perf}")

    print("\n--- E. Decision ---")
    with get_connection() as conn:
        for t_info in [
            ("Canada", "4752"), ("Bosnia and Herzegovina", "4479"),
            ("United States", "4724"), ("Paraguay", "4789"),
        ]:
            tname, tid = t_info
            statuses = [r[0] or "" for r in conn.execute(
                "SELECT statshub_player_id_status FROM statshub_team_players WHERE team_id=?",
                (tid,)).fetchall()]
            conf = sum(1 for s in statuses if s in ("confirmed","skipped_existing"))
            pct  = conf / 26 * 100
            if pct >= 75:
                verdict = "READY"
            elif pct >= 40:
                verdict = "PARTIAL"
            else:
                verdict = "INCOMPLETE"
            print(f"  {tname}: {conf}/26 ({pct:.0f}%) → {verdict}")

    # Did it work?
    total_new = newly_confirmed_count
    if total_new > 10:
        print("\n  Direct fixture endpoint approach: SOLVED (significant IDs extracted)")
    elif total_new > 0:
        print("\n  Direct fixture endpoint approach: PARTIAL (some IDs extracted)")
    else:
        print("\n  Direct fixture endpoint approach: INSUFFICIENT — Playwright/browser rendering may be needed")
        print("  Recommendation: use Playwright to render the fixture page and extract player links")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute",    action="store_true")
    parser.add_argument("--min-delay",  type=float, default=7.0)
    parser.add_argument("--task",       type=int, default=0)
    args = parser.parse_args()

    _ensure_tables()

    probe_results = all_refs = crossmatch_rows = fixture_only = perf_aggs = None
    newly_confirmed_count = 0

    run_all = args.task == 0

    if run_all or args.task == 1:
        probe_results = task1_probe_endpoints(args.execute, args.min_delay)

    if run_all or args.task == 2:
        if probe_results is None:
            # Reload from DB/cache
            probe_results = []
            for fix in FIXTURES:
                for suffix, path_tmpl in ENDPOINT_PATTERNS_EVENT + ENDPOINT_PATTERNS_FIXTURE:
                    eid, fid = fix["event_id"], fix["fixture_id"]
                    ep = (f"event_{eid}_{suffix}" if "{eid}" in path_tmpl
                          else f"fixture_{fid}_{suffix}")
                    rf = raw_file(ep)
                    if rf.exists():
                        try:
                            p = json.loads(rf.read_text(encoding="utf-8"))
                            probe_results.append({
                                "fixture_label": fix["label"], "id_type": "event" if "event" in ep else "fixture",
                                "id_value": eid if "event" in ep else fid,
                                "suffix": suffix, "endpoint": ep, "url": "",
                                "status_code": "cached", "status": "cached",
                                "rows": rows_detected(p), "useful": True,
                                "raw_file": str(rf), "payload": p, "top_keys": list(p.keys())[:10],
                            })
                        except Exception:
                            pass
                # HTML
                ep_html = f"public_fixture_{fix['fixture_id']}_html"
                rf_html = raw_file(ep_html, "html")
                if rf_html.exists():
                    html = rf_html.read_text(encoding="utf-8", errors="replace")
                    probe_results.append({
                        "fixture_label": fix["label"], "id_type": "html",
                        "id_value": fix["fixture_id"], "suffix": "public_html",
                        "endpoint": ep_html, "url": fix["public_url"],
                        "status_code": "cached", "status": "cached",
                        "rows": len(re.findall(r'/player/', html)), "useful": len(html) > 1000,
                        "raw_file": str(rf_html), "payload": html, "top_keys": [],
                    })
        all_refs = task2_extract_player_refs(probe_results)

    if run_all or args.task in (3, 4):
        if all_refs is None:
            with get_connection() as conn:
                all_refs = [dict(r) for r in conn.execute(
                    "SELECT * FROM statshub_fixture_player_refs WHERE snapshot_name=?",
                    (SNAPSHOT_NAME,)).fetchall()]
                # Remap DB column names to expected keys
                remapped = []
                for r in all_refs:
                    remapped.append({
                        "match_label": r.get("match_label", ""), "fixture_id": r.get("public_fixture_id", ""),
                        "event_id": r.get("api_event_id", ""), "source_ep": r.get("source_endpoint", ""),
                        "source_type": r.get("source_type", ""), "team_id": r.get("team_id"),
                        "team_name": r.get("team_name"), "player_id": r.get("player_id", ""),
                        "player_name": r.get("player_name", ""), "player_slug": r.get("player_slug", ""),
                        "href": r.get("player_href", ""), "section": r.get("section", ""),
                        "confidence": r.get("extraction_confidence", ""), "raw_file": r.get("raw_file", ""),
                    })
                all_refs = remapped
        crossmatch_rows, fixture_only, newly_confirmed_count = task3_crossmatch_roster(
            all_refs, args.execute, args.min_delay)

    if run_all or args.task == 5:
        task5_profile_validate(args.execute, args.min_delay)

    if run_all or args.task == 6:
        perf_aggs = task6_download_performance(args.execute, args.min_delay)

    if run_all or args.task == 7:
        task7_excel(probe_results or [], all_refs or [],
                    crossmatch_rows or [], fixture_only or [], perf_aggs or [])

    if run_all or args.task == 8:
        task8_final_report(probe_results or [], all_refs or [], newly_confirmed_count)


if __name__ == "__main__":
    main()
