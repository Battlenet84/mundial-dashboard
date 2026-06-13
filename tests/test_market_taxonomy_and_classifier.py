"""
Tests for market_taxonomy.py (evaluate_market_mapping) and the
_classify_market helper in odds_driven.py.

Coverage added with the market-unlock patch (2026-06):
  player_fouls_committed, player_fouled, player_passes, player_tackles,
  goalkeeper_saves (REVIEW), Alternative Corners → total_corners fix.
"""
from __future__ import annotations

import pytest

from app.betting.market_taxonomy import (
    STATUS_OK,
    STATUS_REVIEW,
    STATUS_UNSUPPORTED,
    STATUS_BLOCKED_UNVERIFIED,
    STATUS_BLOCKED_VARIANT,
    evaluate_market_mapping,
)
from app.betting.odds_driven import _classify_market


# ---------------------------------------------------------------------------
# Classifier: _classify_market
# ---------------------------------------------------------------------------

class TestClassifyMarket:
    """_classify_market(market_l, teams) → (market_type, is_team, is_player)"""

    _teams: tuple[str, ...] = ("Canada", "Bosnia and Herzegovina")

    def _c(self, name: str) -> tuple[str, bool, bool]:
        from app.betting.odds_driven import canonical
        return _classify_market(canonical(name), self._teams)

    # -- Markets unlocked by the patch --

    def test_player_fouls_committed(self):
        mt, is_team, is_player = self._c("Player Fouls Committed")
        assert mt == "player_fouls_committed"
        assert not is_team
        assert is_player

    def test_player_to_be_fouled(self):
        mt, is_team, is_player = self._c("Player To Be Fouled")
        assert mt == "player_fouled"
        assert not is_team
        assert is_player

    def test_player_passes(self):
        mt, is_team, is_player = self._c("Player Passes")
        assert mt == "player_passes"
        assert not is_team
        assert is_player

    def test_player_tackles(self):
        mt, is_team, is_player = self._c("Player Tackles")
        assert mt == "player_tackles"
        assert not is_team
        assert is_player

    def test_goalkeeper_saves(self):
        mt, is_team, is_player = self._c("Goalkeeper Saves")
        assert mt == "goalkeeper_saves"
        assert not is_team
        assert is_player

    # -- Classifier bug fix: Alternative Corners → total_corners --

    def test_alternative_corners_classifies_as_total_corners(self):
        mt, is_team, is_player = self._c("Alternative Corners")
        assert mt == "total_corners", (
            "Alternative Corners must route to total_corners, not team_corners"
        )
        assert not is_team
        assert not is_player

    def test_team_corners_still_routes_correctly(self):
        mt, is_team, _ = self._c("Team Corners")
        assert mt == "team_corners"
        assert is_team

    def test_total_corners_routes_correctly(self):
        mt, is_team, _ = self._c("Total Corners")
        assert mt == "total_corners"
        assert not is_team

    # -- No cross-contamination --

    def test_fouls_committed_not_player_fouled(self):
        mt_committed, _, _ = self._c("Player Fouls Committed")
        mt_fouled, _, _ = self._c("Player To Be Fouled")
        assert mt_committed != mt_fouled

    def test_player_tackles_not_team_tackles(self):
        mt_player, _, _ = self._c("Player Tackles")
        mt_team, _, _ = self._c("Team Tackles Home")
        assert mt_player != mt_team

    def test_player_passes_not_assists(self):
        mt_pass, _, _ = self._c("Player Passes")
        mt_assist, _, _ = self._c("Player Assists")
        assert mt_pass != mt_assist

    # -- Still-blocked markets (regression guard) --

    def test_match_offsides_not_supported(self):
        mt, _, _ = self._c("Match Offsides")
        assert mt == "offsides"

    def test_player_shots_on_target_outside_box(self):
        mt, _, _ = self._c("Player Shots on Target Outside Box")
        assert mt == "player_shots_on_target_outside_box"

    def test_headed_shots_on_target(self):
        mt, _, _ = self._c("Player Headed Shots on Target")
        assert mt == "unsupported_market"


# ---------------------------------------------------------------------------
# Taxonomy: evaluate_market_mapping
# ---------------------------------------------------------------------------

class TestEvaluateMarketMapping:
    """evaluate_market_mapping(market_type, raw_market_name)"""

    # -- New STATUS_OK markets --

    def test_player_fouls_committed_ok(self):
        result = evaluate_market_mapping("player_fouls_committed", "Player Fouls Committed")
        assert result["market_mapping_status"] == STATUS_OK
        assert result["exact_market_match"] is True
        assert result["statshub_field_used"] == "fouls"

    def test_player_fouled_ok(self):
        result = evaluate_market_mapping("player_fouled", "Player To Be Fouled")
        assert result["market_mapping_status"] == STATUS_OK
        assert result["exact_market_match"] is True
        assert result["statshub_field_used"] == "was_fouled"

    def test_player_passes_ok(self):
        result = evaluate_market_mapping("player_passes", "Player Passes")
        assert result["market_mapping_status"] == STATUS_OK
        assert result["exact_market_match"] is True
        assert result["statshub_field_used"] == "passes"

    def test_player_tackles_ok(self):
        result = evaluate_market_mapping("player_tackles", "Player Tackles")
        assert result["market_mapping_status"] == STATUS_OK
        assert result["exact_market_match"] is True
        assert result["statshub_field_used"] == "tackles"

    # -- goalkeeper_saves must be REVIEW, not OK --

    def test_goalkeeper_saves_is_review_not_ok(self):
        result = evaluate_market_mapping("goalkeeper_saves", "Goalkeeper Saves")
        assert result["market_mapping_status"] == STATUS_REVIEW, (
            "goalkeeper_saves must be STATUS_REVIEW (team-level proxy, not per-GK data)"
        )
        assert result["exact_market_match"] is True
        assert result["statshub_field_used"] == "goalkeeper_saves"

    # -- Alternative Corners → total_corners taxonomy pass (REVIEW) --

    def test_alternative_corners_passes_as_total_corners_review(self):
        result = evaluate_market_mapping("total_corners", "Alternative Corners")
        assert result["market_mapping_status"] == STATUS_REVIEW
        assert result["exact_market_match"] is True

    def test_alternative_corners_blocked_under_team_corners(self):
        """After the classifier fix, this path should never be hit in production,
        but the taxonomy itself must also reject the mismatch."""
        result = evaluate_market_mapping("team_corners", "Alternative Corners")
        assert result["exact_market_match"] is False
        assert result["market_mapping_status"] in (
            STATUS_BLOCKED_UNVERIFIED, STATUS_BLOCKED_VARIANT
        )

    # -- No conceptual cross-contamination --

    def test_fouls_committed_blocked_if_wrong_raw_name(self):
        result = evaluate_market_mapping("player_fouls_committed", "Player To Be Fouled")
        assert result["exact_market_match"] is False

    def test_player_fouled_blocked_if_wrong_raw_name(self):
        result = evaluate_market_mapping("player_fouled", "Player Fouls Committed")
        assert result["exact_market_match"] is False

    def test_player_tackles_blocked_if_team_tackles(self):
        result = evaluate_market_mapping("player_tackles", "Team Tackles Home")
        assert result["exact_market_match"] is False

    def test_player_passes_blocked_if_key_passes(self):
        result = evaluate_market_mapping("player_passes", "Key Passes")
        assert result["exact_market_match"] is False

    # -- Still-supported markets unchanged (regression) --

    def test_player_total_shots_still_ok(self):
        result = evaluate_market_mapping("player_total_shots", "Player Shots")
        assert result["market_mapping_status"] == STATUS_OK
        assert result["exact_market_match"] is True

    def test_player_shots_on_target_still_ok(self):
        result = evaluate_market_mapping("player_shots_on_target", "Player Shots on Target")
        assert result["market_mapping_status"] == STATUS_OK
        assert result["exact_market_match"] is True

    def test_over_under_goals_still_ok(self):
        result = evaluate_market_mapping("over_under_goals", "Goals Over/Under")
        assert result["market_mapping_status"] == STATUS_OK
        assert result["exact_market_match"] is True

    # -- Still-blocked markets (regression guard) --

    def test_player_shots_on_target_outside_box_unsupported(self):
        result = evaluate_market_mapping(
            "player_shots_on_target_outside_box", "Player Shots on Target Outside Box"
        )
        assert result["market_mapping_status"] == STATUS_UNSUPPORTED

    def test_unknown_market_type_blocked(self):
        result = evaluate_market_mapping("offsides", "Match Offsides")
        assert result["market_mapping_status"] == STATUS_BLOCKED_UNVERIFIED
        assert result["exact_market_match"] is False

    def test_player_fouls_committed_blocked_variant_first_half(self):
        """Variant containing a blocked pattern must not pass."""
        result = evaluate_market_mapping(
            "player_fouls_committed", "Player Fouls Committed First Half"
        )
        assert result["market_mapping_status"] == STATUS_BLOCKED_VARIANT
        assert result["exact_market_match"] is False
