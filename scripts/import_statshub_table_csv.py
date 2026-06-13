from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app.db.connection import get_connection, init_db
from app.db.queries import utc_now
from app.external.csv_import import coerce_float, file_hash, normalize_name, raw_json


ALIASES = {
    "player_name": ["player", "player_name", "jugador", "name"],
    "team_name": ["team", "team_name", "equipo"],
    "opponent_name": ["opponent", "opponent_name", "rival", "opp"],
    "line": ["line", "linea", "línea"],
    "hit_rate": ["hit rate", "hit_rate", "hit%", "hit %"],
    "average_value": ["average", "avg", "average_value", "promedio"],
    "last_n_games": ["last n", "last_n_games", "games", "partidos"],
    "odds": ["odds", "cuota"],
    "stat_value": ["stat", "stat_value", "value", "valor"],
}


def pick(row: dict[str, str], field: str):
    lookup = {key.strip().lower(): key for key in row}
    for alias in ALIASES[field]:
        key = lookup.get(alias.lower())
        if key is not None:
            return row.get(key)
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--market")
    parser.add_argument("--competition")
    parser.add_argument("--season")
    args = parser.parse_args()

    init_db()
    path = Path(args.csv)
    digest = file_hash(path)
    imported_at = utc_now()
    rows_read = 0
    rows_imported = 0
    rows_skipped = 0

    with path.open(newline="", encoding="utf-8-sig") as handle, get_connection() as conn:
        reader = csv.DictReader(handle)
        detected_columns = list(reader.fieldnames or [])
        for row in reader:
            rows_read += 1
            player_name = pick(row, "player_name")
            if not player_name:
                rows_skipped += 1
                continue
            payload = {
                "source_name": "statshub",
                "season": args.season,
                "competition": args.competition,
                "market": args.market,
                "player_name": player_name,
                "team_name": pick(row, "team_name"),
                "opponent_name": pick(row, "opponent_name"),
                "line": coerce_float(pick(row, "line")),
                "hit_rate": coerce_float(str(pick(row, "hit_rate") or "").replace("%", "")),
                "average_value": coerce_float(pick(row, "average_value")),
                "last_n_games": int(coerce_float(pick(row, "last_n_games")) or 0) or None,
                "odds": pick(row, "odds"),
                "stat_value": coerce_float(pick(row, "stat_value")),
                "raw_row_json": raw_json(row),
                "imported_at": imported_at,
            }
            conn.execute(
                """
                INSERT INTO statshub_prop_stats (
                    source_name, season, competition, market, player_name, team_name,
                    opponent_name, line, hit_rate, average_value, last_n_games,
                    odds, stat_value, raw_row_json, imported_at
                ) VALUES (
                    :source_name, :season, :competition, :market, :player_name, :team_name,
                    :opponent_name, :line, :hit_rate, :average_value, :last_n_games,
                    :odds, :stat_value, :raw_row_json, :imported_at
                )
                """,
                payload,
            )
            conn.execute(
                """
                INSERT INTO source_player_stats_raw (
                    source_name, season, competition, team_name, player_name,
                    raw_row_json, file_hash, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "statshub",
                    args.season,
                    args.competition,
                    payload["team_name"],
                    player_name,
                    raw_json(row),
                    digest,
                    imported_at,
                ),
            )
            rows_imported += 1
        conn.execute(
            """
            INSERT INTO external_dataset_imports (
                source_name, file_path, file_hash, detected_columns, mapped_columns,
                rows_read, rows_imported, rows_skipped, status, message, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "statshub",
                str(path),
                digest,
                json.dumps(detected_columns, ensure_ascii=False),
                json.dumps(ALIASES, ensure_ascii=False),
                rows_read,
                rows_imported,
                rows_skipped,
                "OK" if rows_imported else "WARNING",
                "importacion manual StatsHub",
                imported_at,
            ),
        )

    print("IMPORT STATSHUB CSV")
    print("Este comando no consume API.")
    print(f"Filas leidas: {rows_read}")
    print(f"Filas importadas: {rows_imported}")
    print(f"Filas omitidas: {rows_skipped}")
    print("StatsHub no esta configurado como API. Solo se usan datos guardados/importados manualmente.")


if __name__ == "__main__":
    main()

