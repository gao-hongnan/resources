from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .enums import HealthStatus


class PoolHealthBase(BaseModel):
    """Base health metrics shared by all pool health models.

    This provides common fields and computed properties for pool health
    monitoring across single pools and replicas.
    """

    model_config = ConfigDict(frozen=True)

    status: HealthStatus
    pool_size: int
    pool_max_size: int
    pool_idle_size: int = 0
    latency_s: float | None = None
    message: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pool_utilization_pct(self) -> float:
        """Pool utilization as percentage."""
        if self.pool_max_size == 0:
            return 0.0
        return (self.pool_size / self.pool_max_size) * 100

    def is_healthy(self) -> bool:
        """Check if pool is healthy."""
        return self.status == HealthStatus.HEALTHY


class ReplicaHealthInfo(PoolHealthBase):
    """Health information for a database replica."""

    host: str
    port: int


class HealthCheckResult(PoolHealthBase):
    """Result of a database health check for a single pool."""

    timestamp: datetime = Field(default_factory=datetime.now)
    replicas: tuple[ReplicaHealthInfo, ...] = Field(default_factory=tuple)

    @classmethod
    def initializing(cls: type[Self], pool_max_size: int) -> Self:
        """Create result for pool not yet initialized.

        Parameters
        ----------
        pool_max_size
            Maximum pool size from configuration.

        Returns
        -------
        Self
            HealthCheckResult with INITIALIZING status.
        """
        return cls(
            status=HealthStatus.INITIALIZING,
            pool_size=0,
            pool_max_size=pool_max_size,
            latency_s=None,
            message="Pool not initialized",
        )

    @classmethod
    def unhealthy(cls: type[Self], pool_max_size: int, error: str) -> Self:
        """Create result for failed health check.

        Parameters
        ----------
        pool_max_size
            Maximum pool size from configuration.
        error
            Error message describing the failure.

        Returns
        -------
        Self
            HealthCheckResult with UNHEALTHY status.
        """
        return cls(
            status=HealthStatus.UNHEALTHY,
            pool_size=0,
            pool_max_size=pool_max_size,
            latency_s=None,
            message=error,
        )

    @classmethod
    def healthy(
        cls: type[Self],
        pool_size: int,
        pool_max_size: int,
        latency_s: float,
        pool_idle_size: int,
        replicas: tuple[ReplicaHealthInfo, ...] = (),
    ) -> Self:
        """Create result for successful health check.

        Parameters
        ----------
        pool_size
            Current number of connections in the pool.
        pool_max_size
            Maximum pool size.
        latency_s
            Health check latency in seconds.
        pool_idle_size
            Number of idle connections in the pool.
        replicas
            Health information for replicas (if any).

        Returns
        -------
        Self
            HealthCheckResult with HEALTHY status.
        """
        return cls(
            status=HealthStatus.HEALTHY,
            pool_size=pool_size,
            pool_max_size=pool_max_size,
            latency_s=latency_s,
            message="Pool is healthy",
            pool_idle_size=pool_idle_size,
            replicas=replicas,
        )


class ClusterHealthResult(BaseModel):
    """Health check result for the entire database cluster.

    Aggregates health status across primary and all replica pools.
    """

    model_config = ConfigDict(frozen=True)

    status: HealthStatus
    primary: HealthCheckResult
    replicas: tuple[ReplicaHealthInfo, ...]
    healthy_replica_count: int
    total_replica_count: int

    @property
    def is_healthy(self) -> bool:
        """Check if cluster is fully healthy (primary + all replicas)."""
        return self.status == HealthStatus.HEALTHY

    @property
    def is_operational(self) -> bool:
        """Check if cluster can serve requests (primary healthy)."""
        return self.primary.status == HealthStatus.HEALTHY
