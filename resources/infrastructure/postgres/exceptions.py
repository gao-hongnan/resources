from __future__ import annotations


class AsyncpgWrapperError(Exception):
    pass


class PoolNotInitializedError(AsyncpgWrapperError):
    pass
