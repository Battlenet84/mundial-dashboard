"""
Tests for ensure_db_available() — the .gz bootstrap function in odds_driven.py.
"""
from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path

import pytest

from app.betting.odds_driven import ensure_db_available


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_sqlite_gz(directory: Path, name: str = "test.db") -> tuple[Path, Path]:
    """Write a compressed minimal SQLite DB into directory. Return (db_path, gz_path)."""
    db_path = directory / name
    gz_path = Path(str(db_path) + ".gz")
    tmp = directory / "_seed.db"
    con = sqlite3.connect(tmp)
    con.execute("CREATE TABLE _meta (k TEXT)")
    con.commit()
    con.close()
    with open(tmp, "rb") as src, gzip.open(gz_path, "wb") as dst:
        dst.write(src.read())
    tmp.unlink()
    return db_path, gz_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEnsureDbAvailable:

    def test_decompresses_when_db_absent(self, tmp_path):
        db_path, _ = _make_minimal_sqlite_gz(tmp_path)
        assert not db_path.exists()

        result = ensure_db_available(db_path)

        assert result is True
        assert db_path.exists()

    def test_decompressed_file_is_valid_sqlite(self, tmp_path):
        db_path, _ = _make_minimal_sqlite_gz(tmp_path)
        ensure_db_available(db_path)

        header = db_path.read_bytes()[:6]
        assert header == b"SQLite", f"Unexpected header: {header!r}"

    def test_no_op_when_db_already_exists(self, tmp_path):
        db_path, _ = _make_minimal_sqlite_gz(tmp_path)
        db_path.write_bytes(b"sentinel_content")

        result = ensure_db_available(db_path)

        assert result is False
        assert db_path.read_bytes() == b"sentinel_content"

    def test_no_op_when_gz_absent(self, tmp_path):
        db_path = tmp_path / "test.db"

        result = ensure_db_available(db_path)

        assert result is False
        assert not db_path.exists()

    def test_no_tmp_file_left_after_success(self, tmp_path):
        db_path, _ = _make_minimal_sqlite_gz(tmp_path)
        ensure_db_available(db_path)

        assert list(tmp_path.glob("*.tmp")) == []

    def test_does_not_overwrite_existing_db(self, tmp_path):
        db_path, _ = _make_minimal_sqlite_gz(tmp_path)
        original = b"DO_NOT_OVERWRITE" * 100
        db_path.write_bytes(original)

        ensure_db_available(db_path)

        assert db_path.read_bytes() == original

    def test_decompressed_db_is_queryable(self, tmp_path):
        db_path, _ = _make_minimal_sqlite_gz(tmp_path)
        ensure_db_available(db_path)

        con = sqlite3.connect(db_path)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.close()
        assert "_meta" in tables
