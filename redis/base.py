from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator, cast

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster
from redis.commands.core import AsyncCoreCommands

from ..core.enums import HealthCheckStatus
from ..logger import get_logger

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

    from .config import RedisConfig

logger: BoundLogger = get_logger(__name__)

type RedisClientType = Redis[bytes] | RedisCluster[bytes]
type RedisCommands = AsyncCoreCommands[bytes]


class BaseRedisClient(ABC):
    """Base class with shared Redis client logic."""

    def __init__(self, config: RedisConfig) -> None:
        self.config = config
        self._client: RedisClientType | None = None
        self._init_lock = asyncio.Lock()

    @abstractmethod
    async def ainitialize(self) -> None:
        """Initialize the Redis client."""

    @abstractmethod
    async def aclose(self) -> None:
        """Close the Redis client and release resources."""

    async def ahealth_check(self) -> HealthCheckStatus:
        """Check Redis connection health."""
        if self._client is None:
            return HealthCheckStatus.INITIALIZING

        try:
            # Cast is safe: both Redis and RedisCluster inherit from AsyncCoreCommands
            await cast(RedisCommands, self._client).ping()
            return HealthCheckStatus.HEALTHY
        except Exception as e:
            logger.error("Redis health check failed", exc_info=e)
            return HealthCheckStatus.UNHEALTHY

    @property
    def client(self) -> RedisClientType:
        """Get the Redis client directly.

        Returns
        -------
        RedisClientType
            The initialized Redis client.

        Raises
        ------
        RuntimeError
            If the client has not been initialized.
        """
        if self._client is None:
            raise RuntimeError("Redis client not initialized")
        return self._client

    @asynccontextmanager
    async def aget_client(self) -> AsyncIterator[RedisCommands]:
        """Get the Redis client within a context manager.

        Yields
        ------
        RedisCommands
            The initialized Redis client with typed command methods.

        Raises
        ------
        RuntimeError
            If the client has not been initialized.
        """
        if self._client is None:
            raise RuntimeError("Redis client not initialized")

        try:
            # Cast is safe: both Redis and RedisCluster inherit from AsyncCoreCommands
            yield cast(RedisCommands, self._client)
        except Exception as e:
            logger.error("Redis operation failed", exc_info=e)
            raise
