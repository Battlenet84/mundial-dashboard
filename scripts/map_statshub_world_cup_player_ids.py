from __future__ import annotations

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
from app.external.statshub_snapshot import classify_response, rows_detected, top_keys, validate_statshub_url


SNAPSHOT_NAME = "world_cup_48_player_id_mapping_probe"
SQUAD_SNAPSHOT = "world_cup_48_squads_probe"
OUTPUT_FILE = Path("data/processed/statshub/world_cup_48_player_id_mapping_review.xlsx")
RAW_DIR = ROOT_DIR / "data" / "raw" / "statshub" / "snapshots" / SNAPSHOT_NAME
BASELINE_CONFIRMED_BEFORE = 46


def norm(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def token_sort_norm(value: str | None) -> str:
    return " ".join(sorted(norm(value).split()))


def endpoint_safe(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", norm(value)).strip("_")[:50]
    return f"player_search_{prefix}_{digest}"


def search_url(query: str) -> str:
    return f"https://www.statshub.com/api/search?q={quote_plus(query)}"


def snapshot_file(endpoint_name: str, suffix: str = "json") -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DIR / f"{endpoint_name}.{suffix}"


def ensure_schema() -> None:
    init_db()
    with get_connection() as conn:
        player_cols = {row["name"] for row in conn.execute("PRAGMA table_info(statshub_team_players)").fetchall()}
        required = {
            "player_id_confidence_score": "REAL",
            "player_id_match_source": "TEXT",
            "player_id_match_method": "TEXT",
            "player_id_match_query": "TEXT",
            "player_id_match_notes": "TEXT",
            "candidate_ids": "TEXT",
            "updated_at": "TEXT",
        }
        for col, typ in required.items():
            if col not in player_cols:
                conn.execute(f"ALTER TABLE statshub_team_players ADD COLUMN {col} {typ}")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS statshub_player_id_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_name TEXT,
                world_cup_year INTEGER,
                team_name TEXT,
                statshub_team_id TEXT,
                player_name TEXT,
                player_name_canonical TEXT,
                position TEXT,
                jersey_number TEXT,
                candidate_player_id TEXT,
                candidate_name TEXT,
                candidate_team TEXT,
                candidate_country TEXT,
                score REAL,
                evidence TEXT,
                source_query TEXT,
                raw_file TEXT,
                status TEXT,
                imported_at TEXT
            )
            """
        )
        raw_cols = {row["name"] for row in conn.execute("PRAGMA table_info(statshub_raw_sources)").fetchall()}
        for col, typ in {"player_name": "TEXT", "notes": "TEXT"}.items():
            if col not in raw_cols:
                conn.execute(f"ALTER TABLE statshub_raw_sources ADD COLUMN {col} {typ}")


def load_players() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, world_cup_year, team_id, team_name, player_id, player_name,
                   player_name_canonical, position, jersey_number, statshub_player_id_status,
                   player_id_confidence_score, player_id_match_source, player_id_match_method,
                   player_id_match_query, player_id_match_notes, candidate_ids
            FROM statshub_team_players
            WHERE snapshot_name = ?
            ORDER BY team_name, jersey_number + 0, player_name
            """,
            (SQUAD_SNAPSHOT,),
        ).fetchall()
    return [dict(row) for row in rows]


def existing_local_player_index() -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    with get_connection() as conn:
        queries = [
            "SELECT team_name, player_name, player_id FROM statshub_worldcup_players WHERE player_id IS NOT NULL",
            "SELECT team_name, player_name, player_id FROM statshub_raw_players WHERE player_id IS NOT NULL",
            "SELECT team_name, player_name, player_id FROM statshub_raw_worldcup_player_performance WHERE player_id IS NOT NULL",
            "SELECT team_name, player_name, player_id FROM statshub_raw_player_performance WHERE player_id IS NOT NULL",
        ]
        for query in queries:
            try:
                rows = conn.execute(query).fetchall()
            except Exception:
                continue
            for row in rows:
                team_key = norm(row["team_name"])
                name = row["player_name"]
                pid = row["player_id"]
                if not name or not pid:
                    continue
                found[(team_key, norm(name))] = str(pid)
                found[(team_key, token_sort_norm(name))] = str(pid)
    return found


def fetch_search(query: str, min_delay: float) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    url = search_url(query)
    validate_statshub_url(url)
    endpoint = endpoint_safe(query)
    target = snapshot_file(endpoint, "json")
    if target.exists():
        text = target.read_text(encoding="utf-8", errors="ignore")
        payload = json.loads(text)
        meta = {
            "endpoint_name": endpoint,
            "url": url,
            "status_code": None,
            "content_type": "application/json",
            "response_size": len(text.encode("utf-8")),
            "raw_file": str(target),
            "status": "cache_hit",
        }
        return payload, meta

    time.sleep(min_delay)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.statshub.com/",
    }
    try:
        response = requests.get(url, headers=headers, timeout=20)
        text = response.text
        payload = json.loads(text) if text.lstrip().startswith("{") else None
        status = classify_response(response.status_code, response.headers.get("content-type", ""), text, payload)
        suffix = "json" if payload is not None else "txt"
        target = snapshot_file(endpoint, suffix)
        target.write_text(text, encoding="utf-8")
        meta = {
            "endpoint_name": endpoint,
            "url": url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", ""),
            "response_size": len(response.content),
            "raw_file": str(target),
            "status": status,
        }
        return payload, meta
    except Exception as exc:
        target = snapshot_file(endpoint, "txt")
        text = f"request_error: {exc}"
        target.write_text(text, encoding="utf-8")
        return None, {
            "endpoint_name": endpoint,
            "url": url,
            "status_code": None,
            "content_type": "",
            "response_size": len(text.encode("utf-8")),
            "raw_file": str(target),
            "status": "error",
        }


def register_raw_source(meta: dict[str, Any], payload: Any, player: dict[str, Any], notes: str) -> None:
    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM statshub_raw_sources WHERE snapshot_name = ? AND endpoint_name = ? AND raw_file = ?",
            (SNAPSHOT_NAME, meta["endpoint_name"], meta["raw_file"]),
        ).fetchone()
        if exists:
            return
        conn.execute(
            """
            INSERT INTO statshub_raw_sources (
                snapshot_name, entity_type, team_id, team_name, endpoint_name, url, status_code,
                content_type, response_size, top_keys, rows_detected, raw_file,
                classification_status, player_name, notes, imported_at
            ) VALUES (?, 'player_search', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                SNAPSHOT_NAME,
                player.get("team_id"),
                player.get("team_name"),
                meta["endpoint_name"],
                meta["url"],
                meta["status_code"],
                meta["content_type"],
                meta["response_size"],
                ",".join(top_keys(payload)),
                rows_detected(payload) if payload is not None else 0,
                meta["raw_file"],
                meta["status"],
                player.get("player_name"),
                notes,
                utc_now(),
            ),
        )


def candidate_score(player: dict[str, Any], candidate: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    evidence: list[str] = []
    player_name = player["player_name"]
    cand_name = candidate.get("name") or ""
    if norm(cand_name) == norm(player_name):
        score += 70
        evidence.append("exact normalized name")
    elif token_sort_norm(cand_name) == token_sort_norm(player_name):
        score += 65
        evidence.append("token-sort name match")
    elif norm(player_name) in norm(cand_name) or norm(cand_name) in norm(player_name):
        score += 45
        evidence.append("partial name match")
    if norm(player.get("team_name")) and norm(player.get("team_name")) == norm(candidate.get("countrySlug")):
        score += 15
        evidence.append("country slug matches team")
    if candidate.get("id"):
        score += 5
        evidence.append("has player id")
    return score, evidence


def extract_candidates(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    return [item for item in (payload.get("players") or []) if isinstance(item, dict)]


def classify_candidates(player: dict[str, Any], candidates: list[dict[str, Any]], query: str, raw_file: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scored = []
    for candidate in candidates:
        score, evidence = candidate_score(player, candidate)
        if score < 45:
            continue
        scored.append((score, candidate, evidence))
    scored.sort(key=lambda item: item[0], reverse=True)
    candidate_rows = []
    for score, candidate, evidence in scored[:10]:
        candidate_rows.append(
            {
                "snapshot_name": SNAPSHOT_NAME,
                "world_cup_year": 2026,
                "team_name": player["team_name"],
                "statshub_team_id": player.get("team_id"),
                "player_name": player["player_name"],
                "player_name_canonical": player.get("player_name_canonical"),
                "position": player.get("position"),
                "jersey_number": player.get("jersey_number"),
                "candidate_player_id": str(candidate.get("id")) if candidate.get("id") is not None else None,
                "candidate_name": candidate.get("name"),
                "candidate_team": candidate.get("teamName") or candidate.get("team"),
                "candidate_country": candidate.get("countrySlug"),
                "score": score,
                "evidence": "; ".join(evidence),
                "source_query": query,
                "raw_file": raw_file,
                "status": "candidate",
            }
        )
    if not scored:
        return {
            "player_id": None,
            "player_id_status": "unresolved",
            "confidence_score": 0,
            "match_method": "statsHub_search",
            "match_query": query,
            "match_source": raw_file,
            "candidate_ids": "",
            "notes": "No usable candidate from bounded search.",
        }, candidate_rows
    best_score, best, best_evidence = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0
    ids = [str(item[1].get("id")) for item in scored if item[1].get("id") is not None]
    if best_score >= 75 and best_score - second_score >= 10:
        status = "confirmed"
    elif best_score >= 65 and len(scored) == 1:
        status = "confirmed"
    elif best_score >= 60:
        status = "probable"
    else:
        status = "ambiguous" if len(scored) > 1 else "probable"
    if len(scored) > 1 and best_score - second_score < 10:
        status = "ambiguous"
    return {
        "player_id": str(best.get("id")) if status in {"confirmed", "probable"} and best.get("id") is not None else None,
        "player_id_status": status,
        "confidence_score": best_score,
        "match_method": "statsHub_search",
        "match_query": query,
        "match_source": raw_file,
        "candidate_ids": json.dumps(ids, ensure_ascii=False),
        "notes": "; ".join(best_evidence),
    }, candidate_rows


def update_player(row_id: int, result: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
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
            """,
            (
                result.get("player_id"),
                result["player_id_status"],
                result.get("confidence_score"),
                result.get("match_source"),
                result.get("match_method"),
                result.get("match_query"),
                result.get("notes"),
                result.get("candidate_ids"),
                utc_now(),
                row_id,
            ),
        )


def insert_candidates(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with get_connection() as conn:
        cols = [row["name"] for row in conn.execute("PRAGMA table_info(statshub_player_id_candidates)").fetchall()]
        insert_cols = [col for col in cols if col in rows[0] or col == "imported_at"]
        sql = f"INSERT INTO statshub_player_id_candidates ({','.join(insert_cols)}) VALUES ({','.join('?' for _ in insert_cols)})"
        now = utc_now()
        for row in rows:
            conn.execute(sql, [row.get(col) if col != "imported_at" else now for col in insert_cols])


def run_mapping(max_searches: int, min_delay: float) -> None:
    ensure_schema()
    players = load_players()
    local_index = existing_local_player_index()
    with get_connection() as conn:
        conn.execute("DELETE FROM statshub_player_id_candidates WHERE snapshot_name = ?", (SNAPSHOT_NAME,))

    searches = 0
    for player in players:
        if player.get("player_id"):
            update_player(player["id"], {
                "player_id": player["player_id"],
                "player_id_status": "skipped_existing",
                "confidence_score": 100,
                "match_source": "existing statshub_team_players.player_id",
                "match_method": "existing",
                "match_query": "",
                "notes": "Existing confirmed player_id preserved.",
                "candidate_ids": json.dumps([player["player_id"]]),
            })
            continue
        local_key = (norm(player["team_name"]), norm(player["player_name"]))
        local_token_key = (norm(player["team_name"]), token_sort_norm(player["player_name"]))
        local_pid = local_index.get(local_key) or local_index.get(local_token_key)
        if local_pid:
            update_player(player["id"], {
                "player_id": local_pid,
                "player_id_status": "confirmed",
                "confidence_score": 95,
                "match_source": "local SQLite player registry",
                "match_method": "local_exact_or_token_name",
                "match_query": "",
                "notes": "Matched local player registry with same team/name context.",
                "candidate_ids": json.dumps([local_pid]),
            })
            continue
        if max_searches and searches >= max_searches:
            break
        query = player["player_name"]
        payload, meta = fetch_search(query, min_delay)
        searches += 1
        register_raw_source(meta, payload, player, "Exact player-name StatsHub search. No performance endpoint used.")
        result, candidate_rows = classify_candidates(player, extract_candidates(payload), query, meta["raw_file"])
        if result["player_id_status"] == "unresolved":
            query2 = f"{player['player_name']} {player['team_name']}"
            payload2, meta2 = fetch_search(query2, min_delay)
            searches += 1
            register_raw_source(meta2, payload2, player, "Player-name plus team StatsHub search. No performance endpoint used.")
            result2, candidate_rows2 = classify_candidates(player, extract_candidates(payload2), query2, meta2["raw_file"])
            candidate_rows.extend(candidate_rows2)
            if result2["confidence_score"] >= result["confidence_score"]:
                result = result2
        update_player(player["id"], result)
        insert_candidates(candidate_rows)
        if searches % 50 == 0:
            print(f"searches={searches}")


def load_current_results() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT team_name, team_id AS statshub_team_id, player_name, player_name_canonical,
                   position, jersey_number, player_id, statshub_player_id_status AS player_id_status,
                   player_id_confidence_score AS confidence_score, player_id_match_method AS match_method,
                   player_id_match_query AS match_query, player_id_match_source AS match_source,
                   candidate_ids, player_id_match_notes AS notes
            FROM statshub_team_players
            WHERE snapshot_name = ?
            ORDER BY team_name, jersey_number + 0, player_name
            """,
            (SQUAD_SNAPSHOT,),
        ).fetchall()
    return [dict(row) for row in rows]


def make_excel() -> None:
    results = load_current_results()
    total = len(results)
    already = BASELINE_CONFIRMED_BEFORE
    confirmed = sum(1 for row in results if row["player_id_status"] in {"confirmed", "skipped_existing"})
    probable = sum(1 for row in results if row["player_id_status"] == "probable")
    ambiguous = sum(1 for row in results if row["player_id_status"] == "ambiguous")
    unresolved = sum(1 for row in results if row["player_id_status"] in {None, "unresolved"})
    summary = [{
        "total_players": total,
        "already_confirmed_before": already,
        "attempted_missing": total - BASELINE_CONFIRMED_BEFORE,
        "newly_confirmed": max(confirmed - already, 0),
        "probable": probable,
        "ambiguous": ambiguous,
        "unresolved": unresolved,
        "total_confirmed_after": confirmed,
        "confirmed_percentage": round((confirmed / total) * 100, 2) if total else 0,
        "notes": "Identity mapping only. No player performance endpoints called.",
    }]
    by_team = defaultdict(list)
    for row in results:
        by_team[row["team_name"]].append(row)
    team_rows = []
    for team, rows in sorted(by_team.items()):
        confirmed_team = sum(1 for row in rows if row["player_id_status"] in {"confirmed", "skipped_existing"})
        probable_team = sum(1 for row in rows if row["player_id_status"] == "probable")
        ambiguous_team = sum(1 for row in rows if row["player_id_status"] == "ambiguous")
        unresolved_team = sum(1 for row in rows if row["player_id_status"] in {None, "unresolved"})
        team_rows.append({
            "team_name": team,
            "statshub_team_id": rows[0]["statshub_team_id"],
            "total_players_expected": 26,
            "confirmed_player_ids": confirmed_team,
            "probable_player_ids": probable_team,
            "ambiguous_player_ids": ambiguous_team,
            "unresolved_player_ids": unresolved_team,
            "coverage_percentage": round((confirmed_team / 26) * 100, 2),
            "status": "complete" if confirmed_team == 26 else "partial" if confirmed_team else "missing",
            "notes": "",
        })
    with get_connection() as conn:
        candidates = [dict(row) for row in conn.execute("SELECT * FROM statshub_player_id_candidates WHERE snapshot_name = ?", (SNAPSHOT_NAME,)).fetchall()]
        raw_sources = [dict(row) for row in conn.execute("SELECT * FROM statshub_raw_sources WHERE snapshot_name = ?", (SNAPSHOT_NAME,)).fetchall()]
    sheets = {
        "mapping_summary": pd.DataFrame(summary),
        "team_mapping_coverage": pd.DataFrame(team_rows),
        "player_mapping_results": pd.DataFrame(results),
        "ambiguous_players": pd.DataFrame([row for row in results if row["player_id_status"] == "ambiguous"]),
        "unresolved_players": pd.DataFrame([row for row in results if row["player_id_status"] in {None, "unresolved"}]),
        "player_id_candidates": pd.DataFrame(candidates),
        "raw_sources": pd.DataFrame(raw_sources),
    }
    sheets["data_dictionary"] = pd.DataFrame(
        [
            {"sheet_name": sheet, "column_name": col, "original_json_path": "", "inferred_type": "unknown", "meaning": "unknown", "notes": "review column"}
            for sheet, df in sheets.items()
            for col in df.columns
        ]
    )
    output = ROOT_DIR / OUTPUT_FILE
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name in ["mapping_summary", "team_mapping_coverage", "player_mapping_results", "ambiguous_players", "unresolved_players", "player_id_candidates", "raw_sources", "data_dictionary"]:
            sheets[name].to_excel(writer, sheet_name=name, index=False)
    print(f"Output file: {output}")
    for name, df in sheets.items():
        print(f"- {name}: rows={len(df)} columns={len(df.columns)}")
    print("Overall mapping")
    for key, value in summary[0].items():
        print(f"- {key}: {value}")
    print("Team coverage")
    for row in team_rows:
        print(f"- {row['team_name']}: confirmed={row['confirmed_player_ids']}/26 probable={row['probable_player_ids']} ambiguous={row['ambiguous_player_ids']} unresolved={row['unresolved_player_ids']}")
    print("Decision")
    print("- proceed_to_player_performance_for_confirmed: partial")
    print("- include_probable_automatically: no")
    print("- remaining: unresolved and ambiguous player identities")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-searches", type=int, default=0)
    parser.add_argument("--min-delay", type=float, default=0.5)
    args = parser.parse_args()
    if args.execute:
        run_mapping(args.max_searches, args.min_delay)
    make_excel()


if __name__ == "__main__":
    main()
