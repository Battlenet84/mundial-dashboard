import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_with_temp_db(command, tmp_path):
    env = os.environ.copy()
    env["DB_PATH"] = str(tmp_path / "test_mundial.db")
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)


def test_inspect_saved_statshub_html_static_table(tmp_path):
    html = tmp_path / "statshub.html"
    html.write_text(
        "<html><head><title>StatsHub Test</title></head><body>"
        "<table><tr><th>Player</th><th>Shots</th><th>Hit Rate</th></tr>"
        "<tr><td>Test Player</td><td>3</td><td>60%</td></tr></table>"
        "</body></html>",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "scripts.inspect_saved_statshub_html", "--html", str(html)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Este comando no consume API." in result.stdout
    assert "Tablas detectadas: 1" in result.stdout
    assert "Test" not in result.stderr


def test_inspect_saved_statshub_html_no_table(tmp_path):
    html = tmp_path / "dynamic.html"
    html.write_text("<html><head><title>Dynamic</title></head><body><div id='app'></div></body></html>", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.inspect_saved_statshub_html", "--html", str(html)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "No se encontraron datos tabulares" in result.stdout


def test_import_statshub_table_csv(tmp_path):
    csv_path = tmp_path / "props.csv"
    csv_path.write_text(
        "Player,Team,Opponent,Line,Hit Rate,Average,Last N,Odds,Value\n"
        "Test Player,ARG,BRA,2.5,60,3.1,5,-120,4\n",
        encoding="utf-8",
    )
    result = run_with_temp_db(
        [
            sys.executable,
            "-m",
            "scripts.import_statshub_table_csv",
            "--csv",
            str(csv_path),
            "--market",
            "shots",
            "--competition",
            "test",
            "--season",
            "2025-2026",
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Filas importadas: 1" in result.stdout
    assert "Este comando no consume API." in result.stdout


def test_statshub_status_consumes_zero_api(tmp_path):
    result = run_with_temp_db([sys.executable, "-m", "scripts.statshub_status"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Este comando no consume API." in result.stdout
    assert "StatsHub no esta configurado como API" in result.stdout

