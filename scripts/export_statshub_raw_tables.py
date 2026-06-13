from __future__ import annotations

import argparse
import csv
from pathlib import Path

from scripts.statshub_raw_audit import (
    get_columns,
    get_database_path,
    list_tables,
    open_readonly_connection,
    quote_identifier,
    table_exists,
)


DEFAULT_OUT_DIR = Path("data") / "exports" / "statshub"


def export_table(conn, table: str, out_dir: Path) -> Path:
    columns = get_columns(conn, table)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{table}.csv"
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in conn.execute(f"SELECT * FROM {quote_identifier(table)}"):
            writer.writerow([row[column] for column in columns])
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exporta tablas StatsHub locales a CSV.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Carpeta destino.")
    parser.add_argument("--table", help="Tabla StatsHub a exportar.")
    parser.add_argument("--all", action="store_true", help="Exportar todas las tablas statshub_* existentes.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    db_path = get_database_path()
    print("Export StatsHub raw local")
    print(f"DB path: {db_path}")
    print("Este comando no consume API ni hace requests externos.")

    conn = open_readonly_connection(db_path)
    if conn is None:
        print("Base SQLite no encontrada. No se exporto nada.")
        return

    with conn:
        if args.table:
            if not table_exists(conn, args.table):
                print(f"Error: tabla no encontrada: {args.table}")
                return
            targets = [args.table]
        elif args.all:
            targets = [table for table in list_tables(conn) if table.startswith("statshub_")]
            if not targets:
                print("No hay tablas statshub_* para exportar.")
                return
        else:
            print("Indica --table TABLA o --all.")
            return

        for table in targets:
            path = export_table(conn, table, out_dir)
            print(f"Exportado: {path}")


if __name__ == "__main__":
    main()
