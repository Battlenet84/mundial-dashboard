from __future__ import annotations

from typing import Any, Iterable

from app.config.settings import get_settings
from app.providers.base import BaseProvider


class ApiFootballProvider(BaseProvider):
    name = "api_football"

    @classmethod
    def from_settings(
        cls,
        execute: bool = False,
        force: bool = False,
        use_cache: bool | None = None,
    ) -> "ApiFootballProvider":
        settings = get_settings()
        return cls(
            base_url=settings.api_football_base_url,
            api_key=settings.api_football_key,
            raw_data_dir=settings.raw_data_dir,
            execute=execute,
            force=force,
            use_cache=settings.use_api_cache if use_cache is None else use_cache,
        )

    def headers(self) -> dict[str, str]:
        return {"x-apisports-key": self.api_key}

    def get_worldcup_fixtures(self) -> dict[str, Any]:
        settings = get_settings()
        return self.get(
            "fixtures",
            {"league": settings.world_cup_league_id, "season": settings.world_cup_season},
            category="fixtures",
        )

    def get_fixtures(self) -> dict[str, Any]:
        return self.get_worldcup_fixtures()

    def get_worldcup_teams(self) -> dict[str, Any]:
        settings = get_settings()
        return self.get(
            "teams",
            {"league": settings.world_cup_league_id, "season": settings.world_cup_season},
            category="teams",
        )

    def get_teams(self) -> dict[str, Any]:
        return self.get_worldcup_teams()

    def get_worldcup_coverage(self) -> dict[str, Any]:
        settings = get_settings()
        return self.get(
            "leagues",
            {"id": settings.world_cup_league_id, "season": settings.world_cup_season},
            category="coverage",
        )

    def get_worldcup_players(self, page: int = 1) -> dict[str, Any]:
        settings = get_settings()
        return self.get(
            "players",
            {
                "league": settings.world_cup_league_id,
                "season": settings.world_cup_season,
                "page": page,
            },
            category="players",
        )

    def get_players_page(self, page: int) -> dict[str, Any]:
        return self.get_worldcup_players(page)

    def iter_players_pages(self, max_pages: int = 100) -> Iterable[tuple[int, dict[str, Any]]]:
        for page in range(1, max_pages + 1):
            payload = self.get_players_page(page)
            yield page, payload
            if not payload.get("response"):
                break
            paging = payload.get("paging") or {}
            current = paging.get("current")
            total = paging.get("total")
            if current and total and current >= total:
                break

    def get_injuries(self) -> dict[str, Any]:
        settings = get_settings()
        return self.get(
            "injuries",
            {"league": settings.world_cup_league_id, "season": settings.world_cup_season},
            category="injuries",
        )

    def get_fixture_odds(self, fixture_id: int) -> dict[str, Any]:
        return self.get("odds", {"fixture": fixture_id}, category="odds")

    def get_fixture_lineups(self, fixture_id: int) -> dict[str, Any]:
        return self.get("fixtures/lineups", {"fixture": fixture_id}, category="lineups")

    def get_fixture_events(self, fixture_id: int) -> dict[str, Any]:
        return self.get("fixtures/events", {"fixture": fixture_id}, category="events")

    def get_fixture_statistics(self, fixture_id: int) -> dict[str, Any]:
        return self.get("fixtures/statistics", {"fixture": fixture_id}, category="statistics")

    def get_team_squad(self, team_id: int) -> dict[str, Any]:
        return self.get("players/squads", {"team": team_id}, category="squads")

    def get_player_season_stats(self, player_id: int, season: int) -> dict[str, Any]:
        return self.get("players", {"id": player_id, "season": season}, category="player_season_stats")
