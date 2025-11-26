"""Integration tests for Redis standalone client using real Redis via TestContainers.

Tests core Redis operations, health checks, and client lifecycle with a real Redis instance.

These 3 tests cover the most critical functionality:
1. Basic operations (GET/SET/DELETE) - core functionality everything depends on
2. Health check - critical for production monitoring and readiness probes
3. Client lifecycle - proper resource management (init/close)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from pixiu.core.enums import HealthCheckStatus
from pixiu.redis import (
    RedisConfig,
    RedisConnectionSettings,
    RedisDriverSettings,
    RedisPoolSettings,
    RedisSSLSettings,
    RedisStandaloneClient,
)

if TYPE_CHECKING:
    from pixiu.redis import BaseRedisClient
    from tests.integration.conftest import RedisContainerProtocol


@pytest.mark.integration
class TestRedisStandaloneBasicOperations:
    """Test basic Redis string operations: GET, SET, DELETE."""

    @pytest.mark.asyncio
    async def test_set_get_delete_operations(
        self, redis_client: BaseRedisClient
    ) -> None:
        """Test the fundamental Redis operations that everything else depends on.

        This is the most critical test because:
        - SET/GET are the foundation of all Redis usage
        - DELETE ensures we can clean up data
        - If these fail, the entire Redis integration is broken
        """
        async with redis_client.aget_client() as redis:
            # Test SET operation
            await redis.set("test_key", "test_value")

            # Test GET operation - verify value was stored
            value = await redis.get("test_key")
            assert value == "test_value", "GET should return the value that was SET"

            # Test GET for non-existent key - should return None
            missing = await redis.get("nonexistent_key")
            assert missing is None, "GET on missing key should return None"

            # Test DELETE operation
            deleted_count = await redis.delete("test_key")
            assert deleted_count == 1, "DELETE should return count of deleted keys"

            # Verify key was actually deleted
            after_delete = await redis.get("test_key")
            assert after_delete is None, "GET after DELETE should return None"

            # Test DELETE on non-existent key
            deleted_missing = await redis.delete("already_deleted_key")
            assert deleted_missing == 0, "DELETE on missing key should return 0"


@pytest.mark.integration
class TestRedisStandaloneHealthCheck:
    """Test Redis health check mechanism critical for production monitoring."""

    @pytest.mark.asyncio
    async def test_health_check_returns_healthy_when_connected(
        self, redis_client: BaseRedisClient
    ) -> None:
        """Test that health check returns HEALTHY for initialized client.

        Health checks are critical for:
        - Kubernetes readiness/liveness probes
        - Load balancer health checks
        - Service mesh circuit breakers
        """
        status = await redis_client.ahealth_check()

        assert status == HealthCheckStatus.HEALTHY, (
            "Health check should return HEALTHY for an initialized and connected client"
        )

    @pytest.mark.asyncio
    async def test_health_check_returns_initializing_when_not_initialized(
        self, redis_container: RedisContainerProtocol
    ) -> None:
        """Test that health check returns INITIALIZING for uninitialized client.

        This ensures we don't report HEALTHY before the client is ready,
        preventing premature traffic routing.
        """
        exposed_port = redis_container.get_exposed_port(6379)
        host = redis_container.get_container_host_ip()

        config = RedisConfig(
            connection=RedisConnectionSettings(
                host=host,
                port=exposed_port,
                db=0,
                password=SecretStr(""),
            ),
            ssl=RedisSSLSettings(enabled=False),
            pool=RedisPoolSettings(max_connections=10),
            driver=RedisDriverSettings(decode_responses=True),
        )

        # Create client but do NOT initialize it
        uninitialized_client = RedisStandaloneClient(config)

        try:
            status = await uninitialized_client.ahealth_check()
            assert status == HealthCheckStatus.INITIALIZING, (
                "Health check should return INITIALIZING when client is not initialized"
            )
        finally:
            # Ensure cleanup even though we didn't initialize
            await uninitialized_client.aclose()


@pytest.mark.integration
class TestRedisStandaloneLifecycle:
    """Test Redis client lifecycle: initialization, usage, and cleanup."""

    @pytest.mark.asyncio
    async def test_client_lifecycle_initialize_use_close(
        self, redis_container: RedisContainerProtocol
    ) -> None:
        """Test complete client lifecycle from creation to cleanup.

        Proper lifecycle management is critical for:
        - Preventing connection leaks
        - Ensuring clean shutdown during deployments
        - Resource management in long-running services
        """
        exposed_port = redis_container.get_exposed_port(6379)
        host = redis_container.get_container_host_ip()

        config = RedisConfig(
            connection=RedisConnectionSettings(
                host=host,
                port=exposed_port,
                db=0,
                password=SecretStr(""),
            ),
            ssl=RedisSSLSettings(enabled=False),
            pool=RedisPoolSettings(max_connections=10),
            driver=RedisDriverSettings(decode_responses=True),
        )

        client = RedisStandaloneClient(config)

        # Phase 1: Before initialization - accessing client should raise
        with pytest.raises(RuntimeError, match="Redis client not initialized"):
            _ = client.client

        # Phase 2: Initialize
        await client.ainitialize()

        # Phase 3: Use - should work after initialization
        async with client.aget_client() as redis:
            await redis.set("lifecycle_test", "initialized")
            value = await redis.get("lifecycle_test")
            assert value == "initialized", (
                "Client should be usable after initialization"
            )

        # Verify health is good
        status = await client.ahealth_check()
        assert status == HealthCheckStatus.HEALTHY

        # Phase 4: Close
        await client.aclose()

        # Phase 5: After close - client property should raise since _client is None
        with pytest.raises(RuntimeError, match="Redis client not initialized"):
            _ = client.client

        # Health check should return INITIALIZING after close (client is None)
        status_after_close = await client.ahealth_check()
        assert status_after_close == HealthCheckStatus.INITIALIZING
