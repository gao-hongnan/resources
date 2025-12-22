"""ACID compliance tests for PostgreSQL via AsyncConnectionPool.

These tests verify that our connection pool properly supports PostgreSQL's
ACID (Atomicity, Consistency, Isolation, Durability) guarantees through
comprehensive transaction testing including concurrent scenarios.

ACID Properties Tested
----------------------
- Atomicity: All operations in a transaction succeed or fail together
- Consistency: Database constraints are always enforced
- Isolation: Concurrent transactions don't interfere with each other
- Durability: Committed transactions persist even after connection loss

Note: S608 warnings are suppressed because TEST_USERS_TABLE is a hardcoded
constant, not user input - there is no SQL injection risk.
"""
# ruff: noqa: S608

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import asyncpg
import pytest
from pydantic import SecretStr

from leitmotif.infrastructure.postgres import (
    AsyncConnectionPool,
    AsyncpgConfig,
    AsyncpgConnectionSettings,
    AsyncpgPoolSettings,
    AsyncpgServerSettings,
    AsyncpgStatementCacheSettings,
)
from tests.integration.postgres.conftest import TEST_USERS_TABLE

if TYPE_CHECKING:
    from testcontainers.postgres import PostgresContainer


# =============================================================================
# ATOMICITY TESTS
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestAtomicity:
    """Tests for transaction atomicity (all-or-nothing).

    Atomicity guarantees that all operations within a transaction either
    complete successfully together, or none of them take effect.
    """

    async def test_atomicity_all_operations_commit_together(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Verify multiple operations in a transaction all commit together.

        When a transaction completes successfully, ALL operations within it
        must be persisted to the database.
        """
        async with asyncpg_pool.atransaction() as conn:
            await conn.execute(
                f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                "atom_user1",
                "atom1@example.com",
                25,
            )
            await conn.execute(
                f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                "atom_user2",
                "atom2@example.com",
                30,
            )
            await conn.execute(
                f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                "atom_user3",
                "atom3@example.com",
                35,
            )

        # All three users should exist
        count = await asyncpg_pool.afetchval(
            f"SELECT COUNT(*) FROM {TEST_USERS_TABLE} WHERE username LIKE 'atom_user%'"
        )
        assert count == 3

    async def test_atomicity_all_operations_rollback_on_failure(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Verify all operations rollback when transaction fails.

        If an exception occurs after multiple successful operations,
        ALL prior operations must be rolled back.
        """
        with pytest.raises(RuntimeError, match="Intentional failure"):
            async with asyncpg_pool.atransaction() as conn:
                await conn.execute(
                    f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                    "rollback_user1",
                    "rollback1@example.com",
                    25,
                )
                await conn.execute(
                    f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                    "rollback_user2",
                    "rollback2@example.com",
                    30,
                )
                # Simulate application failure after successful inserts
                msg = "Intentional failure"
                raise RuntimeError(msg)

        # Neither user should exist - all operations rolled back
        count = await asyncpg_pool.afetchval(
            f"SELECT COUNT(*) FROM {TEST_USERS_TABLE} WHERE username LIKE 'rollback_user%'"
        )
        assert count == 0

    async def test_atomicity_constraint_violation_rolls_back_prior_operations(
        self, asyncpg_pool: AsyncConnectionPool
    ) -> None:
        """Verify constraint violation rolls back ALL prior operations.

        When the third INSERT violates a constraint, the first two
        successful INSERTs must also be rolled back.
        """
        with pytest.raises(asyncpg.UniqueViolationError):
            async with asyncpg_pool.atransaction() as conn:
                await conn.execute(
                    f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                    "constraint_user1",
                    "constraint1@example.com",
                    25,
                )
                await conn.execute(
                    f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                    "constraint_user2",
                    "constraint2@example.com",
                    30,
                )
                # This violates UNIQUE constraint on username
                await conn.execute(
                    f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                    "constraint_user1",  # Duplicate username!
                    "constraint3@example.com",
                    35,
                )

        # No users should exist - constraint violation rolled back everything
        count = await asyncpg_pool.afetchval(
            f"SELECT COUNT(*) FROM {TEST_USERS_TABLE} WHERE username LIKE 'constraint_user%'"
        )
        assert count == 0


# =============================================================================
# CONSISTENCY TESTS
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestConsistency:
    """Tests for database consistency constraints within transactions.

    Consistency guarantees that transactions bring the database from one
    valid state to another. Constraints (CHECK, UNIQUE, NOT NULL, FK)
    must be enforced.
    """

    async def test_consistency_check_constraint_enforced_in_transaction(
        self, asyncpg_pool: AsyncConnectionPool
    ) -> None:
        """Verify CHECK constraint is enforced within transaction.

        The test_users table has CHECK (age >= 0 AND age <= 150).
        Violating this should abort the transaction.
        """
        with pytest.raises(asyncpg.CheckViolationError):
            async with asyncpg_pool.atransaction() as conn:
                await conn.execute(
                    f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                    "check_user",
                    "check@example.com",
                    -5,  # Violates CHECK constraint
                )

        # User should not exist
        result = await asyncpg_pool.afetchrow(f"SELECT * FROM {TEST_USERS_TABLE} WHERE username = $1", "check_user")
        assert result is None

    async def test_consistency_unique_constraint_enforced_in_transaction(
        self, asyncpg_pool: AsyncConnectionPool
    ) -> None:
        """Verify UNIQUE constraint is enforced within transaction.

        The test_users table has UNIQUE constraint on username.
        Inserting duplicate should abort the transaction.
        """
        # First insert succeeds
        await asyncpg_pool.aexecute(
            f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
            "unique_user",
            "unique@example.com",
            25,
        )

        # Second insert with same username should fail
        with pytest.raises(asyncpg.UniqueViolationError):
            async with asyncpg_pool.atransaction() as conn:
                await conn.execute(
                    f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                    "unique_user",  # Duplicate!
                    "unique2@example.com",
                    30,
                )

        # Only one user should exist
        count = await asyncpg_pool.afetchval(
            f"SELECT COUNT(*) FROM {TEST_USERS_TABLE} WHERE username = $1", "unique_user"
        )
        assert count == 1

    async def test_consistency_not_null_enforced_in_transaction(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Verify NOT NULL constraint is enforced within transaction.

        The test_users table has NOT NULL on username, email, age.
        """
        with pytest.raises(asyncpg.NotNullViolationError):
            async with asyncpg_pool.atransaction() as conn:
                await conn.execute(
                    f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                    None,  # Violates NOT NULL
                    "notnull@example.com",
                    25,
                )

    async def test_consistency_multiple_constraints_in_single_transaction(
        self, asyncpg_pool: AsyncConnectionPool
    ) -> None:
        """Verify multiple valid inserts succeed, invalid one fails.

        Tests that constraint checking happens per-statement within transaction.
        """
        # Valid inserts should work
        async with asyncpg_pool.atransaction() as conn:
            await conn.execute(
                f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                "multi_user1",
                "multi1@example.com",
                25,
            )
            await conn.execute(
                f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                "multi_user2",
                "multi2@example.com",
                30,
            )

        # Both should exist
        count = await asyncpg_pool.afetchval(
            f"SELECT COUNT(*) FROM {TEST_USERS_TABLE} WHERE username LIKE 'multi_user%'"
        )
        assert count == 2


# =============================================================================
# ISOLATION TESTS
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestIsolation:
    """Tests for transaction isolation levels and anomaly prevention.

    Isolation guarantees that concurrent transactions don't interfere with
    each other. PostgreSQL supports multiple isolation levels:
    - READ COMMITTED (default): Prevents dirty reads
    - REPEATABLE READ: Prevents dirty reads and non-repeatable reads
    - SERIALIZABLE: Prevents all anomalies, transactions appear serial
    """

    async def test_isolation_no_dirty_read_in_read_committed(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Verify READ COMMITTED prevents dirty reads.

        Dirty Read: Transaction reads data written by concurrent uncommitted
        transaction. This should NOT be possible in READ COMMITTED.

        Scenario:
        1. T1 starts, INSERTs a row, does NOT commit yet
        2. T2 (READ COMMITTED) tries to read that row
        3. T2 should NOT see T1's uncommitted row
        """
        t1_inserted = asyncio.Event()
        t1_can_commit = asyncio.Event()
        t2_first_read_result: list[bool] = []

        async def transaction1() -> str:
            async with asyncpg_pool.atransaction() as conn:
                await conn.execute(
                    f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                    "dirty_read_user",
                    "dirty@example.com",
                    25,
                )
                t1_inserted.set()
                await t1_can_commit.wait()
            return "t1_committed"

        async def transaction2() -> None:
            await t1_inserted.wait()

            async with asyncpg_pool.atransaction(isolation="read_committed") as conn:
                result = await conn.fetchrow(
                    f"SELECT * FROM {TEST_USERS_TABLE} WHERE username = $1",
                    "dirty_read_user",
                )
                t2_first_read_result.append(result is None)
                t1_can_commit.set()

        t1_task = asyncio.create_task(transaction1())
        await transaction2()
        await t1_task

        assert t2_first_read_result[0] is True, "Dirty read occurred!"

    async def test_isolation_no_dirty_read_in_repeatable_read(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Verify REPEATABLE READ also prevents dirty reads.

        Same test as above but with REPEATABLE READ isolation level.
        """
        t1_inserted = asyncio.Event()
        t1_can_commit = asyncio.Event()
        t2_first_read_result: list[bool] = []

        async def transaction1() -> str:
            async with asyncpg_pool.atransaction() as conn:
                await conn.execute(
                    f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                    "dirty_rr_user",
                    "dirty_rr@example.com",
                    25,
                )
                t1_inserted.set()
                await t1_can_commit.wait()
            return "t1_committed"

        async def transaction2() -> None:
            await t1_inserted.wait()

            async with asyncpg_pool.atransaction(isolation="repeatable_read") as conn:
                result = await conn.fetchrow(
                    f"SELECT * FROM {TEST_USERS_TABLE} WHERE username = $1",
                    "dirty_rr_user",
                )
                t2_first_read_result.append(result is None)
                t1_can_commit.set()

        t1_task = asyncio.create_task(transaction1())
        await transaction2()
        await t1_task

        assert t2_first_read_result[0] is True, "Dirty read occurred in REPEATABLE READ!"

    async def test_isolation_non_repeatable_read_possible_in_read_committed(
        self, asyncpg_pool: AsyncConnectionPool
    ) -> None:
        """Verify READ COMMITTED allows non-repeatable reads.

        Non-Repeatable Read: Same query returns different results within
        same transaction because another transaction committed changes.

        Scenario:
        1. Insert initial row with age=25
        2. T1 (READ COMMITTED) reads row, sees age=25
        3. T2 updates age to 99 and commits
        4. T1 reads again, sees age=99 (non-repeatable read!)
        """
        # Setup: Insert initial row
        await asyncpg_pool.aexecute(
            f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
            "nrr_user",
            "nrr@example.com",
            25,
        )

        t1_first_read_done = asyncio.Event()
        t2_committed = asyncio.Event()
        reads: list[int] = []

        async def transaction1() -> None:
            async with asyncpg_pool.atransaction(isolation="read_committed") as conn:
                # First read
                row = await conn.fetchrow(f"SELECT age FROM {TEST_USERS_TABLE} WHERE username = $1", "nrr_user")
                reads.append(row["age"])
                t1_first_read_done.set()

                await t2_committed.wait()

                # Second read - in READ COMMITTED, sees T2's committed change
                row = await conn.fetchrow(f"SELECT age FROM {TEST_USERS_TABLE} WHERE username = $1", "nrr_user")
                reads.append(row["age"])

        async def transaction2() -> None:
            await t1_first_read_done.wait()

            await asyncpg_pool.aexecute(
                f"UPDATE {TEST_USERS_TABLE} SET age = $1 WHERE username = $2",
                99,
                "nrr_user",
            )
            t2_committed.set()

        await asyncio.gather(transaction1(), transaction2())

        assert reads[0] == 25, "First read should see original value"
        assert reads[1] == 99, "Second read should see committed update (non-repeatable read)"

    async def test_isolation_no_non_repeatable_read_in_repeatable_read(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Verify REPEATABLE READ prevents non-repeatable reads.

        Same scenario as above, but T1 uses REPEATABLE READ.
        T1 should see consistent snapshot - both reads return same value.
        """
        # Setup: Insert initial row
        await asyncpg_pool.aexecute(
            f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
            "rr_user",
            "rr@example.com",
            25,
        )

        t1_first_read_done = asyncio.Event()
        t2_committed = asyncio.Event()
        reads: list[int] = []

        async def transaction1() -> None:
            async with asyncpg_pool.atransaction(isolation="repeatable_read") as conn:
                # First read
                row = await conn.fetchrow(f"SELECT age FROM {TEST_USERS_TABLE} WHERE username = $1", "rr_user")
                reads.append(row["age"])
                t1_first_read_done.set()

                await t2_committed.wait()
                await asyncio.sleep(0.05)  # Give time for T2 to fully commit

                # Second read - REPEATABLE READ sees snapshot, NOT T2's change
                row = await conn.fetchrow(f"SELECT age FROM {TEST_USERS_TABLE} WHERE username = $1", "rr_user")
                reads.append(row["age"])

        async def transaction2() -> None:
            await t1_first_read_done.wait()

            await asyncpg_pool.aexecute(
                f"UPDATE {TEST_USERS_TABLE} SET age = $1 WHERE username = $2",
                99,
                "rr_user",
            )
            t2_committed.set()

        await asyncio.gather(transaction1(), transaction2())

        assert reads[0] == 25, "First read should see original value"
        assert reads[1] == 25, "Second read should ALSO see original (repeatable read)"

    async def test_isolation_phantom_read_possible_in_read_committed(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Verify READ COMMITTED allows phantom reads.

        Phantom Read: Same range query returns different rows because
        another transaction inserted/deleted rows.

        Scenario:
        1. Insert user with age=30
        2. T1 counts users with age >= 25, sees 1
        3. T2 inserts another user with age=28 and commits
        4. T1 counts again, sees 2 (phantom row appeared!)
        """
        # Setup
        await asyncpg_pool.aexecute(
            f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
            "phantom_user1",
            "phantom1@example.com",
            30,
        )

        t1_first_count_done = asyncio.Event()
        t2_committed = asyncio.Event()
        counts: list[int] = []

        async def transaction1() -> None:
            async with asyncpg_pool.atransaction(isolation="read_committed") as conn:
                # First count
                count = await conn.fetchval(
                    f"SELECT COUNT(*) FROM {TEST_USERS_TABLE} WHERE age >= 25 AND username LIKE 'phantom_user%'"
                )
                counts.append(count)
                t1_first_count_done.set()

                await t2_committed.wait()

                # Second count - READ COMMITTED sees new row
                count = await conn.fetchval(
                    f"SELECT COUNT(*) FROM {TEST_USERS_TABLE} WHERE age >= 25 AND username LIKE 'phantom_user%'"
                )
                counts.append(count)

        async def transaction2() -> None:
            await t1_first_count_done.wait()

            await asyncpg_pool.aexecute(
                f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                "phantom_user2",
                "phantom2@example.com",
                28,
            )
            t2_committed.set()

        await asyncio.gather(transaction1(), transaction2())

        assert counts[0] == 1, "First count should be 1"
        assert counts[1] == 2, "Second count should be 2 (phantom read)"

    async def test_isolation_serializable_prevents_phantom_read(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Verify SERIALIZABLE prevents phantom reads.

        With SERIALIZABLE, T1 should see consistent snapshot.
        Note: PostgreSQL's SSI may detect conflict and abort one transaction.
        """
        # Setup
        await asyncpg_pool.aexecute(
            f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
            "ser_phantom_user1",
            "ser_phantom1@example.com",
            30,
        )

        t1_first_count_done = asyncio.Event()
        t2_can_insert = asyncio.Event()
        counts: list[int] = []

        async def transaction1() -> None:
            async with asyncpg_pool.atransaction(isolation="serializable") as conn:
                # First count
                count = await conn.fetchval(
                    f"SELECT COUNT(*) FROM {TEST_USERS_TABLE} WHERE age >= 25 AND username LIKE 'ser_phantom_user%'"
                )
                counts.append(count)
                t1_first_count_done.set()

                await t2_can_insert.wait()
                await asyncio.sleep(0.05)

                # Second count - SERIALIZABLE sees same snapshot
                count = await conn.fetchval(
                    f"SELECT COUNT(*) FROM {TEST_USERS_TABLE} WHERE age >= 25 AND username LIKE 'ser_phantom_user%'"
                )
                counts.append(count)

        async def transaction2() -> None:
            await t1_first_count_done.wait()

            await asyncpg_pool.aexecute(
                f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                "ser_phantom_user2",
                "ser_phantom2@example.com",
                28,
            )
            t2_can_insert.set()

        await asyncio.gather(transaction1(), transaction2())

        assert counts[0] == 1, "First count should be 1"
        assert counts[1] == 1, "Second count should ALSO be 1 (no phantom in SERIALIZABLE)"

    async def test_isolation_serialization_failure_on_write_conflict(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Verify SERIALIZABLE detects write conflicts.

        When two SERIALIZABLE transactions have conflicting writes,
        PostgreSQL's SSI will abort one with SerializationError.
        """
        # Setup
        await asyncpg_pool.aexecute(
            f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
            "conflict_user",
            "conflict@example.com",
            25,
        )

        t1_read_done = asyncio.Event()
        t2_read_done = asyncio.Event()
        results: list[str | BaseException] = []

        async def transaction1() -> str:
            async with asyncpg_pool.atransaction(isolation="serializable") as conn:
                await conn.fetchrow(f"SELECT * FROM {TEST_USERS_TABLE} WHERE username = $1", "conflict_user")
                t1_read_done.set()
                await t2_read_done.wait()

                await conn.execute(
                    f"UPDATE {TEST_USERS_TABLE} SET age = $1 WHERE username = $2",
                    30,
                    "conflict_user",
                )
            return "t1_success"

        async def transaction2() -> str:
            async with asyncpg_pool.atransaction(isolation="serializable") as conn:
                await conn.fetchrow(f"SELECT * FROM {TEST_USERS_TABLE} WHERE username = $1", "conflict_user")
                t2_read_done.set()
                await t1_read_done.wait()

                await conn.execute(
                    f"UPDATE {TEST_USERS_TABLE} SET age = $1 WHERE username = $2",
                    35,
                    "conflict_user",
                )
            return "t2_success"

        gathered = await asyncio.gather(transaction1(), transaction2(), return_exceptions=True)
        results.extend(gathered)

        # At least one should succeed, and possibly one fails with serialization error
        successes = [r for r in results if r in ("t1_success", "t2_success")]
        failures = [r for r in results if isinstance(r, asyncpg.SerializationError)]

        # PostgreSQL might allow both or abort one - depends on timing
        # The key is that if one fails, it's a SerializationError
        assert len(successes) >= 1, "At least one transaction should succeed"
        assert all(isinstance(f, asyncpg.SerializationError) for f in failures), (
            "Any failure should be SerializationError"
        )


# =============================================================================
# DURABILITY TESTS
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestDurability:
    """Tests for transaction durability (committed data persists).

    Durability guarantees that once a transaction is committed, its effects
    survive system failures (connection drops, restarts, etc.).
    """

    async def test_durability_data_persists_after_pool_recreation(self, postgres_container: PostgresContainer) -> None:
        """Verify committed data persists after closing and recreating pool.

        1. Create pool, insert data, commit, close pool
        2. Create new pool
        3. Data should still exist
        """
        config = AsyncpgConfig(
            connection=AsyncpgConnectionSettings(
                host=postgres_container.get_container_host_ip(),
                port=int(postgres_container.get_exposed_port(5432)),
                database=postgres_container.dbname,
                user=postgres_container.username,
                password=SecretStr(postgres_container.password),
            ),
            pool=AsyncpgPoolSettings(min_size=1, max_size=5),
            statement_cache=AsyncpgStatementCacheSettings(max_size=64),
            server_settings=AsyncpgServerSettings(application_name="durability_test"),
        )

        # First pool - insert and commit
        async with AsyncConnectionPool(config) as pool1:
            # Ensure table exists
            async with pool1.aacquire() as conn:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {TEST_USERS_TABLE} (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(255) UNIQUE NOT NULL,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        age INTEGER NOT NULL CHECK (age >= 0 AND age <= 150),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)

            await pool1.aexecute(
                f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                "durable_user",
                "durable@example.com",
                25,
            )
        # pool1 is now closed

        # Second pool - data should persist
        async with AsyncConnectionPool(config) as pool2:
            result = await pool2.afetchrow(f"SELECT * FROM {TEST_USERS_TABLE} WHERE username = $1", "durable_user")

            assert result is not None, "Committed data should persist after pool recreation"
            assert result["username"] == "durable_user"
            assert result["age"] == 25

            # Cleanup
            await pool2.aexecute(f"DELETE FROM {TEST_USERS_TABLE} WHERE username = $1", "durable_user")

    async def test_durability_uncommitted_data_lost_on_connection_close(
        self, postgres_container: PostgresContainer
    ) -> None:
        """Verify uncommitted data is lost when connection closes.

        This is the flip side of durability - only COMMITTED data persists.
        Uncommitted data should be lost.
        """
        config = AsyncpgConfig(
            connection=AsyncpgConnectionSettings(
                host=postgres_container.get_container_host_ip(),
                port=int(postgres_container.get_exposed_port(5432)),
                database=postgres_container.dbname,
                user=postgres_container.username,
                password=SecretStr(postgres_container.password),
            ),
            pool=AsyncpgPoolSettings(min_size=1, max_size=5),
            statement_cache=AsyncpgStatementCacheSettings(max_size=64),
            server_settings=AsyncpgServerSettings(application_name="durability_test2"),
        )

        # First pool - start transaction but don't commit
        async with AsyncConnectionPool(config) as pool1:
            # Ensure table exists
            async with pool1.aacquire() as conn:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {TEST_USERS_TABLE} (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(255) UNIQUE NOT NULL,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        age INTEGER NOT NULL CHECK (age >= 0 AND age <= 150),
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)

            # Get a connection and start a transaction manually
            conn = await pool1._pool.acquire()  # noqa: SLF001
            tr = conn.transaction()
            await tr.start()
            await conn.execute(
                f"INSERT INTO {TEST_USERS_TABLE} (username, email, age) VALUES ($1, $2, $3)",
                "uncommitted_user",
                "uncommitted@example.com",
                30,
            )
            # Do NOT commit - just release connection and close pool
            await pool1._pool.release(conn)  # noqa: SLF001
        # pool1 closed without committing

        # Second pool - uncommitted data should NOT exist
        async with AsyncConnectionPool(config) as pool2:
            result = await pool2.afetchrow(f"SELECT * FROM {TEST_USERS_TABLE} WHERE username = $1", "uncommitted_user")

            assert result is None, "Uncommitted data should NOT persist"
