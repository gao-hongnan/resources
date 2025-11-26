from __future__ import annotations

import types
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, Self

import asyncpg
from asyncpg import Pool, Record

from ...core.enums import HealthCheckStatus
from ...logger import get_logger
from .config import DatabaseConfig
from .models import HealthCheckResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterable, Sequence

    from asyncpg.cursor import CursorIterator
    from asyncpg.pool import PoolConnectionProxy


type IsolationLevel = Literal["read_uncommitted", "read_committed", "repeatable_read", "serializable"]

logger = get_logger(__name__)


class AsyncConnectionPool:
    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._pool: Pool[Record] | None = None

    async def __aenter__(self) -> Self:
        await self.ainitialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        if exc_type is not None and exc_val is not None:
            logger.error(
                "AsyncConnectionPool context manager exiting with exception",
                extra={"exc_type": exc_type.__name__, "exc_val": str(exc_val)},
                exc_info=(exc_type, exc_val, exc_tb),
            )
        await self.aclose()
        logger.info("AsyncConnectionPool context manager exited")

    async def ainitialize(self) -> None:
        if self._pool is not None:
            logger.debug("Connection pool already initialized, skipping")
            return

        self._pool = await asyncpg.create_pool(
            dsn=self._config.url,
            **self._config.asyncpg.model_dump(),
            **self._config.pool.model_dump(),
        )

        async with self._pool.acquire() as conn:
            await conn.execute("SELECT 1")

        logger.info("Database connection pool initialized")

    async def aclose(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("Database connection pool closed")

    async def ahealth_check(self) -> HealthCheckResult:
        timestamp = datetime.now(UTC)

        if self._pool is None:
            return HealthCheckResult(status=HealthCheckStatus.UNHEALTHY, timestamp=timestamp, pool_initialized=False)

        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

            return HealthCheckResult(
                status=HealthCheckStatus.HEALTHY,
                timestamp=timestamp,
                pool_initialized=True,
                pool_size=self._pool.get_size(),
                pool_max_size=self._pool.get_max_size(),
            )
        except Exception:
            return HealthCheckResult(status=HealthCheckStatus.UNHEALTHY, timestamp=timestamp, pool_initialized=True)

    @property
    def pool(self) -> Pool[Record]:
        if self._pool is None:
            raise RuntimeError("Connection pool not initialized. Call `ainitialize()` first.")
        return self._pool

    @asynccontextmanager
    async def aacquire(self) -> AsyncIterator[PoolConnectionProxy[Record]]:
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
        async with self.atransaction(
            isolation=isolation,
            readonly=readonly,
            deferrable=deferrable,
        ) as conn:
            cursor_factory = conn.cursor(query, *args, prefetch=prefetch, timeout=timeout)
            # CursorFactory.__aiter__() returns CursorIterator which IS async iterable
            yield cursor_factory.__aiter__()

    async def aexecute(self, query: str, *args: object, timeout: float | None = None) -> str:
        async with self.aacquire() as conn:
            return await conn.execute(query, *args, timeout=timeout)

    async def afetch(self, query: str, *args: object, timeout: float | None = None) -> list[Record]:
        async with self.aacquire() as conn:
            return await conn.fetch(query, *args, timeout=timeout)

    async def afetchrow(self, query: str, *args: object, timeout: float | None = None) -> Record | None:
        async with self.aacquire() as conn:
            return await conn.fetchrow(query, *args, timeout=timeout)

    async def afetchval(self, query: str, *args: object, timeout: float | None = None) -> Any:
        async with self.aacquire() as conn:
            return await conn.fetchval(query, *args, timeout=timeout)

    async def aexecutemany(self, query: str, args: Iterable[Sequence[object]], timeout: float | None = None) -> None:
        async with self.aacquire() as conn:
            await conn.executemany(query, args, timeout=timeout)
