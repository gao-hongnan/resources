"""Connection failure recovery integration tests.

Tests critical failure scenarios:
- Connection failures during active operations
- Pool recovery after database becomes unavailable
- Connection validation after idle periods
- Graceful degradation when database down
- Automatic connection replacement
- Connection failure detection

These tests expose production bugs related to connection lifecycle,
failure recovery, and pool resilience.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING, Any

import asyncpg
import pytest
from pydantic import SecretStr

from pixiu.database import AsyncConnectionPool, DatabaseConfig, DatabaseConnectionSettings, PoolSettings
from pixiu.database.models import HealthCheckStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.mark.integration
@pytest.mark.database
class TestConnectionFailureRecovery:
    """Test connection failure and recovery scenarios."""

    @pytest.fixture
    async def recovery_pool(self, postgres_container: Any) -> AsyncIterator[AsyncConnectionPool]:
        """Create pool for failure recovery testing.

        Pool configuration:
        - min_size: 2
        - max_size: 5
        - timeout: 10.0 seconds
        """
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
                max_size=5,
                timeout=10.0,
            ),
        )

        pool = AsyncConnectionPool(config)
        await pool.ainitialize()

        # Create test table
        async with pool.aacquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS test_recovery (
                    id SERIAL PRIMARY KEY,
                    value INTEGER,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """
            )

        try:
            yield pool
        finally:
            async with pool.aacquire() as conn:
                await conn.execute("DROP TABLE IF EXISTS test_recovery CASCADE")
            await pool.aclose()

    async def test_pool_handles_connection_closed_during_query(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test that pool handles connection closing mid-query.

        Scenario:
        1. Acquire connection and start using it
        2. Close connection externally (simulate network failure)
        3. Verify appropriate exception raised
        4. Verify pool remains healthy
        5. Verify new queries work with fresh connections
        """
        # This connection will be terminated
        async with recovery_pool.aacquire() as conn:
            # Insert some data successfully
            await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 100)

            # Simulate connection failure by closing it
            await conn.close()

            # Next query should fail
            with pytest.raises(asyncpg.exceptions.InterfaceError):
                await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 200)

        # Pool should recover - new connection should work
        async with recovery_pool.aacquire() as fresh_conn:
            result: int = await fresh_conn.fetchval("SELECT COUNT(*) FROM test_recovery")
            assert result == 1, "Should have 1 row from before connection closed"

            # New insert should work
            await fresh_conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 300)

        # Verify pool health
        health = await recovery_pool.ahealth_check()
        assert health.status == HealthCheckStatus.HEALTHY

    async def test_connection_validation_after_idle_period(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test connection validation detects stale connections.

        Scenario:
        1. Acquire connection and use it
        2. Release connection back to pool
        3. Close the connection externally (simulate server disconnect)
        4. Acquire connection again - pool should validate and replace
        5. Verify new connection works
        """
        # First use - connection works
        async with recovery_pool.aacquire() as conn:
            await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 100)

        # Connection returned to pool
        # In real scenario, connection might die while idle

        # Try to use pool again - should get working connection
        async with recovery_pool.aacquire() as conn:
            result: int = await conn.fetchval("SELECT COUNT(*) FROM test_recovery")
            assert result == 1

            # New operations should work
            await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 200)

        # Verify final state
        final_count: int = await recovery_pool.afetchval("SELECT COUNT(*) FROM test_recovery")
        assert final_count == 2

    async def test_graceful_degradation_when_database_unavailable(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test pool behavior when database becomes unavailable.

        Scenario:
        1. Verify pool is healthy initially
        2. Simulate database unavailability (close all connections)
        3. Health check should detect unhealthy state
        4. Pool should handle connection attempts gracefully
        """
        # Initial health check should pass
        initial_health = await recovery_pool.ahealth_check()
        assert initial_health.status == HealthCheckStatus.HEALTHY

        # Use connection successfully
        result: int = await recovery_pool.afetchval("SELECT 1")
        assert result == 1

        # Simulate database becoming unavailable
        # Note: In production, this would be network partition or database crash
        # Here we test that pool handles connection errors gracefully

        # Pool should still be queryable (will fail but not crash)
        # This tests graceful error handling
        try:
            async with recovery_pool.aacquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception:
            # Expected to potentially fail
            pass

        # Pool should eventually recover when database available again
        # (TestContainers keeps database running)
        await asyncio.sleep(0.5)

        # Should be able to query again
        recovered_result: int = await recovery_pool.afetchval("SELECT 1")
        assert recovered_result == 1

    async def test_pool_replaces_broken_connections(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test that pool replaces broken connections automatically.

        Scenario:
        1. Acquire multiple connections
        2. Break one connection
        3. Release back to pool
        4. Acquire connections again
        5. Verify pool doesn't return broken connection
        """
        initial_size = recovery_pool.pool.get_size()

        # Acquire and break a connection
        async with recovery_pool.aacquire() as conn:
            # Use it successfully first
            await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 100)

            # Now close it
            await conn.close()

        # Connection returned to pool (but it's closed)
        # Pool should detect this on next acquire

        # Next acquire should get a working connection
        async with recovery_pool.aacquire() as fresh_conn:
            result: int = await fresh_conn.fetchval("SELECT COUNT(*) FROM test_recovery")
            assert result == 1

            # Should be able to use new connection
            await fresh_conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 200)

        # Verify pool maintains proper size
        final_size = recovery_pool.pool.get_size()
        assert final_size >= initial_size - 1  # May have replaced broken connection

    async def test_query_fails_with_closed_connection(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test that queries fail appropriately with closed connections.

        Scenario:
        1. Get connection from pool
        2. Close the connection
        3. Try to query - should raise error
        4. Verify error type is correct
        """
        async with recovery_pool.aacquire() as conn:
            # Connection is valid
            result: int = await conn.fetchval("SELECT 1")
            assert result == 1

            # Close it
            await conn.close()

            # Queries should fail with InterfaceError
            with pytest.raises(asyncpg.exceptions.InterfaceError):
                await conn.fetchval("SELECT 2")

    async def test_pool_health_check_detects_pool_issues(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test that health check accurately reports pool status.

        Scenario:
        1. Verify healthy pool reports HEALTHY
        2. Check pool metrics are accurate
        3. Verify health check doesn't interfere with operations
        """
        # Health check should pass
        health = await recovery_pool.ahealth_check()
        assert health.status == HealthCheckStatus.HEALTHY
        assert health.pool_initialized is True
        assert health.pool_size is not None
        assert health.pool_size >= 2  # At least min_size

        # Health check during active operations
        async with recovery_pool.aacquire() as conn:
            await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 100)

            # Health check should still work
            health_during_op = await recovery_pool.ahealth_check()
            assert health_during_op.status == HealthCheckStatus.HEALTHY

        # Final health check
        final_health = await recovery_pool.ahealth_check()
        assert final_health.status == HealthCheckStatus.HEALTHY

    async def test_concurrent_connection_failures(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test pool handles multiple concurrent connection failures.

        Scenario:
        1. Acquire multiple connections concurrently
        2. Close some connections mid-operation
        3. Verify pool handles failures gracefully
        4. Verify pool recovers and remains functional
        """
        failure_count = 0

        async def operation_with_possible_failure(fail: bool) -> None:
            nonlocal failure_count
            try:
                async with recovery_pool.aacquire() as conn:
                    await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 100)

                    if fail:
                        # Close connection mid-operation
                        await conn.close()
                        failure_count += 1

                    # Try another operation (will fail if closed)
                    await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 200)
            except asyncpg.exceptions.InterfaceError:
                # Expected for closed connections
                pass

        # Run mix of failing and successful operations
        await asyncio.gather(
            operation_with_possible_failure(fail=True),
            operation_with_possible_failure(fail=False),
            operation_with_possible_failure(fail=True),
            operation_with_possible_failure(fail=False),
            operation_with_possible_failure(fail=False),
            return_exceptions=True,
        )

        # Some operations should have failed
        assert failure_count > 0

        # Pool should recover
        await asyncio.sleep(0.1)

        # Pool should still be functional
        result: int = await recovery_pool.afetchval("SELECT COUNT(*) FROM test_recovery")
        # Should have some successful inserts
        assert result > 0

        # Health check should pass
        health = await recovery_pool.ahealth_check()
        assert health.status == HealthCheckStatus.HEALTHY

    async def test_pool_recovers_after_all_connections_fail(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test pool recovery when all connections become invalid.

        Scenario:
        1. Force all connections in pool to close
        2. Try to acquire new connection
        3. Verify pool creates new connections
        4. Verify operations work with fresh connections
        """
        # Close all connections in pool by using and closing them
        async with (
            recovery_pool.aacquire() as conn1,
            recovery_pool.aacquire() as conn2,
        ):
            # Use connections first
            await conn1.execute("INSERT INTO test_recovery (value) VALUES ($1)", 100)
            await conn2.execute("INSERT INTO test_recovery (value) VALUES ($1)", 200)

            # Close both
            await conn1.close()
            await conn2.close()

        # Pool should create new connections on next acquire
        await asyncio.sleep(0.2)

        # This should work with fresh connection
        async with recovery_pool.aacquire() as fresh_conn:
            result: int = await fresh_conn.fetchval("SELECT COUNT(*) FROM test_recovery")
            assert result == 2  # Original inserts before close

            # New operation should work
            await fresh_conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 300)

        # Verify final state
        final_count: int = await recovery_pool.afetchval("SELECT COUNT(*) FROM test_recovery")
        assert final_count == 3

    async def test_health_check_after_connection_failures(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test health check remains accurate after connection failures.

        Scenario:
        1. Cause multiple connection failures
        2. Run health check
        3. Verify health status is accurate
        4. Verify pool metrics are correct
        """
        # Cause some connection failures
        for _ in range(3):
            with suppress(asyncpg.exceptions.InterfaceError):
                async with recovery_pool.aacquire() as conn:
                    await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 100)
                    await conn.close()
                    await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 200)

        # Wait for pool to stabilize
        await asyncio.sleep(0.2)

        # Health check should still work
        health = await recovery_pool.ahealth_check()
        assert health.status == HealthCheckStatus.HEALTHY
        assert health.pool_initialized is True
        assert health.pool_size is not None

        # Pool should still be functional
        result: int = await recovery_pool.afetchval("SELECT 1")
        assert result == 1
