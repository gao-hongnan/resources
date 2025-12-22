"""PostgreSQL infrastructure with asyncpg.

This module provides:

- `AsyncConnectionPool`: Single connection pool for one database
- `DatabaseCluster`: Primary/replica topology with explicit routing
- `DatabaseClusterConfig`: Configuration for cluster topology

Usage
-----
Single database::

    async with AsyncConnectionPool(config) as pool:
        rows = await pool.afetch("SELECT * FROM users")

Primary + replicas (recommended)::

    config = DatabaseClusterConfig.with_replica_hosts(
        primary_cfg,
        ["replica-1.db.com", "replica-2.db.com"],
    )
    async with DatabaseCluster.from_config(config) as cluster:
        await cluster.primary.aexecute("INSERT ...")  # Write
        await cluster.replica.afetch("SELECT ...")    # Read (stale OK)
"""

from .cluster import DatabaseCluster
from .config import (
    AsyncpgConfig,
    AsyncpgConnectionSettings,
    AsyncpgPoolSettings,
    AsyncpgServerSettings,
    AsyncpgStatementCacheSettings,
    DatabaseClusterConfig,
)
from .exceptions import AsyncpgWrapperError, PoolNotInitializedError
from .health import ClusterHealthResult, HealthCheckResult, PoolHealthBase, ReplicaHealthInfo
from .pool import AsyncConnectionPool, IsolationLevel

__all__ = [
    "AsyncConnectionPool",
    "AsyncpgConfig",
    "AsyncpgConnectionSettings",
    "AsyncpgPoolSettings",
    "AsyncpgServerSettings",
    "AsyncpgStatementCacheSettings",
    "AsyncpgWrapperError",
    "ClusterHealthResult",
    "DatabaseCluster",
    "DatabaseClusterConfig",
    "HealthCheckResult",
    "IsolationLevel",
    "PoolHealthBase",
    "PoolNotInitializedError",
    "ReplicaHealthInfo",
]
