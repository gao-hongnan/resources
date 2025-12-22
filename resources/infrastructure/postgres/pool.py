"""Async connection pool for PostgreSQL using asyncpg.

This module provides a single connection pool abstraction. For primary/replica
topology with explicit routing, use `DatabaseCluster` instead.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, Literal, Self

import asyncpg
from asyncpg import Pool, Record
from hypervigilant.structlog import StructlogConfig, configure_logging, get_logger
from profilist.timer import Timer

from .exceptions import PoolNotInitializedError
from .health import HealthCheckResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable, Sequence
    from types import TracebackType

    from asyncpg.cursor import CursorIterator
    from asyncpg.pool import PoolConnectionProxy

    from .config import AsyncpgConfig

configure_logging(
    config=StructlogConfig(service_name="leitmotif.infrastructure.postgres.pool", json_output=True, json_indent=4)
)
logger = get_logger(__name__)

type IsolationLevel = Literal["read_uncommitted", "read_committed", "repeatable_read", "serializable"]


class AsyncConnectionPool:
    """Async connection pool for a single PostgreSQL database.

    For primary/replica topology, use `DatabaseCluster` which wraps
    multiple `AsyncConnectionPool` instances with explicit routing.

    Examples
    --------
    >>> async with AsyncConnectionPool(config) as pool:
    ...     rows = await pool.afetch("SELECT * FROM users")
    ...     await pool.aexecute("INSERT INTO users (name) VALUES ($1)", "Alice")
    """

    # NOTE: Explain why we use __slots__
    __slots__ = ("_config", "_init_lock", "_pool")

    def __init__(self, config: AsyncpgConfig) -> None:
        self._config = config
        self._pool: Pool[Record] | None = None
        self._init_lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        await self.ainitialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None and exc_val is not None:
            logger.error(
                "AsyncConnectionPool context manager exiting with exception",
                exc_type=exc_type.__name__,
                exc_val=str(exc_val),
            )
        await self.aclose()

    @property
    def pool(self) -> Pool[Record]:
        """Access the underlying asyncpg pool.

        Raises
        ------
        PoolNotInitializedError
            If pool has not been initialized via `ainitialize()`.
        """
        if self._pool is None:
            # NOTE: how can we make the message not repeat itself if I raise this error many times?
            msg = "Pool not initialized. Call ainitialize() first."
            raise PoolNotInitializedError(msg)
        return self._pool

    async def ainitialize(self) -> None:
        """Initialize the connection pool.

        This is idempotent - calling multiple times is safe.

        Thread Safety
        -------------
        An asyncio lock ensures that concurrent calls to this method do not
        create multiple pools. Without the lock, a race condition could occur
        when the same pool instance is used concurrently before initialization:

        >>> pool = AsyncConnectionPool(config)
        >>> await asyncio.gather(
        ...     task_using_pool(pool),  # Both call ainitialize()
        ...     task_using_pool(pool),
        ... )

        In this scenario:

        1. Task A checks self._pool is not None -> False
        2. Task A awaits create_pool() (yields control)
        3. Task B checks self._pool is not None -> still False
        4. Both tasks create pools; one is orphaned (resource leak)

        The lock serializes initialization, preventing this scenario.
        """
        async with self._init_lock:
            if self._pool is not None:
                return

            self._pool = await asyncpg.create_pool(**self._config.to_pool_params())

            async with self._pool.acquire() as conn:
                # NOTE: what is this line doing?
                await conn.execute("SELECT 1")

            logger.info("AsyncConnectionPool initialized", **self._config.to_pool_params())

    async def aclose(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("AsyncConnectionPool closed")

    async def ahealth_check(self) -> HealthCheckResult:
        """Check pool health by executing a simple query.

        Returns
        -------
        HealthCheckResult
            Health status with latency and pool statistics.
        """
        if self._pool is None:
            return HealthCheckResult.initializing(pool_max_size=self._config.pool.max_size)

        try:
            async with Timer(silent=True) as t, self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            latency_s = t.elapsed_seconds
        except Exception as e:
            return HealthCheckResult.unhealthy(
                pool_max_size=self._config.pool.max_size,
                error=str(e),
            )

        return HealthCheckResult.healthy(
            pool_size=self._pool.get_size(),
            pool_max_size=self._pool.get_max_size(),
            latency_s=latency_s,
            pool_idle_size=self._pool.get_idle_size(),
        )

    async def awarmup(self) -> None:
        """Ensure all min_size connections are established and validated.

        Call this during startup before accepting traffic to avoid
        first-request latency.

        Raises
        ------
        Exception
            If any connection fails to establish or validate.
        """
        if self._pool is None:
            await self.ainitialize()

        target = self._config.pool.min_size
        connections: list[PoolConnectionProxy[Record]] = []
        try:
            for _ in range(target):
                conn = await self._pool.acquire()  # type: ignore[union-attr]
                await conn.fetchval("SELECT 1")
                connections.append(conn)
        finally:
            for conn in connections:
                await self._pool.release(conn)  # type: ignore[union-attr]

        logger.info("Pool warmup completed", connections=target)

    @asynccontextmanager
    async def aacquire(self) -> AsyncIterator[PoolConnectionProxy[Record]]:
        """Acquire a connection from the pool.

        Yields
        ------
        PoolConnectionProxy[Record]
            A connection proxy that is returned to the pool on exit.
        """
        async with self.pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def atransaction(
        self,
        isolation: IsolationLevel = "read_committed",
        *,
        readonly: bool = False,
        deferrable: bool = False,
    ) -> AsyncIterator[PoolConnectionProxy[Record]]:
        """Acquire a connection and start a transaction.

        Parameters
        ----------
        isolation
            Transaction isolation level.
        readonly
            If True, the transaction is read-only (PostgreSQL optimization hint).
        deferrable
            If True and readonly=True, allows deferrable transactions.

        Yields
        ------
        PoolConnectionProxy[Record]
            A connection within a transaction context.
        """
        async with (
            self.aacquire() as conn,
            conn.transaction(
                isolation=isolation,
                readonly=readonly,
                deferrable=deferrable,
            ),
        ):
            yield conn

    @asynccontextmanager
    async def acursor(
        self,
        query: str,
        *args: object,
        prefetch: int = 50,
        timeout: float | None = None,
        isolation: IsolationLevel = "read_committed",
        readonly: bool = False,
        deferrable: bool = False,
    ) -> AsyncIterator[CursorIterator[Record]]:
        """Execute a query and return a cursor for iteration.

        Parameters
        ----------
        query
            SQL query to execute.
        *args
            Query parameters.
        prefetch
            Number of rows to prefetch.
        timeout
            Query timeout in seconds.
        isolation
            Transaction isolation level.
        readonly
            If True, the transaction is read-only.
        deferrable
            If True and readonly=True, allows deferrable transactions.

        Yields
        ------
        CursorIterator[Record]
            Async iterator over query results.
        """
        async with self.atransaction(
            isolation=isolation,
            readonly=readonly,
            deferrable=deferrable,
        ) as conn:
            cursor_factory = conn.cursor(query, *args, prefetch=prefetch, timeout=timeout)
            yield cursor_factory.__aiter__()

    async def aexecute(self, query: str, *args: object, timeout: float | None = None) -> str:
        """Execute a query without returning results.

        Parameters
        ----------
        query
            SQL query to execute.
        *args
            Query parameters.
        timeout
            Query timeout in seconds.

        Returns
        -------
        str
            Command status string (e.g., "INSERT 0 1").
        """
        async with self.aacquire() as conn:
            return await conn.execute(query, *args, timeout=timeout)

    async def aexecutemany(self, query: str, args: Iterable[Sequence[object]], timeout: float | None = None) -> None:
        """Execute a query with multiple parameter sets.

        Parameters
        ----------
        query
            SQL query to execute.
        args
            Iterable of parameter sequences.
        timeout
            Query timeout in seconds.
        """
        async with self.aacquire() as conn:
            await conn.executemany(query, args, timeout=timeout)

    async def afetch(self, query: str, *args: object, timeout: float | None = None) -> list[Record]:
        """Execute a query and return all rows.

        Parameters
        ----------
        query
            SQL query to execute.
        *args
            Query parameters.
        timeout
            Query timeout in seconds.

        Returns
        -------
        list[Record]
            All rows returned by the query.
        """
        async with self.aacquire() as conn:
            return await conn.fetch(query, *args, timeout=timeout)

    async def afetchrow(self, query: str, *args: object, timeout: float | None = None) -> Record | None:
        """Execute a query and return the first row.

        Parameters
        ----------
        query
            SQL query to execute.
        *args
            Query parameters.
        timeout
            Query timeout in seconds.

        Returns
        -------
        Record | None
            First row or None if no rows returned.
        """
        async with self.aacquire() as conn:
            return await conn.fetchrow(query, *args, timeout=timeout)

    async def afetchval(self, query: str, *args: object, timeout: float | None = None) -> Any:
        """Execute a query and return the first value of the first row.

        Parameters
        ----------
        query
            SQL query to execute.
        *args
            Query parameters.
        timeout
            Query timeout in seconds.

        Returns
        -------
        Any
            First column of first row, or None if no rows returned.
        """
        async with self.aacquire() as conn:
            return await conn.fetchval(query, *args, timeout=timeout)

    async def acopy_records_to_table(
        self,
        table_name: str,
        records: Sequence[Sequence[object]],
        columns: Sequence[str],
        timeout: float | None = None,
    ) -> str:
        """Bulk copy records to a table using PostgreSQL COPY.

        Parameters
        ----------
        table_name
            Target table name.
        records
            List of tuples containing row data.
        columns
            Column names in the target table.
        timeout
            Operation timeout in seconds.

        Returns
        -------
        str
            COPY command status string.
        """
        async with self.aacquire() as conn:
            return await conn.copy_records_to_table(
                table_name,
                records=records,
                columns=columns,
                timeout=timeout,
            )

    @property
    def pool_size(self) -> int:
        """Current number of connections in the pool."""
        if self._pool is None:
            return 0
        return self._pool.get_size()

    @property
    def pool_min_size(self) -> int:
        """Minimum pool size from configuration."""
        return self._config.pool.min_size

    @property
    def pool_max_size(self) -> int:
        """Maximum pool size from configuration."""
        return self._config.pool.max_size

    @property
    def pool_idle_size(self) -> int:
        """Idle pool size from configuration."""
        if self._pool is None:
            return 0
        return self._pool.get_idle_size()
