from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DLQConfig(BaseModel):
    """Configuration for Dead Letter Queue using Redis Streams.

    Combines reliability features (consumer groups, stream limits) with
    clean configuration patterns.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Stream settings
    stream_name: str = Field(
        default="pixiu:dlq",
        min_length=1,
        description="Redis stream name for DLQ",
    )
    consumer_group: str = Field(
        default="dlq-consumers",
        min_length=1,
        description="Consumer group name for reliable delivery",
    )
    key_prefix: str = Field(
        default="pixiu",
        min_length=1,
        description="Prefix for Redis keys",
    )

    # Limits
    max_stream_length: int = Field(
        default=100_000,
        ge=1000,
        description="Maximum entries in stream (older entries trimmed)",
    )
    max_requeue_attempts: int = Field(
        default=3,
        ge=1,
        description="Maximum times an entry can be requeued before discard",
    )

    # Timeouts
    block_timeout_ms: int = Field(
        default=5000,
        ge=0,
        description="Blocking timeout for XREADGROUP (0 = non-blocking)",
    )
    claim_timeout_ms: int = Field(
        default=60_000,
        ge=1000,
        description="Idle time before entry can be claimed from dead consumer",
    )
    batch_size: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Number of entries to read per batch",
    )

    def get_main_queue_key(self, queue_name: str) -> str:
        """Generate Redis stream key for main queue.

        Parameters
        ----------
        queue_name : str
            Name of the queue.

        Returns
        -------
        str
            Redis key in format "{prefix}:queue:{queue_name}".
        """
        return f"{self.key_prefix}:queue:{queue_name}"
