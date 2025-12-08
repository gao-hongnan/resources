"""Unit tests for DLQConfig validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from transcreation.services.dlq import DLQConfig


class TestDLQConfigDefaults:
    """Tests for DLQConfig default values."""

    @pytest.mark.parametrize(
        ("field", "expected"),
        [
            ("stream_name", "pixiu:dlq"),
            ("consumer_group", "dlq-consumers"),
            ("key_prefix", "pixiu"),
            ("max_stream_length", 100_000),
            ("max_requeue_attempts", 3),
            ("block_timeout_ms", 5000),
            ("claim_timeout_ms", 60_000),
            ("batch_size", 100),
        ],
    )
    def test_default_values(self, field: str, expected: str | int) -> None:
        """Test DLQConfig has correct default values."""
        config = DLQConfig()
        assert getattr(config, field) == expected


class TestDLQConfigValidation:
    """Tests for DLQConfig field validation."""

    def test_max_stream_length_minimum_1000(self) -> None:
        """Test max stream length allows minimum value of 1000."""
        config = DLQConfig(max_stream_length=1000)
        assert config.max_stream_length == 1000

    def test_max_stream_length_below_minimum_raises(self) -> None:
        """Test max stream length below 1000 raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DLQConfig(max_stream_length=999)
        assert "max_stream_length" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("value", "should_pass"),
        [
            (1, True),
            (100, True),
            (1000, True),
            (0, False),
            (1001, False),
            (-1, False),
        ],
    )
    def test_batch_size_range(self, value: int, should_pass: bool) -> None:
        """Test batch size must be between 1 and 1000."""
        if should_pass:
            config = DLQConfig(batch_size=value)
            assert config.batch_size == value
        else:
            with pytest.raises(ValidationError):
                DLQConfig(batch_size=value)

    def test_claim_timeout_minimum_1000ms(self) -> None:
        """Test claim timeout allows minimum value of 1000ms."""
        config = DLQConfig(claim_timeout_ms=1000)
        assert config.claim_timeout_ms == 1000

    def test_claim_timeout_below_minimum_raises(self) -> None:
        """Test claim timeout below 1000ms raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            DLQConfig(claim_timeout_ms=999)
        assert "claim_timeout_ms" in str(exc_info.value)

    def test_block_timeout_allows_zero(self) -> None:
        """Test block timeout allows zero (non-blocking mode)."""
        config = DLQConfig(block_timeout_ms=0)
        assert config.block_timeout_ms == 0

    def test_block_timeout_negative_raises(self) -> None:
        """Test block timeout negative raises ValidationError."""
        with pytest.raises(ValidationError):
            DLQConfig(block_timeout_ms=-1)

    def test_max_requeue_attempts_minimum_1(self) -> None:
        """Test max requeue attempts allows minimum value of 1."""
        config = DLQConfig(max_requeue_attempts=1)
        assert config.max_requeue_attempts == 1

    def test_max_requeue_attempts_zero_raises(self) -> None:
        """Test max requeue attempts zero raises ValidationError."""
        with pytest.raises(ValidationError):
            DLQConfig(max_requeue_attempts=0)

    def test_stream_name_empty_raises(self) -> None:
        """Test empty stream name raises ValidationError."""
        with pytest.raises(ValidationError):
            DLQConfig(stream_name="")

    def test_consumer_group_empty_raises(self) -> None:
        """Test empty consumer group raises ValidationError."""
        with pytest.raises(ValidationError):
            DLQConfig(consumer_group="")

    def test_key_prefix_empty_raises(self) -> None:
        """Test empty key prefix raises ValidationError."""
        with pytest.raises(ValidationError):
            DLQConfig(key_prefix="")


class TestDLQConfigImmutability:
    """Tests for DLQConfig frozen model behavior."""

    def test_config_is_frozen(self) -> None:
        """Test config cannot be modified after creation."""
        config = DLQConfig()
        with pytest.raises(ValidationError):
            config.stream_name = "new-name"  # type: ignore[misc]

    def test_extra_fields_forbidden(self) -> None:
        """Test extra fields are rejected."""
        with pytest.raises(ValidationError):
            DLQConfig(unknown_field="value")  # type: ignore[call-arg]


class TestDLQConfigHelpers:
    """Tests for DLQConfig helper methods."""

    def test_get_main_queue_key_formatting(self) -> None:
        """Test get_main_queue_key returns correct format."""
        config = DLQConfig()
        result = config.get_main_queue_key("translations")
        assert result == "pixiu:queue:translations"

    def test_get_main_queue_key_with_custom_prefix(self) -> None:
        """Test get_main_queue_key uses custom prefix."""
        config = DLQConfig(key_prefix="myapp")
        result = config.get_main_queue_key("orders")
        assert result == "myapp:queue:orders"

    def test_get_main_queue_key_with_empty_queue_name(self) -> None:
        """Test get_main_queue_key handles empty queue name."""
        config = DLQConfig()
        result = config.get_main_queue_key("")
        assert result == "pixiu:queue:"

    def test_get_main_queue_key_with_special_characters(self) -> None:
        """Test get_main_queue_key preserves special characters."""
        config = DLQConfig()
        result = config.get_main_queue_key("queue-name:with:colons")
        assert result == "pixiu:queue:queue-name:with:colons"
