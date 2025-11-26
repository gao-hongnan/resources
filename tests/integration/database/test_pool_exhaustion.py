# """Connection pool exhaustion and recovery integration tests.

# Tests critical pool behavior under resource exhaustion:
# - Pool blocking when all connections acquired
# - Timeout behavior when pool fully utilized
# - Proper connection recovery when connections released
# - Connection leak prevention via context managers
# - Pool statistics accuracy under concurrent load

# These tests expose production bugs related to connection pool deadlocks,
# hangs, and resource leaks.
# """

# from __future__ import annotations

# import asyncio
# from typing import TYPE_CHECKING, Any

# import pytest
# from pydantic import SecretStr

# from pixiu.database import AsyncConnectionPool, DatabaseConfig, DatabaseConnectionSettings, PoolSettings
# from pixiu.database.models import HealthCheckStatus

# if TYPE_CHECKING:
#     from collections.abc import AsyncIterator


# @pytest.mark.integration
# @pytest.mark.database
# class TestPoolExhaustion:
#     """Test connection pool exhaustion and recovery scenarios."""

#     @pytest.fixture
#     async def small_pool(self, postgres_container: Any) -> AsyncIterator[AsyncConnectionPool]:
#         """Create pool with small max_size for exhaustion testing.

#         Pool configuration:
#         - min_size: 1 (minimal connections)
#         - max_size: 3 (small pool to easily exhaust)
#         - timeout: 2.0 seconds (reasonable for tests)
#         """
#         exposed_port = postgres_container.get_exposed_port(5432)
#         host = postgres_container.get_container_host_ip()

#         config = DatabaseConfig(
#             connection=DatabaseConnectionSettings(
#                 host=host,
#                 port=exposed_port,
#                 database="test_db",
#                 user="test_user",
#                 password=SecretStr("test_password"),
#                 sslmode="disable",
#             ),
#             pool=PoolSettings(
#                 min_size=1,
#                 max_size=3,
#                 timeout=2.0,
#             ),
#         )

#         pool = AsyncConnectionPool(config)
#         await pool.ainitialize()

#         # Create test table
#         async with pool.aacquire() as conn:
#             await conn.execute("""
#                 CREATE TABLE IF NOT EXISTS test_accounts (
#                     id SERIAL PRIMARY KEY,
#                     name VARCHAR(100),
#                     balance INTEGER DEFAULT 0
#                 )
#             """)

#         try:
#             yield pool
#         finally:
#             async with pool.aacquire() as conn:
#                 await conn.execute("DROP TABLE IF EXISTS test_accounts CASCADE")
#             await pool.aclose()

#     async def test_pool_blocks_when_all_connections_acquired(self, small_pool: AsyncConnectionPool) -> None:
#         """Test that pool blocks indefinitely when all connections are held.

#         Scenario:
#         1. Pool max_size=3
#         2. Acquire all 3 connections and hold them
#         3. Attempt 4th acquire should block (not fail immediately)
#         4. Verify blocking using asyncio.wait_for with timeout
#         """
#         release_event = asyncio.Event()
#         connections_acquired = 0

#         async def hold_connection() -> None:
#             """Acquire connection and hold until event set."""
#             nonlocal connections_acquired
#             async with small_pool.aacquire():
#                 connections_acquired += 1
#                 await release_event.wait()

#         # Start 3 tasks to hold all connections
#         holders = [asyncio.create_task(hold_connection()) for _ in range(3)]

#         # Wait for all 3 connections to be acquired
#         await asyncio.sleep(0.2)
#         assert connections_acquired == 3, "All 3 connections should be acquired"

#         # 4th acquire should block (timeout after 0.5 seconds)
#         # Use wrapper coroutine to ensure proper cleanup on timeout
#         async def try_acquire() -> None:
#             async with small_pool.aacquire():
#                 pass

#         with pytest.raises(asyncio.TimeoutError):
#             await asyncio.wait_for(try_acquire(), timeout=0.5)

#         # Cleanup: release all connections
#         release_event.set()
#         await asyncio.gather(*holders)

#     async def test_pool_raises_timeout_when_no_connections_available(self, small_pool: AsyncConnectionPool) -> None:
#         """Test that acquiring with pool timeout raises TimeoutError.

#         Scenario:
#         1. Exhaust all connections in pool
#         2. Next acquire should timeout based on pool config (timeout=2.0)
#         3. Verify TimeoutError raised after ~2 seconds
#         """
#         release_event = asyncio.Event()

#         async def hold_connection() -> None:
#             async with small_pool.aacquire():
#                 await release_event.wait()

#         # Hold all 3 connections
#         holders = [asyncio.create_task(hold_connection()) for _ in range(3)]
#         await asyncio.sleep(0.2)

#         # This should timeout after ~2 seconds (pool.timeout)
#         import time

#         start = time.monotonic()
#         timeout_occurred = False
#         elapsed = 0.0

#         # Wrap in safety timeout to prevent test from hanging
#         async def try_acquire_with_timeout() -> None:
#             nonlocal timeout_occurred, elapsed
#             try:
#                 async with small_pool.aacquire():
#                     pass
#             except (TimeoutError, Exception):
#                 # Pool timeout kicked in (expected)
#                 elapsed = time.monotonic() - start
#                 timeout_occurred = True
#                 raise

#         # Safety timeout (longer than expected pool timeout)
#         try:
#             await asyncio.wait_for(try_acquire_with_timeout(), timeout=5.0)
#             pytest.fail("Expected pool timeout, but acquire succeeded")
#         except (TimeoutError, Exception):
#             if not timeout_occurred:
#                 # Safety timeout hit, not pool timeout
#                 pytest.fail("Pool timeout didn't work - test safety timeout triggered")

#         # Should timeout after approximately 2 seconds (pool config)
#         assert 1.5 < elapsed < 3.0, f"Expected ~2s timeout, got {elapsed:.2f}s"

#         # Cleanup
#         release_event.set()
#         await asyncio.gather(*holders)

#     async def test_pool_recovers_when_connections_released(self, small_pool: AsyncConnectionPool) -> None:
#         """Test that pool immediately recovers when connection is released.

#         Scenario:
#         1. Exhaust pool (all 3 connections held)
#         2. Release one connection
#         3. Next acquire should succeed immediately (no blocking)
#         """
#         release_event = asyncio.Event()
#         single_release = asyncio.Event()

#         async def hold_connection(wait_for_single: bool = False) -> None:
#             async with small_pool.aacquire():
#                 if wait_for_single:
#                     await single_release.wait()
#                 else:
#                     await release_event.wait()

#         # Hold 2 connections indefinitely, 1 connection temporarily
#         holder1 = asyncio.create_task(hold_connection())
#         holder2 = asyncio.create_task(hold_connection())
#         holder3 = asyncio.create_task(hold_connection(wait_for_single=True))

#         await asyncio.sleep(0.2)

#         # Pool exhausted - verify by attempting acquire with short timeout
#         async def try_acquire() -> None:
#             async with small_pool.aacquire():
#                 pass

#         with pytest.raises(asyncio.TimeoutError):
#             await asyncio.wait_for(try_acquire(), timeout=0.3)

#         # Release one connection
#         single_release.set()
#         await asyncio.sleep(0.1)  # Give it time to release

#         # Now acquire should succeed immediately (within 0.5s)
#         async with asyncio.timeout(0.5):
#             async with small_pool.aacquire() as conn:
#                 result = await conn.fetchval("SELECT 1")
#                 assert result == 1

#         # Cleanup
#         release_event.set()
#         await asyncio.gather(holder1, holder2, holder3)

#     async def test_multiple_waiters_get_connections_in_order(self, small_pool: AsyncConnectionPool) -> None:
#         """Test that multiple waiting tasks get connections in FIFO order.

#         Scenario:
#         1. Exhaust pool
#         2. Queue 3 waiters
#         3. Release connections one by one
#         4. Verify waiters wake up in order they were queued
#         """
#         release_events = [asyncio.Event() for _ in range(3)]
#         waiter_results: list[int] = []

#         async def holder(idx: int) -> None:
#             """Hold a connection until signaled."""
#             async with small_pool.aacquire():
#                 await release_events[idx].wait()

#         async def waiter(waiter_id: int, ready_event: asyncio.Event) -> None:
#             """Wait for connection and record order."""
#             ready_event.set()  # Signal that waiter is ready
#             # Add timeout to prevent hanging if connection never becomes available
#             async with asyncio.timeout(10.0):
#                 async with small_pool.aacquire() as conn:
#                     waiter_results.append(waiter_id)
#                     result: int = await conn.fetchval("SELECT 1")
#                     assert result == 1

#         # Hold all 3 connections
#         holders = [asyncio.create_task(holder(i)) for i in range(3)]
#         await asyncio.sleep(0.2)

#         # Queue 3 waiters
#         waiter_ready_events = [asyncio.Event() for _ in range(3)]
#         waiters = [asyncio.create_task(waiter(i, waiter_ready_events[i])) for i in range(3)]

#         # Ensure all waiters are queued
#         for event in waiter_ready_events:
#             await event.wait()
#         await asyncio.sleep(0.1)

#         # Release connections one by one and verify FIFO order
#         for idx in range(3):
#             release_events[idx].set()
#             await asyncio.sleep(0.2)  # Give time for waiter to acquire

#         # Wait for all waiters to complete (with timeout)
#         try:
#             await asyncio.wait_for(asyncio.gather(*waiters), timeout=10.0)
#         except TimeoutError:
#             pytest.fail("Waiters didn't complete in time - possible deadlock")

#         # Verify FIFO ordering
#         assert waiter_results == [0, 1, 2], f"Expected FIFO order [0,1,2], got {waiter_results}"

#         # Cleanup
#         await asyncio.wait_for(asyncio.gather(*holders), timeout=5.0)

#     async def test_connection_always_returned_on_exception(self, small_pool: AsyncConnectionPool) -> None:
#         """Test that connection is returned to pool even when exception occurs.

#         Scenario:
#         1. Acquire connection
#         2. Raise exception inside context manager
#         3. Verify pool size restored (connection returned)
#         4. Verify connection is healthy and reusable
#         """
#         # Get initial pool size
#         initial_size = small_pool.pool.get_size()

#         class TestException(Exception):
#             pass

#         # Acquire and raise exception
#         with pytest.raises(TestException):
#             async with small_pool.aacquire() as conn:
#                 await conn.fetchval("SELECT 1")
#                 raise TestException("Intentional error")

#         # Pool size should be restored
#         await asyncio.sleep(0.1)
#         final_size = small_pool.pool.get_size()
#         assert final_size == initial_size, f"Pool size should be restored: {initial_size} -> {final_size}"

#         # Connection should be reusable
#         async with small_pool.aacquire() as conn:
#             result = await conn.fetchval("SELECT 42")
#             assert result == 42

#     async def test_pool_statistics_accurate_under_concurrent_load(self, small_pool: AsyncConnectionPool) -> None:
#         """Test that pool statistics remain accurate under concurrent acquire/release cycles.

#         Scenario:
#         1. Launch concurrent acquire/release operations
#         2. Continuously verify pool size never exceeds max_size
#         3. Verify pool size eventually returns to min_size when idle
#         """
#         max_size = small_pool.pool.get_max_size()
#         violations: list[int] = []

#         async def acquire_release_cycle() -> None:
#             """Perform acquire/release cycle."""
#             async with small_pool.aacquire() as conn:
#                 # Check pool size doesn't exceed max
#                 current_size = small_pool.pool.get_size()
#                 if current_size > max_size:
#                     violations.append(current_size)

#                 await conn.fetchval("SELECT 1")
#                 await asyncio.sleep(0.05)  # Hold briefly

#         # Run 20 concurrent cycles
#         await asyncio.gather(*[acquire_release_cycle() for _ in range(20)])

#         # No violations should occur
#         assert len(violations) == 0, f"Pool size exceeded max_size: {violations}"

#         # Pool should still be healthy
#         health = await small_pool.ahealth_check()
#         assert health.status == HealthCheckStatus.HEALTHY
#         assert health.pool_size is not None
#         assert health.pool_size <= max_size

#     async def test_no_connection_leak_with_context_manager(self, small_pool: AsyncConnectionPool) -> None:
#         """Test that context manager guarantees connection is always returned.

#         Scenario:
#         1. Acquire connections multiple times
#         2. Verify pool size unchanged after each acquisition
#         3. Test both normal exit and exception exit
#         """
#         initial_size = small_pool.pool.get_size()

#         # Normal exit - 10 iterations
#         for _ in range(10):
#             async with small_pool.aacquire() as conn:
#                 await conn.fetchval("SELECT 1")

#         await asyncio.sleep(0.1)
#         assert small_pool.pool.get_size() == initial_size, "Pool size should be unchanged after normal exits"

#         # Exception exit - 10 iterations
#         for _ in range(10):
#             try:
#                 async with small_pool.aacquire() as conn:
#                     await conn.fetchval("SELECT 1")
#                     raise ValueError("Test exception")
#             except ValueError:
#                 pass

#         await asyncio.sleep(0.1)
#         assert small_pool.pool.get_size() == initial_size, "Pool size should be unchanged even after exception exits"

#     async def test_pool_health_check_while_connections_busy(self, small_pool: AsyncConnectionPool) -> None:
#         """Test that health check works even when connections are busy.

#         Scenario:
#         1. Acquire 2 of 3 connections (hold them)
#         2. Health check should still succeed (uses remaining connection)
#         3. Verify accurate pool statistics
#         """
#         release_event = asyncio.Event()

#         async def hold_connection() -> None:
#             async with small_pool.aacquire():
#                 await release_event.wait()

#         # Hold 2 connections
#         holders = [asyncio.create_task(hold_connection()) for _ in range(2)]
#         await asyncio.sleep(0.2)

#         # Health check should succeed
#         health = await small_pool.ahealth_check()
#         assert health.status == HealthCheckStatus.HEALTHY
#         assert health.pool_initialized is True
#         assert health.pool_size is not None
#         assert health.pool_max_size == 3

#         # Cleanup
#         release_event.set()
#         await asyncio.gather(*holders)

#     async def test_concurrent_acquire_release_stress_test(self, small_pool: AsyncConnectionPool) -> None:
#         """Stress test with many concurrent acquire/release operations.

#         Scenario:
#         1. Launch 50 concurrent tasks
#         2. Each task performs multiple acquire/release cycles
#         3. Verify no deadlocks, no exceptions, all tasks complete
#         4. Verify pool remains healthy
#         """
#         task_count = 50
#         cycles_per_task = 3
#         completed_tasks = 0

#         async def stress_worker() -> None:
#             nonlocal completed_tasks
#             for _ in range(cycles_per_task):
#                 async with small_pool.aacquire() as conn:
#                     await conn.fetchval("SELECT 1")
#                     await asyncio.sleep(0.01)  # Small delay
#             completed_tasks += 1

#         # Run all tasks concurrently
#         await asyncio.gather(*[stress_worker() for _ in range(task_count)])

#         # All tasks should complete
#         assert completed_tasks == task_count, f"Expected {task_count} tasks to complete, got {completed_tasks}"

#         # Pool should still be healthy
#         health = await small_pool.ahealth_check()
#         assert health.status == HealthCheckStatus.HEALTHY

#     async def test_pool_exhaustion_does_not_affect_other_operations(self, small_pool: AsyncConnectionPool) -> None:
#         """Test that exhausting pool doesn't prevent other operations from completing.

#         Scenario:
#         1. Hold all 3 connections
#         2. Launch operation that eventually gets connection when one is released
#         3. Verify operation completes successfully
#         """
#         release_event = asyncio.Event()
#         operation_completed = asyncio.Event()

#         async def holder() -> None:
#             async with small_pool.aacquire():
#                 await release_event.wait()

#         async def delayed_operation() -> int:
#             """This will wait for a connection, then execute."""
#             # Add timeout to prevent infinite waiting
#             async with asyncio.timeout(10.0):
#                 async with small_pool.aacquire() as conn:
#                     result: int = await conn.fetchval("SELECT 42")
#                     operation_completed.set()
#                     return result

#         # Hold all connections
#         holders = [asyncio.create_task(holder()) for _ in range(3)]
#         await asyncio.sleep(0.2)

#         # Start delayed operation (will wait for connection)
#         delayed_task = asyncio.create_task(delayed_operation())
#         await asyncio.sleep(0.2)

#         # Operation should not have completed yet
#         assert not operation_completed.is_set(), "Operation should be waiting for connection"

#         # Release one connection
#         release_event.set()

#         # Operation should now complete (with timeout)
#         try:
#             result = await asyncio.wait_for(delayed_task, timeout=5.0)
#             assert result == 42
#             assert operation_completed.is_set()
#         except TimeoutError:
#             pytest.fail("Delayed operation didn't complete after connection was released")

#         # Cleanup
#         await asyncio.wait_for(asyncio.gather(*holders), timeout=5.0)
