from __future__ import annotations

import argparse
from pathlib import Path

from app.betting.odds_driven import (
    ODDS_API_CACHE,
    connect,
    insert_raw_rows,
    raw_rows_from_manual_file,
    raw_rows_from_odds_api_cache,
    write_actual_odds_template,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest actual bookmaker odds into betting_odds_raw.")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--from-odds-api-cache", action="store_true")
    parser.add_argument("--cache-path", type=Path, default=ODDS_API_CACHE)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    template = write_actual_odds_template()
    rows = []
    if args.input:
        rows.extend(raw_rows_from_manual_file(args.input))
    if args.from_odds_api_cache:
        rows.extend(raw_rows_from_odds_api_cache(args.cache_path))

    with connect() as con:
        inserted = insert_raw_rows(con, rows, replace=args.replace)
        total = con.execute("SELECT COUNT(*) FROM betting_odds_raw").fetchone()[0]
    print("ODDS-DRIVEN INGEST")
    print(f"Template: {template}")
    print(f"Raw odds rows ingested: {inserted}")
    print(f"Raw odds rows in table: {total}")


if __name__ == "__main__":
    main()
