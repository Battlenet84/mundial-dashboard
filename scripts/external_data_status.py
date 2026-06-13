from __future__ import annotations

from app.db.connection import get_connection, init_db


def main() -> None:
    init_db()
    with get_connection() as conn:
        sources = conn.execute("SELECT source_name, source_type, status, season, competition FROM external_data_sources ORDER BY id DESC LIMIT 10").fetchall()
        imports = conn.execute("SELECT source_name, file_path, rows_imported, status, imported_at FROM external_dataset_imports ORDER BY id DESC LIMIT 10").fetchall()
        stats_count = conn.execute("SELECT COUNT(*) FROM external_player_stats").fetchone()[0]
        features_count = conn.execute("SELECT COUNT(*) FROM external_player_model_features").fetchone()[0]
        competitions = conn.execute("SELECT competition, COUNT(*) AS rows_count FROM external_player_stats GROUP BY competition ORDER BY rows_count DESC LIMIT 10").fetchall()
        teams = conn.execute("SELECT team_name, COUNT(*) AS rows_count FROM external_player_stats GROUP BY team_name ORDER BY rows_count DESC LIMIT 10").fetchall()
        latest = conn.execute("SELECT source_name, rows_read, rows_imported, rows_skipped, message, imported_at FROM external_dataset_imports ORDER BY id DESC LIMIT 5").fetchall()
        missing = conn.execute(
            """
            SELECT
                SUM(CASE WHEN minutes IS NULL THEN 1 ELSE 0 END) AS missing_minutes,
                SUM(CASE WHEN goals IS NULL THEN 1 ELSE 0 END) AS missing_goals,
                SUM(CASE WHEN assists IS NULL THEN 1 ELSE 0 END) AS missing_assists
            FROM external_player_stats
            """
        ).fetchone()
    print("ESTADO DATOS EXTERNOS")
    print("Este comando no consume API.")
    print("Fuentes registradas:")
    for row in sources:
        print(f"- {row['source_name']} {row['season'] or ''} {row['competition'] or ''} {row['status'] or ''}")
    if not sources:
        print("- Sin fuentes registradas")
    print("Imports:")
    for row in imports:
        print(f"- {row['source_name']}: {row['rows_imported']} filas - {row['status']} - {row['file_path']}")
    if not imports:
        print("- Sin imports")
    print(f"external_player_stats: {stats_count}")
    print(f"external_player_model_features: {features_count}")
    print("Top competiciones:")
    for row in competitions:
        print(f"- {row['competition']}: {row['rows_count']}")
    print("Top equipos:")
    for row in teams:
        print(f"- {row['team_name']}: {row['rows_count']}")
    print("Campos importantes faltantes:")
    print(dict(missing) if missing else {})
    print("Ultimos imports:")
    for row in latest:
        print(f"- {row['source_name']}: read={row['rows_read']} imported={row['rows_imported']} skipped={row['rows_skipped']} - {row['message']}")


if __name__ == "__main__":
    main()

