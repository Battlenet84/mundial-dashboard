from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import RAW_DATA_DIR


CACHE_DIR = RAW_DATA_DIR / "cache"


def build_cache_key(endpoint: str, params: dict[str, Any] | None) -> str:
    payload = {"endpoint": endpoint, "params": params or {}}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _cache_path(category: str, endpoint: str, params: dict[str, Any] | None) -> Path:
    return CACHE_DIR / category / f"{build_cache_key(endpoint, params)}.json"


def get_cached_response(
    category: str,
    endpoint: str,
    params: dict[str, Any] | None,
    max_age_hours: int | None = None,
) -> dict[str, Any] | None:
    path = _cache_path(category, endpoint, params)
    if not path.exists():
        return None
    if max_age_hours is not None:
        age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        if age > max_age_hours * 3600:
            return None
    print("Usando cache local. No se consumio request de API.")
    return json.loads(path.read_text(encoding="utf-8"))


def save_cached_response(
    category: str,
    endpoint: str,
    params: dict[str, Any] | None,
    payload: dict[str, Any],
) -> Path:
    path = _cache_path(category, endpoint, params)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

