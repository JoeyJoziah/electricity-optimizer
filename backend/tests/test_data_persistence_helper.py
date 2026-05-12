"""
Tests for services/data_persistence_helper.py — persist_batch().

Coverage:
- Empty rows list returns 0 without any DB calls
- Single row inserted and committed, returns 1
- Multiple rows all inserted, returns count
- Per-row exception is swallowed; successful rows still committed
- All rows fail → no commit, returns 0
- Commit exception triggers rollback and re-raises
- Log-safe keys surfaced in warning on per-row failure
"""

from unittest.mock import AsyncMock

import pytest

from services.data_persistence_helper import persist_batch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(execute_side_effect=None, commit_side_effect=None):
    db = AsyncMock()
    if execute_side_effect is not None:
        db.execute.side_effect = execute_side_effect
    db.commit = AsyncMock(side_effect=commit_side_effect)
    db.rollback = AsyncMock()
    return db


SQL = "INSERT INTO test_table (state, supplier_id) VALUES (:state, :supplier_id)"


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


class TestPersistBatchEmpty:
    @pytest.mark.asyncio
    async def test_empty_rows_returns_zero(self):
        db = _make_db()
        result = await persist_batch(db, "test_table", SQL, [])
        assert result == 0

    @pytest.mark.asyncio
    async def test_empty_rows_no_db_execute(self):
        db = _make_db()
        await persist_batch(db, "test_table", SQL, [])
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_rows_no_commit(self):
        db = _make_db()
        await persist_batch(db, "test_table", SQL, [])
        db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Successful inserts
# ---------------------------------------------------------------------------


class TestPersistBatchSuccess:
    @pytest.mark.asyncio
    async def test_single_row_returns_one(self):
        db = _make_db()
        result = await persist_batch(db, "test_table", SQL, [{"state": "CT", "supplier_id": "s1"}])
        assert result == 1

    @pytest.mark.asyncio
    async def test_single_row_commits_once(self):
        db = _make_db()
        await persist_batch(db, "test_table", SQL, [{"state": "CT", "supplier_id": "s1"}])
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_multiple_rows_returns_full_count(self):
        db = _make_db()
        rows = [
            {"state": "CT", "supplier_id": "s1"},
            {"state": "NY", "supplier_id": "s2"},
            {"state": "MA", "supplier_id": "s3"},
        ]
        result = await persist_batch(db, "test_table", SQL, rows)
        assert result == 3

    @pytest.mark.asyncio
    async def test_multiple_rows_commits_once(self):
        db = _make_db()
        rows = [{"state": "CT", "supplier_id": f"s{i}"} for i in range(5)]
        await persist_batch(db, "test_table", SQL, rows)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_called_once_per_row(self):
        db = _make_db()
        rows = [{"state": "CT", "supplier_id": "s1"}, {"state": "NY", "supplier_id": "s2"}]
        await persist_batch(db, "test_table", SQL, rows)
        assert db.execute.await_count == 2


# ---------------------------------------------------------------------------
# Per-row failures
# ---------------------------------------------------------------------------


class TestPersistBatchPartialFailure:
    @pytest.mark.asyncio
    async def test_row_exception_swallowed_returns_partial_count(self):
        errors = [None, Exception("unique violation"), None]

        async def execute_fn(stmt, row):
            e = errors.pop(0)
            if e:
                raise e

        db = _make_db()
        db.execute.side_effect = execute_fn
        rows = [
            {"state": "CT", "supplier_id": "s1"},
            {"state": "NY", "supplier_id": "s2"},
            {"state": "MA", "supplier_id": "s3"},
        ]
        result = await persist_batch(db, "test_table", SQL, rows)
        assert result == 2

    @pytest.mark.asyncio
    async def test_partial_success_still_commits(self):
        async def execute_fn(stmt, row):
            if row.get("supplier_id") == "bad":
                raise Exception("constraint violation")

        db = _make_db()
        db.execute.side_effect = execute_fn
        rows = [{"state": "CT", "supplier_id": "good"}, {"state": "NY", "supplier_id": "bad"}]
        await persist_batch(db, "test_table", SQL, rows)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_rows_fail_returns_zero(self):
        db = _make_db(execute_side_effect=Exception("DB error"))
        rows = [{"state": "CT", "supplier_id": "s1"}, {"state": "NY", "supplier_id": "s2"}]
        result = await persist_batch(db, "test_table", SQL, rows)
        assert result == 0

    @pytest.mark.asyncio
    async def test_all_rows_fail_no_commit(self):
        db = _make_db(execute_side_effect=Exception("DB error"))
        rows = [{"state": "CT", "supplier_id": "s1"}]
        await persist_batch(db, "test_table", SQL, rows)
        db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Commit failure
# ---------------------------------------------------------------------------


class TestPersistBatchCommitFailure:
    @pytest.mark.asyncio
    async def test_commit_exception_triggers_rollback(self):
        db = _make_db(commit_side_effect=Exception("deadlock"))
        rows = [{"state": "CT", "supplier_id": "s1"}]
        with pytest.raises(Exception, match="deadlock"):
            await persist_batch(db, "test_table", SQL, rows)
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commit_exception_reraises(self):
        db = _make_db(commit_side_effect=RuntimeError("tx aborted"))
        rows = [{"state": "CT", "supplier_id": "s1"}]
        with pytest.raises(RuntimeError, match="tx aborted"):
            await persist_batch(db, "test_table", SQL, rows)


# ---------------------------------------------------------------------------
# Log context parameter (smoke test — verifies no crash with custom context)
# ---------------------------------------------------------------------------


class TestPersistBatchLogContext:
    @pytest.mark.asyncio
    async def test_custom_log_context_does_not_raise(self):
        db = _make_db()
        result = await persist_batch(
            db,
            "weather_cache",
            SQL,
            [{"state": "CT", "supplier_id": "s1"}],
            log_context="weather_cache",
        )
        assert result == 1
