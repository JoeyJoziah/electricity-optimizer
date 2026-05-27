"""
Integration tests for the drip pipeline's raw SQL (audit follow-up).

The unit tests in ``test_drip_service.py`` mock ``db.execute`` and therefore
cannot catch SQL column-name typos or schema drift. That gap let a real bug
ship: ``process_day2_batch`` referenced ``bill_uploads.status = 'completed'``
but the column is ``parse_status`` (values pending/complete/failed), so the
batch SELECT raised ``column "status" does not exist`` at plan time and
``POST /api/v1/internal/drip/process`` returned HTTP 500 on every daily cron
run after the drip pipeline went live (2026-05-14).

These tests run the actual batch SELECTs against a real migrated schema. The
plan-time column error fires even with zero matching rows, so they catch the
class of bug regardless of DB contents.

The whole module is skipped if ``DATABASE_URL`` is unset (see ``conftest.py``).
Email dispatch helpers are mocked so no mail is sent even if rows happen to
match — the point is to exercise the SELECT, not the send path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.drip_service import DripService

pytestmark = [pytest.mark.asyncio]


async def test_process_day2_batch_query_executes_against_real_schema(db):
    """The day2 batch SELECT must plan and execute (regression for bu.status)."""
    svc = DripService(db)
    # Never dispatch real email, even if live rows match — only verify the query.
    svc._send_day2_connected = AsyncMock(return_value=False)
    svc._send_day2_pending = AsyncMock(return_value=False)

    result = await svc.process_day2_batch()

    assert {"total", "sent_a", "sent_b", "errors"} <= set(result)
    assert result["total"] >= 0


async def test_process_day7_batch_query_executes_against_real_schema(db):
    """The day7 batch SELECT must plan and execute."""
    svc = DripService(db)
    svc._send_day7_upgrade = AsyncMock(return_value=False)

    result = await svc.process_day7_batch()

    assert {"total", "sent", "errors"} <= set(result)
    assert result["total"] >= 0
