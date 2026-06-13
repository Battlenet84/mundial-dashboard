from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.connection import get_connection, init_db
from app.db.queries import utc_now
from app.external.csv_import import (
    TARGET_FIELDS,
    candidate_mapping,
    file_hash,
    load_mapping,
    map_row,
    raw_json,
    read_csv_rows,
)
from scripts.build_external_player_features import build_features


IMPORTANT = {"player_name", "team_name", "minutes"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--source", required=True, choices=["fbref", "transfermarkt", "fpl", "generic"])
    parser.add_argument("--season", required=True)
    parser.add_argument("--competition")
    parser.add_argument("--mapping")
    args = parser.parse_args()

    init_db()
    path = Path(args.csv)
    columns, rows = read_csv_rows(path)
    digest = file_hash(path)
    mapping = candidate_mapping(columns, load_mapping(args.source, args.mapping))
    missing = sorted(IMPORTANT - set(mapping))
    imported_at = utc_now()
    imported = 0
    skipped = 0

    with get_connection() as conn:
        for row in rows:
            mapped = map_row(row, mapping, args.season, args.competition)
            conn.execute(
                """
                INSERT INTO source_player_stats_raw (
                    source_name, season, competition, team_name, player_name,
                    raw_row_json, file_hash, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.source,
                    args.season,
                    args.competition,
                    mapped.get("team_name"),
                    mapped.get("player_name"),
                    raw_json(row),
                    digest,
                    imported_at,
                ),
            )
            if not mapped.get("player_name"):
                skipped += 1
                continue
            values = {
                **{field: mapped.get(field) for field in TARGET_FIELDS},
                "source_name": args.source,
                "normalized_player_name": mapped.get("normalized_player_name"),
                "raw_row_json": raw_json(row),
                "source_file_hash": digest,
                "imported_at": imported_at,
            }
            conn.execute(
                """
                INSERT INTO external_player_stats (
                    source_name, season, competition, player_name, normalized_player_name,
                    team_name, position, nationality, age, minutes, appearances, starts,
                    goals, assists, shots_total, shots_on, passes_total, passes_key,
                    fouls_committed, fouls_drawn, yellow_cards, red_cards, tackles,
                    interceptions, progressive_passes, progressive_carries, xg, npxg,
                    xa, sca, gca, raw_row_json, source_file_hash, imported_at
                ) VALUES (
                    :source_name, :season, :competition, :player_name, :normalized_player_name,
                    :team_name, :position, :nationality, :age, :minutes, :appearances, :starts,
                    :goals, :assists, :shots_total, :shots_on, :passes_total, :passes_key,
                    :fouls_committed, :fouls_drawn, :yellow_cards, :red_cards, :tackles,
                    :interceptions, :progressive_passes, :progressive_carries, :xg, :npxg,
                    :xa, :sca, :gca, :raw_row_json, :source_file_hash, :imported_at
                )
                ON CONFLICT(source_name, season, competition, player_name, team_name)
                DO UPDATE SET
                    position=excluded.position,
                    nationality=excluded.nationality,
                    age=excluded.age,
                    minutes=excluded.minutes,
                    appearances=excluded.appearances,
                    starts=excluded.starts,
                    goals=excluded.goals,
                    assists=excluded.assists,
                    shots_total=excluded.shots_total,
                    shots_on=excluded.shots_on,
                    passes_total=excluded.passes_total,
                    passes_key=excluded.passes_key,
                    fouls_committed=excluded.fouls_committed,
                    fouls_drawn=excluded.fouls_drawn,
                    yellow_cards=excluded.yellow_cards,
                    red_cards=excluded.red_cards,
                    tackles=excluded.tackles,
                    interceptions=excluded.interceptions,
                    progressive_passes=excluded.progressive_passes,
                    progressive_carries=excluded.progressive_carries,
                    xg=excluded.xg,
                    npxg=excluded.npxg,
                    xa=excluded.xa,
                    sca=excluded.sca,
                    gca=excluded.gca,
                    raw_row_json=excluded.raw_row_json,
                    source_file_hash=excluded.source_file_hash,
                    imported_at=excluded.imported_at
                """,
                values,
            )
            imported += 1
        conn.execute(
            """
            INSERT INTO external_dataset_imports (
                source_name, file_path, file_hash, detected_columns, mapped_columns,
                rows_read, rows_imported, rows_skipped, status, message, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                args.source,
                str(path),
                digest,
                json.dumps(columns, ensure_ascii=False),
                json.dumps(mapping, ensure_ascii=False),
                len(rows),
                imported,
                skipped,
                "OK" if imported else "WARNING",
                f"missing important columns: {missing}" if missing else "importado",
                imported_at,
            ),
        )

    features = build_features()
    print("IMPORT EXTERNAL PLAYER STATS")
    print("Este comando no consume API.")
    print(f"Filas leidas: {len(rows)}")
    print(f"Filas importadas: {imported}")
    print(f"Filas omitidas: {skipped}")
    print(f"Columnas importantes faltantes: {missing}")
    print(f"Features generadas: {features}")


if __name__ == "__main__":
    main()

