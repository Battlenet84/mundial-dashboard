from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin

import requests


DEFAULT_BASE_URL = "https://api.odds-api.io/v3"
BASE_URL = DEFAULT_BASE_URL
API_KEY_ENV = "ODDS_API_IO_KEY"
BASE_URL_ENV = "ODDS_API_IO_BASE_URL"
ENV_FILE = Path(".env")
RAW_DIR = Path("data/raw/odds_api_io/probes")
PROCESSED_CSV = Path("data/processed/odds_api_io/latest_bet365_odds.csv")
TARGET_SLUG = "canada_bosnia_world_cup"
TARGET_RAW_DIR = Path("data/raw/odds_api_io/target_matches") / TARGET_SLUG
TARGET_PROCESSED_DIR = Path("data/processed/odds_api_io/target_matches") / TARGET_SLUG
TIMEOUT_SECONDS = 20
PLACEHOLDER_VALUES = {
    "",
    "put_your_key_here",
    "PASTE_YOUR_ODDS_API_IO_KEY_HERE",
}


@dataclass
class ProbeResult:
    action: str
    url: str
    params: dict[str, Any]
    status_code: int | None
    response_json: Any | None
    response_text_preview: str | None
    error: str | None
    raw_file: Path

    @property
    def ok(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300 and self.error is None


@dataclass
class ProbeConfig:
    api_key: str
    base_url: str
    env_file_detected: bool


def parse_local_env() -> tuple[dict[str, str], bool]:
    if not ENV_FILE.exists():
        return {}, False

    values: dict[str, str] = {}
    allowed = {API_KEY_ENV, BASE_URL_ENV}
    for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key not in allowed:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values, True


def is_configured_api_key(value: str | None) -> bool:
    return bool(value and value.strip() not in PLACEHOLDER_VALUES)


def load_config() -> ProbeConfig:
    local_values, env_file_detected = parse_local_env()
    api_key = os.environ.get(API_KEY_ENV, "").strip() or local_values.get(API_KEY_ENV, "").strip()
    base_url = os.environ.get(BASE_URL_ENV, "").strip() or local_values.get(BASE_URL_ENV, "").strip() or DEFAULT_BASE_URL
    return ProbeConfig(api_key=api_key, base_url=base_url.rstrip("/"), env_file_detected=env_file_detected)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fetched_at_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def strip_api_key(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if key.lower() != "apikey"}


def build_url_without_api_key(endpoint: str, params: dict[str, Any]) -> str:
    public_params = strip_api_key(params)
    url = urljoin(f"{BASE_URL}/", endpoint.lstrip("/"))
    if public_params:
        return f"{url}?{urlencode(public_params)}"
    return url


def raw_filename(action: str, args: argparse.Namespace, suffix: str | None = None) -> Path:
    stamp = utc_stamp()
    parts: list[str] = [action]
    if action == "events":
        parts.append(args.sport)
        if args.bookmaker:
            parts.append(args.bookmaker.lower().replace(" ", "_"))
        if getattr(args, "status", None):
            parts.append(str(args.status).lower().replace(" ", "_"))
        if getattr(args, "league", None):
            parts.append(str(args.league).lower().replace(" ", "_"))
    if action == "leagues":
        parts.append(args.sport)
    if action == "odds":
        bookmakers = (args.bookmakers or "bookmakers").lower().replace(" ", "_").replace(",", "_")
        parts.extend([bookmakers, str(args.event_id)])
    if suffix:
        parts.append(suffix)
    return RAW_DIR / f"{'_'.join(parts)}_{stamp}.json"


def save_raw(
    *,
    action: str,
    endpoint: str,
    params: dict[str, Any],
    status_code: int | None,
    response_json: Any | None,
    response_text_preview: str | None,
    error: str | None,
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at_utc": fetched_at_utc(),
        "url_without_api_key": build_url_without_api_key(endpoint, params),
        "action": action,
        "params_without_api_key": strip_api_key(params),
        "status_code": status_code,
        "response_json": response_json,
        "response_text_preview": response_text_preview,
        "error": error,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def request_probe(
    *,
    action: str,
    endpoint: str,
    params: dict[str, Any],
    raw_path: Path,
) -> ProbeResult:
    url = urljoin(f"{BASE_URL}/", endpoint.lstrip("/"))
    status_code: int | None = None
    response_json: Any | None = None
    response_text_preview: str | None = None
    error: str | None = None

    try:
        response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
        status_code = response.status_code
        try:
            response_json = response.json()
        except ValueError:
            response_text_preview = response.text[:1000]
        error = friendly_status_error(status_code)
    except requests.Timeout:
        error = f"Timeout despues de {TIMEOUT_SECONDS} segundos"
    except requests.RequestException as exc:
        error = str(exc)

    raw_file = save_raw(
        action=action,
        endpoint=endpoint,
        params=params,
        status_code=status_code,
        response_json=response_json,
        response_text_preview=response_text_preview,
        error=error,
        path=raw_path,
    )
    return ProbeResult(
        action=action,
        url=url,
        params=params,
        status_code=status_code,
        response_json=response_json,
        response_text_preview=response_text_preview,
        error=error,
        raw_file=raw_file,
    )


def friendly_status_error(status_code: int | None) -> str | None:
    if status_code in {401, 403}:
        return "API key invalid, missing, or unauthorized"
    if status_code == 429:
        return "rate limit reached"
    if status_code == 404:
        return "endpoint not found or changed"
    if status_code is not None and status_code >= 400:
        return f"HTTP {status_code}"
    return None


def detected_count(payload: Any) -> int | None:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("data", "events", "bookmakers", "sports", "response", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return None


def top_level_keys(payload: Any) -> str:
    if isinstance(payload, dict):
        return ", ".join(str(key) for key in payload.keys()) or "-"
    if isinstance(payload, list):
        return "list"
    return "-"


def print_summary(result: ProbeResult, args: argparse.Namespace, note: str | None = None) -> None:
    json_received = result.response_json is not None
    count = detected_count(result.response_json)
    print("ODDS-API.IO PROBE")
    print(f"Accion: {result.action}")
    if getattr(args, "sport", None):
        print(f"Deporte: {args.sport}")
    if getattr(args, "bookmaker", None):
        print(f"Bookmaker: {args.bookmaker}")
    if getattr(args, "bookmakers", None):
        print(f"Bookmakers: {args.bookmakers}")
    if getattr(args, "event_id", None):
        print(f"Evento: {args.event_id}")
    print(f"Status code: {result.status_code if result.status_code is not None else '-'}")
    print(f"JSON: {'si' if json_received else 'no'}")
    if count is not None:
        print(f"Items detectados: {count}")
    print(f"Top-level keys: {top_level_keys(result.response_json)}")
    print(f"Raw file: {result.raw_file}")
    if note:
        print(f"Nota: {note}")
    if result.error:
        print(f"Error: {result.error}")


def require_api_key() -> str:
    api_key = load_config().api_key
    if not is_configured_api_key(api_key):
        raise SystemExit(
            "ODDS_API_IO_KEY no configurada. Pegá tu key en el archivo .env o definila como variable de entorno."
        )
    return api_key


def run_config_check() -> int:
    config = load_config()
    print("ODDS-API.IO CONFIG")
    print(f".env detectado: {'sí' if config.env_file_detected else 'no'}")
    print(f"ODDS_API_IO_KEY: {'configurada' if is_configured_api_key(config.api_key) else 'no configurada'}")
    print(f"ODDS_API_IO_BASE_URL: {config.base_url}")
    return 0


def run_sports(args: argparse.Namespace) -> ProbeResult:
    return request_probe(
        action="sports",
        endpoint="sports",
        params={},
        raw_path=raw_filename("sports", args),
    )


def run_bookmakers(args: argparse.Namespace) -> tuple[ProbeResult, str | None]:
    result = request_probe(
        action="bookmakers",
        endpoint="bookmakers",
        params={},
        raw_path=raw_filename("bookmakers", args),
    )
    if result.status_code in {401, 403}:
        api_key = require_api_key()
        time.sleep(1)
        retry = request_probe(
            action="bookmakers",
            endpoint="bookmakers",
            params={"apiKey": api_key},
            raw_path=raw_filename("bookmakers", args, "with_key"),
        )
        return retry, "Endpoint requirio apiKey; se reintento sin imprimir ni guardar la clave."
    return result, None


def run_events(args: argparse.Namespace) -> tuple[ProbeResult, str | None]:
    api_key = require_api_key()
    params: dict[str, Any] = {"apiKey": api_key, "sport": args.sport, "limit": args.limit}
    if args.bookmaker:
        params["bookmaker"] = args.bookmaker
    if args.status:
        params["status"] = args.status
    if args.league:
        params["league"] = args.league
    result = request_probe(
        action="events",
        endpoint="events",
        params=params,
        raw_path=raw_filename("events", args),
    )
    if args.status and result.status_code in {400, 404, 422}:
        time.sleep(1)
        fallback_params = dict(params)
        fallback_params.pop("status", None)
        fallback = request_probe(
            action="events",
            endpoint="events",
            params=fallback_params,
            raw_path=raw_filename("events", args, "without_status"),
        )
        return fallback, "Parametro status no soportado o rechazado en /events; se uso fallback sin status."
    if args.bookmaker and result.status_code in {400, 404, 422}:
        time.sleep(1)
        fallback_params = {"apiKey": api_key, "sport": args.sport, "limit": args.limit}
        if args.status:
            fallback_params["status"] = args.status
        if args.league:
            fallback_params["league"] = args.league
        fallback = request_probe(
            action="events",
            endpoint="events",
            params=fallback_params,
            raw_path=raw_filename("events", args, "without_bookmaker"),
        )
        return fallback, "Filtro bookmaker no soportado o rechazado en /events; se uso fallback sin bookmaker."
    return result, None


def run_leagues(args: argparse.Namespace) -> ProbeResult:
    api_key = require_api_key()
    return request_probe(
        action="leagues",
        endpoint="leagues",
        params={"apiKey": api_key, "sport": args.sport},
        raw_path=raw_filename("leagues", args),
    )


def run_odds(args: argparse.Namespace) -> tuple[ProbeResult, str | None]:
    api_key = require_api_key()
    params = {"apiKey": api_key, "eventId": args.event_id, "bookmakers": args.bookmakers}
    result = request_probe(
        action="odds",
        endpoint="odds",
        params=params,
        raw_path=raw_filename("odds", args),
    )
    note = normalize_odds_if_possible(result)
    return result, note


def raw_response_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "events", "response", "results", "leagues"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def event_summary(event: dict[str, Any], source_file: Path | str) -> dict[str, Any]:
    sport = first_value(event, "sport", "sport_key", "sportName")
    league = first_value(event, "league", "competition", "tournament", "leagueName")
    return {
        "event_id": first_value(event, "id", "eventId", "event_id"),
        "home": first_value(event, "home", "homeTeam", "home_team", "homeName"),
        "away": first_value(event, "away", "awayTeam", "away_team", "awayName"),
        "date_utc": first_value(event, "date", "eventDate", "commence_time", "startTime", "startsAt"),
        "status": first_value(event, "status"),
        "sport": sport.get("name") if isinstance(sport, dict) else sport,
        "sport_slug": sport.get("slug") if isinstance(sport, dict) else None,
        "league_name": league.get("name") if isinstance(league, dict) else league,
        "league_slug": league.get("slug") if isinstance(league, dict) else None,
        "source_file": str(source_file),
        "raw_event": event,
    }


def team_matches(value: Any, patterns: tuple[str, ...]) -> bool:
    text = str(value or "").lower()
    return any(pattern.lower() in text for pattern in patterns)


def is_target_event(event: dict[str, Any], home_terms: tuple[str, ...], away_terms: tuple[str, ...]) -> bool:
    home = first_value(event, "home", "homeTeam", "home_team", "homeName")
    away = first_value(event, "away", "awayTeam", "away_team", "awayName")
    normal = team_matches(home, home_terms) and team_matches(away, away_terms)
    reversed_match = team_matches(home, away_terms) and team_matches(away, home_terms)
    return normal or reversed_match


def score_target(summary: dict[str, Any], context: str) -> int:
    score = 0
    if summary.get("status") in {"pending", "live"}:
        score += 4
    league_text = f"{summary.get('league_name') or ''} {summary.get('league_slug') or ''}".lower()
    if context and context.lower() in league_text:
        score += 3
    if "fifa" in league_text or "international" in league_text:
        score += 1
    if "bet365" in str(summary.get("source_file", "")).lower():
        score += 1
    return score


def iter_json_files(*directories: Path) -> list[Path]:
    files: list[Path] = []
    for directory in directories:
        if directory.exists():
            files.extend(path for path in directory.rglob("*.json") if path.is_file())
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def find_local_target_events(home_terms: tuple[str, ...], away_terms: tuple[str, ...]) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for path in iter_json_files(RAW_DIR, TARGET_RAW_DIR):
        if "bet365_odds" in path.name:
            continue
        try:
            wrapper = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        payload = wrapper.get("response_json", wrapper) if isinstance(wrapper, dict) else wrapper
        for event in raw_response_items(payload):
            if is_target_event(event, home_terms, away_terms):
                matches.append(event_summary(event, path))
    return matches


def write_candidate_report(candidates: list[dict[str, Any]]) -> Path:
    TARGET_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = TARGET_PROCESSED_DIR / "candidate_events.md"
    lines = ["# Canada vs Bosnia candidate events", ""]
    if not candidates:
        lines.append("No local/API candidate events found.")
    for item in candidates:
        lines.extend(
            [
                f"## Event {item.get('event_id')}",
                "",
                f"- event_id: {item.get('event_id')}",
                f"- home: {item.get('home')}",
                f"- away: {item.get('away')}",
                f"- date UTC: {item.get('date_utc')}",
                f"- status: {item.get('status')}",
                f"- sport: {item.get('sport')}",
                f"- league name: {item.get('league_name')}",
                f"- league slug: {item.get('league_slug')}",
                f"- source raw file: {item.get('source_file')}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def existing_target_odds(event_id: Any) -> Path | None:
    if not TARGET_RAW_DIR.exists():
        return None
    matches = sorted(
        TARGET_RAW_DIR.glob(f"canada_bosnia_bet365_odds_{event_id}_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def copy_target_raw(source: Path, event_id: Any, kind: str) -> Path:
    TARGET_RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    target = TARGET_RAW_DIR / f"canada_bosnia_{kind}_{event_id}_{stamp}.json"
    shutil.copyfile(source, target)
    return target


def save_target_event(summary: dict[str, Any]) -> Path:
    TARGET_RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    event_id = summary.get("event_id")
    path = TARGET_RAW_DIR / f"canada_bosnia_event_{event_id}_{stamp}.json"
    metadata = {key: value for key, value in summary.items() if key != "raw_event"}
    payload = {
        "fetched_at_utc": fetched_at_utc(),
        "event": metadata,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def bet365_markets(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    bookmakers = payload.get("bookmakers")
    if isinstance(bookmakers, dict):
        value = bookmakers.get("Bet365") or bookmakers.get("bet365")
        return value if isinstance(value, list) else []
    if isinstance(bookmakers, list):
        for bookmaker in bookmakers:
            name = first_value(bookmaker, "name", "title", "key", "bookmaker") if isinstance(bookmaker, dict) else None
            if name and str(name).lower() == "bet365":
                return first_list(bookmaker, "markets", "odds", "prices")
    return []


def market_rows(payload: Any, source_file: Path) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if not isinstance(payload, dict):
        return [], ["Odds payload is not an object."]
    markets = bet365_markets(payload)
    if not markets:
        return [], ["Bet365 returned no markets."]

    sport = first_value(payload, "sport", "sport_key")
    league = first_value(payload, "league", "competition", "tournament")
    base = {
        "fetched_at_utc": fetched_at_utc(),
        "event_id": first_value(payload, "id", "eventId", "event_id"),
        "sport": sport.get("name") if isinstance(sport, dict) else sport,
        "league_name": league.get("name") if isinstance(league, dict) else league,
        "league_slug": league.get("slug") if isinstance(league, dict) else None,
        "home": first_value(payload, "home", "homeTeam", "home_team"),
        "away": first_value(payload, "away", "awayTeam", "away_team"),
        "event_date_utc": first_value(payload, "date", "eventDate", "commence_time", "startTime"),
        "event_status": first_value(payload, "status"),
        "bookmaker": "Bet365",
        "source_file": str(source_file),
    }
    rows: list[dict[str, Any]] = []
    for market_index, market in enumerate(markets):
        if not isinstance(market, dict):
            warnings.append(f"Market {market_index} is not an object.")
            continue
        market_name = first_value(market, "name", "key", "market") or f"market_{market_index}"
        market_updated_at = first_value(market, "updatedAt", "updated_at", "lastUpdate")
        outcomes = first_list(market, "outcomes", "selections", "runners")
        if not outcomes and isinstance(market.get("odds"), list):
            outcomes = market["odds"]
        if not outcomes and isinstance(market.get("odds"), dict):
            outcomes = [{"name": key, "odds": value} for key, value in market["odds"].items()]
        if not outcomes:
            warnings.append(f"Market {market_index} has unknown outcome structure.")
            rows.append(
                {
                    **base,
                    "market_name": market_name,
                    "market_updated_at": market_updated_at,
                    "selection_name": first_value(market, "selection", "label", "name"),
                    "line": first_value(market, "line", "point", "handicap"),
                    "odds_decimal": first_value(market, "price", "odds", "decimal"),
                    "raw_market_index": market_index,
                    "raw_odds_index": "",
                }
            )
            continue
        for odds_index, outcome in enumerate(outcomes):
            if not isinstance(outcome, dict):
                warnings.append(f"Outcome {market_index}.{odds_index} is not an object.")
                continue
            expanded = expand_market_outcome(base, market_name, market_updated_at, market_index, odds_index, outcome)
            if expanded:
                rows.extend(expanded)
            else:
                warnings.append(f"Outcome {market_index}.{odds_index} has unknown odds fields.")
    return rows, warnings


def expand_market_outcome(
    base: dict[str, Any],
    market_name: Any,
    market_updated_at: Any,
    market_index: int,
    odds_index: int,
    outcome: dict[str, Any],
) -> list[dict[str, Any]]:
    line = first_value(outcome, "line", "point", "handicap", "hdp")
    label = first_value(outcome, "name", "selection", "label", "team")
    rows: list[dict[str, Any]] = []
    standard_fields = [
        ("home", base.get("home") or "Home"),
        ("draw", "Draw"),
        ("away", base.get("away") or "Away"),
        ("over", f"Over {line}" if line not in (None, "") else "Over"),
        ("under", f"Under {line}" if line not in (None, "") else "Under"),
    ]
    for key, selection_name in standard_fields:
        value = outcome.get(key)
        if value in (None, ""):
            continue
        if label and key in {"over", "under"} and "chance" in str(market_name).lower():
            selection_name = label
        rows.append(
            {
                **base,
                "market_name": market_name,
                "market_updated_at": market_updated_at,
                "selection_name": selection_name,
                "line": line,
                "odds_decimal": value,
                "raw_market_index": market_index,
                "raw_odds_index": odds_index,
            }
        )
    if rows:
        return rows

    odds_decimal = first_value(outcome, "price", "odds", "decimal")
    if odds_decimal in (None, ""):
        return []
    return [
        {
            **base,
            "market_name": market_name,
            "market_updated_at": market_updated_at,
            "selection_name": label,
            "line": line,
            "odds_decimal": odds_decimal,
            "raw_market_index": market_index,
            "raw_odds_index": odds_index,
        }
    ]


def write_target_processed(event: dict[str, Any] | None, odds_file: Path | None, api_calls: list[str]) -> dict[str, Any]:
    TARGET_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = TARGET_PROCESSED_DIR / "canada_bosnia_bet365_odds_normalized.csv"
    summary_path = TARGET_PROCESSED_DIR / "canada_bosnia_bet365_snapshot_summary.json"
    report_path = TARGET_PROCESSED_DIR / "canada_bosnia_bet365_report.md"
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    payload: Any | None = None
    if odds_file and odds_file.exists():
        wrapper = json.loads(odds_file.read_text(encoding="utf-8"))
        payload = wrapper.get("response_json", wrapper) if isinstance(wrapper, dict) else wrapper
        rows, warnings = market_rows(payload, odds_file)

    columns = [
        "fetched_at_utc",
        "event_id",
        "sport",
        "league_name",
        "league_slug",
        "home",
        "away",
        "event_date_utc",
        "event_status",
        "bookmaker",
        "market_name",
        "market_updated_at",
        "selection_name",
        "line",
        "odds_decimal",
        "raw_market_index",
        "raw_odds_index",
        "source_file",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    markets = bet365_markets(payload)
    summary = {
        "generated_at_utc": fetched_at_utc(),
        "event": event,
        "raw_odds_file": str(odds_file) if odds_file else None,
        "normalized_csv": str(csv_path),
        "market_count": len(markets),
        "row_count": len(rows),
        "warnings": warnings,
        "api_call_count": len(api_calls),
        "api_calls": api_calls,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Canada vs Bosnia Bet365 odds",
        "",
        f"- event_id: {event.get('event_id') if event else '-'}",
        f"- home: {event.get('home') if event else '-'}",
        f"- away: {event.get('away') if event else '-'}",
        f"- date UTC: {event.get('date_utc') if event else '-'}",
        f"- status: {event.get('status') if event else '-'}",
        f"- league: {event.get('league_name') if event else '-'}",
        f"- raw odds file: {odds_file or '-'}",
        f"- normalized CSV: {csv_path}",
        f"- Bet365 markets: {len(markets)}",
        f"- normalized rows: {len(rows)}",
        "",
    ]
    if warnings:
        lines.append("## Parser warnings")
        lines.extend(f"- {warning}" for warning in warnings)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    summary["summary_path"] = str(summary_path)
    summary["report_path"] = str(report_path)
    return summary


def extract_likely_leagues(result: ProbeResult) -> list[str]:
    terms = ("world cup", "fifa world cup", "world cup 2026", "international", "friendlies", "national teams")
    slugs: list[str] = []
    for item in raw_response_items(result.response_json):
        text = json.dumps(item, ensure_ascii=False).lower()
        if any(term in text for term in terms):
            slug = first_value(item, "slug", "key", "id", "league")
            if slug and str(slug) not in slugs:
                slugs.append(str(slug))
    return slugs


def run_fetch_target_match(args: argparse.Namespace) -> int:
    home_terms = ("Canada", "CAN")
    away_terms = ("Bosnia", "Bosnia and Herzegovina", "Bosnia-Herzegovina", "Bosnia & Herzegovina", "BIH", args.away)
    candidates = find_local_target_events(home_terms, away_terms)
    api_calls: list[str] = []
    notes: list[str] = []

    def add_candidates(result: ProbeResult) -> None:
        for event in raw_response_items(result.response_json):
            if is_target_event(event, home_terms, away_terms):
                candidates.append(event_summary(event, result.raw_file))

    if not candidates:
        variants = [
            {"bookmaker": args.bookmakers, "status": "pending", "league": None, "label": "events bookmaker+pending"},
            {"bookmaker": None, "status": "pending", "league": None, "label": "events pending"},
            {"bookmaker": args.bookmakers, "status": None, "league": None, "label": "events bookmaker"},
            {"bookmaker": None, "status": None, "league": None, "label": "events"},
        ]
        for variant in variants:
            probe_args = argparse.Namespace(
                sport=args.sport,
                bookmaker=variant["bookmaker"],
                bookmakers=args.bookmakers,
                status=variant["status"],
                league=variant["league"],
                limit=args.limit,
                event_id=None,
            )
            result, note = run_events(probe_args)
            api_calls.append(f"/events {variant['label']} status={result.status_code}")
            if note:
                notes.append(note)
            add_candidates(result)
            if candidates:
                break
            time.sleep(1)

    if not candidates:
        leagues_args = argparse.Namespace(sport=args.sport, bookmaker=None, bookmakers=args.bookmakers, status=None, league=None, limit=args.limit, event_id=None)
        leagues_result = run_leagues(leagues_args)
        api_calls.append(f"/leagues sport={args.sport} status={leagues_result.status_code}")
        likely_slugs = extract_likely_leagues(leagues_result)
        for league_slug in likely_slugs[:5]:
            probe_args = argparse.Namespace(
                sport=args.sport,
                bookmaker=args.bookmakers,
                bookmakers=args.bookmakers,
                status=None,
                league=league_slug,
                limit=args.limit,
                event_id=None,
            )
            result, note = run_events(probe_args)
            api_calls.append(f"/events league={league_slug} bookmaker={args.bookmakers} status={result.status_code}")
            if note:
                notes.append(note)
            add_candidates(result)
            if candidates:
                break
            time.sleep(1)

    candidates.sort(key=lambda item: score_target(item, args.context), reverse=True)
    candidate_report = write_candidate_report(candidates)
    selected = candidates[0] if candidates else None
    event_file: Path | None = None
    odds_file: Path | None = None

    if selected:
        event_file = save_target_event(selected)
        event_id = selected["event_id"]
        existing = existing_target_odds(event_id)
        if existing and not args.force_refresh:
            odds_file = existing
            notes.append("Odds target cache reused; no /odds call made.")
        else:
            odds_args = argparse.Namespace(event_id=event_id, bookmakers=args.bookmakers, sport=args.sport, bookmaker=None, status=None, league=None, limit=args.limit)
            result, note = run_odds(odds_args)
            api_calls.append(f"/odds eventId={event_id} bookmakers={args.bookmakers} status={result.status_code}")
            if note:
                notes.append(note)
            odds_file = copy_target_raw(result.raw_file, event_id, "bet365_odds")

    processed = write_target_processed(selected, odds_file, api_calls)
    print("ODDS-API.IO TARGET MATCH")
    print(f"Evento encontrado: {'sí' if selected else 'no'}")
    if selected:
        print(f"event_id: {selected.get('event_id')}")
        print(f"Partido: {selected.get('home')} vs {selected.get('away')}")
        print(f"Fecha UTC: {selected.get('date_utc')}")
        print(f"Status: {selected.get('status')}")
        print(f"Liga: {selected.get('league_name')}")
    print(f"Candidate report: {candidate_report}")
    print(f"Event raw target: {event_file or '-'}")
    print(f"Odds raw target: {odds_file or '-'}")
    print(f"Normalized CSV: {processed['normalized_csv']}")
    print(f"Summary JSON: {processed['summary_path']}")
    print(f"Report MD: {processed['report_path']}")
    print(f"Bet365 markets: {processed['market_count']}")
    print(f"Normalized rows: {processed['row_count']}")
    print(f"API calls this run: {len(api_calls)}")
    for call in api_calls:
        print(f"- {call}")
    for note in notes:
        print(f"Nota: {note}")
    return 0 if selected else 1


def normalize_odds_if_possible(result: ProbeResult) -> str | None:
    payload = result.response_json
    if not result.ok or payload is None:
        return None

    rows = extract_odds_rows(payload, result.raw_file)
    if not rows:
        return "Raw odds saved, but normalization was skipped because the structure was not recognized."

    PROCESSED_CSV.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "fetched_at_utc",
        "event_id",
        "sport",
        "league",
        "home",
        "away",
        "event_date",
        "bookmaker",
        "market_name",
        "selection_name",
        "line",
        "odds_decimal",
        "source_file",
    ]
    with PROCESSED_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return f"CSV normalizado: {PROCESSED_CSV}"


def extract_odds_rows(payload: Any, source_file: Path) -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        for key in ("data", "events", "response", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                containers.extend(item for item in value if isinstance(item, dict))
        if not containers:
            containers = [payload]
    elif isinstance(payload, list):
        containers = [item for item in payload if isinstance(item, dict)]

    rows: list[dict[str, Any]] = []
    for event in containers:
        event_id = first_value(event, "id", "eventId", "event_id")
        sport = first_value(event, "sport", "sport_key")
        league = first_value(event, "league", "competition", "tournament")
        home = first_value(event, "home", "homeTeam", "home_team")
        away = first_value(event, "away", "awayTeam", "away_team")
        event_date = first_value(event, "date", "eventDate", "commence_time", "startTime")
        bookmaker_items = first_list(event, "bookmakers", "sites", "odds")
        for bookmaker in bookmaker_items:
            if not isinstance(bookmaker, dict):
                continue
            bookmaker_name = first_value(bookmaker, "name", "title", "key", "bookmaker") or "Bet365"
            markets = first_list(bookmaker, "markets", "odds", "prices")
            for market in markets:
                if not isinstance(market, dict):
                    continue
                market_name = first_value(market, "name", "key", "market")
                selections = first_list(market, "outcomes", "selections", "runners")
                for selection in selections:
                    if not isinstance(selection, dict):
                        continue
                    rows.append(
                        {
                            "fetched_at_utc": fetched_at_utc(),
                            "event_id": event_id,
                            "sport": sport,
                            "league": league,
                            "home": home,
                            "away": away,
                            "event_date": event_date,
                            "bookmaker": bookmaker_name,
                            "market_name": market_name,
                            "selection_name": first_value(selection, "name", "selection", "label"),
                            "line": first_value(selection, "line", "point", "handicap"),
                            "odds_decimal": first_value(selection, "price", "odds", "decimal"),
                            "source_file": str(source_file),
                        }
                    )
    return rows


def first_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def first_list(mapping: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, list):
            return value
    return []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe minimo para Odds-API.io.")
    parser.add_argument(
        "--action",
        required=True,
        choices=["sports", "bookmakers", "events", "odds", "leagues", "config-check", "fetch-target-match"],
    )
    parser.add_argument("--sport", default="football")
    parser.add_argument("--bookmaker")
    parser.add_argument("--bookmakers", default="Bet365")
    parser.add_argument("--event-id")
    parser.add_argument("--status")
    parser.add_argument("--league")
    parser.add_argument("--home", default="Canada")
    parser.add_argument("--away", default="Bosnia")
    parser.add_argument("--context", default="World Cup")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.action == "odds" and not args.event_id:
        parser.error("--event-id es requerido para --action odds")
    return args


def main() -> int:
    global BASE_URL
    args = parse_args()
    config = load_config()
    BASE_URL = config.base_url
    note: str | None = None

    if args.action == "config-check":
        return run_config_check()
    if args.action == "fetch-target-match":
        return run_fetch_target_match(args)
    if args.action == "sports":
        result = run_sports(args)
    elif args.action == "bookmakers":
        result, note = run_bookmakers(args)
    elif args.action == "events":
        result, note = run_events(args)
    elif args.action == "leagues":
        result = run_leagues(args)
    elif args.action == "odds":
        result, note = run_odds(args)
    else:
        raise AssertionError(args.action)

    print_summary(result, args, note)
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
