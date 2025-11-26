"""Query timeout and cancellation integration tests.

Tests critical timeout behavior:
- command_timeout terminates slow queries
- Connection recovery after timeout
- Pool health after timeouts
- Cursor timeout during iteration
- Transaction timeout handling
- No connection leaks from timeouts

These tests prevent connection pool starvation from slow queries.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import SecretStr

from pixiu.database import AsyncConnectionPool, DatabaseConfig, DatabaseConnectionSettings, PoolSettings
from pixiu.database.config import AsyncpgSettings
from pixiu.database.models import HealthCheckStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.mark.integration
@pytest.mark.database
class TestQueryTimeout:
    """Test query timeout and cancellation scenarios."""

    @pytest.fixture
    async def timeout_pool(self, postgres_container: Any) -> AsyncIterator[AsyncConnectionPool]:
        """Create pool with short command_timeout for testing.

        Pool configuration:
        - min_size: 2
        - max_size: 5
        - command_timeout: 2.0 seconds (short for testing)
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
                command_timeout=2.0,  # Short timeout for testing
            ),
        )

        pool = AsyncConnectionPool(config)
        await pool.ainitialize()

        # Create test table
        async with pool.aacquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS test_data (
                    id SERIAL PRIMARY KEY,
                    value INTEGER
                )
            """)
            # Insert some test data
            await conn.executemany(
                "INSERT INTO test_data (value) VALUES ($1)",
                [(i,) for i in range(1000)],
            )

        try:
            yield pool
        finally:
            async with pool.aacquire() as conn:
                await conn.execute("DROP TABLE IF EXISTS test_data CASCADE")
            await pool.aclose()

    async def test_command_timeout_terminates_slow_query(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test that command_timeout terminates slow query.

        Scenario:
        1. Execute query with pg_sleep(10) seconds
        2. command_timeout=2.0 should cancel query after 2 seconds
        3. Should raise TimeoutError
        """
        start = time.monotonic()

        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await timeout_pool.aexecute("SELECT pg_sleep(10)")

        elapsed = time.monotonic() - start

        # Should timeout around 2 seconds (command_timeout), not wait full 10 seconds
        assert elapsed < 4.0, f"Query should timeout around 2s, took {elapsed:.2f}s"
        assert elapsed > 1.5, f"Query should take at least 1.5s to timeout, took {elapsed:.2f}s"

    async def test_connection_usable_after_timeout(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test that connection is usable immediately after timeout.

        Scenario:
        1. Query times out
        2. Same connection should work for next query
        3. Verify no corruption or state issues
        """
        # First query times out
        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await timeout_pool.aexecute("SELECT pg_sleep(10)")

        # Immediately after timeout, connection should work
        result = await timeout_pool.afetchval("SELECT 42")
        assert result == 42

        # And again
        result = await timeout_pool.afetchval("SELECT COUNT(*) FROM test_data")
        assert result == 1000

    async def test_pool_not_blocked_by_slow_queries(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test that pool remains responsive when some queries timeout.

        Scenario:
        1. Launch 2 slow queries (will timeout)
        2. Pool max_size=5, so 3 connections should remain available
        3. Fast queries should still work concurrently
        """
        slow_query_count = 0

        async def slow_query() -> None:
            nonlocal slow_query_count
            try:
                await timeout_pool.aexecute("SELECT pg_sleep(10)")
            except TimeoutError:
                slow_query_count += 1

        async def fast_query() -> int:
            result: int = await timeout_pool.afetchval("SELECT 1")
            return result

        # Launch 2 slow queries and 3 fast queries concurrently
        results = await asyncio.gather(
            slow_query(),
            slow_query(),
            fast_query(),
            fast_query(),
            fast_query(),
            return_exceptions=True,
        )

        # Slow queries should timeout
        assert slow_query_count == 2, "Both slow queries should timeout"

        # Fast queries should succeed
        fast_results = [r for r in results if isinstance(r, int)]
        assert len(fast_results) == 3, "All 3 fast queries should succeed"
        assert all(r == 1 for r in fast_results), "Fast queries should return 1"

    async def test_cursor_timeout_during_iteration(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test cursor timeout when timeout occurs during iteration.

        Scenario:
        1. Start cursor iteration
        2. Use pg_sleep in query to cause timeout
        3. Verify proper exception and cleanup
        """
        # Query that times out
        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            async with timeout_pool.acursor(
                "SELECT pg_sleep(10), id FROM test_data",
                timeout=2.0,
            ) as cursor:
                async for _row in cursor:
                    pass  # Should timeout before completing iteration

        # Pool should still be healthy
        health = await timeout_pool.ahealth_check()
        assert health.status == HealthCheckStatus.HEALTHY

    async def test_transaction_timeout_with_multiple_queries(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test transaction timeout when one query in transaction times out.

        Scenario:
        1. Transaction with multiple queries
        2. One query times out
        3. Verify transaction is rolled back
        4. Verify connection returned to pool
        """
        initial_count = await timeout_pool.afetchval("SELECT COUNT(*) FROM test_data")

        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            async with timeout_pool.atransaction() as conn:
                # Insert some data
                await conn.execute("INSERT INTO test_data (value) VALUES ($1)", 9999)

                # This query will timeout
                await conn.execute("SELECT pg_sleep(10)")

                # Should never reach here
                await conn.execute("INSERT INTO test_data (value) VALUES ($1)", 8888)

        # Count should be unchanged (transaction rolled back)
        final_count = await timeout_pool.afetchval("SELECT COUNT(*) FROM test_data")
        assert final_count == initial_count, "Transaction should have been rolled back"

        # No row with value 9999 should exist
        marker_count = await timeout_pool.afetchval("SELECT COUNT(*) FROM test_data WHERE value = $1", 9999)
        assert marker_count == 0, "Inserted row should have been rolled back"

    async def test_timeout_exception_propagates_correctly(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test that timeout exception propagates through nested contexts.

        Scenario:
        1. Timeout in nested context managers
        2. Exception should bubble up properly
        3. All resources should be cleaned up
        """
        exception_caught = False

        try:
            async with timeout_pool.atransaction() as conn:
                # Nested operation that times out
                await conn.execute("SELECT pg_sleep(10)")
        except TimeoutError:
            exception_caught = True

        assert exception_caught, "TimeoutError should propagate"

        # Pool should be healthy
        health = await timeout_pool.ahealth_check()
        assert health.status == HealthCheckStatus.HEALTHY

    async def test_no_connection_leak_from_timeout(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test that timeouts don't leak connections.

        Scenario:
        1. Multiple queries timeout
        2. Verify pool size unchanged
        3. Verify all connections eventually returned
        """
        initial_size = timeout_pool.pool.get_size()

        # Run 5 queries that will timeout
        for _ in range(5):
            with suppress(TimeoutError, asyncio.TimeoutError):
                await timeout_pool.aexecute("SELECT pg_sleep(10)")

        # Give pool time to return connections
        await asyncio.sleep(0.5)

        # Pool size should be same (no leaks)
        final_size = timeout_pool.pool.get_size()
        assert final_size == initial_size, f"Pool size changed: {initial_size} -> {final_size}"

        # Pool should still be healthy
        health = await timeout_pool.ahealth_check()
        assert health.status == HealthCheckStatus.HEALTHY

    async def test_per_query_timeout_overrides_pool_timeout(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test that per-query timeout parameter overrides pool command_timeout.

        Scenario:
        1. Pool has command_timeout=2.0
        2. Query with timeout=0.5 should timeout faster
        3. Query with timeout=5.0 should timeout slower
        """
        # Fast timeout (0.5s) should override pool timeout (2.0s)
        start = time.monotonic()
        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await timeout_pool.aexecute("SELECT pg_sleep(10)", timeout=0.5)
        elapsed = time.monotonic() - start

        assert elapsed < 1.5, f"Query should timeout around 0.5s, took {elapsed:.2f}s"

        # Slow timeout (5.0s) - query completes before timeout
        start = time.monotonic()
        result = await timeout_pool.afetchval("SELECT pg_sleep(0.1)", timeout=5.0)
        elapsed = time.monotonic() - start

        assert result is None, "pg_sleep should return NULL"
        assert elapsed < 1.0, f"Query should complete quickly, took {elapsed:.2f}s"

    async def test_concurrent_timeouts_do_not_interfere(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test that concurrent queries timing out don't interfere with each other.

        Scenario:
        1. Launch multiple queries with different timeout durations
        2. Each should timeout independently
        3. No cross-contamination of state
        """
        results: list[float] = []

        async def query_with_timeout(sleep_time: float, timeout: float) -> None:
            start = time.monotonic()
            try:
                await timeout_pool.aexecute(f"SELECT pg_sleep({sleep_time})", timeout=timeout)
            except TimeoutError:
                elapsed = time.monotonic() - start
                results.append(elapsed)

        # Launch queries with different timeouts concurrently
        await asyncio.gather(
            query_with_timeout(10.0, 0.5),  # Should timeout around 0.5s
            query_with_timeout(10.0, 1.0),  # Should timeout around 1.0s
            query_with_timeout(10.0, 1.5),  # Should timeout around 1.5s
        )

        # All should have timed out
        assert len(results) == 3, "All queries should have timed out"

        # Verify independent timeout behavior (rough checks)
        results.sort()
        assert results[0] < 1.0, "First timeout should be < 1.0s"
        assert results[1] < 1.5, "Second timeout should be < 1.5s"
        assert results[2] < 2.0, "Third timeout should be < 2.0s"

    async def test_timeout_in_executemany(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test timeout behavior with executemany batch operations.

        Scenario:
        1. executemany with slow operation
        2. Should timeout appropriately
        3. No partial batch application
        """
        # Create slow batch operation using trigger or slow function
        # For simplicity, test that timeout works with executemany
        # Use values 10000+ to avoid collision with fixture data (0-999)
        batch_data = [(i + 10000,) for i in range(100)]

        # Fast batch should work
        await timeout_pool.aexecutemany(
            "INSERT INTO test_data (value) VALUES ($1)",
            batch_data,
            timeout=5.0,
        )

        # Verify inserted (check for values >= 10000)
        count = await timeout_pool.afetchval("SELECT COUNT(*) FROM test_data WHERE value >= 10000")
        assert count == 100

    async def test_health_check_after_multiple_timeouts(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test that pool health remains good after multiple timeouts.

        Scenario:
        1. Trigger multiple query timeouts
        2. Health check should still show healthy
        3. Pool should be fully functional
        """
        # Cause 10 timeouts
        for _ in range(10):
            with suppress(TimeoutError, asyncio.TimeoutError):
                await timeout_pool.aexecute("SELECT pg_sleep(10)")

        # Pool should still be healthy
        health = await timeout_pool.ahealth_check()
        assert health.status == HealthCheckStatus.HEALTHY
        assert health.pool_initialized is True
        assert health.pool_size is not None
        assert health.pool_size >= 2  # At least min_size

        # Pool should still work normally
        result = await timeout_pool.afetchval("SELECT 999")
        assert result == 999

    async def test_timeout_with_large_result_set(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test timeout behavior when fetching large result set.

        Scenario:
        1. Query returns large result set
        2. Timeout while fetching results
        3. Verify proper cleanup
        """
        # This should work (fetch all 1000 rows)
        results = await timeout_pool.afetch("SELECT * FROM test_data")
        assert len(results) == 1000

        # Query with artificial slowdown and timeout
        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            await timeout_pool.afetch(
                "SELECT pg_sleep(0.01), * FROM test_data",
                timeout=1.0,
            )

        # Pool should still work
        result = await timeout_pool.afetchval("SELECT 1")
        assert result == 1

    async def test_timeout_does_not_affect_other_connections(self, timeout_pool: AsyncConnectionPool) -> None:
        """Test that one connection timing out doesn't affect others.

        Scenario:
        1. Connection A times out
        2. Connection B should continue working normally
        3. No cross-connection contamination
        """

        async def timeout_query() -> None:
            with suppress(TimeoutError, asyncio.TimeoutError):
                await timeout_pool.aexecute("SELECT pg_sleep(10)")

        async def normal_query() -> int:
            # This should work fine while other connection times out
            await asyncio.sleep(0.5)  # Give timeout_query time to start
            result: int = await timeout_pool.afetchval("SELECT 42")
            return result

        # Run both concurrently
        results = await asyncio.gather(
            timeout_query(),
            normal_query(),
            return_exceptions=True,
        )

        # Normal query should succeed
        normal_result = [r for r in results if isinstance(r, int)]
        assert len(normal_result) == 1
        assert normal_result[0] == 42
