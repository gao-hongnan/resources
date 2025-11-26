"""Pool lifecycle tests for AsyncConnectionPool.

Tests initialization, shutdown, and context manager behavior.
Uses real PostgreSQL via TestContainers (no mocks).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr
from rich.console import Console

from pixiu.database import AsyncConnectionPool, DatabaseConfig, DatabaseConnectionSettings, PoolSettings
from pixiu.database.models import HealthCheckStatus

console = Console()


@pytest.mark.integration
@pytest.mark.database
class TestPoolLifecycle:
    """Test AsyncConnectionPool initialization and shutdown lifecycle."""

    async def test_successful_initialization(self, postgres_container: Any) -> None:
        """Test successful pool initialization with valid credentials."""
        console.print("[bold blue]Testing successful pool initialization[/bold blue]")

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
            pool=PoolSettings(min_size=2, max_size=5),
        )

        pool = AsyncConnectionPool(config)

        # Initially pool should not be initialized
        assert pool._pool is None

        # Initialize
        await pool.ainitialize()

        # Verify pool is initialized
        assert pool._pool is not None
        assert pool._pool.get_size() >= config.pool.min_size  # type: ignore[unreachable]
        assert pool._pool.get_max_size() == config.pool.max_size  # type: ignore[unreachable]

        # Clean up
        await pool.aclose()

        console.print("[green]✓ Pool initialized successfully[/green]")

    async def test_double_initialization_is_idempotent(self, postgres_container: Any) -> None:
        """Test that calling ainitialize() twice is safe (idempotent)."""
        console.print("[bold blue]Testing double initialization (idempotency)[/bold blue]")

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
            )
        )

        pool = AsyncConnectionPool(config)

        # First initialization
        await pool.ainitialize()
        first_pool = pool._pool

        # Second initialization should be a no-op
        await pool.ainitialize()
        second_pool = pool._pool

        # Should be the same pool object
        assert first_pool is second_pool

        await pool.aclose()

        console.print("[green]✓ Double initialization is idempotent[/green]")

    async def test_initialization_with_bad_credentials_fails(self, postgres_container: Any) -> None:
        """Test that initialization fails with invalid credentials."""
        console.print("[bold blue]Testing initialization with bad credentials[/bold blue]")

        exposed_port = postgres_container.get_exposed_port(5432)
        host = postgres_container.get_container_host_ip()

        config = DatabaseConfig(
            connection=DatabaseConnectionSettings(
                host=host,
                port=exposed_port,
                database="test_db",
                user="wrong_user",
                password=SecretStr("wrong_password"),
                sslmode="disable",
            )
        )

        pool = AsyncConnectionPool(config)

        # Should fail with authentication error
        with pytest.raises(Exception) as exc_info:
            await pool.ainitialize()

        # Verify it's an authentication-related error
        error_msg = str(exc_info.value).lower()
        assert any(keyword in error_msg for keyword in ["password", "authentication", "auth", "failed"])

        console.print(f"[yellow]✓ Bad credentials correctly rejected: {exc_info.value}[/yellow]")

    async def test_initialization_with_wrong_host_fails(self) -> None:
        """Test that initialization fails with unreachable host."""
        console.print("[bold blue]Testing initialization with wrong host[/bold blue]")

        config = DatabaseConfig(
            connection=DatabaseConnectionSettings(
                host="nonexistent.invalid",
                port=5432,
                database="test_db",
                user="test_user",
                password=SecretStr("test_password"),
                sslmode="disable",
            ),
            pool=PoolSettings(min_size=1, max_size=2, timeout=2.0),  # Short timeout
        )

        pool = AsyncConnectionPool(config)

        # Should fail with TimeoutError or OSError (connection-related errors)
        with pytest.raises((TimeoutError, OSError, Exception)) as exc_info:
            await pool.ainitialize()

        # Verify it's a network-related error (TimeoutError, OSError, or ConnectionError subclass)
        assert isinstance(exc_info.value, TimeoutError | OSError) or "connection" in str(exc_info.value).lower()

        console.print(f"[yellow]✓ Wrong host correctly rejected: {type(exc_info.value).__name__}[/yellow]")

    async def test_initialization_with_wrong_port_fails(self, postgres_container: Any) -> None:
        """Test that initialization fails with wrong port."""
        console.print("[bold blue]Testing initialization with wrong port[/bold blue]")

        host = postgres_container.get_container_host_ip()

        config = DatabaseConfig(
            connection=DatabaseConnectionSettings(
                host=host,
                port=19999,  # Wrong port
                database="test_db",
                user="test_user",
                password=SecretStr("test_password"),
                sslmode="disable",
            ),
            pool=PoolSettings(min_size=1, max_size=2, timeout=2.0),  # Short timeout
        )

        pool = AsyncConnectionPool(config)

        # Should fail with connection error
        with pytest.raises(Exception) as exc_info:
            await pool.ainitialize()

        # Verify it's a connection-related error
        error_msg = str(exc_info.value).lower()
        assert any(keyword in error_msg for keyword in ["connect", "failed", "refused", "timeout"])

        console.print(f"[yellow]✓ Wrong port correctly rejected: {exc_info.value}[/yellow]")

    async def test_using_pool_before_initialization_raises_error(self) -> None:
        """Test that accessing pool property before initialization raises RuntimeError."""
        console.print("[bold blue]Testing pool access before initialization[/bold blue]")

        config = DatabaseConfig()  # Default config
        pool = AsyncConnectionPool(config)

        # Should raise RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            _ = pool.pool

        assert "not initialized" in str(exc_info.value).lower()
        assert "ainitialize" in str(exc_info.value).lower()

        console.print(f"[yellow]✓ Correct error for uninitialized pool: {exc_info.value}[/yellow]")

    async def test_clean_shutdown(self, postgres_container: Any) -> None:
        """Test clean shutdown with no active connections."""
        console.print("[bold blue]Testing clean shutdown[/bold blue]")

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
            )
        )

        pool = AsyncConnectionPool(config)
        await pool.ainitialize()

        # Verify pool is initialized
        assert pool._pool is not None

        # Close pool
        await pool.aclose()

        # Verify pool is None after close
        assert pool._pool is None

        console.print("[green]✓ Clean shutdown completed[/green]")  # type: ignore[unreachable]

    async def test_multiple_shutdown_calls_are_safe(self, postgres_container: Any) -> None:
        """Test that calling aclose() multiple times is safe (idempotent)."""
        console.print("[bold blue]Testing multiple shutdown calls[/bold blue]")

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
            )
        )

        pool = AsyncConnectionPool(config)
        await pool.ainitialize()

        # First close
        await pool.aclose()
        assert pool._pool is None

        # Second close should be safe (no error)
        await pool.aclose()
        assert pool._pool is None

        console.print("[green]✓ Multiple shutdown calls are safe[/green]")


@pytest.mark.integration
@pytest.mark.database
class TestContextManager:
    """Test AsyncConnectionPool context manager behavior."""

    async def test_context_manager_normal_exit(self, postgres_container: Any) -> None:
        """Test context manager with normal exit."""
        console.print("[bold blue]Testing context manager normal exit[/bold blue]")

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
            )
        )

        pool = AsyncConnectionPool(config)

        # Use as context manager
        async with pool as p:
            # Pool should be initialized
            assert p._pool is not None
            assert p is pool

            # Can execute queries
            async with p.aacquire() as conn:
                result = await conn.fetchval("SELECT 1")
                assert result == 1

        # After exiting context, pool should be closed
        assert pool._pool is None

        console.print("[green]✓ Context manager normal exit works correctly[/green]")

    async def test_context_manager_with_exception(self, postgres_container: Any) -> None:
        """Test context manager cleanup when exception occurs."""
        console.print("[bold blue]Testing context manager with exception[/bold blue]")

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
            )
        )

        pool = AsyncConnectionPool(config)

        # Use context manager with exception
        with pytest.raises(ValueError) as exc_info:
            async with pool as p:
                assert p._pool is not None

                # Raise exception inside context
                raise ValueError("Test exception")

        assert str(exc_info.value) == "Test exception"

        # Pool should still be closed despite exception
        assert pool._pool is None

        console.print("[green]✓ Context manager cleanup on exception works correctly[/green]")

    async def test_context_manager_without_initialization(self) -> None:
        """Test that context manager initializes pool automatically."""
        console.print("[bold blue]Testing context manager auto-initialization[/bold blue]")

        # Note: This test will fail to connect, but we're testing the initialization logic
        config = DatabaseConfig(
            connection=DatabaseConnectionSettings(
                host="nonexistent.invalid",
                port=5432,
                database="test_db",
                user="test_user",
                password=SecretStr("test_password"),
                sslmode="disable",
            ),
            pool=PoolSettings(min_size=1, max_size=2, timeout=1.0),
        )

        pool = AsyncConnectionPool(config)

        # Pool is not initialized
        assert pool._pool is None

        # Context manager should attempt initialization
        with pytest.raises((TimeoutError, OSError)):  # Will fail to connect
            async with pool:
                pass  # Won't reach here

        console.print("[yellow]✓ Context manager attempts initialization[/yellow]")


@pytest.mark.integration
@pytest.mark.database
class TestHealthCheckLifecycle:
    """Test health check behavior during pool lifecycle."""

    async def test_health_check_before_initialization(self) -> None:
        """Test health check when pool is not initialized."""
        console.print("[bold blue]Testing health check before initialization[/bold blue]")

        config = DatabaseConfig()
        pool = AsyncConnectionPool(config)

        # Health check before initialization
        result = await pool.ahealth_check()

        assert result.status == HealthCheckStatus.UNHEALTHY
        assert result.pool_initialized is False
        assert result.pool_size is None
        assert result.pool_max_size is None

        console.print("[yellow]✓ Health check before init returns UNHEALTHY[/yellow]")

    async def test_health_check_after_initialization(self, postgres_container: Any) -> None:
        """Test health check after successful initialization."""
        console.print("[bold blue]Testing health check after initialization[/bold blue]")

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
            pool=PoolSettings(min_size=3, max_size=10),
        )

        pool = AsyncConnectionPool(config)
        await pool.ainitialize()

        # Health check after initialization
        result = await pool.ahealth_check()

        assert result.status == HealthCheckStatus.HEALTHY
        assert result.pool_initialized is True
        assert result.pool_size is not None
        assert result.pool_size >= 3  # At least min_size
        assert result.pool_max_size == 10

        await pool.aclose()

        console.print("[green]✓ Health check after init returns HEALTHY[/green]")

    async def test_health_check_after_close(self, postgres_container: Any) -> None:
        """Test health check after pool is closed."""
        console.print("[bold blue]Testing health check after close[/bold blue]")

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
            )
        )

        pool = AsyncConnectionPool(config)
        await pool.ainitialize()
        await pool.aclose()

        # Health check after close
        result = await pool.ahealth_check()

        assert result.status == HealthCheckStatus.UNHEALTHY
        assert result.pool_initialized is False

        console.print("[yellow]✓ Health check after close returns UNHEALTHY[/yellow]")


@pytest.mark.integration
@pytest.mark.database
class TestPoolPropertyAccess:
    """Test pool property access during different lifecycle stages."""

    async def test_pool_property_before_initialization(self) -> None:
        """Test that pool property raises error before initialization."""
        console.print("[bold blue]Testing pool property access before init[/bold blue]")

        config = DatabaseConfig()
        pool_obj = AsyncConnectionPool(config)

        with pytest.raises(RuntimeError) as exc_info:
            _ = pool_obj.pool

        assert "not initialized" in str(exc_info.value).lower()

        console.print(f"[yellow]✓ Pool property raises error: {exc_info.value}[/yellow]")

    async def test_pool_property_after_initialization(self, postgres_container: Any) -> None:
        """Test that pool property returns pool after initialization."""
        console.print("[bold blue]Testing pool property access after init[/bold blue]")

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
            )
        )

        pool_obj = AsyncConnectionPool(config)
        await pool_obj.ainitialize()

        # Pool property should return the pool
        pool = pool_obj.pool
        assert pool is not None
        assert pool is pool_obj._pool

        await pool_obj.aclose()

        console.print("[green]✓ Pool property returns pool after init[/green]")

    async def test_pool_property_after_close(self, postgres_container: Any) -> None:
        """Test that pool property raises error after close."""
        console.print("[bold blue]Testing pool property access after close[/bold blue]")

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
            )
        )

        pool_obj = AsyncConnectionPool(config)
        await pool_obj.ainitialize()
        await pool_obj.aclose()

        # Should raise error after close
        with pytest.raises(RuntimeError) as exc_info:
            _ = pool_obj.pool

        assert "not initialized" in str(exc_info.value).lower()

        console.print(f"[yellow]✓ Pool property raises error after close: {exc_info.value}[/yellow]")
