from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

from app.config.settings import ROOT_DIR


SNAPSHOT_NAME = "mexico_alexis_season_depth_probe"
BASE = "https://www.statshub.com"


def build_url(path: str, params: dict[str, object] | None = None) -> str:
    query = urlencode({key: value for key, value in (params or {}).items() if value is not None})
    return f"{BASE}{path}" + (f"?{query}" if query else "")


def endpoint_plan() -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []

    for entity, entity_id in [("team", "4781"), ("player", "815637")]:
        path = f"/api/{entity}/{entity_id}/performance"
        variants = [
            ("base", {}),
            ("limit50", {"limit": 50}),
            ("limit100", {"limit": 100}),
            ("page1", {"page": 1}),
            ("page2", {"page": 2}),
            ("offset0_limit50", {"offset": 0, "limit": 50}),
            ("offset10_limit50", {"offset": 10, "limit": 50}),
            ("offset50_limit50", {"offset": 50, "limit": 50}),
        ]
        for suffix, params in variants:
            urls.append((f"{entity}_{entity_id}_performance_{suffix}", build_url(path, params)))

    mexico_tournaments = {
        "16": [58210, 41087],
        "851": [87155, 69578],
        "14100": [61662],
        "140": [50492],
        "133": [57114],
    }
    alexis_tournaments = {
        "16": [58210],
        "851": [87155, 69578],
        "11620": [87699, 70096],
        "11621": [76500, 61419],
        "14100": [61662],
        "13783": [72227],
    }

    for tournament_id, season_ids in mexico_tournaments.items():
        urls.append(
            (
                f"team_4781_performance_t{tournament_id}_limit50",
                build_url("/api/team/4781/performance", {"tournamentId": tournament_id, "limit": 50}),
            )
        )
        urls.append(
            (
                f"team_4781_performance_ut{tournament_id}_limit50",
                build_url("/api/team/4781/performance", {"uniqueTournamentId": tournament_id, "limit": 50}),
            )
        )
        for season_id in season_ids[:1]:
            urls.append(
                (
                    f"team_4781_performance_t{tournament_id}_s{season_id}_limit50",
                    build_url(
                        "/api/team/4781/performance",
                        {"tournamentId": tournament_id, "seasonId": season_id, "limit": 50},
                    ),
                )
            )

    for tournament_id, season_ids in alexis_tournaments.items():
        urls.append(
            (
                f"player_815637_performance_t{tournament_id}_limit50",
                build_url("/api/player/815637/performance", {"tournamentId": tournament_id, "limit": 50}),
            )
        )
        urls.append(
            (
                f"player_815637_performance_ut{tournament_id}_limit50",
                build_url("/api/player/815637/performance", {"uniqueTournamentId": tournament_id, "limit": 50}),
            )
        )
        for season_id in season_ids[:1]:
            urls.append(
                (
                    f"player_815637_performance_t{tournament_id}_s{season_id}_limit50",
                    build_url(
                        "/api/player/815637/performance",
                        {"tournamentId": tournament_id, "seasonId": season_id, "limit": 50},
                    ),
                )
            )

    return urls


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max planned endpoints. 0 means all.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    plan = endpoint_plan()
    if args.limit:
        plan = plan[: args.limit]

    env = os.environ.copy()
    env["STATSHUB_ENABLED"] = "true"
    env.setdefault("STATSHUB_MIN_SECONDS_BETWEEN_REQUESTS", "7")
    env.setdefault("STATSHUB_CACHE_ENABLED", "true")
    env.setdefault("STATSHUB_MAX_REQUESTS_PER_RUN", "1")

    print("STATSHUB DEPTH PROBE")
    print("Snapshot:", SNAPSHOT_NAME)
    print("Endpoints planned:", len(plan))
    print("Execute:", "yes" if args.execute else "no")
    print("Scope: Mexico team 4781 + Alexis Vega player 815637 only")

    for index, (endpoint_name, url) in enumerate(plan, start=1):
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
        ]
        if args.execute:
            command.append("--execute")
        if args.force:
            command.append("--force")
        result = subprocess.run(command, cwd=ROOT_DIR, env=env, capture_output=True, text=True, check=False)
        lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
        tail = " | ".join(lines[-5:])
        print(f"{index}/{len(plan)} {endpoint_name}: code={result.returncode} {tail}")
        if result.returncode != 0:
            continue


if __name__ == "__main__":
    main()
