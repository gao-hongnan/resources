from __future__ import annotations

from .base import BaseRedisClient
from .cluster import RedisClusterClient
from .config import RedisConfig
from .standalone import RedisStandaloneClient


def create_redis_client(config: RedisConfig) -> BaseRedisClient:
    """Create appropriate Redis client based on configuration.

    Parameters
    ----------
    config : RedisConfig
        Redis configuration. If cluster.enabled is True, creates a cluster client;
        otherwise creates a standalone client.

    Returns
    -------
    BaseRedisClient
        Either RedisStandaloneClient or RedisClusterClient based on config.

    Examples
    --------
    Standalone mode:

    >>> config = RedisConfig(
    ...     connection=RedisConnectionSettings(host="localhost"),
    ...     cluster=RedisClusterSettings(enabled=False),
    ... )
    >>> client = create_redis_client(config)  # Returns RedisStandaloneClient

    Cluster mode:

    >>> config = RedisConfig(
    ...     connection=RedisConnectionSettings(host="clustercfg.xxx.cache.amazonaws.com"),
    ...     cluster=RedisClusterSettings(enabled=True),
    ... )
    >>> client = create_redis_client(config)  # Returns RedisClusterClient
    """
    if config.cluster.enabled:
        return RedisClusterClient(config)
    return RedisStandaloneClient(config)
