from __future__ import annotations

from app.betting.odds_driven import connect, normalize_raw_odds


def main() -> None:
    with connect() as con:
        summary = normalize_raw_odds(con, replace=True)
    print("ODDS-DRIVEN NORMALIZE")
    print(f"Raw odds rows: {summary['raw']}")
    print(f"Normalized markets: {summary['normalized']}")
    print(f"Supported/matched markets: {summary['supported']}")
    print(f"Unsupported markets: {summary['unsupported']}")
    print(f"Unmatched selections: {summary['unmatched']}")


if __name__ == "__main__":
    main()
