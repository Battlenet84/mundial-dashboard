import subprocess
import sys
from pathlib import Path

import pytest

from app.providers.api_football import ApiFootballProvider
from app.providers.api_guard import assert_api_allowed


ROOT = Path(__file__).resolve().parents[1]


def test_api_guard_blocks_without_execute():
    with pytest.raises(RuntimeError):
        assert_api_allowed(False)


def test_provider_dry_run_returns_estimate():
    provider = ApiFootballProvider.from_settings(execute=False)
    payload = provider.get_worldcup_players(page=1)
    assert payload["dry_run"] is True
    assert payload["estimated_requests"] == 1
    assert payload["endpoint"] == "players"


def test_budget_planner_does_not_call_api():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.plan_api_fetch", "--dataset", "players"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Este comando no consume API." in result.stdout


def test_api_budget_does_not_require_api_key():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.api_budget"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Este comando no consume API." in result.stdout


def test_core_and_matchday_planners_do_not_call_api():
    for command in [
        [sys.executable, "-m", "scripts.plan_core_fetch"],
        [sys.executable, "-m", "scripts.plan_matchday_fetch", "--date", "2026-06-11", "--max-players", "20"],
        [sys.executable, "-m", "scripts.plan_player_stats_fetch", "--date", "2026-06-11", "--season", "2025", "--max-players", "20"],
    ]:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        assert "consume API" in result.stdout


def test_api_budget_does_not_print_key(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEYS_JSON", '{"backup":"SECRET_SHOULD_NOT_PRINT"}')
    monkeypatch.setenv("API_FOOTBALL_PROFILE", "backup")
    result = subprocess.run(
        [sys.executable, "-m", "scripts.api_budget"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "SECRET_SHOULD_NOT_PRINT" not in result.stdout
    assert "Perfil API seleccionado: backup" in result.stdout
    assert "API key configurada: si" in result.stdout
