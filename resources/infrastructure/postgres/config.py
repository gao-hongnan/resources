"""Configuration models for asyncpg connection pools.

This module provides Pydantic models for configuring PostgreSQL connections.

- `AsyncpgConfig`: Configuration for a single connection pool
- `DatabaseClusterConfig`: Configuration for primary + replica topology
"""

from __future__ import annotations

from typing import Any, Literal, Self
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field, SecretStr, computed_field


class AsyncpgConnectionSettings(BaseModel):
    """Connection settings for a PostgreSQL database."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(default="localhost")
    port: int = Field(default=5432, ge=1, le=65535)
    database: str = Field(default="transcreation")
    user: str = Field(default="postgres")
    password: SecretStr | None = Field(default=None)


class AsyncpgPoolSettings(BaseModel):
    """Connection pool settings."""

    model_config = ConfigDict(extra="forbid")

    min_size: int = Field(default=10, ge=1, le=100)
    max_size: int = Field(default=20, ge=1, le=200)
    max_inactive_connection_lifetime: float = Field(default=300.0, ge=0.0)
    command_timeout: float = Field(default=60.0, ge=1.0, le=300.0)


class AsyncpgStatementCacheSettings(BaseModel):
    """Statement cache settings for prepared statements."""

    model_config = ConfigDict(extra="forbid")

    max_size: int = Field(default=256, ge=0, le=1000)
    max_lifetime: int = Field(default=300, ge=0)
    max_cacheable_statement_size: int = Field(default=15360, ge=0)


class AsyncpgServerSettings(BaseModel):
    """PostgreSQL server settings passed to the connection."""

    model_config = ConfigDict(extra="forbid")

    application_name: str = Field(default="transcreation")
    jit: Literal["on", "off"] = Field(default="off")


class AsyncpgConfig(BaseModel):
    """Complete configuration for an asyncpg connection pool.

    Examples
    --------
    >>> config = AsyncpgConfig(
    ...     connection=AsyncpgConnectionSettings(
    ...         host="localhost",
    ...         database="mydb",
    ...         user="postgres",
    ...         password=SecretStr("secret"),
    ...     ),
    ...     pool=AsyncpgPoolSettings(min_size=5, max_size=20),
    ... )
    >>> async with AsyncConnectionPool(config) as pool:
    ...     await pool.afetch("SELECT 1")
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    connection: AsyncpgConnectionSettings = Field(default_factory=AsyncpgConnectionSettings)
    pool: AsyncpgPoolSettings = Field(default_factory=AsyncpgPoolSettings)
    statement_cache: AsyncpgStatementCacheSettings = Field(default_factory=AsyncpgStatementCacheSettings)
    server_settings: AsyncpgServerSettings = Field(default_factory=AsyncpgServerSettings)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dsn(self) -> str:
        """Build PostgreSQL DSN from connection settings."""
        password = self.connection.password.get_secret_value() if self.connection.password else ""
        escaped_user = quote_plus(self.connection.user)
        escaped_password = quote_plus(password) if password else ""
        auth = f"{escaped_user}:{escaped_password}@" if escaped_password else f"{escaped_user}@"
        return f"postgresql://{auth}{self.connection.host}:{self.connection.port}/{self.connection.database}"

    def to_pool_params(self) -> dict[str, Any]:
        """Convert config to asyncpg.create_pool() parameters.

        Returns
        -------
        dict[str, Any]
            Parameters for asyncpg.create_pool().
        """
        return {
            "dsn": self.dsn,
            **self.pool.model_dump(),
            "statement_cache_size": self.statement_cache.max_size,
            "max_cached_statement_lifetime": self.statement_cache.max_lifetime,
            "max_cacheable_statement_size": self.statement_cache.max_cacheable_statement_size,
            "server_settings": self.server_settings.model_dump(),
        }

    def for_replica(self, host: str, port: int | None = None) -> Self:
        """Create a replica config by copying this config with a different host.

        Replicas typically share database, credentials, and pool settings with
        the primary - only the host (and occasionally port) differs.

        Parameters
        ----------
        host
            Hostname for the replica database.
        port
            Optional port override. Defaults to same as primary.

        Returns
        -------
        Self
            A new config with the specified host (and optionally port).

        Examples
        --------
        >>> primary = AsyncpgConfig(
        ...     connection=AsyncpgConnectionSettings(host="primary.db.com", ...)
        ... )
        >>> replica1 = primary.for_replica("replica-1.db.com")
        >>> replica2 = primary.for_replica("replica-2.db.com", port=5433)
        """
        new_connection = self.connection.model_copy(
            update={"host": host, "port": port if port is not None else self.connection.port}
        )
        return self.model_copy(update={"connection": new_connection})


class DatabaseClusterConfig(BaseModel):
    """Configuration for a database cluster with primary and replicas.

    This provides a single configuration object for the entire cluster topology,
    useful for loading from config files or dependency injection.

    Examples
    --------
    >>> # Option 1: Explicit replica configs
    >>> config = DatabaseClusterConfig(
    ...     primary=primary_cfg,
    ...     replicas=(
    ...         primary_cfg.for_replica("replica-1.db.com"),
    ...         primary_cfg.for_replica("replica-2.db.com"),
    ...     ),
    ... )

    >>> # Option 2: Convenience helper
    >>> config = DatabaseClusterConfig.with_replica_hosts(
    ...     primary_cfg,
    ...     ["replica-1.db.com", "replica-2.db.com"],
    ... )

    >>> # Option 3: From config file
    >>> config = DatabaseClusterConfig.model_validate(yaml.safe_load(f))

    >>> # Create cluster
    >>> cluster = DatabaseCluster.from_config(config)
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    primary: AsyncpgConfig
    replicas: tuple[AsyncpgConfig, ...] = Field(default_factory=tuple)

    @classmethod
    def with_replica_hosts(
        cls,
        primary: AsyncpgConfig,
        hosts: list[str],
    ) -> Self:
        """Create cluster config with replicas derived from primary.

        This is a convenience method when replicas share all settings with
        the primary except for the hostname.

        Parameters
        ----------
        primary
            Primary database configuration.
        hosts
            List of replica hostnames. Credentials, port, and pool settings
            are inherited from primary.

        Returns
        -------
        Self
            A new cluster config with replicas for each host.

        Examples
        --------
        >>> config = DatabaseClusterConfig.with_replica_hosts(
        ...     primary_cfg,
        ...     ["replica-1.db.com", "replica-2.db.com"],
        ... )
        """
        replicas = tuple(primary.for_replica(host) for host in hosts)
        return cls(primary=primary, replicas=replicas)
