"""Shared fixtures for database tests using canonical TestContainers patterns."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from pixiu.database import AsyncConnectionPool
from pixiu.database.config import AsyncpgSettings, DatabaseConfig, DatabaseConnectionSettings, PoolSettings


@pytest.fixture
async def connection_pool(postgres_container: Any) -> AsyncIterator[AsyncConnectionPool]:
    """Provide an initialized connection pool for testing."""

    # Get the dynamically allocated port
    exposed_port = postgres_container.get_exposed_port(5432)
    host = postgres_container.get_container_host_ip()

    config = DatabaseConfig(
        connection=DatabaseConnectionSettings(
            host=host,
            port=exposed_port,
            database="test_db",
            user="test_user",
            password="test_password",  # type: ignore[arg-type]
            sslmode="disable",
        ),
        pool=PoolSettings(min_size=2, max_size=5, timeout=10.0),
        asyncpg=AsyncpgSettings(
            command_timeout=30.0,
            statement_cache_size=128,
        ),
    )

    pool = AsyncConnectionPool(config)
    await pool.ainitialize()

    # Create test table
    async with pool.aacquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS test_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL,
                age INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    try:
        yield pool
    finally:
        # Clean up test data and close pool
        try:
            async with pool.aacquire() as conn:
                await conn.execute("DROP TABLE IF EXISTS test_users CASCADE")
        except Exception:
            # Ignore cleanup errors
            pass
        await pool.aclose()


# Custom pytest markers are defined in pyproject.toml
