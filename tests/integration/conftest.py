"""Shared fixtures for integration tests.

Provides:
- postgres_container: Session-scoped PostgreSQL container
- redis_container: Session-scoped Redis container
- connection_pool: Function-scoped connection pool for tests
- redis_client: Function-scoped Redis client for tests
- test_users table: Automatically created for tests that need it
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import pytest
from pydantic import SecretStr

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from pixiu.database import AsyncConnectionPool
    from pixiu.redis.base import BaseRedisClient


class PostgresContainerProtocol(Protocol):
    """Protocol for PostgreSQL container interface."""

    def get_exposed_port(self, port: int) -> int: ...
    def get_container_host_ip(self) -> str: ...
    def start(self) -> PostgresContainerProtocol: ...
    def stop(self) -> None: ...


def _check_docker_available() -> bool:
    """Check if Docker is available using docker client.

    Tries multiple socket locations for compatibility with:
    - Standard Linux Docker (/var/run/docker.sock)
    - macOS Docker Desktop (~/.docker/run/docker.sock)
    - Custom DOCKER_HOST environment variable

    Returns:
        True if Docker daemon is accessible, False otherwise.
    """
    try:
        from pathlib import Path

        from docker import DockerClient  # type: ignore[import-untyped]
        from docker.errors import DockerException  # type: ignore[import-untyped]

        socket_locations = [
            None,
            "unix:///var/run/docker.sock",
            f"unix://{Path.home()}/.docker/run/docker.sock",
        ]

        for socket_url in socket_locations:
            try:
                if socket_url is None:
                    from docker import from_env  # type: ignore[import-untyped]

                    client = from_env()
                else:
                    client = DockerClient(base_url=socket_url)

                client.ping()
                return True
            except DockerException:
                continue

        return False
    except ImportError:
        return False


def _create_postgres_container() -> PostgresContainerProtocol:
    """Create and configure PostgreSQL test container.

    Returns:
        Configured PostgreSQL container instance.

    Raises:
        ImportError: If testcontainers is not installed.
    """
    from typing import cast

    from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]

    container = PostgresContainer(
        "postgres:16-alpine",
        username="test_user",
        password="test_password",
        dbname="test_db",
    )
    return cast(PostgresContainerProtocol, container)


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainerProtocol]:
    """Provide session-scoped PostgreSQL container.

    Lifecycle:
    - Created once per test session
    - Shared across all tests
    - Automatically cleaned up after session

    Skips:
        If Docker daemon is not available.

    Yields:
        Running PostgreSQL container instance.
    """
    _configure_docker_environment()

    if not _check_docker_available():
        pytest.skip(
            "Docker daemon not available. "
            "Install Docker Desktop (macOS) or Docker Engine (Linux) to run integration tests."
        )

    try:
        container = _create_postgres_container()
    except ImportError as e:
        pytest.skip(f"testcontainers not installed: {e}")

    container.start()

    try:
        yield container
    finally:
        container.stop()


def _configure_docker_environment() -> None:
    """Configure Docker environment for testcontainers.

    Sets DOCKER_HOST if not already set and macOS Docker Desktop socket exists.
    This ensures testcontainers can find Docker on macOS.
    """
    import os
    from pathlib import Path

    if os.environ.get("DOCKER_HOST"):
        return

    macos_socket = Path.home() / ".docker" / "run" / "docker.sock"
    if macos_socket.exists():
        os.environ["DOCKER_HOST"] = f"unix://{macos_socket}"


@pytest.fixture
async def connection_pool(postgres_container: PostgresContainerProtocol) -> AsyncIterator[AsyncConnectionPool]:
    """Provide async connection pool for tests.

    Creates fresh pool for each test function.
    Automatically initializes test schema.

    Configuration:
    - min_size: 2
    - max_size: 10
    - timeout: 30.0 seconds
    - command_timeout: 60.0 seconds

    Yields:
        Initialized connection pool instance.
    """
    from pixiu.database import AsyncConnectionPool, DatabaseConfig, DatabaseConnectionSettings, PoolSettings
    from pixiu.database.config import AsyncpgSettings

    exposed_port = postgres_container.get_exposed_port(5432)
    host = postgres_container.get_container_host_ip()

    config = DatabaseConfig(
        connection=DatabaseConnectionSettings(
            host=host,
            port=exposed_port,
            database="test_db",
            user="test_user",
            password=SecretStr("test_password"),
            sslmode="disable",
        ),
        pool=PoolSettings(
            min_size=2,
            max_size=10,
            timeout=30.0,
        ),
        asyncpg=AsyncpgSettings(
            command_timeout=60.0,
        ),
    )

    pool = AsyncConnectionPool(config)
    await pool.ainitialize()

    await _initialize_test_schema(pool)

    try:
        yield pool
    finally:
        await pool.aclose()


async def _initialize_test_schema(pool: AsyncConnectionPool) -> None:
    """Initialize test database schema.

    Creates:
    - test_users table with proper schema
    - Necessary indexes and constraints

    Args:
        pool: Initialized connection pool.
    """
    async with pool.aacquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                age INTEGER NOT NULL CHECK (age >= 0 AND age <= 150),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_test_users_age
            ON test_users(age)
            """
        )

        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_test_users_username
            ON test_users(username)
            """
        )


# ============================================================================
# Redis Container Fixtures
# ============================================================================


class RedisContainerProtocol(Protocol):
    """Protocol for Redis container interface."""

    def get_exposed_port(self, port: int) -> int: ...
    def get_container_host_ip(self) -> str: ...
    def start(self) -> RedisContainerProtocol: ...
    def stop(self) -> None: ...


def _create_redis_container() -> RedisContainerProtocol:
    """Create and configure Redis test container.

    Returns:
        Configured Redis container instance.

    Raises:
        ImportError: If testcontainers is not installed.
    """
    from typing import cast

    from testcontainers.redis import RedisContainer  # type: ignore[import-untyped]

    container = RedisContainer("redis:7-alpine")
    return cast(RedisContainerProtocol, container)


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainerProtocol]:
    """Provide session-scoped Redis container.

    Lifecycle:
    - Created once per test session
    - Shared across all tests
    - Automatically cleaned up after session

    Skips:
        If Docker daemon is not available.

    Yields:
        Running Redis container instance.
    """
    _configure_docker_environment()

    if not _check_docker_available():
        pytest.skip(
            "Docker daemon not available. "
            "Install Docker Desktop (macOS) or Docker Engine (Linux) to run integration tests."
        )

    try:
        container = _create_redis_container()
    except ImportError as e:
        pytest.skip(f"testcontainers not installed: {e}")

    container.start()

    try:
        yield container
    finally:
        container.stop()


@pytest.fixture
async def redis_client(redis_container: RedisContainerProtocol) -> AsyncIterator[BaseRedisClient]:
    """Provide async Redis client for tests.

    Creates fresh client for each test function.

    Yields:
        Initialized Redis client instance.
    """
    from pixiu.redis import (
        RedisConfig,
        RedisConnectionSettings,
        RedisDriverSettings,
        RedisPoolSettings,
        RedisSSLSettings,
        RedisStandaloneClient,
    )

    exposed_port = redis_container.get_exposed_port(6379)
    host = redis_container.get_container_host_ip()

    config = RedisConfig(
        connection=RedisConnectionSettings(
            host=host,
            port=exposed_port,
            db=0,
            password=SecretStr(""),  # Redis test container has no password
        ),
        ssl=RedisSSLSettings(enabled=False),
        pool=RedisPoolSettings(
            max_connections=10,
            health_check_interval=30,
        ),
        driver=RedisDriverSettings(
            decode_responses=True,
            socket_timeout=30.0,
            socket_connect_timeout=10.0,
        ),
    )

    client = RedisStandaloneClient(config)
    await client.ainitialize()

    # Flush the database before each test
    async with client.aget_client() as redis:
        await redis.flushdb()  # type: ignore[misc]

    try:
        yield client
    finally:
        await client.aclose()
