from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class DatabaseConnectionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, ge=1, le=65535, description="Database port")
    database: str = Field(default="postgres", description="Database name")
    user: str = Field(default="postgres", description="Database user")
    password: SecretStr = Field(default=SecretStr(""), description="Database password")
    sslmode: str = Field(
        default="prefer", description="SSL mode (disable, allow, prefer, require, verify-ca, verify-full)"
    )


class PoolSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_size: int = Field(default=5, ge=1, le=100, description="Minimum pool size")
    max_size: int = Field(default=20, ge=1, le=1000, description="Maximum pool size")
    timeout: float = Field(default=30.0, ge=1.0, le=300.0, description="Pool acquisition timeout (seconds)")


class AsyncpgSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_timeout: float = Field(default=60.0, ge=1.0, le=3600.0, description="Command timeout (seconds)")
    statement_cache_size: int = Field(default=256, ge=0, le=1024, description="Statement cache size (0 to disable)")
    max_queries: int = Field(default=50_000, ge=1, le=1_000_000, description="Max queries per connection")
    max_inactive_connection_lifetime: float = Field(
        default=300.0, ge=1.0, le=3600.0, description="Max connection idle time (seconds)"
    )


class DatabaseConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, validate_assignment=True)

    connection: DatabaseConnectionSettings = Field(
        default_factory=DatabaseConnectionSettings, description="Database connection settings"
    )
    pool: PoolSettings = Field(default_factory=PoolSettings, description="Connection pool settings")
    asyncpg: AsyncpgSettings = Field(default_factory=AsyncpgSettings, description="AsyncPG driver settings")

    @property
    def url(self) -> str:
        from urllib.parse import quote_plus

        pw = self.connection.password.get_secret_value()
        escaped_user = quote_plus(self.connection.user)
        escaped_pw = quote_plus(pw) if pw else ""
        auth = f"{escaped_user}:{escaped_pw}@" if pw else f"{escaped_user}@"

        return f"postgresql://{auth}{self.connection.host}:{self.connection.port}/{self.connection.database}?sslmode={self.connection.sslmode}"
