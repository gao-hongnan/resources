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
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    wait_random_exponential,
)
from tenacity.stop import stop_base
from tenacity.wait import wait_base

from ..core.types import P, R
from .config import RetryConfig
from .types import BeforeSleepCallback, RetryCallback


def build_retry_decorator(
    config: RetryConfig,
    before: RetryCallback | None = None,
    after: RetryCallback | None = None,
    before_sleep: BeforeSleepCallback | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    stop: stop_base = stop_after_attempt(config.max_attempts)
    if config.max_delay_seconds:
        stop = stop | stop_after_delay(config.max_delay_seconds)

    wait: wait_base
    if config.use_jitter:
        wait = wait_random_exponential(min=config.wait_min, max=config.wait_max)
    else:
        wait = wait_exponential(min=config.wait_min, max=config.wait_max, multiplier=config.wait_multiplier)

    retry_condition = (
        retry_if_exception_type(config.retry_on_exceptions) if config.retry_on_exceptions else retry_if_exception_type()
    )

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                async for attempt in AsyncRetrying(
                    stop=stop,
                    wait=wait,
                    retry=retry_condition,
                    before=cast(
                        Callable[[RetryCallState], Awaitable[None] | None],
                        before or before_nothing,
                    ),
                    after=cast(
                        Callable[[RetryCallState], Awaitable[None] | None],
                        after or after_nothing,
                    ),
                    before_sleep=before_sleep or None,
                    reraise=config.reraise,
                ):
                    with attempt:
                        coro_func = cast(Callable[P, Coroutine[object, object, R]], func)
                        return await coro_func(*args, **kwargs)
                raise AssertionError("unreachable")

            return cast(Callable[P, R], async_wrapper)
        else:

            @wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                for attempt in Retrying(
                    stop=stop,
                    wait=wait,
                    retry=retry_condition,
                    before=cast(
                        Callable[[RetryCallState], None],
                        before or before_nothing,
                    ),
                    after=cast(
                        Callable[[RetryCallState], None],
                        after or after_nothing,
                    ),
                    before_sleep=cast(
                        Callable[[RetryCallState], None] | None,
                        before_sleep,
                    ),
                    reraise=config.reraise,
                ):
                    with attempt:
                        return func(*args, **kwargs)
                raise AssertionError("unreachable")

            return sync_wrapper

    return decorator


def retry(
    config: RetryConfig | None = None,
    before: RetryCallback | None = None,
    after: RetryCallback | None = None,
    before_sleep: BeforeSleepCallback | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    retry_config = config or RetryConfig()
    return build_retry_decorator(retry_config, before=before, after=after, before_sleep=before_sleep)
