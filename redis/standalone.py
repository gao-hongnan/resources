from __future__ import annotations

from typing import TYPE_CHECKING

from redis.asyncio import ConnectionPool, Redis

from ..logger import get_logger
from .base import BaseRedisClient

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

    from .config import RedisConfig

logger: BoundLogger = get_logger(__name__)


class RedisStandaloneClient(BaseRedisClient):
    """Redis client for standalone mode with explicit connection pool.

    Uses a pre-configured ConnectionPool for controlled lifecycle management.

    Parameters
    ----------
    config : RedisConfig
        Redis configuration containing connection, pool, driver, and SSL settings.

    Examples
    --------
    >>> config = RedisConfig(
    ...     connection=RedisConnectionSettings(host="localhost"),
    ...     ssl=RedisSSLSettings(enabled=False),
    ...     pool=RedisPoolSettings(),
    ...     driver=RedisDriverSettings(),
    ... )
    >>> client = RedisStandaloneClient(config)
    >>> await client.ainitialize()
    >>> await client.aclose()
    """

    def __init__(self, config: RedisConfig) -> None:
        super().__init__(config)
        self._pool: ConnectionPool | None = None

    async def ainitialize(self) -> None:
        """Initialize the Redis standalone client with connection pool."""
        async with self._init_lock:
            if self._client is not None:
                return

            self._pool = ConnectionPool(**self.config.get_connection_pool_kwargs())
            self._client = Redis(connection_pool=self._pool)

            try:
                await self._client.ping()  # type: ignore[misc]
                logger.info(
                    "Redis standalone client initialized",
                    host=self.config.connection.host,
                    port=self.config.connection.port,
                    db=self.config.connection.db,
                    ssl_enabled=self.config.ssl.enabled,
                )
            except Exception as e:
                logger.error("Failed to initialize Redis standalone client", exc_info=e)
                raise

    async def aclose(self) -> None:
        """Close the Redis client and connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None

        logger.info("Redis standalone client closed")
