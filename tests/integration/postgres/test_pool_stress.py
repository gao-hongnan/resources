"""Connection pool stress, exhaustion, and recovery integration tests.

Tests critical pool behavior under stress conditions:
- Pool blocking when all connections acquired
- Dynamic scaling from min_size to max_size under load
- Connection failure recovery
- Pool statistics accuracy under concurrent load
- Connection lifecycle management

These tests expose production bugs related to connection pool deadlocks,
resource leaks, and scaling behavior.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING

import asyncpg
import pytest

from leitmotif.infrastructure.postgres.enums import HealthStatus

if TYPE_CHECKING:
    from leitmotif.infrastructure.postgres import AsyncConnectionPool


@pytest.mark.asyncio
@pytest.mark.integration
class TestPoolExhaustion:
    """Test connection pool exhaustion and recovery scenarios."""

    async def test_pool_blocks_when_all_connections_acquired(self, small_pool: AsyncConnectionPool) -> None:
        """Test that pool blocks when all connections are held.

        Scenario:
        1. Pool max_size=3
        2. Acquire all 3 connections and hold them
        3. Attempt 4th acquire should block (not fail immediately)
        4. Verify blocking using asyncio.wait_for with timeout
        """
        release_event = asyncio.Event()
        connections_acquired = 0

        async def hold_connection() -> None:
            """Acquire connection and hold until event set."""
            nonlocal connections_acquired
            async with small_pool.aacquire():
                connections_acquired += 1
                await release_event.wait()

        # Start 3 tasks to hold all connections
        holders = [asyncio.create_task(hold_connection()) for _ in range(3)]

        # Wait for all 3 connections to be acquired
        await asyncio.sleep(0.2)
        assert connections_acquired == 3, "All 3 connections should be acquired"

        # 4th acquire should block (timeout after 0.5 seconds)
        async def try_acquire() -> None:
            async with small_pool.aacquire():
                pass

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(try_acquire(), timeout=0.5)

        # Cleanup: release all connections
        release_event.set()
        await asyncio.gather(*holders)

    async def test_pool_recovers_when_connections_released(self, small_pool: AsyncConnectionPool) -> None:
        """Test that pool immediately recovers when connection is released.

        Scenario:
        1. Exhaust pool (all 3 connections held)
        2. Release one connection
        3. Next acquire should succeed immediately
        """
        release_event = asyncio.Event()
        single_release = asyncio.Event()

        async def hold_connection(wait_for_single: bool = False) -> None:
            async with small_pool.aacquire():
                if wait_for_single:
                    await single_release.wait()
                else:
                    await release_event.wait()

        # Hold 2 connections indefinitely, 1 connection temporarily
        holder1 = asyncio.create_task(hold_connection())
        holder2 = asyncio.create_task(hold_connection())
        holder3 = asyncio.create_task(hold_connection(wait_for_single=True))

        await asyncio.sleep(0.2)

        # Pool exhausted - verify by attempting acquire with short timeout
        async def try_acquire() -> None:
            async with small_pool.aacquire():
                pass

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(try_acquire(), timeout=0.3)

        # Release one connection
        single_release.set()
        await asyncio.sleep(0.1)

        # Now acquire should succeed immediately (within 0.5s)
        async with asyncio.timeout(0.5):
            async with small_pool.aacquire() as conn:
                result = await conn.fetchval("SELECT 1")
                assert result == 1

        # Cleanup
        release_event.set()
        await asyncio.gather(holder1, holder2, holder3)

    async def test_connection_always_returned_on_exception(self, small_pool: AsyncConnectionPool) -> None:
        """Test that connection is returned to pool even when exception occurs.

        Scenario:
        1. Acquire connection
        2. Raise exception inside context manager
        3. Verify pool size restored (connection returned)
        4. Verify connection is healthy and reusable
        """
        initial_size = small_pool.pool_size

        class IntentionalTestError(Exception):
            """Exception raised intentionally during testing."""

        # Acquire and raise exception
        with pytest.raises(IntentionalTestError):
            async with small_pool.aacquire() as conn:
                await conn.fetchval("SELECT 1")
                raise IntentionalTestError

        # Pool size should be restored
        await asyncio.sleep(0.1)
        final_size = small_pool.pool_size
        assert final_size == initial_size, f"Pool size should be restored: {initial_size} -> {final_size}"

        # Connection should be reusable
        async with small_pool.aacquire() as conn:
            result = await conn.fetchval("SELECT 42")
            assert result == 42

    async def test_pool_statistics_accurate_under_concurrent_load(self, small_pool: AsyncConnectionPool) -> None:
        """Test that pool statistics remain accurate under concurrent acquire/release cycles.

        Scenario:
        1. Launch concurrent acquire/release operations
        2. Continuously verify pool size never exceeds max_size
        3. Verify pool remains healthy
        """
        max_size = small_pool.pool_max_size
        violations: list[int] = []

        async def acquire_release_cycle() -> None:
            """Perform acquire/release cycle."""
            async with small_pool.aacquire() as conn:
                # Check pool size doesn't exceed max
                current_size = small_pool.pool_size
                if current_size > max_size:
                    violations.append(current_size)

                await conn.fetchval("SELECT 1")
                await asyncio.sleep(0.05)

        # Run 20 concurrent cycles
        await asyncio.gather(*[acquire_release_cycle() for _ in range(20)])

        # No violations should occur
        assert len(violations) == 0, f"Pool size exceeded max_size: {violations}"

        # Pool should still be healthy
        health = await small_pool.ahealth_check()
        assert health.status == HealthStatus.HEALTHY
        assert health.pool_size is not None
        assert health.pool_size <= max_size

    async def test_no_connection_leak_with_context_manager(self, small_pool: AsyncConnectionPool) -> None:
        """Test that context manager guarantees connection is always returned.

        Scenario:
        1. Acquire connections multiple times
        2. Verify pool size unchanged after each acquisition
        3. Test both normal exit and exception exit
        """
        initial_size = small_pool.pool_size

        # Normal exit - 10 iterations
        for _ in range(10):
            async with small_pool.aacquire() as conn:
                await conn.fetchval("SELECT 1")

        await asyncio.sleep(0.1)
        assert small_pool.pool_size == initial_size, "Pool size should be unchanged after normal exits"

        # Exception exit - 10 iterations
        class LeakTestError(Exception):
            """Exception for testing leak prevention."""

        async def trigger_exception_in_context() -> None:
            """Trigger exception during connection use for leak testing."""
            async with small_pool.aacquire() as conn:
                await conn.fetchval("SELECT 1")
                raise LeakTestError

        for _ in range(10):
            with suppress(LeakTestError):
                await trigger_exception_in_context()

        await asyncio.sleep(0.1)
        assert small_pool.pool_size == initial_size, "Pool size should be unchanged even after exception exits"

    async def test_concurrent_acquire_release_stress(self, small_pool: AsyncConnectionPool) -> None:
        """Stress test with many concurrent acquire/release operations.

        Scenario:
        1. Launch 50 concurrent tasks
        2. Each task performs multiple acquire/release cycles
        3. Verify no deadlocks, all tasks complete
        4. Verify pool remains healthy
        """
        task_count = 50
        cycles_per_task = 3
        completed_tasks = 0

        async def stress_worker() -> None:
            nonlocal completed_tasks
            for _ in range(cycles_per_task):
                async with small_pool.aacquire() as conn:
                    await conn.fetchval("SELECT 1")
                    await asyncio.sleep(0.01)
            completed_tasks += 1

        # Run all tasks concurrently
        await asyncio.gather(*[stress_worker() for _ in range(task_count)])

        # All tasks should complete
        assert completed_tasks == task_count, f"Expected {task_count} tasks to complete, got {completed_tasks}"

        # Pool should still be healthy
        health = await small_pool.ahealth_check()
        assert health.status == HealthStatus.HEALTHY


@pytest.mark.asyncio
@pytest.mark.integration
class TestPoolSizeDynamics:
    """Test pool size dynamics and connection lifecycle."""

    async def test_pool_starts_with_min_size_connections(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool initializes with min_size connections.

        Scenario:
        1. Pool initialized
        2. Check pool size immediately
        3. Verify size >= min_size
        4. Verify pool is functional
        """
        pool_size = dynamic_pool.pool_size
        assert pool_size >= 2, f"Pool should have at least 2 connections, got {pool_size}"

        # Connections should be functional
        result: int = await dynamic_pool.afetchval("SELECT 1")
        assert result == 1

        # Health check should pass
        health = await dynamic_pool.ahealth_check()
        assert health.status == HealthStatus.HEALTHY
        assert health.pool_size is not None
        assert health.pool_size >= 2

    async def test_pool_grows_under_concurrent_load(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool grows from min_size to accommodate load.

        Scenario:
        1. Check initial pool size
        2. Launch concurrent queries (more than min_size)
        3. Verify pool size increases
        4. Verify all queries complete
        """
        initial_size = dynamic_pool.pool_size
        assert initial_size >= 2

        async def long_running_query() -> int:
            """Query that holds connection briefly."""
            async with dynamic_pool.aacquire() as conn:
                await asyncio.sleep(0.1)
                result: int = await conn.fetchval("SELECT 1")
                return result

        # Launch 8 concurrent queries
        tasks = [asyncio.create_task(long_running_query()) for _ in range(8)]

        # Give pool time to scale up
        await asyncio.sleep(0.2)

        # Pool should have grown
        peak_size = dynamic_pool.pool_size
        assert peak_size > initial_size, f"Pool should grow: {initial_size} -> {peak_size}"
        assert peak_size <= 10, f"Pool should not exceed max_size: {peak_size}"

        # All tasks should complete
        results = await asyncio.gather(*tasks)
        assert all(r == 1 for r in results)

    async def test_pool_respects_max_size_limit(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool never exceeds max_size even under extreme load.

        Scenario:
        1. Launch more concurrent operations than max_size
        2. Continuously monitor pool size
        3. Verify size never exceeds max_size
        """
        max_size = dynamic_pool.pool_max_size
        size_violations: list[int] = []

        async def monitored_operation() -> None:
            """Operation that checks pool size."""
            async with dynamic_pool.aacquire() as conn:
                current_size = dynamic_pool.pool_size
                if current_size > max_size:
                    size_violations.append(current_size)

                await conn.fetchval("SELECT 1")
                await asyncio.sleep(0.05)

        # Launch 15 operations (more than max_size=10)
        await asyncio.gather(*[monitored_operation() for _ in range(15)])

        # No size violations should occur
        assert len(size_violations) == 0, f"Pool exceeded max_size: {size_violations}"

        # Final pool size should be <= max_size
        final_size = dynamic_pool.pool_size
        assert final_size <= max_size, f"Final size {final_size} exceeds max {max_size}"

    async def test_connection_reuse_across_operations(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test that connections are reused efficiently.

        Scenario:
        1. Perform sequential operations
        2. Track pool size changes
        3. Verify connections are reused (pool size stable)
        """
        sizes: list[int] = []

        for _ in range(10):
            result: int = await dynamic_pool.afetchval("SELECT 1")
            assert result == 1
            sizes.append(dynamic_pool.pool_size)
            await asyncio.sleep(0.05)

        # Pool size should be relatively stable
        size_changes = [abs(sizes[i] - sizes[i - 1]) for i in range(1, len(sizes))]
        avg_change = sum(size_changes) / len(size_changes) if size_changes else 0

        # Average change should be small (connections reused)
        assert avg_change < 1.0, f"Pool size too volatile: {sizes}"

    async def test_pool_handles_acquisition_timeout(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool timeout when all connections busy.

        Scenario:
        1. Exhaust all connections (hold max_size connections)
        2. Try to acquire one more (should timeout)
        3. Verify pool recovers after release
        """
        release_event = asyncio.Event()

        async def hold_connection() -> None:
            """Hold connection until signaled."""
            async with dynamic_pool.aacquire():
                await release_event.wait()

        # Hold all max_size connections
        holders = [asyncio.create_task(hold_connection()) for _ in range(10)]
        await asyncio.sleep(0.3)

        # Next acquire should timeout
        async def acquire_connection() -> None:
            async with dynamic_pool.aacquire():
                pass

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(acquire_connection(), timeout=0.5)

        # Release connections
        release_event.set()
        await asyncio.gather(*holders)

        # Pool should be usable again
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
        max_size = dynamic_pool.pool_max_size

        async def rapid_operation() -> None:
            nonlocal successful_operations
            async with dynamic_pool.aacquire() as conn:
                current_size = dynamic_pool.pool_size
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
        assert health.status == HealthStatus.HEALTHY

    async def test_pool_size_after_exception_in_context_manager(self, dynamic_pool: AsyncConnectionPool) -> None:
        """Test pool size remains correct after exceptions.

        Scenario:
        1. Check initial pool size
        2. Raise exception inside context manager
        3. Verify pool size unchanged
        4. Verify pool remains functional
        """
        initial_size = dynamic_pool.pool_size

        class ContextManagerTestError(Exception):
            """Exception raised to test context manager behavior."""

        with pytest.raises(ContextManagerTestError):
            async with dynamic_pool.aacquire() as conn:
                await conn.fetchval("SELECT 1")
                raise ContextManagerTestError

        await asyncio.sleep(0.1)

        # Pool size should be unchanged
        final_size = dynamic_pool.pool_size
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
            """Operation that validates metrics."""
            async with dynamic_pool.aacquire() as conn:
                size = dynamic_pool.pool_size
                max_size = dynamic_pool.pool_max_size

                assert size <= max_size, f"Size {size} exceeds max {max_size}"

                await conn.fetchval("SELECT 1")
                await asyncio.sleep(0.05)

        # Run operations concurrently
        await asyncio.gather(*[operation_with_metrics_check() for _ in range(20)])

        # Final health check
        health = await dynamic_pool.ahealth_check()
        assert health.status == HealthStatus.HEALTHY
        assert health.pool_size is not None
        assert health.pool_max_size is not None
        assert health.pool_size <= health.pool_max_size


@pytest.mark.asyncio
@pytest.mark.integration
class TestConnectionFailureRecovery:
    """Test connection failure and recovery scenarios."""

    async def test_pool_handles_connection_closed_during_query(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test that pool handles connection closing mid-query.

        Scenario:
        1. Acquire connection and start using it
        2. Close connection externally (simulate network failure)
        3. Verify appropriate exception raised
        4. Verify pool remains healthy with fresh connections
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
        assert health.status == HealthStatus.HEALTHY

    async def test_pool_replaces_broken_connections(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test that pool replaces broken connections automatically.

        Scenario:
        1. Acquire and break a connection
        2. Release back to pool
        3. Acquire again
        4. Verify pool doesn't return broken connection
        """
        initial_size = recovery_pool.pool_size

        # Acquire and break a connection
        async with recovery_pool.aacquire() as conn:
            await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 100)
            await conn.close()

        # Next acquire should get a working connection
        async with recovery_pool.aacquire() as fresh_conn:
            result: int = await fresh_conn.fetchval("SELECT COUNT(*) FROM test_recovery")
            assert result == 1

            await fresh_conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 200)

        # Verify pool maintains proper size
        final_size = recovery_pool.pool_size
        assert final_size >= initial_size - 1

    async def test_query_fails_with_closed_connection(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test that queries fail appropriately with closed connections.

        Scenario:
        1. Get connection from pool
        2. Close the connection
        3. Try to query - should raise error
        4. Verify error type is correct
        """
        async with recovery_pool.aacquire() as conn:
            result: int = await conn.fetchval("SELECT 1")
            assert result == 1

            await conn.close()

            with pytest.raises(asyncpg.exceptions.InterfaceError):
                await conn.fetchval("SELECT 2")

    async def test_pool_health_check_detects_pool_issues(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test that health check accurately reports pool status.

        Scenario:
        1. Verify healthy pool reports HEALTHY
        2. Check pool metrics are accurate
        3. Verify health check doesn't interfere with operations
        """
        health = await recovery_pool.ahealth_check()
        assert health.status == HealthStatus.HEALTHY
        assert health.pool_size is not None
        assert health.pool_size >= 2

        # Health check during active operations
        async with recovery_pool.aacquire() as conn:
            await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 100)

            health_during_op = await recovery_pool.ahealth_check()
            assert health_during_op.status == HealthStatus.HEALTHY

        # Final health check
        final_health = await recovery_pool.ahealth_check()
        assert final_health.status == HealthStatus.HEALTHY

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
                        await conn.close()
                        failure_count += 1

                    await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 200)
            except asyncpg.exceptions.InterfaceError:
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

        assert failure_count > 0

        # Pool should recover
        await asyncio.sleep(0.1)

        result: int = await recovery_pool.afetchval("SELECT COUNT(*) FROM test_recovery")
        assert result > 0

        health = await recovery_pool.ahealth_check()
        assert health.status == HealthStatus.HEALTHY

    async def test_pool_recovers_after_all_connections_fail(self, recovery_pool: AsyncConnectionPool) -> None:
        """Test pool recovery when all connections become invalid.

        Scenario:
        1. Force all connections to close
        2. Try to acquire new connection
        3. Verify pool creates new connections
        4. Verify operations work with fresh connections
        """
        async with (
            recovery_pool.aacquire() as conn1,
            recovery_pool.aacquire() as conn2,
        ):
            await conn1.execute("INSERT INTO test_recovery (value) VALUES ($1)", 100)
            await conn2.execute("INSERT INTO test_recovery (value) VALUES ($1)", 200)

            await conn1.close()
            await conn2.close()

        await asyncio.sleep(0.2)

        async with recovery_pool.aacquire() as fresh_conn:
            result: int = await fresh_conn.fetchval("SELECT COUNT(*) FROM test_recovery")
            assert result == 2

            await fresh_conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 300)

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
        for _ in range(3):
            with suppress(asyncpg.exceptions.InterfaceError):
                async with recovery_pool.aacquire() as conn:
                    await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 100)
                    await conn.close()
                    await conn.execute("INSERT INTO test_recovery (value) VALUES ($1)", 200)

        await asyncio.sleep(0.2)

        health = await recovery_pool.ahealth_check()
        assert health.status == HealthStatus.HEALTHY
        assert health.pool_size is not None

        result: int = await recovery_pool.afetchval("SELECT 1")
        assert result == 1
