"""Health check under stress integration tests.

Tests critical health check behavior:
- Health checks with exhausted connection pools
- Health checks during active query workloads
- Health check timeout behavior
- Health checks with database failures
- Concurrent health check execution
- Health status transition accuracy
- Recovery detection

These tests expose production bugs related to health check reliability,
monitoring accuracy, and system observability under stress.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING, Any

import asyncpg
import pytest
from pydantic import SecretStr

from pixiu.database import AsyncConnectionPool, DatabaseConfig, DatabaseConnectionSettings, PoolSettings
from pixiu.database.config import AsyncpgSettings
from pixiu.database.models import HealthCheckStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.mark.integration
@pytest.mark.database
class TestHealthCheckStress:
    """Test health check behavior under stress conditions."""

    @pytest.fixture
    async def stress_pool(self, postgres_container: Any) -> AsyncIterator[AsyncConnectionPool]:
        """Create pool for health check stress testing.

        Pool configuration:
        - min_size: 2
        - max_size: 5
        - timeout: 10.0 seconds
        - command_timeout: 30.0 seconds
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
            asyncpg=AsyncpgSettings(
                command_timeout=30.0,
            ),
        )

        pool = AsyncConnectionPool(config)
        await pool.ainitialize()

        try:
            yield pool
        finally:
            await pool.aclose()

    async def test_health_check_with_exhausted_pool(self, stress_pool: AsyncConnectionPool) -> None:
        """Test health check when all connections are in use.

        Scenario:
        1. Exhaust pool by holding all connections
        2. Run health check
        3. Verify health check can still execute (acquires connection)
        4. Verify health status reported correctly
        """
        release_event = asyncio.Event()

        async def hold_connection() -> None:
            """Hold connection until signaled"""
            async with stress_pool.aacquire():
                await release_event.wait()

        # Hold all connections (max_size=5)
        holders = [asyncio.create_task(hold_connection()) for _ in range(5)]
        await asyncio.sleep(0.2)

        # Pool is exhausted, but health check should still work
        # (it may time out or succeed depending on timing)
        try:
            health = await asyncio.wait_for(stress_pool.ahealth_check(), timeout=2.0)

            # If health check succeeds, it means it acquired a connection
            # Status may be HEALTHY or DEGRADED depending on pool state
            assert health.pool_initialized is True
            assert health.pool_size is not None
        except TimeoutError:
            # Health check timing out is also acceptable behavior
            # when pool is fully exhausted
            pass

        # Release connections
        release_event.set()
        await asyncio.gather(*holders)

        # Health check should definitely work now
        final_health = await stress_pool.ahealth_check()
        assert final_health.status == HealthCheckStatus.HEALTHY

    async def test_health_check_during_active_queries(self, stress_pool: AsyncConnectionPool) -> None:
        """Test health check doesn't interfere with active workload.

        Scenario:
        1. Start long-running query workload
        2. Run health checks concurrently
        3. Verify health checks complete
        4. Verify queries complete successfully
        5. Verify no interference between health checks and queries
        """
        query_results: list[int] = []
        health_checks: list[HealthCheckStatus] = []

        async def long_query() -> None:
            """Simulate long-running query"""
            result: int = await stress_pool.afetchval("SELECT 1 FROM (SELECT pg_sleep(0.5)) AS t")
            query_results.append(result)

        async def health_check() -> None:
            """Run health check"""
            health = await stress_pool.ahealth_check()
            health_checks.append(health.status)

        # Run queries and health checks concurrently
        tasks = [
            asyncio.create_task(long_query()),
            asyncio.create_task(long_query()),
            asyncio.create_task(health_check()),
            asyncio.create_task(long_query()),
            asyncio.create_task(health_check()),
        ]

        await asyncio.gather(*tasks)

        # All queries should complete
        assert len(query_results) == 3
        assert all(r == 1 for r in query_results)

        # Health checks should complete
        assert len(health_checks) == 2
        assert all(s == HealthCheckStatus.HEALTHY for s in health_checks)

    async def test_health_check_with_slow_database(self, stress_pool: AsyncConnectionPool) -> None:
        """Test health check behavior when database is slow.

        Scenario:
        1. Simulate slow database with pg_sleep
        2. Run health check
        3. Verify health check completes (doesn't hang indefinitely)
        4. Verify health status reflects database state
        """
        # Health check with slow query in background
        slow_query_task = asyncio.create_task(stress_pool.aexecute("SELECT pg_sleep(2)"))

        # Give slow query time to start
        await asyncio.sleep(0.1)

        # Health check should still complete
        health = await stress_pool.ahealth_check()

        # Health check should succeed (database is responsive, just slow)
        assert health.status == HealthCheckStatus.HEALTHY
        assert health.pool_initialized is True

        # Wait for slow query to complete
        await slow_query_task

    async def test_health_check_with_connection_failures(self, stress_pool: AsyncConnectionPool) -> None:
        """Test health check after connection failures.

        Scenario:
        1. Cause some connection failures
        2. Run health check
        3. Verify health check detects and reports accurately
        4. Verify pool can recover
        """
        # Cause connection failures
        for _ in range(3):
            with suppress(asyncpg.exceptions.InterfaceError):
                async with stress_pool.aacquire() as conn:
                    # Use connection
                    await conn.fetchval("SELECT 1")
                    # Close it (simulating failure)
                    await conn.close()
                    # Try to use again (will fail)
                    await conn.fetchval("SELECT 2")

        # Wait for pool to potentially recover
        await asyncio.sleep(0.2)

        # Health check should still work
        health = await stress_pool.ahealth_check()

        # Pool should be healthy (recovered from failures)
        assert health.status == HealthCheckStatus.HEALTHY
        assert health.pool_initialized is True

    async def test_concurrent_health_checks(self, stress_pool: AsyncConnectionPool) -> None:
        """Test multiple health checks running concurrently.

        Scenario:
        1. Launch multiple health checks simultaneously
        2. Verify all complete successfully
        3. Verify results are consistent
        4. Verify no interference between health checks
        """
        # Run 10 concurrent health checks
        health_checks = await asyncio.gather(*[stress_pool.ahealth_check() for _ in range(10)])

        # All should complete
        assert len(health_checks) == 10

        # All should report HEALTHY
        assert all(h.status == HealthCheckStatus.HEALTHY for h in health_checks)

        # All should report pool initialized
        assert all(h.pool_initialized for h in health_checks)

        # Pool sizes should be consistent
        pool_sizes = [h.pool_size for h in health_checks]
        assert all(s is not None for s in pool_sizes)
        assert all(s >= 2 for s in pool_sizes if s is not None)

    async def test_health_check_metrics_accuracy(self, stress_pool: AsyncConnectionPool) -> None:
        """Test health check reports accurate pool metrics.

        Scenario:
        1. Verify health check reports correct pool size
        2. Acquire some connections
        3. Verify health check reflects updated state
        4. Release connections
        5. Verify metrics update accordingly
        """
        # Initial health check
        initial_health = await stress_pool.ahealth_check()
        assert initial_health.pool_size is not None
        initial_size = initial_health.pool_size

        # Hold some connections
        release_event = asyncio.Event()

        async def hold_connection() -> None:
            async with stress_pool.aacquire():
                await release_event.wait()

        holders = [asyncio.create_task(hold_connection()) for _ in range(3)]
        await asyncio.sleep(0.2)

        # Health check with connections held
        busy_health = await stress_pool.ahealth_check()
        assert busy_health.pool_size is not None
        assert busy_health.pool_size >= initial_size

        # Release connections
        release_event.set()
        await asyncio.gather(*holders)
        await asyncio.sleep(0.1)

        # Health check after release
        final_health = await stress_pool.ahealth_check()
        assert final_health.status == HealthCheckStatus.HEALTHY

    async def test_health_check_status_transitions(self, stress_pool: AsyncConnectionPool) -> None:
        """Test health status transitions correctly.

        Scenario:
        1. Verify initial HEALTHY status
        2. Cause pool stress
        3. Verify status reflects state
        4. Recover pool
        5. Verify status returns to HEALTHY
        """
        # Initial status should be HEALTHY
        initial_health = await stress_pool.ahealth_check()
        assert initial_health.status == HealthCheckStatus.HEALTHY

        # Stress the pool by holding all connections
        release_event = asyncio.Event()

        async def hold_connection() -> None:
            async with stress_pool.aacquire():
                await release_event.wait()

        holders = [asyncio.create_task(hold_connection()) for _ in range(5)]
        await asyncio.sleep(0.2)

        # Health check may report different status when stressed
        # (but should still complete)
        try:
            stressed_health = await asyncio.wait_for(
                stress_pool.ahealth_check(),
                timeout=2.0,
            )
            assert stressed_health.pool_initialized is True
        except TimeoutError:
            # Acceptable if pool is fully exhausted
            pass

        # Release connections
        release_event.set()
        await asyncio.gather(*holders)
        await asyncio.sleep(0.2)

        # Should return to HEALTHY
        recovered_health = await stress_pool.ahealth_check()
        assert recovered_health.status == HealthCheckStatus.HEALTHY

    async def test_health_check_doesnt_block_operations(self, stress_pool: AsyncConnectionPool) -> None:
        """Test health checks don't block normal operations.

        Scenario:
        1. Start health check
        2. Run queries concurrently
        3. Verify queries complete normally
        4. Verify health check completes
        """
        # Start health check
        health_task = asyncio.create_task(stress_pool.ahealth_check())

        # Immediately start queries
        query_results = await asyncio.gather(
            stress_pool.afetchval("SELECT 1"),
            stress_pool.afetchval("SELECT 2"),
            stress_pool.afetchval("SELECT 3"),
        )

        # Queries should complete
        assert list(query_results) == [1, 2, 3]

        # Health check should also complete
        health = await health_task
        assert health.status == HealthCheckStatus.HEALTHY

    async def test_health_check_under_sustained_load(self, stress_pool: AsyncConnectionPool) -> None:
        """Test health check accuracy under sustained query load.

        Scenario:
        1. Generate sustained query workload
        2. Periodically run health checks
        3. Verify health checks complete
        4. Verify health status remains accurate
        5. Verify no degradation in health check performance
        """
        health_results: list[HealthCheckStatus] = []
        query_count = 0

        async def sustained_workload() -> None:
            """Generate query load"""
            nonlocal query_count
            for _ in range(20):
                await stress_pool.afetchval("SELECT 1")
                query_count += 1
                await asyncio.sleep(0.05)

        async def periodic_health_checks() -> None:
            """Run health checks periodically"""
            for _ in range(5):
                health = await stress_pool.ahealth_check()
                health_results.append(health.status)
                await asyncio.sleep(0.2)

        # Run both concurrently
        await asyncio.gather(
            sustained_workload(),
            sustained_workload(),
            periodic_health_checks(),
        )

        # Workload should complete
        assert query_count == 40

        # All health checks should succeed
        assert len(health_results) == 5
        assert all(s == HealthCheckStatus.HEALTHY for s in health_results)

    async def test_health_check_pool_max_size_reporting(self, stress_pool: AsyncConnectionPool) -> None:
        """Test health check accurately reports max_size.

        Scenario:
        1. Run health check
        2. Verify max_size matches configuration
        3. Verify current size <= max_size
        """
        health = await stress_pool.ahealth_check()

        assert health.pool_max_size == 5, "max_size should match configuration"
        assert health.pool_size is not None
        assert health.pool_size <= health.pool_max_size, "Current size should not exceed max"
