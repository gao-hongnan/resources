from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ...core.enums import HealthCheckStatus


class HealthCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HealthCheckStatus
    timestamp: datetime
    pool_initialized: bool
    pool_size: int | None = None
    pool_max_size: int | None = None
    pool_free_size: int | None = None
    response_time_ms: float | None = None
    error: str | None = None
