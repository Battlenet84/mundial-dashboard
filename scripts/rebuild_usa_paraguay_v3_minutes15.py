"""
Rebuild USA vs Paraguay EV pipeline with minutes >= 15 filter.

Does NOT call any external API.
Applies MIN_MINUTES_PLAYER = 15 filter to all player prop samples.

Usage:
    python -m scripts.rebuild_usa_paraguay_v3_minutes15
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.betting.odds_driven import (
    DB_PATH,
    MIN_MINUTES_PLAYER,
    OUT_DIR,
    calculate_ev,
    connect,
    ensure_schema,
    normalize_raw_odds,
    write_scores_workbook,
)

RUN_NAME = "usa_paraguay_live_api_odds_probe"
V3_XLSX = OUT_DIR / "usa_paraguay_live_api_odds_value_scores_v3_minutes15.xlsx"


def _counts(con) -> dict:
    def n(sql, *args):
        return con.execute(sql, args).fetchone()[0]

    return {
        "raw": n("SELECT COUNT(*) FROM betting_odds_raw WHERE run_name=?", RUN_NAME),
        "normalized": n("SELECT COUNT(*) FROM betting_odds_normalized WHERE run_name=?", RUN_NAME),
        "ev_total": n("SELECT COUNT(*) FROM betting_value_scores_new WHERE expected_value IS NOT NULL"),
        "ev_ok": n("SELECT COUNT(*) FROM betting_value_scores_new WHERE expected_value IS NOT NULL"),
        "unsupported": n("SELECT COUNT(*) FROM betting_value_scores_new WHERE verdict='UNSUPPORTED'"),
        "unmatched": n("SELECT COUNT(*) FROM betting_value_scores_new WHERE verdict='UNMATCHED'"),
        "value": n("SELECT COUNT(*) FROM betting_value_scores_new WHERE verdict='VALUE'"),
        "no_value": n("SELECT COUNT(*) FROM betting_value_scores_new WHERE verdict='NO_VALUE'"),
        "player_ev": n(
            "SELECT COUNT(*) FROM betting_value_scores_new "
            "WHERE expected_value IS NOT NULL AND minutes_filter_status='ok'"
        ),
        "player_no_valid": n(
            "SELECT COUNT(*) FROM betting_value_scores_new "
            "WHERE minutes_filter_status='no_valid_appearances'"
        ),
        "suspicious_mp": n(
            "SELECT COUNT(*) FROM betting_value_scores_new "
            "WHERE minutes_filter_status NOT IN ('ok','not_applicable','no_valid_appearances') "
            "AND minutes_filter_status IS NOT NULL"
        ),
        "zero_excluded_total": n(
            "SELECT COALESCE(SUM(excluded_zero_minutes_count),0) FROM betting_value_scores_new "
            "WHERE excluded_zero_minutes_count IS NOT NULL"
        ),
        "low_excluded_total": n(
            "SELECT COALESCE(SUM(excluded_low_minutes_count),0) FROM betting_value_scores_new "
            "WHERE excluded_low_minutes_count IS NOT NULL"
        ),
    }


def main() -> None:
    if not DB_PATH.exists():
        print(f"ERROR: DB not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    with connect() as con:
        raw_count = con.execute(
            "SELECT COUNT(*) FROM betting_odds_raw WHERE run_name=?", (RUN_NAME,)
        ).fetchone()[0]
        if raw_count == 0:
            print(f"ERROR: No raw rows for run_name='{RUN_NAME}'", file=sys.stderr)
            sys.exit(1)

        print(f"Raw rows for {RUN_NAME}: {raw_count}")
        print(f"MIN_MINUTES_PLAYER filter = {MIN_MINUTES_PLAYER}")

        # Ensure new columns exist before querying them
        ensure_schema(con)

        before = _counts(con)
        print(f"\nBefore v3 rebuild:")
        print(f"  EV rows:         {before['ev_total']}")
        print(f"  VALUE:           {before['value']}")
        print(f"  Unsupported:     {before['unsupported']}")
        print(f"  Unmatched:       {before['unmatched']}")

        print("\nNormalizing (replace=True)...")
        normalize_raw_odds(con, replace=True)

        print("Calculating EV with minutes >= 15 filter...")
        calculate_ev(con, replace=True)

        after = _counts(con)

        print(f"\nAfter v3 rebuild:")
        print(f"  EV rows:                   {after['ev_total']}")
        print(f"  VALUE:                     {after['value']}")
        print(f"  Unsupported:               {after['unsupported']}")
        print(f"  Unmatched:                 {after['unmatched']}")
        print(f"  Player props (minutes ok): {after['player_ev']}")
        print(f"  No valid appearances:      {after['player_no_valid']}")
        print(f"  Excluded zero-min rows:    {after['zero_excluded_total']}")
        print(f"  Excluded <15-min rows:     {after['low_excluded_total']}")

        print("\nWriting Excel workbook...")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        wb_path = write_scores_workbook(con)
        if wb_path and wb_path.exists():
            shutil.copy(wb_path, V3_XLSX)
            print(f"v3 Excel: {V3_XLSX}")
        else:
            print("WARNING: write_scores_workbook returned no path")

    print(f"\n=== v2 -> v3 Improvement Report (minutes >= {MIN_MINUTES_PLAYER} filter) ===")
    print(f"  EV rows:        {before['ev_total']} -> {after['ev_total']}")
    print(f"  VALUE:          {before['value']} -> {after['value']}")
    print(f"  Unsupported:    {before['unsupported']} -> {after['unsupported']}")
    print(f"  Unmatched:      {before['unmatched']} -> {after['unmatched']}")
    print(f"  Player (ok):    {before['player_ev']} -> {after['player_ev']}")
    print(f"  Zero-min excl:  {before['zero_excluded_total']} -> {after['zero_excluded_total']}")
    print("Done.")


if __name__ == "__main__":
    main()
