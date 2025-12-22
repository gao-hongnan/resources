"""Comprehensive tests for async cursor operations.

Tests the async cursor context manager implementation including:
- Basic cursor iteration
- Prefetch behavior and memory efficiency
- Timeout handling
- Transaction isolation with cursors
- Error handling and cleanup
- Concurrent cursor usage
- Edge cases and boundary conditions
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import asyncpg
import pytest
import pytest_asyncio

from leitmotif.infrastructure.postgres.enums import HealthStatus

if TYPE_CHECKING:
    from leitmotif.infrastructure.postgres import AsyncConnectionPool


@pytest_asyncio.fixture(autouse=True)
async def _setup_cursor_test_data(asyncpg_pool: AsyncConnectionPool) -> None:
    """Set up test data before each cursor test."""
    async with asyncpg_pool.aacquire() as conn:
        # Clean up first
        await conn.execute("TRUNCATE TABLE test_users RESTART IDENTITY CASCADE")

        # Insert test data - 1000 rows for cursor testing
        batch_data: list[tuple[str, str, int]] = [
            (f"user_{i}", f"user{i}@example.com", 20 + (i % 50)) for i in range(1000)
        ]

        await conn.executemany(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            batch_data,
        )


@pytest.mark.asyncio
@pytest.mark.integration
class TestCursorOperations:
    """Integration tests for cursor operations."""

    async def test_cursor_basic_iteration(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test basic cursor iteration with default prefetch."""
        total_count = 0

        async with asyncpg_pool.acursor("SELECT * FROM test_users ORDER BY id") as cursor:
            async for _record in cursor:
                total_count += 1

        assert total_count == 1000, f"Expected 1000 records, got {total_count}"

    async def test_cursor_with_custom_prefetch(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with custom prefetch size."""
        total_count = 0
        prefetch_size = 100

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users ORDER BY id",
            prefetch=prefetch_size,
        ) as cursor:
            async for _record in cursor:
                total_count += 1

        assert total_count == 1000

    async def test_cursor_with_where_clause(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with WHERE clause and parameters."""
        min_age = 30
        max_age = 40
        ages_seen: set[int] = set()

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users WHERE age >= $1 AND age <= $2 ORDER BY age",
            min_age,
            max_age,
            prefetch=50,
        ) as cursor:
            async for record in cursor:
                ages_seen.add(record["age"])

        assert all(min_age <= age <= max_age for age in ages_seen), "Age filter not working correctly"
        assert len(ages_seen) > 0, "No records fetched"

    async def test_cursor_fetch_partial_results(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor when only fetching partial results (early break)."""
        count = 0
        max_fetch = 100

        async with asyncpg_pool.acursor("SELECT * FROM test_users ORDER BY id", prefetch=50) as cursor:
            async for _record in cursor:
                count += 1
                if count >= max_fetch:
                    break

        # Cursor should properly close even when not fully consumed
        assert count == max_fetch

    async def test_cursor_with_timeout(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with timeout parameter."""
        total_count = 0

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users ORDER BY id",
            prefetch=100,
            timeout=30.0,
        ) as cursor:
            async for _record in cursor:
                total_count += 1

        assert total_count == 1000

    async def test_cursor_with_read_committed_isolation(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with read_committed isolation level."""
        count = 0

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users WHERE age > $1 ORDER BY id",
            25,
            prefetch=100,
            isolation="read_committed",
        ) as cursor:
            async for _record in cursor:
                count += 1

        assert count > 0

    async def test_cursor_with_repeatable_read_isolation(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with repeatable_read isolation level."""
        count = 0

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users ORDER BY id",
            prefetch=100,
            isolation="repeatable_read",
        ) as cursor:
            async for _record in cursor:
                count += 1

        assert count == 1000

    async def test_cursor_with_serializable_isolation(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with serializable isolation level."""
        count = 0

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users ORDER BY id",
            prefetch=100,
            isolation="serializable",
        ) as cursor:
            async for _record in cursor:
                count += 1

        assert count == 1000

    async def test_cursor_readonly_transaction(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with readonly transaction (should work for SELECT)."""
        count = 0

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users ORDER BY id",
            prefetch=100,
            readonly=True,
        ) as cursor:
            async for _record in cursor:
                count += 1

        assert count == 1000

    async def test_cursor_empty_result_set(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with query returning no results."""
        count = 0

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users WHERE age > $1",
            1000,  # Age that doesn't exist
            prefetch=50,
        ) as cursor:
            async for _record in cursor:
                count += 1

        assert count == 0

    async def test_cursor_single_result(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with query returning single result."""
        count = 0
        result = None

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users WHERE username = $1",
            "user_0",
            prefetch=1,
        ) as cursor:
            async for record in cursor:
                result = record
                count += 1

        assert count == 1
        assert result is not None
        assert result["username"] == "user_0"

    async def test_cursor_error_handling_invalid_query(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor error handling with invalid SQL query."""
        with pytest.raises(asyncpg.UndefinedTableError):
            async with asyncpg_pool.acursor("SELECT * FROM nonexistent_table") as cursor:
                async for _record in cursor:
                    pass

    async def test_cursor_error_handling_invalid_params(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor error handling with invalid parameters."""
        with pytest.raises((asyncpg.PostgresError, asyncpg.InterfaceError)):
            # Too few parameters
            async with asyncpg_pool.acursor("SELECT * FROM test_users WHERE age = $1") as cursor:
                async for _record in cursor:
                    pass

    async def test_cursor_cleanup_on_exception(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor cleanup when exception occurs during iteration."""

        class CursorProcessingError(Exception):
            """Exception raised during cursor iteration testing."""

        count = 0

        with pytest.raises(CursorProcessingError):
            async with asyncpg_pool.acursor("SELECT * FROM test_users ORDER BY id", prefetch=50) as cursor:
                async for _record in cursor:
                    count += 1
                    if count >= 10:
                        raise CursorProcessingError

        # Verify pool is still healthy after exception
        health = await asyncpg_pool.ahealth_check()
        assert health.status == HealthStatus.HEALTHY
        assert health.pool_size is not None

    async def test_concurrent_cursor_operations(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test multiple concurrent cursor operations."""

        async def count_users_in_age_range(min_age: int, max_age: int) -> int:
            count = 0
            async with asyncpg_pool.acursor(
                "SELECT * FROM test_users WHERE age >= $1 AND age <= $2",
                min_age,
                max_age,
                prefetch=50,
            ) as cursor:
                async for _record in cursor:
                    count += 1
            return count

        # Run multiple cursor operations concurrently
        results = await asyncio.gather(
            count_users_in_age_range(20, 30),
            count_users_in_age_range(31, 40),
            count_users_in_age_range(41, 50),
            count_users_in_age_range(51, 60),
        )

        # All operations should complete successfully
        assert all(isinstance(r, int) and r >= 0 for r in results)
        assert sum(results) <= 1000

    async def test_cursor_with_aggregation(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with aggregation query."""
        age_groups: dict[int, int] = {}

        async with asyncpg_pool.acursor(
            "SELECT age, COUNT(*) as count FROM test_users GROUP BY age ORDER BY age",
            prefetch=50,
        ) as cursor:
            async for record in cursor:
                age_groups[record["age"]] = record["count"]

        assert len(age_groups) > 0
        assert sum(age_groups.values()) == 1000

    async def test_cursor_with_join(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with JOIN query (self-join for testing)."""
        count = 0

        async with asyncpg_pool.acursor(
            """
            SELECT u1.username, u1.age, u2.username as similar_age_user
            FROM test_users u1
            JOIN test_users u2 ON u1.age = u2.age AND u1.id != u2.id
            WHERE u1.id <= 100
            ORDER BY u1.id
            LIMIT 50
            """,
            prefetch=25,
        ) as cursor:
            async for _record in cursor:
                count += 1

        # Should get some results from the join
        assert count > 0

    async def test_cursor_with_order_by(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with ORDER BY to verify correct ordering."""
        prev_age = -1
        count = 0

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users ORDER BY age ASC, id ASC",
            prefetch=100,
        ) as cursor:
            async for record in cursor:
                current_age = record["age"]
                assert current_age >= prev_age, "Records not properly ordered by age"
                prev_age = current_age
                count += 1

        assert count == 1000

    async def test_cursor_prefetch_efficiency(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test different prefetch sizes for efficiency."""
        # Test with very small prefetch
        count_small = 0
        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users ORDER BY id",
            prefetch=10,
        ) as cursor:
            async for _record in cursor:
                count_small += 1

        # Test with large prefetch
        count_large = 0
        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users ORDER BY id",
            prefetch=500,
        ) as cursor:
            async for _record in cursor:
                count_large += 1

        # Both should fetch all records
        assert count_small == count_large == 1000

    async def test_cursor_with_limit(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with LIMIT clause."""
        count = 0
        limit = 50

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users ORDER BY id LIMIT $1",
            limit,
            prefetch=25,
        ) as cursor:
            async for _record in cursor:
                count += 1

        assert count == limit

    async def test_cursor_transaction_isolation_sees_committed_changes(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test that cursor in new transaction sees committed changes."""
        # Insert a new user
        await asyncpg_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "new_user",
            "new@example.com",
            25,
        )

        # Cursor should see the new user
        found = False
        async with asyncpg_pool.acursor("SELECT * FROM test_users WHERE username = $1", "new_user") as cursor:
            async for record in cursor:
                found = True
                assert record["username"] == "new_user"

        assert found

    async def test_cursor_transaction_rollback_on_error(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test that cursor transaction rolls back on error."""
        initial_count: Any = await asyncpg_pool.afetchval("SELECT COUNT(*) FROM test_users")

        try:
            async with asyncpg_pool.acursor("SELECT * FROM test_users ORDER BY id", prefetch=50) as cursor:
                async for _record in cursor:
                    # Try to insert with duplicate username (should fail)
                    await asyncpg_pool.aexecute(
                        "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                        "user_0",  # Duplicate
                        "duplicate@example.com",
                        30,
                    )
        except asyncpg.UniqueViolationError:
            pass

        # Count should be unchanged
        final_count: Any = await asyncpg_pool.afetchval("SELECT COUNT(*) FROM test_users")
        assert final_count == initial_count

    async def test_cursor_deferrable_transaction(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with deferrable transaction option."""
        count = 0

        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users ORDER BY id",
            prefetch=100,
            deferrable=True,
        ) as cursor:
            async for _record in cursor:
                count += 1

        assert count == 1000

    async def test_cursor_complex_where_conditions(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with complex WHERE conditions."""
        count = 0

        async with asyncpg_pool.acursor(
            """
            SELECT * FROM test_users
            WHERE (age > $1 AND age < $2)
               OR (age > $3 AND age < $4)
            ORDER BY age
            """,
            25,
            35,
            45,
            55,
            prefetch=50,
        ) as cursor:
            async for _record in cursor:
                count += 1

        assert count > 0

    async def test_cursor_distinct_query(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor with DISTINCT query."""
        unique_ages: set[int] = set()

        async with asyncpg_pool.acursor(
            "SELECT DISTINCT age FROM test_users ORDER BY age",
            prefetch=50,
        ) as cursor:
            async for record in cursor:
                unique_ages.add(record["age"])

        # Should have distinct ages
        assert len(unique_ages) > 0
        assert len(unique_ages) <= 50  # Since age is 20 + (i % 50)
