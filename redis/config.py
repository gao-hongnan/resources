from __future__ import annotations

import ssl as ssl_module
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class RedisConnectionSettings(BaseModel):
    """Redis connection settings."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, ge=1, le=65535, description="Redis port")
    db: int = Field(default=0, ge=0, le=15, description="Redis database number")
    username: str | None = Field(default=None, description="Redis username for ACL (Redis 6+)")
    password: SecretStr | None = Field(default=None, description="Redis password for authentication")


class RedisSSLSettings(BaseModel):
    """Redis SSL/TLS settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Enable SSL/TLS connections")
    ssl_ca_certs: str | None = Field(default=None, description="Path to CA certificate for SSL verification")


class RedisPoolSettings(BaseModel):
    """Redis connection pool settings."""

    model_config = ConfigDict(extra="forbid")

    max_connections: int = Field(
        default=50,
        ge=10,
        le=1000,
        description="Maximum connections in pool",
    )
    health_check_interval: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Health check interval in seconds",
    )


class RedisDriverSettings(BaseModel):
    """Redis driver-specific settings."""

    model_config = ConfigDict(extra="forbid")

    socket_keepalive: bool = Field(default=True, description="Enable TCP keepalive")
    socket_timeout: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Socket timeout in seconds",
    )
    socket_connect_timeout: float = Field(
        default=5.0,
        ge=0.1,
        le=60.0,
        description="Socket connect timeout in seconds",
    )
    retry_on_timeout: bool = Field(default=True, description="Retry operations on timeout")
    decode_responses: bool = Field(
        default=True,
        description="Decode responses to strings instead of bytes",
    )


class RedisClusterSettings(BaseModel):
    """Redis Cluster settings (AWS Redis OSS cluster mode or self-hosted)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description="Enable cluster mode (uses RedisCluster client)",
    )
    require_full_coverage: bool = Field(
        default=False,
        description="Require all hash slots to be covered (set False during scaling)",
    )
    read_from_replicas: bool = Field(
        default=False,
        description="Distribute read commands across replicas for better read throughput",
    )


class RedisConfig(BaseModel):
    """Main Redis configuration."""

    model_config = ConfigDict(extra="ignore", frozen=True, validate_assignment=True)

    connection: RedisConnectionSettings
    ssl: RedisSSLSettings
    pool: RedisPoolSettings
    driver: RedisDriverSettings
    cluster: RedisClusterSettings = Field(default_factory=RedisClusterSettings)

    @property
    def url(self) -> str:
        """Build Redis connection URL."""
        auth = ""
        if self.connection.username and self.connection.password:
            pw = self.connection.password.get_secret_value()
            auth = f"{self.connection.username}:{pw}@"
        elif self.connection.password:
            pw = self.connection.password.get_secret_value()
            auth = f":{pw}@"

        protocol = "rediss" if self.ssl.enabled else "redis"
        base_url = f"{protocol}://{auth}{self.connection.host}:{self.connection.port}"

        # Cluster mode doesn't support database selection (always db 0)
        if self.cluster.enabled:
            return base_url
        return f"{base_url}/{self.connection.db}"

    def get_connection_pool_kwargs(self) -> dict[str, Any]:
        """Get kwargs for redis.asyncio.ConnectionPool.

        Uses explicit ConnectionPool (not Redis internal pool) for:
        - Controlled lifecycle (init/close with app lifespan)
        - Centralized config (all settings in RedisConfig)
        - Observable resources (pool size, health checks)

        Returns
        -------
        dict[str, Any]
            Kwargs ready for ConnectionPool(**kwargs).
        """
        password = self.connection.password.get_secret_value() if self.connection.password else None

        kwargs: dict[str, Any] = {
            **self.connection.model_dump(exclude={"password"}),
            "password": password,
            **self.pool.model_dump(),
            **self.driver.model_dump(),
        }

        if self.ssl.enabled:
            kwargs["ssl"] = self._build_ssl_context()

        return kwargs

    def get_cluster_kwargs(self) -> dict[str, Any]:
        """Get kwargs for redis.asyncio.cluster.RedisCluster.

        RedisCluster manages its own connection pool internally, so pool settings
        are not included. Database selection (db) is not supported in cluster mode.

        Returns
        -------
        dict[str, Any]
            Kwargs ready for RedisCluster(**kwargs).
        """
        password = self.connection.password.get_secret_value() if self.connection.password else None

        kwargs: dict[str, Any] = {
            **self.connection.model_dump(exclude={"password", "db"}),
            "password": password,
            **self.cluster.model_dump(exclude={"enabled"}),
            **self.driver.model_dump(exclude={"retry_on_timeout"}),
        }

        if self.ssl.enabled:
            kwargs["ssl"] = self._build_ssl_context()

        return kwargs

    def _build_ssl_context(self) -> ssl_module.SSLContext:
        """Build SSL context from ssl settings."""
        context = ssl_module.create_default_context()
        if self.ssl.ssl_ca_certs:
            context.load_verify_locations(self.ssl.ssl_ca_certs)
        return context
