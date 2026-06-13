from app.normalizers.api_football import normalize_player_season_stats


def test_player_season_stats_preserves_multiple_statistics_rows():
    payload = {
        "player": {"id": 10, "name": "Test Player"},
        "statistics": [
            {"team": {"id": 1, "name": "Club"}, "league": {"id": 11, "name": "League"}, "games": {"minutes": 900}, "goals": {"total": 4}},
            {"team": {"id": 2, "name": "National"}, "league": {"id": 1, "name": "World Cup"}, "games": {"minutes": 100}, "goals": {"total": 1}},
        ],
    }
    rows = normalize_player_season_stats(payload, 2025)
    assert len(rows) == 2
    assert {row["provider_team_id"] for row in rows} == {1, 2}
    assert all(row["raw_json"] for row in rows)
    assert all(row["raw_payload_hash"] for row in rows)

