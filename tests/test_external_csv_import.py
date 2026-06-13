import subprocess
import sys
import os
from pathlib import Path

from scripts.build_external_player_features import per90


ROOT = Path(__file__).resolve().parents[1]


def write_sample_csv(path: Path) -> None:
    path.write_text(
        "Player,Squad,Nation,Pos,Age,Min,MP,Starts,Gls,Ast,Sh,SoT,KP,CrdY,CrdR,Tkl,Int,xG,xAG\n"
        "Lionel Test,Argentina,ARG,FW,38,900,10,10,12,4,50,25,20,1,0,5,2,8.5,3.2\n"
        "Zero Minutes,Argentina,ARG,MF,22,0,1,0,0,0,1,0,0,0,0,1,1,0.1,0.0\n",
        encoding="utf-8",
    )


def run_with_temp_db(command, tmp_path):
    env = os.environ.copy()
    env["DB_PATH"] = str(tmp_path / "test_mundial.db")
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_inspect_external_csv_consumes_zero_api(tmp_path):
    csv_path = tmp_path / "players.csv"
    write_sample_csv(csv_path)
    result = run_with_temp_db(
        [sys.executable, "-m", "scripts.inspect_external_csv", "--csv", str(csv_path), "--source", "fbref"],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Este comando no consume API." in result.stdout
    assert "Mapeo candidato" in result.stdout


def test_import_external_player_stats_with_sample_csv(tmp_path):
    csv_path = tmp_path / "players.csv"
    write_sample_csv(csv_path)
    result = run_with_temp_db(
        [
            sys.executable,
            "-m",
            "scripts.import_external_player_stats",
            "--csv",
            str(csv_path),
            "--source",
            "fbref",
            "--season",
            "2025-2026",
            "--competition",
            "test",
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Filas importadas: 2" in result.stdout
    assert "Este comando no consume API." in result.stdout


def test_mapping_missing_columns_does_not_crash(tmp_path):
    csv_path = tmp_path / "minimal.csv"
    csv_path.write_text("Player,Squad\nOnly Name,Only Team\n", encoding="utf-8")
    result = run_with_temp_db(
        [
            sys.executable,
            "-m",
            "scripts.import_external_player_stats",
            "--csv",
            str(csv_path),
            "--source",
            "fbref",
            "--season",
            "2025-2026",
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Columnas importantes faltantes" in result.stdout


def test_per90_calculations():
    assert per90(10, 900) == 1
    assert per90(10, 0) is None


def test_external_data_status_consumes_zero_api(tmp_path):
    result = run_with_temp_db(
        [sys.executable, "-m", "scripts.external_data_status"],
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "Este comando no consume API." in result.stdout
