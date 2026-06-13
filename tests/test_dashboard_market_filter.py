"""
Regression test: dashboard SQL must not hardcode shots/goals market types.

Ensures that after the market-unlock patch the dashboard query is open to all
taxonomy-approved markets and not gated by any hidden market_type IN (...) list.
"""
from __future__ import annotations

import re
from pathlib import Path

DASHBOARD_PATH = Path("app/dashboard/betting_value_dashboard.py")


def _dashboard_source() -> str:
    return DASHBOARD_PATH.read_text(encoding="utf-8")


class TestDashboardMarketFilters:
    def test_no_hardcoded_market_type_in_filter(self):
        """Dashboard must not use market_type IN (...) to restrict visible markets."""
        src = _dashboard_source()
        assert "market_type IN" not in src, (
            "Dashboard contains a hardcoded market_type IN (...) filter — "
            "this would exclude newly unlocked markets."
        )

    def test_newly_unlocked_markets_not_excluded(self):
        """Newly unlocked markets must not appear in any exclusion list."""
        src = _dashboard_source()
        blocked_phrases = [
            "player_fouls_committed NOT",
            "player_fouled NOT",
            "player_passes NOT",
            "player_tackles NOT",
            "exclude.*player_fouls",
            "exclude.*player_fouled",
        ]
        for phrase in blocked_phrases:
            assert not re.search(phrase, src, re.I), (
                f"Dashboard appears to exclude a newly unlocked market: {phrase!r}"
            )

    def test_only_value_filter_uses_ok_status(self):
        """The VALUE-only filter must use market_mapping_status='OK', not a market list."""
        src = _dashboard_source()
        assert "market_mapping_status='OK'" in src or "market_mapping_status = 'OK'" in src, (
            "Dashboard VALUE-only filter should gate on market_mapping_status='OK'"
        )

    def test_review_markets_gated_via_model_uses_proxy(self):
        """REVIEW markets (goalkeeper_saves, total_corners) must be gated by model_uses_proxy."""
        src = _dashboard_source()
        assert "model_uses_proxy" in src, (
            "Dashboard must filter REVIEW markets via model_uses_proxy=0 in VALUE-only mode"
        )
