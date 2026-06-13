from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import get_settings


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ledger_path() -> Path:
    path = get_settings().api_request_ledger_path
    if not path.is_absolute():
        path = get_settings().database_path.parents[0].parents[0] / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_ledger() -> list[dict[str, Any]]:
    path = _ledger_path()
    if not path.exists():
        path.write_text("[]", encoding="utf-8")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def save_ledger(entries: list[dict[str, Any]]) -> None:
    _ledger_path().write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def _today_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    today = datetime.now(timezone.utc).date().isoformat()
    return [e for e in entries if str(e.get("timestamp", "")).startswith(today)]


def get_budget_summary() -> dict[str, Any]:
    settings = get_settings()
    entries = load_ledger()
    today = _today_entries(entries)
    last = entries[-1]["timestamp"] if entries else None
    return {
        "daily_limit": settings.api_daily_limit,
        "used_today": len(today),
        "remaining_today": max(settings.api_daily_limit - len(today), 0),
        "per_minute_limit": settings.api_per_minute_limit,
        "min_seconds_between_requests": settings.api_min_seconds_between_requests,
        "last_request_timestamp": last,
        "ledger_path": str(_ledger_path()),
        "recent_requests": entries[-5:],
        "cache_enabled": settings.use_api_cache,
        "api_profile": settings.api_profile,
        "api_key_configured": bool(settings.api_football_key),
    }


def check_budget_available(estimated_requests: int = 1) -> None:
    settings = get_settings()
    summary = get_budget_summary()
    if summary["remaining_today"] < estimated_requests:
        raise RuntimeError("Presupuesto diario de API agotado o insuficiente.")
    entries = load_ledger()
    now = datetime.now(timezone.utc).timestamp()
    recent = [
        e for e in entries
        if now - datetime.fromisoformat(e["timestamp"]).timestamp() <= 60
    ]
    if len(recent) >= settings.api_per_minute_limit:
        raise RuntimeError("Limite por minuto de API alcanzado.")
    if entries:
        last_ts = datetime.fromisoformat(entries[-1]["timestamp"]).timestamp()
        wait = settings.api_min_seconds_between_requests - (now - last_ts)
        if wait > 0:
            time.sleep(wait)


def log_api_call(
    endpoint: str,
    params: dict[str, Any] | None,
    status_code: int | None,
    status: str,
) -> None:
    entries = load_ledger()
    entries.append(
        {
            "timestamp": utc_now(),
            "endpoint": endpoint,
            "params": params or {},
            "status_code": status_code,
            "status": status,
            "source": "api",
        }
    )
    save_ledger(entries)
