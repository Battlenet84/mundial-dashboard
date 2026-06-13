from __future__ import annotations

from app.config.settings import ROOT_DIR, get_settings
from app.db.connection import get_connection, init_db


def main() -> None:
    init_db()
    settings = get_settings()
    raw_dir = ROOT_DIR / "data" / "raw" / "statshub" / "snapshots"
    raw_files = [path for path in raw_dir.rglob("*") if path.is_file() and path.name != ".gitkeep"]
    with get_connection() as conn:
        snapshot_count = conn.execute("SELECT COUNT(*) FROM statshub_snapshots").fetchone()[0]
        item_count = conn.execute("SELECT COUNT(*) FROM statshub_snapshot_items").fetchone()[0]
        latest = conn.execute(
            """
            SELECT snapshot_name, endpoint_name, status, status_code, rows_detected, created_at
            FROM statshub_snapshots
            ORDER BY id DESC LIMIT 5
            """
        ).fetchall()
        item_types = conn.execute(
            """
            SELECT item_type, COUNT(*) AS rows_count
            FROM statshub_snapshot_items
            GROUP BY item_type
            ORDER BY rows_count DESC
            """
        ).fetchall()
        statuses = conn.execute(
            """
            SELECT status, COUNT(*) AS rows_count
            FROM statshub_snapshots
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
    print("STATUS STATSHUB SNAPSHOTS")
    print("Este comando no consume API.")
    print(f"StatsHub habilitado: {'si' if settings.statshub_enabled else 'no'}")
    print(f"Snapshots registrados: {snapshot_count}")
    print(f"Raw files guardados: {len(raw_files)}")
    print(f"Items importados: {item_count}")
    print("Ultimos snapshots:")
    for row in latest:
        print(f"- {row['snapshot_name']} / {row['endpoint_name']}: {row['status']} code={row['status_code']} rows={row['rows_detected']} at={row['created_at']}")
    if not latest:
        print("- Sin snapshots")
    print("Tipos importados:")
    for row in item_types:
        print(f"- {row['item_type']}: {row['rows_count']}")
    if not item_types:
        print("- Sin items")
    print("Estados:")
    for row in statuses:
        print(f"- {row['status']}: {row['rows_count']}")
    if not statuses:
        print("- Sin estados")
    print("StatsHub se usa solo como descarga puntual. El dashboard y modelos leen SQLite/local.")


if __name__ == "__main__":
    main()

