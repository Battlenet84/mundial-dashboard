"""
Rebuild USA vs Paraguay betting value pipeline from existing DB raw rows.

Does NOT call any external API. Uses run_name='usa_paraguay_live_api_odds_probe'
raw rows already in betting_odds_raw.

Usage:
    python -m scripts.rebuild_usa_paraguay_v2
"""
from __future__ import annotations

import sys
from pathlib import Path

# Bootstrap project root
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.betting.odds_driven import (
    DB_PATH,
    OUT_DIR,
    calculate_ev,
    connect,
    normalize_raw_odds,
    write_scores_workbook,
)

RUN_NAME = "usa_paraguay_live_api_odds_probe"
V2_XLSX = OUT_DIR / "usa_paraguay_live_api_odds_value_scores_v2.xlsx"


def _counts(con) -> dict:
    def n(sql):
        return con.execute(sql).fetchone()[0]
    return {
        "raw": n(f"SELECT COUNT(*) FROM betting_odds_raw WHERE run_name='{RUN_NAME}'"),
        "normalized": n(f"SELECT COUNT(*) FROM betting_odds_normalized WHERE run_name='{RUN_NAME}'"),
        "ev_total": n("SELECT COUNT(*) FROM betting_value_scores_new"),
        "ev_ok": n("SELECT COUNT(*) FROM betting_value_scores_new WHERE expected_value IS NOT NULL"),
        "unsupported": n("SELECT COUNT(*) FROM betting_value_scores_new WHERE verdict='UNSUPPORTED'"),
        "unmatched": n("SELECT COUNT(*) FROM betting_value_scores_new WHERE verdict='UNMATCHED'"),
        "value": n("SELECT COUNT(*) FROM betting_value_scores_new WHERE verdict='VALUE'"),
        "no_value": n("SELECT COUNT(*) FROM betting_value_scores_new WHERE verdict='NO_VALUE'"),
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
            print(f"ERROR: No raw rows found for run_name='{RUN_NAME}'", file=sys.stderr)
            sys.exit(1)
        print(f"Found {raw_count} raw rows for {RUN_NAME}")

        before = _counts(con)
        print("Before rebuild:", before)

        print("Normalizing raw odds ...")
        normalize_raw_odds(con, replace=True)

        print("Calculating EV ...")
        calculate_ev(con, replace=True)

        after = _counts(con)
        print("After rebuild:", after)

        print("Writing Excel workbook ...")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        wb_path = write_scores_workbook(con)
        if wb_path and wb_path.exists():
            import shutil
            shutil.copy(wb_path, V2_XLSX)
            print(f"v2 Excel written to: {V2_XLSX}")
        else:
            print("WARNING: write_scores_workbook returned no path")

    print("\n=== Improvement Report ===")
    print(f"  Raw rows:        {before['raw']} -> {after['raw']} (unchanged)")
    print(f"  Normalized:      {before['normalized']} -> {after['normalized']}")
    print(f"  EV rows:         {before['ev_total']} -> {after['ev_total']}")
    print(f"  EV calculated:   {before['ev_ok']} -> {after['ev_ok']}")
    print(f"  Unsupported:     {before['unsupported']} -> {after['unsupported']}")
    print(f"  Unmatched:       {before['unmatched']} -> {after['unmatched']}")
    print(f"  VALUE bets:      {before['value']} -> {after['value']}")
    print(f"  NO_VALUE:        {before['no_value']} -> {after['no_value']}")
    print("Done.")


if __name__ == "__main__":
    main()
