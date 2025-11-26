"""Pool size dynamics and connection lifecycle integration tests.

Tests critical pool behavior:
- Dynamic scaling from min_size to max_size under load
- Connection reuse and recycling
- Pool warmup and initialization
- Connection lifecycle management
- Max connection limit enforcement
- Connection acquisition timeouts

These tests expose production bugs related to pool resource management,
connection lifecycle, and scaling behavior.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import SecretStr

from pixiu.database import AsyncConnectionPool, DatabaseConfig, DatabaseConnectionSettings, PoolSettings
from pixiu.database.models import HealthCheckStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.mark.integration
@pytest.mark.database
class TestPoolSizeDynamics:
    """Test pool size dynamics and connection lifecycle."""

    @pytest.fixture
    async def dynamic_pool(self, postgres_container: Any) -> AsyncIterator[AsyncConnectionPool]:
        """Create pool with dynamic size configuration.

        Pool configuration:
        - min_size: 2 (warm pool with minimum connections)
        - max_size: 10 (allow scaling under load)
        - timeout: 5.0 seconds
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
                max_size=10,
                timeout=5.0,
            ),
        )

        pool = AsyncConnectionPool(config)
        await pool.ainitialize()

        try:
            yield pool
        finally:
            await pool.aclose()

    async def test_pool_starts_with_min_size_connections(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool initializes with min_size connections.

        Scenario:
        1. Pool initialized
        2. Check pool size immediately
        3. Verify size >= min_size
        4. Verify pool is functional
        """
        # Pool should have at least min_size connections
        pool_size = dynamic_pool.pool.get_size()
        assert pool_size >= 2, f"Pool should have at least 2 connections, got {pool_size}"

        # Connections should be functional
        result: int = await dynamic_pool.afetchval("SELECT 1")
        assert result == 1

        # Health check should pass
        health = await dynamic_pool.ahealth_check()
        assert health.status == HealthCheckStatus.HEALTHY
        assert health.pool_size is not None
        assert health.pool_size >= 2

    async def test_pool_grows_under_concurrent_load(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool grows from min_size to max_size under load.

        Scenario:
        1. Check initial pool size
        2. Launch many concurrent queries (more than min_size)
        3. Verify pool size increases
        4. Verify all queries complete successfully
        """
        initial_size = dynamic_pool.pool.get_size()
        assert initial_size >= 2

        async def long_running_query() -> int:
            """Query that holds connection briefly"""
            async with dynamic_pool.aacquire() as conn:
                # Hold connection for a bit
                await asyncio.sleep(0.1)
                result: int = await conn.fetchval("SELECT 1")
                return result

        # Launch 8 concurrent queries (more than min_size=2)
        tasks = [asyncio.create_task(long_running_query()) for _ in range(8)]

        # Give pool time to scale up
        await asyncio.sleep(0.2)

        # Pool should have grown
        peak_size = dynamic_pool.pool.get_size()
        assert peak_size > initial_size, f"Pool should grow: {initial_size} -> {peak_size}"
        assert peak_size <= 10, f"Pool should not exceed max_size: {peak_size}"

        # All tasks should complete successfully
        results = await asyncio.gather(*tasks)
        assert all(r == 1 for r in results)

    async def test_pool_respects_max_size_limit(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool never exceeds max_size even under extreme load.

        Scenario:
        1. Launch more concurrent operations than max_size
        2. Continuously monitor pool size
        3. Verify size never exceeds max_size
        4. Verify operations queue correctly
        """
        max_size = dynamic_pool.pool.get_max_size()
        size_violations: list[int] = []

        async def monitored_operation() -> None:
            """Operation that checks pool size"""
            async with dynamic_pool.aacquire() as conn:
                # Check size while holding connection
                current_size = dynamic_pool.pool.get_size()
                if current_size > max_size:
                    size_violations.append(current_size)

                await conn.fetchval("SELECT 1")
                await asyncio.sleep(0.05)

        # Launch 15 operations (more than max_size=10)
        await asyncio.gather(*[monitored_operation() for _ in range(15)])

        # No size violations should occur
        assert len(size_violations) == 0, f"Pool exceeded max_size: {size_violations}"

        # Final pool size should be <= max_size
        final_size = dynamic_pool.pool.get_size()
        assert final_size <= max_size, f"Final size {final_size} exceeds max {max_size}"

    async def test_connection_reuse_across_operations(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test that connections are reused efficiently.

        Scenario:
        1. Perform sequential operations
        2. Track pool size changes
        3. Verify connections are reused (pool size stable)
        4. Verify no unnecessary connection creation
        """
        # Perform multiple sequential operations
        sizes: list[int] = []

        for _ in range(10):
            result: int = await dynamic_pool.afetchval("SELECT 1")
            assert result == 1
            sizes.append(dynamic_pool.pool.get_size())
            await asyncio.sleep(0.05)

        # Pool size should be relatively stable
        # (not creating new connection for each operation)
        size_changes = [abs(sizes[i] - sizes[i - 1]) for i in range(1, len(sizes))]
        avg_change = sum(size_changes) / len(size_changes) if size_changes else 0

        # Average change should be small (connections reused)
        assert avg_change < 1.0, f"Pool size too volatile: {sizes}"

    async def test_pool_handles_acquisition_timeout(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool timeout when all connections busy.

        Scenario:
        1. Exhaust all connections (hold max_size connections)
        2. Try to acquire one more (should timeout)
        3. Verify timeout exception raised
        4. Verify pool recovers after connections released
        """
        release_event = asyncio.Event()

        async def hold_connection() -> None:
            """Hold connection until signaled"""
            async with dynamic_pool.aacquire():
                await release_event.wait()

        # Hold all max_size connections
        holders = [asyncio.create_task(hold_connection()) for _ in range(10)]
        await asyncio.sleep(0.3)

        # Next acquire should timeout (pool.timeout=5.0s)
        # Use shorter timeout for test speed
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                dynamic_pool.aacquire().__aenter__(),
                timeout=0.5,
            )

        # Release connections
        release_event.set()
        await asyncio.gather(*holders)

        # Pool should be usable again
        result: int = await dynamic_pool.afetchval("SELECT 1")
        assert result == 1

    async def test_pool_connection_lifecycle_tracking(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool accurately tracks connection lifecycle.

        Scenario:
        1. Monitor pool size before operations
        2. Perform various operations
        3. Verify pool size changes correctly
        4. Verify pool metrics are accurate
        """
        initial_size = dynamic_pool.pool.get_size()

        # Single operation shouldn't change pool size significantly
        await dynamic_pool.aexecute("SELECT 1")
        size_after_one = dynamic_pool.pool.get_size()
        assert abs(size_after_one - initial_size) <= 1

        # Multiple concurrent operations may grow pool
        async def operation() -> None:
            await dynamic_pool.aexecute("SELECT 1")

        await asyncio.gather(*[operation() for _ in range(5)])

        size_after_concurrent = dynamic_pool.pool.get_size()
        assert size_after_concurrent <= 10  # max_size

        # Pool should eventually stabilize
        await asyncio.sleep(0.5)
        final_size = dynamic_pool.pool.get_size()
        assert final_size <= 10

    async def test_pool_warmup_behavior(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool warmup creates initial connections.

        Scenario:
        1. Pool just initialized (already happened in fixture)
        2. Verify min_size connections exist
        3. Verify connections are functional
        4. Verify no unnecessary connections created
        """
        # Pool should have min_size connections ready
        pool_size = dynamic_pool.pool.get_size()
        max_size = dynamic_pool.pool.get_max_size()

        assert pool_size >= 2, "Pool should be warmed up with min_size connections"
        assert pool_size <= max_size, "Pool should not exceed max_size during warmup"

        # All connections should be functional
        for _ in range(pool_size):
            result: int = await dynamic_pool.afetchval("SELECT 1")
            assert result == 1

    async def test_concurrent_scaling_stress(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Stress test with rapid concurrent acquire/release cycles.

        Scenario:
        1. Launch many rapid concurrent operations
        2. Monitor pool size stays within bounds
        3. Verify no operations fail
        4. Verify pool remains healthy
        """
        successful_operations = 0
        size_violations: list[int] = []
        max_size = dynamic_pool.pool.get_max_size()

        async def rapid_operation() -> None:
            nonlocal successful_operations
            async with dynamic_pool.aacquire() as conn:
                # Check pool size
                current_size = dynamic_pool.pool.get_size()
                if current_size > max_size:
                    size_violations.append(current_size)

                await conn.fetchval("SELECT 1")
                successful_operations += 1
                await asyncio.sleep(0.01)

        # Launch 50 rapid operations
        await asyncio.gather(*[rapid_operation() for _ in range(50)])

        # All operations should succeed
        assert successful_operations == 50

        # No size violations
        assert len(size_violations) == 0, f"Size violations: {size_violations}"

        # Pool should be healthy
        health = await dynamic_pool.ahealth_check()
        assert health.status == HealthCheckStatus.HEALTHY

    async def test_pool_size_after_exception_in_context_manager(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool size remains correct after exceptions.

        Scenario:
        1. Check initial pool size
        2. Raise exception inside context manager
        3. Verify pool size unchanged (connection returned)
        4. Verify pool remains functional
        """
        initial_size = dynamic_pool.pool.get_size()

        class TestError(Exception):
            pass

        # Exception should still return connection to pool
        with pytest.raises(TestError):
            async with dynamic_pool.aacquire() as conn:
                await conn.fetchval("SELECT 1")
                raise TestError("Test exception")

        # Wait for connection return
        await asyncio.sleep(0.1)

        # Pool size should be unchanged
        final_size = dynamic_pool.pool.get_size()
        assert final_size == initial_size, f"Pool size changed: {initial_size} -> {final_size}"

        # Pool should still work
        result: int = await dynamic_pool.afetchval("SELECT 1")
        assert result == 1

    async def test_pool_metrics_accuracy_under_load(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test that pool metrics remain accurate under concurrent load.

        Scenario:
        1. Launch concurrent operations
        2. Continuously check pool metrics
        3. Verify metrics are consistent
        4. Verify health check reports accurate data
        """

        async def operation_with_metrics_check() -> None:
            """Operation that validates metrics"""
            async with dynamic_pool.aacquire() as conn:
                # Check metrics while holding connection
                size = dynamic_pool.pool.get_size()
                max_size = dynamic_pool.pool.get_max_size()

                assert size <= max_size, f"Size {size} exceeds max {max_size}"

                await conn.fetchval("SELECT 1")
                await asyncio.sleep(0.05)

        # Run operations concurrently
        await asyncio.gather(*[operation_with_metrics_check() for _ in range(20)])

        # Final health check
        health = await dynamic_pool.ahealth_check()
        assert health.status == HealthCheckStatus.HEALTHY
        assert health.pool_size is not None
        assert health.pool_max_size is not None
        assert health.pool_size <= health.pool_max_size
