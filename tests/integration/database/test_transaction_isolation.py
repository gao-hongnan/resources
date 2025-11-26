"""Transaction isolation and boundary tests.

Tests transaction management, isolation levels, and concurrent access patterns
to ensure data consistency and proper transaction boundaries.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

from pixiu.database import AsyncConnectionPool

if TYPE_CHECKING:
    from asyncpg import Record


@pytest.mark.integration
@pytest.mark.database
class TestTransactionIsolation:
    """Tests for transaction isolation levels and boundaries."""

    @pytest.fixture(autouse=True)
    async def _cleanup_test_data(self, connection_pool: AsyncConnectionPool) -> None:
        """Clean up test data before each test."""
        async with connection_pool.aacquire() as conn:
            await conn.execute("TRUNCATE TABLE test_users RESTART IDENTITY CASCADE")

    async def test_transaction_commit_persists_changes(self, connection_pool: AsyncConnectionPool) -> None:
        """Test that committed transaction persists changes."""
        async with connection_pool.atransaction() as conn:
            await conn.execute(
                "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                "alice",
                "alice@example.com",
                30,
            )

        result: Record | None = await connection_pool.afetchrow("SELECT * FROM test_users WHERE username = $1", "alice")

        assert result is not None
        assert result["username"] == "alice"

    async def test_transaction_rollback_discards_changes(self, connection_pool: AsyncConnectionPool) -> None:
        """Test that rolled back transaction discards changes."""

        async def transaction_with_error() -> None:
            async with connection_pool.atransaction() as conn:
                await conn.execute(
                    "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                    "bob",
                    "bob@example.com",
                    25,
                )
                raise ValueError("Intentional error to trigger rollback")

        with pytest.raises(ValueError, match="Intentional error"):
            await transaction_with_error()

        result: Record | None = await connection_pool.afetchrow("SELECT * FROM test_users WHERE username = $1", "bob")

        assert result is None

    async def test_read_committed_isolation_level(self, connection_pool: AsyncConnectionPool) -> None:
        """Test read_committed isolation level behavior."""
        await connection_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        async with connection_pool.atransaction(isolation="read_committed") as conn1:
            await conn1.execute("UPDATE test_users SET age = $1 WHERE username = $2", 35, "alice")

            async with connection_pool.aacquire() as conn2:
                result: Record | None = await conn2.fetchrow("SELECT age FROM test_users WHERE username = $1", "alice")
                assert result is not None
                assert result["age"] == 30

        result_after: Record | None = await connection_pool.afetchrow(
            "SELECT age FROM test_users WHERE username = $1", "alice"
        )
        assert result_after is not None
        assert result_after["age"] == 35

    async def test_serializable_isolation_level(self, connection_pool: AsyncConnectionPool) -> None:
        """Test serializable isolation level prevents concurrent modifications."""
        await connection_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        async with connection_pool.atransaction(isolation="serializable") as conn:
            result: Record | None = await conn.fetchrow("SELECT age FROM test_users WHERE username = $1", "alice")
            assert result is not None
            original_age = result["age"]

            await conn.execute("UPDATE test_users SET age = $1 WHERE username = $2", original_age + 5, "alice")

        result_after: Record | None = await connection_pool.afetchrow(
            "SELECT age FROM test_users WHERE username = $1", "alice"
        )
        assert result_after is not None
        assert result_after["age"] == 35

    async def test_readonly_transaction_prevents_writes(self, connection_pool: AsyncConnectionPool) -> None:
        """Test that readonly transaction prevents write operations."""
        import asyncpg

        await connection_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        with pytest.raises(asyncpg.ReadOnlySQLTransactionError):
            async with connection_pool.atransaction(readonly=True) as conn:
                await conn.execute("UPDATE test_users SET age = $1 WHERE username = $2", 35, "alice")

    async def test_nested_transaction_context_managers(self, connection_pool: AsyncConnectionPool) -> None:
        """Test proper handling of transaction context managers."""
        async with connection_pool.atransaction() as conn1:
            await conn1.execute(
                "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                "alice",
                "alice@example.com",
                30,
            )

        async with connection_pool.atransaction() as conn2:
            await conn2.execute(
                "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                "bob",
                "bob@example.com",
                25,
            )

        count: Any = await connection_pool.afetchval("SELECT COUNT(*) FROM test_users")
        assert count == 2

    async def test_concurrent_reads_same_data(self, connection_pool: AsyncConnectionPool) -> None:
        """Test that multiple concurrent reads can access the same data."""
        await connection_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        async def read_user() -> Record | None:
            async with connection_pool.aacquire() as conn:
                return await conn.fetchrow("SELECT * FROM test_users WHERE username = $1", "alice")

        results = await asyncio.gather(*[read_user() for _ in range(10)])

        assert len(results) == 10
        assert all(r is not None and r["username"] == "alice" for r in results)

    async def test_transaction_isolation_repeatable_read(self, connection_pool: AsyncConnectionPool) -> None:
        """Test repeatable_read isolation level maintains consistent view."""
        await connection_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        async with connection_pool.atransaction(isolation="repeatable_read") as conn1:
            first_read: Record | None = await conn1.fetchrow("SELECT age FROM test_users WHERE username = $1", "alice")
            assert first_read is not None
            assert first_read["age"] == 30

            async with connection_pool.aacquire() as conn2:
                await conn2.execute("UPDATE test_users SET age = $1 WHERE username = $2", 35, "alice")

            second_read: Record | None = await conn1.fetchrow("SELECT age FROM test_users WHERE username = $1", "alice")
            assert second_read is not None
            assert second_read["age"] == 30

    async def test_transaction_deferrable_constraint(self, connection_pool: AsyncConnectionPool) -> None:
        """Test deferrable transaction option."""
        async with connection_pool.atransaction(deferrable=True) as conn:
            await conn.execute(
                "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                "alice",
                "alice@example.com",
                30,
            )

        result: Record | None = await connection_pool.afetchrow("SELECT * FROM test_users WHERE username = $1", "alice")

        assert result is not None
        assert result["username"] == "alice"

    async def test_multiple_operations_in_single_transaction(self, connection_pool: AsyncConnectionPool) -> None:
        """Test multiple database operations within a single transaction."""
        async with connection_pool.atransaction() as conn:
            await conn.execute(
                "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                "alice",
                "alice@example.com",
                30,
            )

            await conn.execute(
                "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                "bob",
                "bob@example.com",
                25,
            )

            await conn.execute("UPDATE test_users SET age = $1 WHERE username = $2", 35, "alice")

            alice: Record | None = await conn.fetchrow("SELECT age FROM test_users WHERE username = $1", "alice")
            assert alice is not None
            assert alice["age"] == 35

        count: Any = await connection_pool.afetchval("SELECT COUNT(*) FROM test_users")
        assert count == 2

        alice_final: Record | None = await connection_pool.afetchrow(
            "SELECT age FROM test_users WHERE username = $1", "alice"
        )
        assert alice_final is not None
        assert alice_final["age"] == 35
