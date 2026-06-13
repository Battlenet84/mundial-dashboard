import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.external.statshub_snapshot import validate_statshub_url


ROOT = Path(__file__).resolve().parents[1]


def run_with_temp_db(command, tmp_path, extra_env=None):
    env = os.environ.copy()
    env["DB_PATH"] = str(tmp_path / "test_mundial.db")
    env.update(extra_env or {})
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)


def test_plan_statshub_snapshot_consumes_zero_api(tmp_path):
    result = run_with_temp_db(
        [sys.executable, "-m", "scripts.plan_statshub_snapshot", "--date", "2026-06-11"],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Este comando no consume API." in result.stdout
    assert "download_statshub_snapshot" in result.stdout


def test_download_statshub_dry_run_makes_no_external_request(tmp_path):
    result = run_with_temp_db(
        [
            sys.executable,
            "-m",
            "scripts.download_statshub_snapshot",
            "--snapshot-name",
            "test",
            "--endpoint-name",
            "world_cup_kickoff",
            "--url",
            "https://www.statshub.com/api/world-cup/kickoff",
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "no hizo request externo" in result.stdout


def test_download_execute_refuses_when_disabled(tmp_path):
    result = run_with_temp_db(
        [
            sys.executable,
            "-m",
            "scripts.download_statshub_snapshot",
            "--snapshot-name",
            "test",
            "--endpoint-name",
            "world_cup_kickoff",
            "--url",
            "https://www.statshub.com/api/world-cup/kickoff",
            "--execute",
        ],
        tmp_path,
        {"STATSHUB_ENABLED": "false"},
    )
    assert result.returncode != 0
    assert "StatsHub deshabilitado" in (result.stdout + result.stderr)


def test_statshub_url_validation_refuses_non_host_and_sensitive_params():
    with pytest.raises(ValueError):
        validate_statshub_url("https://example.com/api/world-cup/kickoff")
    with pytest.raises(ValueError):
        validate_statshub_url("https://www.statshub.com/api/world-cup/kickoff?token=secret")


def test_inspect_and_import_statshub_snapshot_offline(tmp_path):
    payload = {"data": [{"id": 1, "playerName": "Test Player", "teamName": "ARG", "statType": "shots"}]}
    json_path = tmp_path / "snapshot.json"
    json_path.write_text(json.dumps(payload), encoding="utf-8")

    inspect = run_with_temp_db(
        [sys.executable, "-m", "scripts.inspect_statshub_snapshot", "--file", str(json_path)],
        tmp_path,
    )
    assert inspect.returncode == 0, inspect.stderr
    assert "Este comando no consume API." in inspect.stdout
    assert "rows=1" in inspect.stdout

    imported = run_with_temp_db(
        [
            sys.executable,
            "-m",
            "scripts.import_statshub_snapshot",
            "--file",
            str(json_path),
            "--endpoint-name",
            "props_player_trends",
            "--snapshot-name",
            "test",
        ],
        tmp_path,
    )
    assert imported.returncode == 0, imported.stderr
    assert "Items importados: 1" in imported.stdout


def test_statshub_snapshot_status_reads_local_only(tmp_path):
    result = run_with_temp_db([sys.executable, "-m", "scripts.statshub_snapshot_status"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Este comando no consume API." in result.stdout
    assert "StatsHub se usa solo como descarga puntual" in result.stdout


def test_health_check_includes_statshub_snapshot_counts(tmp_path):
    result = run_with_temp_db([sys.executable, "-m", "scripts.health_check"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "StatsHub snapshots:" in result.stdout

