from __future__ import annotations

import pandas as pd
import streamlit as st

from app.db.connection import get_connection


def read_sql(query: str) -> pd.DataFrame:
    with get_connection() as conn:
        return pd.read_sql_query(query, conn)


st.set_page_config(page_title="Mundial 2026", layout="wide")
st.title("Mundial 2026")
st.info("Datos leidos desde SQLite local. Este dashboard no consume requests de API.")

counts = read_sql(
    """
    SELECT
        (SELECT COUNT(*) FROM teams) AS teams,
        (SELECT COUNT(*) FROM fixtures) AS fixtures,
        (SELECT COUNT(*) FROM players) AS players,
        (SELECT COUNT(*) FROM odds_snapshots) AS odds,
        (SELECT COUNT(*) FROM manual_imports) AS manual_imports,
        (SELECT COUNT(*) FROM player_season_stats) AS player_season_stats,
        (SELECT COUNT(*) FROM player_model_features) AS player_model_features,
        (SELECT COUNT(*) FROM team_roster_features) AS team_roster_features,
        (SELECT COUNT(*) FROM external_player_stats) AS external_player_stats,
        (SELECT COUNT(*) FROM external_player_model_features) AS external_player_model_features,
        (SELECT COUNT(*) FROM statshub_prop_stats) AS statshub_prop_stats,
        (SELECT COUNT(*) FROM statshub_snapshots) AS statshub_snapshots,
        (SELECT COUNT(*) FROM statshub_snapshot_items) AS statshub_snapshot_items,
        (SELECT COUNT(*) FROM statshub_raw_events) AS statshub_raw_events,
        (SELECT COUNT(*) FROM statshub_raw_players) AS statshub_raw_players,
        (SELECT COUNT(*) FROM statshub_raw_player_performance) AS statshub_raw_player_performance,
        (SELECT COUNT(*) FROM statshub_worldcup_teams) AS statshub_worldcup_teams,
        (SELECT COUNT(*) FROM statshub_worldcup_players) AS statshub_worldcup_players,
        (SELECT MAX(finished_at) FROM sync_logs) AS latest_update
    """
)
row = counts.iloc[0].to_dict() if not counts.empty else {}
cols = st.columns(5)
cols[0].metric("Equipos", int(row.get("teams") or 0))
cols[1].metric("Partidos", int(row.get("fixtures") or 0))
cols[2].metric("Jugadores", int(row.get("players") or 0))
cols[3].metric("Cuotas", int(row.get("odds") or 0))
cols[4].metric("Ultima actualizacion", row.get("latest_update") or "-")
st.caption(f"Imports manuales: {int(row.get('manual_imports') or 0)}")
st.caption(
    "Player season stats: "
    f"{int(row.get('player_season_stats') or 0)} | "
    "Player features: "
    f"{int(row.get('player_model_features') or 0)} | "
    "Roster features: "
    f"{int(row.get('team_roster_features') or 0)}"
)
st.caption(
    "World Cup seed teams: "
    f"{int(row.get('statshub_worldcup_teams') or 0)} | "
    "seed players: "
    f"{int(row.get('statshub_worldcup_players') or 0)}"
)
st.caption(
    "StatsHub raw events: "
    f"{int(row.get('statshub_raw_events') or 0)} | "
    "raw players: "
    f"{int(row.get('statshub_raw_players') or 0)} | "
    "raw performance: "
    f"{int(row.get('statshub_raw_player_performance') or 0)}"
)
st.caption(
    "External stats: "
    f"{int(row.get('external_player_stats') or 0)} | "
    "External features: "
    f"{int(row.get('external_player_model_features') or 0)}"
)
st.caption(f"StatsHub props: {int(row.get('statshub_prop_stats') or 0)}")
st.caption(
    "StatsHub snapshots: "
    f"{int(row.get('statshub_snapshots') or 0)} | "
    "Snapshot items: "
    f"{int(row.get('statshub_snapshot_items') or 0)}"
)

st.subheader("Proximos partidos")
fixtures = read_sql(
    """
    SELECT
        date_utc AS fecha,
        home_team_name AS local,
        away_team_name AS visitante,
        status_short AS estado,
        COALESCE(venue_name, '') || CASE WHEN venue_city IS NOT NULL THEN ' - ' || venue_city ELSE '' END AS sede
    FROM fixtures
    WHERE date_utc IS NULL OR status_short IS NULL OR status_short NOT IN ('FT', 'AET', 'PEN')
    ORDER BY date_utc
    LIMIT 25
    """
)
st.dataframe(fixtures, use_container_width=True)

st.subheader("Cuotas disponibles")
odds = read_sql(
    """
    SELECT
        f.home_team_name || ' vs ' || f.away_team_name AS partido,
        o.bookmaker,
        o.market,
        o.selection,
        o.decimal_odds,
        o.implied_probability,
        o.snapshot_time
    FROM odds_snapshots o
    LEFT JOIN fixtures f
        ON f.provider = o.provider
       AND f.provider_fixture_id = o.provider_fixture_id
    ORDER BY o.snapshot_time DESC
    LIMIT 100
    """
)
st.dataframe(odds, use_container_width=True)

st.subheader("Roster features")
roster = read_sql(
    """
    SELECT team_name, squad_size, avg_age, goalkeepers_count, defenders_count,
           midfielders_count, attackers_count, unknown_position_count, updated_at
    FROM team_roster_features
    ORDER BY team_name
    LIMIT 100
    """
)
st.dataframe(roster, use_container_width=True)

st.subheader("Player model features")
player_features = read_sql(
    """
    SELECT player_name, season, total_minutes, total_goals, total_assists,
           shots_per_90, goals_per_90, assists_per_90, updated_at
    FROM player_model_features
    ORDER BY total_minutes DESC
    LIMIT 100
    """
)
st.dataframe(player_features, use_container_width=True)

st.subheader("Datos externos")
st.info("Estos datos vienen de CSV locales/manuales y no consumen API.")
imports = read_sql(
    """
    SELECT source_name, file_path, rows_imported, rows_skipped, status, imported_at
    FROM external_dataset_imports
    ORDER BY id DESC
    LIMIT 20
    """
)
st.dataframe(imports, use_container_width=True)
external_features = read_sql(
    """
    SELECT source_name, season, player_name, team_name, total_minutes,
           total_goals, total_assists, goals_per_90, xg_per_90, xa_per_90
    FROM external_player_model_features
    ORDER BY total_minutes DESC
    LIMIT 100
    """
)
st.dataframe(external_features, use_container_width=True)

st.subheader("StatsHub props")
st.info("StatsHub no esta configurado como API. Solo se usan datos guardados/importados manualmente.")
statshub = read_sql(
    """
    SELECT season, competition, market, player_name, team_name, opponent_name,
           line, hit_rate, average_value, last_n_games, odds, stat_value, imported_at
    FROM statshub_prop_stats
    ORDER BY imported_at DESC
    LIMIT 100
    """
)
st.dataframe(statshub, use_container_width=True)

st.subheader("StatsHub snapshots")
st.info("Estos datos vienen de snapshots locales. El dashboard no llama a StatsHub.")
snapshots = read_sql(
    """
    SELECT snapshot_name, endpoint_name, status, status_code, rows_detected, raw_file_path, created_at
    FROM statshub_snapshots
    ORDER BY id DESC
    LIMIT 50
    """
)
st.dataframe(snapshots, use_container_width=True)
snapshot_items = read_sql(
    """
    SELECT item_type, COUNT(*) AS rows_count
    FROM statshub_snapshot_items
    GROUP BY item_type
    ORDER BY rows_count DESC
    """
)
st.dataframe(snapshot_items, use_container_width=True)

st.subheader("StatsHub raw data only")
raw_events = read_sql(
    """
    SELECT event_id, endpoint_name, snapshot_name, imported_at
    FROM statshub_raw_events
    ORDER BY id DESC
    LIMIT 50
    """
)
st.dataframe(raw_events, use_container_width=True)
raw_players = read_sql(
    """
    SELECT player_id, player_name, team_id, team_name, event_id, endpoint_name, imported_at
    FROM statshub_raw_players
    ORDER BY id DESC
    LIMIT 50
    """
)
st.dataframe(raw_players, use_container_width=True)
