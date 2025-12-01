from __future__ import annotations

from typing import Literal

import pytest
from tenacity import RetryCallState

from transcreation.config.retry import RetryConfig
from transcreation.resilience.retry import retry


@pytest.fixture
def default_retry_config() -> RetryConfig:
    return RetryConfig(
        max_attempts=3,
        wait_min=0.01,
        wait_max=0.02,
        multiplier=1.0,
        exp_base=2.0,
        retry_on_exceptions=None,
        never_retry_on=None,
        reraise=True,
    )


@pytest.fixture
def connection_retry_config() -> RetryConfig:
    return RetryConfig(
        max_attempts=5,
        wait_min=0.01,
        wait_max=0.02,
        multiplier=1.0,
        exp_base=2.0,
        retry_on_exceptions=(ConnectionError, TimeoutError),
        never_retry_on=None,
        reraise=True,
    )


class TestRetryDecoratorAsync:
    """Test async retry decorator behavior."""

    @pytest.mark.asyncio
    async def test_succeeds_without_retry_when_no_error(
        self, default_retry_config: RetryConfig
    ) -> None:
        """Verify decorated function succeeds on first attempt without triggering retry.

        Tests that when a decorated async function executes successfully without
        raising any exception, the retry mechanism does not intervene and the
        function is called exactly once.

        Arrange
        -------
        - Create a retry-decorated async function that always succeeds
        - Initialize call counter to track invocations

        Act
        ---
        - Invoke the decorated function

        Assert
        ------
        - Function returns expected success value
        - Function was called exactly once (no retries)
        """
        call_count = 0

        @retry(default_retry_config)
        async def successful_function() -> Literal["success"]:
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_function()

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_and_succeeds_after_transient_failures(
        self, default_retry_config: RetryConfig
    ) -> None:
        """Verify retry mechanism recovers from transient failures.

        Tests that when a decorated async function fails with retryable exceptions
        on initial attempts but eventually succeeds, the retry mechanism correctly
        retries until success and returns the successful result.

        Arrange
        -------
        - Configure retry with max_attempts=5
        - Create function that fails twice with ConnectionError then succeeds

        Act
        ---
        - Invoke the decorated function

        Assert
        ------
        - Function returns success value after recovery (i.e. 2 failures because < 3 attempts, but when call_count == 3, it succeeds)
        - Function was called exactly 3 times (2 failures + 1 success)
        """
        call_count = 0
        config = default_retry_config.model_copy(update={"max_attempts": 5})

        @retry(config)
        async def flaky_function() -> Literal["success"]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError(f"Transient failure #{call_count}")
            return "success"

        result = await flaky_function()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts_exhausted(
        self, default_retry_config: RetryConfig
    ) -> None:
        """Verify exception propagates after exhausting all retry attempts.

        Tests that when a decorated async function consistently fails on every
        attempt, the retry mechanism exhausts all configured attempts and then
        re-raises the final exception to the caller.

        Arrange
        -------
        - Configure retry with max_attempts=3 and reraise=True
        - Create function that always raises TimeoutError

        Act
        ---
        - Invoke the decorated function expecting TimeoutError

        Assert
        ------
        - TimeoutError is raised after all attempts exhausted
        - Function was called exactly 3 times (all configured attempts)
        """
        call_count = 0

        @retry(default_retry_config)
        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise TimeoutError(f"Always fails - attempt {call_count}")

        with pytest.raises(TimeoutError, match="Always fails"):
            await always_fails()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retries_only_on_configured_exceptions(
        self, connection_retry_config: RetryConfig
    ) -> None:
        """Verify retry only triggers for configured exception types.

        Tests that when a retry decorator is configured to only retry on specific
        exception types (e.g., ConnectionError, TimeoutError), exceptions not in
        that list propagate immediately without triggering any retry attempts.
        This ensures precise control over which failures warrant retry behavior.

        Arrange
        -------
        - Configure retry with retry_on_exceptions=(ConnectionError, TimeoutError)
        - Create function that raises ValueError (not in the retry list)

        Act
        ---
        - Invoke the decorated function expecting ValueError

        Assert
        ------
        - ValueError propagates immediately without retry
        - Function was called exactly once (no retry attempts)
        """
        call_count = 0

        @retry(connection_retry_config)
        async def fails_with_value_error() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Not a retryable error")

        with pytest.raises(ValueError, match="Not a retryable error"):
            await fails_with_value_error()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_specific_exception_then_succeeds(
        self, connection_retry_config: RetryConfig
    ) -> None:
        """Verify retry works for specific exceptions and eventually succeeds.

        Tests that when a function raises different configured exception types
        across multiple attempts, the retry mechanism correctly handles each one
        and continues retrying until success. This validates that all exception
        types in the retry_on_exceptions tuple are treated equally for retry logic.

        Arrange
        -------
        - Configure retry with retry_on_exceptions=(ConnectionError, TimeoutError)
        - Create function that raises ConnectionError, then TimeoutError, then succeeds

        Act
        ---
        - Invoke the decorated function

        Assert
        ------
        - Function eventually returns success value after recovering from both exception types
        - Function was called exactly 3 times (2 different exceptions + 1 success)
        """
        call_count = 0
        error_sequence = [ConnectionError, TimeoutError, None]

        @retry(connection_retry_config)
        async def sequential_errors() -> Literal["recovered"]:
            nonlocal call_count
            if call_count < len(error_sequence):
                error = error_sequence[call_count]
                call_count += 1
                if error:
                    raise error(f"Error #{call_count}")
            return "recovered"

        result = await sequential_errors()

        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_before_sleep_callback_is_invoked(
        self, default_retry_config: RetryConfig
    ) -> None:
        """Verify before_sleep callback is called before each retry sleep.

        Tests that the before_sleep callback hook is invoked immediately before
        the retry mechanism sleeps between attempts. This callback is useful for
        logging retry attempts, updating metrics, or implementing custom backoff
        notifications. The callback receives the RetryCallState with the attempt
        number that just failed.

        Arrange
        -------
        - Configure retry with max_attempts=4
        - Create before_sleep callback that records attempt numbers
        - Create function that fails twice then succeeds

        Act
        ---
        - Invoke the decorated function

        Assert
        ------
        - Function returns success after recovery
        - Callback was invoked with attempt numbers [1, 2] (before sleeping after each failed attempt)
        """
        call_count = 0
        callback_invocations: list[int] = []

        def before_sleep_callback(retry_state: RetryCallState) -> None:
            callback_invocations.append(retry_state.attempt_number)

        config = default_retry_config.model_copy(update={"max_attempts": 4})

        @retry(config, before_sleep=before_sleep_callback)
        async def flaky() -> Literal["done"]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Retry me")
            return "done"

        result = await flaky()

        assert result == "done"
        assert callback_invocations == [1, 2]

    @pytest.mark.asyncio
    async def test_before_callback_is_invoked(
        self, default_retry_config: RetryConfig
    ) -> None:
        """Verify before callback is called before each attempt.

        Tests that the before callback hook is invoked immediately before each
        function execution attempt, including the initial attempt and all retries.
        This callback is useful for logging attempt starts, setting up per-attempt
        context, or implementing pre-execution validation. Unlike before_sleep,
        this fires before every attempt, not just retries.

        Arrange
        -------
        - Create before callback that records attempt numbers
        - Create function that fails once then succeeds

        Act
        ---
        - Invoke the decorated function

        Assert
        ------
        - Callback was invoked with attempt numbers [1, 2] (before each attempt)
        """
        attempt_numbers: list[int] = []

        def before_callback(retry_state: RetryCallState) -> None:
            attempt_numbers.append(retry_state.attempt_number)

        call_count = 0

        @retry(default_retry_config, before=before_callback)
        async def flaky() -> Literal["success"]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Retry")
            return "success"

        await flaky()

        assert attempt_numbers == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_after_callback_is_invoked(
        self, default_retry_config: RetryConfig
    ) -> None:
        """Verify after callback is called after each failed attempt.

        Tests that the after callback hook is invoked immediately after each
        failed attempt, before the sleep delay. Critically, this callback is NOT
        invoked after the final successful attempt - it only fires when an attempt
        fails and a retry will be attempted. This callback is useful for logging
        failures, recording error details, or updating failure metrics.

        Arrange
        -------
        - Create after callback that records attempt numbers
        - Create function that fails once then succeeds

        Act
        ---
        - Invoke the decorated function

        Assert
        ------
        - Callback was invoked only with attempt number [1] (after the failed attempt)
        - Callback was NOT invoked after the successful second attempt
        """
        attempt_numbers: list[int] = []

        def after_callback(retry_state: RetryCallState) -> None:
            attempt_numbers.append(retry_state.attempt_number)

        call_count = 0

        @retry(default_retry_config, after=after_callback)
        async def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Retry")
            return "success"

        await flaky()

        assert attempt_numbers == [1]

    @pytest.mark.asyncio
    async def test_never_retry_on_exceptions(
        self, default_retry_config: RetryConfig
    ) -> None:
        """Verify never_retry_on exceptions bypass retry even if in retry_on_exceptions.

        Tests that when an exception type is listed in both retry_on_exceptions
        and never_retry_on, the never_retry_on takes precedence and the exception
        propagates immediately without any retry attempts.

        Arrange
        -------
        - Configure retry with retry_on_exceptions=(ConnectionError, ValueError)
        - Configure never_retry_on=(ValueError,) to exclude ValueError from retries

        Act
        ---
        - Invoke function that raises ValueError

        Assert
        ------
        - ValueError propagates immediately
        - Function was called exactly once (never_retry_on took precedence)
        """
        call_count = 0
        config = default_retry_config.model_copy(
            update={
                "max_attempts": 5,
                "retry_on_exceptions": (ConnectionError, ValueError),
                "never_retry_on": (ValueError,),
            }
        )

        @retry(config)
        async def fails_with_value_error() -> int:
            nonlocal call_count
            call_count += 1
            raise ValueError("No retry for this")

        with pytest.raises(ValueError):
            await fails_with_value_error()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_kwargs_preserved(self, default_retry_config: RetryConfig) -> None:
        """Verify function kwargs and defaults are preserved through retry decorator.

        Tests that positional args, keyword args, and default parameter values
        are correctly passed through the retry decorator to the wrapped function.

        Arrange
        -------
        - Create function with positional, keyword, and keyword-only parameters

        Act
        ---
        - Call function with mixed argument styles

        Assert
        ------
        - All arguments including defaults are correctly received by the function
        """
        config = default_retry_config.model_copy(update={"max_attempts": 2})

        @retry(config)
        async def func_with_kwargs(a: int, b: int = 10, *, c: str = "default") -> str:
            return f"{a}-{b}-{c}"

        result = await func_with_kwargs(1, c="custom")

        assert result == "1-10-custom"

    @pytest.mark.asyncio
    async def test_wait_times_follow_exponential_backoff_with_jitter(
        self, default_retry_config: RetryConfig
    ) -> None:
        """Verify wait times follow exponential backoff with full jitter.

        Tests that the retry mechanism uses the AWS Full Jitter algorithm:
        sleep = random(0, min(max, multiplier * exp_base^attempt))

        Since jitter is random, we verify:
        1. All sleep durations are within [wait_min, wait_max] bounds
        2. Sleep durations are captured for each retry (not first attempt)

        Arrange
        -------
        - Configure retry with known exponential parameters
        - Create before_sleep callback to capture planned sleep durations

        Act
        ---
        - Run function that fails multiple times then succeeds

        Assert
        ------
        - Sleep durations captured for each retry
        - All durations within configured bounds
        """
        sleep_durations: list[float] = []

        def capture_sleep(retry_state: RetryCallState) -> None:
            if retry_state.next_action:
                sleep_durations.append(retry_state.next_action.sleep)

        config = default_retry_config.model_copy(update={"max_attempts": 5})
        call_count = 0

        @retry(config, before_sleep=capture_sleep)
        async def flaky() -> Literal["done"]:
            nonlocal call_count
            call_count += 1
            if call_count < 4:
                raise ConnectionError("Fail")
            return "done"

        await flaky()

        assert len(sleep_durations) == 3
        for duration in sleep_durations:
            assert config.wait_min <= duration <= config.wait_max


class TestRetryDecoratorSync:
    """Test sync retry decorator behavior."""

    def test_sync_succeeds_after_failures(
        self, default_retry_config: RetryConfig
    ) -> None:
        """Verify sync function retries work correctly."""
        call_count = 0

        @retry(default_retry_config)
        def flaky_sync() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Transient")
            return "success"

        result = flaky_sync()

        assert result == "success"
        assert call_count == 2

    def test_sync_raises_after_exhaustion(
        self, default_retry_config: RetryConfig
    ) -> None:
        """Verify sync function raises after max attempts."""
        call_count = 0
        config = default_retry_config.model_copy(update={"max_attempts": 2})

        @retry(config)
        def always_fails_sync() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Always fails")

        with pytest.raises(RuntimeError):
            always_fails_sync()

        assert call_count == 2

    def test_sync_kwargs_preserved(self, default_retry_config: RetryConfig) -> None:
        """Verify sync function kwargs and defaults are preserved through retry decorator."""
        config = default_retry_config.model_copy(update={"max_attempts": 2})

        @retry(config)
        def func_with_kwargs(a: int, b: int = 10, *, c: str = "default") -> str:
            return f"{a}-{b}-{c}"

        result = func_with_kwargs(1, c="custom")

        assert result == "1-10-custom"

    def test_sync_with_all_callbacks(self, default_retry_config: RetryConfig) -> None:
        """Verify all callbacks (before, after, before_sleep) work together for sync functions.

        Tests the complete callback lifecycle for a sync function that fails
        twice then succeeds, verifying the order and timing of all callback
        invocations.

        Arrange
        -------
        - Configure retry with max_attempts=4
        - Create callbacks for before, after, and before_sleep

        Act
        ---
        - Run function that fails twice then succeeds

        Assert
        ------
        - before callback: [1, 2, 3] (before each of 3 attempts)
        - after callback: [1, 2] (after each of 2 failed attempts)
        - before_sleep callback: [1, 2] (before each of 2 sleeps)
        """
        before_calls: list[int] = []
        after_calls: list[int] = []
        sleep_calls: list[int] = []

        config = default_retry_config.model_copy(update={"max_attempts": 4})

        @retry(
            config,
            before=lambda s: before_calls.append(s.attempt_number),
            after=lambda s: after_calls.append(s.attempt_number),
            before_sleep=lambda s: sleep_calls.append(s.attempt_number),
        )
        def flaky(x: int, y: int) -> int:
            if len(before_calls) < 3:
                raise ConnectionError("Retry")
            return x + y

        result = flaky(3, 4)

        assert result == 7
        assert before_calls == [1, 2, 3]
        assert after_calls == [1, 2]
        assert sleep_calls == [1, 2]
