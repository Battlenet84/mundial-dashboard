from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
import pdfplumber
import requests

from app.config.settings import ROOT_DIR
from app.db.connection import get_connection, init_db
from app.db.queries import utc_now


SNAPSHOT_NAME = "world_cup_48_squads_probe"
PREVIOUS_SNAPSHOT = "world_cup_48_teams_limit50_probe"
OUTPUT_FILE = Path("data/processed/statshub/world_cup_48_squads_review.xlsx")
RAW_DIR = ROOT_DIR / "data" / "raw" / "statshub" / "snapshots" / SNAPSHOT_NAME
FIFA_SQUAD_PDF_URL = "https://fdp.fifa.org/assetspublic/ce281/pdf/SquadLists-English.pdf"

ALIASES_TO_TEST = {
    "Bosnia and Herzegovina": ["Bosnia and Herzegovina", "Bosnia & Herzegovina", "Bosnia", "Bosnia-Herzegovina", "BIH"],
    "Ivory Coast": ["Ivory Coast", "Cote d'Ivoire", "Cote dIvoire", "Côte dIvoire", "CIV"],
    "Congo DR": ["Congo DR", "DR Congo", "Democratic Republic of the Congo", "Democratic Republic Congo", "Congo-Kinshasa", "DRC", "COD"],
}

TEAM_NAME_ALIASES = {
    "Bosnia And Herzegovina": "Bosnia and Herzegovina",
    "Côte d'Ivoire": "Ivory Coast",
    "Côte D'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Congo DR": "Congo DR",
    "DR Congo": "Congo DR",
    "Korea Republic": "South Korea",
    "IR Iran": "Iran",
    "Türkiye": "Turkiye",
    "Turkey": "Turkiye",
    "Curaçao": "Curacao",
    "Czech Republic": "Czechia",
    "United States": "United States",
    "USA": "United States",
    "Cape Verde": "Cape Verde",
    "Cabo Verde": "Cape Verde",
}


def norm(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", "", value)


def endpoint_for_alias(alias: str) -> str:
    return "squad_search_" + re.sub(r"[^A-Za-z0-9]+", "_", norm(alias)).strip("_")


def statshub_search_url(alias: str) -> str:
    return f"https://www.statshub.com/api/search?q={quote_plus(alias)}"


def run_statshub_download(endpoint_name: str, url: str) -> None:
    env = os.environ.copy()
    env["STATSHUB_ENABLED"] = "true"
    env.setdefault("STATSHUB_MIN_SECONDS_BETWEEN_REQUESTS", "2")
    env.setdefault("STATSHUB_CACHE_ENABLED", "true")
    env.setdefault("STATSHUB_MAX_REQUESTS_PER_RUN", "1")
    command = [
        sys.executable,
        "-m",
        "scripts.download_statshub_snapshot",
        "--snapshot-name",
        SNAPSHOT_NAME,
        "--endpoint-name",
        endpoint_name,
        "--url",
        url,
        "--execute",
    ]
    result = subprocess.run(command, cwd=ROOT_DIR, env=env, capture_output=True, text=True, check=False)
    lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    print(f"{endpoint_name}: code={result.returncode} {' | '.join(lines[-4:])}")


def ensure_schema() -> None:
    init_db()
    with get_connection() as conn:
        player_cols = {row["name"] for row in conn.execute("PRAGMA table_info(statshub_team_players)").fetchall()}
        player_required = {
            "world_cup_year": "INTEGER",
            "player_name_canonical": "TEXT",
            "source": "TEXT",
            "source_confidence": "TEXT",
            "statshub_player_id_status": "TEXT",
            "squad_status": "TEXT",
            "notes": "TEXT",
        }
        for col, typ in player_required.items():
            if col not in player_cols:
                conn.execute(f"ALTER TABLE statshub_team_players ADD COLUMN {col} {typ}")
        raw_cols = {row["name"] for row in conn.execute("PRAGMA table_info(statshub_raw_sources)").fetchall()}
        if "notes" not in raw_cols:
            conn.execute("ALTER TABLE statshub_raw_sources ADD COLUMN notes TEXT")


def latest_snapshot(endpoint_name: str, snapshot_name: str = SNAPSHOT_NAME) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM statshub_snapshots
            WHERE snapshot_name = ? AND endpoint_name = ?
            ORDER BY id DESC LIMIT 1
            """,
            (snapshot_name, endpoint_name),
        ).fetchone()
    return dict(row) if row else None


def load_json_source(source: dict[str, Any] | None) -> Any | None:
    if not source or not source.get("raw_file_path"):
        return None
    path = Path(source["raw_file_path"])
    if path.suffix != ".json" or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8", errors="ignore"))


def registry_rows() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT world_cup_year, team_name, group_name, statshub_team_id, statshub_team_slug,
                   statshub_match_status, source, source_confidence, notes
            FROM statshub_world_cup_teams
            WHERE snapshot_name = ?
            ORDER BY group_name, team_name
            """,
            (PREVIOUS_SNAPSHOT,),
        ).fetchall()
    return [dict(row) for row in rows]


def resolve_missing_team(team_name: str) -> dict[str, Any]:
    aliases = ALIASES_TO_TEST[team_name]
    fixture_candidates: dict[str, dict[str, Any]] = {}
    team_candidates: dict[str, dict[str, Any]] = {}
    for alias in aliases:
        source = latest_snapshot(endpoint_for_alias(alias))
        payload = load_json_source(source)
        if not isinstance(payload, dict):
            continue
        for fixture in payload.get("fixtures", []) or []:
            if not isinstance(fixture, dict) or str(fixture.get("tournamentId")) != "16":
                continue
            for side in ["home", "away"]:
                name = fixture.get(f"{side}TeamName")
                slug = fixture.get(f"{side}TeamSlug")
                team_id = fixture.get(f"{side}TeamId")
                wanted = {norm(alias), norm(team_name), norm(TEAM_NAME_ALIASES.get(team_name, team_name))}
                if norm(name) in wanted or norm(slug) in wanted:
                    fixture_candidates[str(team_id)] = {
                        "team_id": str(team_id),
                        "team_name": name,
                        "slug": slug,
                        "source": f"/api/search?q={alias}",
                    }
        for item in payload.get("teams", []) or []:
            if not isinstance(item, dict):
                continue
            wanted = {norm(alias), norm(team_name), norm(TEAM_NAME_ALIASES.get(team_name, team_name))}
            if norm(item.get("name")) in wanted or norm(item.get("slug")) in wanted:
                team_candidates[str(item.get("id"))] = {
                    "team_id": str(item.get("id")),
                    "team_name": item.get("name"),
                    "slug": item.get("slug"),
                    "source": f"/api/search?q={alias}",
                }
    values = list(fixture_candidates.values()) or list(team_candidates.values())
    if len(values) == 1:
        status = "matched"
    elif len(values) > 1:
        status = "ambiguous"
    else:
        status = "unresolved"
    return {
        "team_name": team_name,
        "aliases_tested": json.dumps(aliases, ensure_ascii=False),
        "statshub_team_id": values[0]["team_id"] if status == "matched" else None,
        "match_status": status,
        "candidates_if_ambiguous": json.dumps(values, ensure_ascii=False) if status == "ambiguous" else "",
        "source": values[0]["source"] if values else "StatsHub search aliases",
        "notes": "" if status == "matched" else json.dumps(values, ensure_ascii=False),
        "statshub_team_slug": values[0].get("slug") if status == "matched" else None,
    }


def update_team_mapping(fixes: list[dict[str, Any]]) -> None:
    with get_connection() as conn:
        for fix in fixes:
            if fix["match_status"] == "matched":
                conn.execute(
                    """
                    UPDATE statshub_world_cup_teams
                    SET statshub_team_id = ?, statshub_team_slug = ?, statshub_match_status = 'matched',
                        source = ?, source_confidence = 'statshub_search_alias', notes = ?
                    WHERE snapshot_name = ? AND team_name = ?
                    """,
                    (
                        fix["statshub_team_id"],
                        fix["statshub_team_slug"],
                        fix["source"],
                        "Resolved in squad identity step.",
                        PREVIOUS_SNAPSHOT,
                        fix["team_name"],
                    ),
                )


def download_fifa_pdf() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / "fifa_squad_lists_official.pdf"
    if not target.exists():
        response = requests.get(FIFA_SQUAD_PDF_URL, timeout=30)
        response.raise_for_status()
        target.write_bytes(response.content)
        status_code = response.status_code
        content_type = response.headers.get("content-type", "")
        response_size = len(response.content)
    else:
        status_code = None
        content_type = "application/pdf"
        response_size = target.stat().st_size
    record_raw_source(
        endpoint_name="official_fifa_squad_lists_pdf",
        url=FIFA_SQUAD_PDF_URL,
        status_code=status_code,
        content_type=content_type,
        response_size=response_size,
        rows_detected=0,
        raw_file=str(target),
        classification_status="ok",
        notes="Official FIFA SquadLists-English.pdf used for roster identity only.",
    )
    return target


def canonical_team_name(name: str) -> str:
    return TEAM_NAME_ALIASES.get(name, name)


def parse_pdf_rows(pdf_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            team_name = None
            country_code = None
            for line in text.splitlines():
                match = re.match(r"^([A-Za-zÀ-ÖØ-öø-ÿ'’ .-]+?)\s*\(([A-Z]{3})\)$", line.strip())
                if match:
                    team_name = canonical_team_name(match.group(1).strip())
                    country_code = match.group(2)
                    break
            if not team_name:
                continue
            tables = page.extract_tables() or []
            for table in tables:
                for row in table:
                    clean = [(cell or "").strip() for cell in row]
                    if len(clean) < 4 or clean[1] not in {"GK", "DF", "MF", "FW"}:
                        continue
                    player_name = " ".join(part for part in [clean[4], clean[5]] if part).strip() or clean[2]
                    if not player_name or "PLAYER NAME" in player_name:
                        continue
                    rows.append(
                        {
                            "world_cup_year": 2026,
                            "team_name": team_name,
                            "country_code": country_code,
                            "player_name": clean_text(" ".join(player_name.split())),
                            "position": clean[1],
                            "jersey_number": clean[0],
                            "source": "official FIFA SquadLists-English.pdf",
                            "source_confidence": "confirmed",
                            "notes": "Official squad identity row. Player ID not provided by FIFA PDF.",
                        }
                    )
    return rows


def local_player_ids() -> dict[tuple[str, str], str]:
    with get_connection() as conn:
        rows = conn.execute("SELECT team_name, player_name, player_id FROM statshub_worldcup_players WHERE player_id IS NOT NULL").fetchall()
    found = {}
    for row in rows:
        found[(norm(row["team_name"]), norm(row["player_name"]))] = str(row["player_id"])
        found[(norm(row["team_name"]), token_sort_norm(row["player_name"]))] = str(row["player_id"])
    return found


def token_sort_norm(value: str | None) -> str:
    return " ".join(sorted(norm(value).split()))


def build_player_rows(registry: list[dict[str, Any]], fifa_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ids = local_player_ids()
    teams_by_name = {norm(row["team_name"]): row for row in registry}
    out = []
    for row in fifa_rows:
        team = teams_by_name.get(norm(row["team_name"]))
        team_id = team.get("statshub_team_id") if team else None
        player_id = ids.get((norm(row["team_name"]), norm(row["player_name"]))) or ids.get((norm(row["team_name"]), token_sort_norm(row["player_name"])))
        out.append(
            {
                "snapshot_name": SNAPSHOT_NAME,
                "world_cup_year": 2026,
                "team_id": team_id,
                "team_name": row["team_name"],
                "player_id": player_id,
                "player_name": row["player_name"],
                "player_name_canonical": norm(row["player_name"]),
                "position": row["position"],
                "jersey_number": row["jersey_number"],
                "source": row["source"],
                "source_confidence": row["source_confidence"],
                "statshub_player_id_status": "confirmed" if player_id else "missing",
                "squad_status": "complete",
                "notes": row["notes"],
            }
        )
    return out


def record_raw_source(
    endpoint_name: str,
    url: str,
    status_code: int | None,
    content_type: str,
    response_size: int,
    rows_detected: int,
    raw_file: str,
    classification_status: str,
    notes: str,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO statshub_raw_sources (
                snapshot_name, entity_type, endpoint_name, url, status_code, content_type,
                response_size, rows_detected, raw_file, classification_status, notes, imported_at
            ) VALUES (?, 'squad_source', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (SNAPSHOT_NAME, endpoint_name, url, status_code, content_type, response_size, rows_detected, raw_file, classification_status, notes, utc_now()),
        )


def copy_search_sources_to_raw_sources() -> None:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM statshub_snapshots WHERE snapshot_name = ? ORDER BY id", (SNAPSHOT_NAME,)).fetchall()
        for row in rows:
            exists = conn.execute(
                "SELECT 1 FROM statshub_raw_sources WHERE snapshot_name = ? AND endpoint_name = ? AND raw_file = ?",
                (SNAPSHOT_NAME, row["endpoint_name"], row["raw_file_path"]),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO statshub_raw_sources (
                    snapshot_name, entity_type, endpoint_name, url, status_code, content_type,
                    response_size, top_keys, rows_detected, raw_file, classification_status, notes, imported_at
                ) VALUES (?, 'team_search', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    SNAPSHOT_NAME,
                    row["endpoint_name"],
                    row["url"],
                    row["status_code"],
                    row["content_type"],
                    row["response_size"],
                    row["json_top_keys"],
                    row["rows_detected"],
                    row["raw_file_path"],
                    row["status"],
                    "StatsHub bounded search for unresolved team ID mapping.",
                    utc_now(),
                ),
            )


def insert_players(players: list[dict[str, Any]]) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM statshub_team_players WHERE snapshot_name = ?", (SNAPSHOT_NAME,))
        table_cols = [row["name"] for row in conn.execute("PRAGMA table_info(statshub_team_players)").fetchall()]
        cols = [col for col in table_cols if col in players[0] or col == "imported_at"]
        sql = f"INSERT INTO statshub_team_players ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
        now = utc_now()
        for row in players:
            conn.execute(sql, [row.get(col) if col != "imported_at" else now for col in cols])


def squad_coverage(registry: list[dict[str, Any]], players: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_team = defaultdict(list)
    for player in players:
        by_team[player["team_name"]].append(player)
    rows = []
    for team in registry:
        team_players = by_team.get(team["team_name"], [])
        found = len(team_players)
        with_id = sum(1 for player in team_players if player.get("player_id"))
        if found >= 26:
            status = "complete"
        elif found > 0:
            status = "partial"
        else:
            status = "missing"
        rows.append(
            {
                "team_name": team["team_name"],
                "statshub_team_id": team.get("statshub_team_id"),
                "expected_players": 26,
                "players_found": found,
                "players_with_statshub_id": with_id,
                "squad_status": status,
                "source": "official FIFA SquadLists-English.pdf" if found else "",
                "source_confidence": "confirmed" if found else "",
                "notes": "" if found >= 26 else "Fewer than 26 players found from official squad source.",
            }
        )
    return rows


def raw_sources_df() -> pd.DataFrame:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT endpoint_name, url, status_code, content_type, response_size, rows_detected,
                   raw_file, classification_status, notes
            FROM statshub_raw_sources
            WHERE snapshot_name = ?
            ORDER BY id
            """,
            (SNAPSHOT_NAME,),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def data_dictionary(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    meanings = {
        "team_name": "World Cup team name",
        "statshub_team_id": "StatsHub team identifier when mapped",
        "player_name": "official player name",
        "player_id": "StatsHub player identifier when locally confirmed",
        "position": "FIFA listed position",
        "source": "identity data source",
        "source_confidence": "confidence in source",
        "squad_status": "complete, partial, or missing",
    }
    rows = []
    for sheet_name, df in sheets.items():
        if sheet_name == "data_dictionary":
            continue
        for column in df.columns:
            rows.append(
                {
                    "sheet_name": sheet_name,
                    "column_name": column,
                    "original_json_path": "",
                    "inferred_type": "null" if df[column].dropna().empty else type(df[column].dropna().iloc[0]).__name__,
                    "meaning": meanings.get(column, "unknown"),
                    "notes": "" if column in meanings else "unknown; preserved for review",
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    ensure_schema()
    if args.execute:
        for aliases in ALIASES_TO_TEST.values():
            for alias in aliases:
                run_statshub_download(endpoint_for_alias(alias), statshub_search_url(alias))

    fixes = [resolve_missing_team(team_name) for team_name in ALIASES_TO_TEST]
    update_team_mapping(fixes)
    registry = registry_rows()
    pdf_path = download_fifa_pdf()
    fifa_rows = parse_pdf_rows(pdf_path)
    players = build_player_rows(registry, fifa_rows)
    if players:
        insert_players(players)
    copy_search_sources_to_raw_sources()

    coverage = squad_coverage(registry, players)
    partial = [row for row in coverage if row["players_found"] < 26]

    sheets = {
        "team_mapping_fix": pd.DataFrame(fixes),
        "squad_coverage": pd.DataFrame(coverage),
        "team_players": pd.DataFrame(players),
        "unresolved_or_partial_squads": pd.DataFrame(partial),
        "raw_sources": raw_sources_df(),
    }
    sheets["data_dictionary"] = data_dictionary(sheets)

    output = ROOT_DIR / OUTPUT_FILE
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet in ["team_mapping_fix", "squad_coverage", "team_players", "unresolved_or_partial_squads", "raw_sources", "data_dictionary"]:
            sheets[sheet].to_excel(writer, sheet_name=sheet, index=False)

    complete = sum(1 for row in coverage if row["squad_status"] == "complete")
    partial_count = sum(1 for row in coverage if row["squad_status"] == "partial")
    missing = sum(1 for row in coverage if row["squad_status"] == "missing")
    with_ids = sum(1 for row in players if row.get("player_id"))
    mapped = sum(1 for row in registry if row.get("statshub_team_id"))
    print(f"Output file: {output}")
    for name, df in sheets.items():
        print(f"- {name}: rows={len(df)} columns={len(df.columns)}")
    print("Missing team ID resolution")
    for fix in fixes:
        print(f"- {fix['team_name']}: {fix['match_status']} {fix.get('statshub_team_id') or ''}")
    print("Squad coverage")
    print("- Expected teams: 48")
    print("- Expected players per team: 26")
    print("- Expected total player rows: 1248")
    print(f"- Teams with complete 26-player squad: {complete}")
    print(f"- Teams with partial squad: {partial_count}")
    print(f"- Teams with missing squad: {missing}")
    print(f"- Total player rows collected: {len(players)}")
    print(f"- Player rows with confirmed StatsHub player_id: {with_ids}")
    print(f"- Player rows missing StatsHub player_id: {len(players) - with_ids}")
    print("Decision")
    print(f"- all_48_teams_mapped_to_statshub_ids: {'yes' if mapped == 48 else 'partial'}")
    print(f"- have_26_player_names_for_every_team: {'yes' if complete == 48 else 'partial'}")
    print(f"- player_ids_confirmed_for_all_players: {'yes' if with_ids == len(players) and players else 'partial'}")
    print("- can_proceed_later_to_player_performance_downloads: partial")


if __name__ == "__main__":
    main()
