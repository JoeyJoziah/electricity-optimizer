"""
Database Configuration and Connection Management

Handles connections to:
- Neon PostgreSQL for application data (+ neon_auth schema for authentication)
- Redis for caching and task queues
"""

from contextlib import asynccontextmanager

import asyncpg
import structlog
from redis import asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from config.settings import settings

logger = structlog.get_logger()


# SQLAlchemy Base for ORM models
Base = declarative_base()


class DatabaseManager:
    """Manages database connections and pooling"""

    def __init__(self):
        self.timescale_engine = None
        self.timescale_pool: asyncpg.Pool | None = None
        self.redis_client: aioredis.Redis | None = None
        self.async_session_maker = None

    async def initialize(self):
        """Initialize all database connections"""
        await self._init_database()
        await self._init_redis()

    async def _init_database(self):
        """Initialize database connection pool (Neon PostgreSQL)"""
        db_url = settings.database_url
        if not db_url:
            logger.warning(
                "database_not_configured",
                msg="DATABASE_URL not set — all DB operations will be skipped",
            )
            return

        try:
            # Handle Neon SSL requirement
            connect_args = {}
            from urllib.parse import urlparse

            _host = urlparse(db_url).hostname or ""
            if _host.endswith(".neon.tech"):
                connect_args["ssl"] = "require"
                # PgBouncer transaction-mode pooling does not support named prepared
                # statements (they are bound to a backend connection, but transaction
                # mode may hand the client a different backend each transaction).
                # Setting statement_cache_size=0 disables asyncpg's prepared-statement
                # cache, preventing intermittent
                # InvalidSQLStatementNameError on Neon's pooled endpoint.
                connect_args["statement_cache_size"] = 0

            # Strip sslmode and channel_binding from URL (asyncpg uses connect_args instead)
            from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

            parsed = urlparse(db_url)
            params = parse_qs(parsed.query)
            params.pop("sslmode", None)
            params.pop("channel_binding", None)
            clean_query = urlencode({k: v[0] for k, v in params.items()})
            db_url = urlunparse(parsed._replace(query=clean_query))

            # SQLAlchemy async engine for ORM
            # Pool sizing is configurable via DB_POOL_SIZE and DB_MAX_OVERFLOW
            # env vars (defaults: 5 + 10 = 15 max). See docs/SCALING_PLAN.md.
            # Neon pooler endpoint supports many more than 10 connections via
            # PgBouncer multiplexing; increase DB_POOL_SIZE / DB_MAX_OVERFLOW
            # freely on the pooler endpoint without hitting Neon limits.
            sqlalchemy_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
            self.timescale_engine = create_async_engine(
                sqlalchemy_url,
                echo=False,  # Disable SQL echo in production to reduce overhead
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                pool_pre_ping=True,
                pool_recycle=200,  # recycle 100s before Neon's 5-min auto-suspend
                pool_timeout=20,  # fail faster to avoid cascading timeouts
                connect_args=connect_args,
            )

            # Create async session maker
            self.async_session_maker = async_sessionmaker(
                self.timescale_engine, class_=AsyncSession, expire_on_commit=False
            )

            # Create asyncpg pool for raw queries (skip for Neon - use SQLAlchemy only)
            # Optimized pool sizes for free tier
            if "neon.tech" not in db_url:
                try:
                    self.timescale_pool = await asyncpg.create_pool(
                        db_url,
                        min_size=1,  # Reduced from 2
                        max_size=5,  # Reduced from 10 for free tier
                        command_timeout=30,  # Reduced from 60 to fail faster
                        max_inactive_connection_lifetime=300,  # Close idle connections after 5 min
                    )
                except Exception as pool_err:
                    logger.warning("asyncpg_pool_unavailable", error=str(pool_err))

            logger.info("database_pool_initialized")
        except Exception as e:
            logger.error("database_init_failed", error=str(e))
            logger.warning("continuing_without_database", environment=settings.environment)

    async def _init_redis(self):
        """Initialize Redis connection"""
        if not settings.redis_url:
            logger.info("redis_not_configured")
            return

        try:
            self.redis_client = await aioredis.from_url(
                settings.redis_url,
                password=settings.redis_password,
                encoding="utf-8",
                decode_responses=True,
                max_connections=settings.redis_max_connections,
                socket_keepalive=True,
                socket_connect_timeout=5,
                retry_on_timeout=True,
            )

            # Test connection
            await self.redis_client.ping()

            logger.info("redis_initialized")
        except Exception as e:
            logger.error("redis_init_failed", error=str(e))
            logger.warning("continuing_without_redis", environment=settings.environment)
            self.redis_client = None

    async def close(self):
        """Close all database connections"""
        if self.timescale_pool:
            await self.timescale_pool.close()
            logger.info("database_pool_closed")

        if self.timescale_engine:
            await self.timescale_engine.dispose()
            logger.info("database_engine_disposed")

        if self.redis_client:
            await self.redis_client.close()
            logger.info("redis_connection_closed")

    @asynccontextmanager
    async def get_timescale_session(self):
        """Get database session (SQLAlchemy). Yields None if not initialized."""
        if not self.async_session_maker:
            yield None
            return

        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def _execute_raw_query(self, query: str, *args):
        """Execute raw query on database (asyncpg pool or SQLAlchemy fallback)"""
        if self.timescale_pool:
            async with self.timescale_pool.acquire() as conn:
                return await conn.fetch(query, *args)

        if self.timescale_engine:
            from sqlalchemy import text

            async with self.timescale_engine.connect() as conn:
                result = await conn.execute(text(query))
                return result.fetchall()

        return []

    async def get_redis_client(self) -> aioredis.Redis | None:
        """Get Redis client (returns None if not initialized)"""
        return self.redis_client


# Global database manager instance
db_manager = DatabaseManager()


# Dependency injection for FastAPI
async def get_timescale_session():
    """FastAPI dependency for database session"""
    async with db_manager.get_timescale_session() as session:
        yield session


async def get_redis():
    """FastAPI dependency for Redis client"""
    return await db_manager.get_redis_client()
