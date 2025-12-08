"""
Comprehensive DLQ Usage Example
================================

This example demonstrates the full lifecycle of the Dead Letter Queue:
1. Configuration and initialization
2. Routing failed messages to DLQ
3. Processing DLQ entries (consumer pattern)
4. Requeuing and redrive operations
5. Monitoring and recovery

Prerequisites: Redis Setup
--------------------------
Start Redis using Docker Compose:

    # Start Redis (and other services) in background
    docker run -d --name redis -p 6379:6379 redis:7-alpine
    OR
    docker-compose up -d redis
    ENV=local docker compose --env-file environments/environment/.env.local up -d redis

    # Or start all services
    docker-compose up -d

    # Verify Redis is running
    docker-compose ps redis

Verify Redis Connection
-----------------------
Use redis-cli to check Redis is accessible:

    # Check connection (should return PONG)
    redis-cli ping

    # Check Redis info
    redis-cli info server | head -5

    # Monitor commands in real-time (useful for debugging)
    redis-cli MONITOR

Inspect DLQ Data
----------------
Commands to inspect DLQ state:

    # List all DLQ-related keys
    redis-cli KEYS "pixiu:dlq*"

    # View stream info
    redis-cli XINFO STREAM pixiu:dlq

    # View consumer groups
    redis-cli XINFO GROUPS pixiu:dlq

    # View pending entries
    redis-cli XPENDING pixiu:dlq dlq-consumers

    # Read entries from stream
    redis-cli XRANGE pixiu:dlq - + COUNT 5

    # Get stream length
    redis-cli XLEN pixiu:dlq

Running This Example
--------------------
    # Ensure Redis is running first
    docker-compose up -d redis

    # Run the example
    uv run python examples/dlq_usage.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

from transcreation.infrastructure.redis import (
    RedisConfig,
    RedisConnectionSettings,
    RedisPoolSettings,
    create_redis_client,
)
from transcreation.infrastructure.redis.base import BaseRedisClient
from transcreation.services.dlq import (
    DeadLetterEntry,
    DeadLetterQueue,
    DLQConfig,
    FailureCategory,
)

_ = (DeadLetterEntry, datetime)  # Used in helper functions below

console = Console()


class TransientError(Exception):
    """Temporary failure that may succeed on retry."""


class PermanentError(Exception):
    """Permanent failure that will never succeed."""


async def process_message(payload: bytes) -> None:
    """Placeholder for actual message processing logic."""
    _ = payload


# =============================================================================
# 1. CONFIGURATION & INITIALIZATION
# =============================================================================


async def create_dlq(redis_client: BaseRedisClient) -> DeadLetterQueue:
    """Create and initialize a DLQ instance."""
    # Custom configuration (all fields have sensible defaults)
    config = DLQConfig(
        stream_name="pixiu:dlq",  # Redis stream key
        consumer_group="dlq-consumers",  # Consumer group name
        key_prefix="pixiu",  # Prefix for queue keys
        max_stream_length=100_000,  # Bounded stream (prevents unbounded growth)
        max_requeue_attempts=3,  # Max times to requeue before discard
        block_timeout_ms=5000,  # Consumer blocking timeout
        claim_timeout_ms=60_000,  # Stale message threshold (1 minute)
        batch_size=100,  # Entries per batch
    )

    dlq = DeadLetterQueue(redis_client, config)

    # Initialize creates the consumer group (idempotent - safe to call multiple times)
    await dlq.ainitialize()

    return dlq


# =============================================================================
# 2. ROUTING FAILED MESSAGES TO DLQ
# =============================================================================


async def process_with_dlq_fallback(
    dlq: DeadLetterQueue,
    payload: bytes,
    source_queue: str,
) -> None:
    """Process a message with DLQ fallback on failure."""
    retry_count = 0
    max_retries = 3

    while retry_count < max_retries:
        try:
            # Your actual processing logic here
            await process_message(payload)
            return  # Success!

        except TransientError as e:
            retry_count += 1
            if retry_count >= max_retries:
                # Route to DLQ after exhausting retries
                await dlq.dead_letter(
                    payload=payload,
                    error=e,
                    source_queue=source_queue,
                    retry_count=retry_count,
                    category=FailureCategory.TRANSIENT,
                    metadata={
                        "trace_id": "abc123",
                        "user_id": "user_456",
                    },
                )

        except PermanentError as e:
            # Permanent errors go directly to DLQ (no retries)
            await dlq.dead_letter(
                payload=payload,
                error=e,
                source_queue=source_queue,
                retry_count=0,
                category=FailureCategory.PERMANENT,
            )
            return

        except Exception as e:
            # Unexpected errors - categorize as transient for investigation
            await dlq.dead_letter(
                payload=payload,
                error=e,
                source_queue=source_queue,
                retry_count=retry_count,
                category=FailureCategory.TRANSIENT,
            )
            return


# =============================================================================
# 3. DLQ CONSUMER PATTERN (Processing DLQ Entries)
# =============================================================================


async def dlq_consumer_loop(dlq: DeadLetterQueue) -> None:
    """
    Consumer loop for processing DLQ entries.

    This pattern uses:
    - read() for consuming reads (removes from pending)
    - acknowledge() after successful processing
    - requeue() when DLQ processing itself fails
    """
    while True:
        # Read batch of entries (blocking call)
        entries = await dlq.read(max_count=10)

        if not entries:
            continue

        for entry in entries:
            try:
                # Inspect the entry
                print(f"Processing DLQ entry: {entry.id}")
                print(f"  Source queue: {entry.source_queue}")
                print(f"  Error type: {entry.error_type}")
                print(f"  Error message: {entry.error_message}")
                print(f"  Retry count: {entry.retry_count}")
                print(f"  Category: {entry.category}")
                print(f"  Timestamp: {entry.timestamp}")

                # Your DLQ processing logic here
                await handle_dlq_entry(entry)

                # Acknowledge successful processing
                await dlq.acknowledge([entry])

            except Exception:
                # DLQ processing failed - requeue for later retry
                new_stream_id = await dlq.requeue(entry)

                if new_stream_id is None:
                    # Entry discarded after max_requeue_attempts
                    print(f"Entry {entry.id} discarded after max requeue attempts")
                else:
                    print(f"Entry {entry.id} requeued as {new_stream_id}")


async def handle_dlq_entry(entry: DeadLetterEntry) -> None:
    """
    Handle a DLQ entry based on its failure category.

    This is where you implement your DLQ processing logic:
    - Investigate the error
    - Fix the underlying issue
    - Decide whether to redrive or discard
    """
    match entry.category:
        case FailureCategory.TRANSIENT:
            # Transient errors may self-resolve - check if ready for redrive
            pass

        case FailureCategory.PERMANENT:
            # Permanent errors require manual intervention
            # Log for investigation, alert operations team
            pass

        case FailureCategory.POISON:
            # Poison pill - message consistently causes failures
            # May need to discard or fix message format
            pass

        case FailureCategory.RESOURCE_EXHAUSTED:
            # Wait for resources to free up
            pass

        case FailureCategory.DEPENDENCY_FAILURE:
            # External dependency was down - check if restored
            pass


# =============================================================================
# 4. INSPECTION (Non-Consuming Read)
# =============================================================================


async def inspect_dlq(dlq: DeadLetterQueue) -> None:
    """
    Inspect DLQ entries without consuming them.

    Use peek() for:
    - Debugging and investigation
    - Building admin dashboards
    - Deciding which entries to redrive
    """
    # Peek at first 10 entries (does not affect consumer group state)
    entries = await dlq.peek(max_count=10)

    for entry in entries:
        print(f"Entry {entry.id}:")
        print(f"  Stream ID: {entry.stream_id}")
        print(f"  Source: {entry.source_queue}")
        print(f"  Category: {entry.category}")
        print(f"  Error: {entry.error_type}: {entry.error_message}")
        print(f"  Payload size: {len(entry.payload)} bytes")
        print(f"  Metadata: {entry.metadata}")
        print()


# =============================================================================
# 5. REDRIVE OPERATIONS (Replaying to Main Queue)
# =============================================================================


async def redrive_transient_failures(
    dlq: DeadLetterQueue,
    target_queue: str,
) -> int:
    """
    Redrive transient failures back to the main queue.

    Use after:
    - The underlying issue has been fixed
    - Resources are available again
    - Dependencies are restored
    """
    # Redrive only transient failures
    count = await dlq.redrive_messages(
        target_queue=target_queue,
        predicate=lambda e: e.category == FailureCategory.TRANSIENT,
        max_count=100,
    )

    print(f"Redrove {count} transient failures to {target_queue}")
    return count


async def redrive_by_time_window(
    dlq: DeadLetterQueue,
    target_queue: str,
    since: datetime,
) -> int:
    """Redrive entries that failed after a specific time."""
    count = await dlq.redrive_messages(
        target_queue=target_queue,
        predicate=lambda e: e.timestamp >= since,
    )

    return count


async def redrive_single_message(
    dlq: DeadLetterQueue,
    stream_id: str,
    target_queue: str,
) -> bool:
    """Redrive a single message by its stream ID."""
    success = await dlq.redrive_message(stream_id, target_queue)

    if success:
        print(f"Successfully redrove {stream_id} to {target_queue}")
    else:
        print(f"Entry {stream_id} not found")

    return success


# =============================================================================
# 6. MONITORING & RECOVERY
# =============================================================================


async def monitor_dlq(dlq: DeadLetterQueue) -> dict[str, int | str]:
    """Get DLQ health metrics."""
    total_count = await dlq.get_message_count()
    pending_count = await dlq.get_pending_count()

    metrics: dict[str, int | str] = {
        "total_entries": total_count,
        "pending_entries": pending_count,
        "consumer_id": dlq.consumer_id,
        "stream_name": dlq.stream_name,
    }

    # Alert if DLQ depth exceeds threshold
    if total_count > 1000:
        print(f"WARNING: DLQ depth is {total_count} - investigation required")

    return metrics


async def recover_stale_messages(dlq: DeadLetterQueue) -> None:
    """
    Claim stale messages from dead consumers.

    Use when:
    - A consumer crashed without acknowledging entries
    - A consumer is hung and not processing
    - Entries have been pending longer than claim_timeout_ms
    """
    stale_entries = await dlq.claim_stale()

    if stale_entries:
        print(f"Claimed {len(stale_entries)} stale entries")

        for entry in stale_entries:
            # Process claimed entries
            await handle_dlq_entry(entry)
            await dlq.acknowledge([entry])


# =============================================================================
# 7. COMPLETE EXAMPLE
# =============================================================================


async def create_redis_client_local() -> BaseRedisClient:
    """Create Redis client for local development."""
    from transcreation.infrastructure.redis import RedisDriverSettings, RedisSSLSettings

    config = RedisConfig(
        connection=RedisConnectionSettings(
            host="localhost",
            port=6379,
            db=0,
        ),
        ssl=RedisSSLSettings(enabled=False),
        pool=RedisPoolSettings(
            max_connections=10,
            health_check_interval=30,
        ),
        driver=RedisDriverSettings(),
    )
    client = create_redis_client(config)
    await client.ainitialize()
    return client


async def main() -> None:
    """Complete example demonstrating DLQ lifecycle."""
    console.print(Panel("[bold cyan]DLQ Demo Starting[/bold cyan]", expand=False))

    redis_client = await create_redis_client_local()
    console.print("[green]✓[/green] Redis client initialized")

    dlq = await create_dlq(redis_client)
    console.print("[green]✓[/green] DLQ initialized")

    console.print("\n[bold]1. Sending failed messages to DLQ...[/bold]")
    for i in range(3):
        error = TransientError(f"Connection timeout #{i + 1}")
        await dlq.dead_letter(
            payload=f"message-payload-{i}".encode(),
            error=error,
            source_queue="translations",
            retry_count=3,
            category=FailureCategory.TRANSIENT,
            metadata={"trace_id": f"trace-{i}", "attempt": i + 1},
        )
        console.print(f"  [yellow]→[/yellow] Sent message {i + 1} to DLQ")

    metrics = await monitor_dlq(dlq)
    console.print(f"\n[bold]2. DLQ Metrics:[/bold] {metrics}")

    console.print("\n[bold]3. Peeking at DLQ entries (non-consuming)...[/bold]")
    await inspect_dlq(dlq)

    console.print("\n[bold]4. Consuming and acknowledging entries...[/bold]")
    entries = await dlq.read(max_count=10)
    console.print(f"  Read {len(entries)} entries")
    if entries:
        await dlq.acknowledge(entries)
        console.print(f"  [green]✓[/green] Acknowledged {len(entries)} entries")

    final_metrics = await monitor_dlq(dlq)
    console.print(f"\n[bold]5. Final Metrics:[/bold] {final_metrics}")

    await redis_client.aclose()
    console.print("\n[green]✓[/green] Redis client closed")
    console.print(Panel("[bold green]DLQ Demo Complete[/bold green]", expand=False))


if __name__ == "__main__":
    asyncio.run(main())
