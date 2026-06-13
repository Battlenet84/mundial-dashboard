from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.external.statshub_snapshot import iter_arrays, parse_json_if_possible


def possible_type(path: str, items: list) -> str:
    lower = path.lower()
    sample = items[0] if items and isinstance(items[0], dict) else {}
    keys = {str(key).lower() for key in sample.keys()} if isinstance(sample, dict) else set()
    if "referee" in lower or "referee" in keys:
        return "referees"
    if "odds" in lower or "odds" in keys:
        return "odds"
    if "props" in lower or "line" in keys or "hit" in " ".join(keys):
        return "props"
    if "player" in lower or "player" in keys or "playername" in keys:
        return "player_stats"
    if "fixture" in keys or "event" in lower:
        return "fixtures"
    return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    path = Path(args.file)
    text = path.read_text(encoding="utf-8", errors="ignore")
    payload = parse_json_if_possible(text)
    print("INSPECCION STATSHUB SNAPSHOT")
    print("Este comando no consume API.")
    print(f"Archivo: {path}")
    print(f"Tamano bytes: {path.stat().st_size}")
    if payload is None:
        print("No es JSON valido.")
        return
    if isinstance(payload, dict):
        print(f"Top-level keys: {sorted(payload.keys())}")
    elif isinstance(payload, list):
        print("Top-level keys: []")
    arrays = list(iter_arrays(payload))
    print("Arrays detectados:")
    for array_path, items in arrays[:20]:
        sample = items[0] if items and isinstance(items[0], dict) else {}
        sample_keys = sorted(sample.keys()) if isinstance(sample, dict) else []
        dtype = possible_type(array_path, items)
        print(f"- {array_path}: rows={len(items)} sample_keys={sample_keys} tipo={dtype}")
    if not arrays:
        print("- Sin arrays detectados")
    print(f"Comando sugerido: python -m scripts.import_statshub_snapshot --file \"{path}\" --endpoint-name ENDPOINT_NAME")


if __name__ == "__main__":
    main()

