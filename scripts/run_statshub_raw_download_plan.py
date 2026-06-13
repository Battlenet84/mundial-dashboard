from __future__ import annotations

import argparse
import subprocess
import sys

from app.config.settings import get_settings
from app.db.connection import get_connection, init_db
from app.db.queries import utc_now


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-name", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--import-after-download", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    init_db()
    settings = get_settings()
    limit = min(args.max_requests or settings.statshub_max_requests_per_run, settings.statshub_max_requests_per_run)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM statshub_download_plan_items
            WHERE plan_name = ? AND status = 'planned'
            ORDER BY priority, id
            LIMIT ?
            """,
            (args.plan_name, limit),
        ).fetchall()
    print("RUN PLAN STATSHUB RAW")
    print(f"Planned: {len(rows)}")
    if not args.execute:
        print("Dry-run. No se hicieron requests externos.")
        for row in rows:
            print(f"- {row['endpoint_name']}: {row['url']}")
        return
    if not settings.statshub_enabled:
        raise SystemExit("StatsHub deshabilitado. STATSHUB_ENABLED=true requerido.")

    executed = downloaded = imported = blocked = errors = cache_hits = 0
    for row in rows:
        cmd = [
            sys.executable,
            "-m",
            "scripts.download_statshub_snapshot",
            "--snapshot-name",
            row["snapshot_name"],
            "--endpoint-name",
            row["endpoint_name"],
            "--url",
            row["url"],
            "--execute",
        ]
        result = subprocess.run(cmd, cwd=None, capture_output=True, text=True, check=False)
        executed += 1
        output = result.stdout + result.stderr
        status = "downloaded" if result.returncode == 0 else "error"
        message = output[-1000:]
        raw_file = None
        for line in output.splitlines():
            if line.startswith("Raw file:"):
                raw_file = line.split(":", 1)[1].strip()
            if "cache hit" in line:
                status = "skipped_cache"
        if "Clasificacion: blocked" in output:
            status = "blocked"
            blocked += 1
        elif result.returncode != 0:
            errors += 1
        elif status == "skipped_cache":
            cache_hits += 1
        else:
            downloaded += 1
        if args.import_after_download and raw_file and status in {"downloaded", "skipped_cache"}:
            import_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.import_statshub_raw_snapshot",
                    "--file",
                    raw_file,
                    "--endpoint-name",
                    row["endpoint_name"],
                    "--snapshot-name",
                    row["snapshot_name"],
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if import_result.returncode == 0:
                imported += 1
                status = "imported"
                message += "\n" + import_result.stdout[-500:]
        with get_connection() as conn:
            conn.execute(
                "UPDATE statshub_download_plan_items SET status = ?, raw_file_path = ?, executed_at = ?, message = ? WHERE id = ?",
                (status, raw_file, utc_now(), message, row["id"]),
            )
    print(f"Executed: {executed}")
    print(f"Downloaded: {downloaded}")
    print(f"Cache hits: {cache_hits}")
    print(f"Imported: {imported}")
    print(f"Blocked/errors: {blocked + errors}")


if __name__ == "__main__":
    main()

