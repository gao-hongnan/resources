"""Unit tests for DLQ domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from transcreation.services.dlq import DeadLetterEntry, FailureCategory


@pytest.fixture
def valid_entry_data() -> dict[str, Any]:
    """Provide valid entry data for tests."""
    return {
        "id": "test-id-123",
        "payload": b"test payload",
        "error_type": "ValueError",
        "error_message": "Something went wrong",
        "source_queue": "test-queue",
        "timestamp": datetime.now(UTC),
    }


class TestFailureCategory:
    """Tests for FailureCategory enum."""

    def test_all_categories_have_unique_values(self) -> None:
        """Test all category values are unique."""
        values = [c.value for c in FailureCategory]
        assert len(values) == len(set(values))

    def test_category_string_values(self) -> None:
        """Test category string values match expected."""
        assert FailureCategory.TRANSIENT.value == "transient"
        assert FailureCategory.PERMANENT.value == "permanent"
        assert FailureCategory.POISON.value == "poison"
        assert FailureCategory.RESOURCE_EXHAUSTED.value == "exhausted"
        assert FailureCategory.DEPENDENCY_FAILURE.value == "dependency"

    def test_category_from_string(self) -> None:
        """Test category can be created from string value."""
        assert FailureCategory("transient") == FailureCategory.TRANSIENT
        assert FailureCategory("permanent") == FailureCategory.PERMANENT
        assert FailureCategory("poison") == FailureCategory.POISON

    def test_invalid_category_string_raises(self) -> None:
        """Test invalid category string raises ValueError."""
        with pytest.raises(ValueError):
            FailureCategory("invalid")

    def test_category_is_string_subclass(self) -> None:
        """Test FailureCategory is a str subclass for JSON serialization."""
        assert isinstance(FailureCategory.TRANSIENT, str)
        assert FailureCategory.TRANSIENT.value == "transient"


class TestDeadLetterEntryCreation:
    """Tests for DeadLetterEntry creation."""

    def test_create_with_required_fields(self, valid_entry_data: dict[str, Any]) -> None:
        """Test entry creation with required fields only."""
        entry = DeadLetterEntry(**valid_entry_data)
        assert entry.id == "test-id-123"
        assert entry.payload == b"test payload"
        assert entry.error_type == "ValueError"

    def test_create_with_all_fields(self, valid_entry_data: dict[str, Any]) -> None:
        """Test entry creation with all fields."""
        entry = DeadLetterEntry(
            **valid_entry_data,
            stream_id="1234567890-0",
            error_traceback="Traceback...",
            retry_count=3,
            requeue_count=1,
            category=FailureCategory.PERMANENT,
            metadata={"key": "value"},
        )
        assert entry.stream_id == "1234567890-0"
        assert entry.error_traceback == "Traceback..."
        assert entry.retry_count == 3
        assert entry.requeue_count == 1
        assert entry.category == FailureCategory.PERMANENT
        assert entry.metadata == {"key": "value"}

    def test_default_stream_id_empty(self, valid_entry_data: dict[str, Any]) -> None:
        """Test default stream_id is empty string."""
        entry = DeadLetterEntry(**valid_entry_data)
        assert entry.stream_id == ""

    def test_default_retry_count_zero(self, valid_entry_data: dict[str, Any]) -> None:
        """Test default retry_count is 0."""
        entry = DeadLetterEntry(**valid_entry_data)
        assert entry.retry_count == 0

    def test_default_requeue_count_zero(self, valid_entry_data: dict[str, Any]) -> None:
        """Test default requeue_count is 0."""
        entry = DeadLetterEntry(**valid_entry_data)
        assert entry.requeue_count == 0

    def test_default_category_transient(self, valid_entry_data: dict[str, Any]) -> None:
        """Test default category is TRANSIENT."""
        entry = DeadLetterEntry(**valid_entry_data)
        assert entry.category == FailureCategory.TRANSIENT

    def test_default_metadata_empty_dict(self, valid_entry_data: dict[str, Any]) -> None:
        """Test default metadata is empty dict."""
        entry = DeadLetterEntry(**valid_entry_data)
        assert entry.metadata == {}

    def test_default_error_traceback_empty(self, valid_entry_data: dict[str, Any]) -> None:
        """Test default error_traceback is empty string."""
        entry = DeadLetterEntry(**valid_entry_data)
        assert entry.error_traceback == ""


class TestDeadLetterEntryValidation:
    """Tests for DeadLetterEntry validation."""

    def test_empty_id_rejected(self, valid_entry_data: dict[str, Any]) -> None:
        """Test empty id raises ValidationError."""
        valid_entry_data["id"] = ""
        with pytest.raises(ValidationError) as exc_info:
            DeadLetterEntry(**valid_entry_data)
        assert "id" in str(exc_info.value)

    def test_empty_error_type_rejected(self, valid_entry_data: dict[str, Any]) -> None:
        """Test empty error_type raises ValidationError."""
        valid_entry_data["error_type"] = ""
        with pytest.raises(ValidationError) as exc_info:
            DeadLetterEntry(**valid_entry_data)
        assert "error_type" in str(exc_info.value)

    def test_negative_retry_count_rejected(self, valid_entry_data: dict[str, Any]) -> None:
        """Test negative retry_count raises ValidationError."""
        valid_entry_data["retry_count"] = -1
        with pytest.raises(ValidationError) as exc_info:
            DeadLetterEntry(**valid_entry_data)
        assert "retry_count" in str(exc_info.value)

    def test_negative_requeue_count_rejected(self, valid_entry_data: dict[str, Any]) -> None:
        """Test negative requeue_count raises ValidationError."""
        valid_entry_data["requeue_count"] = -1
        with pytest.raises(ValidationError) as exc_info:
            DeadLetterEntry(**valid_entry_data)
        assert "requeue_count" in str(exc_info.value)

    def test_extra_fields_forbidden(self, valid_entry_data: dict[str, Any]) -> None:
        """Test extra fields raise ValidationError."""
        valid_entry_data["unknown_field"] = "value"
        with pytest.raises(ValidationError):
            DeadLetterEntry(**valid_entry_data)

    def test_missing_required_field_raises(self) -> None:
        """Test missing required field raises ValidationError."""
        with pytest.raises(ValidationError):
            DeadLetterEntry(  # type: ignore[call-arg]
                id="test-id",
                payload=b"payload",
            )

    def test_empty_error_message_allowed(self, valid_entry_data: dict[str, Any]) -> None:
        """Test empty error_message is allowed (no min_length constraint)."""
        valid_entry_data["error_message"] = ""
        entry = DeadLetterEntry(**valid_entry_data)
        assert entry.error_message == ""

    def test_empty_source_queue_allowed(self, valid_entry_data: dict[str, Any]) -> None:
        """Test empty source_queue is allowed (has default)."""
        valid_entry_data["source_queue"] = ""
        entry = DeadLetterEntry(**valid_entry_data)
        assert entry.source_queue == ""


class TestDeadLetterEntryImmutability:
    """Tests for DeadLetterEntry frozen model behavior."""

    @pytest.fixture
    def entry(self) -> DeadLetterEntry:
        """Create a test entry."""
        return DeadLetterEntry(
            id="test-id-123",
            payload=b"test payload",
            error_type="ValueError",
            error_message="Something went wrong",
            source_queue="test-queue",
            timestamp=datetime.now(UTC),
        )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("id", "new-id"),
            ("payload", b"new payload"),
            ("retry_count", 5),
        ],
    )
    def test_cannot_modify_fields_after_creation(
        self, entry: DeadLetterEntry, field: str, value: str | bytes | int
    ) -> None:
        """Test frozen model fields cannot be modified after creation."""
        with pytest.raises(ValidationError):
            setattr(entry, field, value)

    def test_frozen_model_not_hashable_due_to_dict(self, entry: DeadLetterEntry) -> None:
        """Test frozen model is NOT hashable due to mutable dict field.

        Note: Although the model is frozen, it contains a `metadata: dict`
        field which makes the model unhashable. This is expected behavior.
        """
        with pytest.raises(TypeError, match="unhashable type"):
            hash(entry)

    def test_frozen_model_cannot_be_used_in_set(self, entry: DeadLetterEntry) -> None:
        """Test frozen model cannot be used in a set due to unhashable dict.

        Note: This documents the expected behavior - frozen models with
        mutable containers are not hashable and cannot be used in sets.
        """
        with pytest.raises(TypeError):
            {entry}  # noqa: B018


class TestDeadLetterEntryPayload:
    """Tests for payload handling."""

    def test_bytes_payload_preserved(self) -> None:
        """Test bytes payload is preserved exactly."""
        payload = b"\x00\x01\x02\xff\xfe"
        entry = DeadLetterEntry(
            id="test-id",
            payload=payload,
            error_type="ValueError",
            error_message="error",
            source_queue="queue",
            timestamp=datetime.now(UTC),
        )
        assert entry.payload == payload

    def test_empty_bytes_payload_allowed(self) -> None:
        """Test empty bytes payload is allowed."""
        entry = DeadLetterEntry(
            id="test-id",
            payload=b"",
            error_type="ValueError",
            error_message="error",
            source_queue="queue",
            timestamp=datetime.now(UTC),
        )
        assert entry.payload == b""

    def test_large_payload_accepted(self) -> None:
        """Test large payload is accepted (no size limit in domain model)."""
        large_payload = b"x" * 10_000
        entry = DeadLetterEntry(
            id="test-id",
            payload=large_payload,
            error_type="ValueError",
            error_message="error",
            source_queue="queue",
            timestamp=datetime.now(UTC),
        )
        assert len(entry.payload) == 10_000


class TestDeadLetterEntryMetadata:
    """Tests for metadata handling."""

    def test_metadata_with_string_values(self) -> None:
        """Test metadata with string values."""
        entry = DeadLetterEntry(
            id="test-id",
            payload=b"payload",
            error_type="ValueError",
            error_message="error",
            source_queue="queue",
            timestamp=datetime.now(UTC),
            metadata={"trace_id": "abc123", "user_id": "user_456"},
        )
        assert entry.metadata["trace_id"] == "abc123"
        assert entry.metadata["user_id"] == "user_456"

    def test_metadata_with_empty_dict(self) -> None:
        """Test metadata with empty dict."""
        entry = DeadLetterEntry(
            id="test-id",
            payload=b"payload",
            error_type="ValueError",
            error_message="error",
            source_queue="queue",
            timestamp=datetime.now(UTC),
            metadata={},
        )
        assert entry.metadata == {}

    def test_metadata_with_special_characters(self) -> None:
        """Test metadata with special characters in keys and values."""
        entry = DeadLetterEntry(
            id="test-id",
            payload=b"payload",
            error_type="ValueError",
            error_message="error",
            source_queue="queue",
            timestamp=datetime.now(UTC),
            metadata={"key:with:colons": "value with spaces", "unicode_key": "值"},
        )
        assert entry.metadata["key:with:colons"] == "value with spaces"
        assert entry.metadata["unicode_key"] == "值"
