from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import cast

from tenacity import (
    AsyncRetrying,
    RetryCallState,
    Retrying,
    after_nothing,
    before_nothing,
    retry_if_exception_type,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)
from tenacity.retry import retry_base

from ..config.retry import RetryConfig
from ..core.types import P, R
from .types import BeforeSleepCallback, RetryCallback


class RetryLogicError(RuntimeError): ...


class Retry:
    def __init__(
        self,
        config: RetryConfig,
        before: RetryCallback | None = None,
        after: RetryCallback | None = None,
        before_sleep: BeforeSleepCallback | None = None,
    ) -> None:
        self._config = config
        self._before = before
        self._after = after
        self._before_sleep = before_sleep
        self._stop = stop_after_attempt(config.max_attempts)

        # NOTE: Google SRE Full Jitter algorithm from AWS https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
        self._wait = wait_random_exponential(
            multiplier=config.multiplier,
            min=config.wait_min,
            max=config.wait_max,
            exp_base=config.exp_base,
        )
        self._retry_condition = self._build_retry_condition(config)

    def _build_retry_condition(self, config: RetryConfig) -> retry_base:
        if config.retry_on_exceptions:
            condition: retry_base = retry_if_exception_type(config.retry_on_exceptions)
        else:
            condition = retry_if_exception_type(Exception)

        if config.never_retry_on:
            condition = condition & retry_if_not_exception_type(config.never_retry_on)

        return condition

    def __call__(self, func: Callable[P, R]) -> Callable[P, R]:
        if asyncio.iscoroutinefunction(func):
            return cast(Callable[P, R], self._wrap_async(func))
        return self._wrap_sync(func)

    def _wrap_async(
        self, func: Callable[P, Coroutine[object, object, R]]
    ) -> Callable[P, Coroutine[object, object, R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            async for attempt in AsyncRetrying(
                stop=self._stop,
                wait=self._wait,
                retry=self._retry_condition,
                before=cast(
                    Callable[[RetryCallState], Awaitable[None] | None],
                    self._before or before_nothing,
                ),
                after=cast(
                    Callable[[RetryCallState], Awaitable[None] | None],
                    self._after or after_nothing,
                ),
                before_sleep=self._before_sleep,
                reraise=self._config.reraise,
            ):
                with attempt:
                    return await func(*args, **kwargs)

            raise RetryLogicError(
                "Async retry loop completed without success or failure"
            )

        return wrapper

    def _wrap_sync(self, func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in Retrying(
                stop=self._stop,
                wait=self._wait,
                retry=self._retry_condition,
                before=cast(
                    Callable[[RetryCallState], None],
                    self._before or before_nothing,
                ),
                after=cast(
                    Callable[[RetryCallState], None],
                    self._after or after_nothing,
                ),
                before_sleep=cast(
                    Callable[[RetryCallState], None] | None,
                    self._before_sleep,
                ),
                reraise=self._config.reraise,
            ):
                with attempt:
                    return func(*args, **kwargs)

            raise RetryLogicError(
                "Sync retry loop completed without success or failure"
            )

        return wrapper


def retry(
    config: RetryConfig | None = None,
    before: RetryCallback | None = None,
    after: RetryCallback | None = None,
    before_sleep: BeforeSleepCallback | None = None,
) -> Retry:
    retry_config = config or RetryConfig()
    return Retry(retry_config, before, after, before_sleep)
