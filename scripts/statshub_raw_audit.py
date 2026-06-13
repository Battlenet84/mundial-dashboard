from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.config.settings import get_settings


EXPECTED_TABLES = [
    "statshub_snapshots",
    "statshub_snapshot_items",
    "statshub_raw_events",
    "statshub_raw_teams",
    "statshub_raw_players",
    "statshub_raw_player_performance",
    "statshub_raw_referees",
    "statshub_raw_lineups",
    "statshub_raw_team_events",
    "statshub_raw_event_extra_stats",
]

ID_COLUMNS = ["event_id", "team_id", "player_id", "referee_id"]
GROUP_COLUMNS = ["endpoint_name", "snapshot_name"]


def get_database_path() -> Path:
    return Path(get_settings().database_path)


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def open_readonly_connection(db_path: Path | None = None) -> sqlite3.Connection | None:
    path = Path(db_path or get_database_path())
    if not path.exists():
        return None
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [str(row["name"]) for row in rows]


def get_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()
    return [str(row["name"]) for row in rows]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0])


def count_by_column(conn: sqlite3.Connection, table: str, column: str) -> list[tuple[Any, int]]:
    table_q = quote_identifier(table)
    column_q = quote_identifier(column)
    rows = conn.execute(
        f"""
        SELECT {column_q} AS value, COUNT(*) AS total
        FROM {table_q}
        GROUP BY {column_q}
        ORDER BY total DESC, value
        """
    ).fetchall()
    return [(row["value"], int(row["total"])) for row in rows]


def missing_id_count(conn: sqlite3.Connection, table: str, column: str) -> int:
    table_q = quote_identifier(table)
    column_q = quote_identifier(column)
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {table_q}
            WHERE {column_q} IS NULL OR TRIM(CAST({column_q} AS TEXT)) = ''
            """
        ).fetchone()[0]
    )


def duplicate_id_count(conn: sqlite3.Connection, table: str, column: str) -> int:
    table_q = quote_identifier(table)
    column_q = quote_identifier(column)
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT {column_q}
                FROM {table_q}
                WHERE {column_q} IS NOT NULL AND TRIM(CAST({column_q} AS TEXT)) != ''
                GROUP BY {column_q}
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )


def invalid_raw_json_count(conn: sqlite3.Connection, table: str) -> int:
    total = 0
    for row in conn.execute(
        f"SELECT raw_json FROM {quote_identifier(table)} WHERE raw_json IS NOT NULL"
    ):
        raw = row["raw_json"]
        if raw is None or str(raw).strip() == "":
            continue
        try:
            json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            total += 1
    return total


def latest_rows(conn: sqlite3.Connection, table: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(
            f"SELECT * FROM {quote_identifier(table)} ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            f"SELECT * FROM {quote_identifier(table)} LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def build_audit_lines(db_path: Path | None = None) -> list[str]:
    path = Path(db_path or get_database_path())
    lines = [
        "Auditoria local StatsHub raw",
        f"DB path: {path}",
        "Este comando no consume API ni hace requests externos.",
    ]
    conn = open_readonly_connection(path)
    if conn is None:
        lines.extend(
            [
                "Base SQLite no encontrada. Lectura omitida.",
                "Tablas StatsHub existentes: ninguna",
                "Tablas esperadas faltantes:",
                *[f"- {table}: table not found" for table in EXPECTED_TABLES],
            ]
        )
        return lines

    with conn:
        tables = list_tables(conn)
        statshub_tables = [table for table in tables if table.startswith("statshub_")]
        existing_expected = [table for table in EXPECTED_TABLES if table in tables]
        missing_expected = [table for table in EXPECTED_TABLES if table not in tables]

        lines.append("Tablas StatsHub existentes:")
        lines.extend([f"- {table}" for table in statshub_tables] or ["- ninguna"])
        lines.append("Tablas esperadas faltantes:")
        lines.extend([f"- {table}: table not found" for table in missing_expected] or ["- ninguna"])

        lines.append("Conteo de filas por tabla:")
        for table in EXPECTED_TABLES:
            if table not in tables:
                lines.append(f"- {table}: table not found")
                continue
            lines.append(f"- {table}: {count_rows(conn, table)}")

        for table in existing_expected:
            columns = get_columns(conn, table)
            lines.append(f"Detalle: {table}")
            for column in GROUP_COLUMNS:
                if column in columns:
                    lines.append(f"- Filas por {column}:")
                    grouped = count_by_column(conn, table, column)
                    lines.extend([f"  - {value}: {total}" for value, total in grouped] or ["  - sin datos"])
            for column in ID_COLUMNS:
                if column in columns:
                    lines.append(f"- IDs faltantes {column}: {missing_id_count(conn, table, column)}")
                    lines.append(f"- IDs duplicados {column}: {duplicate_id_count(conn, table, column)}")
            if "raw_json" in columns:
                lines.append(f"- raw_json invalido: {invalid_raw_json_count(conn, table)}")
            lines.append("- Ultimas 10 filas:")
            rows = latest_rows(conn, table, 10)
            if not rows:
                lines.append("  - sin datos")
            for row in rows:
                lines.append(f"  - {row}")

    return lines


def main() -> None:
    print("\n".join(build_audit_lines()))


if __name__ == "__main__":
    main()
