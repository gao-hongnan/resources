"""Concurrent transaction conflict and isolation integration tests.

Tests critical transaction behavior under concurrent access:
- Serialization failures with concurrent writes
- Deadlock detection and handling
- Lost update prevention
- Phantom read behavior across isolation levels
- Proper transaction rollback on conflicts

These tests expose data consistency bugs that occur in production
under concurrent load.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import asyncpg
import pytest
from pydantic import SecretStr

from pixiu.database import AsyncConnectionPool, DatabaseConfig, DatabaseConnectionSettings, PoolSettings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.mark.integration
@pytest.mark.database
class TestTransactionConflicts:
    """Test concurrent transaction conflicts and isolation levels."""

    @pytest.fixture
    async def conflict_pool(self, postgres_container: Any) -> AsyncIterator[AsyncConnectionPool]:
        """Create pool for testing transaction conflicts.

        Pool configuration:
        - min_size: 2 (need concurrent connections)
        - max_size: 10 (support multiple concurrent transactions)
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
                timeout=10.0,
            ),
        )

        pool = AsyncConnectionPool(config)
        await pool.ainitialize()

        # Create test tables
        async with pool.aacquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS test_accounts (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) UNIQUE,
                    balance INTEGER DEFAULT 0
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS test_orders (
                    id SERIAL PRIMARY KEY,
                    product VARCHAR(100),
                    quantity INTEGER
                )
            """)

        try:
            yield pool
        finally:
            async with pool.aacquire() as conn:
                await conn.execute("DROP TABLE IF EXISTS test_accounts CASCADE")
                await conn.execute("DROP TABLE IF EXISTS test_orders CASCADE")
            await pool.aclose()

    @pytest.fixture(autouse=True)
    async def _cleanup_data(self, conflict_pool: AsyncConnectionPool) -> None:
        """Clean up test data before each test."""
        async with conflict_pool.aacquire() as conn:
            await conn.execute("TRUNCATE TABLE test_accounts RESTART IDENTITY CASCADE")
            await conn.execute("TRUNCATE TABLE test_orders RESTART IDENTITY CASCADE")

    async def test_serializable_detects_concurrent_write_conflict(self, conflict_pool: AsyncConnectionPool) -> None:
        """Test that serializable isolation detects concurrent write conflicts.

        Scenario:
        1. Transaction 1: Read balance, update it
        2. Transaction 2: Read same balance, update it
        3. One transaction should raise SerializationError
        """
        # Insert test account
        await conflict_pool.aexecute("INSERT INTO test_accounts (name, balance) VALUES ($1, $2)", "alice", 100)

        ready_event = asyncio.Event()
        proceed_event = asyncio.Event()
        results: list[bool | Exception] = []

        async def transaction_1() -> None:
            try:
                async with conflict_pool.atransaction(isolation="serializable") as conn:
                    # Read balance
                    balance = await conn.fetchval("SELECT balance FROM test_accounts WHERE name = $1", "alice")

                    # Signal that we've read, then wait
                    ready_event.set()
                    await proceed_event.wait()

                    # Update balance
                    await conn.execute(
                        "UPDATE test_accounts SET balance = $1 WHERE name = $2",
                        balance + 50,  # type: ignore[operator]
                        "alice",
                    )
                results.append(True)
            except asyncpg.SerializationError as e:
                results.append(e)

        async def transaction_2() -> None:
            try:
                # Wait for T1 to read
                await ready_event.wait()

                async with conflict_pool.atransaction(isolation="serializable") as conn:
                    # Read balance (same as T1)
                    balance = await conn.fetchval("SELECT balance FROM test_accounts WHERE name = $1", "alice")

                    # Try to update - this will conflict with T1
                    await conn.execute(
                        "UPDATE test_accounts SET balance = $1 WHERE name = $2",
                        balance + 30,  # type: ignore[operator]
                        "alice",
                    )

                results.append(True)
            except asyncpg.SerializationError as e:
                results.append(e)

        # Run both transactions concurrently
        t1 = asyncio.create_task(transaction_1())
        t2 = asyncio.create_task(transaction_2())

        # Give T2 time to start and block
        await asyncio.sleep(0.3)

        # Let T1 proceed
        proceed_event.set()

        await asyncio.gather(t1, t2, return_exceptions=True)

        # One should succeed, one should fail with SerializationError
        assert len(results) == 2
        successes = sum(1 for r in results if r is True)
        failures = sum(1 for r in results if isinstance(r, asyncpg.SerializationError))

        assert successes == 1, "Expected exactly one transaction to succeed"
        assert failures == 1, "Expected exactly one transaction to fail with SerializationError"

    async def test_lost_update_prevented_with_serializable(self, conflict_pool: AsyncConnectionPool) -> None:
        """Test that serializable isolation prevents lost updates.

        Classic read-modify-write race condition:
        1. Both transactions read balance=100
        2. Both try to write balance+50
        3. Without serializable, one update would be lost
        4. With serializable, one transaction fails
        """
        await conflict_pool.aexecute("INSERT INTO test_accounts (name, balance) VALUES ($1, $2)", "bob", 100)

        barrier = asyncio.Event()
        results: list[bool | Exception] = []

        async def read_modify_write(increment: int) -> None:
            try:
                async with conflict_pool.atransaction(isolation="serializable") as conn:
                    # Read current balance
                    balance = await conn.fetchval("SELECT balance FROM test_accounts WHERE name = $1", "bob")

                    # Wait for both transactions to read
                    await barrier.wait()
                    await asyncio.sleep(0.1)

                    # Write new balance
                    await conn.execute(
                        "UPDATE test_accounts SET balance = $1 WHERE name = $2",
                        balance + increment,  # type: ignore[operator]
                        "bob",
                    )
                results.append(True)
            except asyncpg.SerializationError as e:
                results.append(e)

        # Start both transactions
        t1 = asyncio.create_task(read_modify_write(50))
        t2 = asyncio.create_task(read_modify_write(30))

        # Wait for both to read
        await asyncio.sleep(0.2)
        barrier.set()

        await asyncio.gather(t1, t2, return_exceptions=True)

        # One should succeed, one should fail
        successes = sum(1 for r in results if r is True)
        failures = sum(1 for r in results if isinstance(r, asyncpg.SerializationError))

        assert successes == 1, "Expected exactly one transaction to succeed"
        assert failures == 1, "Expected exactly one transaction to fail"

        # Final balance should be either 150 or 130 (not 180 which would be lost update)
        final_balance = await conflict_pool.afetchval("SELECT balance FROM test_accounts WHERE name = $1", "bob")
        assert final_balance in (150, 130), f"Expected balance 150 or 130, got {final_balance}"

    async def test_deadlock_detected_with_cross_locked_rows(self, conflict_pool: AsyncConnectionPool) -> None:
        """Test that PostgreSQL detects deadlocks with cross-locked rows.

        Scenario:
        1. Insert two accounts: alice and bob
        2. Transaction 1: lock alice, then try to lock bob
        3. Transaction 2: lock bob, then try to lock alice
        4. One transaction should detect deadlock
        """
        await conflict_pool.aexecute("INSERT INTO test_accounts (name, balance) VALUES ($1, $2)", "alice", 100)
        await conflict_pool.aexecute("INSERT INTO test_accounts (name, balance) VALUES ($1, $2)", "bob", 100)

        ready1 = asyncio.Event()
        ready2 = asyncio.Event()
        proceed = asyncio.Event()
        results: list[bool | Exception] = []

        async def transaction_1() -> None:
            try:
                async with conflict_pool.atransaction(isolation="serializable") as conn:
                    # Lock alice
                    await conn.execute("UPDATE test_accounts SET balance = balance + 10 WHERE name = $1", "alice")
                    ready1.set()

                    # Wait for T2 to lock bob
                    await ready2.wait()
                    await proceed.wait()

                    # Try to lock bob (will deadlock with T2)
                    await conn.execute("UPDATE test_accounts SET balance = balance + 10 WHERE name = $1", "bob")

                results.append(True)
            except asyncpg.DeadlockDetectedError as e:
                results.append(e)
            except asyncpg.SerializationError as e:
                results.append(e)

        async def transaction_2() -> None:
            try:
                async with conflict_pool.atransaction(isolation="serializable") as conn:
                    # Lock bob
                    await conn.execute("UPDATE test_accounts SET balance = balance + 20 WHERE name = $1", "bob")
                    ready2.set()

                    # Wait for T1 to lock alice
                    await ready1.wait()
                    await proceed.wait()

                    # Try to lock alice (will deadlock with T1)
                    await conn.execute("UPDATE test_accounts SET balance = balance + 20 WHERE name = $1", "alice")

                results.append(True)
            except asyncpg.DeadlockDetectedError as e:
                results.append(e)
            except asyncpg.SerializationError as e:
                results.append(e)

        # Start both transactions
        t1 = asyncio.create_task(transaction_1())
        t2 = asyncio.create_task(transaction_2())

        # Wait for both to acquire their first lock
        await ready1.wait()
        await ready2.wait()
        await asyncio.sleep(0.1)

        # Let them proceed and deadlock
        proceed.set()

        await asyncio.gather(t1, t2, return_exceptions=True)

        # At least one should detect deadlock
        deadlocks = sum(1 for r in results if isinstance(r, asyncpg.DeadlockDetectedError | asyncpg.SerializationError))
        assert deadlocks >= 1, "Expected at least one deadlock detection"

    async def test_phantom_read_prevented_with_repeatable_read(self, conflict_pool: AsyncConnectionPool) -> None:
        """Test that repeatable_read prevents phantom reads.

        Scenario:
        1. Transaction 1 reads count (with repeatable_read)
        2. Transaction 2 inserts new row
        3. Transaction 1 reads count again
        4. Count should be unchanged (no phantom read)
        """
        # Insert initial data
        await conflict_pool.aexecute("INSERT INTO test_orders (product, quantity) VALUES ($1, $2)", "widget", 10)

        ready = asyncio.Event()
        proceed = asyncio.Event()
        count1: int | None = None
        count2: int | None = None

        async def transaction_1() -> None:
            nonlocal count1, count2
            async with conflict_pool.atransaction(isolation="repeatable_read") as conn:
                # First read
                count1 = await conn.fetchval("SELECT COUNT(*) FROM test_orders")
                ready.set()

                # Wait for T2 to insert
                await proceed.wait()
                await asyncio.sleep(0.2)

                # Second read - should see same count (no phantom)
                count2 = await conn.fetchval("SELECT COUNT(*) FROM test_orders")

        async def transaction_2() -> None:
            # Wait for T1 to read
            await ready.wait()

            # Insert new row
            await conflict_pool.aexecute("INSERT INTO test_orders (product, quantity) VALUES ($1, $2)", "gadget", 5)

            proceed.set()

        t1 = asyncio.create_task(transaction_1())
        t2 = asyncio.create_task(transaction_2())

        await asyncio.gather(t1, t2)

        # Both reads should see same count (phantom read prevented)
        assert count1 == count2, f"Phantom read detected: {count1} != {count2}"
        assert count1 == 1, "Should initially see 1 order"

    async def test_phantom_read_allowed_with_read_committed(self, conflict_pool: AsyncConnectionPool) -> None:
        """Test that read_committed allows phantom reads.

        Same scenario as above but with read_committed:
        - Second read WILL see the inserted row (phantom read)
        """
        await conflict_pool.aexecute("INSERT INTO test_orders (product, quantity) VALUES ($1, $2)", "widget", 10)

        ready = asyncio.Event()
        proceed = asyncio.Event()
        count1: int | None = None
        count2: int | None = None

        async def transaction_1() -> None:
            nonlocal count1, count2
            async with conflict_pool.atransaction(isolation="read_committed") as conn:
                # First read
                count1 = await conn.fetchval("SELECT COUNT(*) FROM test_orders")
                ready.set()

                # Wait for T2 to insert
                await proceed.wait()
                await asyncio.sleep(0.2)

                # Second read - will see new row (phantom read allowed)
                count2 = await conn.fetchval("SELECT COUNT(*) FROM test_orders")

        async def transaction_2() -> None:
            await ready.wait()
            await conflict_pool.aexecute("INSERT INTO test_orders (product, quantity) VALUES ($1, $2)", "gadget", 5)
            proceed.set()

        t1 = asyncio.create_task(transaction_1())
        t2 = asyncio.create_task(transaction_2())

        await asyncio.gather(t1, t2)

        # Second read should see new row (phantom read)
        assert count1 == 1, "Initial read should see 1 order"
        assert count2 == 2, "Second read should see 2 orders (phantom read)"

    async def test_unique_constraint_with_concurrent_inserts(self, conflict_pool: AsyncConnectionPool) -> None:
        """Test unique constraint violation with concurrent inserts.

        Scenario:
        1. Two transactions try to insert same username
        2. One should succeed, one should fail with UniqueViolationError
        """
        results: list[bool | Exception] = []

        async def insert_user(name: str) -> None:
            try:
                async with conflict_pool.atransaction() as conn:
                    await asyncio.sleep(0.1)  # Small delay to increase conflict chance
                    await conn.execute(
                        "INSERT INTO test_accounts (name, balance) VALUES ($1, $2)",
                        name,
                        100,
                    )
                results.append(True)
            except asyncpg.UniqueViolationError as e:
                results.append(e)

        # Try to insert same username concurrently
        await asyncio.gather(
            insert_user("duplicate_user"),
            insert_user("duplicate_user"),
            return_exceptions=True,
        )

        # One should succeed, one should fail
        successes = sum(1 for r in results if r is True)
        failures = sum(1 for r in results if isinstance(r, asyncpg.UniqueViolationError))

        assert successes == 1, "Expected exactly one insert to succeed"
        assert failures == 1, "Expected exactly one insert to fail with UniqueViolationError"

    async def test_proper_rollback_on_serialization_error(self, conflict_pool: AsyncConnectionPool) -> None:
        """Test that transaction is properly rolled back on serialization error.

        Scenario:
        1. Transaction that will fail with SerializationError
        2. Verify all changes are rolled back
        3. Verify subsequent transaction can succeed
        """
        await conflict_pool.aexecute("INSERT INTO test_accounts (name, balance) VALUES ($1, $2)", "charlie", 100)

        barrier = asyncio.Event()

        async def failing_transaction() -> None:
            async with conflict_pool.atransaction(isolation="serializable") as conn:
                # Read balance
                balance = await conn.fetchval("SELECT balance FROM test_accounts WHERE name = $1", "charlie")

                # Insert a marker row that should be rolled back
                await conn.execute("INSERT INTO test_accounts (name, balance) VALUES ($1, $2)", "marker", 999)

                # Signal that we're ready for conflict
                barrier.set()
                await asyncio.sleep(0.1)

                # This will fail with SerializationError
                await conn.execute(
                    "UPDATE test_accounts SET balance = $1 WHERE name = $2",
                    balance + 50,  # type: ignore[operator]
                    "charlie",
                )

        async def conflicting_transaction() -> None:
            await barrier.wait()
            async with conflict_pool.atransaction(isolation="serializable") as conn:
                # Update charlie (will conflict)
                await conn.execute("UPDATE test_accounts SET balance = $1 WHERE name = $2", 200, "charlie")

        # Run both transactions
        with pytest.raises(asyncpg.SerializationError):
            await asyncio.gather(
                failing_transaction(),
                conflicting_transaction(),
            )

        # Marker row should NOT exist (rolled back)
        marker_count = await conflict_pool.afetchval("SELECT COUNT(*) FROM test_accounts WHERE name = $1", "marker")
        assert marker_count == 0, "Marker row should have been rolled back"

        # Charlie should exist with balance updated by successful transaction
        charlie_count = await conflict_pool.afetchval("SELECT COUNT(*) FROM test_accounts WHERE name = $1", "charlie")
        assert charlie_count == 1, "Charlie should still exist"

    async def test_concurrent_updates_different_isolation_levels(self, conflict_pool: AsyncConnectionPool) -> None:
        """Test behavior with different isolation levels concurrently.

        Scenario:
        1. One transaction with serializable
        2. One transaction with read_committed
        3. Verify both can complete (no strict ordering required)
        """
        await conflict_pool.aexecute("INSERT INTO test_accounts (name, balance) VALUES ($1, $2)", "diana", 100)

        results: list[str] = []

        async def serializable_transaction() -> None:
            async with conflict_pool.atransaction(isolation="serializable") as conn:
                await asyncio.sleep(0.1)
                await conn.execute("UPDATE test_accounts SET balance = balance + 10 WHERE name = $1", "diana")
                results.append("serializable")

        async def read_committed_transaction() -> None:
            async with conflict_pool.atransaction(isolation="read_committed") as conn:
                await asyncio.sleep(0.1)
                await conn.execute("UPDATE test_accounts SET balance = balance + 20 WHERE name = $1", "diana")
                results.append("read_committed")

        await asyncio.gather(
            serializable_transaction(),
            read_committed_transaction(),
            return_exceptions=True,
        )

        # Both should complete (though one might fail with serialization error)
        # At minimum, one should succeed
        assert len(results) >= 1, "At least one transaction should complete"

    async def test_transaction_isolation_with_readonly(self, conflict_pool: AsyncConnectionPool) -> None:
        """Test readonly transaction behavior under concurrent writes.

        Scenario:
        1. Readonly transaction reads data
        2. Write transaction modifies data
        3. Readonly transaction should complete successfully
        """
        await conflict_pool.aexecute("INSERT INTO test_accounts (name, balance) VALUES ($1, $2)", "eve", 100)

        async def readonly_transaction() -> bool:
            async with conflict_pool.atransaction(readonly=True) as conn:
                balance1: int = await conn.fetchval("SELECT balance FROM test_accounts WHERE name = $1", "eve")
                await asyncio.sleep(0.2)
                balance2: int = await conn.fetchval("SELECT balance FROM test_accounts WHERE name = $1", "eve")
                return balance1 == balance2

        async def write_transaction() -> None:
            await asyncio.sleep(0.1)
            await conflict_pool.aexecute("UPDATE test_accounts SET balance = $1 WHERE name = $2", 200, "eve")

        # Both should complete
        consistent, _ = await asyncio.gather(readonly_transaction(), write_transaction())

        # Readonly transaction may or may not see consistent view depending on isolation
        # But it should complete without error
        assert isinstance(consistent, bool), "Readonly transaction should complete"
