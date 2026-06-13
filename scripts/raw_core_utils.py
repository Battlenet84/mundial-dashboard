from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config.settings import RAW_DATA_DIR


CORE_CATEGORIES = ("coverage", "teams", "fixtures")


def latest_json_file(category: str) -> Path | None:
    directory = RAW_DATA_DIR / category
    if not directory.exists():
        return None
    files = [path for path in directory.glob("*.json") if path.is_file()]
    return max(files, key=lambda path: path.stat().st_mtime) if files else None


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON raiz no es un objeto")
    return payload


def response_count(payload: dict[str, Any]) -> int:
    response = payload.get("response")
    return len(response) if isinstance(response, list) else 0


def payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    response = payload.get("response")
    first = response[0] if isinstance(response, list) and response else None
    return {
        "top_level_keys": sorted(payload.keys()),
        "get": payload.get("get"),
        "parameters": payload.get("parameters"),
        "errors": payload.get("errors"),
        "results": payload.get("results"),
        "paging": payload.get("paging"),
        "response_length": len(response) if isinstance(response, list) else None,
        "first_response_item_keys": sorted(first.keys()) if isinstance(first, dict) else None,
    }

