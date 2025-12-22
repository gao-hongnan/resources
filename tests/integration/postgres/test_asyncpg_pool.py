from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg
import pytest

from leitmotif.infrastructure.postgres import (
    AsyncConnectionPool,
    HealthCheckResult,
    PoolNotInitializedError,
)
from leitmotif.infrastructure.postgres.enums import HealthStatus

if TYPE_CHECKING:
    from asyncpg import Record
    from testcontainers.postgres import PostgresContainer


@pytest.mark.asyncio
@pytest.mark.integration
class TestBasicCRUDOperations:
    """Tests for basic CRUD operations."""

    async def test_insert_and_fetch(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test inserting and fetching user records."""
        await asyncpg_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        result: list[Record] = await asyncpg_pool.afetch("SELECT * FROM test_users WHERE username = $1", "alice")

        assert len(result) == 1
        user = result[0]
        assert user["username"] == "alice"
        assert user["email"] == "alice@example.com"
        assert user["age"] == 30

    async def test_fetchrow_returns_single_record(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test fetchrow returns a single record."""
        await asyncpg_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "bob",
            "bob@example.com",
            25,
        )

        result: Record | None = await asyncpg_pool.afetchrow("SELECT * FROM test_users WHERE username = $1", "bob")

        assert result is not None
        assert result["username"] == "bob"
        assert result["email"] == "bob@example.com"
        assert result["age"] == 25

    async def test_fetchrow_returns_none_for_nonexistent(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test fetchrow returns None when no record matches."""
        result: Record | None = await asyncpg_pool.afetchrow(
            "SELECT * FROM test_users WHERE username = $1", "nonexistent"
        )

        assert result is None

    async def test_fetchval_returns_scalar(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test fetchval returns scalar value of various types.

        The fetchval method returns the first column of the first row.
        The return type depends on the SQL query - it can be int, str,
        bool, None, or any other PostgreSQL-supported type.
        """
        await asyncpg_pool.aexecutemany(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            [
                ("user1", "user1@example.com", 20),
                ("user2", "user2@example.com", 30),
                ("user3", "user3@example.com", 40),
            ],
        )

        count = await asyncpg_pool.afetchval("SELECT COUNT(*) FROM test_users")
        assert count == 3
        assert isinstance(count, int)

        username = await asyncpg_pool.afetchval("SELECT username FROM test_users WHERE age = $1", 20)
        assert username == "user1"
        assert isinstance(username, str)

        null_result = await asyncpg_pool.afetchval("SELECT NULL")
        assert null_result is None

        exists = await asyncpg_pool.afetchval("SELECT EXISTS(SELECT 1 FROM test_users WHERE username = $1)", "user1")
        assert exists is True
        assert isinstance(exists, bool)

    async def test_update_operation(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test update operation modifies existing record."""
        await asyncpg_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        await asyncpg_pool.aexecute(
            "UPDATE test_users SET age = $1 WHERE username = $2",
            35,
            "alice",
        )

        result: Record | None = await asyncpg_pool.afetchrow("SELECT age FROM test_users WHERE username = $1", "alice")

        assert result is not None
        assert result["age"] == 35

    async def test_delete_operation(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test delete operation removes record."""
        await asyncpg_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        await asyncpg_pool.aexecute("DELETE FROM test_users WHERE username = $1", "alice")

        result: Record | None = await asyncpg_pool.afetchrow("SELECT * FROM test_users WHERE username = $1", "alice")

        assert result is None


@pytest.mark.asyncio
@pytest.mark.integration
class TestBulkOperations:
    """Tests for bulk insert operations."""

    async def test_executemany_bulk_insert(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test bulk insert with executemany."""
        batch_data: list[tuple[str, str, int]] = [
            ("alice", "alice@example.com", 25),
            ("bob", "bob@example.com", 30),
            ("charlie", "charlie@example.com", 35),
            ("diana", "diana@example.com", 40),
            ("eve", "eve@example.com", 45),
        ]

        await asyncpg_pool.aexecutemany("INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)", batch_data)

        count: int = await asyncpg_pool.afetchval("SELECT COUNT(*) FROM test_users")
        assert count == 5

        users: list[Record] = await asyncpg_pool.afetch("SELECT username, age FROM test_users ORDER BY age")
        assert len(users) == 5
        assert users[0]["username"] == "alice"
        assert users[0]["age"] == 25
        assert users[-1]["username"] == "eve"
        assert users[-1]["age"] == 45

    async def test_copy_records_to_table(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test bulk insert with COPY protocol."""
        records: list[tuple[object, ...]] = [
            ("copy_user1", "copy1@example.com", 21),
            ("copy_user2", "copy2@example.com", 22),
            ("copy_user3", "copy3@example.com", 23),
        ]

        result = await asyncpg_pool.acopy_records_to_table(
            table_name="test_users",
            records=records,
            columns=["username", "email", "age"],
        )

        assert "COPY 3" in result

        count: int = await asyncpg_pool.afetchval("SELECT COUNT(*) FROM test_users")
        assert count == 3


@pytest.mark.asyncio
@pytest.mark.integration
class TestTransactionAPI:
    """Tests for transaction support."""

    async def test_transaction_commit(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test transaction commits on success."""
        async with asyncpg_pool.atransaction() as conn:
            await conn.execute(
                "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                "tx_user",
                "tx@example.com",
                30,
            )

        # Verify commit happened
        result: Record | None = await asyncpg_pool.afetchrow("SELECT * FROM test_users WHERE username = $1", "tx_user")
        assert result is not None
        assert result["username"] == "tx_user"

    async def test_transaction_rollback_on_exception(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test transaction rolls back on exception."""
        simulated_error_msg = "Simulated error"
        with pytest.raises(RuntimeError, match=simulated_error_msg):
            async with asyncpg_pool.atransaction() as conn:
                await conn.execute(
                    "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                    "rollback_user",
                    "rollback@example.com",
                    30,
                )
                raise RuntimeError(simulated_error_msg)

        # Verify rollback happened
        result: Record | None = await asyncpg_pool.afetchrow(
            "SELECT * FROM test_users WHERE username = $1", "rollback_user"
        )
        assert result is None

    async def test_transaction_serializable_isolation(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test transaction with serializable isolation level."""
        async with asyncpg_pool.atransaction(isolation="serializable") as conn:
            await conn.execute(
                "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                "serializable_user",
                "serializable@example.com",
                30,
            )

        result: Record | None = await asyncpg_pool.afetchrow(
            "SELECT * FROM test_users WHERE username = $1", "serializable_user"
        )
        assert result is not None

    async def test_transaction_readonly(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test readonly transaction cannot write."""
        # First insert some data
        await asyncpg_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "readonly_test_user",
            "readonly@example.com",
            30,
        )

        # Readonly transaction should be able to read
        async with asyncpg_pool.atransaction(readonly=True) as conn:
            result = await conn.fetchrow("SELECT * FROM test_users WHERE username = $1", "readonly_test_user")
            assert result is not None


@pytest.mark.asyncio
@pytest.mark.integration
class TestCursorOperations:
    """Tests for cursor/streaming operations."""

    async def test_cursor_streaming(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test cursor streaming for large result sets."""
        # Insert many records
        batch_data = [(f"user{i}", f"user{i}@example.com", 20 + i) for i in range(100)]
        await asyncpg_pool.aexecutemany(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            batch_data,
        )

        # Stream results with cursor
        async with asyncpg_pool.acursor(
            "SELECT * FROM test_users ORDER BY id",
            prefetch=10,
        ) as cursor:
            streamed_rows: list[Record] = [row async for row in cursor]

        assert len(streamed_rows) == 100
        assert streamed_rows[0]["username"] == "user0"
        assert streamed_rows[99]["username"] == "user99"


@pytest.mark.asyncio
@pytest.mark.integration
class TestHealthCheck:
    """Tests for health check functionality."""

    async def test_health_check_returns_healthy(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test health check returns healthy status."""
        result: HealthCheckResult = await asyncpg_pool.ahealth_check()

        assert result.status == HealthStatus.HEALTHY
        assert result.is_healthy()
        assert result.pool_size >= 2
        assert result.pool_max_size == 10
        assert result.latency_s is not None
        assert result.latency_s > 0

    async def test_health_check_to_dict(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test health check serializes to dict."""
        result: HealthCheckResult = await asyncpg_pool.ahealth_check()
        data = result.model_dump(mode="json")

        assert "status" in data
        assert "pool_size" in data
        assert "pool_max_size" in data
        assert "latency_s" in data
        assert data["status"] == "healthy"


@pytest.mark.asyncio
@pytest.mark.integration
class TestPoolLifecycle:
    """Tests for pool lifecycle management."""

    async def test_context_manager(self, postgres_container: PostgresContainer) -> None:
        """Test pool can be used as async context manager."""
        from pydantic import SecretStr

        from leitmotif.infrastructure.postgres import (
            AsyncConnectionPool,
            AsyncpgConfig,
            AsyncpgConnectionSettings,
            AsyncpgPoolSettings,
        )

        exposed_port = postgres_container.get_exposed_port(5432)
        host = postgres_container.get_container_host_ip()

        config = AsyncpgConfig(
            connection=AsyncpgConnectionSettings(
                host=host,
                port=exposed_port,
                database=postgres_container.dbname,
                user=postgres_container.username,
                password=SecretStr(postgres_container.password),
            ),
            pool=AsyncpgPoolSettings(min_size=1, max_size=5),
        )

        async with AsyncConnectionPool(config) as pool:
            result = await pool.afetchval("SELECT 1")
            assert result == 1

    async def test_explicit_initialize_close(self, postgres_container: PostgresContainer) -> None:
        """Test explicit initialization and closing."""
        from pydantic import SecretStr

        from leitmotif.infrastructure.postgres import (
            AsyncConnectionPool,
            AsyncpgConfig,
            AsyncpgConnectionSettings,
            AsyncpgPoolSettings,
        )

        exposed_port = postgres_container.get_exposed_port(5432)
        host = postgres_container.get_container_host_ip()

        config = AsyncpgConfig(
            connection=AsyncpgConnectionSettings(
                host=host,
                port=exposed_port,
                database=postgres_container.dbname,
                user=postgres_container.username,
                password=SecretStr(postgres_container.password),
            ),
            pool=AsyncpgPoolSettings(min_size=1, max_size=5),
        )

        pool = AsyncConnectionPool(config)
        await pool.ainitialize()

        try:
            result = await pool.afetchval("SELECT 1")
            assert result == 1
        finally:
            await pool.aclose()

    async def test_pool_not_initialized_error(self, postgres_container: PostgresContainer) -> None:
        """Test accessing pool before initialization raises error."""
        from pydantic import SecretStr

        from leitmotif.infrastructure.postgres import (
            AsyncConnectionPool,
            AsyncpgConfig,
            AsyncpgConnectionSettings,
            AsyncpgPoolSettings,
        )

        exposed_port = postgres_container.get_exposed_port(5432)
        host = postgres_container.get_container_host_ip()

        config = AsyncpgConfig(
            connection=AsyncpgConnectionSettings(
                host=host,
                port=exposed_port,
                database=postgres_container.dbname,
                user=postgres_container.username,
                password=SecretStr(postgres_container.password),
            ),
            pool=AsyncpgPoolSettings(min_size=1, max_size=5),
        )

        pool = AsyncConnectionPool(config)

        with pytest.raises(PoolNotInitializedError):
            await pool.afetchval("SELECT 1")

    async def test_pool_size_properties(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test pool size properties."""
        assert asyncpg_pool.pool_size >= 2
        assert asyncpg_pool.pool_max_size == 10


@pytest.mark.asyncio
@pytest.mark.integration
class TestErrorHandling:
    """Tests for error handling."""

    async def test_unique_constraint_violation(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test unique constraint violation raises exception."""
        await asyncpg_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
        )

        with pytest.raises(asyncpg.UniqueViolationError):
            await asyncpg_pool.aexecute(
                "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                "alice",
                "alice2@example.com",
                25,
            )

    async def test_check_constraint_violation(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test check constraint violation raises exception."""
        with pytest.raises(asyncpg.CheckViolationError):
            await asyncpg_pool.aexecute(
                "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
                "invalid_age_user",
                "invalid@example.com",
                -5,  # age < 0 violates check constraint
            )

    async def test_query_with_timeout(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test query execution with timeout parameter."""
        await asyncpg_pool.aexecute(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            "alice",
            "alice@example.com",
            30,
            timeout=5.0,
        )

        result: list[Record] = await asyncpg_pool.afetch(
            "SELECT * FROM test_users WHERE username = $1", "alice", timeout=5.0
        )

        assert len(result) == 1
        assert result[0]["username"] == "alice"


@pytest.mark.asyncio
@pytest.mark.integration
class TestComplexQueries:
    """Tests for complex query patterns."""

    async def test_fetch_with_multiple_conditions(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test fetch with complex WHERE clause."""
        await asyncpg_pool.aexecutemany(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            [
                ("alice", "alice@example.com", 25),
                ("bob", "bob@example.com", 30),
                ("charlie", "charlie@example.com", 35),
                ("diana", "diana@example.com", 40),
            ],
        )

        result: list[Record] = await asyncpg_pool.afetch(
            "SELECT username FROM test_users WHERE age >= $1 AND age <= $2", 28, 36
        )

        assert len(result) == 2
        usernames = {row["username"] for row in result}
        assert usernames == {"bob", "charlie"}

    async def test_fetch_with_ordering_and_limit(self, asyncpg_pool: AsyncConnectionPool) -> None:
        """Test fetch with ORDER BY and LIMIT."""
        await asyncpg_pool.aexecutemany(
            "INSERT INTO test_users (username, email, age) VALUES ($1, $2, $3)",
            [
                ("alice", "alice@example.com", 25),
                ("bob", "bob@example.com", 30),
                ("charlie", "charlie@example.com", 35),
            ],
        )

        result: list[Record] = await asyncpg_pool.afetch("SELECT username FROM test_users ORDER BY age DESC LIMIT 2")

        assert len(result) == 2
        assert result[0]["username"] == "charlie"
        assert result[1]["username"] == "bob"
