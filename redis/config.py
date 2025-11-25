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
    password: SecretStr = Field(..., description="Redis password for authentication")


class RedisSSLSettings(BaseModel):
    """Redis SSL/TLS settings."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, description="Enable SSL/TLS connections")
    ca_certs: str | None = Field(default=None, description="Path to CA certificate for SSL verification")


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


class RedisConfig(BaseModel):
    """Main Redis configuration."""

    model_config = ConfigDict(extra="ignore", frozen=True, validate_assignment=True)

    connection: RedisConnectionSettings
    ssl: RedisSSLSettings
    pool: RedisPoolSettings
    driver: RedisDriverSettings

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
        return f"{protocol}://{auth}{self.connection.host}:{self.connection.port}/{self.connection.db}"

    def get_connection_pool_kwargs(self, ssl_context: ssl_module.SSLContext | None = None) -> dict[str, Any]:
        """Get kwargs for redis.asyncio.ConnectionPool.

        Uses explicit ConnectionPool (not Redis internal pool) for:
        - Controlled lifecycle (init/close with app lifespan)
        - Centralized config (all settings in RedisConfig)
        - Observable resources (pool size, health checks)

        Parameters
        ----------
        ssl_context
            Optional SSL context for TLS connections. Pass None to disable SSL.

        Returns
        -------
        dict[str, Any]
            Kwargs ready for ConnectionPool(**kwargs).
        """
        password = self.connection.password.get_secret_value()

        return {
            **self.connection.model_dump(exclude={"password"}),
            "password": password,
            **self.pool.model_dump(),
            **self.driver.model_dump(),
            "ssl": ssl_context,
        }
