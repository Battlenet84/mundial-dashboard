"""
Odds-driven betting value dashboard — multi-match edition.

Run:
    streamlit run app/dashboard/betting_value_dashboard.py
"""
from __future__ import annotations

from pathlib import Path as _Path
import sys as _sys

_PROJECT_ROOT = _Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

import os
import pathlib
import sqlite3
import sys

import pandas as pd
import streamlit as st

from app.betting.odds_driven import (
    DB_PATH,
    OUT_DIR,
    PRIORITY_CLASS_MAP,
    calculate_ev,
    connect,
    insert_raw_rows,
    normalize_raw_odds,
    raw_rows_from_manual_file,
    write_actual_odds_template,
    write_scores_workbook,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KNOWN_RUNS = [
    "today_4_matches_live_api_odds_probe",
    "usa_paraguay_live_api_odds_probe",
    "canada_bosnia_all_available_api_markets_probe",
    "canada_bosnia_live_api_odds_probe",
    "manual_actual_odds",
    "odds_api_io_cache",
]

KNOWN_MATCHES = [
    "Qatar vs Switzerland",
    "Brazil vs Morocco",
    "Haiti vs Scotland",
    "Australia vs Turkey",
    "United States vs Paraguay",
    "Canada vs Bosnia and Herzegovina",
]

HARD_DATA_MARKETS = tuple(
    m for m, cls in PRIORITY_CLASS_MAP.items() if cls == "hard_data_priority"
)
MEDIUM_PRIORITY_MARKETS = tuple(
    m for m, cls in PRIORITY_CLASS_MAP.items() if cls == "medium_priority"
)


def get_con() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


@st.cache_data(ttl=10)
def qdf(sql: str, params: tuple = ()) -> pd.DataFrame:
    with get_con() as con:
        return pd.read_sql_query(sql, con, params=params)


def table_exists(name: str) -> bool:
    with get_con() as con:
        row = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
    return row is not None


def table_columns(name: str) -> set[str]:
    if not table_exists(name):
        return set()
    try:
        with get_con() as con:
            return {row["name"] for row in con.execute(f"PRAGMA table_info({name})").fetchall()}
    except Exception:
        return set()


def _table_where_clause(
    table: str,
    run_filter: str | None,
    match_filter: str | None,
    alias: str | None = None,
) -> tuple[str, list]:
    cols = table_columns(table)
    prefix = f"{alias}." if alias else ""
    parts = []
    params: list = []
    if run_filter and run_filter != "(all)" and "run_name" in cols:
        parts.append(f"{prefix}run_name=?")
        params.append(run_filter)
    if match_filter and match_filter != "(all)" and "match_name" in cols:
        parts.append(f"{prefix}match_name=?")
        params.append(match_filter)
    return ("WHERE " + " AND ".join(parts)) if parts else "", params


def safe_count(table: str, where: str = "1=1", params: tuple | list | None = None) -> int:
    if not table_exists(table):
        return 0
    try:
        p = tuple(params) if params is not None else ()
        return int(qdf(f"SELECT COUNT(*) n FROM {table} WHERE {where}", p).iloc[0]["n"])
    except Exception:
        return 0


def available_runs() -> list[str]:
    if not table_exists("betting_odds_raw"):
        return KNOWN_RUNS
    df = qdf(
        "SELECT DISTINCT run_name FROM betting_odds_raw "
        "WHERE run_name IS NOT NULL ORDER BY run_name DESC"
    )
    runs = df["run_name"].tolist() if not df.empty else []
    for r in KNOWN_RUNS:
        if r not in runs:
            runs.append(r)
    return runs


def available_matches(run_filter: str | None = None) -> list[str]:
    if not table_exists("betting_odds_raw"):
        return KNOWN_MATCHES
    where = "run_name=? AND match_name IS NOT NULL" if run_filter and run_filter != "(all)" else "match_name IS NOT NULL"
    params = (run_filter,) if run_filter and run_filter != "(all)" else ()
    df = qdf(f"SELECT DISTINCT match_name FROM betting_odds_raw WHERE {where} ORDER BY match_name", params)
    matches = df["match_name"].tolist() if not df.empty else []
    for m in KNOWN_MATCHES:
        if m not in matches:
            matches.append(m)
    return matches


def _ingest_upload(uploaded) -> int:
    suffix = pathlib.Path(uploaded.name).suffix
    tmp = OUT_DIR / f"_uploaded_actual_odds{suffix}"
    tmp.write_bytes(uploaded.getvalue())
    rows = raw_rows_from_manual_file(tmp)
    with connect() as con:
        insert_raw_rows(con, rows, replace=True)
        normalize_raw_odds(con, replace=True)
        calculate_ev(con, replace=True)
        write_scores_workbook(con)
    st.cache_data.clear()
    return len(rows)


def _fmt_pct(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.1%}"


def safe_columns(df: pd.DataFrame, columns: list[str]) -> list[str]:
    return [c for c in columns if c in df.columns]


def show_table_or_info(df: pd.DataFrame | None, label: str = "data") -> None:
    if df is None or df.empty:
        st.info(f"No rows available for {label}.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def _get_app_password() -> str:
    """Optional password gate for public deploys. Empty means public app."""
    env_password = os.getenv("APP_PASSWORD", "").strip()
    if env_password:
        return env_password
    try:
        return str(st.secrets.get("APP_PASSWORD", "") or "").strip()
    except Exception:
        return ""


def require_optional_password() -> None:
    expected = _get_app_password()
    if not expected:
        return
    if st.session_state.get("authenticated") is True:
        return
    st.subheader("Acceso privado")
    password = st.text_input("Password", type="password")
    if password == expected:
        st.session_state["authenticated"] = True
        st.rerun()
    elif password:
        st.error("Password incorrecta.")
    st.stop()


def _clean_label_value(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"none", "nan", "null"}:
        return ""
    return text


def _format_line(value) -> str:
    if value is None or pd.isna(value):
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return _clean_label_value(value)
    if numeric.is_integer():
        return f"{numeric:.1f}"
    return f"{numeric:g}"


def _readable_market_name(row: pd.Series) -> str:
    raw_market = _clean_label_value(row.get("raw_market_name"))
    if raw_market:
        return raw_market

    market = _clean_label_value(
        row.get("canonical_market_type")
        or row.get("market_type")
    )
    market_labels = {
        "player_shots_on_target": "Player Shots on Target",
        "player_total_shots": "Player Shots",
        "player_assists": "Player Assists",
        "player_tackles": "Player Tackles",
        "player_passes": "Player Passes",
        "team_total_shots": "Team Total Shots",
        "team_shots_on_target": "Team Shots on Target",
        "match_total_goals": "Total Goals",
        "match_result": "Match Result",
    }
    return market_labels.get(market, market.replace("_", " ").title() if market else "Bet")


def _build_bet_label(row: pd.Series) -> str:
    existing = _clean_label_value(row.get("bet_description"))
    if existing:
        return existing

    subject = (
        _clean_label_value(row.get("player_name"))
        or _clean_label_value(row.get("team_name"))
        or _clean_label_value(row.get("raw_selection_name"))
        or _clean_label_value(row.get("selection"))
    )
    market = _readable_market_name(row)
    side = _clean_label_value(row.get("side")).title()
    line = _format_line(row.get("line"))

    parts = [p for p in [market, side, line] if p]
    detail = " ".join(parts).strip()
    if subject and detail:
        return f"{subject} — {detail}"
    return subject or detail or "-"


def _first_existing_numeric_column(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    for col in candidates:
        if col in df.columns:
            return pd.to_numeric(df[col], errors="coerce")
    return pd.Series([pd.NA] * len(df), index=df.index, dtype="Float64")


def _probability_to_percent(series: pd.Series) -> pd.Series:
    """Return a probability series in percentage points for display.

    Internal model columns are normally 0-1 probabilities. Some imported/manual
    sources can already store hit rates as 0-100 values, so keep those as-is.
    """
    out = pd.to_numeric(series, errors="coerce")
    non_null = out.dropna()
    if non_null.empty:
        return out
    if non_null.abs().max() <= 1.0:
        return out * 100.0
    return out


def _empirical_probability_column(df: pd.DataFrame) -> pd.Series:
    """Best available empirical hit-rate for the clean VALUE table.

    Prefer explicit empirical/hit-rate columns. If the current dataset only has
    model_probability, use it as the empirical probability because this pipeline
    computes model_probability from historical frequency samples.
    """
    explicit_candidates = [
        "empirical_probability",
        "historical_hit_rate",
        "hit_rate",
        "success_rate",
        "observed_probability",
    ]
    for col in explicit_candidates:
        if col in df.columns:
            return _probability_to_percent(df[col])

    ratio_candidates = [
        ("valid_hit_count", "valid_appearance_count"),
        ("hit_count", "sample_size"),
        ("success_count", "sample_size"),
        ("observed_hit_count", "sample_size"),
    ]
    for hit_col, sample_col in ratio_candidates:
        if hit_col in df.columns and sample_col in df.columns:
            hits = pd.to_numeric(df[hit_col], errors="coerce")
            sample = pd.to_numeric(df[sample_col], errors="coerce")
            return (hits / sample.replace(0, pd.NA)) * 100.0

    # In this project model_probability is the historical-frequency probability
    # produced by calculate_probability(), so it is the best available empirical
    # probability when no separate hit-rate column is persisted.
    if "model_probability" in df.columns:
        return _probability_to_percent(df["model_probability"])

    return pd.Series([pd.NA] * len(df), index=df.index, dtype="Float64")


def build_value_display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Build the clean user-facing VALUE table without changing the internal dataframe."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["Partido", "Apuesta", "Cuota Bet", "Prob. Empírica", "EV", "Sample Size"])

    display = pd.DataFrame(index=df.index)
    display["Partido"] = df["match_name"] if "match_name" in df.columns else ""
    display["Apuesta"] = df.apply(_build_bet_label, axis=1)
    display["Cuota Bet"] = _first_existing_numeric_column(df, ["odds_decimal"])
    display["Prob. Empírica"] = _empirical_probability_column(df)
    display["EV"] = _first_existing_numeric_column(df, ["expected_value", "ev"])
    display["Sample Size"] = _first_existing_numeric_column(
        df,
        [
            "sample_size",
            "valid_appearance_count",
            "player_sample_size",
            "appearance_count",
            "model_sample_size",
        ],
    ).round().astype("Int64")

    display = display[["Partido", "Apuesta", "Cuota Bet", "Prob. Empírica", "EV", "Sample Size"]]
    if "EV" in display.columns:
        display = display.sort_values("EV", ascending=False, na_position="last")
    return display.reset_index(drop=True)


def show_value_display_table(df: pd.DataFrame) -> None:
    display_df = build_value_display_df(df)
    if display_df.empty:
        st.info("No rows available for EV Ranking.")
        return

    try:
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Partido": st.column_config.TextColumn("Partido"),
                "Apuesta": st.column_config.TextColumn("Apuesta", width="large"),
                "Cuota Bet": st.column_config.NumberColumn("Cuota Bet", format="%.2f"),
                "Prob. Empírica": st.column_config.NumberColumn("Prob. Empírica", format="%.2f%%"),
                "EV": st.column_config.NumberColumn("EV", format="%.3f"),
                "Sample Size": st.column_config.NumberColumn("Sample Size", format="%d"),
            },
        )
    except Exception:
        st.dataframe(display_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Sidebar helpers
# ---------------------------------------------------------------------------

def _run_where_clause(run_filter: str | None, match_filter: str | None) -> tuple[str, list]:
    parts = []
    params: list = []
    if run_filter and run_filter != "(all)":
        parts.append("run_name=?")
        params.append(run_filter)
    if match_filter and match_filter != "(all)":
        parts.append("match_name=?")
        params.append(match_filter)
    return ("WHERE " + " AND ".join(parts)) if parts else "", params


def blocked_odds_mismatch_count(run_filter: str | None, match_filter: str | None) -> int:
    if not table_exists("betting_value_scores_new"):
        return 0
    try:
        if "normalized_status" not in table_columns("betting_value_scores_new"):
            return 0
        where, params = _table_where_clause("betting_value_scores_new", run_filter, match_filter)
        clause = "normalized_status='BLOCKED_ODDS_MISMATCH'"
        sql = (
            "SELECT COUNT(*) AS n FROM betting_value_scores_new "
            + (f"{where} AND {clause}" if where else f"WHERE {clause}")
        )
        with get_con() as con:
            return int(con.execute(sql, params).fetchone()["n"])
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Tab: EV Ranking
# ---------------------------------------------------------------------------

_COMPLETE_MATCHES_SET = {"Haiti vs Scotland", "Australia vs Turkey", "Brazil vs Morocco"}
_PARTIAL_MATCHES_SET  = {"Qatar vs Switzerland"}


def page_ev_ranking(
    run_filter: str | None, match_filter: str | None,
    market_scope_filter: str, market_type_filter: str | None,
    min_model_prob: float, min_ss: int, min_ev: float,
    max_odds: float | None, incl_review_mp: bool,
    completeness_filter: str = "all",
) -> None:
    st.header("EV Ranking")
    st.caption("Live/API bookmaker markets → EV calculation. Defaults show actionable rows only.")

    if not table_exists("betting_value_scores_new"):
        st.info("No scores yet. Run the fetch script first.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        only_value = st.checkbox("VALUE bets only", value=True)
        priority_filter = st.selectbox(
            "Priority class",
            ["hard_data + medium", "hard_data only", "all"],
            index=0,
        )
    with col2:
        show_team = st.checkbox("Show team markets", value=True)
        show_player = st.checkbox("Show player markets", value=True)
    with col3:
        show_match = st.checkbox("Show match-level markets", value=True)
        include_review_markets = st.checkbox("Include REVIEW markets", value=False)

    where_parts = [
        "expected_value IS NOT NULL",
        "probability_status='ok'",
    ]
    params: list = []

    if run_filter and run_filter != "(all)":
        where_parts.append("source_name='Odds-API.io'")  # optional — source is always API here
    if match_filter and match_filter != "(all)":
        where_parts.append("match_name=?")
        params.append(match_filter)
    if only_value:
        where_parts.extend([
            "verdict='VALUE'",
            "expected_value > 0",
            "market_mapping_status='OK'",
            "exact_market_match=1",
            "COALESCE(model_uses_proxy,0)=0",
            "COALESCE(field_mapping_status,'OK') NOT IN ('WRONG','MISSING_FIELD')",
            "COALESCE(side_line_status,'OK')='OK'",
        ])
    elif not include_review_markets:
        where_parts.append("COALESCE(market_mapping_status,'OK') != 'REVIEW'")
    if min_ev > 0:
        where_parts.append(f"expected_value > {min_ev}")
    if min_ss > 1:
        where_parts.append(f"sample_size >= {min_ss}")
    if not incl_review_mp:
        where_parts.append(
            "(minutes_filter_status IS NULL"
            " OR minutes_filter_status IN ('ok','not_applicable','fallback_raw_json'))"
        )

    try:
        df = qdf(
            f"""
            SELECT rank, match_name, bookmaker, market_type, raw_market_name,
                   raw_selection_name, market_scope, priority_class, bet_description,
                   team_name, player_name, side, line, odds_decimal,
                   implied_probability, model_probability, edge, expected_value,
                   sample_size, valid_appearance_count, excluded_low_minutes_count,
                   min_minutes_filter, minutes_filter_status,
                   data_quality_status, market_mapping_status,
                   exact_market_match, data_completeness_status,
                   field_mapping_status, side_line_status,
                   verdict, notes
            FROM betting_value_scores_new
            WHERE {' AND '.join(where_parts)}
            ORDER BY expected_value DESC
            """,
            tuple(params),
        )
    except Exception as exc:
        st.error(f"EV Ranking query failed: {exc}")
        return

    rows_before = len(df)

    # Priority class filter
    if priority_filter != "all" and not df.empty and "priority_class" in df.columns:
        if priority_filter == "hard_data only":
            df = df[df["priority_class"] == "hard_data_priority"]
        else:
            df = df[df["priority_class"].isin(["hard_data_priority", "medium_priority"])]

    # Market scope filter
    if market_scope_filter != "all" and not df.empty and "market_scope" in df.columns:
        df = df[df["market_scope"] == market_scope_filter]
    if not show_team and not df.empty and "market_scope" in df.columns:
        df = df[df["market_scope"] != "team"]
    if not show_player and not df.empty and "market_scope" in df.columns:
        df = df[df["market_scope"] != "player"]
    if not show_match and not df.empty and "market_scope" in df.columns:
        df = df[df["market_scope"] != "match"]

    # Market type filter
    if market_type_filter and market_type_filter != "(all)" and not df.empty:
        df = df[df["market_type"] == market_type_filter]

    # Model prob filter
    if not df.empty and "model_probability" in df.columns and min_model_prob > 0.0:
        df = df[df["model_probability"] >= min_model_prob]

    # Max odds filter
    if max_odds is not None and not df.empty and "odds_decimal" in df.columns:
        df = df[df["odds_decimal"] <= max_odds]

    # Data completeness filter
    if completeness_filter == "COMPLETE only" and not df.empty and "match_name" in df.columns:
        df = df[df["match_name"].isin(_COMPLETE_MATCHES_SET)]
    elif completeness_filter == "PARTIAL only" and not df.empty and "match_name" in df.columns:
        df = df[df["match_name"].isin(_PARTIAL_MATCHES_SET)]

    rows_after = len(df)

    mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
    mc1.metric("Before filters", rows_before)
    mc2.metric("After filters", rows_after)
    mc3.metric("VALUE rows", int((df["verdict"] == "VALUE").sum()) if not df.empty and "verdict" in df.columns else 0)
    avg_p = df["model_probability"].mean() if not df.empty and "model_probability" in df.columns else None
    mc4.metric("Avg model prob", f"{avg_p:.1%}" if avg_p is not None and pd.notna(avg_p) else "-")
    max_ev_val = df["expected_value"].max() if not df.empty and "expected_value" in df.columns else None
    mc5.metric("Max EV", f"{max_ev_val:.3f}" if max_ev_val is not None and pd.notna(max_ev_val) else "-")
    med_odds = df["odds_decimal"].median() if not df.empty and "odds_decimal" in df.columns else None
    mc6.metric("Median odds", f"{med_odds:.2f}" if med_odds is not None and pd.notna(med_odds) else "-")

    show_value_display_table(df)


# ---------------------------------------------------------------------------
# Tab: Match Coverage
# ---------------------------------------------------------------------------

def show_qatar_switzerland_diagnostics() -> None:
    st.divider()
    st.subheader("Qatar vs Switzerland diagnostics")
    match = "Qatar vs Switzerland"

    if not table_exists("betting_odds_normalized"):
        st.warning("No normalized odds table available for Qatar diagnostics.")
        return

    norm_cols = table_columns("betting_odds_normalized")
    score_cols = table_columns("betting_value_scores_new")
    metrics: list[dict[str, object]] = []
    details: list[tuple[str, pd.DataFrame]] = []

    try:
        normalized_by_match = qdf(
            """
            SELECT match_name, COUNT(*) AS normalized_rows
            FROM betting_odds_normalized
            GROUP BY match_name
            ORDER BY match_name
            """
        )
        details.append(("Normalized odds by match", normalized_by_match))
        metrics.append({
            "check": "odds normalizadas por match",
            "count": int(normalized_by_match.loc[
                normalized_by_match["match_name"] == match, "normalized_rows"
            ].sum()) if not normalized_by_match.empty else 0,
        })
    except Exception as exc:
        st.warning(f"Qatar normalized count unavailable: {exc}")

    try:
        by_type = qdf(
            """
            SELECT market_type, COUNT(*) AS rows
            FROM betting_odds_normalized
            WHERE match_name=?
            GROUP BY market_type
            ORDER BY rows DESC
            """,
            (match,),
        )
        details.append(("Qatar count by market_type", by_type))
    except Exception as exc:
        st.warning(f"Qatar market_type count unavailable: {exc}")

    if "market_mapping_status" in norm_cols:
        try:
            by_mapping = qdf(
                """
                SELECT market_mapping_status, COUNT(*) AS rows
                FROM betting_odds_normalized
                WHERE match_name=?
                GROUP BY market_mapping_status
                ORDER BY rows DESC
                """,
                (match,),
            )
            details.append(("Qatar count by market_mapping_status", by_mapping))
        except Exception as exc:
            st.warning(f"Qatar market mapping count unavailable: {exc}")
    else:
        st.warning("Qatar diagnostics: betting_odds_normalized.market_mapping_status missing.")

    try:
        player_props = safe_count("betting_odds_normalized", "match_name=? AND market_type LIKE 'player_%'", (match,))
        player_with_id = safe_count(
            "betting_odds_normalized",
            "match_name=? AND market_type LIKE 'player_%' AND player_id IS NOT NULL AND player_id != ''",
            (match,),
        )
        metrics.extend([
            {"check": "player props", "count": player_props},
            {"check": "player props with player_id", "count": player_with_id},
        ])
    except Exception as exc:
        st.warning(f"Qatar player prop counts unavailable: {exc}")

    if table_exists("betting_value_scores_new"):
        metric_specs = [
            ("model_probability rows", "model_probability IS NOT NULL"),
            ("EV rows", "expected_value IS NOT NULL"),
            ("VALUE rows", "verdict='VALUE'"),
        ]
        for label, condition in metric_specs:
            if all(col in score_cols for col in ["match_name", condition.split()[0].split("=")[0]] if col):
                metrics.append({
                    "check": label,
                    "count": safe_count("betting_value_scores_new", f"match_name=? AND {condition}", (match,)),
                })
        if "verdict" not in score_cols:
            st.warning("Qatar diagnostics: betting_value_scores_new.verdict missing.")
        if "model_probability" not in score_cols:
            st.warning("Qatar diagnostics: betting_value_scores_new.model_probability missing.")
        if "expected_value" not in score_cols:
            st.warning("Qatar diagnostics: betting_value_scores_new.expected_value missing.")
    else:
        st.warning("Qatar diagnostics: betting_value_scores_new missing.")

    show_table_or_info(pd.DataFrame(metrics), "Qatar diagnostics summary")
    for label, df in details:
        st.caption(label)
        show_table_or_info(df, label)


def page_match_coverage(run_filter: str | None, match_filter: str | None) -> None:
    st.header("Match Coverage")
    st.caption("Raw odds rows and EV coverage per match.")
    if not table_exists("betting_odds_raw"):
        st.info("No odds data loaded.")
        return

    wh, p = _run_where_clause(run_filter, match_filter)
    # Per-match raw counts
    try:
        raw_df = qdf(
            f"""
            SELECT match_name, bookmaker,
                   COUNT(*) as raw_rows,
                   COUNT(DISTINCT raw_market_name) as distinct_markets
            FROM betting_odds_raw {wh}
            GROUP BY match_name, bookmaker
            ORDER BY match_name
            """,
            tuple(p),
        )
        st.subheader("Raw odds by match")
        show_table_or_info(raw_df, "raw odds by match")
    except Exception as exc:
        st.error(f"Raw count query failed: {exc}")

    # Per-match EV counts
    try:
        ev_df = qdf(
            f"""
            SELECT match_name, priority_class, verdict, COUNT(*) as rows
            FROM betting_value_scores_new
            {"WHERE match_name=?" if match_filter and match_filter != "(all)" else ""}
            GROUP BY match_name, priority_class, verdict
            ORDER BY match_name, priority_class
            """,
            (match_filter,) if match_filter and match_filter != "(all)" else (),
        )
        st.subheader("EV breakdown by match")
        show_table_or_info(ev_df, "EV by match")
    except Exception as exc:
        st.error(f"EV match count query failed: {exc}")

    # Market group coverage
    try:
        mg_df = qdf(
            f"""
            SELECT match_name,
                   CASE
                       WHEN market_type LIKE 'player_%' THEN 'player'
                       WHEN market_type LIKE 'team_%' THEN 'team'
                       ELSE 'match'
                   END AS market_scope,
                   market_type,
                   COUNT(*) as rows,
                   COUNT(DISTINCT player_name) as distinct_players
            FROM betting_odds_normalized
            {"WHERE match_name=?" if match_filter and match_filter != "(all)" else ""}
            GROUP BY match_name,
                     CASE
                         WHEN market_type LIKE 'player_%' THEN 'player'
                         WHEN market_type LIKE 'team_%' THEN 'team'
                         ELSE 'match'
                     END,
                     market_type
            ORDER BY match_name, rows DESC
            """,
            (match_filter,) if match_filter and match_filter != "(all)" else (),
        )
        st.subheader("Market types by match")
        show_table_or_info(mg_df, "market types by match")
    except Exception as exc:
        st.error(f"Market group query failed: {exc}")

    show_qatar_switzerland_diagnostics()

    # StatsHub coverage panel
    st.divider()
    st.subheader("StatsHub data completeness (today's 4 matches)")
    coverage_data = [
        {"match": "Qatar vs Switzerland", "home_team": "Qatar", "away_team": "Switzerland",
         "home_perf": 50, "away_perf": 50,
         "home_conf_players": 17, "away_conf_players": 26,
         "home_player_events_min15": 115, "away_player_events_min15": 340,
         "status": "PARTIAL", "note": "Qatar: 17/26 confirmed (9 Arabic names unresolved). Swiss: 26/26."},
        {"match": "Brazil vs Morocco", "home_team": "Brazil", "away_team": "Morocco",
         "home_perf": 50, "away_perf": 50,
         "home_conf_players": 26, "away_conf_players": 23,
         "home_player_events_min15": 1057, "away_player_events_min15": 678,
         "status": "COMPLETE", "note": "26/26 Brazil, 23/26 Morocco — full prop coverage"},
        {"match": "Haiti vs Scotland", "home_team": "Haiti", "away_team": "Scotland",
         "home_perf": 50, "away_perf": 50,
         "home_conf_players": 25, "away_conf_players": 25,
         "home_player_events_min15": 324, "away_player_events_min15": 248,
         "status": "COMPLETE", "note": "25/26 Haiti, 25/26 Scotland — global parser fix applied"},
        {"match": "Australia vs Turkey", "home_team": "Australia", "away_team": "Turkey",
         "home_perf": 50, "away_perf": 50,
         "home_conf_players": 26, "away_conf_players": 25,
         "home_player_events_min15": 213, "away_player_events_min15": 343,
         "status": "COMPLETE", "note": "26/26 Australia, 25/26 Turkey — global parser fix applied"},
    ]
    cov_df = pd.DataFrame(coverage_data)
    def _color_status(val):
        if val == "COMPLETE":
            return "background-color: #C6EFCE"
        elif val == "PARTIAL":
            return "background-color: #FFEB9C"
        return ""
    try:
        styled = cov_df.style.applymap(_color_status, subset=["status"])
        st.dataframe(styled, use_container_width=True)
    except Exception:
        st.dataframe(cov_df, use_container_width=True)
    st.caption(
        "Turkey name mismatch fixed: DB renamed Turkiye → Turkey in team_performance_events and team_players. "
        "Player performance downloaded for 60 confirmed players (2,885 per-event rows). "
        "Run scripts/fetch_today_4_matches_statshub_coverage.py --execute to refresh."
    )


# ---------------------------------------------------------------------------
# Tab: Raw API Odds
# ---------------------------------------------------------------------------

def page_raw_odds(run_filter: str | None, match_filter: str | None) -> None:
    st.header("Raw API Odds")
    if not table_exists("betting_odds_raw"):
        st.info("No raw odds ingested.")
        return
    wh, p = _run_where_clause(run_filter, match_filter)
    try:
        df = qdf(f"SELECT * FROM betting_odds_raw {wh} ORDER BY id DESC", tuple(p))
    except Exception as exc:
        st.error(f"Query failed: {exc}")
        return
    st.caption(f"{len(df)} rows")
    show_table_or_info(df, "Raw API Odds")


# ---------------------------------------------------------------------------
# Tab: Normalized Markets
# ---------------------------------------------------------------------------

def page_normalized_markets(run_filter: str | None, match_filter: str | None) -> None:
    st.header("Normalized Markets")
    if not table_exists("betting_odds_normalized"):
        st.info("No normalized odds yet.")
        return
    wh, p = _run_where_clause(run_filter, match_filter)
    try:
        df = qdf(f"SELECT * FROM betting_odds_normalized {wh} ORDER BY id", tuple(p))
    except Exception as exc:
        st.error(f"Query failed: {exc}")
        return
    st.caption(f"{len(df)} rows")
    show_table_or_info(df, "Normalized Markets")


# ---------------------------------------------------------------------------
# Tab: Player Props Found
# ---------------------------------------------------------------------------

def page_player_props_found(run_filter: str | None, match_filter: str | None) -> None:
    st.header("Player Props Found")
    st.caption("All player prop rows returned by API (matched or not). minutesPlayed >= 15 filter applied to EV.")
    if not table_exists("betting_odds_normalized"):
        st.info("No player props loaded.")
        return
    where_parts = ["n.market_type LIKE 'player_%'"]
    params: list = []
    if match_filter and match_filter != "(all)":
        where_parts.append("n.match_name=?")
        params.append(match_filter)
    try:
        df = qdf(
            f"""
            SELECT n.match_name, n.bookmaker, n.market_type, n.raw_market_name,
                   n.raw_selection_name, n.player_name, n.player_id,
                   n.side, n.line, n.odds_decimal, n.normalized_status,
                   n.match_confidence, n.notes,
                   v.minutes_filter_status, v.valid_appearance_count,
                   v.excluded_low_minutes_count, v.verdict
            FROM betting_odds_normalized n
            LEFT JOIN betting_value_scores_new v
              ON v.raw_market_name=n.raw_market_name
             AND v.raw_selection_name=n.raw_selection_name
             AND v.match_name=n.match_name
            WHERE {' AND '.join(where_parts)}
            ORDER BY n.match_name, n.raw_market_name, n.player_name
            """,
            tuple(params),
        )
    except Exception as exc:
        st.error(f"Query failed: {exc}")
        return
    show_cols = safe_columns(df, [
        "match_name", "bookmaker", "market_type", "raw_market_name", "raw_selection_name",
        "player_name", "player_id", "side", "line", "odds_decimal",
        "normalized_status", "match_confidence", "minutes_filter_status",
        "valid_appearance_count", "excluded_low_minutes_count", "verdict", "notes",
    ])
    st.caption(f"{len(df)} player prop rows")
    show_table_or_info(df[show_cols] if show_cols else df, "Player Props")


# ---------------------------------------------------------------------------
# Tab: Unsupported / Unmatched
# ---------------------------------------------------------------------------

def page_unsupported_unmatched(run_filter: str | None, match_filter: str | None) -> None:
    st.header("Unsupported / Unmatched")
    if not table_exists("betting_value_scores_new"):
        st.info("No review rows yet.")
        return
    where_parts = [
        "(verdict IN ('UNSUPPORTED','UNMATCHED')"
        " OR normalized_status IN ('unsupported_market','unmatched_selection')"
        " OR probability_status IN ('unsupported_market','unmatched_selection'))"
    ]
    params: list = []
    if match_filter and match_filter != "(all)":
        where_parts.append("match_name=?")
        params.append(match_filter)
    try:
        df = qdf(
            f"""
            SELECT match_name, market_type, market_scope, raw_market_name,
                   raw_selection_name, team_name, player_name, side, line,
                   odds_decimal, probability_status, normalized_status, verdict, notes
            FROM betting_value_scores_new
            WHERE {' AND '.join(where_parts)}
            ORDER BY match_name, raw_market_name
            """,
            tuple(params),
        )
    except Exception as exc:
        st.error(f"Query failed: {exc}")
        return
    show_cols = safe_columns(df, [
        "match_name", "market_type", "market_scope", "raw_market_name", "raw_selection_name",
        "team_name", "player_name", "side", "line", "odds_decimal",
        "probability_status", "normalized_status", "verdict", "notes",
    ])
    st.caption(f"{len(df)} rows")
    show_table_or_info(df[show_cols] if show_cols else df, "Unsupported/Unmatched")


# ---------------------------------------------------------------------------
# Tab: Market Mapping Audit
# ---------------------------------------------------------------------------

def page_market_mapping_audit(run_filter: str | None, match_filter: str | None) -> None:
    st.header("Market Mapping Audit")
    if not table_exists("betting_value_scores_new"):
        st.info("No market mapping audit rows yet.")
        return

    cols = table_columns("betting_value_scores_new")
    required = {
        "match_name", "raw_market_name", "raw_selection_name", "market_type",
        "market_mapping_status", "market_mapping_reason",
    }
    missing = sorted(required - cols)
    if missing:
        st.warning("Market Mapping Audit unavailable. Missing columns: " + ", ".join(missing))
        show_table_or_info(pd.DataFrame(), "Market Mapping Audit")
        return
    optional = [
        "exact_market_match", "canonical_market_type", "statshub_field_used",
        "field_mapping_status", "side_line_status", "data_completeness_status",
    ]
    optional_missing = [col for col in optional if col not in cols]
    if optional_missing:
        st.warning("Market Mapping Audit missing optional columns: " + ", ".join(optional_missing))

    def col_expr(col: str) -> str:
        return col if col in cols else f"NULL AS {col}"

    wh, params = _table_where_clause("betting_value_scores_new", run_filter, match_filter)
    prefix = f"{wh} AND " if wh else "WHERE "
    try:
        df = qdf(
            f"""
            SELECT match_name, raw_market_name, raw_selection_name,
                   market_type AS proposed_market_type,
                   market_mapping_status, market_mapping_reason,
                   {col_expr('exact_market_match')}, {col_expr('canonical_market_type')},
                   {col_expr('statshub_field_used')}, {col_expr('field_mapping_status')},
                   {col_expr('side_line_status')}, {col_expr('data_completeness_status')},
                   CASE
                       WHEN market_mapping_status='OK' THEN 'allow'
                       WHEN market_mapping_status='REVIEW' THEN 'review_only'
                       ELSE 'block'
                   END AS action
            FROM betting_value_scores_new
            {prefix}COALESCE(market_mapping_status,'OK') != 'OK'
            ORDER BY market_mapping_status, match_name, raw_market_name, raw_selection_name
            """,
            tuple(params),
        )
    except Exception as exc:
        st.error(f"Market mapping audit query failed: {exc}")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Blocked variants", int((df["market_mapping_status"] == "BLOCKED_MARKET_VARIANT").sum()) if not df.empty else 0)
    c2.metric("Review markets", int((df["market_mapping_status"] == "REVIEW").sum()) if not df.empty else 0)
    c3.metric("Unsupported/blocked", int((df["action"] == "block").sum()) if not df.empty else 0)
    show_table_or_info(df, "Market Mapping Audit")


# ---------------------------------------------------------------------------
# Tab: Model/Data Readiness
# ---------------------------------------------------------------------------

def page_model_data_readiness(run_filter: str | None, match_filter: str | None) -> None:
    st.header("Model/Data Readiness")
    if not table_exists("betting_odds_normalized"):
        st.info("No normalized odds table available.")
        return

    try:
        match_df = qdf(
            """
            WITH matches AS (
                SELECT match_name,
                       COUNT(*) AS odds_normalized_count,
                       SUM(market_type LIKE 'player_%') AS player_props_count,
                       SUM(market_type LIKE 'player_%' AND player_id IS NOT NULL AND player_id != '') AS player_props_with_player_id,
                       SUM(market_mapping_status='OK') AS ok_market_count
                FROM betting_odds_normalized
                GROUP BY match_name
            ),
            scores AS (
                SELECT match_name,
                       SUM(model_probability IS NOT NULL) AS model_probability_rows,
                       SUM(expected_value IS NOT NULL) AS ev_rows,
                       SUM(probability_status='INCOMPLETE_PLAYER_DATA') AS incomplete_player_data_rows,
                       SUM(verdict='VALUE') AS value_rows
                FROM betting_value_scores_new
                GROUP BY match_name
            )
            SELECT m.match_name,
                   m.odds_normalized_count,
                   m.player_props_count,
                   m.player_props_with_player_id,
                   m.ok_market_count,
                   COALESCE(s.model_probability_rows,0) AS model_probability_rows,
                   COALESCE(s.model_probability_rows,0) AS calculable_rows,
                   COALESCE(s.ev_rows,0) AS EV_rows,
                   COALESCE(s.incomplete_player_data_rows,0) AS blocked_incomplete_player_data_rows,
                   COALESCE(s.value_rows,0) AS VALUE_rows,
                   CASE
                       WHEN m.odds_normalized_count > 0 AND COALESCE(s.model_probability_rows,0)=0 THEN 'NOT_READY'
                       WHEN COALESCE(s.model_probability_rows,0) > 0 THEN 'PARTIAL'
                       ELSE 'NOT_READY'
                   END AS status,
                   CASE
                       WHEN m.odds_normalized_count > 0 AND COALESCE(s.model_probability_rows,0)=0
                       THEN 'odds present but no model_probability'
                       WHEN COALESCE(s.incomplete_player_data_rows,0) > 0
                       THEN 'partial player coverage; some rows blocked as INCOMPLETE_PLAYER_DATA'
                       ELSE ''
                   END AS no_bets_reason
            FROM matches m
            LEFT JOIN scores s ON s.match_name=m.match_name
            ORDER BY m.match_name
            """
        )
        if match_filter and match_filter != "(all)" and not match_df.empty:
            match_df = match_df[match_df["match_name"] == match_filter]
        show_table_or_info(match_df, "Model readiness by match")
    except Exception as exc:
        st.warning(f"Model/Data Readiness match query failed: {exc}")

    try:
        team_df = qdf(
            """
            WITH roster AS (
                SELECT team_name,
                       COUNT(*) AS expected_roster_count,
                       SUM(player_id IS NOT NULL AND player_id != '') AS resolved_roster_players
                FROM statshub_team_players
                GROUP BY team_name
            ),
            perf AS (
                SELECT team_name,
                       COUNT(*) AS player_performance_rows,
                       COUNT(DISTINCT player_id) AS players_with_performance_rows,
                       COUNT(DISTINCT CASE WHEN COALESCE(minutes_played,0) >= 15 THEN player_id END) AS players_with_minutes,
                       COUNT(DISTINCT CASE WHEN COALESCE(minutes_played,0) >= 15
                         AND (shots IS NOT NULL OR shots_on_target IS NOT NULL OR was_fouled IS NOT NULL
                              OR tackles IS NOT NULL OR passes IS NOT NULL OR yellow_cards IS NOT NULL)
                         THEN player_id END) AS players_with_required_stats
                FROM statshub_player_performance_events
                GROUP BY team_name
            ),
            team_perf AS (
                SELECT team_name, COUNT(*) AS team_performance_rows
                FROM statshub_team_performance_events
                GROUP BY team_name
            ),
            odds_teams AS (
                SELECT substr(match_name, 1, instr(match_name, ' vs ')-1) AS team_name
                FROM betting_odds_normalized
                WHERE instr(match_name, ' vs ') > 0
                UNION
                SELECT substr(match_name, instr(match_name, ' vs ')+4) AS team_name
                FROM betting_odds_normalized
                WHERE instr(match_name, ' vs ') > 0
            )
            SELECT o.team_name,
                   COALESCE(r.expected_roster_count,0) AS expected_roster_count,
                   COALESCE(r.resolved_roster_players,0) AS resolved_roster_players,
                   ROUND(CASE WHEN COALESCE(r.expected_roster_count,0)>0
                        THEN 100.0 * COALESCE(r.resolved_roster_players,0) / r.expected_roster_count
                        ELSE 0 END, 2) AS roster_coverage_pct,
                   COALESCE(p.players_with_performance_rows,0) AS players_with_performance_rows,
                   COALESCE(p.players_with_minutes,0) AS players_with_minutes,
                   COALESCE(p.players_with_required_stats,0) AS players_with_required_stats,
                   COALESCE(p.player_performance_rows,0) AS player_performance_rows,
                   COALESCE(t.team_performance_rows,0) AS team_performance_rows,
                   CASE
                       WHEN COALESCE(r.expected_roster_count,0)>0
                        AND 100.0 * COALESCE(r.resolved_roster_players,0) / r.expected_roster_count >= 80
                        AND COALESCE(p.players_with_required_stats,0) >= 14
                        AND COALESCE(p.players_with_minutes,0) >= 8
                        AND COALESCE(p.player_performance_rows,0) >= 300
                        AND COALESCE(t.team_performance_rows,0) >= 30
                       THEN 'READY'
                       WHEN COALESCE(t.team_performance_rows,0) >= 30 OR COALESCE(p.player_performance_rows,0) > 0
                       THEN 'PARTIAL'
                       ELSE 'NOT_READY'
                   END AS status
            FROM odds_teams o
            LEFT JOIN roster r ON r.team_name=o.team_name
            LEFT JOIN perf p ON p.team_name=o.team_name
            LEFT JOIN team_perf t ON t.team_name=o.team_name
            ORDER BY o.team_name
            """
        )
        show_table_or_info(team_df, "Model readiness by team")
    except Exception as exc:
        st.warning(f"Model/Data Readiness team query failed: {exc}")


# ---------------------------------------------------------------------------
# Tab: Data Quality
# ---------------------------------------------------------------------------

def page_data_quality(run_filter: str | None, match_filter: str | None) -> None:
    st.header("Data Quality")
    if not table_exists("betting_value_scores_new"):
        st.info("No data quality rows yet.")
        return

    match_where = f"match_name=?" if match_filter and match_filter != "(all)" else "1=1"
    match_params = (match_filter,) if match_filter and match_filter != "(all)" else ()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Raw odds", safe_count("betting_odds_raw",
              match_where if match_filter and match_filter != "(all)" else "1=1", match_params))
    c2.metric("Normalized", safe_count("betting_odds_normalized",
              match_where if match_filter and match_filter != "(all)" else "1=1", match_params))
    c3.metric("EV rows", safe_count("betting_value_scores_new", "expected_value IS NOT NULL"))
    c4.metric("Unsupported", safe_count("betting_value_scores_new", "verdict='UNSUPPORTED'"))
    c5.metric("Unmatched", safe_count("betting_value_scores_new", "verdict='UNMATCHED'"))
    c6.metric("VALUE bets", safe_count("betting_value_scores_new", "verdict='VALUE'"))

    try:
        df = qdf(
            """
            SELECT match_name, priority_class, minutes_filter_status,
                   probability_status, normalized_status, data_quality_status,
                   verdict, COUNT(*) rows
            FROM betting_value_scores_new
            GROUP BY match_name, priority_class, minutes_filter_status,
                     probability_status, normalized_status, data_quality_status, verdict
            ORDER BY match_name, rows DESC
            """
        )
        show_table_or_info(df, "Data Quality breakdown")
    except Exception as exc:
        st.error(f"Data quality query failed: {exc}")


# ---------------------------------------------------------------------------
# Tab: Event / Match Resolution
# ---------------------------------------------------------------------------

def page_event_resolution() -> None:
    st.header("Event / Match Resolution")
    st.caption("Events found and evaluated during the API event search.")
    if not table_exists("betting_event_candidates"):
        st.info("No event candidate data yet — run the fetch script first.")
        return
    try:
        df = qdf(
            """
            SELECT run_name, api_event_id, event_name, home_team, away_team,
                   start_time, sport, league, confidence, selected, notes, captured_at
            FROM betting_event_candidates
            ORDER BY confidence DESC, selected DESC
            """
        )
    except Exception as exc:
        st.error(f"Event candidates query failed: {exc}")
        return
    if df.empty:
        st.info("No event candidates recorded.")
        return
    show_cols = safe_columns(df, [
        "run_name", "api_event_id", "event_name", "home_team", "away_team",
        "start_time", "confidence", "selected", "notes", "captured_at",
    ])
    selected_df = df[df["selected"] == 1] if "selected" in df.columns else pd.DataFrame()
    rejected_df = df[df["selected"] == 0] if "selected" in df.columns else df
    if not selected_df.empty:
        st.subheader("Selected events")
        st.dataframe(selected_df[show_cols] if show_cols else selected_df,
                     use_container_width=True, hide_index=True)
    if not rejected_df.empty:
        st.subheader("Rejected / other candidates")
        st.dataframe(rejected_df[show_cols] if show_cols else rejected_df,
                     use_container_width=True, hide_index=True)

    # Also show raw odds source runs
    if table_exists("betting_odds_raw"):
        st.subheader("Runs in DB")
        runs_df = qdf(
            """SELECT run_name, match_name, bookmaker, COUNT(*) as raw_rows
               FROM betting_odds_raw GROUP BY run_name, match_name, bookmaker
               ORDER BY run_name, match_name"""
        )
        show_table_or_info(runs_df, "runs in DB")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Betting Value Dashboard",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    require_optional_password()
    st.title("Odds-driven Betting Value Dashboard")
    st.caption("Live/API bookmaker markets → EV calculation. Multi-match edition.")

    with st.sidebar:
        st.header("Filters")

        # Run filter
        run_options = ["(all)"] + available_runs()
        run_filter = st.selectbox("Run", run_options, index=0)
        # Default to 4-match run if present
        if "today_4_matches_live_api_odds_probe" in available_runs():
            idx = run_options.index("today_4_matches_live_api_odds_probe")
            run_filter = st.selectbox("Run", run_options, index=idx, key="run_select_default")

        # Match filter
        match_options = ["(all)"] + available_matches(run_filter)
        match_filter = st.selectbox("Match", match_options, index=0)

        st.divider()
        st.header("EV Filters")

        market_scope_filter = st.selectbox(
            "Market scope", ["all", "player", "team", "match"], index=0,
            help="Filter by whether the bet is on a player, team, or match outcome."
        )

        all_market_types = ["(all)"] + sorted(set(list(PRIORITY_CLASS_MAP.keys())))
        market_type_filter = st.selectbox("Market type", all_market_types, index=0)

        min_model_prob = st.slider(
            "Min model probability", 0.0, 1.0, 0.25, 0.01, format="%.2f",
            help="Only show bets where our empirical hit rate is at least this value."
        )

        min_ss = st.number_input(
            "Min sample size", min_value=1, max_value=100, value=10,
            help="Minimum number of valid appearances (minutes >= 15) in historical sample."
        )

        min_ev = st.number_input(
            "Min EV", min_value=-1.0, max_value=20.0, value=0.0, step=0.01, format="%.2f",
            help="Expected value threshold. 0 = all positive-EV bets."
        )

        limit_odds = st.checkbox("Limit max odds", value=False)
        max_odds = None
        if limit_odds:
            max_odds = st.number_input("Max odds", 1.0, 200.0, 10.0, 0.5, format="%.1f")

        incl_review_mp = st.checkbox(
            "Include REVIEW minutes-filter rows", value=False,
            help="If unchecked, only shows rows where the minutes filter passed (ok/not_applicable)."
        )

        st.divider()
        st.header("Data Completeness")
        completeness_filter = st.selectbox(
            "StatsHub coverage", ["all", "COMPLETE only", "PARTIAL only"], index=0,
            help=(
                "COMPLETE = both teams have confirmed StatsHub players with min-15 events. "
                "COMPLETE matches: Haiti vs Scotland, Australia vs Turkey, Brazil vs Morocco. "
                "PARTIAL: Qatar vs Switzerland — Qatar has 17/26 confirmed players (9 Arabic names unresolved); "
                "Swiss 26/26."
            ),
        )
        _COMPLETE_MATCHES = {"Haiti vs Scotland", "Australia vs Turkey", "Brazil vs Morocco"}
        _PARTIAL_MATCHES  = {"Qatar vs Switzerland"}

        st.divider()
        st.header("Actions")

        template_path = write_actual_odds_template()
        with open(template_path, "rb") as handle:
            st.download_button(
                "Download odds input template",
                handle,
                file_name="today_actual_odds_input_template.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        uploaded = st.file_uploader("Upload actual bookmaker odds", type=["xlsx", "csv"])
        if uploaded:
            count = _ingest_upload(uploaded)
            st.success(f"Imported {count} actual odds rows.")

        st.divider()
        # Download available Excel outputs
        for xlsx_name, label in [
            ("today_4_matches_live_api_odds_value_scores.xlsx", "Download 4-match odds Excel"),
            ("usa_paraguay_live_api_odds_value_scores_v3_minutes15.xlsx", "Download USA vs Paraguay v3"),
            ("today_odds_driven_value_scores.xlsx", "Download general value scores"),
        ]:
            p = OUT_DIR / xlsx_name
            if p.exists():
                with open(p, "rb") as handle:
                    st.download_button(
                        label, handle, file_name=xlsx_name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

        st.divider()
        # Current DB metrics
        st.subheader("DB snapshot")
        match_where = f"match_name='{match_filter}'" if match_filter and match_filter != "(all)" else "1=1"
        st.metric("Raw odds", safe_count("betting_odds_raw", match_where))
        st.metric("Normalized", safe_count("betting_odds_normalized", match_where))
        st.metric("EV rows", safe_count("betting_value_scores_new", "expected_value IS NOT NULL"))
        st.metric("VALUE bets", safe_count("betting_value_scores_new", "verdict='VALUE'"))
        st.metric("Unsupported", safe_count("betting_value_scores_new", "verdict='UNSUPPORTED'"))
        st.metric("Unmatched", safe_count("betting_value_scores_new", "verdict='UNMATCHED'"))
        if table_exists("betting_odds_raw"):
            run_df = qdf(f"SELECT DISTINCT run_name FROM betting_odds_raw WHERE {match_where} ORDER BY run_name")
            if not run_df.empty:
                st.caption("Run(s): " + ", ".join(run_df["run_name"].tolist()))
            bm_df = qdf(f"SELECT DISTINCT bookmaker FROM betting_odds_raw WHERE {match_where}")
            if not bm_df.empty:
                st.caption("Bookmaker(s): " + ", ".join(bm_df["bookmaker"].tolist()))

    blocked_count = blocked_odds_mismatch_count(run_filter, match_filter)
    if blocked_count:
        st.warning(
            f"{blocked_count} odds rows blocked by raw/manual reconciliation mismatch. "
            "Blocked rows are excluded from actionable EV."
        )
    if table_exists("betting_value_scores_new"):
        blocked_variants = safe_count("betting_value_scores_new", "market_mapping_status='BLOCKED_MARKET_VARIANT'")
        review_markets = safe_count("betting_value_scores_new", "market_mapping_status='REVIEW'")
        unsupported_markets = safe_count(
            "betting_value_scores_new",
            "market_mapping_status IN ('UNSUPPORTED','BLOCKED_UNVERIFIED_MARKET')",
        )
        if blocked_variants:
            st.warning(f"{blocked_variants} blocked market variant rows. They are never actionable.")
        if review_markets:
            st.info(f"{review_markets} REVIEW market rows. Enable review visibility to inspect only.")
        if unsupported_markets:
            st.info(f"{unsupported_markets} unsupported/unverified market rows.")

    # --- Tabs ---
    tab_names = [
        "EV Ranking",
        "Match Coverage",
        "Raw API Odds",
        "Normalized Markets",
        "Player Props Found",
        "Unsupported / Unmatched",
        "Market Mapping Audit",
        "Model/Data Readiness",
        "Data Quality",
        "Event / Match Resolution",
    ]
    tabs = st.tabs(tab_names)

    with tabs[0]:
        page_ev_ranking(
            run_filter, match_filter, market_scope_filter, market_type_filter,
            min_model_prob, min_ss, min_ev, max_odds, incl_review_mp,
            completeness_filter,
        )
    with tabs[1]:
        page_match_coverage(run_filter, match_filter)
    with tabs[2]:
        page_raw_odds(run_filter, match_filter)
    with tabs[3]:
        page_normalized_markets(run_filter, match_filter)
    with tabs[4]:
        page_player_props_found(run_filter, match_filter)
    with tabs[5]:
        page_unsupported_unmatched(run_filter, match_filter)
    with tabs[6]:
        page_market_mapping_audit(run_filter, match_filter)
    with tabs[7]:
        page_model_data_readiness(run_filter, match_filter)
    with tabs[8]:
        page_data_quality(run_filter, match_filter)
    with tabs[9]:
        page_event_resolution()


if __name__ == "__main__":
    main()
