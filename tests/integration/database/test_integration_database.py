"""Integration tests for database operations using real PostgreSQL via TestContainers.

Tests actual database operations including CRUD, batch operations, and error handling
with a real PostgreSQL instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pixiu.database import AsyncConnectionPool
from pixiu.database.models import HealthCheckStatus

if TYPE_CHECKING:
    from asyncpg import Record


@pytest.mark.integration
class TestDatabaseIntegration:
    """Integration tests with real PostgreSQL database."""

    @pytest.fixture(autouse=True)
    async def _cleanup_test_data(self, connection_pool: AsyncConnectionPool) -> None:
        """Clean up test data before each test."""
        async with connection_pool.aacquire() as conn:
            await conn.execute("TRUNCATE TABLE test_users RESTART IDENTITY CASCADE")

    async def test_insert_and_fetch_user(self, connection_pool: AsyncConnectionPool) -> None:
        """Test inserting and fetching user records."""
        await connection_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        result: list[Record] = await connection_pool.afetch("SELECT * FROM test_users WHERE username = $1", "alice")

        assert len(result) == 1
        user = result[0]
        assert user["username"] == "alice"
        assert user["email"] == "alice@example.com"
        assert user["age"] == 30

    async def test_fetchrow_returns_single_user(self, connection_pool: AsyncConnectionPool) -> None:
        """Test fetchrow returns a single user record."""
        await connection_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "bob",
            "bob@example.com",
            25,
        )

        result: Record | None = await connection_pool.afetchrow("SELECT * FROM test_users WHERE username = $1", "bob")

        assert result is not None
        assert result["username"] == "bob"
        assert result["email"] == "bob@example.com"
        assert result["age"] == 25

    async def test_fetchrow_returns_none_for_nonexistent_user(self, connection_pool: AsyncConnectionPool) -> None:
        """Test fetchrow returns None when no record matches."""
        result: Record | None = await connection_pool.afetchrow(
            "SELECT * FROM test_users WHERE username = $1", "nonexistent"
        )

        assert result is None

    async def test_fetchval_returns_count(self, connection_pool: AsyncConnectionPool) -> None:
        """Test fetchval returns scalar count value."""
        await connection_pool.aexecutemany(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            [
                ("user1", "user1@example.com", 20),
                ("user2", "user2@example.com", 30),
                ("user3", "user3@example.com", 40),
            ],
        )

        count: Any = await connection_pool.afetchval("SELECT COUNT(*) FROM test_users")

        assert count == 3

    async def test_executemany_bulk_insert(self, connection_pool: AsyncConnectionPool) -> None:
        """Test bulk insert with executemany."""
        batch_data: list[tuple[Any, ...]] = [
            ("alice", "alice@example.com", 25),
            ("bob", "bob@example.com", 30),
            ("charlie", "charlie@example.com", 35),
            ("diana", "diana@example.com", 40),
            ("eve", "eve@example.com", 45),
        ]

        await connection_pool.aexecutemany(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            batch_data,
        )

        count: Any = await connection_pool.afetchval("SELECT COUNT(*) FROM test_users")
        assert count == 5

        users: list[Record] = await connection_pool.afetch("SELECT username, age FROM test_users ORDER BY age")
        assert len(users) == 5
        assert users[0]["username"] == "alice"
        assert users[0]["age"] == 25
        assert users[-1]["username"] == "eve"
        assert users[-1]["age"] == 45

    async def test_update_operation(self, connection_pool: AsyncConnectionPool) -> None:
        """Test update operation modifies existing record."""
        await connection_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        await connection_pool.aexecute(
            "UPDATE test_users SET age = $1 WHERE username = $2",
            35,
            "alice",
        )

        result: Record | None = await connection_pool.afetchrow(
            "SELECT age FROM test_users WHERE username = $1", "alice"
        )

        assert result is not None
        assert result["age"] == 35

    async def test_delete_operation(self, connection_pool: AsyncConnectionPool) -> None:
        """Test delete operation removes record."""
        await connection_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        await connection_pool.aexecute("DELETE FROM test_users WHERE username = $1", "alice")

        result: Record | None = await connection_pool.afetchrow("SELECT * FROM test_users WHERE username = $1", "alice")

        assert result is None

    async def test_unique_constraint_violation(self, connection_pool: AsyncConnectionPool) -> None:
        """Test unique constraint violation raises exception."""
        import asyncpg

        await connection_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        with pytest.raises(asyncpg.UniqueViolationError):
            await connection_pool.aexecute(
                "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                "alice",
                "alice2@example.com",
                25,
            )

    async def test_connection_pool_health_check(self, connection_pool: AsyncConnectionPool) -> None:
        """Test connection pool health check returns healthy status."""
        result = await connection_pool.ahealth_check()

        assert result.status == HealthCheckStatus.HEALTHY
        assert result.pool_initialized
        assert result.pool_size is not None
        assert result.pool_max_size is not None
        assert result.pool_size >= 2
        assert result.pool_max_size == 5

    async def test_query_with_timeout(self, connection_pool: AsyncConnectionPool) -> None:
        """Test query execution with timeout parameter."""
        await connection_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
            timeout=5.0,
        )

        result: list[Record] = await connection_pool.afetch(
            "SELECT * FROM test_users WHERE username = $1", "alice", timeout=5.0
        )

        assert len(result) == 1
        assert result[0]["username"] == "alice"

    async def test_fetch_with_multiple_conditions(self, connection_pool: AsyncConnectionPool) -> None:
        """Test fetch with complex WHERE clause."""
        await connection_pool.aexecutemany(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            [
                ("alice", "alice@example.com", 25),
                ("bob", "bob@example.com", 30),
                ("charlie", "charlie@example.com", 35),
                ("diana", "diana@example.com", 40),
            ],
        )

        result: list[Record] = await connection_pool.afetch(
            "SELECT username FROM test_users WHERE age >= $1 AND age <= $2", 28, 36
        )

        assert len(result) == 2
        usernames = {row["username"] for row in result}
        assert usernames == {"bob", "charlie"}
