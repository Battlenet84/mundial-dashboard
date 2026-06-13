from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from scripts.statshub_raw_audit import (
    duplicate_id_count,
    get_columns,
    get_database_path,
    invalid_raw_json_count,
    list_tables,
    missing_id_count,
    open_readonly_connection,
    quote_identifier,
)


ID_COLUMNS = ["event_id", "team_id", "player_id", "referee_id"]


def load_table(conn, table: str, limit: int) -> pd.DataFrame:
    return pd.read_sql_query(
        f"SELECT * FROM {quote_identifier(table)} LIMIT ?",
        conn,
        params=(limit,),
    )


def filter_dataframe(df: pd.DataFrame, text: str) -> pd.DataFrame:
    query = text.strip().lower()
    if not query or df.empty:
        return df
    string_columns = [
        column
        for column in df.columns
        if pd.api.types.is_object_dtype(df[column]) or pd.api.types.is_string_dtype(df[column])
    ]
    if not string_columns:
        return df.iloc[0:0]
    mask = pd.Series(False, index=df.index)
    for column in string_columns:
        mask = mask | df[column].fillna("").astype(str).str.lower().str.contains(query, regex=False)
    return df[mask]


def render_raw_json(df: pd.DataFrame) -> None:
    if "raw_json" not in df.columns or df.empty:
        return
    st.subheader("raw_json")
    raw_values = [value for value in df["raw_json"].tolist() if value]
    if not raw_values:
        st.info("No hay raw_json para mostrar.")
        return
    selected = st.selectbox("Fila raw_json", range(len(raw_values)), format_func=lambda idx: f"raw_json #{idx + 1}")
    raw = raw_values[selected]
    try:
        st.json(json.loads(raw))
    except (TypeError, json.JSONDecodeError):
        st.code(str(raw), language="text")


def render_quality(conn, table: str, columns: list[str]) -> None:
    st.subheader("Data quality")
    metrics = []
    for column in ID_COLUMNS:
        if column in columns:
            metrics.append(
                {
                    "columna": column,
                    "ids_faltantes": missing_id_count(conn, table, column),
                    "ids_duplicados": duplicate_id_count(conn, table, column),
                }
            )
    if metrics:
        st.dataframe(pd.DataFrame(metrics), use_container_width=True)
    else:
        st.info("La tabla no tiene columnas ID conocidas.")
    if "raw_json" in columns:
        st.metric("raw_json invalido", invalid_raw_json_count(conn, table))


def main() -> None:
    st.set_page_config(page_title="StatsHub raw browser", layout="wide")
    st.title("StatsHub raw browser local")
    db_path = get_database_path()
    st.caption(f"SQLite: {db_path}")
    st.caption("Lectura local solamente. No consume API ni hace requests externos.")

    conn = open_readonly_connection(db_path)
    if conn is None:
        st.info("Base SQLite no encontrada. Ejecuta el importador local cuando este listo y vuelve a abrir esta vista.")
        return

    with conn:
        tables = [table for table in list_tables(conn) if table.startswith("statshub_")]
        if not tables:
            st.info("No hay tablas statshub_* todavia. La vista queda lista para cuando termine la importacion raw.")
            return

        table = st.sidebar.selectbox("Tabla", tables)
        limit = st.sidebar.selectbox("Limite de filas", [50, 100, 250, 500, 1000, 5000], index=1)
        search = st.sidebar.text_input("Buscar")

        columns = get_columns(conn, table)
        total_rows = conn.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0]
        st.metric("Filas", total_rows)
        st.write("Columnas")
        st.code(", ".join(columns), language="text")

        df = load_table(conn, table, limit)
        filtered = filter_dataframe(df, search)
        st.dataframe(filtered, use_container_width=True)
        st.download_button(
            "Descargar CSV filtrado",
            filtered.to_csv(index=False).encode("utf-8"),
            file_name=f"{table}.csv",
            mime="text/csv",
        )
        render_raw_json(filtered)
        render_quality(conn, table, columns)


if __name__ == "__main__":
    main()
