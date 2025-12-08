"""Unit tests for DeadLetterQueue service."""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import ResponseError

from transcreation.services.dlq import DeadLetterEntry, DeadLetterQueue, DLQConfig, FailureCategory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_redis() -> MagicMock:
    """Create a mock Redis client (the actual client returned by context manager)."""
    redis = MagicMock()
    redis.xgroup_create = AsyncMock()
    redis.xadd = AsyncMock(return_value=b"1234567890123-0")
    redis.xreadgroup = AsyncMock(return_value=None)
    redis.xrange = AsyncMock(return_value=[])
    redis.xack = AsyncMock(return_value=1)
    redis.xdel = AsyncMock(return_value=1)
    redis.xlen = AsyncMock(return_value=0)
    redis.xpending = AsyncMock(return_value={"pending": 0})
    redis.xpending_range = AsyncMock(return_value=[])
    redis.xclaim = AsyncMock(return_value=[])
    redis.eval = AsyncMock(return_value=1)  # For Lua script execution
    return redis


@pytest.fixture
def mock_redis_client(mock_redis: MagicMock) -> MagicMock:
    """Create a mock BaseRedisClient with async context manager."""
    client = MagicMock()

    @asynccontextmanager
    async def mock_aget_client() -> AsyncIterator[MagicMock]:
        yield mock_redis

    client.aget_client = mock_aget_client
    return client


@pytest.fixture
def dlq_config() -> DLQConfig:
    """Create test DLQ configuration."""
    return DLQConfig(
        stream_name="test:dlq",
        consumer_group="test-consumers",
        key_prefix="test",
        max_stream_length=1000,
        max_requeue_attempts=3,
        block_timeout_ms=100,
        claim_timeout_ms=1000,
        batch_size=10,
    )


@pytest.fixture
async def dlq(mock_redis_client: MagicMock, dlq_config: DLQConfig) -> DeadLetterQueue:
    """Create DLQ instance with mocked Redis."""
    dlq = DeadLetterQueue(mock_redis_client, dlq_config)
    await dlq.ainitialize()
    return dlq


@pytest.fixture
def sample_entry() -> DeadLetterEntry:
    """Create a sample DeadLetterEntry for testing."""
    return DeadLetterEntry(
        id="test-entry-id",
        stream_id="1234567890123-0",
        payload=b"test payload",
        error_type="ValueError",
        error_message="Test error",
        error_traceback="Traceback...",
        retry_count=2,
        requeue_count=1,
        category=FailureCategory.TRANSIENT,
        source_queue="test-queue",
        timestamp=datetime.now(UTC),
        metadata={"key": "value"},
    )


# =============================================================================
# TEST CLASSES
# =============================================================================


class TestDeadLetterQueueInit:
    """Tests for DeadLetterQueue initialization."""

    def test_creates_with_redis_client_and_config(self, mock_redis_client: MagicMock, dlq_config: DLQConfig) -> None:
        """Test DLQ is created with provided client and config."""
        dlq = DeadLetterQueue(mock_redis_client, dlq_config)
        assert dlq._redis_client is mock_redis_client
        assert dlq._config is dlq_config

    def test_uses_default_config_when_none(self, mock_redis_client: MagicMock) -> None:
        """Test DLQ uses default config when None provided."""
        dlq = DeadLetterQueue(mock_redis_client, None)
        assert isinstance(dlq._config, DLQConfig)
        assert dlq._config.stream_name == "pixiu:dlq"

    def test_generates_unique_consumer_id(self, mock_redis_client: MagicMock, dlq_config: DLQConfig) -> None:
        """Test DLQ generates unique consumer ID."""
        dlq1 = DeadLetterQueue(mock_redis_client, dlq_config)
        dlq2 = DeadLetterQueue(mock_redis_client, dlq_config)
        assert dlq1.consumer_id != dlq2.consumer_id
        assert dlq1.consumer_id.startswith("worker_")
        assert len(dlq1.consumer_id) == len("worker_") + 8

    def test_starts_uninitialized(self, mock_redis_client: MagicMock, dlq_config: DLQConfig) -> None:
        """Test DLQ starts in uninitialized state."""
        fresh_dlq = DeadLetterQueue(mock_redis_client, dlq_config)
        assert fresh_dlq._initialized is False

    def test_stream_name_property(self, dlq: DeadLetterQueue) -> None:
        """Test stream_name property returns config value."""
        assert dlq.stream_name == "test:dlq"


class TestAinitialize:
    """Tests for ainitialize method."""

    @pytest.mark.asyncio
    async def test_creates_consumer_group(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test ainitialize creates consumer group."""
        await dlq.ainitialize()
        mock_redis.xgroup_create.assert_called_once_with(
            name="test:dlq",
            groupname="test-consumers",
            id="0",
            mkstream=True,
        )
        assert dlq._initialized is True

    @pytest.mark.asyncio
    async def test_handles_busygroup_exception(
        self, mock_redis_client: MagicMock, mock_redis: MagicMock, dlq_config: DLQConfig
    ) -> None:
        """Test ainitialize handles BUSYGROUP exception (group already exists)."""
        mock_redis.xgroup_create.side_effect = ResponseError("BUSYGROUP Consumer Group name already exists")
        dlq = DeadLetterQueue(mock_redis_client, dlq_config)
        await dlq.ainitialize()
        assert dlq._initialized is True

    @pytest.mark.asyncio
    async def test_propagates_other_exceptions(
        self, mock_redis_client: MagicMock, mock_redis: MagicMock, dlq_config: DLQConfig
    ) -> None:
        """Test ainitialize propagates non-BUSYGROUP exceptions."""
        mock_redis.xgroup_create.side_effect = ResponseError("ERR Connection refused")
        dlq = DeadLetterQueue(mock_redis_client, dlq_config)
        with pytest.raises(ResponseError, match="Connection refused"):
            await dlq.ainitialize()

    @pytest.mark.asyncio
    async def test_idempotent_when_already_initialized(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test ainitialize returns early when already initialized."""
        # dlq fixture already calls ainitialize()
        mock_redis.xgroup_create.reset_mock()
        await dlq.ainitialize()  # Second call should be no-op
        mock_redis.xgroup_create.assert_not_called()


class TestDeadLetter:
    """Tests for dead_letter method."""

    @pytest.mark.asyncio
    async def test_adds_entry_to_stream(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test dead_letter adds entry to Redis stream."""
        try:
            raise ValueError("Test error")
        except ValueError as e:
            await dlq.dead_letter(
                payload=b"test payload",
                error=e,
                source_queue="test-queue",
            )

        mock_redis.xadd.assert_called_once()
        call_kwargs = mock_redis.xadd.call_args[1]
        assert call_kwargs["name"] == "test:dlq"
        assert call_kwargs["maxlen"] == 1000

    @pytest.mark.asyncio
    async def test_returns_stream_id(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test dead_letter returns stream ID."""
        mock_redis.xadd.return_value = b"9999999999999-0"

        try:
            raise ValueError("Test error")
        except ValueError as e:
            stream_id = await dlq.dead_letter(
                payload=b"test",
                error=e,
                source_queue="queue",
            )

        assert stream_id == "9999999999999-0"

    @pytest.mark.asyncio
    async def test_base64_encodes_payload(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test dead_letter base64 encodes payload."""
        payload = b"\x00\x01\x02\xff"

        try:
            raise ValueError("Test")
        except ValueError as e:
            await dlq.dead_letter(payload=payload, error=e, source_queue="q")

        fields = mock_redis.xadd.call_args[1]["fields"]
        assert fields["payload"] == base64.b64encode(payload).decode()

    @pytest.mark.asyncio
    async def test_captures_error_type(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test dead_letter captures error type name."""
        try:
            raise TypeError("Type error")
        except TypeError as e:
            await dlq.dead_letter(payload=b"", error=e, source_queue="q")

        fields = mock_redis.xadd.call_args[1]["fields"]
        assert fields["error_type"] == "TypeError"

    @pytest.mark.asyncio
    async def test_captures_error_message(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test dead_letter captures error message."""
        try:
            raise ValueError("Specific error message")
        except ValueError as e:
            await dlq.dead_letter(payload=b"", error=e, source_queue="q")

        fields = mock_redis.xadd.call_args[1]["fields"]
        assert fields["error_message"] == "Specific error message"

    @pytest.mark.asyncio
    async def test_captures_traceback_in_exception_context(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test dead_letter captures traceback when called in exception context."""
        try:
            raise ValueError("Test")
        except ValueError as e:
            await dlq.dead_letter(payload=b"", error=e, source_queue="q")

        fields = mock_redis.xadd.call_args[1]["fields"]
        assert "ValueError" in fields["error_traceback"]
        assert "Test" in fields["error_traceback"]

    @pytest.mark.asyncio
    async def test_minimal_traceback_outside_exception_context(
        self, dlq: DeadLetterQueue, mock_redis: MagicMock
    ) -> None:
        """Test dead_letter captures exception info even when created outside exception context.

        When an exception is created but not raised, it has no __traceback__.
        The implementation uses format_exception() which still captures the
        exception type and message, just without the stack frames.
        """
        error = ValueError("Pre-created error")
        await dlq.dead_letter(payload=b"", error=error, source_queue="q")

        fields = mock_redis.xadd.call_args[1]["fields"]
        # Exception type and message are captured even without traceback frames
        assert "ValueError" in fields["error_traceback"]
        assert "Pre-created error" in fields["error_traceback"]
        # But no file/line info since exception was never raised
        assert "line" not in fields["error_traceback"].lower()

    @pytest.mark.asyncio
    async def test_uses_custom_entry_id_when_provided(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test dead_letter uses custom entry_id when provided."""
        try:
            raise ValueError("Test")
        except ValueError as e:
            await dlq.dead_letter(
                payload=b"",
                error=e,
                source_queue="q",
                entry_id="custom-id-123",
            )

        fields = mock_redis.xadd.call_args[1]["fields"]
        assert fields["id"] == "custom-id-123"

    @pytest.mark.asyncio
    async def test_generates_uuid_when_entry_id_none(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test dead_letter generates UUID when entry_id not provided."""
        try:
            raise ValueError("Test")
        except ValueError as e:
            await dlq.dead_letter(payload=b"", error=e, source_queue="q")

        fields = mock_redis.xadd.call_args[1]["fields"]
        # UUID should be 36 characters with hyphens
        assert len(fields["id"]) == 36
        assert fields["id"].count("-") == 4

    @pytest.mark.asyncio
    async def test_stores_metadata_with_prefix(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test dead_letter stores metadata with meta_ prefix."""
        try:
            raise ValueError("Test")
        except ValueError as e:
            await dlq.dead_letter(
                payload=b"",
                error=e,
                source_queue="q",
                metadata={"trace_id": "abc123", "user_id": "user_456"},
            )

        fields = mock_redis.xadd.call_args[1]["fields"]
        assert fields["meta_trace_id"] == "abc123"
        assert fields["meta_user_id"] == "user_456"

    @pytest.mark.asyncio
    async def test_stores_category_value(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test dead_letter stores category value."""
        try:
            raise ValueError("Test")
        except ValueError as e:
            await dlq.dead_letter(
                payload=b"",
                error=e,
                source_queue="q",
                category=FailureCategory.PERMANENT,
            )

        fields = mock_redis.xadd.call_args[1]["fields"]
        assert fields["category"] == "permanent"


class TestRead:
    """Tests for read method."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_messages(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test read returns empty list when no messages available."""
        mock_redis.xreadgroup.return_value = None
        entries = await dlq.read()
        assert entries == []

    @pytest.mark.asyncio
    async def test_returns_entries_from_stream(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test read returns parsed entries from stream."""
        mock_redis.xreadgroup.return_value = [
            (
                b"test:dlq",
                [
                    (
                        b"1234567890123-0",
                        {
                            b"id": b"entry-1",
                            b"payload": base64.b64encode(b"payload").decode().encode(),
                            b"error_type": b"ValueError",
                            b"error_message": b"Error",
                            b"error_traceback": b"",
                            b"retry_count": b"0",
                            b"requeue_count": b"0",
                            b"category": b"transient",
                            b"source_queue": b"queue",
                            b"timestamp": datetime.now(UTC).isoformat().encode(),
                        },
                    )
                ],
            )
        ]

        entries = await dlq.read()
        assert len(entries) == 1
        assert entries[0].id == "entry-1"
        assert entries[0].stream_id == "1234567890123-0"

    @pytest.mark.asyncio
    async def test_respects_max_count(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test read respects max_count parameter."""
        mock_redis.xreadgroup.return_value = None
        await dlq.read(max_count=5)

        call_kwargs = mock_redis.xreadgroup.call_args[1]
        assert call_kwargs["count"] == 5

    @pytest.mark.asyncio
    async def test_uses_config_batch_size_when_max_count_none(
        self, dlq: DeadLetterQueue, mock_redis: MagicMock
    ) -> None:
        """Test read uses config batch_size when max_count is None."""
        mock_redis.xreadgroup.return_value = None
        await dlq.read(max_count=None)

        call_kwargs = mock_redis.xreadgroup.call_args[1]
        assert call_kwargs["count"] == 10  # dlq_config.batch_size

    @pytest.mark.asyncio
    async def test_handles_invalid_category(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test read handles invalid category by defaulting to TRANSIENT."""
        mock_redis.xreadgroup.return_value = [
            (
                b"test:dlq",
                [
                    (
                        b"1234567890123-0",
                        {
                            b"id": b"entry-1",
                            b"payload": base64.b64encode(b"payload").decode().encode(),
                            b"error_type": b"ValueError",
                            b"error_message": b"Error",
                            b"category": b"invalid_category",
                            b"source_queue": b"queue",
                            b"timestamp": datetime.now(UTC).isoformat().encode(),
                        },
                    )
                ],
            )
        ]

        entries = await dlq.read()
        assert entries[0].category == FailureCategory.TRANSIENT


class TestPeek:
    """Tests for peek method."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_stream_empty(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test peek returns empty list when stream is empty."""
        mock_redis.xrange.return_value = []
        entries = await dlq.peek()
        assert entries == []

    @pytest.mark.asyncio
    async def test_respects_max_count(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test peek respects max_count parameter."""
        mock_redis.xrange.return_value = []
        await dlq.peek(max_count=5)

        call_kwargs = mock_redis.xrange.call_args[1]
        assert call_kwargs["count"] == 5

    @pytest.mark.asyncio
    async def test_uses_xrange_not_xreadgroup(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test peek uses XRANGE (non-consuming) not XREADGROUP."""
        mock_redis.xrange.return_value = []
        await dlq.peek()

        mock_redis.xrange.assert_called_once()
        mock_redis.xreadgroup.assert_not_called()


class TestAcknowledge:
    """Tests for acknowledge method."""

    @pytest.mark.asyncio
    async def test_acknowledges_entries_with_stream_id(
        self, dlq: DeadLetterQueue, mock_redis: MagicMock, sample_entry: DeadLetterEntry
    ) -> None:
        """Test acknowledge calls XACK with stream IDs."""
        await dlq.acknowledge([sample_entry])

        mock_redis.xack.assert_called_once_with(
            "test:dlq",
            "test-consumers",
            "1234567890123-0",
        )

    @pytest.mark.asyncio
    async def test_returns_count_of_acknowledged(
        self, dlq: DeadLetterQueue, mock_redis: MagicMock, sample_entry: DeadLetterEntry
    ) -> None:
        """Test acknowledge returns count from Redis."""
        mock_redis.xack.return_value = 3
        count = await dlq.acknowledge([sample_entry, sample_entry, sample_entry])
        assert count == 3

    @pytest.mark.asyncio
    async def test_returns_zero_for_empty_list(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test acknowledge returns 0 for empty list."""
        count = await dlq.acknowledge([])
        assert count == 0
        mock_redis.xack.assert_not_called()

    @pytest.mark.asyncio
    async def test_silently_skips_entries_without_stream_id(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test acknowledge silently skips entries without stream_id.

        NOTE: This documents a bug - entries without stream_id are silently dropped
        without any logging.
        """
        entry_no_stream_id = DeadLetterEntry(
            id="test-id",
            stream_id="",  # Empty stream_id
            payload=b"payload",
            error_type="ValueError",
            error_message="error",
            source_queue="queue",
            timestamp=datetime.now(UTC),
        )

        count = await dlq.acknowledge([entry_no_stream_id])
        assert count == 0
        mock_redis.xack.assert_not_called()


class TestRequeue:
    """Tests for requeue method."""

    @pytest.mark.asyncio
    async def test_increments_requeue_count(
        self, dlq: DeadLetterQueue, mock_redis: MagicMock, sample_entry: DeadLetterEntry
    ) -> None:
        """Test requeue increments requeue_count."""
        await dlq.requeue(sample_entry)

        fields = mock_redis.xadd.call_args[1]["fields"]
        assert fields["requeue_count"] == "2"  # sample_entry has requeue_count=1

    @pytest.mark.asyncio
    async def test_returns_new_stream_id(
        self, dlq: DeadLetterQueue, mock_redis: MagicMock, sample_entry: DeadLetterEntry
    ) -> None:
        """Test requeue returns new stream ID."""
        mock_redis.xadd.return_value = b"9999999999999-0"
        stream_id = await dlq.requeue(sample_entry)
        assert stream_id == "9999999999999-0"

    @pytest.mark.asyncio
    async def test_returns_none_when_max_attempts_exceeded(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test requeue returns None when max attempts exceeded."""
        entry = DeadLetterEntry(
            id="test-id",
            stream_id="123-0",
            payload=b"payload",
            error_type="ValueError",
            error_message="error",
            source_queue="queue",
            timestamp=datetime.now(UTC),
            requeue_count=3,  # At max (config has max_requeue_attempts=3)
        )

        result = await dlq.requeue(entry)
        assert result is None
        mock_redis.xadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_acknowledges_original_entry(
        self, dlq: DeadLetterQueue, mock_redis: MagicMock, sample_entry: DeadLetterEntry
    ) -> None:
        """Test requeue acknowledges the original entry."""
        await dlq.requeue(sample_entry)
        mock_redis.xack.assert_called_once()

    @pytest.mark.asyncio
    async def test_preserves_metadata(
        self, dlq: DeadLetterQueue, mock_redis: MagicMock, sample_entry: DeadLetterEntry
    ) -> None:
        """Test requeue preserves metadata."""
        await dlq.requeue(sample_entry)

        fields = mock_redis.xadd.call_args[1]["fields"]
        assert fields["meta_key"] == "value"


class TestClaimStale:
    """Tests for claim_stale method."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_pending(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test claim_stale returns empty list when no pending messages."""
        mock_redis.xpending_range.return_value = []
        entries = await dlq.claim_stale()
        assert entries == []

    @pytest.mark.asyncio
    async def test_claims_stale_messages(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test claim_stale claims messages past timeout."""
        mock_redis.xpending_range.return_value = [
            {"message_id": b"123-0", "time_since_delivered": 2000}  # > 1000ms timeout
        ]
        mock_redis.xclaim.return_value = [
            (
                b"123-0",
                {
                    b"id": b"entry-1",
                    b"payload": base64.b64encode(b"payload").decode().encode(),
                    b"error_type": b"ValueError",
                    b"error_message": b"Error",
                    b"category": b"transient",
                    b"source_queue": b"queue",
                    b"timestamp": datetime.now(UTC).isoformat().encode(),
                },
            )
        ]

        entries = await dlq.claim_stale()
        assert len(entries) == 1
        mock_redis.xclaim.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_claim_fresh_messages(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test claim_stale does not claim messages below timeout."""
        mock_redis.xpending_range.return_value = [
            {"message_id": b"123-0", "time_since_delivered": 500}  # < 1000ms timeout
        ]

        entries = await dlq.claim_stale()
        assert entries == []
        mock_redis.xclaim.assert_not_called()


class TestRedriveMessage:
    """Tests for redrive_message method.

    Note: redrive_message uses a Lua script for atomic operations.
    """

    @pytest.mark.asyncio
    async def test_moves_entry_to_main_queue(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test redrive_message executes Lua script for atomic redrive."""
        mock_redis.eval.return_value = 1  # Success

        result = await dlq.redrive_message("123-0", "target-queue")

        assert result is True
        # Verify eval was called with the Lua script
        mock_redis.eval.assert_called_once()
        call_args = mock_redis.eval.call_args[0]
        assert "XRANGE" in call_args[0]  # Lua script contains XRANGE
        assert "XADD" in call_args[0]  # Lua script contains XADD
        assert "XDEL" in call_args[0]  # Lua script contains XDEL
        assert call_args[1] == 2  # Two keys
        assert call_args[2] == "test:dlq"  # DLQ stream
        assert call_args[3] == "test:queue:target-queue"  # Main queue stream
        assert call_args[4] == "123-0"  # Stream ID to redrive

    @pytest.mark.asyncio
    async def test_atomic_operation_uses_lua_script(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test redrive_message uses Lua script for atomicity."""
        mock_redis.eval.return_value = 1

        await dlq.redrive_message("123-0", "target-queue")

        # Verify atomic operation: xadd and xdel are NOT called separately
        mock_redis.xadd.assert_not_called()
        mock_redis.xdel.assert_not_called()
        # Instead, eval is used for atomic Lua script
        mock_redis.eval.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test redrive_message returns False when Lua script returns nil."""
        mock_redis.eval.return_value = None  # Entry not found
        result = await dlq.redrive_message("nonexistent-123-0", "target-queue")
        assert result is False


class TestRedriveMessages:
    """Tests for redrive_messages method."""

    @pytest.mark.asyncio
    async def test_redrives_all_when_no_predicate(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test redrive_messages redrives all entries when no predicate."""
        mock_redis.xrange.side_effect = [
            [
                (
                    b"123-0",
                    {
                        b"id": b"entry-1",
                        b"payload": base64.b64encode(b"payload").decode().encode(),
                        b"error_type": b"ValueError",
                        b"error_message": b"Error",
                        b"category": b"transient",
                        b"source_queue": b"queue",
                        b"timestamp": datetime.now(UTC).isoformat().encode(),
                    },
                )
            ],
            [],  # Second call returns empty to end loop
        ]

        count = await dlq.redrive_messages("target-queue")
        assert count == 1

    @pytest.mark.asyncio
    async def test_applies_predicate_filter(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test redrive_messages applies predicate filter."""
        mock_redis.xrange.side_effect = [
            [
                (
                    b"123-0",
                    {
                        b"id": b"entry-1",
                        b"payload": base64.b64encode(b"payload").decode().encode(),
                        b"error_type": b"ValueError",
                        b"error_message": b"Error",
                        b"category": b"permanent",  # Not transient
                        b"source_queue": b"queue",
                        b"timestamp": datetime.now(UTC).isoformat().encode(),
                    },
                )
            ],
            [],
        ]

        # Only redrive transient
        count = await dlq.redrive_messages(
            "target-queue",
            predicate=lambda e: e.category == FailureCategory.TRANSIENT,
        )
        assert count == 0  # Filtered out

    @pytest.mark.asyncio
    async def test_respects_max_count(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test redrive_messages respects max_count."""
        entries = [
            (
                f"{i}-0".encode(),
                {
                    b"id": f"entry-{i}".encode(),
                    b"payload": base64.b64encode(b"payload").decode().encode(),
                    b"error_type": b"ValueError",
                    b"error_message": b"Error",
                    b"category": b"transient",
                    b"source_queue": b"queue",
                    b"timestamp": datetime.now(UTC).isoformat().encode(),
                },
            )
            for i in range(10)
        ]
        mock_redis.xrange.side_effect = [entries, []]

        count = await dlq.redrive_messages("target-queue", max_count=3)
        assert count == 3


class TestMonitoring:
    """Tests for monitoring methods."""

    @pytest.mark.asyncio
    async def test_get_message_count_returns_stream_length(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test get_message_count returns stream length."""
        mock_redis.xlen.return_value = 42
        count = await dlq.get_message_count()
        assert count == 42
        mock_redis.xlen.assert_called_once_with("test:dlq")

    @pytest.mark.asyncio
    async def test_get_pending_count_returns_pending_entries(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test get_pending_count returns pending count."""
        mock_redis.xpending.return_value = {"pending": 15}
        count = await dlq.get_pending_count()
        assert count == 15

    @pytest.mark.asyncio
    async def test_get_pending_count_handles_none_response(self, dlq: DeadLetterQueue, mock_redis: MagicMock) -> None:
        """Test get_pending_count handles None response."""
        mock_redis.xpending.return_value = None
        count = await dlq.get_pending_count()
        assert count == 0


class TestHelpers:
    """Tests for helper methods."""

    def test_decode_fields_converts_bytes_to_strings(self, dlq: DeadLetterQueue) -> None:
        """Test _decode_fields converts bytes to strings."""
        fields_raw: dict[bytes | str, bytes | str] = {b"key1": b"value1", b"key2": b"value2"}
        result = dlq._decode_fields(fields_raw)
        assert result == {"key1": "value1", "key2": "value2"}

    def test_decode_fields_handles_string_input(self, dlq: DeadLetterQueue) -> None:
        """Test _decode_fields handles string input (no decode needed)."""
        fields_raw: dict[bytes | str, bytes | str] = {"key1": "value1", "key2": "value2"}
        result = dlq._decode_fields(fields_raw)
        assert result == {"key1": "value1", "key2": "value2"}

    def test_parse_entry_creates_valid_entry(self, dlq: DeadLetterQueue) -> None:
        """Test _parse_entry creates valid DeadLetterEntry."""
        fields = {
            "id": "test-id",
            "payload": base64.b64encode(b"payload").decode(),
            "error_type": "ValueError",
            "error_message": "Error message",
            "error_traceback": "Traceback...",
            "retry_count": "2",
            "requeue_count": "1",
            "category": "transient",
            "source_queue": "queue",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        entry = dlq._parse_entry("123-0", fields)

        assert entry.id == "test-id"
        assert entry.stream_id == "123-0"
        assert entry.payload == b"payload"
        assert entry.error_type == "ValueError"
        assert entry.retry_count == 2
        assert entry.category == FailureCategory.TRANSIENT

    def test_parse_entry_extracts_metadata(self, dlq: DeadLetterQueue) -> None:
        """Test _parse_entry extracts metadata fields."""
        fields = {
            "id": "test-id",
            "payload": base64.b64encode(b"payload").decode(),
            "error_type": "ValueError",
            "error_message": "Error",
            "category": "transient",
            "source_queue": "queue",
            "timestamp": datetime.now(UTC).isoformat(),
            "meta_trace_id": "abc123",
            "meta_user_id": "user_456",
        }

        entry = dlq._parse_entry("123-0", fields)

        assert entry.metadata == {"trace_id": "abc123", "user_id": "user_456"}

    def test_parse_entry_handles_missing_fields(self, dlq: DeadLetterQueue) -> None:
        """Test _parse_entry handles missing fields with defaults."""
        fields: dict[str, str] = {
            "id": "test-id",
            "error_type": "ValueError",
            # Missing many fields
        }

        entry = dlq._parse_entry("123-0", fields)

        assert entry.id == "test-id"
        assert entry.payload == b""  # Empty payload
        assert entry.error_message == ""
        assert entry.category == FailureCategory.TRANSIENT

    def test_parse_entry_handles_invalid_timestamp(self, dlq: DeadLetterQueue) -> None:
        """Test _parse_entry handles invalid timestamp."""
        fields = {
            "id": "test-id",
            "payload": base64.b64encode(b"payload").decode(),
            "error_type": "ValueError",
            "error_message": "Error",
            "category": "transient",
            "source_queue": "queue",
            "timestamp": "not-a-valid-timestamp",
        }

        entry = dlq._parse_entry("123-0", fields)

        # Should use current time as fallback
        assert entry.timestamp is not None
        assert isinstance(entry.timestamp, datetime)

    def test_parse_entry_raises_on_corrupted_base64_payload(self, dlq: DeadLetterQueue) -> None:
        """Test _parse_entry raises ValueError for corrupted base64 payload.

        The implementation fails loudly on data corruption to prevent
        silent data loss. This follows the fail-fast principle.
        """
        fields = {
            "id": "test-id",
            "payload": "not-valid-base64!!!",
            "error_type": "ValueError",
            "error_message": "Error",
            "category": "transient",
            "source_queue": "queue",
            "timestamp": datetime.now(UTC).isoformat(),
        }

        with pytest.raises(ValueError, match="Corrupted payload"):
            dlq._parse_entry("123-0", fields)
