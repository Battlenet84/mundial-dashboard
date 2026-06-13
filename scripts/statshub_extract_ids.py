from __future__ import annotations

import argparse
import csv
from pathlib import Path

from app.config.settings import ROOT_DIR
from app.external.statshub_snapshot import extract_ids, parse_json_if_possible


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--endpoint-name")
    parser.add_argument("--csv", action="store_true")
    args = parser.parse_args()
    path = Path(args.file)
    payload = parse_json_if_possible(path.read_text(encoding="utf-8", errors="ignore"))
    if payload is None:
        raise SystemExit("JSON invalido.")
    ids = extract_ids(payload)
    print("STATSHUB EXTRACT IDS")
    print("Este comando no consume API.")
    for key in ["events", "teams", "players", "referees", "tournaments", "seasons"]:
        print(f"{key}: {len(ids[key])}")
        for item in list(ids[key].values())[:10]:
            clean = {k: v for k, v in item.items() if k != "raw"}
            print(f"- {clean}")
    if args.csv:
        out = ROOT_DIR / "data" / "external" / "statshub" / "snapshots" / f"{path.stem}_ids.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["kind", "id", "name"])
            writer.writeheader()
            for kind, rows in ids.items():
                for row in rows.values():
                    writer.writerow({
                        "kind": kind,
                        "id": row.get(f"{kind[:-1]}_id") or row.get("team_id") or row.get("player_id") or row.get("referee_id"),
                        "name": row.get("team_name") or row.get("player_name") or row.get("referee_name"),
                    })
        print(f"CSV escrito: {out}")


if __name__ == "__main__":
    main()

