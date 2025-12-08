from __future__ import annotations

import base64
import traceback
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Awaitable, cast

from redis.exceptions import ResponseError
from redis.typing import EncodableT, FieldT, StreamIdT

from ...core.logger import get_logger
from .config import DLQConfig
from .domain import DeadLetterEntry, FailureCategory

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

    from ...infrastructure.redis.base import BaseRedisClient

logger: BoundLogger = get_logger(__name__)


class DeadLetterQueue:
    """Dead Letter Queue using Redis Streams with consumer groups.

    Provides reliable at-least-once delivery with:
    - Consumer groups for message acknowledgment (XREADGROUP + XACK)
    - Stale message claiming from dead consumers (XCLAIM)
    - Bounded stream length (maxlen)
    - Requeue limits to prevent infinite loops
    - Redrive to main queue for recovery

    Usage Pattern
    -------------
    ```python
    dlq = DeadLetterQueue(redis_client, DLQConfig())
    await dlq.ainitialize()

    # Route failed message
    stream_id = await dlq.dead_letter(
        payload=b"message bytes",
        error=exception,
        source_queue="translations",
    )

    # Process DLQ entries
    entries = await dlq.read(max_count=10)
    for entry in entries:
        # Process entry...
        await dlq.acknowledge([entry])

    # Redrive to main queue after fix
    count = await dlq.redrive_messages("translations")
    ```
    """

    # H1/H4: Lua script for atomic redrive (read + add + delete in single operation)
    _REDRIVE_LUA_SCRIPT: str = """
local dlq_stream = KEYS[1]
local main_stream = KEYS[2]
local stream_id = ARGV[1]

-- Read entry from DLQ
local entries = redis.call('XRANGE', dlq_stream, stream_id, stream_id)
if #entries == 0 then
    return nil
end

-- Get the fields from the entry
local fields = entries[1][2]

-- Add to main queue with all original fields
redis.call('XADD', main_stream, '*', unpack(fields))

-- Delete from DLQ (atomic - either both happen or neither)
redis.call('XDEL', dlq_stream, stream_id)

return 1
"""

    def __init__(self, redis_client: BaseRedisClient, config: DLQConfig | None = None) -> None:
        self._redis_client = redis_client
        self._config = config or DLQConfig()
        self._consumer_id = f"worker_{uuid.uuid4().hex[:8]}"
        self._initialized = False

    @property
    def consumer_id(self) -> str:
        """Unique identifier for this consumer instance."""
        return self._consumer_id

    @property
    def stream_name(self) -> str:
        """Redis stream name for this DLQ."""
        return self._config.stream_name

    def _ensure_initialized(self) -> None:
        """Ensure DLQ is initialized before operations.

        Raises
        ------
        RuntimeError
            If ainitialize() has not been called.
        """
        if not self._initialized:
            raise RuntimeError("DeadLetterQueue not initialized. Call ainitialize() first.")

    async def ainitialize(self) -> None:
        """Initialize consumer group for the DLQ stream.

        Creates the consumer group if it doesn't exist. Safe to call multiple times.
        """
        if self._initialized:
            return

        async with self._redis_client.aget_client() as client:
            try:
                await client.xgroup_create(
                    name=self._config.stream_name,
                    groupname=self._config.consumer_group,
                    id="0",
                    mkstream=True,
                )
                logger.info(
                    "Created DLQ consumer group",
                    stream=self._config.stream_name,
                    group=self._config.consumer_group,
                )
            except ResponseError as e:
                if "BUSYGROUP" in str(e):
                    logger.debug(
                        "Consumer group already exists",
                        stream=self._config.stream_name,
                        group=self._config.consumer_group,
                    )
                else:
                    raise

        self._initialized = True
        logger.info(
            "DLQ initialized",
            stream=self._config.stream_name,
            consumer_id=self._consumer_id,
        )

    async def dead_letter(
        self,
        payload: bytes,
        error: Exception,
        source_queue: str,
        *,
        retry_count: int = 0,
        category: FailureCategory = FailureCategory.TRANSIENT,
        metadata: dict[str, str] | None = None,
        entry_id: str | None = None,
    ) -> str:
        """Route a failed message to the Dead Letter Queue.

        Parameters
        ----------
        payload : bytes
            Raw message payload.
        error : Exception
            The exception that caused the failure.
        source_queue : str
            Name of the original queue.
        retry_count : int
            Number of retry attempts before DLQ routing.
        category : FailureCategory
            Failure categorization for routing decisions.
        metadata : dict[str, str] | None
            Additional context metadata.
        entry_id : str | None
            Optional entry ID (UUID generated if not provided).

        Returns
        -------
        str
            The Redis Stream entry ID.
        """
        effective_id = entry_id or str(uuid.uuid4())

        fields: dict[FieldT, EncodableT] = {
            "id": effective_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "source_queue": source_queue,
            "payload": base64.b64encode(payload).decode(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "error_traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__)),
            "retry_count": str(retry_count),
            "requeue_count": "0",
            "category": category.value,
        }

        if metadata:
            for key, value in metadata.items():
                fields[f"meta_{key}"] = value

        async with self._redis_client.aget_client() as client:
            stream_id_raw = await client.xadd(
                name=self._config.stream_name,
                fields=fields,
                maxlen=self._config.max_stream_length,
            )
            stream_id = stream_id_raw.decode() if isinstance(stream_id_raw, bytes) else str(stream_id_raw)

        logger.warning(
            "Routed to DLQ",
            stream_id=stream_id,
            entry_id=effective_id,
            error_type=type(error).__name__,
            category=category.value,
            source_queue=source_queue,
        )

        return stream_id

    async def read(self, *, max_count: int | None = None) -> list[DeadLetterEntry]:
        """Read entries from DLQ using consumer group (consuming read).

        Messages read must be acknowledged with `acknowledge()` after processing.

        Parameters
        ----------
        max_count : int | None
            Maximum entries to read. Defaults to config batch_size.

        Returns
        -------
        list[DeadLetterEntry]
            Entries read from the DLQ.

        Raises
        ------
        RuntimeError
            If ainitialize() has not been called.
        """
        self._ensure_initialized()
        effective_count = max_count or self._config.batch_size

        async with self._redis_client.aget_client() as client:
            raw_entries = await client.xreadgroup(
                groupname=self._config.consumer_group,
                consumername=self._consumer_id,
                streams={self._config.stream_name: ">"},
                count=effective_count,
                block=self._config.block_timeout_ms,
            )

        entries: list[DeadLetterEntry] = []

        if raw_entries:
            for _stream_name, stream_entries in raw_entries:
                for stream_id_raw, fields_raw in stream_entries:
                    stream_id = stream_id_raw.decode() if isinstance(stream_id_raw, bytes) else str(stream_id_raw)
                    fields = self._decode_fields(fields_raw)
                    entry = self._parse_entry(stream_id, fields)
                    entries.append(entry)

        if entries:
            logger.info(
                "Read entries from DLQ",
                count=len(entries),
                consumer_id=self._consumer_id,
            )

        return entries

    async def peek(self, *, max_count: int = 10) -> list[DeadLetterEntry]:
        """Inspect entries in DLQ without consuming them.

        Uses XRANGE instead of XREADGROUP - does not affect consumer group state.

        Parameters
        ----------
        max_count : int
            Maximum entries to return.

        Returns
        -------
        list[DeadLetterEntry]
            Entries in the DLQ.

        Raises
        ------
        RuntimeError
            If ainitialize() has not been called.
        """
        self._ensure_initialized()
        async with self._redis_client.aget_client() as client:
            raw_entries = await client.xrange(
                self._config.stream_name,
                count=max_count,
            )

        entries: list[DeadLetterEntry] = []
        for stream_id_raw, fields_raw in raw_entries:
            stream_id = stream_id_raw.decode() if isinstance(stream_id_raw, bytes) else str(stream_id_raw)
            fields = self._decode_fields(fields_raw)
            entry = self._parse_entry(stream_id, fields)
            entries.append(entry)

        return entries

    async def acknowledge(self, entries: Sequence[DeadLetterEntry]) -> int:
        """Acknowledge processed entries.

        Parameters
        ----------
        entries : Sequence[DeadLetterEntry]
            Entries to acknowledge.

        Returns
        -------
        int
            Number of entries acknowledged.

        Raises
        ------
        RuntimeError
            If ainitialize() has not been called.
        """
        self._ensure_initialized()
        if not entries:
            return 0

        stream_ids = [e.stream_id for e in entries if e.stream_id]
        if not stream_ids:
            return 0

        async with self._redis_client.aget_client() as client:
            acked = await client.xack(
                self._config.stream_name,
                self._config.consumer_group,
                *stream_ids,
            )

        logger.info(
            "Acknowledged DLQ entries",
            count=acked,
            stream_ids=stream_ids,
        )

        return int(acked)

    async def requeue(self, entry: DeadLetterEntry) -> str | None:
        """Requeue entry back to DLQ with incremented requeue_count.

        Use when DLQ processing fails but the entry should be retried later.
        If max_requeue_attempts is exceeded, the entry is discarded.

        Parameters
        ----------
        entry : DeadLetterEntry
            Entry to requeue.

        Returns
        -------
        str | None
            New stream_id if requeued, None if discarded (max attempts exceeded).

        Raises
        ------
        RuntimeError
            If ainitialize() has not been called.
        """
        self._ensure_initialized()
        new_requeue_count = entry.requeue_count + 1

        if new_requeue_count > self._config.max_requeue_attempts:
            logger.error(
                "Entry exceeded max requeue attempts, discarding",
                entry_id=entry.id,
                requeue_count=entry.requeue_count,
                max_attempts=self._config.max_requeue_attempts,
            )
            await self.acknowledge([entry])
            return None

        fields: dict[FieldT, EncodableT] = {
            "id": entry.id,
            "timestamp": entry.timestamp.isoformat(),
            "source_queue": entry.source_queue,
            "payload": base64.b64encode(entry.payload).decode(),
            "error_type": entry.error_type,
            "error_message": entry.error_message,
            "error_traceback": entry.error_traceback,
            "retry_count": str(entry.retry_count),
            "requeue_count": str(new_requeue_count),
            "category": entry.category.value,
        }

        for key, value in entry.metadata.items():
            fields[f"meta_{key}"] = value

        # H2: Perform XADD and XACK in same context manager to reduce race window
        async with self._redis_client.aget_client() as client:
            stream_id_raw = await client.xadd(
                name=self._config.stream_name,
                fields=fields,
                maxlen=self._config.max_stream_length,
            )
            stream_id = stream_id_raw.decode() if isinstance(stream_id_raw, bytes) else str(stream_id_raw)

            # Acknowledge old entry in same connection to minimize race window
            if entry.stream_id:
                await client.xack(
                    self._config.stream_name,
                    self._config.consumer_group,
                    entry.stream_id,
                )

        logger.warning(
            "Requeued DLQ entry",
            entry_id=entry.id,
            old_stream_id=entry.stream_id,
            new_stream_id=stream_id,
            requeue_count=new_requeue_count,
        )

        return stream_id

    async def claim_stale(self) -> list[DeadLetterEntry]:
        """Claim stale entries from dead consumers.

        Entries that have been pending longer than `claim_timeout_ms` are
        claimed by this consumer.

        Returns
        -------
        list[DeadLetterEntry]
            Claimed entries.

        Raises
        ------
        RuntimeError
            If ainitialize() has not been called.
        """
        self._ensure_initialized()
        async with self._redis_client.aget_client() as client:
            pending_raw = await client.xpending_range(
                name=self._config.stream_name,
                groupname=self._config.consumer_group,
                min="-",
                max="+",
                count=self._config.batch_size,
            )

            stale_ids: list[StreamIdT] = []
            for pending_entry in pending_raw:
                message_id = pending_entry.get("message_id")
                time_since_delivered = pending_entry.get("time_since_delivered", 0)

                if message_id and time_since_delivered > self._config.claim_timeout_ms:
                    msg_id_str: StreamIdT = message_id.decode() if isinstance(message_id, bytes) else str(message_id)
                    stale_ids.append(msg_id_str)

            if not stale_ids:
                return []

            claimed_raw = await client.xclaim(
                name=self._config.stream_name,
                groupname=self._config.consumer_group,
                consumername=self._consumer_id,
                min_idle_time=self._config.claim_timeout_ms,
                message_ids=stale_ids,
            )

        entries: list[DeadLetterEntry] = []
        for stream_id_raw, fields_raw in claimed_raw:
            stream_id = stream_id_raw.decode() if isinstance(stream_id_raw, bytes) else str(stream_id_raw)
            fields = self._decode_fields(fields_raw)
            entry = self._parse_entry(stream_id, fields)
            entries.append(entry)

        if entries:
            logger.info(
                "Claimed stale DLQ entries",
                count=len(entries),
                consumer_id=self._consumer_id,
            )

        return entries

    async def redrive_message(self, stream_id: str, target_queue: str) -> bool:
        """Redrive a single entry from DLQ to main queue.

        Uses a Lua script for atomic read+add+delete to prevent duplicates
        or message loss on crash.

        Parameters
        ----------
        stream_id : str
            Redis Stream entry ID to redrive.
        target_queue : str
            Target queue name.

        Returns
        -------
        bool
            True if redriven successfully, False if not found.

        Raises
        ------
        RuntimeError
            If ainitialize() has not been called.
        """
        self._ensure_initialized()
        main_stream = self._config.get_main_queue_key(target_queue)

        async with self._redis_client.aget_client() as client:
            # H1/H4: Use Lua script for atomic redrive
            result = await cast(
                Awaitable[int | None],
                client.eval(
                    self._REDRIVE_LUA_SCRIPT,
                    2,  # Number of keys
                    self._config.stream_name,
                    main_stream,
                    stream_id,
                ),
            )

        if result:
            logger.info(
                "Redrove entry from DLQ",
                stream_id=stream_id,
                target_queue=target_queue,
            )
            return True

        logger.warning(
            "Entry not found in DLQ",
            stream_id=stream_id,
        )
        return False

    async def redrive_messages(
        self,
        target_queue: str,
        *,
        predicate: Callable[[DeadLetterEntry], bool] | None = None,
        max_count: int | None = None,
    ) -> int:
        """Redrive entries from DLQ to main queue.

        Parameters
        ----------
        target_queue : str
            Target queue name.
        predicate : Callable[[DeadLetterEntry], bool] | None
            Optional filter. Only entries returning True are redriven.
        max_count : int | None
            Maximum entries to redrive. None means all.

        Returns
        -------
        int
            Number of entries redriven.

        Raises
        ------
        RuntimeError
            If ainitialize() has not been called.
        """
        self._ensure_initialized()
        main_stream = self._config.get_main_queue_key(target_queue)
        redriven_count = 0
        last_id = "-"

        async with self._redis_client.aget_client() as client:
            while max_count is None or redriven_count < max_count:
                remaining = None if max_count is None else max_count - redriven_count
                fetch_count = min(self._config.batch_size, remaining) if remaining else self._config.batch_size

                raw_entries = await client.xrange(
                    self._config.stream_name,
                    min=last_id,
                    count=fetch_count,
                )

                if not raw_entries:
                    break

                ids_to_delete: list[str] = []

                for stream_id_raw, fields_raw in raw_entries:
                    stream_id = stream_id_raw.decode() if isinstance(stream_id_raw, bytes) else str(stream_id_raw)

                    if stream_id == last_id:
                        continue

                    last_id = stream_id
                    fields = self._decode_fields(fields_raw)
                    entry = self._parse_entry(stream_id, fields)

                    if predicate is not None and not predicate(entry):
                        continue

                    redrive_fields: dict[FieldT, EncodableT] = {
                        "message_id": entry.id,
                        "payload": base64.b64encode(entry.payload).decode(),
                    }
                    for meta_key, meta_value in entry.metadata.items():
                        redrive_fields[meta_key] = meta_value
                    await client.xadd(main_stream, redrive_fields)

                    ids_to_delete.append(stream_id)
                    redriven_count += 1

                    if max_count is not None and redriven_count >= max_count:
                        break

                if ids_to_delete:
                    await client.xdel(self._config.stream_name, *ids_to_delete)

                if len(raw_entries) < fetch_count:
                    break

        logger.info(
            "Completed DLQ redrive",
            target_queue=target_queue,
            redriven_count=redriven_count,
        )

        return redriven_count

    async def get_message_count(self) -> int:
        """Get total number of entries in DLQ stream."""
        async with self._redis_client.aget_client() as client:
            result = await cast(Awaitable[int], client.xlen(self._config.stream_name))
            return result

    async def get_pending_count(self) -> int:
        """Get number of entries pending acknowledgment."""
        async with self._redis_client.aget_client() as client:
            pending_info = await client.xpending(
                name=self._config.stream_name,
                groupname=self._config.consumer_group,
            )
            return pending_info.get("pending", 0) if pending_info else 0

    def _decode_fields(self, fields_raw: dict[bytes | str, bytes | str]) -> dict[str, str]:
        """Decode Redis bytes to strings."""
        result: dict[str, str] = {}
        for key, value in fields_raw.items():
            key_str = key.decode() if isinstance(key, bytes) else str(key)
            value_str = value.decode() if isinstance(value, bytes) else str(value)
            result[key_str] = value_str
        return result

    def _safe_int(self, value: str, default: int = 0) -> int:
        """Parse integer with fallback for corrupted data."""
        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid integer value, using default",
                value=value,
                default=default,
            )
            return default

    def _parse_entry(self, stream_id: str, fields: dict[str, str]) -> DeadLetterEntry:
        """Parse Redis fields into DeadLetterEntry.

        Raises
        ------
        ValueError
            If payload is corrupted (base64 decode fails).
        """
        metadata: dict[str, str] = {}
        for key, value in fields.items():
            if key.startswith("meta_"):
                metadata[key[5:]] = value

        entry_id = fields.get("id", "")

        # C4: Log timestamp fallback
        timestamp_str = fields.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.now(UTC)
        except ValueError:
            logger.warning(
                "Invalid timestamp format, using current time",
                raw_timestamp=timestamp_str,
                entry_id=entry_id,
            )
            timestamp = datetime.now(UTC)

        category_str = fields.get("category", FailureCategory.TRANSIENT.value)
        try:
            category = FailureCategory(category_str)
        except ValueError:
            category = FailureCategory.TRANSIENT

        # C3: Fail loudly on base64 decode failure (industry standard: data integrity)
        payload_b64 = fields.get("payload", "")
        try:
            payload = base64.b64decode(payload_b64) if payload_b64 else b""
        except Exception as e:
            logger.error(
                "Base64 decode failed - entry corrupted",
                entry_id=entry_id,
                stream_id=stream_id,
                error=str(e),
            )
            raise ValueError(f"Corrupted payload for entry {entry_id}: {e}") from e

        return DeadLetterEntry(
            id=entry_id,
            stream_id=stream_id,
            payload=payload,
            error_type=fields.get("error_type", ""),
            error_message=fields.get("error_message", ""),
            error_traceback=fields.get("error_traceback", ""),
            retry_count=self._safe_int(fields.get("retry_count", "0")),
            requeue_count=self._safe_int(fields.get("requeue_count", "0")),
            category=category,
            source_queue=fields.get("source_queue", ""),
            timestamp=timestamp,
            metadata=metadata,
        )
