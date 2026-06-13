from __future__ import annotations

from pathlib import Path

from app.config.settings import ROOT_DIR
from app.db.connection import get_connection, init_db


def main() -> None:
    init_db()
    html_dir = ROOT_DIR / "data" / "raw" / "statshub"
    csv_dir = ROOT_DIR / "data" / "external" / "statshub"
    html_files = sorted([path for path in html_dir.glob("*.html") if path.is_file()])
    csv_files = sorted([path for path in csv_dir.glob("*.csv") if path.is_file()])
    with get_connection() as conn:
        rows_count = conn.execute("SELECT COUNT(*) FROM statshub_prop_stats").fetchone()[0]
        latest = conn.execute(
            """
            SELECT file_path, rows_imported, rows_skipped, imported_at
            FROM external_dataset_imports
            WHERE source_name = 'statshub'
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()

    print("STATUS STATSHUB")
    print("Este comando no consume API.")
    print("HTML guardados:")
    for path in html_files[-10:]:
        print(f"- {path}")
    if not html_files:
        print("- Sin HTML guardado")
    print("CSV importables:")
    for path in csv_files[-10:]:
        print(f"- {path}")
    if not csv_files:
        print("- Sin CSV local")
    print(f"Filas statshub_prop_stats: {rows_count}")
    print("Ultimos imports:")
    for row in latest:
        print(f"- {row['file_path']}: imported={row['rows_imported']} skipped={row['rows_skipped']} at={row['imported_at']}")
    if not latest:
        print("- Sin imports StatsHub")
    print("StatsHub no esta configurado como API. Solo se usan datos guardados/importados manualmente.")


if __name__ == "__main__":
    main()

