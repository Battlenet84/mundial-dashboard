import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_structure_exists():
    for path in [
        "app/config/settings.py",
        "app/providers/api_football.py",
        "app/ingestion/sync_all.py",
        "app/db/schema.sql",
        "scripts/init_db.py",
        "scripts/health_check.py",
        ".env.example",
    ]:
        assert (ROOT / path).exists()


def test_no_cloud_dependency_required():
    text = (ROOT / "requirements.txt").read_text(encoding="utf-8", errors="ignore").lower()
    assert "supabase" not in text


def test_init_db_runs_without_errors():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.init_db"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_health_check_runs_without_data():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.health_check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "DATA HEALTH CHECK - MUNDIAL 2026" in result.stdout
