"""Shared batch INSERT logic for internal data pipeline endpoints."""

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# Keys that are safe to surface in warning log lines without leaking PII.
_SAFE_LOG_KEYS = ("state", "supplier_id", "query")


async def persist_batch(
    db: AsyncSession,
    table: str,
    sql: str,
    rows: list[dict],
    log_context: str = "",
) -> int:
    """Execute batch INSERT and return count of persisted rows.

    Parameters
    ----------
    db:
        Active async SQLAlchemy session.
    table:
        Destination table name (used only in log messages).
    sql:
        Parameterised INSERT statement accepted by ``sqlalchemy.text()``.
    rows:
        Sequence of parameter dicts, one per row to insert.
    log_context:
        Short prefix for structured log event names, e.g. ``"weather_cache"``.

    Returns
    -------
    int
        Number of rows successfully inserted and committed.
    """
    persisted = 0
    insert_stmt = text(sql)
    for row in rows:
        try:
            await db.execute(insert_stmt, row)
            persisted += 1
        except Exception as e:
            safe_extras = {k: v for k, v in row.items() if k in _SAFE_LOG_KEYS}
            logger.warning(
                f"{log_context}_insert_failed",
                error=str(e),
                **safe_extras,
            )
    if persisted:
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        logger.info(f"{log_context}_persisted", count=persisted)
    return persisted
