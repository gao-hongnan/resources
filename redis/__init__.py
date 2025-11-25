"""Redis module exports."""

from __future__ import annotations

from .base import BaseRedisClient, RedisClientType
from .cluster import RedisClusterClient
from .config import (
    RedisClusterSettings,
    RedisConfig,
    RedisConnectionSettings,
    RedisDriverSettings,
    RedisPoolSettings,
    RedisSSLSettings,
)
from .factory import create_redis_client
from .standalone import RedisStandaloneClient

__all__ = [
    # Clients
    "BaseRedisClient",
    "RedisClusterClient",
    "RedisStandaloneClient",
    # Factory
    "create_redis_client",
    # Types
    "RedisClientType",
    # Config
    "RedisClusterSettings",
    "RedisConfig",
    "RedisConnectionSettings",
    "RedisDriverSettings",
    "RedisPoolSettings",
    "RedisSSLSettings",
]
