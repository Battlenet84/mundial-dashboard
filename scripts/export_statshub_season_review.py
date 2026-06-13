from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from app.db.connection import get_connection
from app.config.settings import ROOT_DIR


MEXICO_FILE = Path("data/raw/statshub/snapshots/mexico_alexis_season_probe/team_4781_performance_20260611T221648Z.json")
ALEXIS_FILE = Path("data/raw/statshub/snapshots/mexico_alexis_season_probe/player_815637_performance_20260611T221743Z.json")
OUTPUT_FILE = Path("data/processed/statshub/mexico_alexis_season_review.xlsx")


MEANINGS = {
    "entity_type": "entity type used by the review export",
    "entity_id": "StatsHub entity identifier",
    "entity_name": "entity display name",
    "source_file": "raw JSON source file",
    "source_endpoint": "StatsHub endpoint name used for this row",
    "snapshot_name": "StatsHub snapshot name",
    "status": "source status/classification",
    "statistics.goals": "goals",
    "statistics.expectedGoals": "expected goals",
    "statistics.totalShotsOnGoal": "total shots on goal",
    "statistics.shotsOnGoal": "shots on goal",
    "statistics.shotsOffGoal": "shots off goal",
    "statistics.fouls": "fouls committed",
    "statistics.yellowCards": "yellow cards",
    "statistics.redCards": "red cards",
    "statistics.totalTackle": "total tackles",
    "statistics.accuratePasses": "accurate passes",
    "statistics.passes": "passes",
    "statistics.ballPossession": "ball possession",
    "player_statistics_event.goals": "goals",
    "player_statistics_event.goalAssist": "assists",
    "player_statistics_event.shots": "shots",
    "player_statistics_event.onTargetScoringAttempt": "shots on target",
    "player_statistics_event.fouls": "fouls committed",
    "player_statistics_event.wasFouled": "was fouled",
    "player_statistics_event.yellowCard": "yellow cards",
    "player_statistics_event.redCard": "red cards",
    "player_statistics_event.expectedGoals": "expected goals",
    "player_statistics_event.expectedAssists": "expected assists",
    "player_statistics_event.keyPass": "key passes",
    "player_statistics_event.minutesPlayed": "minutes played",
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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def summarize_entity(
    entity_type: str,
    entity_id: str,
    entity_name: str,
    source_file: Path,
    source_endpoint: str,
    snapshot_name: str,
    status: str,
) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    payload = load_json(ROOT_DIR / source_file)
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []

    values_by_path: dict[str, list[Any]] = defaultdict(list)
    type_by_path: dict[str, str] = {}
    for row in rows:
        for path, value in flatten(row).items():
            values_by_path[path].append(value)
            type_by_path[path] = infer_type(value)

    result: dict[str, Any] = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_name": entity_name,
        "source_file": str(source_file),
        "source_endpoint": source_endpoint,
        "snapshot_name": snapshot_name,
        "status": status,
        "source_rows": len(rows),
    }
    unclear = []
    for path, values in sorted(values_by_path.items()):
        clean_values = [value for value in values if value is not None]
        column = path.replace(".", "__")
        if not clean_values:
            result[column] = None
            continue
        unique_values = []
        seen = set()
        for value in clean_values:
            key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                unique_values.append(value)
        result[column] = unique_values[0] if len(unique_values) == 1 else json.dumps(unique_values, ensure_ascii=False, default=str)

        numeric = [float(value) for value in clean_values if is_number(value)]
        if numeric and len(numeric) == len(clean_values):
            result[f"agg_sum__{column}"] = sum(numeric)
            result[f"agg_avg__{column}"] = sum(numeric) / len(numeric)
            result[f"agg_min__{column}"] = min(numeric)
            result[f"agg_max__{column}"] = max(numeric)
            result[f"agg_count__{column}"] = len(numeric)

        if "." in path or isinstance(clean_values[0], str) and clean_values[0].startswith("["):
            unclear.append(column)

    return result, type_by_path, sorted(set(unclear))


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


def raw_sources() -> pd.DataFrame:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                endpoint_name, url, status_code, rows_detected, json_top_keys,
                status, raw_file_path
            FROM statshub_snapshots
            WHERE snapshot_name = 'mexico_alexis_season_probe'
              AND endpoint_name IN ('team_4781_performance', 'player_815637_performance')
            ORDER BY endpoint_name
            """
        ).fetchall()
    metadata = {
        "team_4781_performance": ("team", "4781", "Mexico"),
        "player_815637_performance": ("player", "815637", "Alexis Vega"),
    }
    output = []
    for row in rows:
        entity_type, entity_id, entity_name = metadata[row["endpoint_name"]]
        output.append(
            {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "raw_file": row["raw_file_path"],
                "endpoint_name": row["endpoint_name"],
                "URL": row["url"],
                "status code": row["status_code"],
                "rows detected": row["rows_detected"],
                "top keys": row["json_top_keys"],
                "classification/status": row["status"],
            }
        )
    return pd.DataFrame(output)


def data_dictionary(sheets: dict[str, pd.DataFrame], type_maps: dict[str, dict[str, str]]) -> pd.DataFrame:
    rows = []
    for sheet_name, df in sheets.items():
        if sheet_name in {"data_dictionary"}:
            continue
        source_types = type_maps.get(sheet_name, {})
        for column in df.columns:
            original_no_agg_column = column
            for prefix in ["agg_sum__", "agg_avg__", "agg_min__", "agg_max__", "agg_count__"]:
                if original_no_agg_column.startswith(prefix):
                    original_no_agg_column = original_no_agg_column[len(prefix):]
            original_no_agg = original_no_agg_column.replace("__", ".")
            meaning = MEANINGS.get(original_no_agg, "unknown")
            rows.append(
                {
                    "sheet_name": sheet_name,
                    "column_name": column,
                    "original_json_path": original_no_agg if column not in {"entity_type", "entity_id", "entity_name", "source_file", "source_endpoint", "snapshot_name", "status"} else "",
                    "inferred_type": source_types.get(original_no_agg, infer_exported_type(df[column])),
                    "meaning": meaning,
                    "notes": "" if meaning != "unknown" else "unknown; preserved for review",
                }
            )
    return pd.DataFrame(rows)


def infer_exported_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "null"
    value = non_null.iloc[0]
    return infer_type(value)


def key_metrics(row: dict[str, Any]) -> list[str]:
    found = []
    for key in row:
        lower = key.lower()
        if any(hint in lower for hint in KEY_HINTS) and not lower.startswith("agg_count"):
            found.append(key)
    return sorted(found)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    args = parser.parse_args()

    mexico_row, mexico_types, mexico_unclear = summarize_entity(
        "team",
        "4781",
        "Mexico",
        MEXICO_FILE,
        "team_4781_performance",
        "mexico_alexis_season_probe",
        "ok",
    )
    alexis_row, alexis_types, alexis_unclear = summarize_entity(
        "player",
        "815637",
        "Alexis Vega",
        ALEXIS_FILE,
        "player_815637_performance",
        "mexico_alexis_season_probe",
        "ok",
    )

    common_cols = sorted(set(mexico_row) & set(alexis_row))
    fixed = ["entity_type", "entity_id", "entity_name", "source_file", "source_endpoint", "snapshot_name", "status", "source_rows"]
    common_cols = fixed + [column for column in common_cols if column not in fixed]

    sheets = {
        "summary_all_entities": pd.DataFrame([{column: mexico_row.get(column) for column in common_cols}, {column: alexis_row.get(column) for column in common_cols}]),
        "mexico_season_wide": pd.DataFrame([mexico_row]),
        "alexis_vega_season_wide": pd.DataFrame([alexis_row]),
        "raw_sources": raw_sources(),
    }
    type_maps = {
        "mexico_season_wide": mexico_types,
        "alexis_vega_season_wide": alexis_types,
    }
    sheets["data_dictionary"] = data_dictionary(sheets, type_maps)

    output = ROOT_DIR / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name in ["summary_all_entities", "mexico_season_wide", "alexis_vega_season_wide", "data_dictionary", "raw_sources"]:
            sheets[sheet_name].to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"Output file: {output}")
    print("Sheets:")
    for sheet_name in ["summary_all_entities", "mexico_season_wide", "alexis_vega_season_wide", "data_dictionary", "raw_sources"]:
        df = sheets[sheet_name]
        print(f"- {sheet_name}: rows={len(df)} columns={len(df.columns)}")
    print("Key metrics Mexico:")
    print(key_metrics(mexico_row))
    print("Key metrics Alexis Vega:")
    print(key_metrics(alexis_row))
    print("Fields duplicated/nested/unclear:")
    print(sorted(set(mexico_unclear + alexis_unclear))[:100])


if __name__ == "__main__":
    main()
