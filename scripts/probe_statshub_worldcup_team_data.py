from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
from urllib.parse import urlencode

from app.config.settings import ROOT_DIR


SNAPSHOT_NAME = "world_cup_teams_limit50_probe"
BASE = "https://www.statshub.com"


def url(path: str, params: dict[str, object] | None = None) -> str:
    query = urlencode(params or {})
    return f"{BASE}{path}" + (f"?{query}" if query else "")


def teams() -> list[tuple[str, str]]:
    conn = sqlite3.connect(ROOT_DIR / "data" / "mundial.db")
    rows = conn.execute(
        """
        SELECT DISTINCT team_id, team_name
        FROM statshub_worldcup_teams
        WHERE team_id IS NOT NULL AND team_id != ''
        ORDER BY team_name
        """
    ).fetchall()
    conn.close()
    return [(str(team_id), str(team_name)) for team_id, team_name in rows]


def build_plan() -> list[tuple[str, str]]:
    plan: list[tuple[str, str]] = []
    for team_id, _team_name in teams():
        plan.append((f"team_{team_id}_performance_limit50", url(f"/api/team/{team_id}/performance", {"limit": 50})))
        for suffix, path in [
            ("players", f"/api/team/{team_id}/players"),
            ("squad", f"/api/team/{team_id}/squad"),
            ("roster", f"/api/team/{team_id}/roster"),
            ("details", f"/api/team/{team_id}"),
        ]:
            plan.append((f"team_{team_id}_{suffix}", url(path)))
    return plan


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

    plan = build_plan()
    print("STATSHUB WORLD CUP TEAM DATA PROBE")
    print("Snapshot:", SNAPSHOT_NAME)
    print("Teams:", len(teams()))
    print("Endpoints planned:", len(plan))
    print("Execute:", "yes" if args.execute else "no")
    for endpoint_name, target_url in plan:
        run_download(endpoint_name, target_url, args.execute, args.force, env)


if __name__ == "__main__":
    main()
