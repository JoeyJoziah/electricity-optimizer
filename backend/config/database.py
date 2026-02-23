"""
Database Configuration and Connection Management

Handles connections to:
- Supabase (PostgreSQL) for application data
- TimescaleDB for time-series price data
- Redis for caching and task queues
"""

import asyncpg
from typing import Optional
from contextlib import asynccontextmanager
from redis import asyncio as aioredis
from supabase import create_client, Client
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

import structlog

from config.settings import settings

logger = structlog.get_logger()


# SQLAlchemy Base for ORM models
Base = declarative_base()


class DatabaseManager:
    """Manages database connections and pooling"""

    def __init__(self):
        self.supabase_client: Optional[Client] = None
        self.timescale_engine = None
        self.timescale_pool: Optional[asyncpg.Pool] = None
        self.redis_client: Optional[aioredis.Redis] = None
        self.async_session_maker = None

    async def initialize(self):
        """Initialize all database connections"""
        await self._init_supabase()
        await self._init_timescaledb()
        await self._init_redis()

    async def _init_supabase(self):
        """Initialize Supabase client (optional for local dev)"""
        if not settings.supabase_url or not settings.supabase_service_key:
            logger.info("supabase_not_configured")
            return

        try:
            self.supabase_client = create_client(
                settings.supabase_url,
                settings.supabase_service_key
            )
            logger.info("supabase_initialized")
        except Exception as e:
            logger.warning("supabase_init_failed", error=str(e))
            if settings.is_production:
                raise
            logger.info("continuing_without_supabase", environment=settings.environment)

    async def _init_timescaledb(self):
        """Initialize database connection pool (TimescaleDB or Neon PostgreSQL)"""
        db_url = settings.effective_database_url
        if not db_url:
            logger.info("database_not_configured")
            return

        try:
            # Handle Neon SSL requirement
            connect_args = {}
            if "neon.tech" in db_url or "neon" in db_url:
                connect_args["ssl"] = "require"

            # Strip sslmode and channel_binding from URL (asyncpg uses connect_args instead)
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed = urlparse(db_url)
            params = parse_qs(parsed.query)
            params.pop("sslmode", None)
            params.pop("channel_binding", None)
            clean_query = urlencode({k: v[0] for k, v in params.items()})
            db_url = urlunparse(parsed._replace(query=clean_query))

            # SQLAlchemy async engine for ORM
            # Optimized for free tier (512MB RAM, single worker)
            sqlalchemy_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
            self.timescale_engine = create_async_engine(
                sqlalchemy_url,
                echo=False,  # Disable SQL echo in production to reduce overhead
                pool_size=2,  # Reduced from 5 for free tier
                max_overflow=3,  # Reduced from 10 for free tier
                pool_pre_ping=True,
                pool_recycle=300,
                pool_timeout=30,  # Add timeout to prevent hanging
                connect_args=connect_args,
            )

            # Create async session maker
            self.async_session_maker = async_sessionmaker(
                self.timescale_engine,
                class_=AsyncSession,
                expire_on_commit=False
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
                        max_inactive_connection_lifetime=300  # Close idle connections after 5 min
                    )
                except Exception as pool_err:
                    logger.warning("asyncpg_pool_unavailable", error=str(pool_err))

            logger.info("database_pool_initialized")
        except Exception as e:
            logger.error("database_init_failed", error=str(e))
            if settings.is_production:
                raise
            logger.info("continuing_without_database", environment=settings.environment)

    async def _init_redis(self):
        """Initialize Redis connection"""
        if not settings.redis_url:
            logger.info("redis_not_configured")
            return

        try:
            # Optimized Redis connection pool for free tier
            self.redis_client = await aioredis.from_url(
                settings.redis_url,
                password=settings.redis_password,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10,  # Reduced from 20 for free tier
                socket_keepalive=True,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )

            # Test connection
            await self.redis_client.ping()

            logger.info("redis_initialized")
        except Exception as e:
            logger.error("redis_init_failed", error=str(e))
            if settings.is_production:
                raise
            logger.info("continuing_without_redis", environment=settings.environment)
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
        """Get TimescaleDB session (SQLAlchemy). Yields None if not initialized."""
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

    async def get_redis_client(self) -> Optional[aioredis.Redis]:
        """Get Redis client (returns None if not initialized)"""
        return self.redis_client

    def get_supabase_client(self) -> Optional[Client]:
        """Get Supabase client (returns None if not initialized)"""
        return self.supabase_client


# Global database manager instance
db_manager = DatabaseManager()


# Dependency injection for FastAPI
async def get_timescale_session():
    """FastAPI dependency for TimescaleDB session"""
    async with db_manager.get_timescale_session() as session:
        yield session


async def get_redis():
    """FastAPI dependency for Redis client"""
    return await db_manager.get_redis_client()


def get_supabase():
    """FastAPI dependency for Supabase client"""
    return db_manager.get_supabase_client()
