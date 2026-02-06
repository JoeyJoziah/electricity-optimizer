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

from config.settings import settings


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
            print("ℹ️  Supabase not configured - skipping (optional for local dev)")
            return

        try:
            self.supabase_client = create_client(
                settings.supabase_url,
                settings.supabase_service_key
            )
            print("✅ Supabase client initialized")
        except Exception as e:
            print(f"⚠️  Failed to initialize Supabase: {e}")
            if settings.is_production:
                raise
            print("ℹ️  Continuing without Supabase (development mode)")

    async def _init_timescaledb(self):
        """Initialize TimescaleDB connection pool"""
        try:
            # SQLAlchemy async engine for ORM
            self.timescale_engine = create_async_engine(
                settings.timescaledb_url.replace("postgresql://", "postgresql+asyncpg://"),
                echo=settings.debug,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600
            )

            # Create async session maker
            self.async_session_maker = async_sessionmaker(
                self.timescale_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            # Also create asyncpg pool for raw queries
            self.timescale_pool = await asyncpg.create_pool(
                settings.timescaledb_url,
                min_size=5,
                max_size=20,
                command_timeout=60
            )

            print("✅ TimescaleDB connection pool initialized")
        except Exception as e:
            print(f"❌ Failed to initialize TimescaleDB: {e}")
            raise

    async def _init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = await aioredis.from_url(
                settings.redis_url,
                password=settings.redis_password,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50
            )

            # Test connection
            await self.redis_client.ping()

            print("✅ Redis connection initialized")
        except Exception as e:
            print(f"❌ Failed to initialize Redis: {e}")
            raise

    async def close(self):
        """Close all database connections"""
        if self.timescale_pool:
            await self.timescale_pool.close()
            print("🔌 TimescaleDB pool closed")

        if self.timescale_engine:
            await self.timescale_engine.dispose()
            print("🔌 TimescaleDB engine disposed")

        if self.redis_client:
            await self.redis_client.close()
            print("🔌 Redis connection closed")

    @asynccontextmanager
    async def get_timescale_session(self):
        """Get TimescaleDB session (SQLAlchemy)"""
        if not self.async_session_maker:
            raise RuntimeError("Database not initialized")

        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def execute_timescale_query(self, query: str, *args):
        """Execute raw query on TimescaleDB"""
        if not self.timescale_pool:
            raise RuntimeError("TimescaleDB pool not initialized")

        async with self.timescale_pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def get_redis_client(self) -> aioredis.Redis:
        """Get Redis client"""
        if not self.redis_client:
            raise RuntimeError("Redis not initialized")
        return self.redis_client

    def get_supabase_client(self) -> Client:
        """Get Supabase client"""
        if not self.supabase_client:
            raise RuntimeError("Supabase not initialized")
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
