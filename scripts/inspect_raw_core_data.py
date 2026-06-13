from __future__ import annotations

from app.config.settings import RAW_DATA_DIR
from scripts.raw_core_utils import CORE_CATEGORIES, latest_json_file, load_json, payload_summary


def main() -> None:
    print("INSPECCION RAW CORE DATA - MUNDIAL 2026")
    print("Este comando no consume API.")
    for category in CORE_CATEGORIES:
        path = latest_json_file(category)
        print()
        print(f"{category}:")
        if path is None:
            print(f"- Sin archivos JSON en {RAW_DATA_DIR / category}")
            continue
        print(f"- Archivo: {path}")
        print(f"- Tamano bytes: {path.stat().st_size}")
        try:
            summary = payload_summary(load_json(path))
        except Exception as exc:
            print(f"- ERROR: JSON invalido o ilegible: {exc}")
            continue
        print(f"- Top-level keys: {summary['top_level_keys']}")
        print(f"- get: {summary['get']}")
        print(f"- parameters: {summary['parameters']}")
        print(f"- errors: {summary['errors']}")
        print(f"- results: {summary['results']}")
        print(f"- paging: {summary['paging']}")
        print(f"- response length: {summary['response_length']}")
        print(f"- first response item keys: {summary['first_response_item_keys']}")


if __name__ == "__main__":
    main()

