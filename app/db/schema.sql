CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_team_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    country TEXT,
    code TEXT,
    national INTEGER,
    founded INTEGER,
    logo TEXT,
    venue_id INTEGER,
    venue_name TEXT,
    venue_city TEXT,
    source_type TEXT DEFAULT 'api',
    raw_json TEXT,
    updated_at TEXT,
    UNIQUE(provider, provider_team_id)
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_player_id INTEGER NOT NULL,
    provider_team_id INTEGER,
    team_name TEXT,
    name TEXT NOT NULL,
    firstname TEXT,
    lastname TEXT,
    age INTEGER,
    birth_date TEXT,
    birth_place TEXT,
    birth_country TEXT,
    nationality TEXT,
    position TEXT,
    number INTEGER,
    height TEXT,
    weight TEXT,
    injured INTEGER,
    photo TEXT,
    source_type TEXT DEFAULT 'api',
    raw_json TEXT,
    updated_at TEXT,
    UNIQUE(provider, provider_player_id, provider_team_id)
);

CREATE TABLE IF NOT EXISTS fixtures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_fixture_id INTEGER NOT NULL,
    date_utc TEXT,
    round TEXT,
    group_name TEXT,
    timezone TEXT,
    venue_id INTEGER,
    status_short TEXT,
    status_long TEXT,
    elapsed INTEGER,
    venue_name TEXT,
    venue_city TEXT,
    referee_raw TEXT,
    home_team_provider_id INTEGER,
    away_team_provider_id INTEGER,
    home_team_name TEXT,
    away_team_name TEXT,
    home_goals INTEGER,
    away_goals INTEGER,
    score_halftime_home INTEGER,
    score_halftime_away INTEGER,
    score_fulltime_home INTEGER,
    score_fulltime_away INTEGER,
    score_extratime_home INTEGER,
    score_extratime_away INTEGER,
    score_penalty_home INTEGER,
    score_penalty_away INTEGER,
    source_type TEXT DEFAULT 'api',
    raw_json TEXT,
    updated_at TEXT,
    UNIQUE(provider, provider_fixture_id)
);

CREATE TABLE IF NOT EXISTS injuries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_player_id INTEGER,
    player_name TEXT,
    provider_team_id INTEGER,
    team_name TEXT,
    fixture_provider_id INTEGER,
    reason TEXT,
    type TEXT,
    raw_status TEXT,
    source_type TEXT DEFAULT 'api',
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_fixture_id INTEGER NOT NULL,
    bookmaker TEXT,
    market TEXT,
    selection TEXT,
    decimal_odds REAL,
    implied_probability REAL,
    snapshot_time TEXT NOT NULL,
    raw_payload_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_odds_snapshots_fixture
ON odds_snapshots(provider, provider_fixture_id, snapshot_time);

CREATE TABLE IF NOT EXISTS betting_odds_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_name TEXT,
    source_name TEXT,
    bookmaker TEXT,
    match_name TEXT,
    event_id TEXT,
    api_event_id TEXT,
    statshub_event_id TEXT,
    raw_market_group TEXT,
    raw_market_name TEXT,
    raw_selection_name TEXT,
    raw_line REAL,
    raw_odds REAL,
    odds_format TEXT,
    captured_at TEXT,
    raw_payload TEXT,
    source_url TEXT,
    request_id TEXT,
    raw_file TEXT,
    status TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS betting_odds_normalized (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_id INTEGER,
    run_name TEXT,
    source_name TEXT,
    bookmaker TEXT,
    match_name TEXT,
    event_id TEXT,
    api_event_id TEXT,
    statshub_event_id TEXT,
    market_type TEXT,
    market_name TEXT,
    selection_type TEXT,
    side TEXT,
    team_name TEXT,
    team_id TEXT,
    player_name TEXT,
    player_id TEXT,
    line REAL,
    odds_decimal REAL,
    raw_market_name TEXT,
    raw_selection_name TEXT,
    normalized_status TEXT,
    match_confidence REAL,
    captured_at TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS betting_value_scores_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rank INTEGER,
    source_name TEXT,
    bookmaker TEXT,
    match_name TEXT,
    market_type TEXT,
    raw_market_name TEXT,
    raw_selection_name TEXT,
    selection TEXT,
    team_name TEXT,
    player_name TEXT,
    player_id TEXT,
    side TEXT,
    line REAL,
    odds_decimal REAL,
    implied_probability REAL,
    model_probability REAL,
    edge REAL,
    expected_value REAL,
    probability_method TEXT,
    sample_size INTEGER,
    probability_status TEXT,
    normalized_status TEXT,
    data_quality_status TEXT,
    verdict TEXT,
    notes TEXT,
    computed_at TEXT
);

CREATE TABLE IF NOT EXISTS sync_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sync_name TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    records_count INTEGER,
    estimated_requests INTEGER DEFAULT 0,
    actual_requests INTEGER DEFAULT 0,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS fixture_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_fixture_id INTEGER NOT NULL,
    team_provider_id INTEGER,
    team_name TEXT,
    stat_type TEXT,
    stat_value TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS fixture_lineups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_fixture_id INTEGER NOT NULL,
    team_provider_id INTEGER,
    team_name TEXT,
    formation TEXT,
    coach_name TEXT,
    player_provider_id INTEGER,
    player_name TEXT,
    player_number INTEGER,
    player_position TEXT,
    is_starting INTEGER,
    grid TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS fixture_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_fixture_id INTEGER NOT NULL,
    elapsed INTEGER,
    extra_time INTEGER,
    team_provider_id INTEGER,
    team_name TEXT,
    player_provider_id INTEGER,
    player_name TEXT,
    assist_provider_id INTEGER,
    assist_name TEXT,
    event_type TEXT,
    detail TEXT,
    comments TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    team_provider_id INTEGER NOT NULL,
    team_name TEXT,
    ranking_type TEXT,
    rank_position INTEGER,
    points REAL,
    ranking_date TEXT,
    updated_at TEXT,
    UNIQUE(provider, team_provider_id, ranking_type, ranking_date)
);

CREATE TABLE IF NOT EXISTS manual_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_name TEXT,
    source_name TEXT,
    source_path TEXT,
    data_type TEXT,
    records_count INTEGER,
    imported_at TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    sync_name TEXT PRIMARY KEY,
    last_success_at TEXT,
    records_count INTEGER,
    freshness_hours INTEGER,
    next_recommended_sync TEXT,
    status TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS player_season_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_player_id INTEGER NOT NULL,
    player_name TEXT,
    season INTEGER,
    provider_team_id INTEGER,
    team_name TEXT,
    league_id INTEGER,
    league_name TEXT,
    league_country TEXT,
    league_season INTEGER,
    league_type TEXT,
    league_logo TEXT,
    appearances INTEGER,
    lineups INTEGER,
    minutes INTEGER,
    number INTEGER,
    position TEXT,
    rating REAL,
    captain INTEGER,
    substitutes_in INTEGER,
    substitutes_out INTEGER,
    substitutes_bench INTEGER,
    shots_total INTEGER,
    shots_on INTEGER,
    goals_total INTEGER,
    goals_conceded INTEGER,
    goals_assists INTEGER,
    goals_saves INTEGER,
    passes_total INTEGER,
    passes_key INTEGER,
    passes_accuracy TEXT,
    tackles_total INTEGER,
    tackles_blocks INTEGER,
    tackles_interceptions INTEGER,
    duels_total INTEGER,
    duels_won INTEGER,
    dribbles_attempts INTEGER,
    dribbles_success INTEGER,
    dribbles_past INTEGER,
    fouls_drawn INTEGER,
    fouls_committed INTEGER,
    cards_yellow INTEGER,
    cards_yellowred INTEGER,
    cards_red INTEGER,
    penalty_won INTEGER,
    penalty_committed INTEGER,
    penalty_scored INTEGER,
    penalty_missed INTEGER,
    penalty_saved INTEGER,
    raw_json TEXT,
    raw_payload_hash TEXT,
    fetched_at TEXT,
    updated_at TEXT,
    UNIQUE(provider, provider_player_id, season, provider_team_id, league_id)
);

CREATE TABLE IF NOT EXISTS player_stats_fetch_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_player_id INTEGER NOT NULL,
    player_name TEXT,
    provider_team_id INTEGER,
    team_name TEXT,
    fixture_provider_id INTEGER,
    match_date_utc TEXT,
    priority INTEGER,
    reason TEXT,
    status TEXT,
    requested_season INTEGER,
    last_fetched_at TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS matchday_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_date TEXT NOT NULL,
    status TEXT,
    fixtures_count INTEGER,
    teams_count INTEGER,
    teams_missing_squads_count INTEGER,
    players_candidates_count INTEGER,
    estimated_squad_requests INTEGER,
    estimated_player_stats_requests INTEGER,
    estimated_total_requests INTEGER,
    created_at TEXT,
    raw_plan_json TEXT
);

CREATE TABLE IF NOT EXISTS team_roster_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_team_id INTEGER NOT NULL,
    team_name TEXT,
    squad_size INTEGER,
    avg_age REAL,
    min_age INTEGER,
    max_age INTEGER,
    goalkeepers_count INTEGER,
    defenders_count INTEGER,
    midfielders_count INTEGER,
    attackers_count INTEGER,
    unknown_position_count INTEGER,
    avg_age_goalkeepers REAL,
    avg_age_defenders REAL,
    avg_age_midfielders REAL,
    avg_age_attackers REAL,
    updated_at TEXT,
    UNIQUE(provider, provider_team_id)
);

CREATE TABLE IF NOT EXISTS player_model_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    provider_player_id INTEGER NOT NULL,
    player_name TEXT,
    season INTEGER,
    total_minutes INTEGER,
    total_appearances INTEGER,
    total_goals INTEGER,
    total_assists INTEGER,
    total_shots INTEGER,
    total_shots_on INTEGER,
    total_key_passes INTEGER,
    total_fouls_committed INTEGER,
    total_fouls_drawn INTEGER,
    total_yellow_cards INTEGER,
    total_red_cards INTEGER,
    total_tackles INTEGER,
    total_interceptions INTEGER,
    total_dribble_attempts INTEGER,
    total_dribble_success INTEGER,
    shots_per_90 REAL,
    shots_on_per_90 REAL,
    goals_per_90 REAL,
    assists_per_90 REAL,
    key_passes_per_90 REAL,
    fouls_committed_per_90 REAL,
    fouls_drawn_per_90 REAL,
    cards_per_90 REAL,
    tackles_per_90 REAL,
    interceptions_per_90 REAL,
    updated_at TEXT,
    UNIQUE(provider, provider_player_id, season)
);

CREATE TABLE IF NOT EXISTS external_data_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_type TEXT,
    source_url TEXT,
    local_path TEXT,
    license_notes TEXT,
    season TEXT,
    competition TEXT,
    country TEXT,
    status TEXT,
    added_at TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS external_dataset_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT,
    detected_columns TEXT,
    mapped_columns TEXT,
    rows_read INTEGER,
    rows_imported INTEGER,
    rows_skipped INTEGER,
    status TEXT,
    message TEXT,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS source_player_stats_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    season TEXT,
    competition TEXT,
    team_name TEXT,
    player_name TEXT,
    raw_row_json TEXT NOT NULL,
    file_hash TEXT,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS player_identity_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_player_id TEXT,
    source_name TEXT NOT NULL,
    source_player_id TEXT,
    player_name TEXT NOT NULL,
    normalized_player_name TEXT,
    team_name TEXT,
    nationality TEXT,
    birth_date TEXT,
    confidence REAL,
    status TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS external_player_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    season TEXT,
    competition TEXT,
    player_name TEXT NOT NULL,
    normalized_player_name TEXT,
    team_name TEXT,
    position TEXT,
    nationality TEXT,
    age REAL,
    minutes REAL,
    appearances REAL,
    starts REAL,
    goals REAL,
    assists REAL,
    shots_total REAL,
    shots_on REAL,
    passes_total REAL,
    passes_key REAL,
    fouls_committed REAL,
    fouls_drawn REAL,
    yellow_cards REAL,
    red_cards REAL,
    tackles REAL,
    interceptions REAL,
    progressive_passes REAL,
    progressive_carries REAL,
    xg REAL,
    npxg REAL,
    xa REAL,
    sca REAL,
    gca REAL,
    raw_row_json TEXT,
    source_file_hash TEXT,
    imported_at TEXT,
    UNIQUE(source_name, season, competition, player_name, team_name)
);

CREATE TABLE IF NOT EXISTS external_player_model_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT,
    season TEXT,
    player_name TEXT,
    normalized_player_name TEXT,
    team_name TEXT,
    total_minutes REAL,
    total_appearances REAL,
    total_goals REAL,
    total_assists REAL,
    total_shots REAL,
    total_shots_on REAL,
    total_key_passes REAL,
    total_fouls_committed REAL,
    total_fouls_drawn REAL,
    total_yellow_cards REAL,
    total_red_cards REAL,
    total_tackles REAL,
    total_interceptions REAL,
    total_xg REAL,
    total_xa REAL,
    shots_per_90 REAL,
    shots_on_per_90 REAL,
    goals_per_90 REAL,
    assists_per_90 REAL,
    key_passes_per_90 REAL,
    fouls_committed_per_90 REAL,
    fouls_drawn_per_90 REAL,
    cards_per_90 REAL,
    tackles_per_90 REAL,
    interceptions_per_90 REAL,
    xg_per_90 REAL,
    xa_per_90 REAL,
    updated_at TEXT,
    UNIQUE(source_name, season, player_name, team_name)
);

CREATE TABLE IF NOT EXISTS statshub_prop_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT DEFAULT 'statshub',
    season TEXT,
    competition TEXT,
    market TEXT,
    player_name TEXT,
    team_name TEXT,
    opponent_name TEXT,
    line REAL,
    hit_rate REAL,
    average_value REAL,
    last_n_games INTEGER,
    odds TEXT,
    stat_value REAL,
    raw_row_json TEXT,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_name TEXT NOT NULL,
    endpoint_name TEXT NOT NULL,
    url TEXT NOT NULL,
    method TEXT DEFAULT 'GET',
    status_code INTEGER,
    content_type TEXT,
    response_size INTEGER,
    looks_json INTEGER,
    json_top_keys TEXT,
    rows_detected INTEGER,
    raw_file_path TEXT,
    status TEXT,
    message TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_snapshot_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER,
    endpoint_name TEXT,
    item_type TEXT,
    item_id TEXT,
    player_name TEXT,
    team_name TEXT,
    event_id TEXT,
    stat_type TEXT,
    raw_item_json TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT,
    team_name TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT,
    player_name TEXT,
    team_id TEXT,
    team_name TEXT,
    event_id TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_player_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT,
    player_name TEXT,
    team_id TEXT,
    team_name TEXT,
    tournament_id TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_referees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referee_id TEXT,
    referee_name TEXT,
    next_game_id TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_lineups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT,
    team_id TEXT,
    player_id TEXT,
    player_name TEXT,
    lineup_type TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_team_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT,
    event_id TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_event_extra_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_download_plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_name TEXT NOT NULL,
    snapshot_name TEXT NOT NULL,
    endpoint_name TEXT NOT NULL,
    url TEXT NOT NULL,
    method TEXT DEFAULT 'GET',
    priority INTEGER,
    source_reason TEXT,
    status TEXT,
    raw_file_path TEXT,
    created_at TEXT,
    executed_at TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS statshub_worldcup_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT,
    team_name TEXT,
    source_event_id TEXT,
    raw_json TEXT,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_worldcup_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT,
    player_name TEXT,
    team_id TEXT,
    team_name TEXT,
    source_event_id TEXT,
    raw_json TEXT,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_player_tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT,
    player_name TEXT,
    team_id TEXT,
    team_name TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_worldcup_player_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id TEXT,
    player_name TEXT,
    team_id TEXT,
    team_name TEXT,
    tournament_id TEXT,
    tournament_name TEXT,
    season_id TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_team_tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT,
    team_name TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_team_season_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id TEXT,
    team_name TEXT,
    event_id TEXT,
    endpoint_name TEXT,
    snapshot_name TEXT,
    raw_json TEXT NOT NULL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_world_cup_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_name TEXT,
    world_cup_year INTEGER,
    team_id TEXT,
    team_name TEXT,
    team_name_canonical TEXT,
    country TEXT,
    country_code TEXT,
    group_name TEXT,
    slug TEXT,
    source TEXT,
    source_confidence TEXT,
    confidence_status TEXT,
    statshub_team_id TEXT,
    statshub_team_slug TEXT,
    statshub_match_status TEXT,
    notes TEXT,
    raw_json TEXT,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_team_performance_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_name TEXT,
    endpoint_name TEXT,
    team_id TEXT,
    team_name TEXT,
    event_id TEXT,
    event_date TEXT,
    competition TEXT,
    opponent_team_id TEXT,
    opponent_team_name TEXT,
    home_away TEXT,
    raw_file TEXT,
    raw_row_json TEXT,
    goals_for REAL,
    goals_against REAL,
    expected_goals REAL,
    expected_goals_against REAL,
    shots REAL,
    shots_on_target REAL,
    shots_off_target REAL,
    big_chances REAL,
    fouls REAL,
    yellow_cards REAL,
    red_cards REAL,
    total_tackles REAL,
    accurate_passes REAL,
    total_passes REAL,
    pass_accuracy REAL,
    possession_average REAL,
    corners REAL,
    goalkeeper_saves REAL,
    final_third_entries REAL,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_team_performance_aggregates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_name TEXT,
    endpoint_name TEXT,
    team_id TEXT,
    team_name TEXT,
    source_rows INTEGER,
    date_min TEXT,
    date_max TEXT,
    competitions_detected TEXT,
    matches_in_window INTEGER,
    raw_file TEXT,
    goals_for REAL,
    goals_against REAL,
    expected_goals REAL,
    expected_goals_against REAL,
    shots REAL,
    shots_on_target REAL,
    shots_off_target REAL,
    big_chances REAL,
    fouls REAL,
    yellow_cards REAL,
    red_cards REAL,
    total_tackles REAL,
    accurate_passes REAL,
    total_passes REAL,
    pass_accuracy REAL,
    possession_average REAL,
    corners REAL,
    goalkeeper_saves REAL,
    final_third_entries REAL,
    opponent_expected_goals REAL,
    opponent_shots REAL,
    opponent_shots_on_target REAL,
    opponent_fouls REAL,
    opponent_yellow_cards REAL,
    opponent_red_cards REAL,
    raw_fields_json TEXT,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_team_players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_name TEXT,
    world_cup_year INTEGER,
    team_id TEXT,
    team_name TEXT,
    player_id TEXT,
    player_name TEXT,
    player_name_canonical TEXT,
    player_slug TEXT,
    position TEXT,
    jersey_number TEXT,
    nationality TEXT,
    source TEXT,
    source_confidence TEXT,
    statshub_player_id_status TEXT,
    squad_status TEXT,
    source_endpoint TEXT,
    raw_file TEXT,
    confidence_status TEXT,
    notes TEXT,
    raw_json TEXT,
    imported_at TEXT
);

CREATE TABLE IF NOT EXISTS statshub_raw_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_name TEXT,
    entity_type TEXT,
    team_id TEXT,
    team_name TEXT,
    endpoint_name TEXT,
    url TEXT,
    status_code INTEGER,
    content_type TEXT,
    response_size INTEGER,
    top_keys TEXT,
    rows_detected INTEGER,
    raw_file TEXT,
    classification_status TEXT,
    useful_performance_metrics_found TEXT,
    date_min TEXT,
    date_max TEXT,
    competitions_detected TEXT,
    notes TEXT,
    imported_at TEXT
);
