from __future__ import annotations

import argparse
import os
import subprocess
import sys
from urllib.parse import urlencode

from app.config.settings import ROOT_DIR


SNAPSHOT_NAME = "world_cup_teams_limit50_probe"
BASE = "https://www.statshub.com"


def url(path: str, params: dict[str, object] | None = None) -> str:
    query = urlencode(params or {})
    return f"{BASE}{path}" + (f"?{query}" if query else "")


def discovery_plan() -> list[tuple[str, str]]:
    return [
        ("world_cup_kickoff", url("/api/world-cup/kickoff")),
        ("tournament_16", url("/api/tournament/16")),
        ("tournament_16_seasons", url("/api/tournament/16/seasons")),
        ("tournament_16_teams", url("/api/tournament/16/teams")),
        ("tournament_16_teams_s58210", url("/api/tournament/16/teams", {"seasonId": 58210})),
        ("tournament_16_season_58210_teams", url("/api/tournament/16/season/58210/teams")),
        ("tournament_16_season_58210_events", url("/api/tournament/16/season/58210/events")),
        ("tournament_16_events_s58210", url("/api/tournament/16/events", {"seasonId": 58210})),
        ("unique_tournament_16_season_58210_teams", url("/api/unique-tournament/16/season/58210/teams")),
        ("unique_tournament_16_season_58210_events", url("/api/unique-tournament/16/season/58210/events")),
    ]


def run_download(endpoint_name: str, target_url: str, execute: bool, force: bool, env: dict[str, str]) -> int:
    command = [
        sys.executable,
        "-m",
        "scripts.download_statshub_snapshot",
        "--snapshot-name",
        SNAPSHOT_NAME,
        "--endpoint-name",
        endpoint_name,
        "--url",
        target_url,
    ]
    if execute:
        command.append("--execute")
    if force:
        command.append("--force")
    result = subprocess.run(command, cwd=ROOT_DIR, env=env, capture_output=True, text=True, check=False)
    lines = [line for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    print(f"{endpoint_name}: code={result.returncode} {' | '.join(lines[-5:])}")
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    env = os.environ.copy()
    env["STATSHUB_ENABLED"] = "true"
    env.setdefault("STATSHUB_MIN_SECONDS_BETWEEN_REQUESTS", "7")
    env.setdefault("STATSHUB_CACHE_ENABLED", "true")
    env.setdefault("STATSHUB_MAX_REQUESTS_PER_RUN", "1")

    print("STATSHUB WORLD CUP TEAM DISCOVERY")
    print("Snapshot:", SNAPSHOT_NAME)
    print("Execute:", "yes" if args.execute else "no")
    for endpoint_name, target_url in discovery_plan():
        run_download(endpoint_name, target_url, args.execute, args.force, env)


if __name__ == "__main__":
    main()
