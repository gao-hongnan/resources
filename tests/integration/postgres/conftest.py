"""Shared fixtures for leitmotif.infrastructure.postgres integration tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from docker import from_env  # type: ignore[import-untyped]
from docker.errors import DockerException  # type: ignore[import-untyped]
from pydantic import SecretStr
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]

# Import replication fixtures to make them available to tests
from .replication_fixtures import (  # noqa: F401
    database_cluster,
    multi_replica_cluster,
    primary_container,
    replica_container,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from leitmotif.infrastructure.postgres import AsyncConnectionPool

TEST_USERS_TABLE = "test_users"


def pytest_configure(config: pytest.Config) -> None:  # noqa: ARG001
    """Configure Docker environment for testcontainers.

    This hook runs before any fixtures, ensuring Docker is properly configured
    for both local development and CI environments.
    """
    if not os.environ.get("DOCKER_HOST"):
        possible_sockets = [
            Path("/var/run/docker.sock"),
            Path.home() / ".docker" / "run" / "docker.sock",
        ]
        for socket_path in possible_sockets:
            if socket_path.exists():
                os.environ["DOCKER_HOST"] = f"unix://{socket_path}"
                os.environ["TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE"] = str(socket_path)
                break

    # Ryuk (testcontainers cleanup daemon) has known issues on macOS/Docker Desktop
    if sys.platform == "darwin" and not os.environ.get("TESTCONTAINERS_RYUK_DISABLED"):
        os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"


def _is_docker_available() -> bool:
    """Check if Docker daemon is accessible.

    Returns
    -------
    bool
        True if Docker daemon responds to ping, False otherwise.

    Notes
    -----
    This validates actual daemon connectivity, not just socket existence.
    Important for CI environments where socket may exist but daemon is not running.

    """
    try:
        client = from_env()
        client.ping()
    except (ImportError, DockerException):
        return False
    else:
        return True


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Provide session-scoped PostgreSQL container.

    Yields
    ------
    PostgresContainer
        Running PostgreSQL container instance.

    Notes
    -----
    Uses context manager for automatic cleanup. The `driver="asyncpg"` parameter
    optimizes connection handling for asyncpg-based pools.

    """
    if not _is_docker_available():
        pytest.skip("Docker daemon not accessible")

    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as container:
        yield container


@pytest_asyncio.fixture
async def asyncpg_pool(postgres_container: PostgresContainer) -> AsyncIterator[AsyncConnectionPool]:
    """Provide async connection pool for tests.

    Creates a fresh pool for each test function using container's
    dynamically assigned credentials.

    Yields
    ------
    AsyncConnectionPool
        Initialized connection pool instance.

    """
    from leitmotif.infrastructure.postgres import (
        AsyncConnectionPool,
        AsyncpgConfig,
        AsyncpgConnectionSettings,
        AsyncpgPoolSettings,
        AsyncpgServerSettings,
        AsyncpgStatementCacheSettings,
    )

    config = AsyncpgConfig(
        connection=AsyncpgConnectionSettings(
            host=postgres_container.get_container_host_ip(),
            port=int(postgres_container.get_exposed_port(5432)),
            database=postgres_container.dbname,
            user=postgres_container.username,
            password=SecretStr(postgres_container.password),
        ),
        pool=AsyncpgPoolSettings(min_size=2, max_size=10, command_timeout=60.0),
        statement_cache=AsyncpgStatementCacheSettings(max_size=128),
        server_settings=AsyncpgServerSettings(application_name="leitmotif_test", jit="off"),
    )

    async with AsyncConnectionPool(config) as pool:
        await _initialize_test_schema(pool)
        yield pool


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_test_users(asyncpg_pool: AsyncConnectionPool) -> None:
    """Truncate test_users table before each test for isolation.

    This fixture uses pytest's autouse mechanism to run automatically before
    every test that uses the `asyncpg_pool` fixture.

    How pytest autouse fixtures work
    --------------------------------
    1. `autouse=True` tells pytest to run this fixture automatically without
       explicit request in test function parameters.

    2. This fixture depends on `asyncpg_pool` (declared as parameter). Pytest
       only runs autouse fixtures when their dependencies are satisfied.

    3. When a test requests `asyncpg_pool`, pytest:
       - Resolves and creates the `asyncpg_pool` fixture
       - Detects this autouse fixture depends on `asyncpg_pool`
       - Automatically runs this fixture BEFORE the test executes

    4. Tests that don't use `asyncpg_pool` (like TestPoolLifecycle tests that
       create their own pools) won't trigger this fixture.

    Why this pattern
    ----------------
    - Eliminates duplicate cleanup code in every test class
    - Ensures test isolation (each test starts with empty table)
    - Single source of truth for cleanup logic

    Parameters
    ----------
    asyncpg_pool
        The connection pool fixture. This parameter creates an implicit
        dependency - pytest only runs this fixture for tests using asyncpg_pool.
    """
    async with asyncpg_pool.aacquire() as conn:
        await conn.execute(f"TRUNCATE TABLE {TEST_USERS_TABLE} RESTART IDENTITY CASCADE")


async def _initialize_test_schema(pool: AsyncConnectionPool) -> None:
    """Initialize test database schema.

    Creates the test_users table with proper schema and indexes.

    Parameters
    ----------
    pool
        Initialized connection pool.

    """
    async with pool.aacquire() as conn:
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {TEST_USERS_TABLE} (
                id SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                age INTEGER NOT NULL CHECK (age >= 0 AND age <= 150),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TEST_USERS_TABLE}_age ON {TEST_USERS_TABLE}(age)")
        await conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TEST_USERS_TABLE}_username ON {TEST_USERS_TABLE}(username)"
        )


@pytest_asyncio.fixture
async def small_pool(postgres_container: PostgresContainer) -> AsyncIterator[AsyncConnectionPool]:
    """Provide small pool for exhaustion testing.

    Pool configuration optimized for testing pool limits:
    - min_size: 1 (minimal warm connections)
    - max_size: 3 (small pool to easily exhaust)
    - timeout: 2.0s (reasonable for tests)

    Yields
    ------
    AsyncConnectionPool
        Small initialized pool for exhaustion scenarios.

    """
    from leitmotif.infrastructure.postgres import (
        AsyncConnectionPool,
        AsyncpgConfig,
        AsyncpgConnectionSettings,
        AsyncpgPoolSettings,
        AsyncpgServerSettings,
        AsyncpgStatementCacheSettings,
    )

    config = AsyncpgConfig(
        connection=AsyncpgConnectionSettings(
            host=postgres_container.get_container_host_ip(),
            port=int(postgres_container.get_exposed_port(5432)),
            database=postgres_container.dbname,
            user=postgres_container.username,
            password=SecretStr(postgres_container.password),
        ),
        pool=AsyncpgPoolSettings(min_size=1, max_size=3, command_timeout=30.0),
        statement_cache=AsyncpgStatementCacheSettings(max_size=128),
        server_settings=AsyncpgServerSettings(application_name="leitmotif_test_small", jit="off"),
    )

    async with AsyncConnectionPool(config) as pool:
        yield pool


@pytest_asyncio.fixture
async def dynamic_pool(postgres_container: PostgresContainer) -> AsyncIterator[AsyncConnectionPool]:
    """Provide pool for size dynamics testing.

    Pool configuration for testing scaling behavior:
    - min_size: 2 (warm pool with minimum connections)
    - max_size: 10 (allow scaling under load)
    - timeout: 5.0s

    Yields
    ------
    AsyncConnectionPool
        Dynamic pool for scaling scenarios.

    """
    from leitmotif.infrastructure.postgres import (
        AsyncConnectionPool,
        AsyncpgConfig,
        AsyncpgConnectionSettings,
        AsyncpgPoolSettings,
        AsyncpgServerSettings,
        AsyncpgStatementCacheSettings,
    )

    config = AsyncpgConfig(
        connection=AsyncpgConnectionSettings(
            host=postgres_container.get_container_host_ip(),
            port=int(postgres_container.get_exposed_port(5432)),
            database=postgres_container.dbname,
            user=postgres_container.username,
            password=SecretStr(postgres_container.password),
        ),
        pool=AsyncpgPoolSettings(min_size=2, max_size=10, command_timeout=60.0),
        statement_cache=AsyncpgStatementCacheSettings(max_size=128),
        server_settings=AsyncpgServerSettings(application_name="leitmotif_test_dynamic", jit="off"),
    )

    async with AsyncConnectionPool(config) as pool:
        yield pool


@pytest_asyncio.fixture
async def timeout_pool(postgres_container: PostgresContainer) -> AsyncIterator[AsyncConnectionPool]:
    """Provide pool with short command timeout for timeout testing.

    Pool configuration for testing timeout behavior:
    - command_timeout: 2.0s (short timeout for testing)
    - min_size: 2, max_size: 5

    Yields
    ------
    AsyncConnectionPool
        Pool configured for timeout testing.

    """
    from leitmotif.infrastructure.postgres import (
        AsyncConnectionPool,
        AsyncpgConfig,
        AsyncpgConnectionSettings,
        AsyncpgPoolSettings,
        AsyncpgServerSettings,
        AsyncpgStatementCacheSettings,
    )

    config = AsyncpgConfig(
        connection=AsyncpgConnectionSettings(
            host=postgres_container.get_container_host_ip(),
            port=int(postgres_container.get_exposed_port(5432)),
            database=postgres_container.dbname,
            user=postgres_container.username,
            password=SecretStr(postgres_container.password),
        ),
        pool=AsyncpgPoolSettings(min_size=2, max_size=5, command_timeout=2.0),
        statement_cache=AsyncpgStatementCacheSettings(max_size=128),
        server_settings=AsyncpgServerSettings(application_name="leitmotif_test_timeout", jit="off"),
    )

    async with AsyncConnectionPool(config) as pool:
        yield pool


@pytest_asyncio.fixture
async def conflict_pool(postgres_container: PostgresContainer) -> AsyncIterator[AsyncConnectionPool]:
    """Provide pool for transaction conflict testing.

    Pool configuration for testing concurrent transactions:
    - min_size: 2
    - max_size: 10 (allow concurrent transactions)
    - command_timeout: 30.0s (longer for conflict scenarios)

    Yields
    ------
    AsyncConnectionPool
        Pool configured for transaction conflict testing.

    """
    from leitmotif.infrastructure.postgres import (
        AsyncConnectionPool,
        AsyncpgConfig,
        AsyncpgConnectionSettings,
        AsyncpgPoolSettings,
        AsyncpgServerSettings,
        AsyncpgStatementCacheSettings,
    )

    config = AsyncpgConfig(
        connection=AsyncpgConnectionSettings(
            host=postgres_container.get_container_host_ip(),
            port=int(postgres_container.get_exposed_port(5432)),
            database=postgres_container.dbname,
            user=postgres_container.username,
            password=SecretStr(postgres_container.password),
        ),
        pool=AsyncpgPoolSettings(min_size=2, max_size=10, command_timeout=30.0),
        statement_cache=AsyncpgStatementCacheSettings(max_size=128),
        server_settings=AsyncpgServerSettings(application_name="leitmotif_test_conflict", jit="off"),
    )

    async with AsyncConnectionPool(config) as pool:
        yield pool


@pytest_asyncio.fixture
async def recovery_pool(postgres_container: PostgresContainer) -> AsyncIterator[AsyncConnectionPool]:
    """Provide pool for connection failure recovery testing.

    Pool configuration for testing failure recovery:
    - min_size: 2
    - max_size: 5
    - command_timeout: 10.0s

    Creates test_recovery table for recovery tests.

    Yields
    ------
    AsyncConnectionPool
        Pool configured for recovery testing.

    """
    from leitmotif.infrastructure.postgres import (
        AsyncConnectionPool,
        AsyncpgConfig,
        AsyncpgConnectionSettings,
        AsyncpgPoolSettings,
        AsyncpgServerSettings,
        AsyncpgStatementCacheSettings,
    )

    config = AsyncpgConfig(
        connection=AsyncpgConnectionSettings(
            host=postgres_container.get_container_host_ip(),
            port=int(postgres_container.get_exposed_port(5432)),
            database=postgres_container.dbname,
            user=postgres_container.username,
            password=SecretStr(postgres_container.password),
        ),
        pool=AsyncpgPoolSettings(min_size=2, max_size=5, command_timeout=10.0),
        statement_cache=AsyncpgStatementCacheSettings(max_size=128),
        server_settings=AsyncpgServerSettings(application_name="leitmotif_test_recovery", jit="off"),
    )

    async with AsyncConnectionPool(config) as pool:
        # Create test table for recovery tests
        async with pool.aacquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS test_recovery (
                    id SERIAL PRIMARY KEY,
                    value INTEGER,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        try:
            yield pool
        finally:
            async with pool.aacquire() as conn:
                await conn.execute("DROP TABLE IF EXISTS test_recovery CASCADE")
