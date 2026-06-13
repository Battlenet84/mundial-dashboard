from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from scripts import statshub_raw_audit


ROOT = Path(__file__).resolve().parents[1]


def run_with_temp_db(command, tmp_path, extra_env=None):
    env = os.environ.copy()
    env["DB_PATH"] = str(tmp_path / "test_mundial.db")
    env.update(extra_env or {})
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)


def create_empty_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_mundial.db"
    sqlite3.connect(db_path).close()
    return db_path


def create_sample_db(tmp_path: Path) -> Path:
    db_path = create_empty_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE statshub_raw_events (
                event_id TEXT,
                endpoint_name TEXT,
                snapshot_name TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE statshub_raw_teams (
                team_id TEXT,
                endpoint_name TEXT,
                raw_json TEXT
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO statshub_raw_events
            (event_id, endpoint_name, snapshot_name, raw_json)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("e1", "event_by_date", "snap1", '{"ok": true}'),
                ("e1", "event_by_date", "snap1", "{bad json"),
                ("", "event_by_date", "snap2", None),
            ],
        )
        conn.execute(
            """
            INSERT INTO statshub_raw_teams (team_id, endpoint_name, raw_json)
            VALUES (?, ?, ?)
            """,
            ("t1", "teams", '{"team": 1}'),
        )
    return db_path


def test_audit_works_with_empty_db(tmp_path):
    create_empty_db(tmp_path)
    result = run_with_temp_db([sys.executable, "-m", "scripts.statshub_raw_audit"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "DB path:" in result.stdout
    assert "table not found" in result.stdout
    assert "Este comando no consume API" in result.stdout


def test_audit_works_with_sample_statshub_table(tmp_path):
    create_sample_db(tmp_path)
    result = run_with_temp_db([sys.executable, "-m", "scripts.statshub_raw_audit"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "statshub_raw_events: 3" in result.stdout
    assert "Filas por endpoint_name" in result.stdout
    assert "IDs faltantes event_id: 1" in result.stdout
    assert "IDs duplicados event_id: 1" in result.stdout


def test_export_selected_table_creates_csv(tmp_path):
    create_sample_db(tmp_path)
    out_dir = tmp_path / "exports"
    result = run_with_temp_db(
        [
            sys.executable,
            "-m",
            "scripts.export_statshub_raw_tables",
            "--table",
            "statshub_raw_events",
            "--out-dir",
            str(out_dir),
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    csv_path = out_dir / "statshub_raw_events.csv"
    assert csv_path.exists()
    assert "event_id,endpoint_name,snapshot_name,raw_json" in csv_path.read_text(encoding="utf-8")


def test_export_all_exports_existing_statshub_tables(tmp_path):
    create_sample_db(tmp_path)
    out_dir = tmp_path / "exports"
    result = run_with_temp_db(
        [
            sys.executable,
            "-m",
            "scripts.export_statshub_raw_tables",
            "--all",
            "--out-dir",
            str(out_dir),
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert (out_dir / "statshub_raw_events.csv").exists()
    assert (out_dir / "statshub_raw_teams.csv").exists()


def test_invalid_raw_json_is_reported_without_crashing(tmp_path):
    db_path = create_sample_db(tmp_path)
    conn = statshub_raw_audit.open_readonly_connection(db_path)
    assert conn is not None
    with conn:
        assert statshub_raw_audit.invalid_raw_json_count(conn, "statshub_raw_events") == 1
    result = run_with_temp_db([sys.executable, "-m", "scripts.statshub_raw_audit"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "raw_json invalido: 1" in result.stdout


def test_helper_functions_do_not_make_external_requests(tmp_path, monkeypatch):
    db_path = create_sample_db(tmp_path)

    def blocked_socket(*args, **kwargs):
        raise AssertionError("external request attempted")

    import socket

    monkeypatch.setattr(socket, "socket", blocked_socket)
    monkeypatch.setattr(socket, "create_connection", blocked_socket)

    conn = statshub_raw_audit.open_readonly_connection(db_path)
    assert conn is not None
    with conn:
        assert statshub_raw_audit.count_rows(conn, "statshub_raw_events") == 3
        assert statshub_raw_audit.missing_id_count(conn, "statshub_raw_events", "event_id") == 1
        assert statshub_raw_audit.duplicate_id_count(conn, "statshub_raw_events", "event_id") == 1
