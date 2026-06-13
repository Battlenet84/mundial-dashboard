from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.config.settings import ROOT_DIR


TARGET_FIELDS = [
    "player_name",
    "team_name",
    "nationality",
    "position",
    "age",
    "season",
    "competition",
    "minutes",
    "appearances",
    "starts",
    "goals",
    "assists",
    "shots_total",
    "shots_on",
    "passes_total",
    "passes_key",
    "fouls_committed",
    "fouls_drawn",
    "yellow_cards",
    "red_cards",
    "tackles",
    "interceptions",
    "progressive_passes",
    "progressive_carries",
    "xg",
    "npxg",
    "xa",
    "sca",
    "gca",
]


NUMERIC_FIELDS = set(TARGET_FIELDS) - {
    "player_name",
    "team_name",
    "nationality",
    "position",
    "season",
    "competition",
}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        return list(reader.fieldnames or []), rows


def normalize_name(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value.strip().lower())
    return text or None


def load_mapping(source: str, mapping_path: str | None = None) -> dict[str, list[str]]:
    path = Path(mapping_path) if mapping_path else ROOT_DIR / "data" / "mappings" / f"{source}_player_stats.yaml"
    if not path.exists():
        path = ROOT_DIR / "data" / "mappings" / "generic_player_stats.yaml"
    mapping: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, raw_values = line.split(":", 1)
        raw_values = raw_values.strip()
        if raw_values.startswith("[") and raw_values.endswith("]"):
            values = [item.strip().strip("'\"") for item in raw_values[1:-1].split(",")]
        else:
            values = [raw_values.strip().strip("'\"")]
        mapping[key.strip()] = [value for value in values if value]
    return mapping


def candidate_mapping(columns: list[str], mapping: dict[str, list[str]]) -> dict[str, str]:
    lower_lookup = {column.lower(): column for column in columns}
    result: dict[str, str] = {}
    for target, candidates in mapping.items():
        for candidate in candidates:
            if candidate in columns:
                result[target] = candidate
                break
            if candidate.lower() in lower_lookup:
                result[target] = lower_lookup[candidate.lower()]
                break
    return result


def coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def map_row(row: dict[str, Any], mapped_columns: dict[str, str], season: str, competition: str | None) -> dict[str, Any]:
    output = {field: None for field in TARGET_FIELDS}
    output["season"] = season
    output["competition"] = competition
    for target, source_column in mapped_columns.items():
        if target in output:
            output[target] = row.get(source_column)
    for field in NUMERIC_FIELDS:
        output[field] = coerce_float(output.get(field))
    output["normalized_player_name"] = normalize_name(output.get("player_name"))
    return output


def raw_json(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)

