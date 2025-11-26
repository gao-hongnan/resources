from __future__ import annotations

from collections.abc import Awaitable, Callable

from tenacity import RetryCallState

type RetryCallback = Callable[[RetryCallState], Awaitable[None] | None]
type BeforeSleepCallback = Callable[[RetryCallState], Awaitable[None] | None]
