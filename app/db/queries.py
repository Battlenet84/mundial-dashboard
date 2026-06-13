from __future__ import annotations

from datetime import datetime, timezone
from sqlite3 import Connection
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def upsert_team(conn: Connection, team: dict[str, Any]) -> None:
    data = {
        "national": None,
        "founded": None,
        "venue_id": None,
        "venue_name": None,
        "venue_city": None,
        "raw_json": None,
        **team,
        "source_type": team.get("source_type") or "api",
        "updated_at": team.get("updated_at") or utc_now(),
    }
    conn.execute(
        """
        INSERT INTO teams (
            provider, provider_team_id, name, country, code, national, founded, logo,
            venue_id, venue_name, venue_city, source_type, raw_json, updated_at
        )
        VALUES (
            :provider, :provider_team_id, :name, :country, :code, :national, :founded, :logo,
            :venue_id, :venue_name, :venue_city, :source_type, :raw_json, :updated_at
        )
        ON CONFLICT(provider, provider_team_id) DO UPDATE SET
            name=excluded.name,
            country=excluded.country,
            code=excluded.code,
            national=excluded.national,
            founded=excluded.founded,
            logo=excluded.logo,
            venue_id=excluded.venue_id,
            venue_name=excluded.venue_name,
            venue_city=excluded.venue_city,
            source_type=excluded.source_type,
            raw_json=excluded.raw_json,
            updated_at=excluded.updated_at
        """,
        data,
    )


def upsert_player(conn: Connection, player: dict[str, Any]) -> None:
    data = {
        "team_name": None,
        "firstname": None,
        "lastname": None,
        "age": None,
        "birth_date": None,
        "birth_place": None,
        "birth_country": None,
        "nationality": None,
        "position": None,
        "number": None,
        "height": None,
        "weight": None,
        "injured": None,
        "photo": None,
        "raw_json": None,
        **player,
        "source_type": player.get("source_type") or "api",
        "updated_at": player.get("updated_at") or utc_now(),
    }
    conn.execute(
        """
        INSERT INTO players (
            provider, provider_player_id, provider_team_id, team_name, name, firstname, lastname,
            age, birth_date, birth_place, birth_country, nationality, position, number,
            height, weight, injured, photo, source_type, raw_json, updated_at
        )
        VALUES (
            :provider, :provider_player_id, :provider_team_id, :team_name, :name, :firstname, :lastname,
            :age, :birth_date, :birth_place, :birth_country, :nationality, :position, :number,
            :height, :weight, :injured, :photo, :source_type, :raw_json, :updated_at
        )
        ON CONFLICT(provider, provider_player_id, provider_team_id) DO UPDATE SET
            team_name=excluded.team_name,
            name=excluded.name,
            firstname=excluded.firstname,
            lastname=excluded.lastname,
            age=excluded.age,
            birth_date=excluded.birth_date,
            birth_place=excluded.birth_place,
            birth_country=excluded.birth_country,
            nationality=excluded.nationality,
            position=excluded.position,
            number=excluded.number,
            height=excluded.height,
            weight=excluded.weight,
            injured=excluded.injured,
            photo=excluded.photo,
            source_type=excluded.source_type,
            raw_json=excluded.raw_json,
            updated_at=excluded.updated_at
        """,
        data,
    )


def upsert_fixture(conn: Connection, fixture: dict[str, Any]) -> None:
    data = {
        "timezone": None,
        "venue_id": None,
        "referee_raw": None,
        "score_halftime_home": None,
        "score_halftime_away": None,
        "score_fulltime_home": None,
        "score_fulltime_away": None,
        "score_extratime_home": None,
        "score_extratime_away": None,
        "score_penalty_home": None,
        "score_penalty_away": None,
        "raw_json": None,
        **fixture,
        "group_name": fixture.get("group_name"),
        "source_type": fixture.get("source_type") or "api",
        "updated_at": fixture.get("updated_at") or utc_now(),
    }
    conn.execute(
        """
        INSERT INTO fixtures (
            provider, provider_fixture_id, date_utc, round, group_name, timezone, venue_id,
            status_short, status_long, elapsed, venue_name, venue_city, referee_raw,
            home_team_provider_id, away_team_provider_id, home_team_name, away_team_name,
            home_goals, away_goals, score_halftime_home, score_halftime_away,
            score_fulltime_home, score_fulltime_away, score_extratime_home, score_extratime_away,
            score_penalty_home, score_penalty_away, source_type, raw_json, updated_at
        )
        VALUES (
            :provider, :provider_fixture_id, :date_utc, :round, :group_name, :timezone, :venue_id,
            :status_short, :status_long, :elapsed, :venue_name, :venue_city, :referee_raw,
            :home_team_provider_id, :away_team_provider_id, :home_team_name, :away_team_name,
            :home_goals, :away_goals, :score_halftime_home, :score_halftime_away,
            :score_fulltime_home, :score_fulltime_away, :score_extratime_home, :score_extratime_away,
            :score_penalty_home, :score_penalty_away, :source_type, :raw_json, :updated_at
        )
        ON CONFLICT(provider, provider_fixture_id) DO UPDATE SET
            date_utc=excluded.date_utc,
            round=excluded.round,
            group_name=excluded.group_name,
            timezone=excluded.timezone,
            venue_id=excluded.venue_id,
            status_short=excluded.status_short,
            status_long=excluded.status_long,
            elapsed=excluded.elapsed,
            venue_name=excluded.venue_name,
            venue_city=excluded.venue_city,
            referee_raw=excluded.referee_raw,
            home_team_provider_id=excluded.home_team_provider_id,
            away_team_provider_id=excluded.away_team_provider_id,
            home_team_name=excluded.home_team_name,
            away_team_name=excluded.away_team_name,
            home_goals=excluded.home_goals,
            away_goals=excluded.away_goals,
            score_halftime_home=excluded.score_halftime_home,
            score_halftime_away=excluded.score_halftime_away,
            score_fulltime_home=excluded.score_fulltime_home,
            score_fulltime_away=excluded.score_fulltime_away,
            score_extratime_home=excluded.score_extratime_home,
            score_extratime_away=excluded.score_extratime_away,
            score_penalty_home=excluded.score_penalty_home,
            score_penalty_away=excluded.score_penalty_away,
            source_type=excluded.source_type,
            raw_json=excluded.raw_json,
            updated_at=excluded.updated_at
        """,
        data,
    )


def insert_injury(conn: Connection, injury: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO injuries (
            provider, provider_player_id, player_name, provider_team_id, team_name,
            fixture_provider_id, reason, type, raw_status, source_type, updated_at
        )
        VALUES (
            :provider, :provider_player_id, :player_name, :provider_team_id, :team_name,
            :fixture_provider_id, :reason, :type, :raw_status, :source_type, :updated_at
        )
        """,
        {**injury, "source_type": injury.get("source_type") or "api", "updated_at": injury.get("updated_at") or utc_now()},
    )


def insert_odds_snapshot(conn: Connection, odds: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO odds_snapshots (
            provider, provider_fixture_id, bookmaker, market, selection,
            decimal_odds, implied_probability, snapshot_time, raw_payload_hash
        )
        VALUES (
            :provider, :provider_fixture_id, :bookmaker, :market, :selection,
            :decimal_odds, :implied_probability, :snapshot_time, :raw_payload_hash
        )
        """,
        {**odds, "raw_payload_hash": odds.get("raw_payload_hash"), "snapshot_time": odds.get("snapshot_time") or utc_now()},
    )


def insert_sync_log(
    conn: Connection,
    sync_name: str,
    status: str,
    message: str = "",
    records_count: int = 0,
    started_at: str | None = None,
    finished_at: str | None = None,
    estimated_requests: int = 0,
    actual_requests: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO sync_logs (
            sync_name, status, message, records_count, estimated_requests, actual_requests, started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sync_name,
            status,
            message,
            records_count,
            estimated_requests,
            actual_requests,
            started_at or utc_now(),
            finished_at or utc_now(),
        ),
    )


def insert_fixture_statistic(conn: Connection, item: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO fixture_statistics (
            provider, provider_fixture_id, team_provider_id, team_name, stat_type, stat_value, updated_at
        ) VALUES (
            :provider, :provider_fixture_id, :team_provider_id, :team_name, :stat_type, :stat_value, :updated_at
        )
        """,
        {**item, "updated_at": item.get("updated_at") or utc_now()},
    )


def insert_fixture_lineup(conn: Connection, item: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO fixture_lineups (
            provider, provider_fixture_id, team_provider_id, team_name, formation, coach_name,
            player_provider_id, player_name, player_number, player_position, is_starting, grid, updated_at
        ) VALUES (
            :provider, :provider_fixture_id, :team_provider_id, :team_name, :formation, :coach_name,
            :player_provider_id, :player_name, :player_number, :player_position, :is_starting, :grid, :updated_at
        )
        """,
        {**item, "updated_at": item.get("updated_at") or utc_now()},
    )


def insert_fixture_event(conn: Connection, item: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO fixture_events (
            provider, provider_fixture_id, elapsed, extra_time, team_provider_id, team_name,
            player_provider_id, player_name, assist_provider_id, assist_name, event_type, detail,
            comments, updated_at
        ) VALUES (
            :provider, :provider_fixture_id, :elapsed, :extra_time, :team_provider_id, :team_name,
            :player_provider_id, :player_name, :assist_provider_id, :assist_name, :event_type, :detail,
            :comments, :updated_at
        )
        """,
        {**item, "updated_at": item.get("updated_at") or utc_now()},
    )


def upsert_ranking(conn: Connection, item: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO rankings (
            provider, team_provider_id, team_name, ranking_type, rank_position, points, ranking_date, updated_at
        ) VALUES (
            :provider, :team_provider_id, :team_name, :ranking_type, :rank_position, :points, :ranking_date, :updated_at
        )
        ON CONFLICT(provider, team_provider_id, ranking_type, ranking_date) DO UPDATE SET
            team_name=excluded.team_name,
            rank_position=excluded.rank_position,
            points=excluded.points,
            updated_at=excluded.updated_at
        """,
        {**item, "updated_at": item.get("updated_at") or utc_now()},
    )


def insert_manual_import(conn: Connection, item: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO manual_imports (
            import_name, source_name, source_path, data_type, records_count, imported_at, notes
        ) VALUES (
            :import_name, :source_name, :source_path, :data_type, :records_count, :imported_at, :notes
        )
        """,
        {**item, "imported_at": item.get("imported_at") or utc_now()},
    )


def update_sync_state(conn: Connection, item: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO sync_state (
            sync_name, last_success_at, records_count, freshness_hours, next_recommended_sync, status, message
        ) VALUES (
            :sync_name, :last_success_at, :records_count, :freshness_hours, :next_recommended_sync, :status, :message
        )
        ON CONFLICT(sync_name) DO UPDATE SET
            last_success_at=excluded.last_success_at,
            records_count=excluded.records_count,
            freshness_hours=excluded.freshness_hours,
            next_recommended_sync=excluded.next_recommended_sync,
            status=excluded.status,
            message=excluded.message
        """,
        item,
    )


def get_sync_state(conn: Connection, sync_name: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM sync_state WHERE sync_name = ?", (sync_name,)).fetchone()
    return dict(row) if row else None


def get_counts(conn: Connection) -> dict[str, int]:
    tables = [
        "teams",
        "fixtures",
        "players",
        "injuries",
        "odds_snapshots",
        "fixture_statistics",
        "fixture_lineups",
        "fixture_events",
        "rankings",
        "manual_imports",
        "player_season_stats",
        "player_stats_fetch_queue",
        "matchday_plans",
        "team_roster_features",
        "player_model_features",
        "external_data_sources",
        "external_dataset_imports",
        "source_player_stats_raw",
        "player_identity_map",
        "external_player_stats",
        "external_player_model_features",
        "statshub_prop_stats",
        "statshub_snapshots",
        "statshub_snapshot_items",
        "statshub_raw_events",
        "statshub_raw_teams",
        "statshub_raw_players",
        "statshub_raw_player_performance",
        "statshub_raw_referees",
        "statshub_raw_lineups",
        "statshub_raw_team_events",
        "statshub_raw_event_extra_stats",
        "statshub_download_plan_items",
        "statshub_worldcup_teams",
        "statshub_worldcup_players",
        "statshub_raw_player_tournaments",
        "statshub_raw_worldcup_player_performance",
        "statshub_raw_team_tournaments",
        "statshub_raw_team_season_events",
    ]
    return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}


def get_upcoming_fixtures(conn: Connection, limit: int = 10):
    return conn.execute(
        """
        SELECT * FROM fixtures
        WHERE date_utc IS NULL OR status_short IS NULL OR status_short NOT IN ('FT', 'AET', 'PEN')
        ORDER BY date_utc
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def get_api_budget_summary() -> dict[str, Any]:
    from app.providers.rate_limiter import get_budget_summary

    return get_budget_summary()


def upsert_player_season_stat(conn: Connection, item: dict[str, Any]) -> None:
    data = {**item, "fetched_at": item.get("fetched_at") or utc_now(), "updated_at": item.get("updated_at") or utc_now()}
    columns = [
        "provider", "provider_player_id", "player_name", "season", "provider_team_id", "team_name",
        "league_id", "league_name", "league_country", "league_season", "league_type", "league_logo",
        "appearances", "lineups", "minutes", "number", "position", "rating", "captain",
        "substitutes_in", "substitutes_out", "substitutes_bench", "shots_total", "shots_on",
        "goals_total", "goals_conceded", "goals_assists", "goals_saves", "passes_total",
        "passes_key", "passes_accuracy", "tackles_total", "tackles_blocks", "tackles_interceptions",
        "duels_total", "duels_won", "dribbles_attempts", "dribbles_success", "dribbles_past",
        "fouls_drawn", "fouls_committed", "cards_yellow", "cards_yellowred", "cards_red",
        "penalty_won", "penalty_committed", "penalty_scored", "penalty_missed", "penalty_saved",
        "raw_json", "raw_payload_hash", "fetched_at", "updated_at",
    ]
    for column in columns:
        data.setdefault(column, None)
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns if column not in {"provider", "provider_player_id", "season", "provider_team_id", "league_id"})
    conn.execute(
        f"""
        INSERT INTO player_season_stats ({", ".join(columns)})
        VALUES ({", ".join(":" + column for column in columns)})
        ON CONFLICT(provider, provider_player_id, season, provider_team_id, league_id)
        DO UPDATE SET {assignments}
        """,
        data,
    )


def upsert_team_roster_features(conn: Connection, item: dict[str, Any]) -> None:
    columns = [
        "provider", "provider_team_id", "team_name", "squad_size", "avg_age", "min_age", "max_age",
        "goalkeepers_count", "defenders_count", "midfielders_count", "attackers_count",
        "unknown_position_count", "avg_age_goalkeepers", "avg_age_defenders",
        "avg_age_midfielders", "avg_age_attackers", "updated_at",
    ]
    data = {**item, "updated_at": item.get("updated_at") or utc_now()}
    for column in columns:
        data.setdefault(column, None)
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns if column not in {"provider", "provider_team_id"})
    conn.execute(
        f"""
        INSERT INTO team_roster_features ({", ".join(columns)})
        VALUES ({", ".join(":" + column for column in columns)})
        ON CONFLICT(provider, provider_team_id) DO UPDATE SET {assignments}
        """,
        data,
    )


def upsert_player_model_features(conn: Connection, item: dict[str, Any]) -> None:
    columns = [
        "provider", "provider_player_id", "player_name", "season", "total_minutes",
        "total_appearances", "total_goals", "total_assists", "total_shots", "total_shots_on",
        "total_key_passes", "total_fouls_committed", "total_fouls_drawn", "total_yellow_cards",
        "total_red_cards", "total_tackles", "total_interceptions", "total_dribble_attempts",
        "total_dribble_success", "shots_per_90", "shots_on_per_90", "goals_per_90",
        "assists_per_90", "key_passes_per_90", "fouls_committed_per_90", "fouls_drawn_per_90",
        "cards_per_90", "tackles_per_90", "interceptions_per_90", "updated_at",
    ]
    data = {**item, "updated_at": item.get("updated_at") or utc_now()}
    for column in columns:
        data.setdefault(column, None)
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns if column not in {"provider", "provider_player_id", "season"})
    conn.execute(
        f"""
        INSERT INTO player_model_features ({", ".join(columns)})
        VALUES ({", ".join(":" + column for column in columns)})
        ON CONFLICT(provider, provider_player_id, season) DO UPDATE SET {assignments}
        """,
        data,
    )


def add_player_to_fetch_queue(conn: Connection, item: dict[str, Any]) -> None:
    data = {**item, "status": item.get("status") or "pending", "created_at": item.get("created_at") or utc_now(), "updated_at": item.get("updated_at") or utc_now()}
    columns = [
        "provider", "provider_player_id", "player_name", "provider_team_id", "team_name",
        "fixture_provider_id", "match_date_utc", "priority", "reason", "status",
        "requested_season", "last_fetched_at", "notes", "created_at", "updated_at",
    ]
    for column in columns:
        data.setdefault(column, None)
    conn.execute(
        f"INSERT INTO player_stats_fetch_queue ({', '.join(columns)}) VALUES ({', '.join(':' + c for c in columns)})",
        data,
    )


def update_player_fetch_queue_status(
    conn: Connection,
    provider_player_id: int,
    requested_season: int,
    status: str,
    notes: str = "",
) -> None:
    conn.execute(
        """
        UPDATE player_stats_fetch_queue
        SET status = ?, notes = ?, last_fetched_at = ?, updated_at = ?
        WHERE provider_player_id = ? AND requested_season = ?
        """,
        (status, notes, utc_now(), utc_now(), provider_player_id, requested_season),
    )


def get_fixtures_by_date(conn: Connection, date: str):
    return conn.execute(
        "SELECT * FROM fixtures WHERE substr(date_utc, 1, 10) = ? ORDER BY date_utc",
        (date,),
    ).fetchall()


def get_teams_for_date(conn: Connection, date: str):
    return conn.execute(
        """
        SELECT DISTINCT provider, team_id AS provider_team_id, team_name
        FROM (
            SELECT provider, home_team_provider_id AS team_id, home_team_name AS team_name FROM fixtures WHERE substr(date_utc, 1, 10) = ?
            UNION
            SELECT provider, away_team_provider_id AS team_id, away_team_name AS team_name FROM fixtures WHERE substr(date_utc, 1, 10) = ?
        )
        WHERE team_id IS NOT NULL
        ORDER BY team_name
        """,
        (date, date),
    ).fetchall()


def get_teams_missing_squads_for_date(conn: Connection, date: str):
    teams = get_teams_for_date(conn, date)
    missing = []
    for team in teams:
        count = conn.execute(
            "SELECT COUNT(*) FROM players WHERE provider = ? AND provider_team_id = ?",
            (team["provider"], team["provider_team_id"]),
        ).fetchone()[0]
        if count == 0:
            missing.append(team)
    return missing


def get_players_for_teams(conn: Connection, team_ids: list[int], positions: list[str] | None = None):
    if not team_ids:
        return []
    placeholders = ",".join("?" for _ in team_ids)
    params: list[Any] = list(team_ids)
    where = f"provider_team_id IN ({placeholders})"
    if positions:
        where += " AND UPPER(COALESCE(position, '')) IN (" + ",".join("?" for _ in positions) + ")"
        params.extend([p.upper() for p in positions])
    return conn.execute(
        f"""
        SELECT * FROM players
        WHERE {where}
        ORDER BY CASE UPPER(COALESCE(position, ''))
            WHEN 'ATTACKER' THEN 1 WHEN 'FORWARD' THEN 1
            WHEN 'MIDFIELDER' THEN 2
            WHEN 'DEFENDER' THEN 3
            WHEN 'GOALKEEPER' THEN 4
            ELSE 5 END,
            age IS NULL, age DESC, name
        """,
        params,
    ).fetchall()


def get_players_missing_stats(conn: Connection, players, season: int):
    missing = []
    for player in players:
        count = conn.execute(
            """
            SELECT COUNT(*) FROM player_season_stats
            WHERE provider = ? AND provider_player_id = ? AND season = ?
            """,
            (player["provider"], player["provider_player_id"], season),
        ).fetchone()[0]
        if count == 0:
            missing.append(player)
    return missing


def get_matchday_plan_summary(conn: Connection, date: str, max_players: int | None = None, season: int | None = None) -> dict[str, Any]:
    fixtures = get_fixtures_by_date(conn, date)
    teams = get_teams_for_date(conn, date)
    missing = get_teams_missing_squads_for_date(conn, date)
    team_ids = [row["provider_team_id"] for row in teams]
    players = get_players_for_teams(conn, team_ids)
    selected_players = players[:max_players] if max_players else []
    return {
        "date": date,
        "season": season,
        "fixtures_count": len(fixtures),
        "teams_count": len(teams),
        "teams_missing_squads_count": len(missing),
        "players_candidates_count": len(players),
        "estimated_squad_requests": len(missing),
        "estimated_player_stats_requests": len(selected_players),
        "estimated_total_requests": len(missing) + len(selected_players),
    }


def insert_matchday_plan(conn: Connection, item: dict[str, Any]) -> None:
    data = {**item, "created_at": item.get("created_at") or utc_now()}
    columns = [
        "plan_date", "status", "fixtures_count", "teams_count", "teams_missing_squads_count",
        "players_candidates_count", "estimated_squad_requests", "estimated_player_stats_requests",
        "estimated_total_requests", "created_at", "raw_plan_json",
    ]
    for column in columns:
        data.setdefault(column, None)
    conn.execute(
        f"INSERT INTO matchday_plans ({', '.join(columns)}) VALUES ({', '.join(':' + c for c in columns)})",
        data,
    )
