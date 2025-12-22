"""Integration tests for DatabaseCluster replica behavior.

Tests real PostgreSQL streaming replication using TestContainers to verify:
- Primary-only write enforcement
- Read-after-write consistency guarantees
- Replica eventual consistency
- Round-robin replica selection
- Cluster health monitoring (healthy, degraded, unhealthy states)
- Fallback to primary when no replicas available
- Replication lag detection and monitoring

All tests use real PostgreSQL instances with actual streaming replication,
not mocks, following the project's integration testing philosophy.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import asyncpg
import pytest

from leitmotif.infrastructure.postgres.enums import HealthStatus

if TYPE_CHECKING:
    from leitmotif.infrastructure.postgres import DatabaseCluster

    from .replication_fixtures import (
        PostgresPrimaryContainer,
        PostgresReplicaContainer,
    )


# ============================================================================
# Test Class 1: Primary Write Exclusivity
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.replication
@pytest.mark.usefixtures("database_cluster")
class TestPrimaryWriteExclusivity:
    """Verify writes only succeed on primary, replicas reject writes."""

    async def test_write_to_primary_succeeds(self, database_cluster: DatabaseCluster) -> None:
        """Writing to primary should succeed.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        await database_cluster.primary.aexecute(
            "INSERT INTO test_replication (data) VALUES ($1)",
            "primary_write_test",
        )

        result = await database_cluster.primary.afetchval(
            "SELECT COUNT(*) FROM test_replication WHERE data = $1",
            "primary_write_test",
        )
        assert result == 1

    async def test_write_to_replica_fails_gracefully(self, database_cluster: DatabaseCluster) -> None:
        """Writing to replica should fail with read-only error.

        Replicas are in hot standby mode and reject write operations.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        with pytest.raises(asyncpg.exceptions.ReadOnlySQLTransactionError):
            await database_cluster.replica.aexecute(
                "INSERT INTO test_replication (data) VALUES ($1)",
                "should_fail",
            )

    async def test_update_on_replica_fails(self, database_cluster: DatabaseCluster) -> None:
        """UPDATE operations on replica should fail.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        # First insert on primary
        await database_cluster.primary.aexecute(
            "INSERT INTO test_replication (data) VALUES ($1)",
            "test_data",
        )
        await asyncio.sleep(0.3)  # Wait for replication

        # Attempt update on replica
        with pytest.raises(asyncpg.exceptions.ReadOnlySQLTransactionError):
            await database_cluster.replica.aexecute(
                "UPDATE test_replication SET data = $1 WHERE data = $2",
                "modified",
                "test_data",
            )

    async def test_delete_on_replica_fails(self, database_cluster: DatabaseCluster) -> None:
        """DELETE operations on replica should fail.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        # First insert on primary
        await database_cluster.primary.aexecute(
            "INSERT INTO test_replication (data) VALUES ($1)",
            "delete_test",
        )
        await asyncio.sleep(0.3)

        # Attempt delete on replica
        with pytest.raises(asyncpg.exceptions.ReadOnlySQLTransactionError):
            await database_cluster.replica.aexecute(
                "DELETE FROM test_replication WHERE data = $1",
                "delete_test",
            )


# ============================================================================
# Test Class 2: Read-After-Write Consistency
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.replication
@pytest.mark.usefixtures("database_cluster")
class TestReadAfterWriteConsistency:
    """Verify primary reads immediately see own writes."""

    async def test_primary_read_after_write(self, database_cluster: DatabaseCluster) -> None:
        """Read from primary immediately sees own writes (no sleep needed).

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        unique_data = f"consistency_{uuid.uuid4().hex[:8]}"

        await database_cluster.primary.aexecute(
            "INSERT INTO test_replication (data) VALUES ($1)",
            unique_data,
        )

        # Immediate read - no sleep needed
        result = await database_cluster.primary.afetchrow(
            "SELECT * FROM test_replication WHERE data = $1",
            unique_data,
        )

        assert result is not None
        assert result["data"] == unique_data

    async def test_multiple_writes_and_reads(self, database_cluster: DatabaseCluster) -> None:
        """Multiple consecutive writes and reads maintain consistency.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        test_values = [f"value_{i}" for i in range(5)]

        for value in test_values:
            await database_cluster.primary.aexecute(
                "INSERT INTO test_replication (data) VALUES ($1)",
                value,
            )

            # Immediate verification
            result = await database_cluster.primary.afetchval(
                "SELECT COUNT(*) FROM test_replication WHERE data = $1",
                value,
            )
            assert result == 1


# ============================================================================
# Test Class 3: Replica Eventual Consistency
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.replication
@pytest.mark.usefixtures("database_cluster")
class TestReplicaEventualConsistency:
    """Verify replicas serve reads with eventual consistency."""

    async def test_replica_eventual_consistency(self, database_cluster: DatabaseCluster) -> None:
        """Replica reads are eventually consistent.

        Write to primary, verify replica sees data after replication delay.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        unique_data = f"eventual_{uuid.uuid4().hex[:8]}"

        # 1. Write to primary
        await database_cluster.primary.aexecute(
            "INSERT INTO test_replication (data) VALUES ($1)",
            unique_data,
        )

        # 2. Wait for replication (~200-300ms typical)
        await asyncio.sleep(0.3)

        # 3. Replica should have data
        eventual_result = await database_cluster.replica.afetchrow(
            "SELECT * FROM test_replication WHERE data = $1",
            unique_data,
        )

        assert eventual_result is not None
        assert eventual_result["data"] == unique_data

    async def test_bulk_insert_replication(self, database_cluster: DatabaseCluster) -> None:
        """Bulk inserts replicate to replica.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        test_data = [f"bulk_{i}" for i in range(20)]

        # Bulk insert on primary
        await database_cluster.primary.aexecutemany(
            "INSERT INTO test_replication (data) VALUES ($1)",
            [(d,) for d in test_data],
        )

        # Wait for replication
        await asyncio.sleep(0.5)

        # Verify count on replica
        count = await database_cluster.replica.afetchval(
            "SELECT COUNT(*) FROM test_replication WHERE data LIKE 'bulk_%'"
        )
        assert count == 20


# ============================================================================
# Test Class 4: Replica Round-Robin Selection
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.replication
@pytest.mark.usefixtures("multi_replica_cluster")
class TestReplicaRoundRobin:
    """Verify .replica property distributes queries across replicas."""

    async def test_round_robin_distribution(self, multi_replica_cluster: DatabaseCluster) -> None:
        """Successive .replica calls should hit different replicas.

        Parameters
        ----------
        multi_replica_cluster : DatabaseCluster
            Cluster with primary + 3 replicas.
        """
        assert multi_replica_cluster.replica_count == 3
        assert multi_replica_cluster.has_replicas

        # Track which replica pool is returned
        # Since AsyncConnectionPool doesn't expose host directly,
        # we track pool object identity
        pool_ids = []
        for _ in range(30):
            pool = multi_replica_cluster.replica
            pool_ids.append(id(pool))

        # Count unique pool objects
        unique_pools = len(set(pool_ids))
        assert unique_pools == 3, "Should distribute across all 3 replicas"

        # Verify distribution is relatively even (allow variance)
        from collections import Counter

        distribution = Counter(pool_ids)
        for count in distribution.values():
            # Each replica should get ~10 queries (allow ±3 for variance)
            assert 7 <= count <= 13, f"Uneven distribution: {distribution}"

    async def test_replica_property_cycles_through_replicas(self, multi_replica_cluster: DatabaseCluster) -> None:
        """Verify cycling behavior by checking sequence pattern.

        Parameters
        ----------
        multi_replica_cluster : DatabaseCluster
            Cluster with primary + 3 replicas.
        """
        # Get sequence of pool IDs
        sequence = [id(multi_replica_cluster.replica) for _ in range(9)]

        # First 3 should be unique (one of each replica)
        assert len(set(sequence[:3])) == 3

        # Pattern should repeat every 3 calls
        assert sequence[0] == sequence[3] == sequence[6]
        assert sequence[1] == sequence[4] == sequence[7]
        assert sequence[2] == sequence[5] == sequence[8]


# ============================================================================
# Test Class 5: Cluster Health Checking
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.replication
@pytest.mark.usefixtures("database_cluster")
class TestClusterHealthChecking:
    """Verify cluster health status reflects actual state."""

    async def test_healthy_cluster_status(self, database_cluster: DatabaseCluster) -> None:
        """Healthy cluster reports HEALTHY status.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        health = await database_cluster.ahealth_check()

        assert health.status == HealthStatus.HEALTHY
        assert health.is_healthy
        assert health.is_operational
        assert health.primary.status == HealthStatus.HEALTHY
        assert health.healthy_replica_count == 1
        assert health.total_replica_count == 1
        assert health.replicas[0].status == HealthStatus.HEALTHY

    async def test_degraded_cluster_status(
        self,
        primary_container: PostgresPrimaryContainer,
        replica_container: PostgresReplicaContainer,
    ) -> None:
        """Cluster with unhealthy replica reports DEGRADED.

        Parameters
        ----------
        primary_container : PostgresPrimaryContainer
            Primary database container.
        replica_container : PostgresReplicaContainer
            Replica database container.
        """
        from .replication_fixtures import (
            PostgresReplicaContainer,
            _build_pool_config,
            _initialize_test_schema,
        )

        # Create second replica and immediately stop it
        dead_replica = PostgresReplicaContainer(primary_container)
        dead_replica.start()
        await dead_replica.configure_replication()

        # Get config BEFORE stopping the container (can't query ports after stop)
        dead_replica_cfg = _build_pool_config(dead_replica)
        dead_replica.stop()  # Kill it!

        try:
            from leitmotif.infrastructure.postgres import DatabaseCluster

            replica_cfgs = (
                _build_pool_config(replica_container),
                dead_replica_cfg,
            )

            cluster = DatabaseCluster.from_configs(_build_pool_config(primary_container), replica_cfgs)

            # Initialize primary only (can't initialize dead replica)
            await cluster._primary.ainitialize()  # noqa: SLF001
            await _initialize_test_schema(cluster.primary)

            # Initialize only the healthy replica
            await cluster._replicas[0].ainitialize()  # noqa: SLF001

            # Health check should show degraded state
            health = await cluster.ahealth_check()

            assert health.status == HealthStatus.DEGRADED
            assert not health.is_healthy
            assert health.is_operational  # Primary still works
            assert health.healthy_replica_count == 1
            assert health.total_replica_count == 2

            await cluster.aclose()

        finally:
            # Cleanup
            pass  # dead_replica already stopped

    async def test_cluster_properties(self, database_cluster: DatabaseCluster) -> None:
        """Cluster properties reflect actual configuration.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        assert database_cluster.replica_count == 1
        assert database_cluster.has_replicas


# ============================================================================
# Test Class 6: Fallback to Primary
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.replication
class TestFallbackToPrimary:
    """Verify .replica returns primary when no replicas configured."""

    async def test_replica_property_returns_primary_when_no_replicas(
        self, primary_container: PostgresPrimaryContainer
    ) -> None:
        """With no replicas, .replica returns primary.

        Parameters
        ----------
        primary_container : PostgresPrimaryContainer
            Primary database container.
        """
        from leitmotif.infrastructure.postgres import DatabaseCluster

        from .replication_fixtures import _build_pool_config, _initialize_test_schema

        async with DatabaseCluster.from_configs(_build_pool_config(primary_container), ()) as cluster:
            await _initialize_test_schema(cluster.primary)

            assert cluster.replica_count == 0
            assert not cluster.has_replicas
            assert cluster.replica is cluster.primary

            # Should work for reads
            await cluster.primary.aexecute(
                "INSERT INTO test_replication (data) VALUES ($1)",
                "fallback_test",
            )

            result = await cluster.replica.afetchval(
                "SELECT COUNT(*) FROM test_replication WHERE data = $1",
                "fallback_test",
            )
            assert result == 1

    async def test_single_pool_operations(self, primary_container: PostgresPrimaryContainer) -> None:
        """Cluster with no replicas operates as single pool.

        Parameters
        ----------
        primary_container : PostgresPrimaryContainer
            Primary database container.
        """
        from leitmotif.infrastructure.postgres import DatabaseCluster

        from .replication_fixtures import _build_pool_config, _initialize_test_schema

        async with DatabaseCluster.from_configs(_build_pool_config(primary_container), None) as cluster:
            await _initialize_test_schema(cluster.primary)

            # Both primary and replica point to same pool
            await cluster.primary.aexecute(
                "INSERT INTO test_replication (data) VALUES ($1)",
                "single_pool",
            )

            # Replica read hits same pool
            result = await cluster.replica.afetchval(
                "SELECT data FROM test_replication WHERE data = $1",
                "single_pool",
            )
            assert result == "single_pool"


# ============================================================================
# Test Class 7: Replication Lag Detection
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.replication
@pytest.mark.usefixtures("database_cluster")
class TestReplicationLag:
    """Verify replication lag detection and monitoring."""

    async def test_lag_monitoring_via_postgres_stats(self, database_cluster: DatabaseCluster) -> None:
        """Monitor replication lag using pg_stat_replication.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        stats = await database_cluster.primary.afetch("""
            SELECT
                application_name,
                state,
                replay_lag,
                write_lag,
                flush_lag
            FROM pg_stat_replication
        """)

        assert len(stats) >= 1, "Should have at least 1 replica connection"

        for stat in stats:
            assert stat["state"] == "streaming", "Replica should be streaming"
            # Lag might be None if replication is completely caught up
            if stat["replay_lag"] is not None:
                # Lag should be very small in tests
                assert stat["replay_lag"].total_seconds() < 2.0

    async def test_detectable_replication_lag(
        self,
        database_cluster: DatabaseCluster,
        replica_container: PostgresReplicaContainer,
    ) -> None:
        """Verify we can detect replication lag by pausing WAL replay.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        replica_container : PostgresReplicaContainer
            Replica container for direct control.
        """
        replica_conn = await asyncpg.connect(
            host=replica_container.get_container_host_ip(),
            port=int(replica_container.get_exposed_port(5432)),
            database=replica_container.dbname,  # type: ignore[arg-type]
            user=replica_container.username,  # type: ignore[arg-type]
            password=replica_container.password,  # type: ignore[arg-type]
        )

        try:
            # Pause WAL replay on replica
            await replica_conn.execute("SELECT pg_wal_replay_pause()")
            await asyncio.sleep(0.2)

            # Write to primary
            unique_data = f"lag_test_{uuid.uuid4().hex[:8]}"
            await database_cluster.primary.aexecute(
                "INSERT INTO test_replication (data) VALUES ($1)",
                unique_data,
            )

            # Primary sees data immediately
            primary_result = await database_cluster.primary.afetchval(
                "SELECT COUNT(*) FROM test_replication WHERE data = $1",
                unique_data,
            )
            assert primary_result == 1

            # Replica does NOT see data (WAL paused)
            await asyncio.sleep(0.5)
            replica_result = await database_cluster.replica.afetchval(
                "SELECT COUNT(*) FROM test_replication WHERE data = $1",
                unique_data,
            )
            assert replica_result == 0, "Replica should not see data while paused"

            # Resume WAL replay
            await replica_conn.execute("SELECT pg_wal_replay_resume()")
            await asyncio.sleep(0.5)

            # Now replica sees data
            final_result = await database_cluster.replica.afetchval(
                "SELECT COUNT(*) FROM test_replication WHERE data = $1",
                unique_data,
            )
            assert final_result == 1, "Replica should see data after resume"

        finally:
            # Ensure WAL replay is resumed even if test fails
            await replica_conn.execute("SELECT pg_wal_replay_resume()")
            await replica_conn.close()

    async def test_replication_slot_active(self, database_cluster: DatabaseCluster) -> None:
        """Verify replication slot is active and tracking WAL.

        Parameters
        ----------
        database_cluster : DatabaseCluster
            Cluster with primary + 1 replica.
        """
        # Note: pg_basebackup with -Xs doesn't create replication slots
        # but we can verify pg_stat_replication shows active connections
        stats = await database_cluster.primary.afetch("""
            SELECT
                pid,
                usename,
                application_name,
                client_addr,
                backend_start,
                state,
                sent_lsn,
                write_lsn,
                flush_lsn,
                replay_lsn
            FROM pg_stat_replication
        """)

        assert len(stats) == 1, "Should have exactly 1 replica"
        stat = stats[0]

        assert stat["usename"] == "replicator"
        assert stat["state"] == "streaming"
        assert stat["sent_lsn"] is not None
        assert stat["replay_lsn"] is not None
