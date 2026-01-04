"""
API Dependencies

FastAPI dependency injection for shared resources.
"""

from typing import AsyncGenerator, Optional

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from ..config import settings


# Redis connection pool
_redis_pool: Optional[redis.ConnectionPool] = None


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """
    Get Redis connection from pool.

    Yields:
        Redis client instance
    """
    global _redis_pool

    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=20,
        )

    client = redis.Redis(connection_pool=_redis_pool)
    try:
        yield client
    finally:
        await client.close()


# Database engine and session factory
_engine = None
_session_factory = None


def get_db_engine():
    """Get or create database engine."""
    global _engine

    if _engine is None:
        _engine = create_async_engine(
            settings.postgres_url,
            echo=settings.app_debug,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )

    return _engine


def get_session_factory():
    """Get or create session factory."""
    global _session_factory

    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_db_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _session_factory


async def get_db_pool() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session from pool.

    Yields:
        AsyncSession instance
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
