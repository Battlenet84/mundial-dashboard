from __future__ import annotations

from app.config.settings import DB_PATH
from app.config.settings import get_settings
from app.db.connection import get_connection, init_db
from app.db.queries import get_api_budget_summary, get_counts


def scalar(conn, query: str):
    row = conn.execute(query).fetchone()
    return row[0] if row else None


def main() -> None:
    init_db()
    with get_connection() as conn:
        counts = get_counts(conn)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        latest_syncs = conn.execute(
            """
            SELECT sync_name, status, records_count, finished_at, message
            FROM sync_logs
            WHERE id IN (SELECT MAX(id) FROM sync_logs GROUP BY sync_name)
            ORDER BY sync_name
            """
        ).fetchall()
        upcoming = conn.execute(
            """
            SELECT date_utc, home_team_name, away_team_name
            FROM fixtures
            WHERE date_utc IS NULL OR status_short IS NULL OR status_short NOT IN ('FT', 'AET', 'PEN')
            ORDER BY date_utc
            LIMIT 10
            """
        ).fetchall()
        without_odds = scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM fixtures f
            WHERE NOT EXISTS (
                SELECT 1 FROM odds_snapshots o
                WHERE o.provider = f.provider
                  AND o.provider_fixture_id = f.provider_fixture_id
            )
            """,
        )
        latest_odds = scalar(conn, "SELECT MAX(snapshot_time) FROM odds_snapshots")
        warnings = conn.execute(
            """
            SELECT sync_name, status, message, finished_at
            FROM sync_logs
            WHERE status IN ('ERROR', 'WARNING')
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()
        latest_manual = conn.execute(
            """
            SELECT import_name, data_type, records_count, imported_at
            FROM manual_imports
            ORDER BY id DESC
            LIMIT 5
            """
        ).fetchall()
        manual_teams = scalar(conn, "SELECT COUNT(*) FROM teams WHERE source_type = 'manual'")
        api_teams = scalar(conn, "SELECT COUNT(*) FROM teams WHERE source_type = 'api'")
        manual_fixtures = scalar(conn, "SELECT COUNT(*) FROM fixtures WHERE source_type = 'manual'")
        api_fixtures = scalar(conn, "SELECT COUNT(*) FROM fixtures WHERE source_type = 'api'")
        statshub_snapshots = scalar(conn, "SELECT COUNT(*) FROM statshub_snapshots")
        statshub_items = scalar(conn, "SELECT COUNT(*) FROM statshub_snapshot_items")
        latest_statshub = conn.execute(
            "SELECT endpoint_name, status, created_at FROM statshub_snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
    budget = get_api_budget_summary()
    settings = get_settings()

    print("DATA HEALTH CHECK - MUNDIAL 2026")
    print()
    print(f"Base local: {DB_PATH}")
    print()
    print("Tablas:")
    print(", ".join(row["name"] for row in tables))
    print()
    labels = {
        "teams": "Equipos",
        "fixtures": "Partidos",
        "players": "Jugadores",
        "injuries": "Lesiones",
        "odds_snapshots": "Snapshots de cuotas",
        "fixture_statistics": "Estadisticas de partido",
        "fixture_lineups": "Formaciones",
        "fixture_events": "Eventos",
        "rankings": "Rankings",
        "manual_imports": "Imports manuales",
        "player_season_stats": "Filas player season stats",
        "player_model_features": "Player model features",
        "team_roster_features": "Team roster features",
        "matchday_plans": "Planes matchday",
        "external_player_stats": "External player stats",
        "external_player_model_features": "External player model features",
        "external_dataset_imports": "External dataset imports",
        "statshub_prop_stats": "StatsHub prop stats",
    }
    for key, label in labels.items():
        print(f"{label}: {counts.get(key, 0)}")
    print()
    print("Ultimos syncs:")
    if latest_syncs:
        for row in latest_syncs:
            detail = f" - {row['message']}" if row["message"] else ""
            print(f"- {row['sync_name']}: {row['status']} ({row['records_count']} registros) - {row['finished_at']}{detail}")
    else:
        print("- Sin syncs registrados")
    print()
    print("Proximos partidos:")
    if upcoming:
        for row in upcoming:
            print(f"- {row['home_team_name']} vs {row['away_team_name']} - {row['date_utc']}")
    else:
        print("- Sin partidos cargados")
    print()
    print(f"Partidos sin cuotas: {without_odds}")
    print(f"Ultima actualizacion de cuotas: {latest_odds or '-'}")
    print()
    print("Errores o warnings recientes:")
    if warnings:
        for row in warnings:
            print(f"- {row['sync_name']}: {row['status']} - {row['message']} ({row['finished_at']})")
    else:
        print("- Sin errores ni warnings")
    print()
    print("Imports manuales recientes:")
    if latest_manual:
        for row in latest_manual:
            print(f"- {row['import_name']}: {row['records_count']} {row['data_type']} - {row['imported_at']}")
    else:
        print("- Sin imports manuales")
    print()
    print("Presupuesto API:")
    print(f"- Usados hoy: {budget['used_today']}")
    print(f"- Restantes hoy: {budget['remaining_today']}")
    print(f"- Limite diario: {budget['daily_limit']}")
    print(f"- Cache habilitado: {'si' if budget['cache_enabled'] else 'no'}")
    print()
    print("Resumen de fuentes:")
    print(f"- Equipos manual/API: {manual_teams}/{api_teams}")
    print(f"- Fixtures manual/API: {manual_fixtures}/{api_fixtures}")
    print("StatsHub snapshots:")
    print(f"- Habilitado: {'si' if settings.statshub_enabled else 'no'}")
    print(f"- Snapshots: {statshub_snapshots}")
    print(f"- Items importados: {statshub_items}")
    print(f"- Ultimo estado: {latest_statshub['endpoint_name'] + ' ' + latest_statshub['status'] if latest_statshub else '-'}")
    print("- Nota: snapshot local solamente, sin requests live")
    print("StatsHub raw:")
    for label, table in [
        ("raw events", "statshub_raw_events"),
        ("raw teams", "statshub_raw_teams"),
        ("raw players", "statshub_raw_players"),
        ("raw player performance", "statshub_raw_player_performance"),
        ("raw referees", "statshub_raw_referees"),
        ("raw lineups", "statshub_raw_lineups"),
        ("raw team events", "statshub_raw_team_events"),
        ("raw extra stats", "statshub_raw_event_extra_stats"),
        ("world cup seed teams", "statshub_worldcup_teams"),
        ("world cup seed players", "statshub_worldcup_players"),
        ("raw player tournaments", "statshub_raw_player_tournaments"),
        ("raw world cup player performance", "statshub_raw_worldcup_player_performance"),
        ("raw team tournaments", "statshub_raw_team_tournaments"),
        ("raw team season events", "statshub_raw_team_season_events"),
    ]:
        print(f"- {label}: {counts.get(table, 0)}")
    print("SQLite local, 0 API")
    print("El dashboard y los modelos leen SQLite local y no consumen API.")


if __name__ == "__main__":
    main()
