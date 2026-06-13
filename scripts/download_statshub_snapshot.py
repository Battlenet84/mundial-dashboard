from __future__ import annotations

import argparse
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from app.config.settings import ROOT_DIR, get_settings
from app.db.connection import get_connection, init_db
from app.db.queries import utc_now
from app.external.statshub_snapshot import (
    cache_path,
    classify_response,
    parse_json_if_possible,
    rows_detected,
    snapshot_path,
    top_keys,
    validate_statshub_url,
)


LAST_REQUEST_PATH = ROOT_DIR / "data" / "raw" / "statshub" / "last_request.txt"


def record_snapshot(args, status: str, message: str, status_code=None, content_type="", response_size=0, payload=None, raw_file_path="") -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO statshub_snapshots (
                snapshot_name, endpoint_name, url, method, status_code, content_type,
                response_size, looks_json, json_top_keys, rows_detected, raw_file_path,
                status, message, created_at
            ) VALUES (?, ?, ?, 'GET', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                args.snapshot_name,
                args.endpoint_name,
                args.url,
                status_code,
                content_type,
                response_size,
                1 if payload is not None else 0,
                ",".join(top_keys(payload)),
                rows_detected(payload) if payload is not None else 0,
                raw_file_path,
                status,
                message,
                utc_now(),
            ),
        )


def enforce_delay(seconds: int) -> None:
    if not LAST_REQUEST_PATH.exists():
        return
    try:
        last = float(LAST_REQUEST_PATH.read_text(encoding="utf-8"))
    except ValueError:
        return
    wait = seconds - (time.time() - last)
    if wait > 0:
        time.sleep(wait)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-name", required=True)
    parser.add_argument("--endpoint-name", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        validate_statshub_url(args.url)
    except ValueError as exc:
        record_snapshot(args, "error", str(exc))
        raise SystemExit(str(exc))

    settings = get_settings()
    if not args.execute:
        record_snapshot(args, "dry_run", "dry-run sin request externo")
        print("STATSHUB SNAPSHOT DRY-RUN")
        print("Este comando no hizo request externo.")
        print(f"Snapshot: {args.snapshot_name}")
        print(f"Endpoint: {args.endpoint_name}")
        print(f"URL: {args.url}")
        return
    if not settings.statshub_enabled:
        record_snapshot(args, "error", "STATSHUB_ENABLED=false")
        raise SystemExit("StatsHub deshabilitado. Defini STATSHUB_ENABLED=true para ejecutar una descarga puntual.")
    if settings.statshub_max_requests_per_run < 1:
        raise SystemExit("STATSHUB_MAX_REQUESTS_PER_RUN no permite requests.")

    cache = cache_path(args.url)
    if settings.statshub_cache_enabled and cache.exists() and not args.force:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = snapshot_path(args.snapshot_name, args.endpoint_name, timestamp, cache.suffix.lstrip(".") or "json")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache, target)
        text = target.read_text(encoding="utf-8", errors="ignore")
        payload = parse_json_if_possible(text)
        record_snapshot(args, "cache_hit", "cache hit, no external request", response_size=len(text.encode("utf-8")), payload=payload, raw_file_path=str(target))
        print("cache hit, no external request")
        print(f"Raw file: {target}")
        return

    enforce_delay(settings.statshub_min_seconds_between_requests)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.statshub.com/",
    }
    try:
        response = requests.get(args.url, headers=headers, timeout=20)
        LAST_REQUEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_REQUEST_PATH.write_text(str(time.time()), encoding="utf-8")
        text = response.text
        payload = parse_json_if_possible(text)
        content_type = response.headers.get("content-type", "")
        status = classify_response(response.status_code, content_type, text, payload)
        suffix = "json" if payload is not None else "txt"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = snapshot_path(args.snapshot_name, args.endpoint_name, timestamp, suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        if settings.statshub_cache_enabled:
            cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, cache)
        record_snapshot(args, status, status, response.status_code, content_type, len(response.content), payload, str(target))
        print("STATSHUB SNAPSHOT")
        print(f"Ejecutado: si")
        print(f"Snapshot: {args.snapshot_name}")
        print(f"Endpoint: {args.endpoint_name}")
        print(f"URL: {args.url}")
        print(f"Status code: {response.status_code}")
        print(f"Content type: {content_type}")
        print(f"Response size: {len(response.content)}")
        print(f"JSON: {'si' if payload is not None else 'no'}")
        print(f"Top keys: {top_keys(payload)}")
        print(f"Rows detected: {rows_detected(payload) if payload is not None else 0}")
        print(f"Raw file: {target}")
        print(f"Clasificacion: {status}")
    except Exception as exc:
        record_snapshot(args, "error", str(exc))
        raise


if __name__ == "__main__":
    main()

