"""
Tests for the CSV-cache player-name preservation fix (2026-06).

Root cause: raw_rows_from_odds_api_cache() stored raw_payload = json.dumps(csv_row),
which has no outcome.label.  extract_label_from_raw() therefore returned None,
causing lookup_player("", ...) to fail and all player prop rows to become UNMATCHED.

Fix: _lookup_outcome_from_source_file() re-reads the raw JSON using the
raw_market_index / raw_odds_index / source_file stored in the CSV, and embeds
the full outcome dict in raw_payload so extract_label_from_raw() can recover
outcome.label (the player name).
"""
from __future__ import annotations

import csv
import json
import pathlib
import tempfile

import pytest

from app.betting.odds_driven import (
    _lookup_outcome_from_source_file,
    extract_label_from_raw,
    raw_rows_from_odds_api_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BOOKMAKER = "Bet365"

# Minimal raw JSON that mirrors the real Odds-API.io structure.
def _make_raw_json(markets: list[dict]) -> dict:
    return {
        "fetched_at_utc": "2026-06-12T18:19:23Z",
        "response_json": {
            "id": 99999,
            "home": "TeamA",
            "away": "TeamB",
            "bookmakers": {
                BOOKMAKER: markets,
            },
        },
    }


# ---------------------------------------------------------------------------
# _lookup_outcome_from_source_file
# ---------------------------------------------------------------------------

class TestLookupOutcomeFromSourceFile:

    def _write_json(self, tmp_path: pathlib.Path, markets: list[dict]) -> pathlib.Path:
        p = tmp_path / "raw.json"
        p.write_text(json.dumps(_make_raw_json(markets)), encoding="utf-8")
        return p

    def test_recovers_player_label(self, tmp_path):
        markets = [
            {
                "name": "Player Fouls Committed",
                "odds": [
                    {"label": "Ivan Sunjic (2)", "hdp": 0.5, "over": "1.071"},
                    {"label": "Richie Laryea (1)", "hdp": 0.5, "over": "1.083"},
                ],
            }
        ]
        p = self._write_json(tmp_path, markets)
        outcome = _lookup_outcome_from_source_file(str(p), BOOKMAKER, 0, 0)
        assert outcome.get("label") == "Ivan Sunjic (2)"

    def test_recovers_second_outcome(self, tmp_path):
        markets = [
            {
                "name": "Player Tackles",
                "odds": [
                    {"label": "Richie Laryea (1)", "hdp": 0.5, "over": "1.062"},
                    {"label": "Amar Dedic (2)", "hdp": 0.5, "over": "1.083"},
                ],
            }
        ]
        p = self._write_json(tmp_path, markets)
        outcome = _lookup_outcome_from_source_file(str(p), BOOKMAKER, 0, 1)
        assert outcome.get("label") == "Amar Dedic (2)"

    def test_recovers_second_market(self, tmp_path):
        markets = [
            {"name": "ML", "odds": [{"home": "1.8"}]},
            {
                "name": "Player Passes",
                "odds": [
                    {"label": "Jonathan David (1)", "hdp": 25, "over": "1.200"},
                ],
            },
        ]
        p = self._write_json(tmp_path, markets)
        outcome = _lookup_outcome_from_source_file(str(p), BOOKMAKER, 1, 0)
        assert outcome.get("label") == "Jonathan David (1)"

    def test_returns_empty_when_file_missing(self, tmp_path):
        result = _lookup_outcome_from_source_file(str(tmp_path / "no_such.json"), BOOKMAKER, 0, 0)
        assert result == {}

    def test_returns_empty_when_source_file_none(self):
        result = _lookup_outcome_from_source_file(None, BOOKMAKER, 0, 0)
        assert result == {}

    def test_returns_empty_when_index_out_of_range(self, tmp_path):
        markets = [{"name": "ML", "odds": [{"home": "1.8"}]}]
        p = self._write_json(tmp_path, markets)
        assert _lookup_outcome_from_source_file(str(p), BOOKMAKER, 0, 99) == {}
        assert _lookup_outcome_from_source_file(str(p), BOOKMAKER, 99, 0) == {}

    def test_returns_empty_when_index_not_int(self, tmp_path):
        markets = [{"name": "ML", "odds": [{"home": "1.8"}]}]
        p = self._write_json(tmp_path, markets)
        assert _lookup_outcome_from_source_file(str(p), BOOKMAKER, "", "") == {}
        assert _lookup_outcome_from_source_file(str(p), BOOKMAKER, None, None) == {}

    def test_fallback_to_no_latency_bookmaker_key(self, tmp_path):
        """Bet365 sometimes appears as 'Bet365 (no latency)' in the JSON."""
        p = tmp_path / "raw.json"
        data = {
            "response_json": {
                "id": 1,
                "home": "A", "away": "B",
                "bookmakers": {
                    "Bet365 (no latency)": [
                        {"name": "Player Tackles", "odds": [{"label": "Player X (1)", "hdp": 0.5, "over": "1.1"}]}
                    ]
                },
            }
        }
        p.write_text(json.dumps(data), encoding="utf-8")
        outcome = _lookup_outcome_from_source_file(str(p), "Bet365", 0, 0)
        assert outcome.get("label") == "Player X (1)"


# ---------------------------------------------------------------------------
# raw_rows_from_odds_api_cache — player label end-to-end
# ---------------------------------------------------------------------------

class TestRawRowsFromOddsApiCachePlayerLabel:

    def _build_csv_and_json(self, tmp_path: pathlib.Path) -> pathlib.Path:
        """Write a minimal raw JSON + a matching normalized CSV."""
        markets = [
            # market_index=0: non-player market (ML) — outcome has no label
            {
                "name": "ML",
                "updatedAt": "2026-01-01T00:00:00Z",
                "odds": [{"home": "1.800", "draw": "3.500", "away": "4.750"}],
            },
            # market_index=1: player prop — outcome has label
            {
                "name": "Player Fouls Committed",
                "updatedAt": "2026-01-01T00:00:00Z",
                "odds": [
                    {"label": "Ivan Sunjic (2)", "hdp": 0.5, "over": "1.071"},
                    {"label": "Richie Laryea (1)", "hdp": 0.5, "over": "1.083"},
                ],
            },
            # market_index=2: player passes
            {
                "name": "Player Passes",
                "updatedAt": "2026-01-01T00:00:00Z",
                "odds": [
                    {"label": "Jonathan David (1)", "hdp": 25, "over": "1.200"},
                ],
            },
            # market_index=3: goalkeeper saves
            {
                "name": "Goalkeeper Saves",
                "updatedAt": "2026-01-01T00:00:00Z",
                "odds": [
                    {"label": "Martin Zlomislic", "hdp": 1.5, "over": "1.250"},
                ],
            },
        ]
        raw_json_path = tmp_path / "raw.json"
        raw_json_path.write_text(json.dumps(_make_raw_json(markets)), encoding="utf-8")

        csv_path = tmp_path / "normalized.csv"
        rows = [
            # ML home
            dict(fetched_at_utc="2026-01-01T00:00:00Z", event_id="1", sport="Football",
                 league_name="Test", league_slug="test", home="TeamA", away="TeamB",
                 event_date_utc="2026-01-01T00:00:00Z", event_status="pending",
                 bookmaker="Bet365", market_name="ML", market_updated_at="",
                 selection_name="TeamA", line="", odds_decimal="1.800",
                 raw_market_index=0, raw_odds_index=0, source_file=str(raw_json_path)),
            # Player Fouls Committed — Ivan Sunjic
            dict(fetched_at_utc="2026-01-01T00:00:00Z", event_id="1", sport="Football",
                 league_name="Test", league_slug="test", home="TeamA", away="TeamB",
                 event_date_utc="2026-01-01T00:00:00Z", event_status="pending",
                 bookmaker="Bet365", market_name="Player Fouls Committed", market_updated_at="",
                 selection_name="Over 0.5", line="0.5", odds_decimal="1.071",
                 raw_market_index=1, raw_odds_index=0, source_file=str(raw_json_path)),
            # Player Fouls Committed — Richie Laryea
            dict(fetched_at_utc="2026-01-01T00:00:00Z", event_id="1", sport="Football",
                 league_name="Test", league_slug="test", home="TeamA", away="TeamB",
                 event_date_utc="2026-01-01T00:00:00Z", event_status="pending",
                 bookmaker="Bet365", market_name="Player Fouls Committed", market_updated_at="",
                 selection_name="Over 0.5", line="0.5", odds_decimal="1.083",
                 raw_market_index=1, raw_odds_index=1, source_file=str(raw_json_path)),
            # Player Passes — Jonathan David
            dict(fetched_at_utc="2026-01-01T00:00:00Z", event_id="1", sport="Football",
                 league_name="Test", league_slug="test", home="TeamA", away="TeamB",
                 event_date_utc="2026-01-01T00:00:00Z", event_status="pending",
                 bookmaker="Bet365", market_name="Player Passes", market_updated_at="",
                 selection_name="Over 25", line="25", odds_decimal="1.200",
                 raw_market_index=2, raw_odds_index=0, source_file=str(raw_json_path)),
            # Goalkeeper Saves
            dict(fetched_at_utc="2026-01-01T00:00:00Z", event_id="1", sport="Football",
                 league_name="Test", league_slug="test", home="TeamA", away="TeamB",
                 event_date_utc="2026-01-01T00:00:00Z", event_status="pending",
                 bookmaker="Bet365", market_name="Goalkeeper Saves", market_updated_at="",
                 selection_name="Over 1.5", line="1.5", odds_decimal="1.250",
                 raw_market_index=3, raw_odds_index=0, source_file=str(raw_json_path)),
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return csv_path

    def test_player_fouls_committed_carries_label(self, tmp_path):
        csv_path = self._build_csv_and_json(tmp_path)
        rows = raw_rows_from_odds_api_cache(csv_path)
        fouls_rows = [r for r in rows if r["raw_market_name"] == "Player Fouls Committed"]
        assert len(fouls_rows) == 2

        labels = []
        for r in fouls_rows:
            label = extract_label_from_raw(r["raw_payload"])
            assert label is not None, "Player label must be recoverable from raw_payload"
            assert label != "", "Player label must not be empty"
            labels.append(label)

        # Parenthetical team-number suffix must be stripped by extract_label_from_raw
        assert "Ivan Sunjic" in labels
        assert "Richie Laryea" in labels

    def test_player_passes_carries_label(self, tmp_path):
        csv_path = self._build_csv_and_json(tmp_path)
        rows = raw_rows_from_odds_api_cache(csv_path)
        passes_row = next(r for r in rows if r["raw_market_name"] == "Player Passes")
        label = extract_label_from_raw(passes_row["raw_payload"])
        assert label == "Jonathan David"

    def test_goalkeeper_saves_carries_label(self, tmp_path):
        csv_path = self._build_csv_and_json(tmp_path)
        rows = raw_rows_from_odds_api_cache(csv_path)
        gk_row = next(r for r in rows if r["raw_market_name"] == "Goalkeeper Saves")
        label = extract_label_from_raw(gk_row["raw_payload"])
        assert label == "Martin Zlomislic"

    def test_non_player_market_still_works(self, tmp_path):
        """ML row must still load correctly; no label is fine."""
        csv_path = self._build_csv_and_json(tmp_path)
        rows = raw_rows_from_odds_api_cache(csv_path)
        ml_row = next(r for r in rows if r["raw_market_name"] == "ML")
        # ML has no label; extract_label_from_raw may return None — that is correct
        payload = json.loads(ml_row["raw_payload"])
        assert "outcome" in payload  # new structure always has outcome key
        assert ml_row["raw_odds"] == 1.8
        assert ml_row["raw_selection_name"] == "TeamA"

    def test_row_below_min_odds_still_filtered(self, tmp_path):
        """Rows with odds <= 1.0 must still be skipped."""
        csv_path = tmp_path / "tiny.csv"
        raw_json = tmp_path / "raw.json"
        raw_json.write_text(json.dumps(_make_raw_json([])), encoding="utf-8")
        row = dict(fetched_at_utc="", event_id="", sport="", league_name="",
                   league_slug="", home="A", away="B", event_date_utc="",
                   event_status="", bookmaker="Bet365", market_name="ML",
                   market_updated_at="", selection_name="A", line="",
                   odds_decimal="0.900",
                   raw_market_index=0, raw_odds_index=0, source_file=str(raw_json))
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)
        assert raw_rows_from_odds_api_cache(csv_path) == []

    def test_missing_source_file_falls_back_gracefully(self, tmp_path):
        """If source_file doesn't exist, outcome is {}, row still loads."""
        csv_path = tmp_path / "fallback.csv"
        row = dict(fetched_at_utc="", event_id="", sport="", league_name="",
                   league_slug="", home="A", away="B", event_date_utc="",
                   event_status="", bookmaker="Bet365",
                   market_name="Player Fouls Committed", market_updated_at="",
                   selection_name="Over 0.5", line="0.5", odds_decimal="1.5",
                   raw_market_index=0, raw_odds_index=0,
                   source_file=str(tmp_path / "nonexistent.json"))
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)
        rows = raw_rows_from_odds_api_cache(csv_path)
        assert len(rows) == 1
        payload = json.loads(rows[0]["raw_payload"])
        assert payload["outcome"] == {}  # graceful fallback


# ---------------------------------------------------------------------------
# Regression: Player Shots and Shots on Target must still work
# ---------------------------------------------------------------------------

class TestPlayerShotsRegressionAfterFix:

    def test_player_shots_label_preserved(self, tmp_path):
        markets = [
            {
                "name": "Player Shots",
                "updatedAt": "2026-01-01T00:00:00Z",
                "odds": [
                    {"label": "Alphonso Davies (1)", "hdp": 0.5, "over": "1.400", "under": "2.750"},
                ],
            }
        ]
        raw_json = tmp_path / "raw.json"
        raw_json.write_text(json.dumps(_make_raw_json(markets)), encoding="utf-8")

        csv_path = tmp_path / "shots.csv"
        # "Player Shots" with over+under produces TWO CSV rows for the same odds_index
        base = dict(fetched_at_utc="", event_id="", sport="", league_name="", league_slug="",
                    home="A", away="B", event_date_utc="", event_status="", bookmaker="Bet365",
                    market_name="Player Shots", market_updated_at="",
                    line="0.5", raw_market_index=0, source_file=str(raw_json))
        rows_in = [
            {**base, "selection_name": "Over 0.5", "odds_decimal": "1.400", "raw_odds_index": 0},
            {**base, "selection_name": "Under 0.5", "odds_decimal": "2.750", "raw_odds_index": 0},
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows_in[0].keys()))
            writer.writeheader()
            writer.writerows(rows_in)

        rows_out = raw_rows_from_odds_api_cache(csv_path)
        assert len(rows_out) == 2
        for r in rows_out:
            label = extract_label_from_raw(r["raw_payload"])
            assert label == "Alphonso Davies", f"expected 'Alphonso Davies', got {label!r}"

    def test_player_shots_on_target_label_preserved(self, tmp_path):
        markets = [
            {
                "name": "Player Shots on Target",
                "updatedAt": "2026-01-01T00:00:00Z",
                "odds": [
                    {"label": "Haris Tabakovic (2)", "hdp": 0.5, "over": "1.833"},
                ],
            }
        ]
        raw_json = tmp_path / "raw.json"
        raw_json.write_text(json.dumps(_make_raw_json(markets)), encoding="utf-8")

        csv_path = tmp_path / "sot.csv"
        row = dict(fetched_at_utc="", event_id="", sport="", league_name="", league_slug="",
                   home="A", away="B", event_date_utc="", event_status="", bookmaker="Bet365",
                   market_name="Player Shots on Target", market_updated_at="",
                   selection_name="Over 0.5", line="0.5", odds_decimal="1.833",
                   raw_market_index=0, raw_odds_index=0, source_file=str(raw_json))
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            writer.writeheader()
            writer.writerow(row)

        rows_out = raw_rows_from_odds_api_cache(csv_path)
        assert len(rows_out) == 1
        label = extract_label_from_raw(rows_out[0]["raw_payload"])
        assert label == "Haris Tabakovic"
