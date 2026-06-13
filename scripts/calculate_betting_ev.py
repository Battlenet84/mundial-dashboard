from __future__ import annotations

from app.betting.odds_driven import connect, calculate_ev, write_scores_workbook


def main() -> None:
    with connect() as con:
        summary = calculate_ev(con, replace=True)
        workbook = write_scores_workbook(con)
    print("ODDS-DRIVEN EV")
    print(f"Normalized markets: {summary['normalized']}")
    print(f"Supported markets: {summary['supported']}")
    print(f"Unsupported markets: {summary['unsupported']}")
    print(f"Unmatched selections: {summary['unmatched']}")
    print(f"EV rows calculated: {summary['ev_rows']}")
    print("Top 20 EV opportunities:")
    for row in summary["top20"]:
        print(
            f"- #{row['rank']} {row['match_name']} | {row['raw_market_name']} | "
            f"{row['selection']} @ {row['odds_decimal']} | EV={row['expected_value']} | "
            f"p={row['model_probability']} | {row['verdict']}"
        )
    print(f"Scores workbook: {workbook}")


if __name__ == "__main__":
    main()
