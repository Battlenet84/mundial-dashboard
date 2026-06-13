from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from app.providers.api_guard import assert_api_allowed
from app.providers.cache import get_cached_response, save_cached_response
from app.providers.rate_limiter import check_budget_available, log_api_call


class BaseProvider(ABC):
    name = "base"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        raw_data_dir: Path,
        timeout: int = 30,
        execute: bool = False,
        force: bool = False,
        use_cache: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.raw_data_dir = raw_data_dir
        self.timeout = timeout
        self.execute = execute
        self.force = force
        self.use_cache = use_cache

    @abstractmethod
    def headers(self) -> dict[str, str]:
        raise NotImplementedError

    def dry_run_response(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "dry_run": True,
            "endpoint": endpoint,
            "params": params or {},
            "estimated_requests": 1,
        }

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        category: str = "api",
    ) -> dict[str, Any]:
        if not self.execute:
            return self.dry_run_response(endpoint, params)

        assert_api_allowed(self.execute)
        if self.use_cache and not self.force:
            cached = get_cached_response(category, endpoint, params)
            if cached is not None:
                return cached

        if not self.api_key:
            raise RuntimeError("API_FOOTBALL_KEY no configurada en .env")

        check_budget_available(1)
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = requests.get(url, headers=self.headers(), params=params or {}, timeout=self.timeout)
        status = "OK" if response.ok else "ERROR"
        log_api_call(endpoint, params, response.status_code, status)
        if response.status_code in {401, 403, 429}:
            response.raise_for_status()
        response.raise_for_status()
        payload = response.json()
        if self.use_cache:
            save_cached_response(category, endpoint, params, payload)
        return payload

    def save_raw_response(
        self,
        category: str,
        payload: dict[str, Any],
        suffix: str | int | None = None,
    ) -> Path:
        directory = self.raw_data_dir / category
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        suffix_text = f"_{suffix}" if suffix is not None else ""
        path = directory / f"{self.name}_{stamp}{suffix_text}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
