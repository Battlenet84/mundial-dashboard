from app.config.settings import get_settings


def test_settings_uses_plain_key_when_json_empty(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "plain-key")
    monkeypatch.setenv("API_FOOTBALL_KEYS_JSON", "")
    monkeypatch.setenv("API_FOOTBALL_PROFILE", "default")
    settings = get_settings()
    assert settings.api_football_key == "plain-key"
    assert settings.api_profile == "default"


def test_settings_uses_profile_key_from_json(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "plain-key")
    monkeypatch.setenv("API_FOOTBALL_KEYS_JSON", '{"default":"json-key","backup":"backup-key"}')
    monkeypatch.setenv("API_FOOTBALL_PROFILE", "backup")
    settings = get_settings()
    assert settings.api_football_key == "backup-key"
    assert settings.api_profile == "backup"


def test_settings_derives_ledger_from_profile_when_empty(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_PROFILE", "backup")
    monkeypatch.setenv("API_REQUEST_LEDGER_PATH", "")
    settings = get_settings()
    assert str(settings.api_request_ledger_path).endswith("api_request_ledger_backup.json")
