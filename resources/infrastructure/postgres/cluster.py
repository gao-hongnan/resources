"""Database cluster with explicit primary/replica access.

Why Explicit Routing?
---------------------
Auto-routing (sending reads to replicas based on a `readonly` flag) seems
convenient but introduces subtle, hard-to-debug production issues:

1. **Read-Your-Writes Inconsistency**
   After writing to primary, a subsequent read routed to a replica may
   return stale data due to replication lag. This breaks user expectations
   in flows like: submit form -> redirect -> see submitted data.

   Example failure mode::

       await pool.aexecute("INSERT INTO users (name) VALUES ($1)", "Alice")
       # Auto-routed to replica, but replication lag means Alice isn't there yet
       user = await pool.afetchrow("SELECT * FROM users WHERE name = $1", "Alice")
       assert user is not None  # FAILS intermittently

2. **Replication Lag Unpredictability**
   Lag varies from milliseconds to seconds depending on write load, network
   conditions, and replica capacity. Auto-routing cannot know when it's
   "safe" to read from a replica - only the developer knows the consistency
   requirements of each query.

3. **Transaction Boundary Confusion**
   A transaction on primary followed by an auto-routed "read-only" query
   breaks the ACID guarantees developers expect. The read sees a different
   snapshot than the transaction.

4. **Debugging Difficulty**
   When data inconsistencies occur, tracing whether a query went to primary
   or replica adds significant debugging complexity. Explicit routing makes
   the data flow obvious in code review and logs.

5. **False Sense of Safety**
   The `readonly=True` parameter suggests the query is read-only, but the
   real question is: "Does this query need consistent data?" - a completely
   different concern that only the developer can answer.

Industry Standard
-----------------
Major frameworks adopted explicit routing after learning these lessons:

- **Django**: ``using('default')`` vs ``using('replica')``
- **Rails**: ``connected_to(role: :reading)`` vs ``connected_to(role: :writing)``
- **SQLAlchemy**: Separate ``Session`` objects bound to different engines
- **Spring**: ``@Transactional(readOnly=true)`` with explicit datasource routing

The pattern forces developers to think about data consistency at the point
of each query - exactly when that decision should be made.

When to Use Replicas
--------------------
Replicas are appropriate when ALL of these are true:

- Query is read-only
- Stale data (seconds to minutes old) is acceptable
- Query is not part of a read-after-write flow
- Query is heavy/analytical and would burden primary

Examples:
- Dashboard analytics: ``cluster.replica.afetch("SELECT COUNT(*) FROM orders")``
- Report generation: replicas are ideal
- User profile after update: use PRIMARY for consistency
- Search results: replicas fine (eventual consistency acceptable)

Usage
-----
>>> async with DatabaseCluster.from_configs(primary_cfg, [replica_cfg]) as cluster:
...     # Writes always go to primary
...     await cluster.primary.aexecute("INSERT INTO users (name) VALUES ($1)", "Alice")
...
...     # Read-after-write: use primary for consistency
...     user = await cluster.primary.afetchrow(
...         "SELECT * FROM users WHERE name = $1", "Alice"
...     )
...
...     # Analytics query: replicas are fine (stale data acceptable)
...     stats = await cluster.replica.afetch(
...         "SELECT date, COUNT(*) FROM orders GROUP BY date"
...     )

See Also:
--------
- https://brandur.org/postgres-reads (Why read replicas are tricky)
- https://jepsen.io/consistency (Consistency model deep dive)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Self

from hypervigilant.structlog import get_logger

from .config import AsyncpgConfig, DatabaseClusterConfig
from .enums import HealthStatus
from .health import ClusterHealthResult, ReplicaHealthInfo
from .pool import AsyncConnectionPool

if TYPE_CHECKING:
    import types

logger = get_logger(__name__)


class DatabaseCluster:
    """Manages primary + replica pools with EXPLICIT access.

    This class intentionally does NOT auto-route queries. Users must
    explicitly choose ``.primary`` or ``.replica`` for each operation.
    See module docstring for detailed rationale.

    Attributes
    ----------
    primary : AsyncConnectionPool
        The primary (read-write) connection pool.
    replica : AsyncConnectionPool
        A replica pool (round-robin selection), or primary if no replicas.

    Examples
    --------
    >>> cluster = DatabaseCluster.from_configs(primary_cfg, [replica_cfg])
    >>> async with cluster:
    ...     await cluster.primary.aexecute("INSERT ...")  # Write
    ...     await cluster.replica.afetch("SELECT ...")    # Read (stale OK)
    """

    __slots__ = ("_primary", "_replica_index", "_replicas")

    def __init__(
        self,
        primary: AsyncConnectionPool,
        replicas: list[AsyncConnectionPool] | None = None,
    ) -> None:
        """Initialize cluster with primary and optional replicas.

        Parameters
        ----------
        primary
            The primary (read-write) connection pool.
        replicas
            Optional list of replica (read-only) connection pools.
            If empty/None, ``.replica`` returns primary as fallback.

        Note
        ----
        Pools should be configured WITHOUT internal replica settings.
        The cluster manages topology; individual pools manage connections.
        """
        self._primary = primary
        self._replicas = replicas or []
        self._replica_index = 0

    async def __aenter__(self) -> Self:
        """Initialize all pools in the cluster."""
        await self.ainitialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Close all pools in the cluster."""
        if exc_type is not None and exc_val is not None:
            logger.error(
                "DatabaseCluster exiting with exception",
                exc_type=exc_type.__name__,
                exc_val=str(exc_val),
            )
        await self.aclose()

    @classmethod
    def from_configs(
        cls: type[Self],
        primary_config: AsyncpgConfig,
        replica_configs: tuple[AsyncpgConfig, ...] | None = None,
    ) -> Self:
        return cls.from_config(DatabaseClusterConfig(primary=primary_config, replicas=replica_configs or ()))

    @classmethod
    def from_config(cls, config: DatabaseClusterConfig) -> Self:
        """Create cluster from a unified cluster configuration.

        This is the preferred way to create a cluster when loading
        configuration from files or using dependency injection.

        Parameters
        ----------
        config
            Complete cluster configuration including primary and replicas.

        Returns
        -------
        Self
            A new DatabaseCluster instance (not yet initialized).

        Examples
        --------
        >>> config = DatabaseClusterConfig.with_replica_hosts(
        ...     primary_cfg,
        ...     ["replica-1.db.com", "replica-2.db.com"],
        ... )
        >>> async with DatabaseCluster.from_config(config) as cluster:
        ...     await cluster.primary.aexecute("INSERT ...")
        """
        primary = AsyncConnectionPool(config.primary)
        replicas = [AsyncConnectionPool(cfg) for cfg in config.replicas]
        return cls(primary, replicas)

    async def ainitialize(self) -> None:
        """Initialize all pools in the cluster.

        Raises
        ------
        Exception
            If primary pool fails to initialize. Replica failures are
            logged but do not prevent cluster initialization.
        """
        await self._primary.ainitialize()
        logger.info("Primary pool initialized")

        results = await asyncio.gather(*(replica.ainitialize() for replica in self._replicas), return_exceptions=True)
        initialized_replicas: list[AsyncConnectionPool] = []
        for i, (replica, result) in enumerate(zip(self._replicas, results, strict=True)):
            if isinstance(result, BaseException):
                logger.warning(
                    "Replica pool failed to initialize",
                    replica_index=i,
                    error=str(result),
                )
            else:
                initialized_replicas.append(replica)
                logger.info("Replica pool initialized", replica_index=i)

        self._replicas = initialized_replicas

        logger.info("Database cluster initialized", replica_count=len(self._replicas))

    async def aclose(self) -> None:
        """Close all pools in the cluster."""
        await self._primary.aclose()
        logger.info("Primary pool closed")

        results = await asyncio.gather(*(replica.aclose() for replica in self._replicas), return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Replica pool failed to close",
                    replica_index=i,
                    error=str(result),
                )
            else:
                logger.info("Replica pool closed", replica_index=i)

        logger.info("Database cluster closed")

    async def ahealth_check(self) -> ClusterHealthResult:
        """Check health of all pools in the cluster.

        Returns
        -------
        ClusterHealthResult
            Aggregated health status of primary and all replicas.
        """
        primary_health = await self._primary.ahealth_check()

        health_results = await asyncio.gather(
            *(replica.ahealth_check() for replica in self._replicas),
            return_exceptions=True,
        )

        replica_infos: list[ReplicaHealthInfo] = []
        healthy_count = 0

        for i, result in enumerate(health_results):
            if isinstance(result, BaseException):
                replica_infos.append(
                    ReplicaHealthInfo(
                        host=f"replica-{i}",
                        port=5432,
                        status=HealthStatus.UNHEALTHY,
                        pool_size=0,
                        pool_max_size=0,
                        pool_idle_size=0,
                        latency_s=None,
                        message=str(result),
                    )
                )
            else:
                replica_health = result
                is_healthy = replica_health.status == HealthStatus.HEALTHY
                if is_healthy:
                    healthy_count += 1

                replica_infos.append(
                    ReplicaHealthInfo(
                        host=f"replica-{i}",
                        port=5432,
                        status=replica_health.status,
                        pool_size=replica_health.pool_size,
                        pool_max_size=replica_health.pool_max_size,
                        pool_idle_size=replica_health.pool_idle_size,
                        latency_s=replica_health.latency_s,
                        message=replica_health.message,
                    )
                )

        if primary_health.status != HealthStatus.HEALTHY:
            overall_status = HealthStatus.UNHEALTHY
        elif healthy_count < len(self._replicas):
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return ClusterHealthResult(
            status=overall_status,
            primary=primary_health,
            replicas=tuple(replica_infos),
            healthy_replica_count=healthy_count,
            total_replica_count=len(self._replicas),
        )

    async def awarmup(self) -> None:
        """Warm up primary and all replica pools.

        Raises
        ------
        Exception
            If primary warmup fails. Replica failures are logged as warnings.
        """
        await self._primary.awarmup()

        for i, replica in enumerate(self._replicas):
            try:
                await replica.awarmup()
            except Exception as e:
                logger.warning("Replica warmup failed", replica_index=i, error=str(e))

    @property
    def primary(self) -> AsyncConnectionPool:
        """Access primary pool for writes and consistent reads.

        Use this for:

        - All write operations (INSERT, UPDATE, DELETE)
        - Read-after-write scenarios (consistency required)
        - Transactions that mix reads and writes
        - Any read where you need the latest data

        Returns
        -------
        AsyncConnectionPool
            The primary connection pool.
        """
        return self._primary

    @property
    def replica(self) -> AsyncConnectionPool:
        """Access a replica pool for read-only queries.

        Uses round-robin selection across healthy replicas.
        Returns primary as fallback if no replicas are configured.

        Use this for:

        - Analytics and reporting queries
        - Dashboard data where slight staleness is acceptable
        - Heavy read workloads to offload primary
        - Search/browse operations

        Do NOT use for:

        - Read-after-write scenarios
        - Data that must be current (e.g., balance checks)
        - Queries within a transaction started on primary

        Returns:
        -------
        AsyncConnectionPool
            A replica pool, or primary if no replicas available.

        Warning:
        -------
        Replication lag means recently written data may not be visible.
        When in doubt, use ``.primary``.
        """
        if not self._replicas:
            return self._primary

        pool = self._replicas[self._replica_index % len(self._replicas)]
        self._replica_index += 1
        return pool

    @property
    def replica_count(self) -> int:
        """Return the number of healthy replica pools."""
        return len(self._replicas)

    @property
    def has_replicas(self) -> bool:
        """Check if cluster has replica pools configured."""
        return len(self._replicas) > 0
