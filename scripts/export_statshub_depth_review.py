from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.config.settings import ROOT_DIR
from app.db.connection import get_connection


SNAPSHOT_NAME = "mexico_alexis_season_depth_probe"
OUTPUT_FILE = Path("data/processed/statshub/mexico_alexis_depth_review.xlsx")
MEXICO_ENDPOINT = "team_4781_performance_limit100"
ALEXIS_ENDPOINT = "player_815637_performance_limit100"

TOURNAMENT_FILES = {
    "team": Path("data/raw/statshub/snapshots/mexico_alexis_season_probe/team_4781_tournaments_20260611T221522Z.json"),
    "player": Path("data/raw/statshub/snapshots/mexico_alexis_season_probe/player_815637_tournaments_20260611T221721Z.json"),
}

MEANINGS = {
    "entity_type": "entity type used by the review export",
    "entity_id": "StatsHub entity identifier",
    "entity_name": "entity display name",
    "best_status": "best validation status for this entity",
    "pass_type": "validation result: full_season, last_50, or failed",
    "source_rows": "rows exported from the selected raw source",
    "date_min": "oldest event date detected",
    "date_max": "newest event date detected",
    "competitions_detected": "competitions detected in selected rows",
    "best_raw_file": "selected raw JSON source file",
    "notes": "review notes",
    "statistics.expectedGoals": "expected goals",
    "statistics.totalShotsOnGoal": "total shots on goal",
    "statistics.shotsOnGoal": "shots on goal",
    "statistics.shotsOffGoal": "shots off goal",
    "statistics.fouls": "fouls committed",
    "statistics.yellowCards": "yellow cards",
    "statistics.redCards": "red cards",
    "statistics.totalTackle": "total tackles",
    "statistics.passes": "passes",
    "statistics.accuratePasses": "accurate passes",
    "statistics.ballPossession": "ball possession",
    "player_statistics_event.playerId": "StatsHub player id attached to player row",
    "player_statistics_event.goals": "goals",
    "player_statistics_event.goalAssist": "assists",
    "player_statistics_event.shots": "shots",
    "player_statistics_event.onTargetScoringAttempt": "shots on target",
    "player_statistics_event.expectedGoals": "expected goals",
    "player_statistics_event.expectedAssists": "expected assists",
    "player_statistics_event.xGxA": "expected goals plus expected assists",
    "player_statistics_event.keyPass": "key passes",
    "player_statistics_event.minutesPlayed": "minutes played",
    "player_statistics_event.totalPass": "passes",
    "player_statistics_event.accuratePass": "accurate passes",
    "player_statistics_event.totalTackle": "total tackles",
    "player_statistics_event.fouls": "fouls committed",
    "player_statistics_event.wasFouled": "was fouled",
    "player_statistics_event.yellowCard": "yellow cards",
    "player_statistics_event.redCard": "red cards",
}

KEY_HINTS = [
    "goal",
    "assist",
    "shot",
    "foul",
    "card",
    "tackle",
    "pass",
    "expected",
    "xg",
    "xa",
    "minute",
    "possession",
]


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def latest_snapshot(endpoint_name: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM statshub_snapshots
            WHERE snapshot_name = ? AND endpoint_name = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (SNAPSHOT_NAME, endpoint_name),
        ).fetchone()
    if row is None:
        raise SystemExit(f"Missing snapshot endpoint: {endpoint_name}")
    return dict(row)


def all_probe_sources() -> pd.DataFrame:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT endpoint_name, url, status_code, content_type, response_size, json_top_keys,
                   rows_detected, raw_file_path, status, created_at
            FROM statshub_snapshots
            WHERE snapshot_name = ?
            ORDER BY id
            """,
            (SNAPSHOT_NAME,),
        ).fetchall()
    out = []
    for row in rows:
        endpoint = row["endpoint_name"]
        entity_type = "player" if endpoint.startswith("player_") else "team"
        entity_id = "815637" if entity_type == "player" else "4781"
        entity_name = "Alexis Vega" if entity_type == "player" else "Mexico"
        contains_metrics = "performance" in endpoint and int(row["rows_detected"] or 0) > 0 and row["status"] in {"ok", "cache_hit"}
        rows_detected = int(row["rows_detected"] or 0)
        if rows_detected >= 100:
            row_depth = "100_or_more"
        elif rows_detected >= 50:
            row_depth = "50_or_more"
        elif rows_detected > 10:
            row_depth = "more_than_10"
        elif rows_detected == 10:
            row_depth = "10"
        else:
            row_depth = "less_than_10"
        out.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "endpoint_name": endpoint,
                "URL": row["url"],
                "raw_file": row["raw_file_path"],
                "status code": row["status_code"],
                "content type": row["content_type"],
                "response size": row["response_size"],
                "rows detected": rows_detected,
                "top keys": row["json_top_keys"],
                "classification/status": row["status"],
                "contains valid performance metrics": "yes" if contains_metrics else "no",
                "row depth": row_depth,
                "created_at": row["created_at"],
            }
        )
    return pd.DataFrame(out)


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, nested in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.update(flatten(nested, next_prefix))
    elif isinstance(value, list):
        out[prefix] = json.dumps(value, ensure_ascii=False, default=str)
    else:
        out[prefix] = value
    return out


def infer_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "text"


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def event_timestamp(row: dict[str, Any]) -> int | None:
    event = row.get("event") or row.get("events") or {}
    value = event.get("timeStartTimestamp") or event.get("startTimestamp")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def event_date(value: int | None) -> str:
    if value is None:
        return ""
    return datetime.fromtimestamp(value, timezone.utc).date().isoformat()


def tournament_names(entity_type: str) -> dict[str, str]:
    path = ROOT_DIR / TOURNAMENT_FILES[entity_type]
    if not path.exists():
        return {}
    payload = load_json(path)
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value.get("tournamentName", key)) for key, value in payload.items() if isinstance(value, dict)}


def competition_names(entity_type: str, rows: list[dict[str, Any]]) -> list[str]:
    mapping = tournament_names(entity_type)
    found: set[str] = set()
    for row in rows:
        league = row.get("league")
        if isinstance(league, dict) and league.get("name"):
            found.add(str(league["name"]))
            continue
        event = row.get("events") or row.get("event") or {}
        tournament_id = event.get("uniqueTournamentId")
        if tournament_id is not None:
            found.add(mapping.get(str(tournament_id), str(tournament_id)))
    return sorted(found)


def player_rows_match(rows: list[dict[str, Any]], player_id: str) -> bool:
    for row in rows:
        stats = row.get("player_statistics_event") or {}
        if str(stats.get("playerId")) != player_id:
            return False
    return bool(rows)


def summarize_entity(
    entity_type: str,
    entity_id: str,
    entity_name: str,
    endpoint_name: str,
) -> tuple[dict[str, Any], dict[str, str], list[str], dict[str, Any]]:
    source = latest_snapshot(endpoint_name)
    payload = load_json(source["raw_file_path"])
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    rows = [row for row in rows if isinstance(row, dict)]

    values_by_path: dict[str, list[Any]] = defaultdict(list)
    type_by_path: dict[str, str] = {}
    unclear: set[str] = set()
    for row in rows:
        for path, value in flatten(row).items():
            values_by_path[path].append(value)
            type_by_path[path] = infer_type(value)
            if "." in path:
                unclear.add(path.replace(".", "__"))

    timestamps = [ts for ts in (event_timestamp(row) for row in rows) if ts is not None]
    comps = competition_names(entity_type, rows)
    pass_type = "last_50" if len(rows) >= 50 else "failed"
    best_status = "ok" if source["status"] in {"ok", "cache_hit"} and pass_type != "failed" else "failed"
    notes = "Full season not proven. limit=100 confirms at least last-50 depth."
    if entity_type == "player":
        explicit = player_rows_match(rows, entity_id)
        if not explicit:
            best_status = "failed"
            pass_type = "failed"
        notes += f" All rows explicit player_id={entity_id}: {'yes' if explicit else 'no'}."

    result: dict[str, Any] = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_name": entity_name,
        "best_status": best_status,
        "pass_type": pass_type,
        "source_rows": len(rows),
        "date_min": event_date(min(timestamps) if timestamps else None),
        "date_max": event_date(max(timestamps) if timestamps else None),
        "competitions_detected": json.dumps(comps, ensure_ascii=False),
        "best_raw_file": source["raw_file_path"],
        "notes": notes,
        "source_endpoint": endpoint_name,
        "source_url": source["url"],
    }
    for path, values in sorted(values_by_path.items()):
        clean_values = [value for value in values if value is not None]
        column = path.replace(".", "__")
        if not clean_values:
            result[column] = None
            continue
        unique_values = []
        seen = set()
        for value in clean_values:
            marker = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            if marker not in seen:
                seen.add(marker)
                unique_values.append(value)
        result[column] = unique_values[0] if len(unique_values) == 1 else json.dumps(unique_values, ensure_ascii=False, default=str)
        numeric = [float(value) for value in clean_values if is_number(value)]
        if numeric and len(numeric) == len(clean_values):
            result[f"agg_sum__{column}"] = sum(numeric)
            result[f"agg_avg__{column}"] = sum(numeric) / len(numeric)
            result[f"agg_min__{column}"] = min(numeric)
            result[f"agg_max__{column}"] = max(numeric)
            result[f"agg_count__{column}"] = len(numeric)

    details = {
        "source": source,
        "rows": len(rows),
        "date_min": result["date_min"],
        "date_max": result["date_max"],
        "competitions": comps,
        "key_metrics": key_metrics(result),
        "unclear": sorted(unclear),
        "player_rows_explicit": player_rows_match(rows, entity_id) if entity_type == "player" else None,
    }
    return result, type_by_path, sorted(unclear), details


def exported_original_path(column: str) -> str:
    base = column
    for prefix in ["agg_sum__", "agg_avg__", "agg_min__", "agg_max__", "agg_count__"]:
        if base.startswith(prefix):
            base = base[len(prefix) :]
    return base.replace("__", ".")


def infer_exported_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "null"
    return infer_type(non_null.iloc[0])


def data_dictionary(sheets: dict[str, pd.DataFrame], type_maps: dict[str, dict[str, str]]) -> pd.DataFrame:
    rows = []
    metadata_columns = {
        "entity_type",
        "entity_id",
        "entity_name",
        "best_status",
        "pass_type",
        "source_rows",
        "date_min",
        "date_max",
        "competitions_detected",
        "best_raw_file",
        "notes",
        "source_endpoint",
        "source_url",
    }
    for sheet_name, df in sheets.items():
        if sheet_name == "data_dictionary":
            continue
        source_types = type_maps.get(sheet_name, {})
        for column in df.columns:
            original = "" if column in metadata_columns else exported_original_path(column)
            meaning = MEANINGS.get(original or column, "unknown")
            rows.append(
                {
                    "sheet_name": sheet_name,
                    "column_name": column,
                    "original_json_path": original,
                    "inferred_type": source_types.get(original, infer_exported_type(df[column])),
                    "meaning": meaning,
                    "notes": "" if meaning != "unknown" else "unknown; preserved for review",
                }
            )
    return pd.DataFrame(rows)


def key_metrics(row: dict[str, Any]) -> list[str]:
    found = []
    for key in row:
        lower = key.lower()
        if any(hint in lower for hint in KEY_HINTS) and not lower.startswith("agg_count"):
            found.append(key)
    return sorted(found)


def short_metrics(metrics: list[str]) -> list[str]:
    preferred = [
        metric
        for metric in metrics
        if metric.startswith("agg_sum__") or metric.startswith("agg_avg__") or "__expected" in metric.lower()
    ]
    return preferred[:40] if preferred else metrics[:40]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    args = parser.parse_args()

    mexico_row, mexico_types, mexico_unclear, mexico_details = summarize_entity("team", "4781", "Mexico", MEXICO_ENDPOINT)
    alexis_row, alexis_types, alexis_unclear, alexis_details = summarize_entity("player", "815637", "Alexis Vega", ALEXIS_ENDPOINT)

    summary_cols = [
        "entity_type",
        "entity_id",
        "entity_name",
        "best_status",
        "pass_type",
        "source_rows",
        "date_min",
        "date_max",
        "competitions_detected",
        "best_raw_file",
        "notes",
    ]
    sheets = {
        "depth_summary": pd.DataFrame([{col: mexico_row.get(col) for col in summary_cols}, {col: alexis_row.get(col) for col in summary_cols}]),
        "mexico_wide_review": pd.DataFrame([mexico_row]),
        "alexis_vega_wide_review": pd.DataFrame([alexis_row]),
        "raw_sources": all_probe_sources(),
    }
    type_maps = {
        "mexico_wide_review": mexico_types,
        "alexis_vega_wide_review": alexis_types,
    }
    sheets["data_dictionary"] = data_dictionary(sheets, type_maps)

    output = ROOT_DIR / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name in ["depth_summary", "mexico_wide_review", "alexis_vega_wide_review", "data_dictionary", "raw_sources"]:
            sheets[sheet_name].to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"Output file: {output}")
    print("Sheets:")
    for sheet_name in ["depth_summary", "mexico_wide_review", "alexis_vega_wide_review", "data_dictionary", "raw_sources"]:
        df = sheets[sheet_name]
        print(f"- {sheet_name}: rows={len(df)} columns={len(df.columns)}")

    for label, details in [("Mexico", mexico_details), ("Alexis Vega", alexis_details)]:
        print(label)
        print(f"- best_raw_file: {details['source']['raw_file_path']}")
        print(f"- rows: {details['rows']}")
        print(f"- date_range: {details['date_min']}..{details['date_max']}")
        print(f"- competitions: {details['competitions']}")
        if label == "Alexis Vega":
            print(f"- explicit_player_id_815637: {'yes' if details['player_rows_explicit'] else 'no'}")
        print(f"- pass: {'PASS B last_50' if details['rows'] >= 50 else 'FAIL'}")
        print(f"- key_metrics: {short_metrics(details['key_metrics'])}")

    decision_yes = mexico_details["rows"] >= 50 and alexis_details["rows"] >= 50 and alexis_details["player_rows_explicit"]
    print("Decision:")
    print(f"- move_forward: {'yes' if decision_yes else 'no'}")
    print("- scalable_pattern: last-50/last-N via direct performance limit parameter; full-season not proven")
    print("Fields duplicated/nested/unclear:")
    print(sorted(set(mexico_unclear + alexis_unclear))[:120])


if __name__ == "__main__":
    main()
