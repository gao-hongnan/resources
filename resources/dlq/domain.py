from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FailureCategory(str, Enum):
    """Categorization of failure types for routing decisions."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    POISON = "poison"
    RESOURCE_EXHAUSTED = "exhausted"
    DEPENDENCY_FAILURE = "dependency"


class DeadLetterEntry(BaseModel):
    """Represents an entry in the Dead Letter Queue.

    Contains the original message payload plus failure metadata
    for debugging and redrive operations.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(
        min_length=1,
        description="Unique identifier for this entry (UUID)",
    )
    stream_id: str = Field(
        default="",
        description="Redis Stream entry ID (e.g., '1704067200000-0')",
    )
    payload: bytes = Field(
        description="Raw message payload (preserved exactly as received)",
    )
    error_type: str = Field(
        min_length=1,
        description="Exception class name",
    )
    error_message: str = Field(
        description="Exception message",
    )
    error_traceback: str = Field(
        default="",
        description="Full stack trace",
    )
    retry_count: int = Field(
        default=0,
        ge=0,
        description="Number of retry attempts before DLQ routing",
    )
    requeue_count: int = Field(
        default=0,
        ge=0,
        description="Number of times requeued from DLQ",
    )
    category: FailureCategory = Field(
        default=FailureCategory.TRANSIENT,
        description="Failure categorization for routing",
    )
    source_queue: str = Field(
        default="",
        description="Name of the original queue",
    )
    timestamp: datetime = Field(
        description="When the failure occurred",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Arbitrary headers/metadata from original message",
    )
