"""Redis module re-exports from infrastructure layer."""

from __future__ import annotations

from resources.infrastructure.redis import (
    BaseRedisClient,
    RedisClientType,
    RedisClusterClient,
    RedisClusterSettings,
    RedisConfig,
    RedisConnectionSettings,
    RedisDriverSettings,
    RedisPoolSettings,
    RedisSSLSettings,
    RedisStandaloneClient,
    create_redis_client,
)

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
