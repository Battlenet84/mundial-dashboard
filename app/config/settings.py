import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
DEFAULT_DB_PATH = DATA_DIR / "mundial.db"

load_dotenv(ROOT_DIR / ".env")

DB_PATH = Path(os.getenv("DB_PATH", str(DEFAULT_DB_PATH)))


class Settings(BaseModel):
    api_profile: str = "default"
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    world_cup_league_id: int = 1
    world_cup_season: int = 2026
    api_daily_limit: int = 100
    api_per_minute_limit: int = 10
    api_min_seconds_between_requests: int = 7
    use_api_cache: bool = True
    api_request_ledger_path: Path = DATA_DIR / "api_request_ledger_default.json"
    statshub_enabled: bool = False
    statshub_base_url: str = "https://www.statshub.com"
    statshub_min_seconds_between_requests: int = 10
    statshub_cache_enabled: bool = True
    statshub_max_requests_per_run: int = 5
    statshub_snapshot_mode: bool = True
    database_path: Path = DB_PATH
    raw_data_dir: Path = RAW_DATA_DIR


def _bool_env(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "si", "on"}


def _profile_key(profile: str) -> str:
    keys_json = os.getenv("API_FOOTBALL_KEYS_JSON", "").strip()
    if not keys_json:
        return os.getenv("API_FOOTBALL_KEY", "")
    try:
        keys = json.loads(keys_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("API_FOOTBALL_KEYS_JSON no es JSON valido.") from exc
    if not isinstance(keys, dict):
        raise RuntimeError("API_FOOTBALL_KEYS_JSON debe ser un objeto JSON.")
    return str(keys.get(profile, "") or "")


def get_settings() -> Settings:
    profile = os.getenv("API_FOOTBALL_PROFILE") or os.getenv("API_PROFILE", "default")
    ledger_env = os.getenv("API_REQUEST_LEDGER_PATH", "").strip()
    ledger = ledger_env or str(DATA_DIR / f"api_request_ledger_{profile}.json")
    db_path = Path(os.getenv("DB_PATH", str(DEFAULT_DB_PATH)))
    return Settings(
        api_profile=profile,
        api_football_key=_profile_key(profile),
        api_football_base_url=os.getenv(
            "API_FOOTBALL_BASE_URL",
            "https://v3.football.api-sports.io",
        ),
        world_cup_league_id=int(os.getenv("WORLD_CUP_LEAGUE_ID", "1")),
        world_cup_season=int(os.getenv("WORLD_CUP_SEASON", "2026")),
        api_daily_limit=int(os.getenv("API_DAILY_LIMIT", "100")),
        api_per_minute_limit=int(os.getenv("API_PER_MINUTE_LIMIT", "10")),
        api_min_seconds_between_requests=int(os.getenv("API_MIN_SECONDS_BETWEEN_REQUESTS", "7")),
        use_api_cache=_bool_env("USE_API_CACHE", True),
        api_request_ledger_path=Path(ledger),
        statshub_enabled=_bool_env("STATSHUB_ENABLED", False),
        statshub_base_url=os.getenv("STATSHUB_BASE_URL", "https://www.statshub.com"),
        statshub_min_seconds_between_requests=int(os.getenv("STATSHUB_MIN_SECONDS_BETWEEN_REQUESTS", "10")),
        statshub_cache_enabled=_bool_env("STATSHUB_CACHE_ENABLED", True),
        statshub_max_requests_per_run=int(os.getenv("STATSHUB_MAX_REQUESTS_PER_RUN", "5")),
        statshub_snapshot_mode=_bool_env("STATSHUB_SNAPSHOT_MODE", True),
        database_path=db_path,
    )
