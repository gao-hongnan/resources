from __future__ import annotations

from pydantic import BaseModel, Field


class RetryConfig(BaseModel):
    max_attempts: int = Field(default=3, ge=1, description="Maximum retry attempts")
    max_delay_seconds: float | None = Field(default=None, ge=0, description="Maximum total delay (None = unlimited)")

    use_jitter: bool = Field(default=True, description="Use jitter with exponential backoff (False = pure exponential)")
    wait_min: float = Field(default=1.0, ge=0, description="Minimum wait time in seconds")
    wait_max: float = Field(default=60.0, ge=0, description="Maximum wait time in seconds")
    wait_multiplier: float = Field(default=2.0, ge=1.0, description="Multiplier for exponential backoff")

    retry_on_exceptions: tuple[type[Exception], ...] | None = Field(
        default=None, description="Specific exception types to retry on (None = all exceptions)"
    )

    reraise: bool = Field(default=True, description="Reraise exception after all retries fail")
