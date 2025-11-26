from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, cast

from redis.asyncio.cluster import RedisCluster

from ...logger import get_logger
from .base import BaseRedisClient

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

    from .config import RedisConfig

logger: BoundLogger = get_logger(__name__)


class RedisClusterClient(BaseRedisClient):
    """Redis client for cluster mode (AWS Redis OSS or self-hosted).

    RedisCluster manages its own connection pool internally (one per node).

    Parameters
    ----------
    config : RedisConfig
        Redis configuration containing connection, driver, SSL, and cluster settings.

    Examples
    --------
    AWS Redis OSS cluster mode:

    >>> config = RedisConfig(
    ...     connection=RedisConnectionSettings(host="clustercfg.my-cluster.xxx.use1.cache.amazonaws.com"),
    ...     ssl=RedisSSLSettings(enabled=True),
    ...     cluster=RedisClusterSettings(enabled=True),
    ... )
    >>> client = RedisClusterClient(config)
    >>> await client.ainitialize()
    >>> await client.aclose()

    Notes
    -----
    - Database selection (db) is not supported in cluster mode (always db 0)
    - require_full_coverage=False recommended for AWS Redis OSS cluster mode
      as slots may not all be covered during scaling operations
    """

    def __init__(self, config: RedisConfig) -> None:
        super().__init__(config)

    async def ainitialize(self) -> None:
        """Initialize the Redis cluster client."""
        async with self._init_lock:
            if self._client is not None:
                return

            self._client = RedisCluster(**self.config.get_cluster_kwargs())

            try:
                await cast(Awaitable[bool], self._client.ping())
                logger.info(
                    "Redis cluster client initialized",
                    host=self.config.connection.host,
                    port=self.config.connection.port,
                    ssl_enabled=self.config.ssl.enabled,
                    read_from_replicas=self.config.cluster.read_from_replicas,
                )
            except Exception as e:
                logger.error("Failed to initialize Redis cluster client", exc_info=e)
                raise

    async def aclose(self) -> None:
        """Close the Redis cluster client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

        logger.info("Redis cluster client closed")
