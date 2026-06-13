from __future__ import annotations

import argparse
from pathlib import Path

from app.external.csv_import import candidate_mapping, load_mapping, read_csv_rows


def guess_source(columns: list[str], source: str | None) -> str:
    if source:
        return source
    lower = {column.lower() for column in columns}
    if {"player", "squad"} & lower or {"gls", "ast", "min"} & lower:
        return "fbref"
    if "web_name" in lower:
        return "fpl"
    return "generic"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--source")
    args = parser.parse_args()

    path = Path(args.csv)
    columns, rows = read_csv_rows(path)
    source = guess_source(columns, args.source)
    mapping = candidate_mapping(columns, load_mapping(source))

    print("INSPECCION CSV EXTERNO")
    print("Este comando no consume API.")
    print(f"Archivo: {path}")
    print(f"Tamano bytes: {path.stat().st_size}")
    print(f"Filas: {len(rows)}")
    print(f"Columnas: {columns}")
    print(f"Fuente probable: {source}")
    print(f"Mapeo candidato: {mapping}")
    print("Muestras:")
    for row in rows[:3]:
        print(row)


if __name__ == "__main__":
    main()

