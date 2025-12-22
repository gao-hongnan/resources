"""Fixtures for PostgreSQL replication integration testing.

This module provides TestContainers-based fixtures for testing DatabaseCluster
with real PostgreSQL streaming replication. It implements primary-replica
topologies programmatically without requiring external infrastructure.

Design Rationale
----------------
- TestContainers provide per-test isolation and parallel execution compatibility
- Real PostgreSQL streaming replication (not mocked) for authentic testing
- Dynamic cluster configuration allows testing different topologies
- Class-scoped containers amortize expensive setup costs
- Uses Docker internal networking for cross-platform compatibility (Linux, macOS, Windows)
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Self

import asyncpg
import pytest
import pytest_asyncio
from docker import DockerClient
from docker.errors import APIError, NotFound
from pydantic import SecretStr
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from docker.models.networks import Network

from leitmotif.infrastructure.postgres import AsyncConnectionPool, DatabaseCluster
from leitmotif.infrastructure.postgres.config import (
    AsyncpgConfig,
    AsyncpgConnectionSettings,
    AsyncpgPoolSettings,
)

# Network name for container-to-container communication
_NETWORK_NAME = "leitmotif-replication-test-network"


def _get_or_create_network(name: str = _NETWORK_NAME) -> Network:
    """Get or create a Docker network for container communication.

    This enables container-to-container communication using internal IPs,
    which works reliably across all platforms (Linux, macOS, Windows).

    Parameters
    ----------
    name
        Name of the Docker network to create or retrieve.

    Returns
    -------
    Network
        Docker network object.
    """
    client = DockerClient.from_env()
    try:
        return client.networks.get(name)
    except NotFound:
        return client.networks.create(name, driver="bridge")


def _get_container_internal_ip(container: PostgresContainer, network_name: str = _NETWORK_NAME) -> str:
    """Get the internal IP address of a container on the shared network.

    Parameters
    ----------
    container
        The TestContainer instance.
    network_name
        Name of the Docker network.

    Returns
    -------
    str
        Internal IP address of the container.

    Raises
    ------
    RuntimeError
        If container is not connected to the network.
    """
    wrapped = container.get_wrapped_container()
    wrapped.reload()  # Refresh network info

    networks = wrapped.attrs["NetworkSettings"]["Networks"]
    if network_name not in networks:
        msg = f"Container not connected to network {network_name}"
        raise RuntimeError(msg)

    ip_address: str = networks[network_name]["IPAddress"]
    return ip_address


class PostgresPrimaryContainer(PostgresContainer):  # type: ignore[misc]
    """PostgreSQL primary database with streaming replication enabled.

    Configures PostgreSQL for Write-Ahead Logging (WAL) replication with
    sufficient slots and senders for multiple replicas.

    Parameters
    ----------
    network_name
        Docker network name for container-to-container communication.
    **kwargs
        Additional arguments passed to PostgresContainer.

    Examples
    --------
    >>> primary = PostgresPrimaryContainer()
    >>> primary.start()
    >>> await primary.create_replication_user()
    """

    def __init__(self, network_name: str = _NETWORK_NAME, **kwargs: Any) -> None:
        """Initialize primary container with replication configuration."""
        super().__init__(  # type: ignore[misc]
            image="postgres:17-alpine",
            driver="asyncpg",
            **kwargs,
        )
        self._network_name = network_name
        self.with_command(  # type: ignore[misc]
            [
                "postgres",
                "-c",
                "wal_level=replica",
                "-c",
                "max_wal_senders=10",
                "-c",
                "max_replication_slots=10",
                "-c",
                "hot_standby=on",
                "-c",
                "shared_preload_libraries=pg_stat_statements",
                "-c",
                "wal_sender_timeout=5s",
                "-c",
                "wal_receiver_timeout=5s",
                "-c",
                "log_min_messages=WARNING",
            ]
        )

    def start(self) -> Self:
        """Start the container and connect to shared network."""
        result: Self = super().start()  # type: ignore[misc]

        # Connect to shared network for container-to-container communication
        network = _get_or_create_network(self._network_name)
        network.connect(self.get_wrapped_container())

        return result

    async def create_replication_user(self) -> None:
        """Create replication user and configure pg_hba.conf for replication.

        Creates a PostgreSQL role with REPLICATION privilege required for
        streaming replication connections from replicas, and adds the necessary
        pg_hba.conf entry to allow replication connections.

        Raises
        ------
        asyncpg.PostgresError
            If user creation fails or connection cannot be established.
        RuntimeError
            If pg_hba.conf configuration fails.
        """
        # First, add pg_hba.conf entry for replication connections
        # This must be done before creating the user to ensure reload picks it up
        exec_result = self.get_wrapped_container().exec_run(
            [
                "bash",
                "-c",
                """
                set -e
                # Add replication entry to pg_hba.conf if not already present
                PG_HBA="/var/lib/postgresql/data/pg_hba.conf"
                if ! grep -q "host replication replicator" "$PG_HBA"; then
                    echo "host replication replicator 0.0.0.0/0 md5" >> "$PG_HBA"
                    echo "host replication replicator ::/0 md5" >> "$PG_HBA"
                fi
                """,
            ],
        )
        if exec_result.exit_code != 0:
            output = exec_result.output.decode()
            msg = f"Failed to configure pg_hba.conf: {output}"
            raise RuntimeError(msg)

        conn = await asyncpg.connect(
            host=self.get_container_host_ip(),
            port=int(self.get_exposed_port(5432)),
            database=self.dbname,  # type: ignore[arg-type]
            user=self.username,  # type: ignore[arg-type]
            password=self.password,  # type: ignore[arg-type]
        )
        try:
            await conn.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'replicator') THEN
                        CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD 'replica_pass';
                    END IF;
                END
                $$;
            """)
            await conn.execute("SELECT pg_reload_conf()")
        finally:
            await conn.close()


class PostgresReplicaContainer(PostgresContainer):  # type: ignore[misc]
    """PostgreSQL replica database connected via streaming replication.

    Uses pg_basebackup to create a physical replica from the primary database.
    The replica enters hot standby mode, accepting read-only queries while
    continuously replaying WAL from the primary.

    This container uses a keep-alive shell as PID 1 instead of running postgres
    directly. This allows us to stop/start postgres without killing the container.

    Parameters
    ----------
    primary_container : PostgresPrimaryContainer
        The primary database to replicate from.
    network_name
        Docker network name for container-to-container communication.
    **kwargs
        Additional arguments passed to PostgresContainer.

    Examples
    --------
    >>> primary = PostgresPrimaryContainer()
    >>> primary.start()
    >>> replica = PostgresReplicaContainer(primary)
    >>> replica.start()
    >>> await replica.configure_replication()
    """

    def __init__(
        self,
        primary_container: PostgresPrimaryContainer,
        network_name: str = _NETWORK_NAME,
        **kwargs: Any,
    ) -> None:
        """Initialize replica container."""
        super().__init__(  # type: ignore[misc]
            image="postgres:17-alpine",
            driver="asyncpg",
            **kwargs,
        )
        self.primary = primary_container
        self._network_name = network_name
        # Use a keep-alive shell as PID 1 so we can stop/restart postgres
        # without killing the container
        self.with_command(  # type: ignore[misc]
            [
                "sh",
                "-c",
                "while true; do sleep 86400; done",
            ]
        )

    def _connect(self) -> None:
        """Override to skip postgres wait - we start postgres manually after pg_basebackup."""
        # Do nothing - postgres isn't running yet

    def start(self) -> Self:
        """Start the container and connect to shared network."""
        result: Self = super().start()  # type: ignore[misc]

        # Connect to shared network for container-to-container communication
        network = _get_or_create_network(self._network_name)
        network.connect(self.get_wrapped_container())

        return result

    async def configure_replication(self) -> None:
        """Set up streaming replication using pg_basebackup.

        Performs the following steps:
        1. Stops PostgreSQL on replica
        2. Removes existing data directory
        3. Uses pg_basebackup to create a physical copy from primary
        4. Starts PostgreSQL in hot standby mode

        Uses Docker internal networking for cross-platform compatibility.
        The -R flag automatically creates standby.signal and configures
        primary_conninfo in postgresql.auto.conf.

        Raises
        ------
        RuntimeError
            If replication setup fails.
        """
        # Use internal IP for container-to-container communication
        # This works on all platforms: Linux, macOS, Windows
        primary_ip = _get_container_internal_ip(self.primary, self._network_name)
        primary_port = 5432  # Internal port, not mapped port

        # Execute replication setup in replica container
        # Note: We use aggressive shutdown since we'll wipe the data directory anyway
        exec_result = self.get_wrapped_container().exec_run(
            [
                "bash",
                "-c",
                f"""
            echo "=== Container uses keep-alive shell, postgres not running ==="

            echo "=== Ensuring data directory exists and is empty ==="
            mkdir -p /var/lib/postgresql/data
            rm -rf /var/lib/postgresql/data/*

            echo "=== Running pg_basebackup from {primary_ip}:{primary_port} ==="
            PGPASSWORD=replica_pass pg_basebackup \\
                -h {primary_ip} \\
                -p {primary_port} \\
                -U replicator \\
                -D /var/lib/postgresql/data \\
                -Fp -Xs -P -R -v 2>&1

            if [ $? -ne 0 ]; then
                echo "ERROR: pg_basebackup failed!"
                exit 1
            fi

            echo "=== Verifying data files ==="
            ls -la /var/lib/postgresql/data/
            if [ ! -f /var/lib/postgresql/data/global/pg_filenode.map ]; then
                echo "ERROR: pg_filenode.map missing!"
                exit 1
            fi

            echo "=== Showing postgresql.auto.conf (replication config) ==="
            cat /var/lib/postgresql/data/postgresql.auto.conf

            echo "=== Fixing ownership and permissions ==="
            chown -R postgres:postgres /var/lib/postgresql/data
            chmod 700 /var/lib/postgresql/data

            echo "=== Starting PostgreSQL as replica ==="
            su postgres -c 'pg_ctl start -D /var/lib/postgresql/data \\
                -l /var/lib/postgresql/logfile -o "-c hot_standby=on"'
            PG_START_RESULT=$?

            echo "=== PostgreSQL startup log ==="
            cat /var/lib/postgresql/logfile 2>/dev/null || echo "No logfile found"

            if [ $PG_START_RESULT -ne 0 ]; then
                echo "ERROR: pg_ctl start failed with exit code $PG_START_RESULT"
                exit 1
            fi

            echo "=== Verifying PostgreSQL is ready ==="
            for i in $(seq 1 60); do
                if pg_isready -U postgres > /dev/null 2>&1; then
                    echo "PostgreSQL replica is ready!"
                    exit 0
                fi
                sleep 0.5
            done

            echo "PostgreSQL failed to become ready after 30s" >&2
            cat /var/lib/postgresql/logfile 2>/dev/null || true
            exit 1
            """,
            ],
        )

        if exec_result.exit_code != 0:
            output = exec_result.output.decode()
            msg = f"Replication setup failed: {output}"
            raise RuntimeError(msg)

        # Additional wait for replica to establish connection
        await asyncio.sleep(2)


async def verify_replication_active(
    primary_pool: AsyncConnectionPool,
    expected_replicas: int = 1,
) -> bool:
    """Verify streaming replication is active on primary.

    Queries pg_stat_replication to check that the expected number of replicas
    are connected and streaming WAL.

    Parameters
    ----------
    primary_pool : AsyncConnectionPool
        Connection pool to the primary database.
    expected_replicas : int
        Expected number of streaming replicas.

    Returns
    -------
    bool
        True if all expected replicas are in streaming state.
    """
    result = await primary_pool.afetch("""
        SELECT application_name, state, sync_state
        FROM pg_stat_replication
    """)

    if len(result) != expected_replicas:
        return False

    return all(row["state"] == "streaming" for row in result)


async def wait_for_replication(
    primary_pool: AsyncConnectionPool,
    replica_pool: AsyncConnectionPool,
    timeout: float = 5.0,
) -> None:
    """Wait for replica to catch up with primary by comparing LSNs.

    Polls primary and replica LSN positions until they match or timeout occurs.

    Parameters
    ----------
    primary_pool : AsyncConnectionPool
        Connection pool to the primary database.
    replica_pool : AsyncConnectionPool
        Connection pool to the replica database.
    timeout : float
        Maximum time to wait for replication sync in seconds.

    Raises
    ------
    TimeoutError
        If replica does not catch up within timeout.
    """
    start = time.monotonic()

    while time.monotonic() - start < timeout:
        primary_lsn = await primary_pool.afetchval("SELECT pg_current_wal_lsn()::text")
        replica_lsn = await replica_pool.afetchval("SELECT pg_last_wal_replay_lsn()::text")

        if primary_lsn == replica_lsn:
            return  # Caught up!

        await asyncio.sleep(0.1)

    msg = f"Replica did not catch up within {timeout}s"
    raise TimeoutError(msg)


def _build_pool_config(container: PostgresContainer) -> AsyncpgConfig:
    """Build AsyncpgConfig from TestContainer connection parameters.

    Parameters
    ----------
    container : PostgresContainer
        TestContainer instance to extract connection details from.

    Returns
    -------
    AsyncpgConfig
        Configuration object for AsyncConnectionPool.
    """
    return AsyncpgConfig(
        connection=AsyncpgConnectionSettings(
            host=container.get_container_host_ip(),
            port=int(container.get_exposed_port(5432)),  # type: ignore[arg-type]
            database=container.dbname,  # type: ignore[arg-type]
            user=container.username,  # type: ignore[arg-type]
            password=SecretStr(container.password),  # type: ignore[arg-type]
        ),
        pool=AsyncpgPoolSettings(
            min_size=2,
            max_size=10,
        ),
    )


async def _initialize_test_schema(pool: AsyncConnectionPool) -> None:
    """Initialize test schema for replication tests.

    Creates test_replication table with appropriate constraints and indexes.

    Parameters
    ----------
    pool : AsyncConnectionPool
        Connection pool to initialize schema in.
    """
    await pool.aexecute("""
        CREATE TABLE IF NOT EXISTS test_replication (
            id SERIAL PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    await pool.aexecute("""
        CREATE INDEX IF NOT EXISTS idx_test_replication_data
        ON test_replication(data)
    """)


def _cleanup_network(name: str = _NETWORK_NAME) -> None:
    """Clean up Docker network if no containers are using it.

    Parameters
    ----------
    name
        Name of the Docker network to clean up.
    """
    try:
        client = DockerClient.from_env()
        network = client.networks.get(name)
        # Only remove if no containers are connected
        network.reload()
        if not network.attrs.get("Containers"):
            network.remove()
    except NotFound:
        pass  # Network doesn't exist, nothing to clean up
    except APIError:
        pass  # Network in use or other API error, skip cleanup


# ============================================================================
# Pytest Fixtures
# ============================================================================


@pytest.fixture(scope="class")
def primary_container() -> Iterator[PostgresPrimaryContainer]:
    """Class-scoped PostgreSQL primary container.

    Yields
    ------
    PostgresPrimaryContainer
        Started primary container with replication user created.
    """
    container = PostgresPrimaryContainer()
    container.start()
    asyncio.run(container.create_replication_user())
    yield container
    container.stop()
    _cleanup_network()


@pytest.fixture(scope="class")
def replica_container(
    primary_container: PostgresPrimaryContainer,
) -> Iterator[PostgresReplicaContainer]:
    """Class-scoped PostgreSQL replica container.

    Parameters
    ----------
    primary_container : PostgresPrimaryContainer
        Primary database to replicate from.

    Yields
    ------
    PostgresReplicaContainer
        Started replica container with replication configured.
    """
    container = PostgresReplicaContainer(primary_container)
    container.start()
    asyncio.run(container.configure_replication())
    yield container
    container.stop()


@pytest_asyncio.fixture
async def database_cluster(
    primary_container: PostgresPrimaryContainer,
    replica_container: PostgresReplicaContainer,
) -> AsyncIterator[DatabaseCluster]:
    """DatabaseCluster with primary + 1 replica for testing.

    Creates a fully initialized cluster with test schema replicated to replica.

    Parameters
    ----------
    primary_container : PostgresPrimaryContainer
        Primary database container.
    replica_container : PostgresReplicaContainer
        Replica database container.

    Yields
    ------
    DatabaseCluster
        Initialized cluster with primary and one replica.
    """
    primary_config = _build_pool_config(primary_container)
    replica_config = _build_pool_config(replica_container)

    async with DatabaseCluster.from_configs(primary_config, (replica_config,)) as cluster:
        # Initialize test schema on primary
        await _initialize_test_schema(cluster.primary)

        # Wait for schema to replicate
        await asyncio.sleep(1)

        # Clean any existing test data
        await cluster.primary.aexecute("TRUNCATE TABLE test_replication RESTART IDENTITY")
        await asyncio.sleep(0.5)

        yield cluster

        # Cleanup after test
        await cluster.primary.aexecute("TRUNCATE TABLE test_replication RESTART IDENTITY")


@pytest_asyncio.fixture
async def multi_replica_cluster(
    primary_container: PostgresPrimaryContainer,
) -> AsyncIterator[DatabaseCluster]:
    """DatabaseCluster with primary + 3 replicas for round-robin testing.

    Parameters
    ----------
    primary_container : PostgresPrimaryContainer
        Primary database container.

    Yields
    ------
    DatabaseCluster
        Initialized cluster with primary and three replicas.
    """
    replicas: list[PostgresReplicaContainer] = []

    try:
        # Create 3 replica containers
        for _ in range(3):
            replica = PostgresReplicaContainer(primary_container)
            replica.start()
            await replica.configure_replication()
            replicas.append(replica)

        # Build cluster configuration
        primary_cfg = _build_pool_config(primary_container)
        replica_cfgs = tuple(_build_pool_config(r) for r in replicas)

        async with DatabaseCluster.from_configs(primary_cfg, replica_cfgs) as cluster:
            # Initialize test schema
            await _initialize_test_schema(cluster.primary)
            await asyncio.sleep(1)

            # Clean any existing test data
            await cluster.primary.aexecute("TRUNCATE TABLE test_replication RESTART IDENTITY")
            await asyncio.sleep(0.5)

            yield cluster

            # Cleanup after test
            await cluster.primary.aexecute("TRUNCATE TABLE test_replication RESTART IDENTITY")

    finally:
        # Stop all replica containers
        for replica in replicas:
            replica.stop()
