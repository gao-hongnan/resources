from __future__ import annotations

import asyncio
import ssl as ssl_module
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

from redis.asyncio import ConnectionPool, Redis

from pixiu.core.enums import HealthCheckStatus
from pixiu.logger import get_logger

from .config import RedisConfig

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

logger: BoundLogger = get_logger(__name__)


class RedisClient:
    """Async Redis client with explicit connection pool management.

    Uses a pre-configured ConnectionPool rather than letting Redis create
    one internally because:

    - **Explicit lifecycle**: Pool init/close controlled by application
    lifespan
    - **Centralized config**: All connection settings in one place
    (RedisConfig)
    - **Resource visibility**: Pool size and health directly observable
    - **Testability**: Pool can be mocked/injected for testing

    Parameters
    ----------
    config : RedisConfig
        Redis configuration containing connection, pool, driver, and SSL
    settings.

    Examples
    --------
    >>> config =
    RedisConfig(connection=RedisConnectionSettings(host="localhost"))
    >>> client = RedisClient(config)
    >>> await client.ainitialize()
    >>> await client.aclose()
    """

    def __init__(self, config: RedisConfig) -> None:
        self.config = config
        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None
        self._init_lock = asyncio.Lock()

    async def ainitialize(self) -> None:
        async with self._init_lock:
            if self._pool is not None:
                return

            ssl_context: ssl_module.SSLContext | None = None
            if self.config.ssl.enabled:
                ssl_context = ssl_module.create_default_context()
                if self.config.ssl.ca_certs:
                    ssl_context.load_verify_locations(self.config.ssl.ca_certs)

            self._pool = ConnectionPool(**self.config.get_connection_pool_kwargs(ssl_context))
            self._client = Redis(connection_pool=self._pool)

            try:
                await self._client.ping()  # type: ignore[misc]
                logger.info(
                    "Redis client initialized successfully",
                    host=self.config.connection.host,
                    port=self.config.connection.port,
                    db=self.config.connection.db,
                    ssl_enabled=self.config.ssl.enabled,
                )
            except Exception as e:
                logger.error("Failed to initialize Redis client", exc_info=e)
                raise

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None

        logger.info("Redis client closed")

    async def ahealth_check(self) -> HealthCheckStatus:
        if self._client is None:
            return HealthCheckStatus.INITIALIZING

        try:
            await self._client.ping()  # type: ignore[misc]
            return HealthCheckStatus.HEALTHY
        except Exception as e:
            logger.error("Redis health check failed", exc_info=e)
            return HealthCheckStatus.UNHEALTHY

    @asynccontextmanager
    async def aget_client(self) -> AsyncIterator[Redis]:
        if self._client is None:
            raise RuntimeError("Redis client not initialized")

        try:
            yield self._client
        except Exception as e:
            logger.error("Redis operation failed", exc_info=e)
            raise

    @property
    def client(self) -> Redis:
        if self._client is None:
            raise RuntimeError("Redis client not initialized")
        return self._client
