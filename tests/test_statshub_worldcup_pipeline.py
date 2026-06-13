import json
import os
import subprocess
import sys
from pathlib import Path

from app.external.statshub_snapshot import classify_response
from app.external.statshub_worldcup import is_worldcup_event


ROOT = Path(__file__).resolve().parents[1]


def run_with_temp_db(command, tmp_path, extra_env=None):
    env = os.environ.copy()
    env["DB_PATH"] = str(tmp_path / "test_mundial.db")
    env.update(extra_env or {})
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)


def event_file(tmp_path: Path) -> Path:
    path = tmp_path / "events.json"
    payload = {
        "data": [
            {
                "eventId": "wc1",
                "uniqueTournamentId": 16,
                "tournamentId": "t1",
                "homeTeam": {"id": "team1", "name": "Argentina"},
                "awayTeam": {"id": "team2", "name": "Brazil"},
            },
            {
                "eventId": "other1",
                "uniqueTournamentId": 99,
                "tournament": {"name": "Other Cup"},
                "homeTeam": {"id": "team3", "name": "Other"},
            },
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_worldcup_seed_filter():
    assert is_worldcup_event({"uniqueTournamentId": 16}) is True
    assert is_worldcup_event({"uniqueTournamentId": 99, "tournament": {"name": "Other Cup"}}) is False
    assert is_worldcup_event({"uniqueTournament": {"name": "FIFA World Cup"}}) is True


def test_player_tournament_plan_builds_from_worldcup_players(tmp_path):
    db = tmp_path / "test_mundial.db"
    env = {"DB_PATH": str(db)}
    setup = """
from app.db.connection import init_db, get_connection
init_db()
with get_connection() as conn:
    conn.execute("INSERT INTO statshub_worldcup_players (player_id, player_name, team_id, team_name) VALUES ('p1','A','t1','T')")
"""
    subprocess.run([sys.executable, "-c", setup], cwd=ROOT, env={**os.environ, **env}, check=True)
    result = run_with_temp_db(
        [sys.executable, "-m", "scripts.build_statshub_worldcup_player_season_plan", "--plan-name", "p", "--snapshot-name", "s", "--max-players", "10", "--max-requests", "10"],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Requests planificados: 1" in result.stdout


def test_performance_plan_dedupes_team_tournament_pairs(tmp_path):
    db = tmp_path / "test_mundial.db"
    env = {"DB_PATH": str(db)}
    raw = json.dumps({"data": [{"teamId": "t1", "tournamentId": "tour1"}, {"teamId": "t1", "tournamentId": "tour1"}]})
    setup = f"""
from app.db.connection import init_db, get_connection
init_db()
with get_connection() as conn:
    conn.execute("INSERT INTO statshub_raw_player_tournaments (player_id, raw_json) VALUES ('p1', ?)", ({raw!r},))
"""
    subprocess.run([sys.executable, "-c", setup], cwd=ROOT, env={**os.environ, **env}, check=True)
    result = run_with_temp_db(
        [sys.executable, "-m", "scripts.build_statshub_worldcup_performance_plan", "--plan-name", "perf", "--snapshot-name", "s", "--max-requests", "10"],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Requests planificados: 1" in result.stdout


def test_200_json_performance_classifies_ok():
    assert classify_response(200, "application/json", '{"data":[1]}', {"data": [1]}) == "ok"


def test_error_payload_not_imported_as_performance(tmp_path):
    path = tmp_path / "error.json"
    path.write_text('{"error":"not found"}', encoding="utf-8")
    result = run_with_temp_db(
        [sys.executable, "-m", "scripts.import_statshub_raw_snapshot", "--file", str(path), "--endpoint-name", "team_1_performance", "--snapshot-name", "s"],
        tmp_path,
    )
    assert result.returncode != 0
    assert "Payload de error" in (result.stdout + result.stderr)

