"""Configuration validation tests for database module.

Tests Pydantic validation rules for all database configuration models.
No database connection required - pure validation testing.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError
from rich.console import Console

from pixiu.database.config import (
    AsyncpgSettings,
    DatabaseConfig,
    DatabaseConnectionSettings,
    PoolSettings,
)

console = Console()


class TestDatabaseConnectionSettings:
    """Test DatabaseConnectionSettings Pydantic validation."""

    def test_valid_default_configuration(self) -> None:
        """Test that default configuration is valid."""
        console.print("[bold blue]Testing default DatabaseConnectionSettings[/bold blue]")

        config = DatabaseConnectionSettings()

        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "postgres"
        assert config.user == "postgres"
        assert config.password.get_secret_value() == ""
        assert config.sslmode == "prefer"

        console.print("[green]✓ Default configuration is valid[/green]")

    def test_valid_custom_configuration(self) -> None:
        """Test valid custom configuration values."""
        console.print("[bold blue]Testing custom DatabaseConnectionSettings[/bold blue]")

        config = DatabaseConnectionSettings(
            host="db.example.com",
            port=5433,
            database="myapp",
            user="appuser",
            password=SecretStr("secret123"),
            sslmode="require",
        )

        assert config.host == "db.example.com"
        assert config.port == 5433
        assert config.database == "myapp"
        assert config.user == "appuser"
        assert config.password.get_secret_value() == "secret123"
        assert config.sslmode == "require"

        console.print("[green]✓ Custom configuration is valid[/green]")

    @pytest.mark.parametrize(
        ("port", "expected_valid"),
        [
            (1, True),  # Minimum valid port
            (5432, True),  # Standard PostgreSQL port
            (65535, True),  # Maximum valid port
            (0, False),  # Below minimum
            (-1, False),  # Negative
            (65536, False),  # Above maximum
            (99999, False),  # Way above maximum
        ],
    )
    def test_port_validation(self, port: int, expected_valid: bool) -> None:
        """Test port number validation (1-65535)."""
        console.print(f"[bold blue]Testing port={port}, expecting valid={expected_valid}[/bold blue]")

        if expected_valid:
            config = DatabaseConnectionSettings(port=port)
            assert config.port == port
            console.print(f"[green]✓ Port {port} is valid[/green]")
        else:
            with pytest.raises(ValidationError) as exc_info:
                DatabaseConnectionSettings(port=port)

            assert "port" in str(exc_info.value).lower()
            console.print(f"[yellow]✓ Port {port} correctly rejected[/yellow]")

    def test_password_as_secret_str(self) -> None:
        """Test that password is stored as SecretStr."""
        console.print("[bold blue]Testing SecretStr password handling[/bold blue]")

        config = DatabaseConnectionSettings(password=SecretStr("supersecret"))

        # Password should not be revealed in repr
        config_repr = repr(config)
        assert "supersecret" not in config_repr
        assert "SecretStr" in config_repr

        # But can be accessed via get_secret_value()
        assert config.password.get_secret_value() == "supersecret"

        console.print("[green]✓ Password correctly stored as SecretStr[/green]")

    def test_extra_fields_forbidden(self) -> None:
        """Test that extra fields are rejected (extra='forbid')."""
        console.print("[bold blue]Testing extra fields rejection[/bold blue]")

        with pytest.raises(ValidationError) as exc_info:
            DatabaseConnectionSettings(
                host="localhost",
                unknown_field="should_fail",  # type: ignore[call-arg]
            )

        assert "extra" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()
        console.print("[yellow]✓ Extra fields correctly rejected[/yellow]")

    @pytest.mark.parametrize(
        "sslmode",
        [
            "disable",
            "allow",
            "prefer",
            "require",
            "verify-ca",
            "verify-full",
        ],
    )
    def test_sslmode_values(self, sslmode: str) -> None:
        """Test various SSL mode values (no validation in current code)."""
        console.print(f"[bold blue]Testing sslmode={sslmode}[/bold blue]")

        config = DatabaseConnectionSettings(sslmode=sslmode)
        assert config.sslmode == sslmode

        console.print(f"[green]✓ SSL mode '{sslmode}' accepted[/green]")


class TestPoolSettings:
    """Test PoolSettings Pydantic validation."""

    def test_valid_default_configuration(self) -> None:
        """Test that default pool configuration is valid."""
        console.print("[bold blue]Testing default PoolSettings[/bold blue]")

        config = PoolSettings()

        assert config.min_size == 5
        assert config.max_size == 20
        assert config.timeout == 30.0

        console.print("[green]✓ Default pool configuration is valid[/green]")

    def test_valid_custom_configuration(self) -> None:
        """Test valid custom pool configuration."""
        console.print("[bold blue]Testing custom PoolSettings[/bold blue]")

        config = PoolSettings(min_size=10, max_size=50, timeout=60.0)

        assert config.min_size == 10
        assert config.max_size == 50
        assert config.timeout == 60.0

        console.print("[green]✓ Custom pool configuration is valid[/green]")

    @pytest.mark.parametrize(
        ("min_size", "expected_valid"),
        [
            (1, True),  # Minimum valid
            (50, True),  # Mid-range
            (100, True),  # Maximum valid
            (0, False),  # Below minimum
            (-1, False),  # Negative
            (101, False),  # Above maximum
        ],
    )
    def test_min_size_validation(self, min_size: int, expected_valid: bool) -> None:
        """Test min_size validation (1-100)."""
        console.print(f"[bold blue]Testing min_size={min_size}, expecting valid={expected_valid}[/bold blue]")

        if expected_valid:
            config = PoolSettings(min_size=min_size)
            assert config.min_size == min_size
            console.print(f"[green]✓ min_size {min_size} is valid[/green]")
        else:
            with pytest.raises(ValidationError) as exc_info:
                PoolSettings(min_size=min_size)

            assert "min_size" in str(exc_info.value).lower()
            console.print(f"[yellow]✓ min_size {min_size} correctly rejected[/yellow]")

    @pytest.mark.parametrize(
        ("max_size", "expected_valid"),
        [
            (1, True),  # Minimum valid
            (500, True),  # Mid-range
            (1000, True),  # Maximum valid
            (0, False),  # Below minimum
            (-1, False),  # Negative
            (1001, False),  # Above maximum
        ],
    )
    def test_max_size_validation(self, max_size: int, expected_valid: bool) -> None:
        """Test max_size validation (1-1000)."""
        console.print(f"[bold blue]Testing max_size={max_size}, expecting valid={expected_valid}[/bold blue]")

        if expected_valid:
            config = PoolSettings(max_size=max_size)
            assert config.max_size == max_size
            console.print(f"[green]✓ max_size {max_size} is valid[/green]")
        else:
            with pytest.raises(ValidationError) as exc_info:
                PoolSettings(max_size=max_size)

            assert "max_size" in str(exc_info.value).lower()
            console.print(f"[yellow]✓ max_size {max_size} correctly rejected[/yellow]")

    @pytest.mark.parametrize(
        ("timeout", "expected_valid"),
        [
            (1.0, True),  # Minimum valid
            (150.0, True),  # Mid-range
            (300.0, True),  # Maximum valid
            (0.5, False),  # Below minimum
            (0.0, False),  # Zero
            (-1.0, False),  # Negative
            (301.0, False),  # Above maximum
        ],
    )
    def test_timeout_validation(self, timeout: float, expected_valid: bool) -> None:
        """Test timeout validation (1.0-300.0 seconds)."""
        console.print(f"[bold blue]Testing timeout={timeout}, expecting valid={expected_valid}[/bold blue]")

        if expected_valid:
            config = PoolSettings(timeout=timeout)
            assert config.timeout == timeout
            console.print(f"[green]✓ timeout {timeout} is valid[/green]")
        else:
            with pytest.raises(ValidationError) as exc_info:
                PoolSettings(timeout=timeout)

            assert "timeout" in str(exc_info.value).lower()
            console.print(f"[yellow]✓ timeout {timeout} correctly rejected[/yellow]")

    def test_min_size_greater_than_max_size_allowed(self) -> None:
        """Test that min_size > max_size is currently allowed (potential bug).

        Note: Current implementation doesn't validate min_size <= max_size.
        This test documents the current behavior.
        """
        console.print("[bold blue]Testing min_size > max_size scenario[/bold blue]")

        # This currently succeeds but is logically invalid
        config = PoolSettings(min_size=50, max_size=10)

        assert config.min_size == 50
        assert config.max_size == 10
        console.print("[yellow]⚠ min_size > max_size is currently allowed (may want to add validation)[/yellow]")

    def test_extra_fields_forbidden(self) -> None:
        """Test that extra fields are rejected (extra='forbid')."""
        console.print("[bold blue]Testing extra fields rejection in PoolSettings[/bold blue]")

        with pytest.raises(ValidationError) as exc_info:
            PoolSettings(
                min_size=5,
                extra_field="should_fail",  # type: ignore[call-arg]
            )

        assert "extra" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()
        console.print("[yellow]✓ Extra fields correctly rejected[/yellow]")


class TestAsyncpgSettings:
    """Test AsyncpgSettings Pydantic validation."""

    def test_valid_default_configuration(self) -> None:
        """Test that default asyncpg configuration is valid."""
        console.print("[bold blue]Testing default AsyncpgSettings[/bold blue]")

        config = AsyncpgSettings()

        assert config.command_timeout == 60.0
        assert config.statement_cache_size == 256
        assert config.max_queries == 50_000
        assert config.max_inactive_connection_lifetime == 300.0

        console.print("[green]✓ Default asyncpg configuration is valid[/green]")

    def test_valid_custom_configuration(self) -> None:
        """Test valid custom asyncpg configuration."""
        console.print("[bold blue]Testing custom AsyncpgSettings[/bold blue]")

        config = AsyncpgSettings(
            command_timeout=120.0,
            statement_cache_size=512,
            max_queries=100_000,
            max_inactive_connection_lifetime=600.0,
        )

        assert config.command_timeout == 120.0
        assert config.statement_cache_size == 512
        assert config.max_queries == 100_000
        assert config.max_inactive_connection_lifetime == 600.0

        console.print("[green]✓ Custom asyncpg configuration is valid[/green]")

    @pytest.mark.parametrize(
        ("command_timeout", "expected_valid"),
        [
            (1.0, True),  # Minimum valid
            (1800.0, True),  # Mid-range
            (3600.0, True),  # Maximum valid (1 hour)
            (0.5, False),  # Below minimum
            (0.0, False),  # Zero
            (-1.0, False),  # Negative
            (3601.0, False),  # Above maximum
        ],
    )
    def test_command_timeout_validation(self, command_timeout: float, expected_valid: bool) -> None:
        """Test command_timeout validation (1.0-3600.0 seconds)."""
        console.print(
            f"[bold blue]Testing command_timeout={command_timeout}, expecting valid={expected_valid}[/bold blue]"
        )

        if expected_valid:
            config = AsyncpgSettings(command_timeout=command_timeout)
            assert config.command_timeout == command_timeout
            console.print(f"[green]✓ command_timeout {command_timeout} is valid[/green]")
        else:
            with pytest.raises(ValidationError) as exc_info:
                AsyncpgSettings(command_timeout=command_timeout)

            assert "command_timeout" in str(exc_info.value).lower()
            console.print(f"[yellow]✓ command_timeout {command_timeout} correctly rejected[/yellow]")

    @pytest.mark.parametrize(
        ("cache_size", "expected_valid"),
        [
            (0, True),  # Minimum valid (cache disabled)
            (256, True),  # Default
            (1024, True),  # Maximum valid
            (-1, False),  # Negative
            (1025, False),  # Above maximum
        ],
    )
    def test_statement_cache_size_validation(self, cache_size: int, expected_valid: bool) -> None:
        """Test statement_cache_size validation (0-1024)."""
        console.print(
            f"[bold blue]Testing statement_cache_size={cache_size}, expecting valid={expected_valid}[/bold blue]"
        )

        if expected_valid:
            config = AsyncpgSettings(statement_cache_size=cache_size)
            assert config.statement_cache_size == cache_size
            console.print(f"[green]✓ statement_cache_size {cache_size} is valid[/green]")
        else:
            with pytest.raises(ValidationError) as exc_info:
                AsyncpgSettings(statement_cache_size=cache_size)

            assert "statement_cache_size" in str(exc_info.value).lower()
            console.print(f"[yellow]✓ statement_cache_size {cache_size} correctly rejected[/yellow]")

    @pytest.mark.parametrize(
        ("max_queries", "expected_valid"),
        [
            (1, True),  # Minimum valid
            (50_000, True),  # Default
            (1_000_000, True),  # Maximum valid
            (0, False),  # Below minimum
            (-1, False),  # Negative
            (1_000_001, False),  # Above maximum
        ],
    )
    def test_max_queries_validation(self, max_queries: int, expected_valid: bool) -> None:
        """Test max_queries validation (1-1,000,000)."""
        console.print(f"[bold blue]Testing max_queries={max_queries}, expecting valid={expected_valid}[/bold blue]")

        if expected_valid:
            config = AsyncpgSettings(max_queries=max_queries)
            assert config.max_queries == max_queries
            console.print(f"[green]✓ max_queries {max_queries} is valid[/green]")
        else:
            with pytest.raises(ValidationError) as exc_info:
                AsyncpgSettings(max_queries=max_queries)

            assert "max_queries" in str(exc_info.value).lower()
            console.print(f"[yellow]✓ max_queries {max_queries} correctly rejected[/yellow]")

    @pytest.mark.parametrize(
        ("lifetime", "expected_valid"),
        [
            (1.0, True),  # Minimum valid
            (1800.0, True),  # Mid-range
            (3600.0, True),  # Maximum valid (1 hour)
            (0.5, False),  # Below minimum
            (0.0, False),  # Zero
            (-1.0, False),  # Negative
            (3601.0, False),  # Above maximum
        ],
    )
    def test_max_inactive_connection_lifetime_validation(self, lifetime: float, expected_valid: bool) -> None:
        """Test max_inactive_connection_lifetime validation (1.0-3600.0 seconds)."""
        console.print(
            f"[bold blue]Testing max_inactive_connection_lifetime={lifetime}, "
            f"expecting valid={expected_valid}[/bold blue]"
        )

        if expected_valid:
            config = AsyncpgSettings(max_inactive_connection_lifetime=lifetime)
            assert config.max_inactive_connection_lifetime == lifetime
            console.print(f"[green]✓ max_inactive_connection_lifetime {lifetime} is valid[/green]")
        else:
            with pytest.raises(ValidationError) as exc_info:
                AsyncpgSettings(max_inactive_connection_lifetime=lifetime)

            assert "max_inactive_connection_lifetime" in str(exc_info.value).lower()
            console.print(f"[yellow]✓ max_inactive_connection_lifetime {lifetime} correctly rejected[/yellow]")

    def test_extra_fields_forbidden(self) -> None:
        """Test that extra fields are rejected (extra='forbid')."""
        console.print("[bold blue]Testing extra fields rejection in AsyncpgSettings[/bold blue]")

        with pytest.raises(ValidationError) as exc_info:
            AsyncpgSettings(
                command_timeout=60.0,
                unknown_setting="should_fail",  # type: ignore[call-arg]
            )

        assert "extra" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()
        console.print("[yellow]✓ Extra fields correctly rejected[/yellow]")


class TestDatabaseConfig:
    """Test DatabaseConfig Pydantic validation and URL generation."""

    def test_valid_default_configuration(self) -> None:
        """Test that default database configuration is valid."""
        console.print("[bold blue]Testing default DatabaseConfig[/bold blue]")

        config = DatabaseConfig()

        assert config.connection.host == "localhost"
        assert config.pool.min_size == 5
        assert config.asyncpg.command_timeout == 60.0

        console.print("[green]✓ Default database configuration is valid[/green]")

    def test_valid_custom_configuration(self) -> None:
        """Test valid custom database configuration."""
        console.print("[bold blue]Testing custom DatabaseConfig[/bold blue]")

        config = DatabaseConfig(
            connection=DatabaseConnectionSettings(
                host="db.example.com",
                port=5433,
                database="myapp",
                user="appuser",
                password=SecretStr("secret123"),
                sslmode="require",
            ),
            pool=PoolSettings(min_size=10, max_size=50, timeout=60.0),
            asyncpg=AsyncpgSettings(command_timeout=120.0, statement_cache_size=512),
        )

        assert config.connection.host == "db.example.com"
        assert config.pool.min_size == 10
        assert config.asyncpg.command_timeout == 120.0

        console.print("[green]✓ Custom database configuration is valid[/green]")

    def test_url_generation_default(self) -> None:
        """Test URL generation with default settings."""
        console.print("[bold blue]Testing default URL generation[/bold blue]")

        config = DatabaseConfig()
        url = config.url

        # Default password is empty, so no colon separator
        assert url == "postgresql://postgres@localhost:5432/postgres?sslmode=prefer"
        console.print(f"[green]✓ Default URL: {url}[/green]")

    def test_url_generation_with_password(self) -> None:
        """Test URL generation with password."""
        console.print("[bold blue]Testing URL generation with password[/bold blue]")

        config = DatabaseConfig(
            connection=DatabaseConnectionSettings(
                user="myuser",
                password=SecretStr("mypassword"),
                database="mydb",
            )
        )

        url = config.url

        assert "myuser:mypassword@" in url
        assert url == "postgresql://myuser:mypassword@localhost:5432/mydb?sslmode=prefer"
        console.print(f"[green]✓ URL with password: {url}[/green]")

    def test_url_generation_with_special_characters(self) -> None:
        """Test URL generation with special characters in password."""
        console.print("[bold blue]Testing URL generation with special characters[/bold blue]")

        config = DatabaseConfig(
            connection=DatabaseConnectionSettings(
                user="my@user",
                password=SecretStr("p@ss:word#123"),
                host="db.example.com",
                port=5433,
                database="my-db",
                sslmode="require",
            )
        )

        url = config.url

        # Special characters should be URL-encoded
        assert "my%40user" in url  # @ encoded
        assert "p%40ss%3Aword%23123" in url  # @, :, # encoded
        assert url.endswith("?sslmode=require")
        console.print(f"[green]✓ URL with special chars: {url}[/green]")

    def test_url_generation_without_password(self) -> None:
        """Test URL generation when password is empty."""
        console.print("[bold blue]Testing URL generation without password[/bold blue]")

        config = DatabaseConfig(
            connection=DatabaseConnectionSettings(
                user="appuser",
                password=SecretStr(""),
                database="appdb",
            )
        )

        url = config.url

        # Should have user@ but no password
        assert "appuser@" in url
        assert ":@" not in url  # No empty password separator
        console.print(f"[green]✓ URL without password: {url}[/green]")

    @pytest.mark.parametrize(
        "sslmode",
        [
            "disable",
            "allow",
            "prefer",
            "require",
            "verify-ca",
            "verify-full",
        ],
    )
    def test_url_generation_with_different_sslmodes(self, sslmode: str) -> None:
        """Test URL generation with different SSL modes."""
        console.print(f"[bold blue]Testing URL generation with sslmode={sslmode}[/bold blue]")

        config = DatabaseConfig(connection=DatabaseConnectionSettings(sslmode=sslmode))

        url = config.url

        assert f"sslmode={sslmode}" in url
        console.print(f"[green]✓ URL with sslmode={sslmode}: {url}[/green]")

    def test_configuration_is_frozen(self) -> None:
        """Test that DatabaseConfig is immutable (frozen=True)."""
        console.print("[bold blue]Testing configuration immutability[/bold blue]")

        config = DatabaseConfig()

        # Attempt to modify should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            config.connection = DatabaseConnectionSettings(host="newhost")  # type: ignore[misc]

        assert "frozen" in str(exc_info.value).lower() or "immutable" in str(exc_info.value).lower()
        console.print("[yellow]✓ Configuration correctly frozen (immutable)[/yellow]")

    def test_extra_fields_ignored(self) -> None:
        """Test that extra fields are ignored (extra='ignore') in DatabaseConfig."""
        console.print("[bold blue]Testing extra fields are ignored in DatabaseConfig[/bold blue]")

        # This should succeed (extra='ignore' not 'forbid')
        config = DatabaseConfig(
            connection=DatabaseConnectionSettings(),
            extra_field="should_be_ignored",  # type: ignore[call-arg]
        )

        assert config.connection.host == "localhost"
        assert not hasattr(config, "extra_field")
        console.print("[green]✓ Extra fields correctly ignored[/green]")

    def test_validate_assignment(self) -> None:
        """Test that validate_assignment=True is active."""
        console.print("[bold blue]Testing validate_assignment behavior[/bold blue]")

        config = DatabaseConfig()

        # Since frozen=True, we can't test assignment validation directly
        # But we can verify the config setting
        assert config.model_config.get("validate_assignment") is True
        console.print("[green]✓ validate_assignment is enabled[/green]")

    def test_nested_model_validation(self) -> None:
        """Test that nested model validation works correctly."""
        console.print("[bold blue]Testing nested model validation[/bold blue]")

        # Invalid nested configuration should fail
        with pytest.raises(ValidationError) as exc_info:
            DatabaseConfig(
                connection=DatabaseConnectionSettings(port=99999)  # Invalid port
            )

        assert "port" in str(exc_info.value).lower()
        console.print("[yellow]✓ Nested validation correctly enforced[/yellow]")

    def test_complete_valid_configuration(self) -> None:
        """Test a complete valid configuration with all settings."""
        console.print("[bold blue]Testing complete valid configuration[/bold blue]")

        config = DatabaseConfig(
            connection=DatabaseConnectionSettings(
                host="prod-db.example.com",
                port=5432,
                database="production",
                user="prod_user",
                password=SecretStr("super_secure_password_123!@#"),
                sslmode="verify-full",
            ),
            pool=PoolSettings(min_size=20, max_size=100, timeout=60.0),
            asyncpg=AsyncpgSettings(
                command_timeout=300.0,
                statement_cache_size=1024,
                max_queries=100_000,
                max_inactive_connection_lifetime=600.0,
            ),
        )

        # Verify all settings
        assert config.connection.host == "prod-db.example.com"
        assert config.connection.port == 5432
        assert config.connection.database == "production"
        assert config.connection.user == "prod_user"
        assert config.connection.password.get_secret_value() == "super_secure_password_123!@#"
        assert config.connection.sslmode == "verify-full"

        assert config.pool.min_size == 20
        assert config.pool.max_size == 100
        assert config.pool.timeout == 60.0

        assert config.asyncpg.command_timeout == 300.0
        assert config.asyncpg.statement_cache_size == 1024
        assert config.asyncpg.max_queries == 100_000
        assert config.asyncpg.max_inactive_connection_lifetime == 600.0

        # Verify URL
        url = config.url
        assert "prod-db.example.com" in url
        assert "production" in url
        assert "verify-full" in url

        console.print("[green]✓ Complete configuration is valid[/green]")
        console.print(
            f"[cyan]Generated URL (password hidden): {url.replace(config.connection.password.get_secret_value(), '***')}[/cyan]"
        )
