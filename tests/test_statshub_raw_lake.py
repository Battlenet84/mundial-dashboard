import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_with_temp_db(command, tmp_path, extra_env=None):
    env = os.environ.copy()
    env["DB_PATH"] = str(tmp_path / "test_mundial.db")
    env.update(extra_env or {})
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)


def sample_event_file(tmp_path: Path) -> Path:
    path = tmp_path / "event_by_date.json"
    payload = {
        "data": [
            {
                "eventId": "e1",
                "tournamentId": "t1",
                "homeTeam": {"id": "team1", "name": "Argentina"},
                "awayTeam": {"id": "team2", "name": "Brazil"},
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def sample_referee_file(tmp_path: Path) -> Path:
    path = tmp_path / "referees.json"
    payload = {"data": [{"refereeId": "r1", "refereeName": "Ref One", "nextGameId": "e1"}]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_extract_ids_from_event_by_date_sample(tmp_path):
    path = sample_event_file(tmp_path)
    result = run_with_temp_db(
        [sys.executable, "-m", "scripts.statshub_extract_ids", "--file", str(path), "--endpoint-name", "event_by_date", "--csv"],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "events: 1" in result.stdout
    assert "teams: 2" in result.stdout
    assert "Este comando no consume API." in result.stdout


def test_raw_import_event_by_date(tmp_path):
    path = sample_event_file(tmp_path)
    result = run_with_temp_db(
        [sys.executable, "-m", "scripts.import_statshub_raw_snapshot", "--file", str(path), "--endpoint-name", "event_by_date", "--snapshot-name", "test"],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "statshub_raw_events: 1" in result.stdout


def test_raw_import_referees(tmp_path):
    path = sample_referee_file(tmp_path)
    result = run_with_temp_db(
        [sys.executable, "-m", "scripts.import_statshub_raw_snapshot", "--file", str(path), "--endpoint-name", "referees_list", "--snapshot-name", "test"],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "statshub_raw_referees: 1" in result.stdout


def test_build_raw_plan_excludes_analysis_and_respects_limit(tmp_path):
    path = sample_event_file(tmp_path)
    result = run_with_temp_db(
        [
            sys.executable,
            "-m",
            "scripts.build_statshub_raw_download_plan",
            "--plan-name",
            "raw_test",
            "--snapshot-name",
            "test",
            "--from-event-file",
            str(path),
            "--max-requests",
            "3",
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Requests planificados: 3" in result.stdout
    blocked = ["props/screener", "player-trends", "player-odds"]
    assert not any(term in result.stdout for term in blocked)


def test_run_raw_plan_dry_run_makes_no_external_requests(tmp_path):
    path = sample_event_file(tmp_path)
    build = run_with_temp_db(
        [sys.executable, "-m", "scripts.build_statshub_raw_download_plan", "--plan-name", "raw_test", "--snapshot-name", "test", "--from-event-file", str(path), "--max-requests", "1"],
        tmp_path,
    )
    assert build.returncode == 0, build.stderr
    result = run_with_temp_db([sys.executable, "-m", "scripts.run_statshub_raw_download_plan", "--plan-name", "raw_test"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Dry-run. No se hicieron requests externos." in result.stdout


def test_run_raw_plan_refuses_execute_when_disabled(tmp_path):
    path = sample_event_file(tmp_path)
    build = run_with_temp_db(
        [sys.executable, "-m", "scripts.build_statshub_raw_download_plan", "--plan-name", "raw_test", "--snapshot-name", "test", "--from-event-file", str(path), "--max-requests", "1"],
        tmp_path,
    )
    assert build.returncode == 0, build.stderr
    result = run_with_temp_db(
        [sys.executable, "-m", "scripts.run_statshub_raw_download_plan", "--plan-name", "raw_test", "--execute"],
        tmp_path,
        {"STATSHUB_ENABLED": "false"},
    )
    assert result.returncode != 0
    assert "StatsHub deshabilitado" in (result.stdout + result.stderr)


def test_raw_db_status_reads_local_only(tmp_path):
    result = run_with_temp_db([sys.executable, "-m", "scripts.statshub_raw_db_status"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Este comando no consume API." in result.stdout

