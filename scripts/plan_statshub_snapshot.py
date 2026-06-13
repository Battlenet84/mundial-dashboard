from __future__ import annotations

import argparse
from datetime import datetime, timezone

from app.config.settings import get_settings


def event_by_date_url(date_text: str) -> str:
    day = datetime.fromisoformat(date_text).replace(tzinfo=timezone.utc)
    start = int(day.timestamp())
    end = start + 86399
    return f"https://www.statshub.com/api/event/by-date?startOfDay={start}&endOfDay={end}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    args = parser.parse_args()
    settings = get_settings()
    endpoints = [
        ("world_cup_kickoff", "https://www.statshub.com/api/world-cup/kickoff"),
        ("tournament_upcoming", "https://www.statshub.com/api/tournament?upcomingFixtures=true&days=4"),
        ("referees_list", "https://www.statshub.com/api/referees/list?page=1&limit=50&upcomingFixturesOnly=true&sortField=next_game_timestamp&sortDirection=asc"),
    ]
    if args.date:
        endpoints.append(("event_by_date", event_by_date_url(args.date)))

    print("PLAN STATSHUB SNAPSHOT")
    print("Este comando no consume API.")
    print(f"StatsHub habilitado: {'si' if settings.statshub_enabled else 'no'}")
    print("Descargas seguras iniciales:")
    for index, (name, url) in enumerate(endpoints, start=1):
        print(f"{index}. {name}: 1 request")
        print(f"   Dry-run: python -m scripts.download_statshub_snapshot --snapshot-name test_001 --endpoint-name {name} --url \"{url}\"")
        print(f"   Ejecutar: python -m scripts.download_statshub_snapshot --snapshot-name test_001 --endpoint-name {name} --url \"{url}\" --execute")
    print(f"Requests estimados: {len(endpoints)}")
    print("No se incluyen endpoints de props por defecto.")


if __name__ == "__main__":
    main()

