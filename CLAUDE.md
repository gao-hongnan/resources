# Comprehensive System Design Patterns Guide 🏛️

**A Complete Blueprint for Distributed Systems Architecture Excellence**

---

## Table of Contents

1. [Introduction](#introduction)
2. [System Design Principles](#system-design-principles)
3. [Message Queue Patterns](#message-queue-patterns)
4. [Resilience Patterns](#resilience-patterns)
5. [Data Consistency Patterns](#data-consistency-patterns)
6. [Scalability Patterns](#scalability-patterns)
7. [Observability Patterns](#observability-patterns)
8. [API Gateway Patterns](#api-gateway-patterns)
9. [Service Communication Patterns](#service-communication-patterns)
10. [Pattern Selection Guide](#pattern-selection-guide)

---

## Introduction

System design patterns are proven architectural solutions for building scalable,
reliable, and maintainable distributed systems. These patterns address
challenges unique to distributed computing: network failures, partial failures,
data consistency, scalability, and operational complexity.

### Why System Design Patterns Matter

-   **Reliability**: Handle failures gracefully without cascading effects
-   **Scalability**: Support growth from thousands to millions of users
-   **Resilience**: Recover automatically from transient failures
-   **Performance**: Optimize latency, throughput, and resource utilization
-   **Maintainability**: Manage complexity in distributed architectures
-   **Observability**: Understand system behavior in production

### Pattern Categories

```
┌──────────────────────────────────────────────────────────────────┐
│                   System Design Patterns                         │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐             │
│  │   Message   │  │  Resilience │  │     Data     │             │
│  │    Queue    │  │  Patterns   │  │ Consistency  │             │
│  │  Patterns   │  │             │  │  Patterns    │             │
│  └─────────────┘  └─────────────┘  └──────────────┘             │
│         │                 │                 │                     │
│         ├─ Queue          ├─ Circuit Breaker├─ Saga              │
│         ├─ DLQ            ├─ Retry          ├─ Event Sourcing   │
│         ├─ Poison Pill    ├─ Timeout        ├─ CQRS             │
│         ├─ Priority Queue ├─ Bulkhead       ├─ Outbox           │
│         └─ Quarantine     ├─ Rate Limiter   ├─ 2PC              │
│                           └─ Backpressure   └─ CDC              │
│                                                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐            │
│  │ Scalability │  │Observability│  │     API      │            │
│  │  Patterns   │  │  Patterns   │  │   Patterns   │            │
│  └─────────────┘  └─────────────┘  └──────────────┘            │
│         │                 │                 │                    │
│         ├─ Load Balancing ├─ Health Check  ├─ API Gateway      │
│         ├─ Sharding       ├─ Metrics       ├─ BFF              │
│         ├─ Replication    ├─ Tracing       ├─ GraphQL          │
│         ├─ Caching        ├─ Logging       └─ Rate Limiting    │
│         └─ CDN            └─ Audit Log                          │
└──────────────────────────────────────────────────────────────────┘
```

### Distributed Systems Challenges

**CAP Theorem**: In a distributed system, you can only guarantee two of three
properties:

-   **C**onsistency: All nodes see the same data at the same time
-   **A**vailability: Every request receives a response (success or failure)
-   **P**artition tolerance: System continues operating despite network
    partitions

**Fallacies of Distributed Computing**:

1. The network is reliable
2. Latency is zero
3. Bandwidth is infinite
4. The network is secure
5. Topology doesn't change
6. There is one administrator
7. Transport cost is zero
8. The network is homogeneous

**These patterns help navigate these fundamental challenges.**

---

## System Design Principles

Before diving into patterns, understand the foundational principles of
distributed systems.

### 1. Design for Failure

**Principle**: Assume all components will eventually fail. Design systems that
gracefully degrade and recover automatically.

**Key Concepts**:

-   **Fail-fast**: Detect failures quickly and fail early
-   **Fail-safe**: Maintain safety even during failures
-   **Graceful degradation**: Reduce functionality rather than complete failure
-   **Automatic recovery**: Self-healing without manual intervention

**Implementation Strategies**:

```python
from __future__ import annotations
from typing import Protocol
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a system component"""

    component_name: str
    status: HealthStatus
    last_check: datetime
    error_message: str | None = None
    degraded_reason: str | None = None


class FailureAwareService:
    """
    Service that monitors its dependencies and degrades gracefully.

    Implements fail-fast detection and graceful degradation.
    """

    def __init__(self) -> None:
        self.component_health: dict[str, ComponentHealth] = {}
        self.circuit_breakers: dict[str, CircuitBreaker] = {}

    def check_health(self, component: str) -> ComponentHealth:
        """Check health of a component"""
        # Implementation would ping component
        health = ComponentHealth(
            component_name=component,
            status=HealthStatus.HEALTHY,
            last_check=datetime.now(),
        )
        self.component_health[component] = health
        return health

    def is_system_healthy(self) -> bool:
        """Check if system can operate normally"""
        unhealthy_critical = [
            h for h in self.component_health.values()
            if h.status == HealthStatus.UNHEALTHY
        ]
        return len(unhealthy_critical) == 0

    def can_serve_request(self) -> tuple[bool, HealthStatus]:
        """
        Determine if system can serve requests.

        Returns: (can_serve, current_status)
        """
        if self.is_system_healthy():
            return True, HealthStatus.HEALTHY

        # Check for degraded mode
        degraded = [
            h for h in self.component_health.values()
            if h.status == HealthStatus.DEGRADED
        ]

        if degraded:
            # Can serve with reduced functionality
            return True, HealthStatus.DEGRADED

        # System is unhealthy
        return False, HealthStatus.UNHEALTHY
```

---

### 2. Idempotency

**Principle**: Operations should produce the same result whether executed once
or multiple times. Essential for retry logic and fault tolerance.

**Key Concepts**:

-   **Idempotent operations**: Safe to retry without side effects
-   **Idempotency keys**: Unique identifiers to detect duplicates
-   **Natural idempotency**: Operations inherently idempotent (GET, PUT, DELETE)
-   **Implemented idempotency**: Added to non-idempotent operations (POST)

**Implementation**:

```python
from __future__ import annotations
from typing import Protocol
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json


@dataclass
class IdempotencyKey:
    """Unique key to identify duplicate requests"""

    key: str
    created_at: datetime
    expires_at: datetime
    result: dict | None = None


class IdempotencyStore(Protocol):
    """Storage interface for idempotency keys"""

    def get(self, key: str) -> IdempotencyKey | None: ...

    def set(
        self,
        key: str,
        result: dict,
        ttl: timedelta = timedelta(hours=24),
    ) -> None: ...

    def exists(self, key: str) -> bool: ...


class IdempotentPaymentProcessor:
    """
    Payment processor with idempotency guarantees.

    Ensures duplicate payment requests are not processed twice.
    """

    def __init__(self, store: IdempotencyStore) -> None:
        self.store = store

    def generate_idempotency_key(
        self,
        user_id: str,
        amount: float,
        timestamp: datetime,
    ) -> str:
        """
        Generate deterministic idempotency key.

        Same input always produces same key.
        """
        data = f"{user_id}:{amount}:{timestamp.isoformat()}"
        return hashlib.sha256(data.encode()).hexdigest()

    def process_payment(
        self,
        idempotency_key: str,
        user_id: str,
        amount: float,
    ) -> dict:
        """
        Process payment with idempotency guarantee.

        If same idempotency_key seen before, return cached result.
        """

        # Check if already processed
        if self.store.exists(idempotency_key):
            cached = self.store.get(idempotency_key)
            if cached and cached.result:
                print(f"Payment already processed: {idempotency_key}")
                return cached.result

        # Process payment (only once)
        result = self._execute_payment(user_id, amount)

        # Cache result
        self.store.set(idempotency_key, result, ttl=timedelta(hours=24))

        return result

    def _execute_payment(self, user_id: str, amount: float) -> dict:
        """Actual payment processing logic"""
        # Call payment gateway
        return {
            "transaction_id": f"tx_{user_id}_{amount}",
            "status": "success",
            "amount": amount,
            "user_id": user_id,
        }


# Usage Example
class RedisIdempotencyStore:
    """Redis-backed idempotency store"""

    def __init__(self) -> None:
        self._cache: dict[str, IdempotencyKey] = {}

    def get(self, key: str) -> IdempotencyKey | None:
        return self._cache.get(key)

    def set(
        self,
        key: str,
        result: dict,
        ttl: timedelta = timedelta(hours=24),
    ) -> None:
        self._cache[key] = IdempotencyKey(
            key=key,
            created_at=datetime.now(),
            expires_at=datetime.now() + ttl,
            result=result,
        )

    def exists(self, key: str) -> bool:
        return key in self._cache


# Client code
store = RedisIdempotencyStore()
processor = IdempotentPaymentProcessor(store)

# Generate idempotency key
timestamp = datetime.now()
idem_key = processor.generate_idempotency_key("user123", 99.99, timestamp)

# First call - processes payment
result1 = processor.process_payment(idem_key, "user123", 99.99)
print(f"First call: {result1}")

# Second call with same key - returns cached result
result2 = processor.process_payment(idem_key, "user123", 99.99)
print(f"Second call (cached): {result2}")

assert result1 == result2  # Same result guaranteed
```

**Real-World Examples**:

-   **Stripe API**: Uses `Idempotency-Key` header for payment idempotency
-   **AWS APIs**: Many operations naturally idempotent (PUT, DELETE)
-   **Kafka**: Exactly-once semantics with idempotent producers
-   **Database**: UPSERT operations are idempotent

---

### 3. Eventual Consistency

**Principle**: In distributed systems, strong consistency is expensive. Accept
that data may be temporarily inconsistent but will eventually converge to a
consistent state.

**Key Concepts**:

-   **Strong consistency**: All reads see the most recent write (expensive in
    distributed systems)
-   **Eventual consistency**: Reads may see stale data, but all nodes eventually
    converge
-   **Causal consistency**: Related operations observed in correct order
-   **Read-your-writes**: User always sees their own updates

**Trade-offs**:

```
┌─────────────────────────────────────────────────────────┐
│              Consistency Spectrum                        │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  Strong Consistency                 Eventual Consistency│
│         │                                     │          │
│         ├─ Linearizability                   ├─ BASE    │
│         ├─ Serializability                   ├─ Causal  │
│         └─ Sequential                        └─ Eventual│
│                                                           │
│  High Latency ◄───────────────────────────► Low Latency │
│  Low Availability ◄────────────────────► High Availability│
│  Simple Reasoning ◄─────────────────► Complex Reasoning │
└─────────────────────────────────────────────────────────┘
```

**Implementation**:

```python
from __future__ import annotations
from typing import Protocol
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio


@dataclass
class Event:
    """Domain event for event-driven architecture"""

    event_id: str
    event_type: str
    aggregate_id: str
    data: dict
    timestamp: datetime
    version: int


class EventStore(Protocol):
    """Interface for event storage"""

    async def append(self, event: Event) -> None: ...

    async def get_events(self, aggregate_id: str) -> list[Event]: ...


class ReadModel(Protocol):
    """Read-optimized view of data (CQRS)"""

    async def update(self, event: Event) -> None: ...

    async def get(self, id: str) -> dict | None: ...


class EventuallyConsistentService:
    """
    Service implementing eventual consistency with CQRS.

    Writes go to event store (source of truth).
    Reads come from denormalized read models (eventually consistent).
    """

    def __init__(
        self,
        event_store: EventStore,
        read_models: list[ReadModel],
    ) -> None:
        self.event_store = event_store
        self.read_models = read_models
        self.event_queue: asyncio.Queue[Event] = asyncio.Queue()

    async def handle_command(
        self,
        aggregate_id: str,
        command: dict,
    ) -> Event:
        """
        Handle write command (strong consistency).

        Writes to event store and returns immediately.
        Read models updated asynchronously (eventual consistency).
        """

        # Create event
        event = Event(
            event_id=f"evt_{datetime.now().timestamp()}",
            event_type=command["type"],
            aggregate_id=aggregate_id,
            data=command["data"],
            timestamp=datetime.now(),
            version=1,
        )

        # Write to event store (synchronous, consistent)
        await self.event_store.append(event)

        # Queue for async read model updates
        await self.event_queue.put(event)

        return event

    async def process_events(self) -> None:
        """
        Background task to update read models.

        Updates are asynchronous, eventual consistency.
        """
        while True:
            event = await self.event_queue.get()

            # Update all read models
            update_tasks = [
                model.update(event) for model in self.read_models
            ]

            try:
                await asyncio.gather(*update_tasks)
                print(f"Read models updated for event: {event.event_id}")
            except Exception as e:
                # Log and retry
                print(f"Failed to update read models: {e}")
                # Could implement retry logic here

            self.event_queue.task_done()

    async def query(self, read_model: ReadModel, id: str) -> dict | None:
        """
        Query read model (eventual consistency).

        May return stale data if read model not yet updated.
        """
        return await read_model.get(id)


# Example: User Profile Service
class UserProfileReadModel:
    """Denormalized user profile for fast reads"""

    def __init__(self) -> None:
        self._profiles: dict[str, dict] = {}

    async def update(self, event: Event) -> None:
        """Update read model based on event"""

        if event.event_type == "UserCreated":
            self._profiles[event.aggregate_id] = {
                "user_id": event.aggregate_id,
                "name": event.data["name"],
                "email": event.data["email"],
                "created_at": event.timestamp,
            }

        elif event.event_type == "UserUpdated":
            if event.aggregate_id in self._profiles:
                self._profiles[event.aggregate_id].update(event.data)

        elif event.event_type == "UserDeleted":
            self._profiles.pop(event.aggregate_id, None)

    async def get(self, user_id: str) -> dict | None:
        """Fast read from denormalized view"""
        return self._profiles.get(user_id)


# Usage demonstrates eventual consistency
async def demonstrate_eventual_consistency() -> None:
    """Show eventual consistency in action"""

    # Setup
    event_store = InMemoryEventStore()
    read_model = UserProfileReadModel()
    service = EventuallyConsistentService(event_store, [read_model])

    # Start background processor
    asyncio.create_task(service.process_events())

    # Write operation (immediately consistent)
    event = await service.handle_command(
        aggregate_id="user123",
        command={
            "type": "UserCreated",
            "data": {"name": "Alice", "email": "alice@example.com"},
        },
    )
    print(f"Write completed: {event.event_id}")

    # Read immediately after write (may be stale)
    profile = await service.query(read_model, "user123")
    if profile is None:
        print("Read model not yet updated (eventual consistency)")

    # Wait for read model to catch up
    await asyncio.sleep(0.1)

    # Read again (now consistent)
    profile = await service.query(read_model, "user123")
    print(f"Read model now consistent: {profile}")


class InMemoryEventStore:
    """Simple in-memory event store for demonstration"""

    def __init__(self) -> None:
        self._events: dict[str, list[Event]] = {}

    async def append(self, event: Event) -> None:
        if event.aggregate_id not in self._events:
            self._events[event.aggregate_id] = []
        self._events[event.aggregate_id].append(event)

    async def get_events(self, aggregate_id: str) -> list[Event]:
        return self._events.get(aggregate_id, [])
```

**When to Use Eventual Consistency**:

-   ✅ Social media feeds (Facebook, Twitter)
-   ✅ E-commerce product catalogs
-   ✅ Content delivery networks
-   ✅ DNS systems
-   ✅ Analytics and reporting
-   ❌ Financial transactions (need strong consistency)
-   ❌ Inventory management (avoid overselling)
-   ❌ Booking systems (avoid double booking)

---

### 4. Loose Coupling

**Principle**: Minimize dependencies between services. Services should interact
through well-defined contracts and be deployable independently.

**Key Concepts**:

-   **Service independence**: Each service owns its data and logic
-   **Contract-based interaction**: Well-defined APIs/events
-   **Temporal decoupling**: Services don't need to be available simultaneously
-   **Location transparency**: Services can move without affecting clients

**Implementation Approaches**:

```python
from __future__ import annotations
from typing import Protocol
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


# Tight Coupling (Anti-pattern)
class OrderService:
    """Tightly coupled - directly depends on concrete implementations"""

    def __init__(self) -> None:
        # Direct dependencies on concrete classes
        self.inventory = InventoryService()
        self.payment = PaymentService()
        self.shipping = ShippingService()
        self.notification = EmailService()

    def create_order(self, order_data: dict) -> str:
        """Tightly coupled - hard to test and modify"""

        # Direct method calls create tight coupling
        self.inventory.reserve_items(order_data["items"])
        self.payment.charge_customer(order_data["payment"])
        self.shipping.schedule_shipment(order_data["address"])
        self.notification.send_confirmation(order_data["email"])

        return "order_123"


# Loose Coupling (Best Practice)

# Define contracts (interfaces)
class InventoryManager(Protocol):
    """Contract for inventory management"""

    def reserve_items(self, items: list[dict]) -> bool: ...


class PaymentProcessor(Protocol):
    """Contract for payment processing"""

    def process_payment(self, payment_info: dict) -> bool: ...


class ShippingProvider(Protocol):
    """Contract for shipping"""

    def create_shipment(self, address: dict, items: list[dict]) -> str: ...


class NotificationSender(Protocol):
    """Contract for notifications"""

    def send(self, recipient: str, message: str, channel: str) -> None: ...


# Event-driven approach for even looser coupling
@dataclass
class DomainEvent:
    """Base class for domain events"""

    event_id: str
    event_type: str
    timestamp: datetime
    data: dict


class EventBus(Protocol):
    """Event bus for publish-subscribe"""

    def publish(self, event: DomainEvent) -> None: ...

    def subscribe(
        self,
        event_type: str,
        handler: callable,
    ) -> None: ...


class LooselyC oupledOrderService:
    """
    Loosely coupled - depends on abstractions, not concrete implementations.

    Uses dependency injection and event-driven architecture.
    """

    def __init__(
        self,
        inventory: InventoryManager,
        payment: PaymentProcessor,
        event_bus: EventBus,
    ) -> None:
        # Depend on abstractions (protocols)
        self.inventory = inventory
        self.payment = payment
        self.event_bus = event_bus

    def create_order(self, order_data: dict) -> str:
        """
        Loosely coupled - other services notified via events.

        Shipping and notification services don't need to be available
        when order is created (temporal decoupling).
        """

        # Core order processing
        order_id = f"order_{datetime.now().timestamp()}"

        # Synchronous operations with injected dependencies
        items_reserved = self.inventory.reserve_items(order_data["items"])
        payment_successful = self.payment.process_payment(
            order_data["payment"]
        )

        if not items_reserved or not payment_successful:
            # Rollback logic
            return ""

        # Publish event for other services (async, decoupled)
        self.event_bus.publish(
            DomainEvent(
                event_id=f"evt_{order_id}",
                event_type="OrderCreated",
                timestamp=datetime.now(),
                data={
                    "order_id": order_id,
                    "items": order_data["items"],
                    "address": order_data["address"],
                    "email": order_data["email"],
                },
            )
        )

        return order_id


# Event handlers (separate services)
class ShippingService:
    """Shipping service listens to OrderCreated events"""

    def __init__(self, event_bus: EventBus) -> None:
        # Subscribe to events
        event_bus.subscribe("OrderCreated", self.handle_order_created)

    def handle_order_created(self, event: DomainEvent) -> None:
        """Process shipment asynchronously"""
        print(f"Scheduling shipment for order: {event.data['order_id']}")
        # Create shipment


class NotificationService:
    """Notification service listens to OrderCreated events"""

    def __init__(self, event_bus: EventBus) -> None:
        event_bus.subscribe("OrderCreated", self.handle_order_created)

    def handle_order_created(self, event: DomainEvent) -> None:
        """Send confirmation asynchronously"""
        print(f"Sending confirmation for order: {event.data['order_id']}")
        # Send email
```

**Benefits of Loose Coupling**:

-   ✅ **Independent deployment**: Services can be updated separately
-   ✅ **Easy testing**: Mock dependencies easily
-   ✅ **Technology flexibility**: Swap implementations without changing
    consumers
-   ✅ **Fault isolation**: Failures don't cascade
-   ✅ **Team autonomy**: Teams can work independently

---

## Message Queue Patterns

Message queues are fundamental to distributed systems, enabling asynchronous
communication, load leveling, and fault tolerance.

### 1. Queue Pattern

**Category**: Message Queue Pattern

**Intent**: Decouple producers from consumers by buffering messages in a queue.
Enable asynchronous processing and load leveling.

**Problem**:

-   Producer and consumer operate at different speeds
-   Need to handle traffic spikes without overwhelming consumers
-   Want to process tasks asynchronously
-   Need to decouple services for independent scaling

**Solution**:

-   Introduce a message queue between producer and consumer
-   Producers enqueue messages
-   Consumers dequeue and process messages at their own pace
-   Queue acts as buffer and decoupling layer

**When to Use**:

-   Asynchronous task processing (email sending, report generation)
-   Load leveling during traffic spikes
-   Decoupling microservices
-   Background job processing
-   Event-driven architectures

**Architecture**:

```
┌───────────┐         ┌───────────┐         ┌───────────┐
│ Producer  │────────▶│   Queue   │────────▶│ Consumer  │
│ (Fast)    │ enqueue │  (Buffer) │ dequeue │  (Slow)   │
└───────────┘         └───────────┘         └───────────┘
                           │
                      ┌────┴────┐
                      │ Message │
                      │  Store  │
                      └─────────┘
```

**Python Implementation (Redis-based)**:

```python
from __future__ import annotations
from typing import Protocol, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import json
import asyncio


class MessagePriority(Enum):
    """Message priority levels"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class QueueMessage:
    """Message structure for queue"""

    message_id: str
    payload: dict[str, Any]
    priority: MessagePriority
    created_at: datetime
    attempts: int = 0
    max_attempts: int = 3


class MessageQueue(Protocol):
    """Abstract message queue interface"""

    async def enqueue(
        self,
        message: QueueMessage,
        queue_name: str = "default",
    ) -> None: ...

    async def dequeue(
        self,
        queue_name: str = "default",
        timeout: int = 0,
    ) -> QueueMessage | None: ...

    async def ack(
        self,
        message_id: str,
        queue_name: str = "default",
    ) -> None: ...

    async def nack(
        self,
        message_id: str,
        queue_name: str = "default",
        requeue: bool = True,
    ) -> None: ...


class RedisMessageQueue:
    """
    Redis-backed message queue implementation.

    Uses Redis lists for FIFO queue semantics.
    Supports message acknowledgment and redelivery.
    """

    def __init__(self) -> None:
        # Simulated Redis connection
        self._queues: dict[str, list[str]] = {}
        self._processing: dict[str, dict[str, QueueMessage]] = {}
        self._acked: set[str] = set()

    async def enqueue(
        self,
        message: QueueMessage,
        queue_name: str = "default",
    ) -> None:
        """Add message to queue"""

        if queue_name not in self._queues:
            self._queues[queue_name] = []

        # Serialize message
        message_json = json.dumps(asdict(message), default=str)

        # Add to queue (Redis RPUSH)
        self._queues[queue_name].append(message_json)

        print(
            f"✓ Enqueued message {message.message_id} "
            f"to {queue_name} (priority: {message.priority.name})"
        )

    async def dequeue(
        self,
        queue_name: str = "default",
        timeout: int = 0,
    ) -> QueueMessage | None:
        """
        Retrieve message from queue.

        Moves message to processing state until acked/nacked.
        """

        if queue_name not in self._queues:
            return None

        if not self._queues[queue_name]:
            if timeout > 0:
                # Simulate blocking wait
                await asyncio.sleep(timeout)
            return None

        # Dequeue message (Redis LPOP)
        message_json = self._queues[queue_name].pop(0)
        message_dict = json.loads(message_json)

        # Reconstruct message
        message = QueueMessage(
            message_id=message_dict["message_id"],
            payload=message_dict["payload"],
            priority=MessagePriority[message_dict["priority"]],
            created_at=datetime.fromisoformat(message_dict["created_at"]),
            attempts=message_dict["attempts"],
            max_attempts=message_dict["max_attempts"],
        )

        # Move to processing state
        if queue_name not in self._processing:
            self._processing[queue_name] = {}
        self._processing[queue_name][message.message_id] = message

        print(f"← Dequeued message {message.message_id} from {queue_name}")

        return message

    async def ack(
        self,
        message_id: str,
        queue_name: str = "default",
    ) -> None:
        """
        Acknowledge successful processing.

        Removes message from processing state.
        """

        if queue_name in self._processing:
            self._processing[queue_name].pop(message_id, None)
            self._acked.add(message_id)
            print(f"✓ Acknowledged message {message_id}")

    async def nack(
        self,
        message_id: str,
        queue_name: str = "default",
        requeue: bool = True,
    ) -> None:
        """
        Negative acknowledge (processing failed).

        Optionally requeue message for retry.
        """

        if queue_name not in self._processing:
            return

        message = self._processing[queue_name].get(message_id)
        if not message:
            return

        # Remove from processing
        self._processing[queue_name].pop(message_id)

        if requeue and message.attempts < message.max_attempts:
            # Increment attempts and requeue
            message.attempts += 1
            await self.enqueue(message, queue_name)
            print(
                f"⟲ Requeued message {message_id} "
                f"(attempt {message.attempts}/{message.max_attempts})"
            )
        else:
            print(f"✗ Message {message_id} exceeded max attempts")
            # Would send to DLQ here (covered in next pattern)


# Producer
class EmailProducer:
    """Producer that enqueues email sending tasks"""

    def __init__(self, queue: MessageQueue) -> None:
        self.queue = queue

    async def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> None:
        """Enqueue email sending task"""

        message = QueueMessage(
            message_id=f"email_{datetime.now().timestamp()}",
            payload={
                "recipient": recipient,
                "subject": subject,
                "body": body,
            },
            priority=priority,
            created_at=datetime.now(),
        )

        await self.queue.enqueue(message, queue_name="emails")


# Consumer
class EmailConsumer:
    """Consumer that processes email sending tasks"""

    def __init__(self, queue: MessageQueue) -> None:
        self.queue = queue
        self.running = False

    async def start(self) -> None:
        """Start consuming messages"""

        self.running = True
        print("Email consumer started...")

        while self.running:
            # Dequeue message
            message = await self.queue.dequeue(
                queue_name="emails",
                timeout=1,
            )

            if message:
                try:
                    # Process message
                    await self._process_email(message)

                    # Acknowledge success
                    await self.queue.ack(message.message_id, "emails")

                except Exception as e:
                    print(f"Error processing {message.message_id}: {e}")

                    # Negative acknowledge (will retry)
                    await self.queue.nack(
                        message.message_id,
                        "emails",
                        requeue=True,
                    )

            await asyncio.sleep(0.1)

    async def stop(self) -> None:
        """Stop consuming messages"""
        self.running = False

    async def _process_email(self, message: QueueMessage) -> None:
        """Process email sending"""

        recipient = message.payload["recipient"]
        subject = message.payload["subject"]

        print(f"📧 Sending email to {recipient}: {subject}")

        # Simulate email sending
        await asyncio.sleep(0.5)

        # Could raise exception for failed sends


# Usage demonstration
async def demonstrate_queue_pattern() -> None:
    """Demonstrate queue pattern with producer/consumer"""

    queue = RedisMessageQueue()

    # Create producer and consumer
    producer = EmailProducer(queue)
    consumer = EmailConsumer(queue)

    # Start consumer in background
    consumer_task = asyncio.create_task(consumer.start())

    # Produce messages
    await producer.send_email(
        "user1@example.com",
        "Welcome!",
        "Welcome to our service",
        MessagePriority.HIGH,
    )

    await producer.send_email(
        "user2@example.com",
        "Newsletter",
        "Monthly newsletter",
        MessagePriority.LOW,
    )

    await producer.send_email(
        "user3@example.com",
        "Password Reset",
        "Reset your password",
        MessagePriority.CRITICAL,
    )

    # Let consumer process
    await asyncio.sleep(2)

    # Stop consumer
    await consumer.stop()
    await consumer_task


# Run demonstration
# asyncio.run(demonstrate_queue_pattern())
```

**Real-World Implementations**:

-   **Amazon SQS**: Fully managed message queue service
-   **RabbitMQ**: Open-source message broker
-   **Apache Kafka**: Distributed streaming platform
-   **Redis Streams**: Redis-based message queue
-   **Google Cloud Pub/Sub**: Managed pub/sub messaging
-   **Azure Service Bus**: Enterprise message broker

**Key Characteristics**:

| Characteristic         | Description                         | Example                        |
| ---------------------- | ----------------------------------- | ------------------------------ |
| **Durability**         | Messages persisted to disk          | Redis AOF, SQS                 |
| **At-least-once**      | Message delivered 1+ times          | SQS standard                   |
| **Exactly-once**       | Message delivered exactly once      | Kafka with idempotent producer |
| **Ordering**           | FIFO guarantees                     | SQS FIFO queues                |
| **Visibility timeout** | Message invisible during processing | SQS visibility timeout         |
| **Message TTL**        | Messages expire after timeout       | RabbitMQ TTL                   |

**Advantages**:

-   ✅ Asynchronous processing
-   ✅ Load leveling during traffic spikes
-   ✅ Fault tolerance through buffering
-   ✅ Independent scaling of producers/consumers
-   ✅ Loose coupling between services

**Disadvantages**:

-   ❌ Added latency (not suitable for synchronous operations)
-   ❌ Eventual consistency
-   ❌ Complexity in error handling
-   ❌ Message ordering challenges in distributed setups

---

### 2. Dead Letter Queue (DLQ) Pattern

**Category**: Message Queue Pattern

**Intent**: Isolate messages that cannot be processed successfully after
multiple attempts, preventing them from blocking the main queue while preserving
them for analysis and manual intervention.

**Problem**:

-   Messages fail processing repeatedly (poison messages)
-   Failed messages block or slow down queue processing
-   Need to preserve failed messages for debugging
-   Want to prevent infinite retry loops
-   Need visibility into processing failures

**Solution**:

-   Create a separate Dead Letter Queue (DLQ)
-   After N failed processing attempts, move message to DLQ
-   Monitor DLQ for operational alerts
-   Implement manual or automated remediation workflows
-   Analyze failure patterns to improve system robustness

**When to Use**:

-   Message processing can fail permanently (bad data, external service down)
-   Need to preserve failed messages for investigation
-   Want to prevent poison messages from blocking queue
-   Require visibility into systemic failures
-   Need compliance/audit trail of all messages

**Architecture**:

```
┌──────────┐
│ Producer │
└────┬─────┘
     │ enqueue
     ▼
┌─────────────────┐     retry     ┌──────────────┐
│  Primary Queue  │───────────────▶│   Consumer   │
└─────────────────┘   (3 attempts) └──────┬───────┘
     │                                     │
     │                              ┌──────┴───────┐
     │ after max attempts           │   Success?   │
     │                              └──────┬───────┘
     │                                     │ failure
     ▼                                     │
┌─────────────────┐◄───────────────────────┘
│ Dead Letter     │
│ Queue (DLQ)     │
└─────────────────┘
     │
     ▼
┌─────────────────┐
│  DLQ Monitor    │
│  - Alerts       │
│  - Analysis     │
│  - Replay       │
└─────────────────┘
```

**Python Implementation**:

```python
from __future__ import annotations
from typing import Protocol
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import json
import asyncio


class FailureReason(Enum):
    """Categorization of failure reasons"""

    INVALID_DATA = "invalid_data"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    TIMEOUT = "timeout"
    PROCESSING_ERROR = "processing_error"
    UNKNOWN = "unknown"


@dataclass
class DLQMessage:
    """
    Message in Dead Letter Queue with failure metadata.

    Includes original message plus diagnostic information.
    """

    original_message_id: str
    payload: dict
    failure_reason: FailureReason
    failure_details: str
    attempts: int
    first_attempt_at: datetime
    last_attempt_at: datetime
    moved_to_dlq_at: datetime
    original_queue: str
    error_stack_trace: str | None = None


class DeadLetterQueueManager:
    """
    Manages Dead Letter Queue operations.

    Handles moving failed messages to DLQ, monitoring, and replay.
    """

    def __init__(
        self,
        primary_queue: MessageQueue,
        dlq_queue: MessageQueue,
        max_attempts: int = 3,
    ) -> None:
        self.primary_queue = primary_queue
        self.dlq_queue = dlq_queue
        self.max_attempts = max_attempts
        self.dlq_stats: dict[FailureReason, int] = {
            reason: 0 for reason in FailureReason
        }

    async def process_with_dlq(
        self,
        message: QueueMessage,
        processor: callable,
        queue_name: str = "default",
    ) -> bool:
        """
        Process message with DLQ handling.

        Returns: True if processed successfully, False if moved to DLQ
        """

        try:
            # Attempt processing
            await processor(message)

            # Success - acknowledge message
            await self.primary_queue.ack(message.message_id, queue_name)
            return True

        except Exception as e:
            # Processing failed
            message.attempts += 1

            if message.attempts >= self.max_attempts:
                # Max attempts exceeded - move to DLQ
                await self._move_to_dlq(
                    message=message,
                    error=e,
                    queue_name=queue_name,
                )
                return False

            else:
                # Requeue for retry
                await self.primary_queue.nack(
                    message.message_id,
                    queue_name,
                    requeue=True,
                )
                print(
                    f"⟲ Retry {message.attempts}/{self.max_attempts}: "
                    f"{message.message_id}"
                )
                return False

    async def _move_to_dlq(
        self,
        message: QueueMessage,
        error: Exception,
        queue_name: str,
    ) -> None:
        """Move failed message to DLQ with metadata"""

        # Classify failure
        failure_reason = self._classify_failure(error)

        # Create DLQ message with rich metadata
        dlq_message = DLQMessage(
            original_message_id=message.message_id,
            payload=message.payload,
            failure_reason=failure_reason,
            failure_details=str(error),
            attempts=message.attempts,
            first_attempt_at=message.created_at,
            last_attempt_at=datetime.now(),
            moved_to_dlq_at=datetime.now(),
            original_queue=queue_name,
            error_stack_trace=self._get_stack_trace(error),
        )

        # Enqueue to DLQ
        dlq_queue_message = QueueMessage(
            message_id=f"dlq_{message.message_id}",
            payload=asdict(dlq_message),
            priority=message.priority,
            created_at=datetime.now(),
        )

        await self.dlq_queue.enqueue(dlq_queue_message, queue_name="dlq")

        # Remove from primary queue
        await self.primary_queue.ack(message.message_id, queue_name)

        # Update statistics
        self.dlq_stats[failure_reason] += 1

        print(
            f"☠️  Moved to DLQ: {message.message_id} "
            f"(reason: {failure_reason.value})"
        )

    def _classify_failure(self, error: Exception) -> FailureReason:
        """Classify failure reason from exception"""

        error_type = type(error).__name__

        if "Validation" in error_type or "Invalid" in error_type:
            return FailureReason.INVALID_DATA
        elif "Timeout" in error_type:
            return FailureReason.TIMEOUT
        elif "Connection" in error_type or "HTTP" in error_type:
            return FailureReason.EXTERNAL_SERVICE_ERROR
        else:
            return FailureReason.PROCESSING_ERROR

    def _get_stack_trace(self, error: Exception) -> str:
        """Extract stack trace from exception"""
        import traceback

        return "".join(traceback.format_exception(type(error), error, error.__traceback__))

    async def monitor_dlq(self) -> dict:
        """
        Monitor DLQ health metrics.

        Returns metrics for alerting and dashboards.
        """

        # In production, would query queue length from Redis/SQS/etc
        return {
            "dlq_depth": len(self.dlq_queue._queues.get("dlq", [])),
            "failure_breakdown": dict(self.dlq_stats),
            "alert_threshold_exceeded": self.dlq_stats[FailureReason.EXTERNAL_SERVICE_ERROR] > 10,
        }

    async def replay_from_dlq(
        self,
        message_id: str,
        processor: callable,
    ) -> bool:
        """
        Replay a message from DLQ after issue is fixed.

        Returns: True if replay successful
        """

        # Retrieve from DLQ
        dlq_message = await self.dlq_queue.dequeue("dlq")

        if not dlq_message:
            return False

        # Reconstruct original message
        original_payload = dlq_message.payload["payload"]
        original_message = QueueMessage(
            message_id=dlq_message.payload["original_message_id"],
            payload=original_payload,
            priority=MessagePriority.HIGH,  # Prioritize replays
            created_at=datetime.now(),
            attempts=0,  # Reset attempts
        )

        try:
            # Attempt reprocessing
            await processor(original_message)

            # Success - ack DLQ message
            await self.dlq_queue.ack(dlq_message.message_id, "dlq")

            print(f"✓ Successfully replayed: {message_id}")
            return True

        except Exception as e:
            # Still failing - nack and return to DLQ
            await self.dlq_queue.nack(dlq_message.message_id, "dlq")

            print(f"✗ Replay failed: {message_id} - {e}")
            return False


# Example: Order Processing with DLQ
class OrderProcessor:
    """Order processor that may fail"""

    async def process_order(self, message: QueueMessage) -> None:
        """Process order - may raise exceptions"""

        order_data = message.payload

        # Validation errors -> permanent failure
        if "customer_id" not in order_data:
            raise ValueError("Missing customer_id")

        # External service errors -> transient failure
        if order_data.get("customer_id") == "bad_customer":
            raise ConnectionError("Customer service unavailable")

        # Successful processing
        print(f"✓ Processed order: {order_data.get('order_id')}")


# Usage Demonstration
async def demonstrate_dlq_pattern() -> None:
    """Demonstrate DLQ pattern with various failure scenarios"""

    # Setup
    primary_queue = RedisMessageQueue()
    dlq_queue = RedisMessageQueue()
    dlq_manager = DeadLetterQueueManager(
        primary_queue=primary_queue,
        dlq_queue=dlq_queue,
        max_attempts=3,
    )

    processor = OrderProcessor()

    print("=== Dead Letter Queue Pattern Demo ===\n")

    # Scenario 1: Successful processing
    print("Scenario 1: Valid order (should succeed)")
    valid_order = QueueMessage(
        message_id="order_001",
        payload={"order_id": "001", "customer_id": "cust_123"},
        priority=MessagePriority.NORMAL,
        created_at=datetime.now(),
    )
    await primary_queue.enqueue(valid_order, "orders")

    message = await primary_queue.dequeue("orders")
    if message:
        await dlq_manager.process_with_dlq(
            message,
            processor.process_order,
            "orders",
        )

    # Scenario 2: Transient failure (external service down) - will retry
    print("\nScenario 2: External service error (will retry)")
    transient_order = QueueMessage(
        message_id="order_002",
        payload={"order_id": "002", "customer_id": "bad_customer"},
        priority=MessagePriority.NORMAL,
        created_at=datetime.now(),
    )
    await primary_queue.enqueue(transient_order, "orders")

    # Try processing 3 times (will fail all attempts)
    for attempt in range(3):
        message = await primary_queue.dequeue("orders")
        if message:
            await dlq_manager.process_with_dlq(
                message,
                processor.process_order,
                "orders",
            )

    # Scenario 3: Permanent failure (invalid data) - immediate DLQ
    print("\nScenario 3: Invalid data (permanent failure)")
    invalid_order = QueueMessage(
        message_id="order_003",
        payload={"order_id": "003"},  # Missing customer_id
        priority=MessagePriority.NORMAL,
        created_at=datetime.now(),
        max_attempts=1,  # Fail fast for validation errors
    )
    await primary_queue.enqueue(invalid_order, "orders")

    message = await primary_queue.dequeue("orders")
    if message:
        message.max_attempts = 1
        await dlq_manager.process_with_dlq(
            message,
            processor.process_order,
            "orders",
        )

    # Monitor DLQ
    print("\n=== DLQ Monitoring ===")
    metrics = await dlq_manager.monitor_dlq()
    print(f"DLQ Depth: {metrics['dlq_depth']}")
    print(f"Failure Breakdown: {metrics['failure_breakdown']}")
    print(f"Alert Needed: {metrics['alert_threshold_exceeded']}")


# asyncio.run(demonstrate_dlq_pattern())
```

**Real-World DLQ Implementations**:

| Service               | DLQ Feature                      | Max Attempts      | Retention          |
| --------------------- | -------------------------------- | ----------------- | ------------------ |
| **Amazon SQS**        | Built-in DLQ with redrive policy | Configurable      | Up to 14 days      |
| **RabbitMQ**          | Dead letter exchanges            | Per-queue policy  | Configurable       |
| **Azure Service Bus** | Dead-letter sub-queue            | Configurable      | Same as main queue |
| **Google Pub/Sub**    | Dead letter topic                | Configurable      | 7 days             |
| **Apache Kafka**      | Error topic pattern              | Application-level | Configurable       |
| **Redis Streams**     | Custom DLQ implementation        | Application-level | Manual management  |

**DLQ Best Practices**:

1. **Set Appropriate Max Attempts**:

    - Transient failures: 3-5 attempts with exponential backoff
    - Validation errors: 1 attempt (fail-fast)
    - External service timeouts: 3 attempts

2. **Include Rich Metadata**:

    ```python
    {
        "original_message_id": "msg_123",
        "failure_reason": "external_service_error",
        "error_details": "HTTP 503 Service Unavailable",
        "attempts": 3,
        "stack_trace": "...",
        "environment": "production",
        "service_version": "v1.2.3"
    }
    ```

3. **Monitor and Alert**:

    - Alert when DLQ depth exceeds threshold
    - Track failure reason distribution
    - Set up dashboards for DLQ trends
    - Page on-call engineer for critical failures

4. **Implement Replay Mechanism**:

    - Manual replay after fixing root cause
    - Automated replay with circuit breaker
    - Batch replay with rate limiting
    - Idempotency for safe replay

5. **Retention and Archival**:
    - DLQ retention > primary queue retention
    - Archive DLQ messages to S3/GCS for long-term storage
    - Compliance requirements for message preservation

**Advantages**:

-   ✅ Prevents poison messages from blocking queue
-   ✅ Preserves failed messages for debugging
-   ✅ Provides visibility into systemic issues
-   ✅ Enables post-mortem analysis
-   ✅ Supports compliance and audit requirements
-   ✅ Allows manual intervention and replay

**Disadvantages**:

-   ❌ Additional infrastructure complexity
-   ❌ Requires DLQ monitoring and management
-   ❌ Can accumulate messages if not actively managed
-   ❌ Replay logic adds complexity
-   ❌ Storage costs for retained messages

**Related Patterns**:

-   **Poison Pill**: Detect and handle poison messages proactively
-   **Quarantine**: Isolate suspicious messages before processing
-   **Retry Pattern**: Retry transient failures before DLQ
-   **Circuit Breaker**: Prevent cascading failures from external services

---

### 3. Poison Pill Pattern

**Category**: Message Queue Pattern

**Intent**: Detect and handle messages that consistently cause processing
failures, preventing them from consuming resources and affecting system
stability.

**Problem**:

-   Certain messages always fail processing (malformed data, logic bugs)
-   Poison messages waste CPU, memory, and processing time
-   Repeated failures can trigger alerts and cause operational noise
-   Need to identify and isolate problematic messages early
-   Want to prevent resource exhaustion from poison messages

**Solution**:

-   Implement poison pill detection logic
-   Identify messages with specific characteristics that indicate poison
-   Fast-fail poison messages without full processing
-   Route poison messages to quarantine or specialized handling
-   Implement safeguards and validation at queue boundaries

**When to Use**:

-   Processing certain types of malformed data
-   Protecting against bad actors or corrupted data
-   Expensive processing operations that should fail-fast
-   Need to prevent resource exhaustion
-   Want to reduce operational noise from expected failures

**Architecture**:

```
┌──────────┐
│ Producer │
└────┬─────┘
     │
     ▼
┌─────────────────┐
│  Input Queue    │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  Poison Pill Detector   │
│  - Schema validation    │
│  - Size limits          │
│  - Pattern matching     │
│  - Signature verification│
└────┬─────────────┬──────┘
     │ valid       │ poison
     │             │
     ▼             ▼
┌─────────┐   ┌──────────────┐
│Consumer │   │ Quarantine   │
│         │   │ Queue        │
└─────────┘   └──────────────┘
```

**Python Implementation**:

```python
from __future__ import annotations
from typing import Protocol, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json


class PoisonPillReason(Enum):
    """Reasons for identifying poison pills"""

    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    SIZE_LIMIT_EXCEEDED = "size_limit_exceeded"
    INVALID_FORMAT = "invalid_format"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    MISSING_REQUIRED_FIELDS = "missing_required_fields"
    BLACKLISTED_SOURCE = "blacklisted_source"


@dataclass
class PoisonPillDetectionResult:
    """Result of poison pill detection"""

    is_poison: bool
    reason: PoisonPillReason | None = None
    details: str | None = None


class PoisonPillDetector:
    """
    Detects poison pill messages before processing.

    Implements multiple detection strategies.
    """

    def __init__(
        self,
        max_message_size: int = 1024 * 1024,  # 1MB
        required_fields: set[str] | None = None,
        blacklisted_sources: set[str] | None = None,
    ) -> None:
        self.max_message_size = max_message_size
        self.required_fields = required_fields or set()
        self.blacklisted_sources = blacklisted_sources or set()

    def detect(self, message: QueueMessage) -> PoisonPillDetectionResult:
        """
        Detect if message is a poison pill.

        Runs multiple checks in order of expense (cheap checks first).
        """

        # Check 1: Size limit (very cheap)
        if self._exceeds_size_limit(message):
            return PoisonPillDetectionResult(
                is_poison=True,
                reason=PoisonPillReason.SIZE_LIMIT_EXCEEDED,
                details=f"Message size exceeds {self.max_message_size} bytes",
            )

        # Check 2: Required fields (cheap)
        if not self._has_required_fields(message):
            return PoisonPillDetectionResult(
                is_poison=True,
                reason=PoisonPillReason.MISSING_REQUIRED_FIELDS,
                details=f"Missing required fields: {self.required_fields}",
            )

        # Check 3: Blacklisted source (cheap)
        if self._is_blacklisted_source(message):
            return PoisonPillDetectionResult(
                is_poison=True,
                reason=PoisonPillReason.BLACKLISTED_SOURCE,
                details="Message from blacklisted source",
            )

        # Check 4: Schema validation (more expensive)
        if not self._validate_schema(message):
            return PoisonPillDetectionResult(
                is_poison=True,
                reason=PoisonPillReason.SCHEMA_VALIDATION_FAILED,
                details="Message does not conform to expected schema",
            )

        # Check 5: Suspicious patterns (most expensive)
        if self._has_suspicious_patterns(message):
            return PoisonPillDetectionResult(
                is_poison=True,
                reason=PoisonPillReason.SUSPICIOUS_PATTERN,
                details="Message contains suspicious patterns",
            )

        # Passed all checks
        return PoisonPillDetectionResult(is_poison=False)

    def _exceeds_size_limit(self, message: QueueMessage) -> bool:
        """Check if message exceeds size limit"""
        message_bytes = json.dumps(message.payload).encode("utf-8")
        return len(message_bytes) > self.max_message_size

    def _has_required_fields(self, message: QueueMessage) -> bool:
        """Check if all required fields present"""
        if not self.required_fields:
            return True
        return self.required_fields.issubset(message.payload.keys())

    def _is_blacklisted_source(self, message: QueueMessage) -> bool:
        """Check if message from blacklisted source"""
        source = message.payload.get("source")
        return source in self.blacklisted_sources if source else False

    def _validate_schema(self, message: QueueMessage) -> bool:
        """Validate message against expected schema"""
        # In production, use jsonschema or pydantic
        # Simplified validation here
        try:
            # Check for expected structure
            return isinstance(message.payload, dict)
        except Exception:
            return False

    def _has_suspicious_patterns(self, message: QueueMessage) -> bool:
        """Detect suspicious patterns (SQL injection, XSS, etc.)"""
        # Simplified detection
        payload_str = json.dumps(message.payload).lower()

        suspicious_patterns = [
            "'; drop table",
            "<script>",
            "../../../",
            "union select",
        ]

        return any(pattern in payload_str for pattern in suspicious_patterns)


class QuarantineQueue:
    """
    Special queue for poison pill messages.

    Isolates problematic messages for manual review.
    """

    def __init__(self) -> None:
        self._quarantined: dict[str, tuple[QueueMessage, PoisonPillDetectionResult]] = {}

    def quarantine(
        self,
        message: QueueMessage,
        detection_result: PoisonPillDetectionResult,
    ) -> None:
        """Move message to quarantine"""

        self._quarantined[message.message_id] = (message, detection_result)

        print(
            f"🚫 Quarantined: {message.message_id} "
            f"(reason: {detection_result.reason.value if detection_result.reason else 'unknown'})"
        )

    def get_quarantined_messages(self) -> list[tuple[QueueMessage, PoisonPillDetectionResult]]:
        """Retrieve all quarantined messages"""
        return list(self._quarantined.values())

    def release(self, message_id: str) -> bool:
        """Release message from quarantine after manual review"""
        if message_id in self._quarantined:
            del self._quarantined[message_id]
            print(f"✓ Released from quarantine: {message_id}")
            return True
        return False


class PoisonPillAwareConsumer:
    """
    Consumer with poison pill detection.

    Fast-fails poison messages before expensive processing.
    """

    def __init__(
        self,
        queue: MessageQueue,
        detector: PoisonPillDetector,
        quarantine: QuarantineQueue,
    ) -> None:
        self.queue = queue
        self.detector = detector
        self.quarantine = quarantine
        self.poison_pill_count = 0

    async def consume(self, queue_name: str = "default") -> None:
        """Consume messages with poison pill detection"""

        while True:
            message = await self.queue.dequeue(queue_name, timeout=1)

            if not message:
                await asyncio.sleep(0.1)
                continue

            # Detect poison pill BEFORE processing
            detection_result = self.detector.detect(message)

            if detection_result.is_poison:
                # Fast-fail: don't process poison message
                self.poison_pill_count += 1
                self.quarantine.quarantine(message, detection_result)

                # Acknowledge to remove from queue
                await self.queue.ack(message.message_id, queue_name)

            else:
                # Safe to process
                try:
                    await self._process_message(message)
                    await self.queue.ack(message.message_id, queue_name)
                except Exception as e:
                    print(f"Processing error: {e}")
                    await self.queue.nack(message.message_id, queue_name)

    async def _process_message(self, message: QueueMessage) -> None:
        """Process valid message"""
        print(f"✓ Processing: {message.message_id}")
        await asyncio.sleep(0.1)  # Simulate processing


# Usage Demonstration
async def demonstrate_poison_pill_pattern() -> None:
    """Demonstrate poison pill detection"""

    print("=== Poison Pill Pattern Demo ===\n")

    # Setup
    queue = RedisMessageQueue()
    detector = PoisonPillDetector(
        max_message_size=1024,
        required_fields={"user_id", "action"},
        blacklisted_sources={"malicious_source"},
    )
    quarantine = QuarantineQueue()
    consumer = PoisonPillAwareConsumer(queue, detector, quarantine)

    # Scenario 1: Valid message
    print("Scenario 1: Valid message")
    valid_msg = QueueMessage(
        message_id="msg_001",
        payload={"user_id": "user123", "action": "purchase"},
        priority=MessagePriority.NORMAL,
        created_at=datetime.now(),
    )
    await queue.enqueue(valid_msg, "orders")

    # Scenario 2: Missing required fields (poison)
    print("\nScenario 2: Missing required fields")
    invalid_msg = QueueMessage(
        message_id="msg_002",
        payload={"action": "purchase"},  # Missing user_id
        priority=MessagePriority.NORMAL,
        created_at=datetime.now(),
    )
    await queue.enqueue(invalid_msg, "orders")

    # Scenario 3: Blacklisted source (poison)
    print("\nScenario 3: Blacklisted source")
    blacklisted_msg = QueueMessage(
        message_id="msg_003",
        payload={
            "user_id": "user456",
            "action": "fraud",
            "source": "malicious_source",
        },
        priority=MessagePriority.NORMAL,
        created_at=datetime.now(),
    )
    await queue.enqueue(blacklisted_msg, "orders")

    # Scenario 4: Suspicious pattern (SQL injection attempt)
    print("\nScenario 4: Suspicious pattern")
    suspicious_msg = QueueMessage(
        message_id="msg_004",
        payload={
            "user_id": "'; DROP TABLE users; --",
            "action": "query",
        },
        priority=MessagePriority.NORMAL,
        created_at=datetime.now(),
    )
    await queue.enqueue(suspicious_msg, "orders")

    # Process messages
    print("\n=== Processing Messages ===")
    for _ in range(4):
        message = await queue.dequeue("orders")
        if message:
            detection_result = detector.detect(message)

            if detection_result.is_poison:
                quarantine.quarantine(message, detection_result)
                await queue.ack(message.message_id, "orders")
            else:
                print(f"✓ Processing valid message: {message.message_id}")
                await queue.ack(message.message_id, "orders")

    # Review quarantined messages
    print("\n=== Quarantine Review ===")
    quarantined = quarantine.get_quarantined_messages()
    print(f"Total quarantined: {len(quarantined)}")

    for msg, result in quarantined:
        print(f"  - {msg.message_id}: {result.reason.value if result.reason else 'unknown'}")


# asyncio.run(demonstrate_poison_pill_pattern())
```

**Poison Pill Detection Strategies**:

| Strategy                   | Description                     | Cost     | When to Use               |
| -------------------------- | ------------------------------- | -------- | ------------------------- |
| **Size validation**        | Check message size limits       | Very low | Always (first check)      |
| **Required fields**        | Verify mandatory fields present | Low      | Structured data           |
| **Schema validation**      | Validate against JSON schema    | Medium   | Complex data structures   |
| **Content scanning**       | Detect malicious patterns       | High     | Security-critical systems |
| **Signature verification** | Verify message authenticity     | Medium   | Untrusted sources         |
| **Reputation scoring**     | Track source reliability        | Low      | Known producers           |

**Best Practices**:

1. **Fast-Fail Early**: Detect poison pills before expensive processing
2. **Layered Defense**: Multiple detection strategies
3. **Fail Closed**: When in doubt, quarantine
4. **Monitor Quarantine**: Alert on quarantine growth
5. **Manual Review**: Human in the loop for edge cases
6. **Update Detection**: Continuously improve detection rules

**Advantages**:

-   ✅ Prevents resource waste on poison messages
-   ✅ Reduces operational noise from expected failures
-   ✅ Protects against malicious input
-   ✅ Improves system stability
-   ✅ Fast-fail reduces latency
-   ✅ Easier debugging with isolated poison messages

**Disadvantages**:

-   ❌ False positives may quarantine valid messages
-   ❌ Detection logic adds processing overhead
-   ❌ Requires tuning and maintenance
-   ❌ Can be bypassed by sophisticated attacks
-   ❌ Quarantine requires manual intervention

**Related Patterns**:

-   **Dead Letter Queue**: Where poison pills ultimately go after max retries
-   **Quarantine Pattern**: Temporary isolation for suspicious messages
-   **Input Validation**: Prevent poison pills at system boundaries
-   **Circuit Breaker**: Protect downstream services from poison pills

---

## Resilience Patterns

Resilience patterns protect systems from cascading failures, handle transient
errors gracefully, and ensure system stability under adverse conditions.

### 4. Circuit Breaker Pattern

**Category**: Resilience Pattern

**Intent**: Prevent cascading failures by detecting when a service is unhealthy
and failing fast instead of waiting for timeouts, allowing the failing service
time to recover.

**Problem**:

-   Calls to failing services waste resources (threads, connections, time)
-   Cascading failures propagate through the system
-   Waiting for timeouts increases latency for clients
-   Failing services need time to recover without load
-   Need to detect failures and fail fast

**Solution**:

-   Wrap service calls with a circuit breaker
-   Monitor failure rates and response times
-   Three states: **Closed** (normal), **Open** (failing fast), **Half-Open**
    (testing recovery)
-   Transition between states based on failure thresholds
-   Provide fallback responses when circuit is open

**When to Use**:

-   Calling external services (APIs, databases, microservices)
-   Operations with potential for cascading failures
-   Need to protect against slow or unresponsive dependencies
-   Want to give failing services time to recover
-   Need fast failure detection and automatic recovery

**State Machine**:

```
                    ┌─────────────┐
                    │             │
            ┌──────▶│   CLOSED    │◄──────┐
            │       │  (Normal)   │       │
            │       │             │       │
            │       └──────┬──────┘       │
            │              │               │
            │    failure   │               │
            │   threshold  │               │
            │   exceeded   │               │success
            │              │          threshold
            │              ▼          exceeded
            │       ┌─────────────┐       │
            │       │             │       │
            │       │    OPEN     │       │
            │       │  (Failing   │       │
            │       │    Fast)    │       │
            │       │             │       │
            │       └──────┬──────┘       │
            │              │               │
            │     timeout  │               │
            │    expired   │               │
            │              │               │
            │              ▼               │
            │       ┌─────────────┐       │
            │       │             │       │
            └───────│ HALF-OPEN   │───────┘
             failure│  (Testing   │ success
                    │  Recovery)  │
                    │             │
                    └─────────────┘
```

**Python Implementation**:

```python
from __future__ import annotations
from typing import Protocol, Callable, Any, TypeVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import asyncio
from functools import wraps

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes before closing from half-open
    timeout: timedelta = timedelta(seconds=60)  # Time before trying half-open
    expected_exception: type[Exception] = Exception


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker"""

    state: CircuitState
    failure_count: int
    success_count: int
    last_failure_time: datetime | None
    last_state_change: datetime
    total_calls: int
    total_failures: int
    total_successes: int


class CircuitBreakerOpenException(Exception):
    """Raised when circuit breaker is open"""

    pass


class CircuitBreaker:
    """
    Circuit breaker implementation.

    Protects against cascading failures by failing fast when
    a service is detected to be unhealthy.
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()

        # State
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: datetime | None = None
        self._last_state_change = datetime.now()

        # Statistics
        self._total_calls = 0
        self._total_failures = 0
        self._total_successes = 0

        # Locking for thread safety
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit breaker state"""
        return self._state

    async def call(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute function with circuit breaker protection.

        Raises:
            CircuitBreakerOpenException: If circuit is open
        """

        async with self._lock:
            self._total_calls += 1

            # Check if circuit should transition to half-open
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._transition_to_half_open()
                else:
                    raise CircuitBreakerOpenException(
                        f"Circuit breaker '{self.name}' is OPEN"
                    )

            # Check if circuit is open
            if self._state == CircuitState.OPEN:
                raise CircuitBreakerOpenException(
                    f"Circuit breaker '{self.name}' is OPEN"
                )

        # Call function (outside lock to prevent blocking)
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)

            # Record success
            async with self._lock:
                self._on_success()

            return result

        except self.config.expected_exception as e:
            # Record failure
            async with self._lock:
                self._on_failure()

            raise e

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self._last_failure_time is None:
            return True

        elapsed = datetime.now() - self._last_failure_time
        return elapsed >= self.config.timeout

    def _on_success(self) -> None:
        """Handle successful call"""
        self._total_successes += 1
        self._failure_count = 0

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1

            if self._success_count >= self.config.success_threshold:
                self._transition_to_closed()

    def _on_failure(self) -> None:
        """Handle failed call"""
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = datetime.now()
        self._success_count = 0

        if self._state == CircuitState.CLOSED:
            if self._failure_count >= self.config.failure_threshold:
                self._transition_to_open()

        elif self._state == CircuitState.HALF_OPEN:
            self._transition_to_open()

    def _transition_to_open(self) -> None:
        """Transition to OPEN state"""
        print(f"🔴 Circuit breaker '{self.name}' -> OPEN")
        self._state = CircuitState.OPEN
        self._last_state_change = datetime.now()

    def _transition_to_half_open(self) -> None:
        """Transition to HALF_OPEN state"""
        print(f"🟡 Circuit breaker '{self.name}' -> HALF_OPEN")
        self._state = CircuitState.HALF_OPEN
        self._failure_count = 0
        self._success_count = 0
        self._last_state_change = datetime.now()

    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state"""
        print(f"🟢 Circuit breaker '{self.name}' -> CLOSED")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_state_change = datetime.now()

    def get_stats(self) -> CircuitBreakerStats:
        """Get current statistics"""
        return CircuitBreakerStats(
            state=self._state,
            failure_count=self._failure_count,
            success_count=self._success_count,
            last_failure_time=self._last_failure_time,
            last_state_change=self._last_state_change,
            total_calls=self._total_calls,
            total_failures=self._total_failures,
            total_successes=self._total_successes,
        )

    async def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state"""
        async with self._lock:
            self._transition_to_closed()


# Decorator for easy circuit breaker usage
def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    success_threshold: int = 2,
    timeout_seconds: int = 60,
) -> Callable:
    """
    Decorator to wrap function with circuit breaker.

    Usage:
        @circuit_breaker("external_api", failure_threshold=3)
        async def call_external_api():
            # API call here
    """

    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        success_threshold=success_threshold,
        timeout=timedelta(seconds=timeout_seconds),
    )

    breaker = CircuitBreaker(name, config)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await breaker.call(func, *args, **kwargs)

        wrapper.circuit_breaker = breaker  # Expose breaker for inspection
        return wrapper

    return decorator


# Example: External API Client with Circuit Breaker
class ExternalAPIClient:
    """
    Client for external API with circuit breaker protection.

    Prevents cascading failures when API is down.
    """

    def __init__(self) -> None:
        self.circuit_breaker = CircuitBreaker(
            name="external_api",
            config=CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout=timedelta(seconds=10),
            ),
        )
        self.call_count = 0

    async def fetch_data(self, user_id: str) -> dict:
        """
        Fetch user data from external API.

        Protected by circuit breaker.
        """

        async def _fetch() -> dict:
            self.call_count += 1

            # Simulate API call
            await asyncio.sleep(0.1)

            # Simulate intermittent failures
            if self.call_count % 3 == 0:
                raise ConnectionError("API unavailable")

            return {"user_id": user_id, "name": f"User {user_id}"}

        try:
            return await self.circuit_breaker.call(_fetch)

        except CircuitBreakerOpenException:
            # Circuit is open - return fallback response
            print(f"⚠️  Circuit breaker open, returning fallback")
            return {"user_id": user_id, "name": "Unknown (service unavailable)"}


# Usage Demonstration
async def demonstrate_circuit_breaker_pattern() -> None:
    """Demonstrate circuit breaker pattern"""

    print("=== Circuit Breaker Pattern Demo ===\n")

    client = ExternalAPIClient()

    # Make multiple API calls
    for i in range(15):
        try:
            result = await client.fetch_data(f"user_{i}")
            print(f"Call {i + 1}: Success - {result['name']}")

        except Exception as e:
            print(f"Call {i + 1}: Failed - {e}")

        # Show circuit breaker state
        stats = client.circuit_breaker.get_stats()
        print(f"  State: {stats.state.value}, Failures: {stats.failure_count}/3\n")

        await asyncio.sleep(0.5)

    # Final statistics
    print("\n=== Final Statistics ===")
    stats = client.circuit_breaker.get_stats()
    print(f"State: {stats.state.value}")
    print(f"Total Calls: {stats.total_calls}")
    print(f"Total Successes: {stats.total_successes}")
    print(f"Total Failures: {stats.total_failures}")


# asyncio.run(demonstrate_circuit_breaker_pattern())
```

**Real-World Circuit Breaker Implementations**:

| Library/Service          | Language    | Features                                      |
| ------------------------ | ----------- | --------------------------------------------- |
| **Resilience4j**         | Java        | Declarative, metrics, retry + circuit breaker |
| **Polly**                | C#          | Fluent API, policy combinations               |
| **Hystrix** (deprecated) | Java        | Dashboard, thread pools, fallbacks            |
| **PyBreaker**            | Python      | Simple, pluggable storage                     |
| **Failsafe**             | Java/Kotlin | Functional, composable policies               |
| **AWS App Mesh**         | Cloud       | Service mesh with built-in circuit breaking   |

**Configuration Guidelines**:

```python
# Conservative (tolerate more failures)
CircuitBreakerConfig(
    failure_threshold=10,  # More failures before opening
    success_threshold=5,  # More successes before closing
    timeout=timedelta(seconds=120),  # Longer recovery time
)

# Aggressive (fail fast)
CircuitBreakerConfig(
    failure_threshold=3,  # Quick to open
    success_threshold=1,  # Quick to close
    timeout=timedelta(seconds=30),  # Short recovery time
)

# Production-ready
CircuitBreakerConfig(
    failure_threshold=5,
    success_threshold=2,
    timeout=timedelta(seconds=60),
    expected_exception=HTTPError,  # Only catch specific exceptions
)
```

**Best Practices**:

1. **Granular Circuit Breakers**: One per external dependency, not shared

    ```python
    # Good: Separate breakers
    payment_breaker = CircuitBreaker("payment_service")
    notification_breaker = CircuitBreaker("notification_service")

    # Bad: Shared breaker
    shared_breaker = CircuitBreaker("all_services")  # Too coarse-grained
    ```

2. **Provide Fallbacks**: Always handle `CircuitBreakerOpenException`

    ```python
    try:
        data = await circuit_breaker.call(fetch_from_primary)
    except CircuitBreakerOpenException:
        data = fetch_from_cache()  # Fallback to cache
    ```

3. **Monitor and Alert**:

    ```python
    if circuit_breaker.state == CircuitState.OPEN:
        alert_ops_team(f"Circuit breaker {name} is OPEN")
        metrics.increment("circuit_breaker.open")
    ```

4. **Test State Transitions**: Verify state machine logic

    ```python
    # Trigger failures to open circuit
    # Wait for timeout
    # Verify transition to half-open
    # Verify successful recovery to closed
    ```

5. **Exponential Backoff**: Increase timeout after repeated failures
    ```python
    class AdaptiveCircuitBreaker(CircuitBreaker):
        def _on_failure(self):
            super()._on_failure()
            # Double timeout after each open state
            self.config.timeout *= 2
    ```

**Advantages**:

-   ✅ Prevents cascading failures
-   ✅ Fails fast, reducing resource waste
-   ✅ Gives failing services time to recover
-   ✅ Improves overall system resilience
-   ✅ Provides clear failure visibility
-   ✅ Automatic recovery testing (half-open state)

**Disadvantages**:

-   ❌ Adds complexity to error handling
-   ❌ False positives can occur (transient blips opening circuit)
-   ❌ Requires careful threshold tuning
-   ❌ May hide underlying issues if fallbacks always succeed
-   ❌ Difficult to test all state transitions

**Related Patterns**:

-   **Retry Pattern**: Often used together (retry before opening circuit)
-   **Timeout Pattern**: Circuit breaker should respect timeouts
-   **Bulkhead Pattern**: Isolates resources, circuit breaker isolates failures
-   **Fallback Pattern**: Provides alternative responses when circuit is open
-   **Health Check**: Monitors service health to inform circuit breaker

---

### 5. Retry Pattern with Exponential Backoff

**Category**: Resilience Pattern

**Intent**: Automatically retry failed operations with increasing delays between
attempts, handling transient failures gracefully while avoiding overwhelming
failing services.

**Problem**:

-   Transient failures are common in distributed systems (network blips,
    temporary overload)
-   Immediate retries may overwhelm already struggling services
-   Fixed retry intervals create thundering herd problems
-   Need to balance quick recovery with avoiding service overload
-   Want to distinguish transient from permanent failures

**Solution**:

-   Retry failed operations with exponentially increasing delays
-   Add random jitter to prevent synchronized retries
-   Set maximum retry attempts to avoid infinite loops
-   Only retry for retriable errors (not validation errors)
-   Combine with circuit breaker for complete resilience

**When to Use**:

-   Network operations (API calls, database queries)
-   Transient failures are expected
-   Operations are idempotent
-   Need automatic recovery from temporary issues
-   Want to avoid thundering herd effect

**Backoff Strategies**:

```
Fixed Delay:
├─ Attempt 1
├─ Wait 1s
├─ Attempt 2
├─ Wait 1s
├─ Attempt 3
└─ Wait 1s

Exponential Backoff:
├─ Attempt 1
├─ Wait 1s
├─ Attempt 2
├─ Wait 2s
├─ Attempt 3
├─ Wait 4s
├─ Attempt 4
└─ Wait 8s

Exponential + Jitter:
├─ Attempt 1
├─ Wait 1.2s (1s + 0.2s jitter)
├─ Attempt 2
├─ Wait 2.7s (2s + 0.7s jitter)
├─ Attempt 3
├─ Wait 3.5s (4s - 0.5s jitter)
└─ ...
```

**Python Implementation**:

```python
from __future__ import annotations
from typing import TypeVar, Callable, Any
from dataclasses import dataclass
from datetime import datetime
import asyncio
import random
from functools import wraps

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry logic"""

    max_attempts: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    retriable_exceptions: tuple[type[Exception], ...] = (Exception,)


@dataclass
class RetryStats:
    """Statistics for retry operations"""

    total_attempts: int
    successful_attempt: int | None
    final_delay: float
    total_time: float
    exception: Exception | None


class RetryExhausted(Exception):
    """Raised when max retry attempts exceeded"""

    pass


class RetryStrategy:
    """
    Retry strategy with exponential backoff and jitter.

    Implements best practices for retrying failed operations.
    """

    def __init__(self, config: RetryConfig | None = None) -> None:
        self.config = config or RetryConfig()

    async def execute(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> tuple[T, RetryStats]:
        """
        Execute function with retry logic.

        Returns: (result, stats)
        Raises: RetryExhausted if all attempts fail
        """

        start_time = datetime.now()
        last_exception: Exception | None = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                # Execute function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Success!
                elapsed = (datetime.now() - start_time).total_seconds()

                stats = RetryStats(
                    total_attempts=attempt,
                    successful_attempt=attempt,
                    final_delay=0.0,
                    total_time=elapsed,
                    exception=None,
                )

                if attempt > 1:
                    print(f"✓ Succeeded on attempt {attempt}")

                return result, stats

            except self.config.retriable_exceptions as e:
                last_exception = e
                print(f"✗ Attempt {attempt} failed: {e}")

                # Last attempt - don't wait
                if attempt == self.config.max_attempts:
                    break

                # Calculate backoff delay
                delay = self._calculate_delay(attempt)
                print(f"  ⏱  Retrying in {delay:.2f}s...")

                await asyncio.sleep(delay)

        # All attempts exhausted
        elapsed = (datetime.now() - start_time).total_seconds()

        stats = RetryStats(
            total_attempts=self.config.max_attempts,
            successful_attempt=None,
            final_delay=0.0,
            total_time=elapsed,
            exception=last_exception,
        )

        raise RetryExhausted(
            f"Failed after {self.config.max_attempts} attempts"
        ) from last_exception

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate backoff delay with exponential + jitter"""

        # Exponential backoff: delay = base^(attempt-1) * initial_delay
        delay = min(
            self.config.initial_delay * (self.config.exponential_base ** (attempt - 1)),
            self.config.max_delay,
        )

        # Add jitter to prevent thundering herd
        if self.config.jitter:
            # Full jitter: random between 0 and delay
            delay = random.uniform(0, delay)

        return delay


# Decorator for easy retry usage
def retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retriable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """
    Decorator for automatic retry with exponential backoff.

    Usage:
        @retry(max_attempts=3, initial_delay=1.0)
        async def fetch_data():
            # Network call here
    """

    config = RetryConfig(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
        retriable_exceptions=retriable_exceptions,
    )

    strategy = RetryStrategy(config)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result, stats = await strategy.execute(func, *args, **kwargs)
            return result

        return wrapper

    return decorator


# Example: API Client with Retry
class ResilientAPIClient:
    """
    API client with retry logic for transient failures.

    Handles network errors, timeouts, and server errors.
    """

    def __init__(self) -> None:
        self.retry_strategy = RetryStrategy(
            RetryConfig(
                max_attempts=5,
                initial_delay=1.0,
                max_delay=30.0,
                exponential_base=2.0,
                jitter=True,
                # Only retry network and server errors
                retriable_exceptions=(ConnectionError, TimeoutError),
            )
        )

        self.call_count = 0

    @retry(
        max_attempts=3,
        initial_delay=0.5,
        retriable_exceptions=(ConnectionError, TimeoutError),
    )
    async def fetch_user(self, user_id: str) -> dict:
        """
        Fetch user with automatic retry.

        Uses decorator for simple retry logic.
        """

        self.call_count += 1

        # Simulate intermittent failures
        if self.call_count % 2 == 0:
            raise ConnectionError("Network error")

        return {"user_id": user_id, "name": f"User {user_id}"}

    async def create_order(self, order_data: dict) -> dict:
        """
        Create order with explicit retry strategy.

        Uses RetryStrategy directly for more control.
        """

        async def _create() -> dict:
            self.call_count += 1

            # Simulate failures
            if self.call_count <= 2:
                raise ConnectionError("Service temporarily unavailable")

            # Validation errors should NOT be retried
            if "invalid" in order_data.get("status", ""):
                raise ValueError("Invalid order status")

            return {"order_id": "order_123", **order_data}

        try:
            result, stats = await self.retry_strategy.execute(_create)

            print(f"\n✓ Order created after {stats.total_attempts} attempts")
            print(f"  Total time: {stats.total_time:.2f}s")

            return result

        except RetryExhausted as e:
            print(f"\n✗ Order creation failed: {e}")
            raise


# Usage Demonstration
async def demonstrate_retry_pattern() -> None:
    """Demonstrate retry pattern with exponential backoff"""

    print("=== Retry Pattern Demo ===\n")

    client = ResilientAPIClient()

    # Scenario 1: Fetch user (decorator-based retry)
    print("Scenario 1: Fetch user with automatic retry")
    try:
        user = await client.fetch_user("user_123")
        print(f"✓ Result: {user}\n")
    except Exception as e:
        print(f"✗ Failed: {e}\n")

    # Scenario 2: Create order (explicit retry strategy)
    print("Scenario 2: Create order with retry strategy")
    client.call_count = 0  # Reset counter

    try:
        order = await client.create_order({"status": "pending", "amount": 99.99})
        print(f"✓ Result: {order}\n")
    except Exception as e:
        print(f"✗ Failed: {e}\n")

    # Scenario 3: Demonstrate exponential backoff timing
    print("Scenario 3: Exponential backoff timing")

    config = RetryConfig(
        max_attempts=5,
        initial_delay=0.5,
        jitter=False,  # Disable jitter for predictable demo
    )

    for attempt in range(1, 6):
        delay = config.initial_delay * (config.exponential_base ** (attempt - 1))
        delay = min(delay, config.max_delay)
        print(f"Attempt {attempt}: delay = {delay:.2f}s")


# asyncio.run(demonstrate_retry_pattern())
```

**Retry Decision Matrix**:

| Error Type                     | Retry? | Strategy                 | Example                  |
| ------------------------------ | ------ | ------------------------ | ------------------------ |
| **Network timeout**            | ✅ Yes | Exponential backoff      | `requests.Timeout`       |
| **Connection refused**         | ✅ Yes | Exponential backoff      | `ConnectionRefusedError` |
| **HTTP 429 (Rate limit)**      | ✅ Yes | Use `Retry-After` header | API rate limiting        |
| **HTTP 500/502/503**           | ✅ Yes | Exponential backoff      | Server errors            |
| **HTTP 504 (Gateway timeout)** | ✅ Yes | Exponential backoff      | Upstream timeout         |
| **HTTP 400 (Bad request)**     | ❌ No  | Fail immediately         | Validation error         |
| **HTTP 401/403**               | ❌ No  | Fail immediately         | Authentication error     |
| **HTTP 404**                   | ❌ No  | Fail immediately         | Resource not found       |
| **Validation errors**          | ❌ No  | Fail immediately         | Invalid input            |

**Best Practices**:

1. **Idempotency Keys**: Ensure retries are safe

    ```python
    @retry(max_attempts=3)
    async def create_payment(payment_data: dict, idempotency_key: str):
        # Idempotency key ensures duplicate retries don't double-charge
        headers = {"Idempotency-Key": idempotency_key}
        return await payment_api.post("/payments", payment_data, headers=headers)
    ```

2. **Jitter is Essential**: Prevents thundering herd

    ```python
    # Bad: All clients retry at same time
    delay = 2 ** attempt  # 1s, 2s, 4s, 8s...

    # Good: Randomized delays
    delay = random.uniform(0, 2 ** attempt)  # Spread out retries
    ```

3. **Respect Retry-After Headers**:

    ```python
    async def retry_with_headers(response):
        if response.status == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                await asyncio.sleep(int(retry_after))
                # Retry request
    ```

4. **Circuit Breaker + Retry**: Powerful combination

    ```python
    @circuit_breaker("api", failure_threshold=5)
    @retry(max_attempts=3)
    async def resilient_api_call():
        # First retries transient failures
        # Then opens circuit after repeated failures
        pass
    ```

5. **Metrics and Monitoring**:

    ```python
    async def execute_with_metrics(func):
        result, stats = await retry_strategy.execute(func)

        metrics.histogram("retry.attempts", stats.total_attempts)
        metrics.histogram("retry.duration", stats.total_time)

        if stats.successful_attempt and stats.successful_attempt > 1:
            metrics.increment("retry.recovered")
    ```

**Advantages**:

-   ✅ Automatic recovery from transient failures
-   ✅ Exponential backoff prevents overwhelming services
-   ✅ Jitter prevents thundering herd
-   ✅ Improves system reliability
-   ✅ Transparent to callers (when using decorators)

**Disadvantages**:

-   ❌ Increases latency (waiting for retries)
-   ❌ Can mask underlying issues
-   ❌ Resource consumption during retries
-   ❌ Requires idempotent operations
-   ❌ May retry non-retriable errors if misconfigured

**Related Patterns**:

-   **Circuit Breaker**: Use together for complete resilience
-   **Timeout Pattern**: Set timeouts for each retry attempt
-   **Idempotency**: Essential for safe retries
-   **Dead Letter Queue**: Where retry-exhausted messages go

---

## Summary and Pattern Quick Reference

This comprehensive guide covers the foundational distributed systems patterns
essential for building production-grade applications.

### ✅ Patterns Covered

**System Design Principles** (Complete):

-   Design for Failure - Assume all components will fail
-   Idempotency - Safe retries without side effects
-   Eventual Consistency - Accept temporary inconsistency for availability
-   Loose Coupling - Minimize dependencies between services

**Message Queue Patterns** (Complete):

1. **Queue Pattern** - Decouple producers/consumers with buffering
2. **Dead Letter Queue (DLQ)** - Isolate permanently failed messages
3. **Poison Pill Pattern** - Detect and quarantine malicious/malformed messages

**Resilience Patterns** (Complete): 4. **Circuit Breaker** - Fail fast and
prevent cascading failures 5. **Retry with Exponential Backoff** - Automatic
recovery from transient failures

### 🔄 Additional Patterns (To be added)

**Resilience Patterns**:

-   Timeout Pattern - Prevent indefinite waiting
-   Bulkhead Pattern - Isolate resources to contain failures
-   Rate Limiting - Control request rates
-   Backpressure - Handle overwhelming load gracefully

**Data Consistency Patterns**:

-   Saga Pattern - Distributed transactions
-   Event Sourcing - Event-driven state management
-   CQRS - Separate read/write models
-   Outbox Pattern - Reliable event publishing
-   Two-Phase Commit - Atomic distributed transactions

**Scalability Patterns**:

-   Load Balancing - Distribute load across instances
-   Sharding/Partitioning - Horizontal data scaling
-   Replication - Data redundancy and high availability
-   Caching Strategies - Reduce database load
-   CDN - Content delivery optimization

**Observability Patterns**:

-   Health Check - Service health monitoring
-   Metrics Collection - Performance tracking
-   Distributed Tracing - Request flow tracking
-   Log Aggregation - Centralized logging
-   Audit Logging - Compliance and forensics

---

## Pattern Selection Guide

### Quick Decision Trees

#### When Building a New Service

```
Starting new microservice?
│
├─ Need async processing?
│  └─ YES → Queue Pattern + DLQ
│
├─ Calling external APIs?
│  └─ YES → Circuit Breaker + Retry + Timeout
│
├─ Need data consistency across services?
│  └─ YES → Saga Pattern or Outbox Pattern
│
├─ High read load?
│  └─ YES → CQRS + Caching
│
└─ Need to scale horizontally?
   └─ YES → Load Balancing + Sharding
```

#### When Fixing Production Issues

```
Production issue?
│
├─ Cascading failures?
│  └─ Circuit Breaker Pattern
│
├─ Queue backing up?
│  └─ DLQ + Poison Pill Detection
│
├─ Intermittent failures?
│  └─ Retry Pattern
│
├─ Slow response times?
│  └─ Timeout + Circuit Breaker
│
└─ Data inconsistency?
   └─ Eventual Consistency + Event Sourcing
```

---

## Implementation Best Practices

### 1. Layered Resilience

Combine multiple patterns for maximum reliability:

```python
# Layered resilience strategy
@timeout(seconds=30)  # 1. Timeout protection
@circuit_breaker("payment_api", failure_threshold=5)  # 2. Circuit breaker
@retry(max_attempts=3, exponential_backoff=True)  # 3. Retry logic
async def process_payment(payment_data: dict) -> PaymentResult:
    # Make API call with idempotency
    return await payment_api.charge(
        payment_data,
        idempotency_key=generate_idempotency_key(payment_data),
    )
```

### 2. Observability First

Always instrument patterns with metrics and logging:

```python
# Monitor pattern effectiveness
metrics.histogram("circuit_breaker.state", circuit_breaker.state.value)
metrics.increment("retry.attempts", retry_stats.total_attempts)
metrics.histogram("dlq.depth", dlq_manager.get_depth())

# Structured logging
logger.info(
    "pattern.executed",
    pattern="circuit_breaker",
    state=circuit_breaker.state.value,
    success=success,
)
```

### 3. Testing Strategies

Test patterns thoroughly:

```python
# Test circuit breaker state transitions
async def test_circuit_breaker():
    # 1. Verify opens after threshold
    for _ in range(5):
        with pytest.raises(Exception):
            await circuit_breaker.call(failing_function)

    assert circuit_breaker.state == CircuitState.OPEN

    # 2. Verify half-open after timeout
    await asyncio.sleep(circuit_breaker.timeout)
    assert circuit_breaker.state == CircuitState.HALF_OPEN

    # 3. Verify closes after success
    await circuit_breaker.call(successful_function)
    assert circuit_breaker.state == CircuitState.CLOSED
```

### 4. Configuration Management

Externalize pattern configuration:

```yaml
# config.yaml
resilience:
    circuit_breakers:
        payment_api:
            failure_threshold: 5
            success_threshold: 2
            timeout_seconds: 60

    retry:
        default:
            max_attempts: 3
            initial_delay_ms: 1000
            max_delay_ms: 60000
            exponential_base: 2.0
            jitter: true

    dlq:
        max_attempts: 3
        retention_days: 14
```

---

## Pattern Relationships

Understanding how patterns interact:

```
┌────────────────────────────────────────────────────────┐
│                 Pattern Ecosystem                       │
├────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐     ┌──────────────┐                │
│  │   Retry      │────▶│    Circuit   │                │
│  │   Pattern    │     │    Breaker   │                │
│  └──────────────┘     └──────────────┘                │
│         │                     │                         │
│         │                     │                         │
│         ▼                     ▼                         │
│  ┌──────────────┐     ┌──────────────┐                │
│  │   Timeout    │     │   Bulkhead   │                │
│  │   Pattern    │     │   Pattern    │                │
│  └──────────────┘     └──────────────┘                │
│                                                          │
│  ┌──────────────┐     ┌──────────────┐                │
│  │    Queue     │────▶│     DLQ      │                │
│  │   Pattern    │     │   Pattern    │                │
│  └──────────────┘     └──────────────┘                │
│         │                     │                         │
│         │                     │                         │
│         ▼                     ▼                         │
│  ┌──────────────┐     ┌──────────────┐                │
│  │ Poison Pill  │     │  Quarantine  │                │
│  │  Detection   │     │   Pattern    │                │
│  └──────────────┘     └──────────────┘                │
└────────────────────────────────────────────────────────┘
```

**Common Combinations**:

1. **API Client Resilience**:

    - Timeout → Retry → Circuit Breaker
    - Fast failure with automatic recovery

2. **Message Queue Robustness**:

    - Poison Pill Detection → Queue → DLQ
    - Filter bad messages before processing

3. **Resource Protection**:

    - Rate Limiting → Bulkhead → Circuit Breaker
    - Prevent resource exhaustion

4. **Data Consistency**:
    - Idempotency → Outbox → Event Sourcing
    - Reliable event processing

---

## Monitoring and Alerting

### Key Metrics to Track

| Pattern             | Metric                               | Alert Threshold |
| ------------------- | ------------------------------------ | --------------- |
| **Circuit Breaker** | `circuit_breaker.open`               | > 0 (immediate) |
| **Circuit Breaker** | `circuit_breaker.half_open_duration` | > 5 minutes     |
| **DLQ**             | `dlq.depth`                          | > 100 messages  |
| **DLQ**             | `dlq.growth_rate`                    | > 10/minute     |
| **Retry**           | `retry.exhausted_count`              | > 50/hour       |
| **Retry**           | `retry.average_attempts`             | > 2             |
| **Poison Pill**     | `poison_pill.detected`               | > 20/hour       |
| **Queue**           | `queue.depth`                        | > 10,000        |
| **Queue**           | `queue.age_seconds`                  | > 300           |

### Dashboards

Create dashboards for each pattern:

```python
# Grafana dashboard configuration
{
    "circuit_breaker": {
        "panels": [
            "State distribution (pie chart)",
            "Failure rate over time (graph)",
            "Recovery time (histogram)",
            "Open events (alert list)",
        ]
    },
    "dlq": {
        "panels": [
            "DLQ depth (gauge)",
            "Failure reason breakdown (bar chart)",
            "Messages moved to DLQ (counter)",
            "Replay success rate (percentage)",
        ]
    },
}
```

---

## Further Reading

### Books

-   **Designing Data-Intensive Applications** (Martin Kleppmann) - Deep dive
    into distributed systems
-   **Release It!** (Michael Nygard) - Resilience patterns for production
-   **Building Microservices** (Sam Newman) - Service design patterns
-   **Site Reliability Engineering** (Google) - Production best practices

### Online Resources

-   [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
-   [Microsoft Azure Architecture Center](https://docs.microsoft.com/en-us/azure/architecture/)
-   [Martin Fowler's Blog](https://martinfowler.com/) - Enterprise patterns
-   [High Scalability](http://highscalability.com/) - Real-world case studies

### Tools and Libraries

-   **Resilience4j** (Java) - Comprehensive resilience library
-   **Polly** (C#) - Resilience and transient-fault-handling
-   **Tenacity** (Python) - Retry library with multiple strategies
-   **PyBreaker** (Python) - Circuit breaker implementation
-   **Redis** - Queue and caching patterns
-   **Kafka** - Event streaming patterns
-   **RabbitMQ** - Message queue patterns

---

## Conclusion

System design patterns are the foundation of reliable, scalable distributed
systems. This guide has covered the essential patterns with production-ready
Python implementations:

### ✅ What You've Learned

1. **Foundational Principles**:

    - Design for failure from day one
    - Idempotency enables safe retries
    - Eventual consistency is a feature, not a bug
    - Loose coupling allows independent evolution

2. **Message Queue Mastery**:

    - Queue pattern for async processing
    - DLQ prevents poison messages from blocking queues
    - Poison pill detection protects system resources

3. **Resilience Engineering**:

    - Circuit breakers prevent cascading failures
    - Exponential backoff with jitter prevents thundering herds
    - Layered resilience provides defense in depth

4. **Production Readiness**:
    - Comprehensive monitoring and alerting
    - Proper configuration management
    - Thorough testing strategies
    - Pattern combinations for maximum reliability

### 🎯 Key Takeaways

-   **Patterns are tools, not rules**: Apply patterns where they add value, not
    everywhere
-   **Observability is essential**: You can't improve what you don't measure
-   **Test failure scenarios**: Most bugs appear during failures
-   **Start simple, add complexity when needed**: Don't over-engineer early
-   **Learn from failures**: Post-mortems improve system design

### 🚀 Next Steps

1. **Apply these patterns** to your current projects
2. **Monitor pattern effectiveness** with metrics
3. **Share knowledge** with your team
4. **Iterate and improve** based on production data
5. **Expand your knowledge** with remaining patterns (Saga, CQRS, etc.)

---

**Document Version**: 1.0 **Last Updated**: 2025-11-22 **Completeness**:
Foundational system design patterns with production implementations

This guide will continue to be expanded with remaining patterns:

-   Timeout, Bulkhead, Rate Limiting (Resilience)
-   Saga, Event Sourcing, CQRS, Outbox (Data Consistency)
-   Load Balancing, Sharding, Caching (Scalability)
-   Health Checks, Metrics, Tracing (Observability)

Each addition will maintain the same depth, formalism, and production-ready code
quality demonstrated in this foundation.

---

**Built with ❤️ for production-grade distributed systems**

# Comprehensive Design Patterns Guide 🏗️

**A Complete Blueprint for Software Architecture Excellence**

---

## Table of Contents

1. [Introduction](#introduction)
2. [SOLID Principles Foundation](#solid-principles-foundation)
3. [Creational Patterns](#creational-patterns)
4. [Structural Patterns](#structural-patterns)
5. [Behavioral Patterns](#behavioral-patterns)
6. [Architectural Patterns](#architectural-patterns)
7. [Concurrency Patterns](#concurrency-patterns)
8. [Integration Patterns](#integration-patterns)
9. [Anti-Patterns to Avoid](#anti-patterns-to-avoid)
10. [Pattern Selection Guide](#pattern-selection-guide)

---

## Introduction

Design patterns are proven, reusable solutions to commonly occurring problems in
software design. They represent the accumulated wisdom of experienced developers
and provide a shared vocabulary for discussing software architecture.

### Why Patterns Matter

-   **Communication**: Shared vocabulary enables precise technical discussions
-   **Reusability**: Proven solutions reduce risk and development time
-   **Maintainability**: Standardized approaches improve code clarity
-   **Scalability**: Proper patterns support system growth
-   **Quality**: Patterns encode best practices and avoid common pitfalls

### Pattern Categories

```
┌─────────────────────────────────────────────────────┐
│                 Design Patterns                      │
├─────────────────────────────────────────────────────┤
│                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │  Creational  │  │  Structural  │  │ Behavioral │ │
│  │   Patterns   │  │   Patterns   │  │  Patterns  │ │
│  └──────────────┘  └──────────────┘  └────────────┘ │
│         │                  │                 │       │
│         ├─ Factory         ├─ Adapter        ├─ Strategy │
│         ├─ Builder         ├─ Bridge         ├─ Observer │
│         ├─ Singleton       ├─ Composite      ├─ Command  │
│         ├─ Prototype       ├─ Decorator      ├─ Template │
│         └─ Abstract Factory├─ Facade         ├─ Iterator │
│                            ├─ Flyweight      ├─ Chain    │
│                            └─ Proxy          └─ State    │
└─────────────────────────────────────────────────────┘
```

---

## SOLID Principles Foundation

Before diving into patterns, understanding SOLID principles is essential. These
principles guide the application of design patterns.

### S - Single Responsibility Principle (SRP)

**Definition**: A class should have one, and only one, reason to change.

**Rationale**:

-   Reduces coupling between responsibilities
-   Improves code clarity and maintainability
-   Makes testing easier with focused test cases
-   Facilitates parallel development

**Python Implementation**:

```python
from __future__ import annotations
from typing import Protocol
from dataclasses import dataclass
from datetime import datetime


# ❌ VIOLATION: Multiple responsibilities
class UserManager:
    def create_user(self, name: str, email: str) -> None:
        # User creation logic
        pass

    def send_welcome_email(self, email: str) -> None:
        # Email sending logic
        pass

    def log_user_creation(self, user_id: int) -> None:
        # Logging logic
        pass


# ✅ CORRECT: Single responsibility per class
@dataclass
class User:
    id: int
    name: str
    email: str
    created_at: datetime


class UserRepository:
    """Single responsibility: User data persistence"""

    def create(self, user: User) -> User:
        # Database operations only
        pass

    def find_by_id(self, user_id: int) -> User | None:
        pass


class EmailService:
    """Single responsibility: Email operations"""

    def send_welcome_email(self, user: User) -> None:
        # Email logic only
        pass


class AuditLogger:
    """Single responsibility: Audit logging"""

    def log_user_created(self, user: User) -> None:
        # Logging logic only
        pass


class UserService:
    """Orchestrates user creation workflow"""

    def __init__(
        self,
        repository: UserRepository,
        email_service: EmailService,
        logger: AuditLogger,
    ) -> None:
        self.repository = repository
        self.email_service = email_service
        self.logger = logger

    def register_user(self, name: str, email: str) -> User:
        user = User(id=0, name=name, email=email, created_at=datetime.now())
        created_user = self.repository.create(user)
        self.email_service.send_welcome_email(created_user)
        self.logger.log_user_created(created_user)
        return created_user
```

---

### O - Open/Closed Principle (OCP)

**Definition**: Software entities should be open for extension but closed for
modification.

**Rationale**:

-   Protects stable, tested code from changes
-   Enables adding functionality without breaking existing code
-   Reduces regression risk
-   Promotes plugin architectures

**Python Implementation**:

```python
from abc import ABC, abstractmethod
from typing import Protocol
from decimal import Decimal


# ✅ Strategy Pattern implements OCP
class PricingStrategy(Protocol):
    """Protocol defining pricing behavior"""

    def calculate_price(self, base_price: Decimal) -> Decimal: ...


class RegularPricing:
    """Standard pricing without discounts"""

    def calculate_price(self, base_price: Decimal) -> Decimal:
        return base_price


class SeasonalDiscountPricing:
    """Seasonal discount pricing"""

    def __init__(self, discount_percent: Decimal) -> None:
        self.discount_percent = discount_percent

    def calculate_price(self, base_price: Decimal) -> Decimal:
        return base_price * (Decimal("1.0") - self.discount_percent / 100)


class BulkPurchasePricing:
    """Volume-based pricing"""

    def __init__(self, quantity: int, bulk_discount: Decimal) -> None:
        self.quantity = quantity
        self.bulk_discount = bulk_discount

    def calculate_price(self, base_price: Decimal) -> Decimal:
        if self.quantity >= 10:
            return base_price * (Decimal("1.0") - self.bulk_discount / 100)
        return base_price


class Product:
    """Product with extensible pricing"""

    def __init__(
        self,
        name: str,
        base_price: Decimal,
        pricing_strategy: PricingStrategy,
    ) -> None:
        self.name = name
        self.base_price = base_price
        self.pricing_strategy = pricing_strategy

    def get_price(self) -> Decimal:
        """Calculate price using injected strategy"""
        return self.pricing_strategy.calculate_price(self.base_price)

    def set_pricing_strategy(self, strategy: PricingStrategy) -> None:
        """Change pricing strategy at runtime"""
        self.pricing_strategy = strategy


# Usage - extending without modifying existing code
product = Product(
    name="Widget",
    base_price=Decimal("100.00"),
    pricing_strategy=RegularPricing(),
)

# Switch to seasonal pricing
product.set_pricing_strategy(SeasonalDiscountPricing(discount_percent=Decimal("15")))

# Add new pricing strategy without changing Product class
class LoyaltyPricing:
    def __init__(self, loyalty_level: int) -> None:
        self.loyalty_level = loyalty_level

    def calculate_price(self, base_price: Decimal) -> Decimal:
        discount = Decimal(str(self.loyalty_level * 2))
        return base_price * (Decimal("1.0") - discount / 100)


product.set_pricing_strategy(LoyaltyPricing(loyalty_level=5))
```

---

### L - Liskov Substitution Principle (LSP)

**Definition**: Objects of a superclass should be replaceable with objects of
its subclasses without breaking the application.

**Rationale**:

-   Ensures inheritance hierarchies are logically consistent
-   Prevents subtle bugs from type substitution
-   Enables polymorphism without surprises
-   Guarantees behavioral compatibility

**Python Implementation**:

```python
from abc import ABC, abstractmethod
from typing import Protocol


# ❌ VIOLATION: Square violates LSP
class Rectangle:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height

    def set_width(self, width: float) -> None:
        self.width = width

    def set_height(self, height: float) -> None:
        self.height = height

    def area(self) -> float:
        return self.width * self.height


class Square(Rectangle):
    """LSP violation: changing width also changes height"""

    def set_width(self, width: float) -> None:
        self.width = width
        self.height = width  # Violates Rectangle's expected behavior

    def set_height(self, height: float) -> None:
        self.width = height
        self.height = height


def process_rectangle(rect: Rectangle) -> None:
    """This function expects Rectangle behavior"""
    rect.set_width(5)
    rect.set_height(4)
    assert rect.area() == 20  # Fails for Square!


# ✅ CORRECT: Use composition or separate hierarchies
class Shape(Protocol):
    """Protocol for all shapes"""

    def area(self) -> float: ...


class Rectangle:
    def __init__(self, width: float, height: float) -> None:
        self._width = width
        self._height = height

    @property
    def width(self) -> float:
        return self._width

    @property
    def height(self) -> float:
        return self._height

    def area(self) -> float:
        return self._width * self._height


class Square:
    """Independent implementation, not inheriting from Rectangle"""

    def __init__(self, side: float) -> None:
        self._side = side

    @property
    def side(self) -> float:
        return self._side

    def area(self) -> float:
        return self._side * self._side


def calculate_total_area(shapes: list[Shape]) -> float:
    """Works with any Shape, respects LSP"""
    return sum(shape.area() for shape in shapes)
```

---

### I - Interface Segregation Principle (ISP)

**Definition**: Clients should not be forced to depend on interfaces they don't
use.

**Rationale**:

-   Prevents fat interfaces with unnecessary methods
-   Reduces coupling between components
-   Improves code clarity and maintainability
-   Facilitates independent evolution of interfaces

**Python Implementation**:

```python
from typing import Protocol
from abc import ABC, abstractmethod


# ❌ VIOLATION: Fat interface forces implementations to define unused methods
class Worker(ABC):
    @abstractmethod
    def work(self) -> None:
        pass

    @abstractmethod
    def eat_lunch(self) -> None:
        pass

    @abstractmethod
    def get_salary(self) -> float:
        pass


class HumanWorker(Worker):
    def work(self) -> None:
        print("Human working")

    def eat_lunch(self) -> None:
        print("Human eating lunch")

    def get_salary(self) -> float:
        return 50000.0


class RobotWorker(Worker):
    def work(self) -> None:
        print("Robot working")

    def eat_lunch(self) -> None:
        # Robots don't eat! Forced to implement unused method
        raise NotImplementedError("Robots don't eat")

    def get_salary(self) -> float:
        # Robots don't get paid! Another unused method
        raise NotImplementedError("Robots don't get salaries")


# ✅ CORRECT: Segregated interfaces
class Workable(Protocol):
    """Interface for entities that can work"""

    def work(self) -> None: ...


class Feedable(Protocol):
    """Interface for entities that need feeding"""

    def eat_lunch(self) -> None: ...


class Payable(Protocol):
    """Interface for entities that receive payment"""

    def get_salary(self) -> float: ...


class HumanWorker:
    """Implements all three interfaces"""

    def work(self) -> None:
        print("Human working")

    def eat_lunch(self) -> None:
        print("Human eating lunch")

    def get_salary(self) -> float:
        return 50000.0


class RobotWorker:
    """Only implements Workable - no forced methods"""

    def work(self) -> None:
        print("Robot working")


class WorkManager:
    """Depends only on Workable interface"""

    def manage_work(self, worker: Workable) -> None:
        worker.work()


class PayrollManager:
    """Depends only on Payable interface"""

    def process_payroll(self, employee: Payable) -> None:
        salary = employee.get_salary()
        print(f"Processing salary: ${salary}")


# Usage demonstrates proper segregation
def coordinate_workforce(
    workers: list[Workable],
    employees: list[Payable],
    hungry_workers: list[Feedable],
) -> None:
    """Each function receives only the interface it needs"""

    work_mgr = WorkManager()
    for worker in workers:
        work_mgr.manage_work(worker)

    payroll_mgr = PayrollManager()
    for employee in employees:
        payroll_mgr.process_payroll(employee)

    for worker in hungry_workers:
        worker.eat_lunch()
```

---

### D - Dependency Inversion Principle (DIP)

**Definition**: High-level modules should not depend on low-level modules. Both
should depend on abstractions.

**Rationale**:

-   Decouples high-level business logic from implementation details
-   Enables easy swapping of implementations
-   Facilitates testing with mock objects
-   Supports plugin architectures

**Python Implementation**:

```python
from typing import Protocol
from abc import ABC, abstractmethod


# ❌ VIOLATION: High-level module depends on low-level concrete class
class MySQLDatabase:
    def save(self, data: str) -> None:
        print(f"Saving to MySQL: {data}")


class UserService:
    """High-level module directly depends on MySQLDatabase"""

    def __init__(self) -> None:
        self.database = MySQLDatabase()  # Tight coupling!

    def create_user(self, username: str) -> None:
        self.database.save(username)
        # Cannot switch to PostgreSQL without modifying this class


# ✅ CORRECT: Both depend on abstraction
class Database(Protocol):
    """Abstract interface for database operations"""

    def save(self, data: str) -> None: ...

    def find(self, query: str) -> list[str]: ...


class MySQLDatabase:
    """Low-level module implements abstraction"""

    def save(self, data: str) -> None:
        print(f"Saving to MySQL: {data}")

    def find(self, query: str) -> list[str]:
        print(f"MySQL query: {query}")
        return []


class PostgreSQLDatabase:
    """Alternative implementation of the same abstraction"""

    def save(self, data: str) -> None:
        print(f"Saving to PostgreSQL: {data}")

    def find(self, query: str) -> list[str]:
        print(f"PostgreSQL query: {query}")
        return []


class RedisDatabase:
    """Another alternative implementation"""

    def save(self, data: str) -> None:
        print(f"Caching in Redis: {data}")

    def find(self, query: str) -> list[str]:
        print(f"Redis lookup: {query}")
        return []


class UserService:
    """High-level module depends on abstraction"""

    def __init__(self, database: Database) -> None:
        self.database = database  # Dependency injected!

    def create_user(self, username: str) -> None:
        self.database.save(username)

    def find_users(self, criteria: str) -> list[str]:
        return self.database.find(criteria)


# Factory pattern for creating the right implementation
class DatabaseFactory:
    @staticmethod
    def create(db_type: str) -> Database:
        if db_type == "mysql":
            return MySQLDatabase()
        elif db_type == "postgresql":
            return PostgreSQLDatabase()
        elif db_type == "redis":
            return RedisDatabase()
        else:
            raise ValueError(f"Unknown database type: {db_type}")


# Usage - swappable implementations
mysql_service = UserService(DatabaseFactory.create("mysql"))
postgres_service = UserService(DatabaseFactory.create("postgresql"))
redis_service = UserService(DatabaseFactory.create("redis"))

# All services work identically, different implementations
mysql_service.create_user("alice")
postgres_service.create_user("bob")
redis_service.create_user("charlie")
```

---

## Creational Patterns

Creational patterns abstract the instantiation process, making systems
independent of how objects are created, composed, and represented.

### 1. Factory Method Pattern

**Category**: Creational

**Intent**: Define an interface for creating objects, but let subclasses decide
which class to instantiate.

**Problem**:

-   Direct object creation couples code to specific classes
-   Adding new product types requires modifying existing code
-   Violates Open/Closed Principle

**Solution**:

-   Define a factory method that returns objects of a common interface
-   Let subclasses override the factory method to create specific types
-   Decouple object creation from business logic

**When to Use**:

-   When a class can't anticipate the type of objects it must create
-   When you want to delegate instantiation to subclasses
-   When you need to provide hooks for extending object creation

**Structure**:

```
┌─────────────────────┐
│     Creator         │
├─────────────────────┤
│ + factory_method() │◄──────┐
│ + some_operation() │       │ Creates
└─────────────────────┘       │
         △                     │
         │                     │
         │                     ▼
┌────────┴─────────┐    ┌─────────────┐
│ ConcreteCreatorA │    │   Product   │
├──────────────────┤    └─────────────┘
│ + factory_method()│          △
└──────────────────┘          │
         △                     │
         │                     │
┌────────┴─────────┐    ┌─────┴────────┐
│ ConcreteCreatorB │    │ ConcreteProduct│
├──────────────────┤    └──────────────┘
│ + factory_method()│
└──────────────────┘
```

**Python Implementation**:

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Protocol
from dataclasses import dataclass
from decimal import Decimal


# Product interface
class PaymentProcessor(Protocol):
    """Abstract payment processor interface"""

    def process_payment(self, amount: Decimal) -> PaymentResult: ...

    def refund(self, transaction_id: str, amount: Decimal) -> PaymentResult: ...


@dataclass
class PaymentResult:
    success: bool
    transaction_id: str
    message: str


# Concrete Products
class StripePaymentProcessor:
    """Stripe payment implementation"""

    def process_payment(self, amount: Decimal) -> PaymentResult:
        # Stripe-specific API calls
        return PaymentResult(
            success=True,
            transaction_id="stripe_tx_123",
            message=f"Stripe processed ${amount}",
        )

    def refund(self, transaction_id: str, amount: Decimal) -> PaymentResult:
        return PaymentResult(
            success=True,
            transaction_id=transaction_id,
            message=f"Stripe refunded ${amount}",
        )


class PayPalPaymentProcessor:
    """PayPal payment implementation"""

    def process_payment(self, amount: Decimal) -> PaymentResult:
        # PayPal-specific API calls
        return PaymentResult(
            success=True,
            transaction_id="paypal_tx_456",
            message=f"PayPal processed ${amount}",
        )

    def refund(self, transaction_id: str, amount: Decimal) -> PaymentResult:
        return PaymentResult(
            success=True,
            transaction_id=transaction_id,
            message=f"PayPal refunded ${amount}",
        )


class CryptoPaymentProcessor:
    """Cryptocurrency payment implementation"""

    def process_payment(self, amount: Decimal) -> PaymentResult:
        # Blockchain API calls
        return PaymentResult(
            success=True,
            transaction_id="crypto_tx_789",
            message=f"Crypto processed ${amount}",
        )

    def refund(self, transaction_id: str, amount: Decimal) -> PaymentResult:
        return PaymentResult(
            success=True,
            transaction_id=transaction_id,
            message=f"Crypto refunded ${amount}",
        )


# Creator (Abstract Factory)
class PaymentService(ABC):
    """Abstract payment service with factory method"""

    @abstractmethod
    def create_processor(self) -> PaymentProcessor:
        """Factory method to be overridden by subclasses"""
        pass

    def execute_payment(self, amount: Decimal) -> PaymentResult:
        """Template method using factory method"""
        processor = self.create_processor()
        result = processor.process_payment(amount)
        self._log_transaction(result)
        return result

    def execute_refund(self, transaction_id: str, amount: Decimal) -> PaymentResult:
        processor = self.create_processor()
        return processor.refund(transaction_id, amount)

    def _log_transaction(self, result: PaymentResult) -> None:
        print(f"Transaction logged: {result.transaction_id}")


# Concrete Creators
class StripePaymentService(PaymentService):
    """Stripe-specific payment service"""

    def create_processor(self) -> PaymentProcessor:
        return StripePaymentProcessor()


class PayPalPaymentService(PaymentService):
    """PayPal-specific payment service"""

    def create_processor(self) -> PaymentProcessor:
        return PayPalPaymentProcessor()


class CryptoPaymentService(PaymentService):
    """Cryptocurrency payment service"""

    def create_processor(self) -> PaymentProcessor:
        return CryptoPaymentProcessor()


# Usage
def process_customer_payment(service: PaymentService, amount: Decimal) -> None:
    """Client code works with factory, not concrete classes"""
    result = service.execute_payment(amount)
    if result.success:
        print(f"✓ Payment successful: {result.message}")
    else:
        print(f"✗ Payment failed: {result.message}")


# Different payment services can be used interchangeably
stripe_service = StripePaymentService()
paypal_service = PayPalPaymentService()
crypto_service = CryptoPaymentService()

process_customer_payment(stripe_service, Decimal("99.99"))
process_customer_payment(paypal_service, Decimal("149.99"))
process_customer_payment(crypto_service, Decimal("0.005"))
```

**Real-World Use Cases**:

-   Payment gateway abstraction (Stripe, PayPal, Square)
-   Database connection factories (MySQL, PostgreSQL, MongoDB)
-   UI framework widget creation (web, mobile, desktop)
-   Document parsing (PDF, Word, Excel)
-   Notification delivery (email, SMS, push)

**Advantages**:

-   ✅ Adheres to Open/Closed Principle (extend without modifying)
-   ✅ Adheres to Single Responsibility Principle (separates creation from use)
-   ✅ Loose coupling between creator and concrete products
-   ✅ Easy to add new product types
-   ✅ Centralizes product creation logic

**Disadvantages**:

-   ❌ Can introduce unnecessary complexity for simple cases
-   ❌ Requires creating many subclasses
-   ❌ May be overkill if product variations are minimal

**Related Patterns**:

-   **Abstract Factory**: Factory Method is often used within Abstract Factory
-   **Template Method**: Factory Method is a specialization of Template Method
-   **Prototype**: Can be alternative to Factory Method

---

### 2. Abstract Factory Pattern

**Category**: Creational

**Intent**: Provide an interface for creating families of related or dependent
objects without specifying their concrete classes.

**Problem**:

-   Need to create multiple related objects that should work together
-   Want to ensure consistency among products
-   Need to support multiple product families (themes, platforms)

**Solution**:

-   Define abstract factory interface with methods for creating each product
-   Implement concrete factories for each product family
-   Products from one factory are designed to work together

**When to Use**:

-   System should be independent of how products are created
-   System needs to work with multiple families of related products
-   Want to enforce constraints that products must be used together
-   Need to provide a library of products revealing only interfaces

**Structure**:

```
┌──────────────────────┐
│  AbstractFactory     │
├──────────────────────┤
│ + createProductA()   │
│ + createProductB()   │
└──────────────────────┘
         △
         │
    ┌────┴────┐
    │         │
┌───┴─────────┴──┐  ┌────────────────┐
│ ConcreteFactory1│  │ConcreteFactory2│
├─────────────────┤  ├────────────────┤
│ + createProductA()│ │+ createProductA()│
│ + createProductB()│ │+ createProductB()│
└─────────────────┘  └────────────────┘
    │      │             │      │
    │      │             │      │
    ▼      ▼             ▼      ▼
ProductA1 ProductB1  ProductA2 ProductB2
```

**Python Implementation**:

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Protocol
from dataclasses import dataclass


# Abstract Products
class Button(Protocol):
    """Abstract button interface"""

    def render(self) -> str: ...

    def on_click(self) -> None: ...


class TextField(Protocol):
    """Abstract text field interface"""

    def render(self) -> str: ...

    def get_value(self) -> str: ...


class Checkbox(Protocol):
    """Abstract checkbox interface"""

    def render(self) -> str: ...

    def is_checked(self) -> bool: ...


# Concrete Products - Windows Family
class WindowsButton:
    def render(self) -> str:
        return "🔲 Windows Button"

    def on_click(self) -> None:
        print("Windows button clicked with mouse")


class WindowsTextField:
    def __init__(self) -> None:
        self._value = ""

    def render(self) -> str:
        return f"📝 Windows TextField: {self._value}"

    def get_value(self) -> str:
        return self._value


class WindowsCheckbox:
    def __init__(self) -> None:
        self._checked = False

    def render(self) -> str:
        state = "☑" if self._checked else "☐"
        return f"{state} Windows Checkbox"

    def is_checked(self) -> bool:
        return self._checked


# Concrete Products - macOS Family
class MacOSButton:
    def render(self) -> str:
        return "🔘 macOS Button"

    def on_click(self) -> None:
        print("macOS button clicked with trackpad")


class MacOSTextField:
    def __init__(self) -> None:
        self._value = ""

    def render(self) -> str:
        return f"✏️  macOS TextField: {self._value}"

    def get_value(self) -> str:
        return self._value


class MacOSCheckbox:
    def __init__(self) -> None:
        self._checked = False

    def render(self) -> str:
        state = "✓" if self._checked else "○"
        return f"{state} macOS Checkbox"

    def is_checked(self) -> bool:
        return self._checked


# Concrete Products - Web Family
class WebButton:
    def render(self) -> str:
        return '<button class="btn">Click Me</button>'

    def on_click(self) -> None:
        print("Web button clicked in browser")


class WebTextField:
    def __init__(self) -> None:
        self._value = ""

    def render(self) -> str:
        return f'<input type="text" value="{self._value}"/>'

    def get_value(self) -> str:
        return self._value


class WebCheckbox:
    def __init__(self) -> None:
        self._checked = False

    def render(self) -> str:
        checked_attr = 'checked="checked"' if self._checked else ""
        return f'<input type="checkbox" {checked_attr}/>'

    def is_checked(self) -> bool:
        return self._checked


# Abstract Factory
class UIFactory(ABC):
    """Abstract factory for creating UI component families"""

    @abstractmethod
    def create_button(self) -> Button:
        pass

    @abstractmethod
    def create_text_field(self) -> TextField:
        pass

    @abstractmethod
    def create_checkbox(self) -> Checkbox:
        pass


# Concrete Factories
class WindowsUIFactory(UIFactory):
    """Factory for Windows UI components"""

    def create_button(self) -> Button:
        return WindowsButton()

    def create_text_field(self) -> TextField:
        return WindowsTextField()

    def create_checkbox(self) -> Checkbox:
        return WindowsCheckbox()


class MacOSUIFactory(UIFactory):
    """Factory for macOS UI components"""

    def create_button(self) -> Button:
        return MacOSButton()

    def create_text_field(self) -> TextField:
        return MacOSTextField()

    def create_checkbox(self) -> Checkbox:
        return MacOSCheckbox()


class WebUIFactory(UIFactory):
    """Factory for Web UI components"""

    def create_button(self) -> Button:
        return WebButton()

    def create_text_field(self) -> TextField:
        return WebTextField()

    def create_checkbox(self) -> Checkbox:
        return WebCheckbox()


# Client Code
class LoginForm:
    """Client that uses abstract factory"""

    def __init__(self, factory: UIFactory) -> None:
        self.factory = factory
        self.username_field = factory.create_text_field()
        self.password_field = factory.create_text_field()
        self.remember_me = factory.create_checkbox()
        self.submit_button = factory.create_button()

    def render(self) -> str:
        """Render the login form using platform-specific components"""
        components = [
            "=== Login Form ===",
            f"Username: {self.username_field.render()}",
            f"Password: {self.password_field.render()}",
            f"{self.remember_me.render()} Remember Me",
            f"Submit: {self.submit_button.render()}",
        ]
        return "\n".join(components)


# Factory Selection
class UIFactoryProvider:
    """Selects appropriate factory based on platform"""

    @staticmethod
    def get_factory(platform: str) -> UIFactory:
        factories = {
            "windows": WindowsUIFactory(),
            "macos": MacOSUIFactory(),
            "web": WebUIFactory(),
        }

        factory = factories.get(platform.lower())
        if factory is None:
            raise ValueError(f"Unknown platform: {platform}")
        return factory


# Usage
def create_application(platform: str) -> None:
    """Create application with platform-specific UI"""
    factory = UIFactoryProvider.get_factory(platform)
    login_form = LoginForm(factory)
    print(f"\n{platform.upper()} Application:")
    print(login_form.render())


# All platforms use the same client code
create_application("windows")
create_application("macos")
create_application("web")
```

**Real-World Use Cases**:

-   Cross-platform UI frameworks (Qt, wxWidgets)
-   Database access layers (different SQL dialects)
-   Cloud provider abstractions (AWS, Azure, GCP)
-   Theme systems (light mode, dark mode)
-   Internationalization (different locales)

**Advantages**:

-   ✅ Ensures product compatibility within families
-   ✅ Isolates concrete classes from client code
-   ✅ Easy to swap entire product families
-   ✅ Promotes consistency among products
-   ✅ Adheres to Open/Closed Principle

**Disadvantages**:

-   ❌ Complex to implement and maintain
-   ❌ Adding new products requires changing all factories
-   ❌ Can lead to numerous classes
-   ❌ Overkill for simple scenarios

**Related Patterns**:

-   **Factory Method**: Often implemented using Factory Methods
-   **Singleton**: Factories often implemented as Singletons
-   **Prototype**: Can be used instead of Abstract Factory

---

### 3. Builder Pattern

**Category**: Creational

**Intent**: Separate the construction of complex objects from their
representation, allowing the same construction process to create different
representations.

**Problem**:

-   Constructor with many parameters is unwieldy and error-prone
-   Need to create objects with many optional components
-   Want to construct objects step-by-step
-   Need different representations of the same construction process

**Solution**:

-   Extract object construction into separate builder classes
-   Define a director to orchestrate building steps
-   Allow incremental object construction
-   Build immutable objects safely

**When to Use**:

-   Object construction is complex with many steps
-   Need to create different representations of the same object
-   Want to construct immutable objects safely
-   Telescoping constructor anti-pattern is present

**Structure**:

```
┌─────────────┐       ┌──────────────┐
│  Director   │──────▶│   Builder    │
├─────────────┤       ├──────────────┤
│ + construct()│      │ + buildPartA()│
└─────────────┘       │ + buildPartB()│
                      │ + get_result()│
                      └──────────────┘
                            △
                            │
                   ┌────────┴────────┐
                   │                 │
        ┌──────────┴────────┐  ┌────┴─────────────┐
        │ ConcreteBuilder1  │  │ ConcreteBuilder2 │
        ├───────────────────┤  ├──────────────────┤
        │ + buildPartA()    │  │ + buildPartA()   │
        │ + buildPartB()    │  │ + buildPartB()   │
        │ + get_result()    │  │ + get_result()   │
        └───────────────────┘  └──────────────────┘
                │                      │
                ▼                      ▼
            Product1              Product2
```

**Python Implementation**:

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol
from enum import Enum
from decimal import Decimal


# Product
@dataclass
class Pizza:
    """Complex product with many optional components"""

    size: str
    crust: str
    sauce: str | None = None
    cheese: str | None = None
    toppings: list[str] = field(default_factory=list)
    is_vegan: bool = False
    is_gluten_free: bool = False
    extra_sauce: bool = False
    well_done: bool = False
    price: Decimal = Decimal("0.00")

    def __str__(self) -> str:
        parts = [f"{self.size} pizza with {self.crust} crust"]

        if self.sauce:
            parts.append(f"{self.sauce} sauce")

        if self.cheese:
            parts.append(f"{self.cheese} cheese")

        if self.toppings:
            parts.append(f"toppings: {', '.join(self.toppings)}")

        modifiers = []
        if self.is_vegan:
            modifiers.append("vegan")
        if self.is_gluten_free:
            modifiers.append("gluten-free")
        if self.extra_sauce:
            modifiers.append("extra sauce")
        if self.well_done:
            modifiers.append("well done")

        if modifiers:
            parts.append(f"({', '.join(modifiers)})")

        parts.append(f"${self.price}")

        return " | ".join(parts)


# Builder Interface
class PizzaBuilder(Protocol):
    """Abstract builder interface"""

    def set_size(self, size: str) -> PizzaBuilder: ...

    def set_crust(self, crust: str) -> PizzaBuilder: ...

    def add_sauce(self, sauce: str) -> PizzaBuilder: ...

    def add_cheese(self, cheese: str) -> PizzaBuilder: ...

    def add_topping(self, topping: str) -> PizzaBuilder: ...

    def make_vegan(self) -> PizzaBuilder: ...

    def make_gluten_free(self) -> PizzaBuilder: ...

    def add_extra_sauce(self) -> PizzaBuilder: ...

    def make_well_done(self) -> PizzaBuilder: ...

    def build(self) -> Pizza: ...


# Concrete Builder
class StandardPizzaBuilder:
    """Fluent builder for creating pizzas"""

    def __init__(self) -> None:
        self._pizza = Pizza(size="medium", crust="regular")
        self._base_price = Decimal("10.00")

    def set_size(self, size: str) -> StandardPizzaBuilder:
        self._pizza.size = size

        size_prices = {
            "small": Decimal("8.00"),
            "medium": Decimal("10.00"),
            "large": Decimal("12.00"),
            "extra-large": Decimal("15.00"),
        }
        self._base_price = size_prices.get(size, Decimal("10.00"))

        return self

    def set_crust(self, crust: str) -> StandardPizzaBuilder:
        self._pizza.crust = crust

        if crust == "thick":
            self._base_price += Decimal("1.50")
        elif crust == "stuffed":
            self._base_price += Decimal("3.00")

        return self

    def add_sauce(self, sauce: str) -> StandardPizzaBuilder:
        self._pizza.sauce = sauce
        return self

    def add_cheese(self, cheese: str) -> StandardPizzaBuilder:
        self._pizza.cheese = cheese

        if cheese == "extra":
            self._base_price += Decimal("2.00")
        elif cheese in ["vegan", "goat"]:
            self._base_price += Decimal("2.50")

        return self

    def add_topping(self, topping: str) -> StandardPizzaBuilder:
        self._pizza.toppings.append(topping)
        self._base_price += Decimal("1.50")
        return self

    def make_vegan(self) -> StandardPizzaBuilder:
        self._pizza.is_vegan = True
        return self

    def make_gluten_free(self) -> StandardPizzaBuilder:
        self._pizza.is_gluten_free = True
        self._base_price += Decimal("3.00")
        return self

    def add_extra_sauce(self) -> StandardPizzaBuilder:
        self._pizza.extra_sauce = True
        self._base_price += Decimal("0.50")
        return self

    def make_well_done(self) -> StandardPizzaBuilder:
        self._pizza.well_done = True
        return self

    def build(self) -> Pizza:
        """Finalize and return the pizza"""
        self._pizza.price = self._base_price
        return self._pizza

    def reset(self) -> None:
        """Reset builder for creating a new pizza"""
        self._pizza = Pizza(size="medium", crust="regular")
        self._base_price = Decimal("10.00")


# Director (Optional - encapsulates common construction sequences)
class PizzaDirector:
    """Orchestrates common pizza recipes"""

    def __init__(self, builder: PizzaBuilder) -> None:
        self.builder = builder

    def make_margherita(self) -> Pizza:
        """Classic Margherita pizza"""
        return (
            self.builder
            .set_size("medium")
            .set_crust("thin")
            .add_sauce("tomato")
            .add_cheese("mozzarella")
            .add_topping("basil")
            .build()
        )

    def make_pepperoni(self) -> Pizza:
        """Classic pepperoni pizza"""
        return (
            self.builder
            .set_size("large")
            .set_crust("regular")
            .add_sauce("tomato")
            .add_cheese("mozzarella")
            .add_topping("pepperoni")
            .build()
        )

    def make_vegan_supreme(self) -> Pizza:
        """Vegan pizza with multiple toppings"""
        return (
            self.builder
            .set_size("large")
            .set_crust("thin")
            .add_sauce("tomato")
            .add_cheese("vegan")
            .add_topping("mushrooms")
            .add_topping("bell peppers")
            .add_topping("onions")
            .add_topping("olives")
            .make_vegan()
            .build()
        )

    def make_gluten_free_hawaiian(self) -> Pizza:
        """Gluten-free Hawaiian pizza"""
        return (
            self.builder
            .set_size("medium")
            .set_crust("gluten-free")
            .add_sauce("tomato")
            .add_cheese("mozzarella")
            .add_topping("ham")
            .add_topping("pineapple")
            .make_gluten_free()
            .build()
        )


# Usage
def demonstrate_builder_pattern() -> None:
    """Demonstrate various ways to use the builder"""

    # Direct builder usage with fluent interface
    print("=== Custom Pizza Order ===")
    builder = StandardPizzaBuilder()
    custom_pizza = (
        builder
        .set_size("large")
        .set_crust("stuffed")
        .add_sauce("bbq")
        .add_cheese("extra")
        .add_topping("chicken")
        .add_topping("bacon")
        .add_topping("red onion")
        .add_extra_sauce()
        .make_well_done()
        .build()
    )
    print(custom_pizza)

    # Using director for common recipes
    print("\n=== Director-Created Pizzas ===")
    director = PizzaDirector(StandardPizzaBuilder())

    margherita = director.make_margherita()
    print(f"Margherita: {margherita}")

    pepperoni = director.make_pepperoni()
    print(f"Pepperoni: {pepperoni}")

    vegan = director.make_vegan_supreme()
    print(f"Vegan Supreme: {vegan}")

    gf_hawaiian = director.make_gluten_free_hawaiian()
    print(f"GF Hawaiian: {gf_hawaiian}")

    # Demonstrate builder reuse
    print("\n=== Builder Reuse ===")
    builder2 = StandardPizzaBuilder()

    simple_pizza = builder2.set_size("small").add_sauce("tomato").add_cheese("mozzarella").build()
    print(f"Simple: {simple_pizza}")

    builder2.reset()
    complex_pizza = (
        builder2
        .set_size("extra-large")
        .add_topping("sausage")
        .add_topping("peppers")
        .make_well_done()
        .build()
    )
    print(f"Complex: {complex_pizza}")


demonstrate_builder_pattern()
```

**Real-World Use Cases**:

-   SQL query builders (SQLAlchemy, Django ORM)
-   HTTP request builders (httpx, requests)
-   Configuration object construction
-   Document/report generation
-   Test data builders
-   Email/message composition

**Advantages**:

-   ✅ Construct objects step-by-step
-   ✅ Reuse construction code for different representations
-   ✅ Isolates complex construction code
-   ✅ Adheres to Single Responsibility Principle
-   ✅ Fluent interface improves readability
-   ✅ Safely builds immutable objects

**Disadvantages**:

-   ❌ Increases overall code complexity
-   ❌ Requires creating multiple new classes
-   ❌ Clients must be aware of builder existence

**Related Patterns**:

-   **Abstract Factory**: Both create complex objects, but Builder focuses on
    step-by-step construction
-   **Composite**: Builder often builds Composites
-   **Fluent Interface**: Modern builders often use fluent APIs

---

### 4. Singleton Pattern

**Category**: Creational

**Intent**: Ensure a class has only one instance and provide a global point of
access to it.

**Problem**:

-   Need exactly one instance of a class (e.g., database connection pool)
-   Want controlled access to shared resources
-   Need lazy initialization of expensive resources

**Solution**:

-   Make constructor private
-   Create static method to access the single instance
-   Lazily create instance on first access

**When to Use**:

-   Exactly one instance is required
-   Instance needs global accessibility
-   Lazy initialization is beneficial
-   Controlling access to shared resources (connection pools, caches,
    configuration)

**Structure**:

```
┌────────────────────────┐
│     Singleton          │
├────────────────────────┤
│ - instance: Singleton  │
│ - __init__() [private] │
├────────────────────────┤
│ + get_instance()       │
└────────────────────────┘
```

**Python Implementation**:

```python
from __future__ import annotations
from threading import Lock
from typing import Any


# ⚠️ Classic Singleton (Thread-Safe with Double-Checked Locking)
class DatabaseConnection:
    """
    Thread-safe singleton database connection.

    Note: In modern Python, consider using module-level instances
    or dependency injection instead of classic Singleton.
    """

    _instance: DatabaseConnection | None = None
    _lock: Lock = Lock()

    def __new__(cls) -> DatabaseConnection:
        """Control instance creation with double-checked locking"""

        if cls._instance is None:
            with cls._lock:
                # Double-check inside lock
                if cls._instance is None:
                    cls._instance = super().__new__(cls)

        return cls._instance

    def __init__(self) -> None:
        """Initialize only once"""
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self.connection_string = "postgresql://localhost:5432/mydb"
            print(f"Initializing database connection: {self.connection_string}")

    def execute_query(self, query: str) -> list[dict[str, Any]]:
        """Execute database query"""
        print(f"Executing: {query}")
        return []


# ✅ Modern Pythonic Approach: Metaclass-based Singleton
class SingletonMeta(type):
    """
    Thread-safe Singleton metaclass.

    Any class using this metaclass becomes a singleton.
    """

    _instances: dict[type, Any] = {}
    _lock: Lock = Lock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Control instance creation"""

        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance

        return cls._instances[cls]


class ConfigurationManager(metaclass=SingletonMeta):
    """Application configuration singleton"""

    def __init__(self) -> None:
        self.settings: dict[str, Any] = {}
        print("Loading configuration...")

    def get(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.settings[key] = value


# ✅ Best Practice: Module-Level Singleton
class _ConnectionPool:
    """Private connection pool implementation"""

    def __init__(self, max_connections: int = 10) -> None:
        self.max_connections = max_connections
        self.active_connections = 0
        print(f"Initializing connection pool (max: {max_connections})")

    def acquire(self) -> str:
        """Acquire a connection from the pool"""
        if self.active_connections < self.max_connections:
            self.active_connections += 1
            return f"Connection #{self.active_connections}"
        raise RuntimeError("Connection pool exhausted")

    def release(self, connection: str) -> None:
        """Release a connection back to the pool"""
        self.active_connections -= 1
        print(f"Released {connection}")


# Module-level singleton instance
connection_pool = _ConnectionPool(max_connections=20)


# ✅ Dependency Injection Alternative (Preferred in Modern Python)
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    database_url: str = "postgresql://localhost/mydb"
    redis_url: str = "redis://localhost:6379/0"
    debug: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor - effectively a singleton"""
    return Settings()


# Usage Examples
def demonstrate_singleton_patterns() -> None:
    """Demonstrate various singleton implementations"""

    print("=== Classic Singleton ===")
    db1 = DatabaseConnection()
    db2 = DatabaseConnection()
    print(f"Same instance? {db1 is db2}")  # True

    print("\n=== Metaclass Singleton ===")
    config1 = ConfigurationManager()
    config1.set("app_name", "MyApp")

    config2 = ConfigurationManager()
    print(f"Same instance? {config1 is config2}")  # True
    print(f"Shared state? {config2.get('app_name')}")  # MyApp

    print("\n=== Module-Level Singleton ===")
    conn1 = connection_pool.acquire()
    conn2 = connection_pool.acquire()
    print(f"Active connections: {connection_pool.active_connections}")

    print("\n=== Dependency Injection Singleton ===")
    settings1 = get_settings()
    settings2 = get_settings()
    print(f"Same instance? {settings1 is settings2}")  # True
    print(f"Database URL: {settings1.database_url}")


demonstrate_singleton_patterns()
```

**Real-World Use Cases**:

-   Database connection pools
-   Application configuration
-   Logger instances
-   Cache managers
-   Thread pools
-   Hardware interface access (printer spooler, file system)

**Advantages**:

-   ✅ Controlled access to single instance
-   ✅ Reduced memory footprint
-   ✅ Global access point
-   ✅ Lazy initialization possible
-   ✅ Avoids global variables

**Disadvantages**:

-   ❌ Violates Single Responsibility Principle (controls instantiation +
    business logic)
-   ❌ Makes unit testing difficult (global state)
-   ❌ Requires special treatment in multithreaded environments
-   ❌ Hides dependencies (implicit coupling)
-   ❌ Can become a God Object anti-pattern

**Modern Alternatives**:

-   **Module-level instances**: Pythonic and simple
-   **Dependency Injection**: More testable and flexible
-   **`@lru_cache`**: Functional approach to caching instances

**Related Patterns**:

-   **Abstract Factory**: Often implemented as Singleton
-   **Facade**: Often implemented as Singleton
-   **State**: State objects often Singletons

---

### 5. Prototype Pattern

**Category**: Creational

**Intent**: Specify the kinds of objects to create using a prototypical
instance, and create new objects by copying this prototype.

**Problem**:

-   Object creation is expensive (database queries, complex initialization)
-   Need to create objects with similar state
-   Want to avoid subclass explosion for object creation
-   Need to create objects at runtime based on dynamic types

**Solution**:

-   Create objects by cloning existing instances
-   Implement a clone method for deep/shallow copying
-   Maintain a registry of prototypical objects

**When to Use**:

-   Object initialization is expensive
-   Want to avoid building class hierarchies of factories
-   Need to hide complexity of creating new instances
-   Instances have only a few different combinations of state

**Structure**:

```
┌──────────────────┐
│    Prototype     │
├──────────────────┤
│ + clone()        │
└──────────────────┘
        △
        │
┌───────┴──────────┐
│                  │
┌────────────────┐ ┌────────────────┐
│ConcretePrototype1│ │ConcretePrototype2│
├────────────────┤ ├────────────────┤
│ + clone()      │ │ + clone()      │
└────────────────┘ └────────────────┘

┌──────────────────┐
│  Client          │
├──────────────────┤
│ prototype        │──────┐
├──────────────────┤      │ clones
│ + operation()    │      │
└──────────────────┘      ▼
```

**Python Implementation**:

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from copy import copy, deepcopy
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


# Prototype Interface
class Cloneable(ABC):
    """Abstract prototype interface"""

    @abstractmethod
    def clone(self) -> Cloneable:
        """Create a shallow copy"""
        pass

    @abstractmethod
    def deep_clone(self) -> Cloneable:
        """Create a deep copy"""
        pass


# Complex nested objects
@dataclass
class Address:
    street: str
    city: str
    country: str
    postal_code: str


@dataclass
class ContactInfo:
    email: str
    phone: str
    address: Address


class DocumentType(Enum):
    INVOICE = "invoice"
    QUOTE = "quote"
    RECEIPT = "receipt"


# Concrete Prototype
@dataclass
class Document(Cloneable):
    """
    Complex document that's expensive to create.

    Contains nested objects and computed fields.
    """

    doc_type: DocumentType
    template_name: str
    header: str
    footer: str
    contact_info: ContactInfo
    line_items: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def clone(self) -> Document:
        """Shallow copy - shares references to mutable objects"""
        return copy(self)

    def deep_clone(self) -> Document:
        """Deep copy - independent copy of all nested objects"""
        return deepcopy(self)

    def customize(
        self,
        header: str | None = None,
        footer: str | None = None,
        line_items: list[dict[str, Any]] | None = None,
    ) -> Document:
        """Customize cloned document"""
        if header:
            self.header = header
        if footer:
            self.footer = footer
        if line_items:
            self.line_items = line_items
        return self


# Prototype Registry
class DocumentPrototypeRegistry:
    """
    Registry of prototype documents.

    Manages a collection of pre-configured prototypes.
    """

    def __init__(self) -> None:
        self._prototypes: dict[str, Document] = {}

    def register(self, name: str, prototype: Document) -> None:
        """Register a prototype"""
        self._prototypes[name] = prototype

    def unregister(self, name: str) -> None:
        """Remove a prototype"""
        del self._prototypes[name]

    def get(self, name: str) -> Document:
        """Get a deep clone of the prototype"""
        prototype = self._prototypes.get(name)
        if prototype is None:
            raise ValueError(f"Prototype '{name}' not found")
        return prototype.deep_clone()

    def list_prototypes(self) -> list[str]:
        """List all registered prototype names"""
        return list(self._prototypes.keys())


# Factory using Prototype Pattern
class DocumentFactory:
    """Factory that uses prototypes for document creation"""

    def __init__(self) -> None:
        self.registry = DocumentPrototypeRegistry()
        self._initialize_prototypes()

    def _initialize_prototypes(self) -> None:
        """Create and register standard prototypes"""

        # Company contact info (shared across documents)
        company_contact = ContactInfo(
            email="billing@acmecorp.com",
            phone="+1-555-0100",
            address=Address(
                street="123 Business Ave",
                city="Commerce City",
                country="USA",
                postal_code="12345",
            ),
        )

        # Invoice prototype
        invoice_prototype = Document(
            doc_type=DocumentType.INVOICE,
            template_name="standard_invoice",
            header="ACME Corporation\nInvoice",
            footer="Payment due within 30 days\nThank you for your business!",
            contact_info=company_contact,
            metadata={
                "currency": "USD",
                "tax_rate": 0.08,
                "payment_terms": "Net 30",
            },
        )
        self.registry.register("invoice", invoice_prototype)

        # Quote prototype
        quote_prototype = Document(
            doc_type=DocumentType.QUOTE,
            template_name="standard_quote",
            header="ACME Corporation\nPrice Quote",
            footer="Quote valid for 30 days\nWe appreciate your interest!",
            contact_info=company_contact,
            metadata={
                "currency": "USD",
                "validity_days": 30,
            },
        )
        self.registry.register("quote", quote_prototype)

        # Receipt prototype
        receipt_prototype = Document(
            doc_type=DocumentType.RECEIPT,
            template_name="standard_receipt",
            header="ACME Corporation\nReceipt",
            footer="Thank you for your purchase!",
            contact_info=company_contact,
            metadata={
                "currency": "USD",
            },
        )
        self.registry.register("receipt", receipt_prototype)

    def create_invoice(self, line_items: list[dict[str, Any]]) -> Document:
        """Create customized invoice from prototype"""
        invoice = self.registry.get("invoice")
        invoice.line_items = line_items
        invoice.metadata["invoice_date"] = "2025-01-15"
        invoice.metadata["invoice_number"] = "INV-2025-001"
        return invoice

    def create_quote(self, line_items: list[dict[str, Any]]) -> Document:
        """Create customized quote from prototype"""
        quote = self.registry.get("quote")
        quote.line_items = line_items
        quote.metadata["quote_date"] = "2025-01-15"
        quote.metadata["quote_number"] = "QTE-2025-001"
        return quote

    def create_receipt(self, line_items: list[dict[str, Any]]) -> Document:
        """Create customized receipt from prototype"""
        receipt = self.registry.get("receipt")
        receipt.line_items = line_items
        receipt.metadata["receipt_date"] = "2025-01-15"
        receipt.metadata["receipt_number"] = "RCP-2025-001"
        return receipt


# Usage
def demonstrate_prototype_pattern() -> None:
    """Demonstrate prototype pattern usage"""

    factory = DocumentFactory()

    print("=== Available Prototypes ===")
    print(factory.registry.list_prototypes())

    print("\n=== Creating Documents from Prototypes ===")

    # Create invoice
    invoice_items = [
        {"product": "Widget A", "quantity": 10, "unit_price": 25.00},
        {"product": "Widget B", "quantity": 5, "unit_price": 50.00},
    ]
    invoice = factory.create_invoice(invoice_items)
    print(f"\nInvoice: {invoice.doc_type.value}")
    print(f"Header: {invoice.header}")
    print(f"Items: {len(invoice.line_items)}")
    print(f"Metadata: {invoice.metadata}")

    # Create quote (shares same contact info but independent copy)
    quote_items = [
        {"product": "Widget C", "quantity": 100, "unit_price": 20.00},
    ]
    quote = factory.create_quote(quote_items)
    print(f"\nQuote: {quote.doc_type.value}")
    print(f"Header: {quote.header}")
    print(f"Metadata: {quote.metadata}")

    # Demonstrate independence of clones
    print("\n=== Demonstrating Clone Independence ===")
    quote.contact_info.email = "sales@acmecorp.com"
    print(f"Quote email: {quote.contact_info.email}")
    print(f"Invoice email: {invoice.contact_info.email}")  # Unchanged

    # Shallow vs Deep copy demonstration
    print("\n=== Shallow vs Deep Copy ===")
    original = factory.registry.get("invoice")
    shallow = original.clone()
    deep = original.deep_clone()

    # Modify nested object in shallow copy
    shallow.contact_info.email = "modified@example.com"
    print(f"Original email: {original.contact_info.email}")  # Modified! (shared reference)
    print(f"Shallow email: {shallow.contact_info.email}")    # Modified
    print(f"Deep email: {deep.contact_info.email}")          # Unchanged (independent copy)


demonstrate_prototype_pattern()
```

**Real-World Use Cases**:

-   Document templates and form generation
-   Game object spawning (enemies, items)
-   Configuration presets
-   Database record cloning
-   UI component templates
-   Machine learning model snapshots

**Advantages**:

-   ✅ Reduces object creation cost
-   ✅ Avoids subclass explosion
-   ✅ Hides complexity of creating new instances
-   ✅ Allows adding/removing products at runtime
-   ✅ Specifies new objects by varying values

**Disadvantages**:

-   ❌ Cloning complex objects with circular references can be tricky
-   ❌ Deep copying can be expensive
-   ❌ Requires implementing clone method for each class
-   ❌ Can be confusing when to use shallow vs deep copy

**Related Patterns**:

-   **Abstract Factory**: Can use Prototype internally
-   **Composite**: Often needs Prototype for cloning trees
-   **Decorator**: Often used with Prototype

---

## Structural Patterns

Structural patterns deal with object composition, creating relationships between
objects to form larger structures.

### 6. Adapter Pattern

**Category**: Structural

**Intent**: Convert the interface of a class into another interface clients
expect. Adapter lets classes work together that couldn't otherwise because of
incompatible interfaces.

**Problem**:

-   Need to use an existing class with an incompatible interface
-   Want to create reusable classes that cooperate with unrelated classes
-   Need to integrate third-party libraries with incompatible interfaces
-   Legacy code needs to work with new systems

**Solution**:

-   Create an adapter class that translates one interface to another
-   Wrap the incompatible object with a compatible interface
-   Use composition to delegate calls to the wrapped object

**When to Use**:

-   Want to use an existing class with an incompatible interface
-   Need to create a reusable class that cooperates with unrelated classes
-   Need to use several existing subclasses with a common interface
-   Integrating third-party libraries or legacy systems

**Structure**:

```
┌───────────┐          ┌──────────────┐
│  Client   │─────────▶│    Target    │
└───────────┘          ├──────────────┤
                       │ + request()  │
                       └──────────────┘
                              △
                              │ implements
                       ┌──────┴───────┐
                       │   Adapter    │
                       ├──────────────┤
                       │ - adaptee    │────┐
                       │ + request()  │    │ delegates
                       └──────────────┘    │
                                           ▼
                                    ┌──────────────┐
                                    │   Adaptee    │
                                    ├──────────────┤
                                    │ + specific_  │
                                    │   request()  │
                                    └──────────────┘
```

**Python Implementation**:

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Protocol
from dataclasses import dataclass
from decimal import Decimal


# Target Interface (what client expects)
class PaymentProcessor(Protocol):
    """Standard payment processor interface"""

    def process_payment(
        self,
        amount: Decimal,
        currency: str,
        customer_id: str,
    ) -> PaymentResult: ...

    def refund_payment(
        self,
        transaction_id: str,
        amount: Decimal,
    ) -> PaymentResult: ...


@dataclass
class PaymentResult:
    success: bool
    transaction_id: str
    message: str
    amount: Decimal


# Existing interface we want to adapt (Adaptee)
class LegacyPaymentGateway:
    """
    Legacy payment system with incompatible interface.

    This is existing code we cannot modify.
    """

    def make_payment(
        self,
        cents: int,
        currency_code: str,
        cust_ref: str,
    ) -> dict[str, any]:
        """
        Legacy payment method.

        - Uses cents instead of decimal amounts
        - Returns dict instead of PaymentResult
        - Uses different parameter names
        """
        print(f"Legacy gateway: Processing {cents} cents ({currency_code}) for {cust_ref}")

        return {
            "status": "success",
            "tx_id": f"legacy_tx_{cents}_{cust_ref}",
            "amount_cents": cents,
            "msg": "Payment processed via legacy system",
        }

    def reverse_payment(self, tx_ref: str, cents: int) -> dict[str, any]:
        """Legacy refund method"""
        print(f"Legacy gateway: Refunding {cents} cents for {tx_ref}")

        return {
            "status": "success",
            "tx_id": f"refund_{tx_ref}",
            "amount_cents": cents,
            "msg": "Refund processed via legacy system",
        }


# Adapter
class LegacyPaymentAdapter:
    """
    Adapter that converts PaymentProcessor interface to LegacyPaymentGateway.

    Translates between new interface and legacy implementation.
    """

    def __init__(self, legacy_gateway: LegacyPaymentGateway) -> None:
        self.legacy_gateway = legacy_gateway

    def process_payment(
        self,
        amount: Decimal,
        currency: str,
        customer_id: str,
    ) -> PaymentResult:
        """Adapt new interface to legacy method"""

        # Convert Decimal to cents
        cents = int(amount * 100)

        # Call legacy method with adapted parameters
        legacy_result = self.legacy_gateway.make_payment(
            cents=cents,
            currency_code=currency,
            cust_ref=customer_id,
        )

        # Convert legacy response to new format
        return PaymentResult(
            success=legacy_result["status"] == "success",
            transaction_id=legacy_result["tx_id"],
            message=legacy_result["msg"],
            amount=Decimal(legacy_result["amount_cents"]) / 100,
        )

    def refund_payment(
        self,
        transaction_id: str,
        amount: Decimal,
    ) -> PaymentResult:
        """Adapt refund interface to legacy method"""

        cents = int(amount * 100)

        legacy_result = self.legacy_gateway.reverse_payment(
            tx_ref=transaction_id,
            cents=cents,
        )

        return PaymentResult(
            success=legacy_result["status"] == "success",
            transaction_id=legacy_result["tx_id"],
            message=legacy_result["msg"],
            amount=Decimal(legacy_result["amount_cents"]) / 100,
        )


# Modern Payment Gateway (already compatible)
class StripePaymentGateway:
    """Modern payment gateway with compatible interface"""

    def process_payment(
        self,
        amount: Decimal,
        currency: str,
        customer_id: str,
    ) -> PaymentResult:
        print(f"Stripe: Processing ${amount} {currency} for {customer_id}")

        return PaymentResult(
            success=True,
            transaction_id=f"stripe_tx_{customer_id}",
            message="Payment processed via Stripe",
            amount=amount,
        )

    def refund_payment(
        self,
        transaction_id: str,
        amount: Decimal,
    ) -> PaymentResult:
        print(f"Stripe: Refunding ${amount} for {transaction_id}")

        return PaymentResult(
            success=True,
            transaction_id=f"refund_{transaction_id}",
            message="Refund processed via Stripe",
            amount=amount,
        )


# Client Code
class PaymentService:
    """
    Client that works with PaymentProcessor interface.

    Can use any payment processor without knowing implementation details.
    """

    def __init__(self, processor: PaymentProcessor) -> None:
        self.processor = processor

    def charge_customer(
        self,
        customer_id: str,
        amount: Decimal,
        currency: str = "USD",
    ) -> None:
        """Process customer payment"""

        result = self.processor.process_payment(
            amount=amount,
            currency=currency,
            customer_id=customer_id,
        )

        if result.success:
            print(f"✓ {result.message} | TX: {result.transaction_id}")
        else:
            print(f"✗ Payment failed: {result.message}")

    def issue_refund(
        self,
        transaction_id: str,
        amount: Decimal,
    ) -> None:
        """Process refund"""

        result = self.processor.refund_payment(
            transaction_id=transaction_id,
            amount=amount,
        )

        if result.success:
            print(f"✓ Refund issued: {result.message}")
        else:
            print(f"✗ Refund failed: {result.message}")


# Usage
def demonstrate_adapter_pattern() -> None:
    """Demonstrate adapter pattern with multiple payment processors"""

    print("=== Modern Payment Processor (No Adapter Needed) ===")
    stripe = StripePaymentGateway()
    service1 = PaymentService(stripe)
    service1.charge_customer("customer_123", Decimal("99.99"))
    service1.issue_refund("stripe_tx_customer_123", Decimal("99.99"))

    print("\n=== Legacy Payment Processor (With Adapter) ===")
    legacy_gateway = LegacyPaymentGateway()
    legacy_adapter = LegacyPaymentAdapter(legacy_gateway)
    service2 = PaymentService(legacy_adapter)
    service2.charge_customer("customer_456", Decimal("149.99"))
    service2.issue_refund("legacy_tx_14999_customer_456", Decimal("149.99"))

    print("\n=== Switching Processors Transparently ===")
    # Client code remains the same regardless of implementation
    processors = [stripe, legacy_adapter]

    for i, processor in enumerate(processors, 1):
        service = PaymentService(processor)
        print(f"\nProcessor {i}:")
        service.charge_customer(f"customer_{i}", Decimal("50.00"))


demonstrate_adapter_pattern()
```

**Real-World Use Cases**:

-   Integrating third-party libraries with different interfaces
-   Legacy system integration
-   Database driver adapters (different SQL dialects)
-   API versioning (v1 to v2 adapter)
-   File format converters
-   Cloud provider abstractions (AWS S3 to Azure Blob Storage)

**Advantages**:

-   ✅ Adheres to Single Responsibility Principle (separates interface
    conversion)
-   ✅ Adheres to Open/Closed Principle (introduce new adapters without changing
    client)
-   ✅ Reuses existing functionality
-   ✅ Increases class reusability
-   ✅ Provides compatibility between incompatible interfaces

**Disadvantages**:

-   ❌ Increases overall code complexity (new abstraction layer)
-   ❌ Can reduce performance (extra indirection)
-   ❌ Sometimes easier to just change the service class

**Related Patterns**:

-   **Bridge**: Similar structure but different intent (Bridge designed upfront,
    Adapter retrofitted)
-   **Decorator**: Changes object behavior, Adapter changes interface
-   **Proxy**: Provides same interface, Adapter provides different interface
-   **Facade**: Simplifies complex interface, Adapter makes incompatible
    interfaces work

---

### 7. Bridge Pattern

**Category**: Structural

**Intent**: Decouple an abstraction from its implementation so that the two can
vary independently.

**Problem**:

-   Inheritance creates tight coupling between abstraction and implementation
-   Need to extend both abstraction and implementation dimensions independently
-   Want to avoid a proliferation of classes from combining variations
-   Platform-specific implementations should be swappable

**Solution**:

-   Separate abstraction hierarchy from implementation hierarchy
-   Use composition instead of inheritance
-   Abstraction contains a reference to implementation interface
-   Both can evolve independently

**When to Use**:

-   Want to avoid permanent binding between abstraction and implementation
-   Both abstraction and implementation should be extensible by subclassing
-   Changes in implementation should not affect clients
-   Want to share implementation among multiple objects (hide from client)
-   Have a proliferation of classes from two-dimensional hierarchy

**Structure**:

```
┌──────────────┐           ┌──────────────────┐
│ Abstraction  │◇─────────▶│  Implementation  │
├──────────────┤           ├──────────────────┤
│ + operation()│           │ + operation_impl()│
└──────────────┘           └──────────────────┘
       △                           △
       │                           │
       │                   ┌───────┴────────┐
┌──────┴────────┐          │                │
│  Refined      │   ┌──────┴──────┐  ┌──────┴──────┐
│  Abstraction  │   │Concrete     │  │Concrete     │
├───────────────┤   │Impl A       │  │Impl B       │
│ + operation() │   └─────────────┘  └─────────────┘
└───────────────┘
```

**Python Implementation**:

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Protocol
from dataclasses import dataclass


# Implementation Interface (Platform-specific operations)
class NotificationSender(Protocol):
    """Implementation interface for sending notifications"""

    def send(self, recipient: str, message: str) -> bool: ...


# Concrete Implementations
class EmailSender:
    """Email implementation"""

    def send(self, recipient: str, message: str) -> bool:
        print(f"📧 Email to {recipient}: {message}")
        return True


class SMSSender:
    """SMS implementation"""

    def send(self, recipient: str, message: str) -> bool:
        print(f"📱 SMS to {recipient}: {message}")
        return True


class PushNotificationSender:
    """Push notification implementation"""

    def send(self, recipient: str, message: str) -> bool:
        print(f"🔔 Push to {recipient}: {message}")
        return True


class SlackSender:
    """Slack implementation"""

    def send(self, recipient: str, message: str) -> bool:
        print(f"💬 Slack to {recipient}: {message}")
        return True


# Abstraction (Business logic)
class Notification(ABC):
    """
    Abstraction for notifications.

    Contains a reference to implementation (bridge).
    """

    def __init__(self, sender: NotificationSender) -> None:
        self.sender = sender

    @abstractmethod
    def notify(self, recipient: str) -> bool:
        """Send notification (delegates to implementation)"""
        pass


# Refined Abstractions (Different notification types)
class AlertNotification(Notification):
    """Urgent alert notification"""

    def __init__(self, sender: NotificationSender, alert_level: str) -> None:
        super().__init__(sender)
        self.alert_level = alert_level

    def notify(self, recipient: str) -> bool:
        message = f"🚨 [{self.alert_level}] ALERT: System requires attention!"
        return self.sender.send(recipient, message)


class ReminderNotification(Notification):
    """Friendly reminder notification"""

    def __init__(self, sender: NotificationSender, event: str) -> None:
        super().__init__(sender)
        self.event = event

    def notify(self, recipient: str) -> bool:
        message = f"⏰ Reminder: {self.event}"
        return self.sender.send(recipient, message)


class MarketingNotification(Notification):
    """Marketing/promotional notification"""

    def __init__(self, sender: NotificationSender, offer: str) -> None:
        super().__init__(sender)
        self.offer = offer

    def notify(self, recipient: str) -> bool:
        message = f"🎁 Special Offer: {self.offer}"
        return self.sender.send(recipient, message)


class TransactionalNotification(Notification):
    """Transaction confirmation notification"""

    def __init__(
        self,
        sender: NotificationSender,
        transaction_id: str,
        amount: str,
    ) -> None:
        super().__init__(sender)
        self.transaction_id = transaction_id
        self.amount = amount

    def notify(self, recipient: str) -> bool:
        message = f"✅ Transaction {self.transaction_id}: ${self.amount} confirmed"
        return self.sender.send(recipient, message)


# Usage
def demonstrate_bridge_pattern() -> None:
    """Demonstrate bridge pattern with various combinations"""

    print("=== Bridge Pattern: Notification System ===\n")

    # Alert via different channels
    print("ALERT NOTIFICATIONS:")
    email_alert = AlertNotification(EmailSender(), "CRITICAL")
    email_alert.notify("admin@example.com")

    sms_alert = AlertNotification(SMSSender(), "HIGH")
    sms_alert.notify("+1-555-0100")

    push_alert = AlertNotification(PushNotificationSender(), "MEDIUM")
    push_alert.notify("user_device_token")

    # Reminders via different channels
    print("\nREMINDER NOTIFICATIONS:")
    email_reminder = ReminderNotification(EmailSender(), "Team meeting at 2 PM")
    email_reminder.notify("team@example.com")

    slack_reminder = ReminderNotification(SlackSender(), "Deploy to production")
    slack_reminder.notify("#dev-team")

    # Marketing via different channels
    print("\nMARKETING NOTIFICATIONS:")
    email_marketing = MarketingNotification(EmailSender(), "50% off all items!")
    email_marketing.notify("customer@example.com")

    push_marketing = MarketingNotification(
        PushNotificationSender(),
        "Flash sale: 24 hours only!",
    )
    push_marketing.notify("customer_device_123")

    # Transactional via different channels
    print("\nTRANSACTIONAL NOTIFICATIONS:")
    email_tx = TransactionalNotification(EmailSender(), "TX-2025-001", "99.99")
    email_tx.notify("buyer@example.com")

    sms_tx = TransactionalNotification(SMSSender(), "TX-2025-002", "149.50")
    sms_tx.notify("+1-555-0200")


demonstrate_bridge_pattern()
```

**Real-World Use Cases**:

-   UI frameworks supporting multiple platforms (Windows, macOS, Linux)
-   Database abstraction layers (different SQL dialects)
-   Graphics rendering (OpenGL, DirectX, Vulkan)
-   Notification systems (email, SMS, push, Slack)
-   Payment processors (different payment gateways)
-   Logging frameworks (different output targets)

**Advantages**:

-   ✅ Decouples abstraction from implementation
-   ✅ Adheres to Open/Closed Principle (extend independently)
-   ✅ Adheres to Single Responsibility Principle
-   ✅ Platform-independent code
-   ✅ Can combine abstractions and implementations at runtime

**Disadvantages**:

-   ❌ Increases complexity with additional abstraction layer
-   ❌ Might be overkill for simple scenarios

**Related Patterns**:

-   **Adapter**: Retrofits incompatible interfaces; Bridge designed upfront
-   **Abstract Factory**: Can create and configure particular bridges
-   **Strategy**: Similar structure but different intent (behavior vs structure)

---

### 8. Composite Pattern

**Category**: Structural

**Intent**: Compose objects into tree structures to represent part-whole
hierarchies. Composite lets clients treat individual objects and compositions
uniformly.

**Problem**:

-   Need to represent tree structures (hierarchies)
-   Want to treat leaf and composite objects uniformly
-   Need to work with complex nested structures
-   Don't want clients to distinguish between simple and complex elements

**Solution**:

-   Define a common interface for leaf and composite objects
-   Implement component interface for both leaves and containers
-   Containers hold child components (leaves or other containers)
-   Clients interact with all objects through common interface

**When to Use**:

-   Need to represent part-whole hierarchies
-   Want clients to ignore differences between compositions and individual
    objects
-   Need to work with tree structures (file systems, UI components,
    organizations)

**Structure**:

```
┌────────────┐
│  Client    │
└────────────┘
      │ uses
      ▼
┌────────────┐
│ Component  │
├────────────┤
│ + operation()│
└────────────┘
      △
      │ implements
   ┌──┴───┐
   │      │
┌──┴───┐  ┌┴─────────┐
│ Leaf │  │Composite │
├──────┤  ├──────────┤
│+ operation()│+ add()   │
└──────┘  │+ remove() │
          │+ operation()│
          └──────────┘
```

**Python Implementation**:

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Protocol
from dataclasses import dataclass, field
from decimal import Decimal


# Component Interface
class FileSystemComponent(Protocol):
    """Common interface for files and directories"""

    @property
    def name(self) -> str: ...

    @property
    def size(self) -> int: ...

    def display(self, indent: int = 0) -> None: ...


# Leaf
@dataclass
class File:
    """Leaf component - represents a file"""

    name: str
    _size: int
    content_type: str = "text/plain"

    @property
    def size(self) -> int:
        return self._size

    def display(self, indent: int = 0) -> None:
        prefix = "  " * indent
        print(f"{prefix}📄 {self.name} ({self._size} bytes, {self.content_type})")


# Composite
@dataclass
class Directory:
    """Composite component - represents a directory"""

    name: str
    children: list[FileSystemComponent] = field(default_factory=list)

    @property
    def size(self) -> int:
        """Calculate total size recursively"""
        return sum(child.size for child in self.children)

    def add(self, component: FileSystemComponent) -> None:
        """Add a child component"""
        self.children.append(component)

    def remove(self, component: FileSystemComponent) -> None:
        """Remove a child component"""
        self.children.remove(component)

    def get_child(self, name: str) -> FileSystemComponent | None:
        """Find child by name"""
        for child in self.children:
            if child.name == name:
                return child
        return None

    def display(self, indent: int = 0) -> None:
        """Display directory tree recursively"""
        prefix = "  " * indent
        print(f"{prefix}📁 {self.name}/ ({self.size} bytes total)")

        for child in self.children:
            child.display(indent + 1)


# More Complex Example: Product Catalog
class CatalogItem(ABC):
    """Abstract component for catalog items"""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def price(self) -> Decimal:
        pass

    @abstractmethod
    def display(self, indent: int = 0) -> None:
        pass


# Leaf: Individual Product
@dataclass
class Product(CatalogItem):
    """Leaf - individual product"""

    _name: str
    _price: Decimal
    sku: str
    stock_quantity: int = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def price(self) -> Decimal:
        return self._price

    def display(self, indent: int = 0) -> None:
        prefix = "  " * indent
        stock_status = "✓" if self.stock_quantity > 0 else "✗"
        print(
            f"{prefix}{stock_status} {self.name} - "
            f"${self.price} (SKU: {self.sku}, Stock: {self.stock_quantity})"
        )


# Composite: Product Bundle
@dataclass
class ProductBundle(CatalogItem):
    """Composite - bundle of products"""

    _name: str
    items: list[CatalogItem] = field(default_factory=list)
    discount_percent: Decimal = Decimal("0")

    @property
    def name(self) -> str:
        return self._name

    @property
    def price(self) -> Decimal:
        """Calculate bundle price with discount"""
        total = sum(item.price for item in self.items)
        discount = total * (self.discount_percent / 100)
        return total - discount

    def add(self, item: CatalogItem) -> None:
        """Add item to bundle"""
        self.items.append(item)

    def remove(self, item: CatalogItem) -> None:
        """Remove item from bundle"""
        self.items.remove(item)

    def display(self, indent: int = 0) -> None:
        """Display bundle contents recursively"""
        prefix = "  " * indent
        savings = ""
        if self.discount_percent > 0:
            original = sum(item.price for item in self.items)
            savings = f" (Save ${original - self.price:.2f}!)"

        print(f"{prefix}📦 {self.name} - ${self.price:.2f}{savings}")

        for item in self.items:
            item.display(indent + 1)


# Usage
def demonstrate_composite_pattern() -> None:
    """Demonstrate composite pattern"""

    print("=== File System Example ===\n")

    # Build file system tree
    root = Directory("root")

    # Documents directory
    docs = Directory("documents")
    docs.add(File("resume.pdf", 150_000, "application/pdf"))
    docs.add(File("cover_letter.docx", 50_000, "application/vnd.openxmlformats"))

    # Projects directory
    projects = Directory("projects")

    # Python project
    python_proj = Directory("python-app")
    python_proj.add(File("main.py", 5_000, "text/x-python"))
    python_proj.add(File("utils.py", 3_000, "text/x-python"))
    python_proj.add(File("requirements.txt", 500, "text/plain"))

    # JavaScript project
    js_proj = Directory("web-app")
    js_proj.add(File("index.html", 2_000, "text/html"))
    js_proj.add(File("app.js", 8_000, "application/javascript"))
    js_proj.add(File("styles.css", 4_000, "text/css"))

    projects.add(python_proj)
    projects.add(js_proj)

    # Media directory
    media = Directory("media")
    media.add(File("vacation.jpg", 2_000_000, "image/jpeg"))
    media.add(File("presentation.mp4", 50_000_000, "video/mp4"))

    # Build tree
    root.add(docs)
    root.add(projects)
    root.add(media)

    # Display entire tree
    root.display()

    print(f"\nTotal disk usage: {root.size:,} bytes\n")

    # Product Catalog Example
    print("=== Product Catalog Example ===\n")

    # Individual products
    laptop = Product("Gaming Laptop", Decimal("1299.99"), "LAP-001", 5)
    mouse = Product("Wireless Mouse", Decimal("29.99"), "MOU-001", 50)
    keyboard = Product("Mechanical Keyboard", Decimal("89.99"), "KEY-001", 30)
    headset = Product("Gaming Headset", Decimal("79.99"), "HEA-001", 20)
    monitor = Product("4K Monitor", Decimal("399.99"), "MON-001", 10)

    # Create bundles
    gaming_bundle = ProductBundle("Gaming Essentials Bundle", discount_percent=Decimal("10"))
    gaming_bundle.add(laptop)
    gaming_bundle.add(mouse)
    gaming_bundle.add(keyboard)
    gaming_bundle.add(headset)

    productivity_bundle = ProductBundle("Productivity Setup", discount_percent=Decimal("15"))
    productivity_bundle.add(laptop)
    productivity_bundle.add(keyboard)
    productivity_bundle.add(monitor)

    # Nested bundle
    complete_setup = ProductBundle(
        "Complete Gaming Station",
        discount_percent=Decimal("20"),
    )
    complete_setup.add(gaming_bundle)
    complete_setup.add(monitor)

    # Display catalog
    print("Individual Products:")
    laptop.display()
    mouse.display()
    keyboard.display()

    print("\nBundles:")
    gaming_bundle.display()
    print()
    productivity_bundle.display()
    print()
    complete_setup.display()


demonstrate_composite_pattern()
```

**Real-World Use Cases**:

-   File systems (directories and files)
-   UI component trees (containers and widgets)
-   Organizational hierarchies (departments and employees)
-   Product catalogs (categories and products)
-   Graphics applications (shapes and groups)
-   Menu systems (menus and menu items)

**Advantages**:

-   ✅ Treat individual objects and compositions uniformly
-   ✅ Easy to add new component types
-   ✅ Adheres to Open/Closed Principle
-   ✅ Simplifies client code (no type checking)
-   ✅ Natural representation of tree structures

**Disadvantages**:

-   ❌ Can make design overly general
-   ❌ Hard to restrict component types
-   ❌ Difficult to limit component types in containers

**Related Patterns**:

-   **Iterator**: Often used to traverse composites
-   **Visitor**: Can apply operations over composite structures
-   **Decorator**: Often used with Composite (similar structure)
-   **Chain of Responsibility**: Often combined with Composite

---

## Summary of Design Patterns Guide

This comprehensive guide has covered the foundational design patterns in detail:

### ✅ Covered Patterns

**SOLID Principles** (Complete):

-   Single Responsibility Principle
-   Open/Closed Principle
-   Liskov Substitution Principle
-   Interface Segregation Principle
-   Dependency Inversion Principle

**Creational Patterns** (Complete):

1. Factory Method - Define interface for creating objects, let subclasses decide
2. Abstract Factory - Create families of related objects
3. Builder - Construct complex objects step-by-step
4. Singleton - Ensure single instance with global access
5. Prototype - Clone objects instead of creating new ones

**Structural Patterns** (Partially Complete): 6. Adapter - Convert interfaces
for compatibility 7. Bridge - Decouple abstraction from implementation 8.
Composite - Treat individual objects and compositions uniformly

**Remaining Patterns to Add**:

-   Decorator - Add responsibilities dynamically
-   Facade - Simplify complex subsystems
-   Flyweight - Share fine-grained objects
-   Proxy - Control access to objects

**Behavioral Patterns** (To Add):

-   Strategy - Encapsulate algorithms
-   Observer - Notify dependents of changes
-   Command - Encapsulate requests as objects
-   Template Method - Define algorithm skeleton
-   Iterator - Access collection elements sequentially
-   Chain of Responsibility - Pass requests along chain
-   State - Change behavior based on state
-   Visitor - Add operations to objects without modifying them
-   Mediator - Encapsulate object interactions
-   Memento - Capture and restore object state

**Architectural Patterns** (To Add):

-   Repository Pattern
-   Unit of Work Pattern
-   CQRS (Command Query Responsibility Segregation)
-   Event Sourcing
-   Saga Pattern
-   Hexagonal Architecture (Ports and Adapters)

**Concurrency Patterns** (To Add):

-   Active Object
-   Producer-Consumer
-   Read-Write Lock
-   Thread Pool
-   Future/Promise

**Integration Patterns** (To Add):

-   API Gateway
-   Circuit Breaker
-   Retry Pattern
-   Bulkhead
-   Rate Limiter

---

## Pattern Selection Guide

### Quick Reference: When to Use Each Pattern

#### Creational Patterns Decision Tree

```
Need to create objects?
│
├─ Complex construction process?
│  └─ YES → Builder Pattern
│
├─ Need exactly one instance?
│  └─ YES → Singleton Pattern (or module-level instance)
│
├─ Don't know exact type until runtime?
│  ├─ Single product? → Factory Method
│  └─ Family of products? → Abstract Factory
│
└─ Expensive object creation?
   └─ YES → Prototype Pattern
```

#### Structural Patterns Decision Tree

```
Need to work with existing code?
│
├─ Incompatible interface?
│  └─ YES → Adapter Pattern
│
├─ Tree structure needed?
│  └─ YES → Composite Pattern
│
├─ Separate abstraction from implementation?
│  └─ YES → Bridge Pattern
│
├─ Simplify complex subsystem?
│  └─ YES → Facade Pattern (to be added)
│
├─ Add responsibilities dynamically?
│  └─ YES → Decorator Pattern (to be added)
│
├─ Control access or add behavior?
│  └─ YES → Proxy Pattern (to be added)
│
└─ Many similar objects consuming memory?
   └─ YES → Flyweight Pattern (to be added)
```

#### Behavioral Patterns Decision Tree

```
Need to change object behavior?
│
├─ Swap algorithms at runtime?
│  └─ YES → Strategy Pattern (to be added)
│
├─ Notify multiple objects of changes?
│  └─ YES → Observer Pattern (to be added)
│
├─ Encapsulate request as object?
│  └─ YES → Command Pattern (to be added)
│
├─ Define algorithm skeleton?
│  └─ YES → Template Method (to be added)
│
├─ Behavior depends on state?
│  └─ YES → State Pattern (to be added)
│
├─ Chain of handlers?
│  └─ YES → Chain of Responsibility (to be added)
│
└─ Traverse collection?
   └─ YES → Iterator Pattern (to be added)
```

---

## Pattern Combinations and Best Practices

### Common Pattern Synergies

**1. Abstract Factory + Singleton**

-   Factories often implemented as singletons
-   Ensures consistent object creation across application

**2. Composite + Iterator**

-   Traverse hierarchical structures
-   Process tree nodes uniformly

**3. Decorator + Factory Method**

-   Create decorated objects
-   Wrap objects with responsibilities dynamically

**4. Observer + Mediator**

-   Manage complex object communications
-   Centralize event handling

**5. Strategy + Factory Method**

-   Create appropriate strategies
-   Swap algorithms based on context

**6. Command + Memento**

-   Implement undo/redo functionality
-   Store command history with state snapshots

**7. Prototype + Abstract Factory**

-   Clone prototypes instead of creating from scratch
-   Combine family creation with efficient copying

**8. Bridge + Abstract Factory**

-   Create platform-specific implementations
-   Separate abstraction and implementation hierarchies

### Anti-Patterns to Avoid

**1. God Object**

-   **Problem**: Single class knows or does too much
-   **Solution**: Apply Single Responsibility Principle, extract
    responsibilities

**2. Spaghetti Code**

-   **Problem**: Tangled control flow, high coupling
-   **Solution**: Apply Strategy, State, or Command patterns

**3. Golden Hammer**

-   **Problem**: Using same pattern for every problem
-   **Solution**: Understand problem before selecting pattern

**4. Premature Optimization**

-   **Problem**: Applying complex patterns too early
-   **Solution**: Start simple, refactor when needed

**5. Cargo Cult Programming**

-   **Problem**: Using patterns without understanding
-   **Solution**: Learn pattern intent and context

**6. Big Ball of Mud**

-   **Problem**: No discernible architecture
-   **Solution**: Gradual refactoring with appropriate patterns

**7. Poltergeist**

-   **Problem**: Classes with limited responsibility and short lifecycle
-   **Solution**: Inline or eliminate unnecessary classes

**8. Singleton Overuse**

-   **Problem**: Everything is a singleton, hidden dependencies
-   **Solution**: Use dependency injection, module-level instances

---

## Implementation Checklist

### Before Implementing a Pattern

-   [ ] Clearly understand the problem
-   [ ] Consider simpler alternatives first
-   [ ] Verify pattern actually solves your problem
-   [ ] Check if pattern introduces acceptable complexity
-   [ ] Ensure team understands the pattern
-   [ ] Document pattern usage and rationale

### During Implementation

-   [ ] Follow naming conventions from pattern
-   [ ] Maintain clear separation of concerns
-   [ ] Use type hints for all interfaces
-   [ ] Implement proper error handling
-   [ ] Write comprehensive tests
-   [ ] Document deviations from standard pattern

### After Implementation

-   [ ] Review with team
-   [ ] Verify pattern solves original problem
-   [ ] Check for code smell introduction
-   [ ] Monitor performance impact
-   [ ] Update architectural documentation
-   [ ] Plan for future refactoring if needed

---

## Further Reading and Resources

### Books

-   **Design Patterns: Elements of Reusable Object-Oriented Software** (Gang of
    Four)
-   **Head First Design Patterns** (Freeman & Freeman)
-   **Refactoring to Patterns** (Joshua Kerievsky)
-   **Clean Architecture** (Robert C. Martin)
-   **Domain-Driven Design** (Eric Evans)

### Online Resources

-   [Refactoring.Guru Design Patterns](https://refactoring.guru/design-patterns)
-   [SourceMaking Design Patterns](https://sourcemaking.com/design_patterns)
-   [Python Design Patterns](https://python-patterns.guide/)

### Python-Specific

-   `typing` module documentation (Protocols, Generics)
-   `abc` module documentation (Abstract Base Classes)
-   `dataclasses` module (Modern Python data structures)
-   `functools` module (Functional programming patterns)

---

## Conclusion

Design patterns are powerful tools for solving recurring software design
problems. However, they should be applied judiciously:

**✅ DO**:

-   Understand the problem before selecting a pattern
-   Use patterns to communicate intent
-   Refactor to patterns when needed
-   Keep patterns simple and focused
-   Combine patterns thoughtfully

**❌ DON'T**:

-   Force patterns where they don't fit
-   Use patterns to show off knowledge
-   Apply all patterns at once
-   Ignore simpler solutions
-   Forget SOLID principles

**Remember**: Patterns are means to an end, not the end itself. The goal is
clean, maintainable, testable code that solves real problems.

---

## Appendix: Pattern Quick Reference

| Pattern                 | Category   | Intent                     | When to Use                       |
| ----------------------- | ---------- | -------------------------- | --------------------------------- |
| Factory Method          | Creational | Define creation interface  | Unknown types until runtime       |
| Abstract Factory        | Creational | Create object families     | Related products need consistency |
| Builder                 | Creational | Construct complex objects  | Many optional parameters          |
| Singleton               | Creational | Single instance            | Exactly one instance needed       |
| Prototype               | Creational | Clone objects              | Expensive object creation         |
| Adapter                 | Structural | Convert interfaces         | Incompatible interfaces           |
| Bridge                  | Structural | Decouple abstraction       | Independent hierarchies           |
| Composite               | Structural | Tree structures            | Part-whole hierarchies            |
| Decorator               | Structural | Add responsibilities       | Dynamic behavior addition         |
| Facade                  | Structural | Simplify subsystems        | Complex subsystem                 |
| Flyweight               | Structural | Share fine-grained objects | Memory optimization               |
| Proxy                   | Structural | Control access             | Lazy loading, access control      |
| Strategy                | Behavioral | Encapsulate algorithms     | Swappable algorithms              |
| Observer                | Behavioral | Notify dependents          | One-to-many dependencies          |
| Command                 | Behavioral | Encapsulate requests       | Undo/redo, queuing                |
| Template Method         | Behavioral | Algorithm skeleton         | Invariant algorithm steps         |
| Iterator                | Behavioral | Traverse collections       | Access elements sequentially      |
| Chain of Responsibility | Behavioral | Pass requests              | Multiple handlers                 |
| State                   | Behavioral | Behavior by state          | State-dependent behavior          |
| Visitor                 | Behavioral | Add operations             | Operations on object structure    |
| Mediator                | Behavioral | Encapsulate interactions   | Complex object communication      |
| Memento                 | Behavioral | Capture state              | Undo functionality                |

---

**Document Version**: 1.0 **Last Updated**: 2025-11-22 **Completeness**:
Foundational patterns (SOLID + 8 major patterns with full implementations)

This guide will continue to be expanded with the remaining patterns,
architectural patterns, concurrency patterns, and integration patterns. Each
addition will maintain the same depth and quality of explanation with
production-ready Python implementations.

Python FastAPI Best Practices for Web Apps (mid-2025 Edition by Jeffrey Emanuel)

-   uv and a venv targeting only python 3.13 and higher (NOT pip/poetry/conda!);
    key commands to use for this are:

    -   uv venv --python 3.13
    -   uv lock --upgrade
    -   uv sync --all-extras

-   pyproject.toml with hatchling build system; ruff for linter and mypy for
    type checking;

-   .envrc file containing `source .venv/bin/activate` (for direnv)

-   setup.sh script for automating all that stuff targeting ubuntu 25

-   All settings handled via .env file using the python-decouple library; key
    pattern to always use:

    ```python
    from decouple import Config as DecoupleConfig, RepositoryEnv
    decouple_config = DecoupleConfig(RepositoryEnv(".env"))
    POSTGRES_URL = decouple_config("DATABASE_URL")
    ```

-   fastapi for backend; automatic generation of openapi.json file so we can do
    automatic client/model generation for the separate frontend (a different
    project entirely using nextjs 15). Fastapi routes must be fully documented
    and use response models (using sqlmodel library)

-   sqlmodel/sqlalchemy for database connecting to postgres; alembic for db
    migrations. Database operations should be as efficient as possible; batch
    operations should use batch insertions where possible (same with reads); we
    should create all relevant database indexes to optimize the access patterns
    we care about, and create views where it simplifies the code and improves
    performance.

-   where it would help a lot and make sense in the overall flow of logic and be
    complementary, we should liberally use redis to speed things up.

-   typer library used for any CLI (including detailed help)

-   rich library used for all console output; really leveraging all the many
    powerful features to make everything looks extremely slick, polished,
    colorful, detailed; syntax highlighting for json, progress bars, rounded
    boxes, live panels (be careful about having more than one live panel at
    once!), etc.

-   uvicorn with uvloop for serving (to be reverse proxied from NGINX)

-   For key functionality in the app and key dependencies (e.g., postgres
    database, redis, elastic search, openai API, etc) we want to "fail fast" so
    we can address core bugs and problems, not hide issues and try to recover
    gracefully from everything.

-   Async for absolutely everything: all network activity (use httpx); all file
    access (use aiofiles); all database operations
    (sqlmodel/sqlalchemy/psycopg2); etc.

-   No unit tests or mocks; no fake/generated data; always REAL data, REAL API
    calls, and REAL, REALISTIC, ACTUAL END TO END INTEGRATION TESTS. All
    integration tests should feature super detailed and informative logging
    using the rich library.

-   Aside from the allowed ruff exceptions specified in the pyproject.toml file,
    we must always strive for ZERO ruff linter warnings/errors in the entire
    project, as well as ZERO mypy warnings/errors!

-   Network requests (especial API calls to third party services like OpenAI,
    Gemini, Anthropic, etc. should be properly rate limited with semaphores and
    use robust retry with exponential backoff and random jitter. Where possible,
    we should always try to do network requests in parallel using
    asyncio.gather() and similar design patterns (using the semaphores to
    prevent rate limiting issues automatically).

-   Usage of AI APIs should either get precise token length estimates using
    official APIs or should use the tiktoken library and the relevant tokenizer,
    never estimate using simplistic rules of thumb. We should always carefully
    track and monitor and report (using rich console output) the total costs of
    using APIs since the last startup of the app, for the most recent
    operations, etc. and track approximate run-rate of spend per day using
    extrapolation.

-   Code should be sensibly organized by functional areas using customary and
    typical code structures to make it easy and familiar to navigate. But we
    don't want extreme fragmentation and proliferation of tiny code files! It's
    about striking the right balance so we don't end up with excessively long
    and monolithic code files but so we also don't have dozens and dozens of
    code files with under 50 lines each!

Here is a sample complete pyproject.toml file showing the basic structure of an
example application:

```
# pyproject.toml - SmartEdgar.ai Configuration

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "smartedgar"
version = "0.1.0"
description = "SEC EDGAR filing downloader and processor with API"
readme = "README.md"
requires-python = ">=3.13"
license = { text = "MIT" }
authors = [
    { name = "SmartEdgar Team", email = "info@smartedgar.ai" },
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Financial and Insurance Industry",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.13",
    "Topic :: Office/Business :: Financial :: Investment",
    "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
    "Topic :: Text Processing :: Indexing",
    "Framework :: FastAPI",
    "Typing :: Typed",
]

# Core dependencies
dependencies = [
    # Web framework and server
    "fastapi >= 0.120.0",
    "uvicorn[standard] >= 0.35.0",
    # Async operations and HTTP
    "aiofiles >= 23.2.0",
    "aiohttp[speedups] >= 3.9.0",
    "aiohttp-retry >= 2.8.0",
    "aioh2 >= 0.2.0",
    "aiolimiter >= 1.1.0",
    "aiosqlite >= 0.19.0",
    "httpx[http2] >= 0.25.0",
    # Data processing and validation
    "beautifulsoup4 >= 4.12.0",
    "lxml >= 4.9.0",
    "html2text >= 2020.1.0",
    "html5lib >= 1.1",
    "pydantic >= 2.7.0",
    "python-decouple>=3.8",
    "pandas >= 2.0.0",
    # Database and ORM
    "sqlalchemy >= 2.0.41",
    "sqlmodel >= 0.0.15",
    # Text processing and NLP
    "tiktoken >= 0.5.0",
    "nltk >= 3.8.0",
    "fuzzywuzzy >= 0.18.0",
    "python-Levenshtein >= 0.20.0",
    "tenacity >= 8.2.0",
    # PDF and document processing
    "PyMuPDF >= 1.23.0",
    "PyPDF2 >= 3.0.0",
    "pdf2image >= 1.16.0",
    "Pillow >= 10.0.0",
    # Word document processing
    "python-docx >= 1.1.0",
    "mammoth >= 1.8.0",
    # PowerPoint processing
    "python-pptx >= 1.0.0",
    # RTF processing
    "striprtf >= 0.0.26",
    # Text encoding detection
    "chardet >= 5.2.0",
    # Excel and data formats
    "openpyxl >= 3.1.0",
    "xlsx2html >= 0.4.0",
    "markitdown >= 0.1.0",
    # XBRL processing
    "arelle-release >= 2.37.0",
    "tidyxbrl >= 1.2.0",
    # Caching and performance
    "redis[hiredis] >= 5.3.0",
    "cachetools >= 5.3.0",
    # Console output and CLI
    "rich>=13.7.0",
    "typer >= 0.15.0",
    "prompt_toolkit >= 3.0.0",
    "colorama >= 0.4.0",
    "termcolor >= 2.3.0",
    # Progress and utilities
    "tqdm >= 4.66.0",
    "psutil >= 5.9.0",
    "tabulate >= 0.9.0",
    "structlog >= 23.0.0",
    # Networking and scraping
    "scrapling >= 0.2.0",
    "sec-cik-mapper >= 2.1.0",
    # Machine learning and AI
    "torch >= 2.1.0",
    "transformers >= 4.35.0",
    "aisuite[all] >= 0.1.0",
    # Development and code quality
    "ruff>=0.9.0",
    "mypy >= 1.7.0",
    # Monitoring and profiling
    "yappi >= 1.4.0",
    "nvidia-ml-py3 >= 7.352.0",
    # Integration and protocols
    "mcp[cli] >= 1.5.0",
    "fastapi-mcp>=0.3.4",
    "google-genai",
    "tiktoken",
    "scipy>=1.15.3",
    "numpy>=2.2.6",
    "cryptography>=45.0.3",
    "pyyaml>=6.0.2",
    "watchdog>=6.0.0",
    "pytrends",
    "pandas-ta>=0.3.14b0",
    "scikit-learn",
    "statsmodels",
    "backtesting",
    "defusedxml",
    "ciso8601",
    "holidays",
    "matplotlib>=3.5.0",
    "seaborn>=0.11.0",
    "plotly>=5.0.0",
    "networkx",
    "authlib>=1.5.2",
    "jinja2>=3.1.6",
    "itsdangerous>=2.2.0",
    "openai",
    "elasticsearch>=9.0.0,<10.0.0",
    "pyjwt",
    "httpx-oauth",
    "arelle>=2.2",
    "alembic",
    "brotli>=1.1.0",
    "psycopg2-binary>=2.9.10",
    "sqlalchemy-utils>=0.41.2",
    "pgcli>=4.3.0",
    "asyncpg>=0.30.0",
    "user-agents>=2.2.0",
    "types-aiofiles>=24.1.0.20250606",
    "types-pyyaml>=6.0.12.20250516",
    "types-cachetools>=6.0.0.20250525",
    "orjson>=3.11.2,<4",
    "opentelemetry-instrumentation-fastapi>=0.45",
    "testcontainers>=4.0",
]

[project.optional-dependencies]
# Heavy ML dependencies (optional for basic functionality)
ml = [
    "ray >= 2.40.0",
    "flashinfer-python < 0.2.3",
]

# Interactive tools
interactive = [
    "streamlit >= 1.22.0",
    "ipython >= 8.0.0",
]

# Development dependencies
dev = [
    "pytest >= 7.4.0",
    "pytest-asyncio >= 0.21.0",
    "pytest-cov >= 4.1.0",
    "black >= 23.0.0",
    "pre-commit >= 3.0.0",
]

# All optional dependencies
all = [
    "smartedgar[ml,interactive,dev]",
]

[project.scripts]
smartedgar = "smartedgar.cli.main:main"

[project.urls]
Homepage = "https://github.com/Dicklesworthstone/smartedgar"
Repository = "https://github.com/Dicklesworthstone/smartedgar"
Issues = "https://github.com/Dicklesworthstone/smartedgar/issues"
Documentation = "https://github.com/Dicklesworthstone/smartedgar#readme"

# Configure Hatchling
[tool.hatch.build.targets.wheel]
packages = ["smartedgar"]

[tool.hatch.build.targets.sdist]
exclude = [
    "/.venv",
    "/.vscode",
    "/.git",
    "/.github",
    "/__pycache__",
    "/*.pyc",
    "/*.pyo",
    "/*.pyd",
    "*.db",
    "*.db-journal",
    "*.db-wal",
    "*.db-shm",
    ".env",
    "tests/*",
    "docs/*",
    "*.log",
    "sec_filings/*",  # Exclude downloaded filings
    "logs/*",         # Exclude logs
    "old_code/*",     # Exclude archived code
    "*.gz",           # Exclude gzipped files
    ".DS_Store",
    "cache.db",
    "fonts/*",        # Exclude font files
    "static/*.html",  # Exclude demo files
]

# --- Tool Configurations ---

[tool.ruff]
line-length = 150
target-version = "py313"

[tool.ruff.lint]
select = [
    "E",     # pycodestyle errors
    "W",     # pycodestyle warnings
    "F",     # pyflakes
    "I",     # isort
    "C4",    # flake8-comprehensions
    "B",     # flake8-bugbear
    "A",     # flake8-builtins
    "RUF",   # Ruff-specific rules
    "ASYNC", # flake8-async
    "FA",    # flake8-future-annotations
    "SIM",   # flake8-simplify
    "TID",   # flake8-tidy-imports
    "PTH",   # flake8-use-pathlib
    "RUF100", # Ruff-specific rule for unused noqa
]
extend-select = [
    "A005",   # stdlib-module-shadowing
    "A006",   # builtin-lambda-argument-shadowing
    "FURB188", # slice-to-remove-prefix-or-suffix
    "PLR1716", # boolean-chained-comparison
    "RUF032",  # decimal-from-float-literal
    "RUF033",  # post-init-default
    "RUF034",  # useless-if-else
]
ignore = [
    "E501",  # Line too long (handled by formatter)
    "E402",  # Module level import not at top of file
    "B008",  # Do not perform function calls in argument defaults
    "B007",  # Loop control variable not used
    "A003",  # Class attribute shadowing builtin (needed for pydantic)
    "SIM108", # Use ternary operator (sometimes less readable)
    "W293",  # Blank lines contain whitespace
    "RUF003", # Ambiguous characters in comments
]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
docstring-code-format = true
# 2025 style guide presets
line-ending = "lf"
skip-magic-trailing-comma = false
docstring-code-line-length = "dynamic"

[tool.ruff.lint.isort]
known-first-party = ["smartedgar"]
combine-as-imports = true

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "I001"]  # Allow assert in tests and ignore import formatting in tests
"old_code/*" = ["E", "W", "F", "I", "C4", "B", "A", "RUF"]  # Ignore archived code

# Black configuration removed - use Ruff format instead

[tool.mypy]
python_version = "3.13"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
strict_optional = true
disallow_untyped_defs = false  # Start permissive for large codebase
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true

# Performance optimizations (mypy 1.16+)
sqlite_cache = true
cache_fine_grained = true
incremental = true

[[tool.mypy.overrides]]
module = "streamlit.*"
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = [
    "--strict-markers",
    "--cov=smartedgar",
    "--cov-report=term-missing",
    "--cov-report=html",
]

[tool.coverage.run]
source = ["smartedgar"]
omit = ["tests/*", "*/conftest.py", "old_code/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]

# --- uv specific configuration ---
[tool.uv]

[dependency-groups]
dev = [
    "types-aiofiles>=24.1.0.20250606",
    "types-cachetools>=6.0.0.20250525",
    "types-python-dateutil>=2.9.0.20250516",
    "types-pyyaml>=6.0.12.20250516",
]
# uv will use the Python version from requires-python by default

# ---------------------------------------------------------------
# Installation Instructions with uv:
# ---------------------------------------------------------------
# 1. Update .python-version to use Python 3.13:
#    echo "3.13" > .python-version
#
# 2. Create virtual environment:
#    uv venv --python 3.13
#
#    # For experimental free-threaded Python (GIL-less, mid-2025):
#    uv python install 3.13.0-ft
#    uv venv .venv --python 3.13.0-ft
#
# 3. Activate virtual environment:
#    source .venv/bin/activate  # On Unix/macOS
#
# 4. Install the project:
#    uv sync                    # Basic install
#    uv sync --extra interactive # Add Streamlit/IPython
#    uv sync --extra ml         # Add ML dependencies
#    uv sync --all-extras       # Install everything
#
#    # Run tools without installing in .venv:
#    uvx ruff check .           # Linting via uvx (alias: uv tool run)
#    uvx black .                # Formatting without polluting environment
#
# 5. Set up environment variables:
#    cp .env.example .env
#    # Edit .env with your configuration
#
# 6. Initialize the system:
#    smartedgar setup
#
# 7. Run the API server:
#    smartedgar api
#    # Or: uvicorn smartedgar.api.main:app --reload
#
# 8. Other commands:
#    smartedgar --help          # Show all commands
#    smartedgar status          # Check system health
#    smartedgar download        # Download SEC filings
#    smartedgar dashboard       # Start Streamlit dashboard
# ---------------------------------------------------------------

```

## Advanced uv Features

**Leverage uv's tool functionality** to install and run linters/formatters in
isolation without polluting your app's virtual environment:

```bash
uv tool install ruff
uv tool install black
uv tool run ruff check .
```

**For monorepo projects**, uv provides workspace management capabilities. It
supports constraint dependencies and override dependencies for complex
dependency scenarios. The tool can also automatically install Python versions
including experimental JIT and free-threaded builds for Python 3.13+.

• **Workspace initialization**: Use `uv workspace init` to create a Cargo-style
workspace for multi-package monorepos, allowing shared dependencies and
coordinated builds across packages. • **Free-threaded Python**: Install GIL-less
CPython with `uv python install 3.13.0-ft` to experiment with true parallelism
in CPU-bound workloads (requires careful testing as not all packages are
compatible yet).

## Project Structure for Scale

When your application grows beyond a few modules, consider **domain-based
organization**:

```
smartedgar/
├── api/
│   ├── main.py          # FastAPI app creation
│   └── middleware.py    # Custom ASGI middleware
├── filings/
│   ├── router.py        # Domain-specific routes
│   ├── models.py        # SQLModel definitions
│   ├── service.py       # Business logic
│   └── repository.py    # Database queries
├── analytics/
│   ├── router.py
│   ├── models.py
│   └── service.py
└── common/
    └── dependencies.py  # Shared FastAPI dependencies
```

Each domain package contains its own router, models, and services, keeping
related code together while maintaining clear boundaries.

## FastAPI Performance Optimizations

**Use lifespan context manager** instead of deprecated `@app.on_event`
decorators (FastAPI 0.120.0+):

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_to_database()
    await initialize_redis_pool()
    yield
    # Shutdown
    await disconnect_database()
    await close_redis_pool()

app = FastAPI(lifespan=lifespan)
```

**Avoid BaseHTTPMiddleware** - it introduces 2-3x performance overhead under
load. Use raw ASGI middleware instead:

```python
async def timing_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

app.add_middleware(timing_middleware)
```

**Use orjson for 3x faster JSON serialization**:

```python
from fastapi.responses import ORJSONResponse

app = FastAPI(default_response_class=ORJSONResponse)
```

**Optimize response models** to reduce serialization overhead:

```python
@router.get("/items",
    response_model_exclude_unset=True,
    response_model_by_alias=False  # For internal APIs
)
async def list_items():
    # Only serializes set fields
```

**For streaming AI responses** with token counting:

```python
@router.post("/chat", response_class=StreamingResponse)
async def chat_stream(request: ChatRequest):
    async def generate():
        async for chunk in ai_client.stream(
            messages=request.messages,
            stream_options={"include_usage": True}
        ):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

## Advanced Database Patterns

**Use SQLModel's async-first patterns** (v0.0.15+):

```python
from sqlmodel import SQLModel, create_engine
from sqlmodel.ext.asyncio.session import AsyncSession, AsyncEngine
from sqlalchemy.ext.asyncio import create_async_engine

# Create async engine using SQLModel patterns
engine = AsyncEngine(create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    echo=False,
    future=True
))

# Use AsyncSession from sqlmodel.ext.asyncio
async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session
```

**Configure connection pool** for optimal async performance:

```python
from sqlalchemy.pool import AsyncAdaptedQueuePool

engine = create_async_engine(
    "postgresql+asyncpg://...",
    poolclass=AsyncAdaptedQueuePool,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    query_cache_size=1200,
    connect_args={
        "server_settings": {
            "application_name": "smartedgar",
            "jit": "off"  # Disable for OLTP workloads
        },
        "command_timeout": 60,
        # asyncpg 0.30+ defaults to statement_cache_size=256
        # Set to 0 only for dynamic SQL edge cases
        "statement_cache_size": 256,  # ~15% throughput gain
    }
)
```

**Use PostgreSQL COPY for bulk operations** achieving 100,000-500,000
rows/second:

```python
async def bulk_insert_with_copy(df: pd.DataFrame, table_name: str):
    from io import StringIO
    import csv

    buffer = StringIO()
    df.to_csv(buffer, index=False, header=False, quoting=csv.QUOTE_MINIMAL)
    buffer.seek(0)

    async with engine.raw_connection() as conn:
        async with conn.cursor() as cursor:
            await cursor.copy_expert(
                f"COPY {table_name} FROM STDIN WITH CSV",
                buffer
            )
```

**For bulk updates, use the UNNEST pattern**:

```python
async def bulk_update_filings(updates: list[dict]):
    stmt = text("""
        UPDATE filings
        SET status = updates.status
        FROM (
            SELECT * FROM UNNEST(
                :ids::integer[],
                :statuses::text[]
            ) AS t(id, status)
        ) AS updates
        WHERE filings.id = updates.id
    """)

    await session.execute(stmt, {
        "ids": [u["id"] for u in updates],
        "statuses": [u["status"] for u in updates]
    })
```

**Leverage PostgreSQL's JSON capabilities** for complex aggregations:

```python
# Return nested JSON directly from database
query = text("""
    SELECT json_build_object(
        'company', c.name,
        'filings', json_agg(
            json_build_object(
                'id', f.id,
                'type', f.type,
                'filed_at', f.filed_at
            ) ORDER BY f.filed_at DESC
        )
    ) as data
    FROM companies c
    LEFT JOIN filings f ON c.id = f.company_id
    GROUP BY c.id
""")
```

**Use AsyncAttrs mixin** for safe lazy loading in async contexts:

```python
from sqlalchemy.ext.asyncio import AsyncAttrs

class Base(AsyncAttrs, SQLModel):
    pass

class Filing(Base, table=True):
    # Now supports await filing.awaitable_attrs.company
    company: Company = Relationship(back_populates="filings")
```

## Redis Advanced Patterns

**Note: redis-py now includes async support** (aioredis is deprecated):

```python
from redis import asyncio as redis

# Connection pool with circuit breaker
class RedisClient:
    def __init__(self):
        self.pool = redis.ConnectionPool(
            host="localhost",
            max_connections=50,
            socket_keepalive=True,
            socket_keepalive_options={
                1: 1,  # TCP_KEEPIDLE
                2: 2,  # TCP_KEEPINTVL
                3: 3,  # TCP_KEEPCNT
            }
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60
        )

    async def get(self, key: str):
        if not self.circuit_breaker.is_closed:
            return None  # Fail gracefully

        try:
            async with redis.Redis(connection_pool=self.pool) as r:
                return await r.get(key)
        except redis.RedisError:
            self.circuit_breaker.record_failure()
            raise
```

**Use Lua scripts for atomic operations**:

```python
# Sliding window rate limiter with microsecond precision
rate_limit_script = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', key, 0, now - window * 1000000)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, now)
    redis.call('EXPIRE', key, window)
    return 1
else
    return 0
end
"""

async def check_rate_limit(user_id: str, limit: int = 100, window: int = 60):
    async with redis.Redis(connection_pool=redis_pool) as r:
        allowed = await r.eval(
            rate_limit_script,
            1,
            f"rate:{user_id}",
            limit,
            window,
            int(time.time() * 1000000)
        )
        return bool(allowed)
```

**Leverage Redis Streams** for event-driven architectures:

```python
async def publish_event(stream: str, event: dict):
    async with redis.Redis(connection_pool=redis_pool) as r:
        await r.xadd(stream, {"data": json.dumps(event)})

async def consume_events(stream: str, consumer_group: str):
    async with redis.Redis(connection_pool=redis_pool) as r:
        while True:
            messages = await r.xreadgroup(
                consumer_group, "consumer1", {stream: ">"}, count=10
            )
            for stream_name, stream_messages in messages:
                for msg_id, data in stream_messages:
                    yield json.loads(data[b"data"])
                    await r.xack(stream_name, consumer_group, msg_id)
```

## Rich Console Advanced Features

**Optimize Live displays** with appropriate refresh rates:

```python
from rich.live import Live
from rich.table import Table

# Use fixed console width to prevent recalculation
console = Console(width=120)

# Configure refresh rate for smooth updates without overwhelming resources
with Live(
    table,
    refresh_per_second=4,  # 4-10 FPS is optimal
    transient=True,
    console=console
) as live:
    for update in data_stream:
        table.add_row(update)
        live.update(table)
```

**Memory-efficient rendering** for large datasets:

```python
from rich.console import Console
from rich.text import Text

console = Console()

# Use pagination for large outputs
with console.pager():
    for line in massive_dataset:
        console.print(line)

# Stream output instead of building entire string
def stream_json_pretty(data: dict):
    for line in json.dumps(data, indent=2).splitlines():
        yield Text(line, style="json")

console.print(stream_json_pretty(large_json))
```

## Integration Testing Patterns

**Use TestContainers v4.0+** for real service testing (mid-2025 improvements):

-   v4.0 adds typed async APIs and parallel network mode
-   ~40% faster test suite execution on GitHub Actions
-   Module-scoped Container.start() context manager for better resource
    management

```python
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
import pytest
```

**Transaction-per-test pattern** for test isolation:

```python
@pytest.fixture
async def db_session(test_db):
    """Each test runs in a transaction that's rolled back"""
    async with test_db.begin() as transaction:
        yield test_db
        await transaction.rollback()
```

**Parallel test execution** with pytest-xdist:

```bash
# Run tests in parallel with 4 workers
pytest -n 4 --dist loadscope

# Configure in pyproject.toml
[tool.pytest.ini_options]
addopts = [
    "-n", "auto",  # Auto-detect CPU count
    "--dist", "loadscope",  # Group by module
]
```

## AI API Token Management

**Provider-specific token counting**:

```python
# OpenAI with tiktoken
encoding_gpt4o = tiktoken.encoding_for_model("gpt-4o")  # o200k_base
encoding_gpt4 = tiktoken.encoding_for_model("gpt-4")    # cl100k_base

# Anthropic (use their API)
async def count_anthropic_tokens(text: str):
    response = await anthropic_client.count_tokens(
        model="claude-3-opus",
        messages=[{"role": "user", "content": text}]
    )
    return response.usage.input_tokens

# Google Gemini (character-based)
def estimate_gemini_tokens(text: str):
    # Gemini uses ~4 characters per token on average
    return len(text) / 4
```

**Request coalescing** for similar queries:

```python
from collections import defaultdict
import asyncio

class AIRequestCoalescer:
    def __init__(self, wait_time: float = 0.1):
        self.pending = defaultdict(list)
        self.wait_time = wait_time

    async def request(self, prompt: str, callback):
        prompt_hash = hash(prompt)

        # Add to pending requests
        future = asyncio.Future()
        self.pending[prompt_hash].append(future)

        # If first request for this prompt, process after wait_time
        if len(self.pending[prompt_hash]) == 1:
            asyncio.create_task(self._process_batch(prompt_hash, prompt))

        return await future

    async def _process_batch(self, prompt_hash: str, prompt: str):
        await asyncio.sleep(self.wait_time)

        # Make single API call
        response = await ai_client.complete(prompt)

        # Resolve all waiting futures
        for future in self.pending[prompt_hash]:
            future.set_result(response)

        del self.pending[prompt_hash]
```

## Production Deployment

**Gunicorn configuration** with uvicorn workers:

```python
# gunicorn.conf.py
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000

# Restart workers after this many requests to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Graceful shutdown
graceful_timeout = 30
timeout = 60

# Access logs with timing
accesslog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
```

**Graceful shutdown handling**:

```python
import signal
import asyncio
from contextlib import asynccontextmanager

shutdown_event = asyncio.Event()

def signal_handler(signum, frame):
    shutdown_event.set()

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    # Wait for ongoing requests to complete
    await asyncio.sleep(0.5)

    # Close connections gracefully
    await redis_pool.disconnect()
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
```

**Health check endpoints** with dependency verification:

```python
from datetime import datetime

startup_time = datetime.now()

@app.get("/health/liveness")
async def liveness():
    return {
        "status": "alive",
        "uptime": (datetime.now() - startup_time).total_seconds()
    }

@app.get("/health/readiness")
async def readiness(
    db: AsyncSession = Depends(get_db),
    redis_client = Depends(get_redis)
):
    checks = {
        "database": "unknown",
        "redis": "unknown",
        "external_api": "unknown"
    }

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception:
        checks["database"] = "unhealthy"

    # Check Redis
    try:
        await redis_client.ping()
        checks["redis"] = "healthy"
    except Exception:
        checks["redis"] = "unhealthy"

    # Check external API
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get("https://api.openai.com/v1/models")
            checks["external_api"] = "healthy" if resp.status_code == 200 else "degraded"
    except Exception:
        checks["external_api"] = "unhealthy"

    all_healthy = all(v == "healthy" for v in checks.values())
    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks
    }
```

## Dockerization

**Multi-stage build** for lean production images (mid-2025 pattern):

```dockerfile
# Dockerfile
# Stage 1: Builder
FROM python:3.13-slim-bookworm as builder

# Set up the environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    UV_SYSTEM_PYTHON=true

WORKDIR /app

# Install uv
RUN pip install uv

# Copy only the dependency configuration files
COPY pyproject.toml uv.lock* ./

# Install dependencies into a virtual environment
RUN uv venv .venv && \
    source .venv/bin/activate && \
    uv sync --all-extras

# ---
# Stage 2: Final Image
FROM python:3.13-slim-bookworm as final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Create a non-root user for security
RUN addgroup --system app && adduser --system --group app
USER app

# Copy the virtual environment from the builder stage
COPY --from=builder /app/.venv ./.venv

# Copy the application source code
COPY ./smartedgar ./smartedgar
COPY gunicorn.conf.py .

# Make the virtual environment's executables available
ENV PATH="/app/.venv/bin:$PATH"

# Expose the port the app runs on
EXPOSE 8000

# The command to run the application using gunicorn
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "gunicorn.conf.py", "smartedgar.api.main:app"]
```

## CI/CD with GitHub Actions

**Automated testing and linting** for every commit:

```yaml
# .github/workflows/ci.yml
name: CI Pipeline

on:
    push:
        branches: ["main"]
    pull_request:
        branches: ["main"]

jobs:
    test-and-lint:
        runs-on: ubuntu-latest
        strategy:
            matrix:
                python-version: ["3.13", "3.14-dev"] # Pre-test Python 3.14 beta (Oct 2025)

        steps:
            - name: Checkout code
              uses: actions/checkout@v4

            - name: Set up Python ${{ matrix.python-version }}
              uses: actions/setup-python@v5
              with:
                  python-version: ${{ matrix.python-version }}

            - name: Cache uv dependencies
              uses: actions/cache@v3
              with:
                  path: |
                      ~/.cache/uv
                      .venv
                  key:
                      ${{ runner.os }}-uv-${{ matrix.python-version }}-${{
                      hashFiles('uv.lock') }}
                  restore-keys: |
                      ${{ runner.os }}-uv-${{ matrix.python-version }}-

            - name: Install uv
              run: pip install uv

            - name: Install dependencies
              run: uv sync --all-extras

            - name: Lint with Ruff
              run: uvx ruff check .

            - name: Format check with Ruff
              run: uvx ruff format . --check

            - name: Type check with MyPy
              run: uv run mypy .

            - name: Run tests with Pytest
              run: uv run pytest

            - name: Security audit
              run: uv run pip-audit
```

## Monitoring and Observability

**Structured logging with correlation IDs**:

```python
from asgi_correlation_id import CorrelationIdMiddleware
import structlog

# Add correlation ID middleware
app.add_middleware(CorrelationIdMiddleware)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# Use in routes
logger = structlog.get_logger()

@app.get("/process")
async def process_filing(filing_id: int):
    logger.info("processing_filing", filing_id=filing_id)
    # Correlation ID automatically included in all logs
```

**Prometheus metrics integration**:

```python
from prometheus_client import Counter, Histogram, Gauge
import prometheus_client

# Define metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

http_request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"]
)

active_connections = Gauge(
    "active_connections",
    "Number of active connections"
)

# Track metrics in middleware
@app.middleware("http")
async def track_metrics(request: Request, call_next):
    active_connections.inc()

    with http_request_duration.labels(
        method=request.method,
        endpoint=request.url.path
    ).time():
        response = await call_next(request)

    http_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()

    active_connections.dec()
    return response

# Expose metrics endpoint
@app.get("/metrics")
async def metrics():
    return Response(
        prometheus_client.generate_latest(),
        media_type="text/plain"
    )
```

## Security Enhancements

**Regular dependency auditing**:

```bash
# Add to your CI/CD pipeline
pip install safety
safety check

# Or use pip-audit
pip install pip-audit
pip-audit
```

**Secure headers middleware**:

```python
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.sessions import SessionMiddleware

# Security headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Trusted host validation
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["example.com", "*.example.com"]
)
```

## Type Checking Enhancements

**Mypy 1.16+ performance improvements** (2.2x faster with orjson cache):

```toml
[tool.mypy]
python_version = "3.13"
strict = true
plugins = [
    "pydantic.mypy",
    "sqlalchemy.ext.mypy.plugin"
]

# Performance optimizations
cache_fine_grained = true
incremental = true
sqlite_cache = true
```

**Find and use type stub libraries where available!**

For many popular libraries, there are already community provided type stub
libraries available from PyPi for projects that don't yet provide types directly
in the library itself. Here is a sampling of some of these:

```
    "asyncpg-stubs >=0",
    "elasticsearch-stubs",
    "pandas-stubs>=2.2.3.250527",
    "sqlalchemy2-stubs >=0",
    "types-aiofiles>=24.1.0.20250606",
    "types-beautifulsoup4>=4.12.0",
    "types-cachetools>=6.0.0.20250525",
    "types-lxml>=2024.8.7",
    "types-openpyxl>=3.1.5",
    "types-passlib>=1.7.7",
    "types-psutil>=7.0.0",
    "types-python-dateutil>=2.9.0.20250516",
    "types-python-jose>=3.5.0.20250531",
    "types-pyyaml>=6.0.12.20250516",
    "types-pytz>0",
    "types-redis>=4.6.0.20241004",
    "types-reportlab",
    "types-requests>=2.32.4.20250611",
    "types-setuptools>=80.9.0.20250529",
    "types-sqlalchemy>=1.4.53.38",
    "types-tabulate>=0.9.0",
    "types-termcolor",
    "types-tqdm>=4.67.0",
```

Wherever it is relevant and such libraries exist (you always need to search
online to verify that a proposed library actually is available under that exact
name in PyPi!), you should use them rather than try to create your own ad-hoc,
incomplete type specifications.

## Ruff 2025 Style Guide Updates

**Adopt the new Ruff 2025 style guide** (v0.9.0+) for enhanced readability:

```python
# F-string formatting - now breaks expressions intelligently
print(f"Processing {
    very_long_variable_name_that_exceeds_line_limit
} items")

# Implicit string concatenation - merges single-line strings
message = "This is a long message that continues seamlessly."

# Assertion messages - wraps message in parentheses
assert condition, (
    "Detailed error message stays together"
)
```

**Enable newly stabilized lint rules**:

```toml
[tool.ruff.lint]
extend-select = [
    "A005",   # stdlib-module-shadowing
    "A006",   # builtin-lambda-argument-shadowing
    "FURB188", # slice-to-remove-prefix-or-suffix
    "PLR1716", # boolean-chained-comparison
    "RUF032",  # decimal-from-float-literal
    "RUF033",  # post-init-default
    "RUF034",  # useless-if-else
]
```

## FastAPI Router-Level Configuration

**Reduce endpoint duplication** with router-level dependencies:

```python
# Common authentication for all endpoints in router
admin_router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_role)],
    responses={403: {"description": "Insufficient permissions"}}
)

# All routes automatically require admin role
@admin_router.get("/users")
async def list_users():
    # No need to add Depends(require_admin_role) here
    return await get_all_users()
```

## Service Layer Architecture Pattern

**Implement clean separation of concerns** beyond simple routers:

```python
# services/filing_service.py - Business logic layer
class FilingService:
    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis
        self.repository = FilingRepository(db)

    async def process_filing(self, filing_id: int) -> Filing:
        # Orchestrate complex business logic
        filing = await self.repository.get(filing_id)

        # Check cache first
        cached = await self.redis.get(f"filing:{filing_id}:processed")
        if cached:
            return Filing.parse_raw(cached)

        # Process with multiple steps
        filing = await self._validate_filing(filing)
        filing = await self._enrich_filing(filing)
        filing = await self._calculate_metrics(filing)

        # Update database and cache
        await self.repository.update(filing)
        await self.redis.setex(
            f"filing:{filing_id}:processed",
            3600,
            filing.json()
        )
        return filing

# api/endpoints/filings.py - Presentation layer
@router.post("/filings/{filing_id}/process")
async def process_filing(
    filing_id: int,
    service: FilingService = Depends(get_filing_service)
):
    # Router only handles HTTP concerns
    result = await service.process_filing(filing_id)
    return FilingResponse.from_orm(result)
```

## Advanced Async Patterns

**Structured concurrency with asyncio.TaskGroup** (Python 3.11+):

```python
import asyncio

# Replace ad-hoc gather() with TaskGroup for better error handling
async def process_many_items(items: list) -> list:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(process_item(item)) for item in items]

    # All tasks complete successfully or TaskGroup cancels all on first failure
    return [task.result() for task in tasks]

# Compare with the old pattern:
# results = await asyncio.gather(*tasks, return_exceptions=True)  # Continues even if some fail
```

**Create a utility wrapper around asyncio.Runner** for CLI entry points:

```python
# common/async_utils.py
import asyncio
from typing import Coroutine, TypeVar

T = TypeVar('T')

def run_async(coro: Coroutine[None, None, T]) -> T:
    """Run async code with proper context propagation (Python 3.13+)"""
    with asyncio.Runner() as runner:
        return runner.run(coro)

# Use in Typer CLI instead of asyncio.run()
import typer
from .common.async_utils import run_async

app = typer.Typer()

@app.command()
def process(file: str):
    result = run_async(process_file_async(file))
    typer.echo(f"Processed: {result}")
```

**Rate limiting with semaphores** for external APIs:

```python
# Limit concurrent API calls
api_semaphore = asyncio.Semaphore(10)

async def call_external_api(endpoint: str):
    async with api_semaphore:  # Automatically queues if limit reached
        async with httpx.AsyncClient() as client:
            return await client.get(f"https://api.example.com/{endpoint}")

# Process many requests without overwhelming the API
results = await asyncio.gather(*[
    call_external_api(f"item/{i}") for i in range(100)
])
```

**Graceful error handling** in concurrent operations:

```python
async def process_batch_with_failures(items: list):
    tasks = [process_item(item) for item in items]

    # Don't fail everything if one task fails
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful = []
    failed = []

    for item, result in zip(items, results):
        if isinstance(result, Exception):
            failed.append((item, str(result)))
        else:
            successful.append(result)

    logger.info(f"Processed {len(successful)} successfully, {len(failed)} failed")
    return successful, failed
```

**Integrate blocking code** safely:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Create a thread pool for blocking operations
executor = ThreadPoolExecutor(max_workers=4)

async def process_pdf(pdf_path: str):
    loop = asyncio.get_event_loop()

    # Run blocking PDF processing in thread pool
    result = await loop.run_in_executor(
        executor,
        extract_text_from_pdf,  # Blocking function
        pdf_path
    )

    return result
```

## Task Queue with arq

**Production-ready background jobs** with arq (async-native alternative to
Celery):

```python
# worker.py
from arq import Worker
from arq.connections import RedisSettings

async def send_email(ctx, user_id: int, subject: str, body: str):
    """Background task to send emails"""
    user = await get_user(user_id)
    await email_client.send(
        to=user.email,
        subject=subject,
        body=body
    )
    logger.info(f"Email sent to {user.email}")

async def generate_report(ctx, report_id: int):
    """Long-running report generation"""
    redis: Redis = ctx["redis"]

    # Update progress in Redis
    await redis.set(f"report:{report_id}:status", "processing")

    # Generate report...
    result = await create_complex_report(report_id)

    await redis.set(f"report:{report_id}:status", "completed")
    return result

# Worker configuration
class WorkerSettings:
    functions = [send_email, generate_report]
    redis_settings = RedisSettings(host="localhost", port=6379)
    max_jobs = 10
    job_timeout = 300

# api/endpoints/reports.py - Enqueue jobs
from arq import create_pool

@router.post("/reports")
async def create_report(request: ReportRequest):
    pool = await create_pool(RedisSettings())

    # Enqueue job and return immediately
    job = await pool.enqueue_job(
        "generate_report",
        report_id=request.id,
        _job_try=3  # Retry up to 3 times
    )

    return {
        "job_id": job.job_id,
        "status": "queued"
    }
```

**Run the worker**:

```bash
arq worker.WorkerSettings
```

## WebSocket + Redis Pub/Sub for Real-time Features

**Scalable WebSocket implementation** across multiple servers:

```python
from fastapi import WebSocket
import aioredis
from broadcaster import Broadcast

# Initialize broadcaster with Redis backend
broadcast = Broadcast("redis://localhost:6379")

# Use lifespan context manager instead of deprecated @app.on_event
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await broadcast.connect()
    yield
    # Shutdown
    await broadcast.disconnect()

app = FastAPI(lifespan=lifespan)

# WebSocket endpoint
@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    await websocket.accept()

    async def receive_broadcasts():
        async with broadcast.subscribe(channel) as subscriber:
            async for event in subscriber:
                await websocket.send_json(event.message)

    async def receive_websocket():
        async for data in websocket.iter_json():
            # Broadcast to all subscribers
            await broadcast.publish(channel, data)

    # Run both concurrently
    await asyncio.gather(
        receive_broadcasts(),
        receive_websocket()
    )

# Publish events from regular endpoints
@app.post("/notify/{channel}")
async def send_notification(channel: str, message: dict):
    await broadcast.publish(channel, message)
    return {"status": "sent"}
```

## OpenTelemetry Distributed Tracing

**Full observability stack with zero-instrumentation shims** (mid-2025):

Note: OpenTelemetry instrumentation shims stabilized in spring 2025. One-line
`instrument_app()` now covers FastAPI, SQLAlchemy async, redis-py, and httpx,
giving you distributed traces without custom middleware. Latency impact is <1
µs/request when the exporter batches.

```python
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure OpenTelemetry
def setup_telemetry(app: FastAPI):
    # Set up OTLP exporter (for Jaeger, Tempo, etc.)
    otlp_exporter = OTLPSpanExporter(
        endpoint="http://localhost:4317",
        insecure=True
    )

    # Configure tracer
    provider = TracerProvider()
    processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    # Auto-instrument libraries with zero LOC overhead (2025 pattern)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    SQLAlchemyInstrumentor().instrument(engine=engine)
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()

# Custom spans for business logic
tracer = trace.get_tracer(__name__)

async def process_complex_operation(data: dict):
    with tracer.start_as_current_span("process_operation") as span:
        span.set_attribute("operation.type", data["type"])
        span.set_attribute("operation.size", len(data["items"]))

        # Nested span for sub-operation
        with tracer.start_as_current_span("validate_data"):
            validated = await validate(data)

        with tracer.start_as_current_span("save_to_database"):
            result = await save(validated)
            span.set_attribute("db.rows_affected", result.rowcount)

        return result
```

## Alembic Team Collaboration Best Practices

**Prevent migration conflicts** in team environments:

```bash
# Always pull latest migrations before creating new ones
git pull origin main
alembic current  # Check current state
alembic history  # Review migration chain

# Create migration with descriptive message
alembic revision --autogenerate -m "add_filing_status_index"

# ALWAYS review autogenerated migrations
# Alembic can miss: table renames, column type changes, complex constraints
```

**Migration review checklist**:

```python
"""Add filing status index

Revision ID: abc123
Revises: def456
Create Date: 2025-01-15 10:00:00

CHECKLIST:
[ ] Reviewed autogenerated SQL
[ ] Added missing operations (renames, custom types)
[ ] Tested upgrade AND downgrade
[ ] Considered performance impact
[ ] Added concurrent index creation for large tables
"""

def upgrade():
    # Use CONCURRENTLY for zero-downtime index creation
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_filings_status ON filings(status)"
    )

def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_filings_status")
```

## Production Deployment Architecture

**Three-layer deployment pattern** explanation:

```nginx
# nginx.conf - Layer 1: Edge proxy
upstream app_servers {
    # Unix socket for same-machine communication (faster than TCP)
    server unix:/tmp/gunicorn.sock fail_timeout=0;
}

server {
    listen 80;
    listen 443 ssl http2;  # HTTP/2 support with Uvicorn 0.35.0+
    server_name api.example.com;

    # Security headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # Optimize for API traffic
    client_max_body_size 50M;
    client_body_timeout 60s;

    # Compression
    gzip on;
    gzip_types application/json;
    gzip_min_length 1000;

    location / {
        proxy_pass http://app_servers;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts for long-running requests
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
```

**systemd service** for production:

```ini
# /etc/systemd/system/smartedgar.service
[Unit]
Description=SmartEdgar API
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=smartedgar
Group=smartedgar
WorkingDirectory=/opt/smartedgar
Environment="PATH=/opt/smartedgar/.venv/bin"
ExecStart=/opt/smartedgar/.venv/bin/gunicorn \
    -c /opt/smartedgar/gunicorn.conf.py \
    smartedgar.api.main:app

# Restart policy
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

## Advanced LLM Development Patterns

**Context management for LLM-assisted coding**:

````python
class LLMContext:
    """Manage context window efficiently"""

    def __init__(self, max_tokens: int = 8000):
        self.max_tokens = max_tokens
        self.encoder = tiktoken.encoding_for_model("gpt-4")

    def build_context(
        self,
        task: str,
        relevant_code: list[str],
        error_messages: list[str] = None,
        examples: list[dict] = None
    ) -> str:
        """Build optimal context within token limits"""

        sections = []

        # Always include task
        sections.append(f"TASK: {task}")

        # Add code context
        if relevant_code:
            sections.append("RELEVANT CODE:")
            for code in relevant_code:
                sections.append(f"```python\n{code}\n```")

        # Add errors if present
        if error_messages:
            sections.append("ERRORS TO FIX:")
            sections.extend(error_messages)

        # Add examples if space allows
        if examples:
            sections.append("EXAMPLES:")
            for ex in examples:
                test_context = "\n\n".join(sections + [str(ex)])
                if self.count_tokens(test_context) < self.max_tokens:
                    sections.append(str(ex))
                else:
                    break

        return "\n\n".join(sections)

    def count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))
````

**Multi-model orchestration** with LangChain:

```python
from langchain.chat_models import ChatOpenAI, ChatAnthropic
from langchain.schema import SystemMessage, HumanMessage

class MultiModelOrchestrator:
    def __init__(self):
        self.fast_model = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0
        )
        self.smart_model = ChatAnthropic(
            model="claude-3-opus",
            temperature=0
        )
        self.code_model = ChatOpenAI(
            model="gpt-4",
            temperature=0
        )

    async def process(self, task: str) -> str:
        # Route to appropriate model based on task
        if "debug" in task or "fix" in task:
            return await self.smart_model.ainvoke([
                SystemMessage("You are an expert debugger."),
                HumanMessage(task)
            ])
        elif "code" in task or "implement" in task:
            return await self.code_model.ainvoke([
                SystemMessage("You are an expert Python developer."),
                HumanMessage(task)
            ])
        else:
            # Use fast model for simple queries
            return await self.fast_model.ainvoke([HumanMessage(task)])
```

## Documentation Workflow (mid-2025)

**Use MkDocs ≥ 1.6 with material theme** for comprehensive project
documentation:

```toml
# mkdocs.yml
site_name: SmartEdgar Documentation
theme:
  name: material
  features:
    - navigation.instant
    - navigation.tracking
    - search.suggest
    - content.code.copy
  palette:
    scheme: slate
    primary: indigo

plugins:
  - search
  - autorefs
  - mkdocstrings:
      handlers:
        python:
          options:
            show_source: true

nav:
  - Home: index.md
  - Architecture: architecture.md
  - API Reference: api.md
  - ADRs: adrs/index.md
```

**Architectural Decision Records (ADRs)** to codify technical decisions:

```markdown
# docs/adrs/001-free-threaded-python.md

# ADR-001: Experimental Free-Threaded Python Support

## Status

Experimental

## Context

Python 3.13 introduced an experimental free-threaded (GIL-less) build that
allows true parallelism for CPU-bound workloads. This could significantly
improve performance for our data processing pipelines.

## Decision

We will offer an optional free-threaded build configuration for power users who
want to experiment with improved parallelism, while maintaining the standard
build as the default.

## Consequences

-   Potential 2-4x performance improvement for CPU-bound tasks
-   Some C extensions may not be compatible
-   Requires careful testing before production use
-   Must maintain both build configurations
```

This approach ensures future contributors understand the "why" behind technical
choices and won't inadvertently reverse important decisions.

# ✨ Core Principles for Pristine Python ✨

## 1. Foundational Tooling for Quality & Safety 🛠️

| Requirement                            | Why This Is Essential                                    |
| -------------------------------------- | -------------------------------------------------------- |
| **Python 3.12 or later**               | Latest typing & pattern-matching features.               |
| **uv** (dependency manager)            | Fast, reproducible installs; native PEP 668 support.     |
| **ruff** (`ruff check`, `ruff format`) | Enforces PEP 8, auto-formats, catches code smells early. |
| **mypy + pyright** (zero errors)       | Cross-editor, CI-grade static type guarantees.           |

## 2. Impeccable Type Safety 🔒

1. **Modern union types** – use `A | B`; never import `Union` or `Optional`.
2. **Generics where appropriate**
    - Define reusable `TypeVar`s once in **`types.py`** (with correct variance).
    - Use `TypeVar`s to parameterize functions and classes.
    - Use `Generic` to parameterize classes.
    - Use `type` instead of `TypeAlias` for simple type definitions.
3. **Precisely-typed collections**

    - Prefer `tuple[str, …]` for fixed-size sequences.
    - **Almost never** `dict[str, Any]`; instead:
        - **Pydantic v2** models (`BaseModel`,
          `model_config = ConfigDict(arbitrary_types_allowed=True)`) etc

4. **No escape hatches** – remove `Any`, `# type: ignore`, and refactor until
   the checker is green.

---

## 3. Robust Configuration with Pydantic V2 ⚙️

```python
# settings.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class AppSettings(BaseSettings):
    """Validated, singleton application configuration."""

    database_url: str = Field(..., validation_alias="DB__URL")
    openai_api_key: str | None = Field(None, validation_alias="OPENAI__API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",         # or "forbid" for maximal strictness
    )

@lru_cache
def get_settings() -> AppSettings:
    """Cached settings accessor."""
    return AppSettings()
```

Why it matters:

-   **Single Source of Truth** – secrets rotate in one place.
-   **Fail-fast** – mis-configs surface at import time.

---

## 4. SOLID Architecture & Decoupled Design 🏗️

| SOLID Principle               | Concrete Action                                                 |
| ----------------------------- | --------------------------------------------------------------- |
| **S** – Single Responsibility | Keep business logic framework-agnostic; extract pure services.  |
| **O** – Open/Closed           | Use **Strategy** for swappable LLM providers or data stores.    |
| **L** – Liskov Substitution   | Program to **`Protocol`** interfaces, not concrete classes.     |
| **I** – Interface Segregation | Split “kitchen-sink” interfaces into cohesive protocols.        |
| **D** – Dependency Injection  | Constructor injection + factories; avoid globals except config. |

### Key Patterns

-   **Factory / Builder** – hide construction detail of complex objects.
-   **Observer (Pub/Sub)** – domain events without tight coupling (start
    in-memory).
-   **Decorator** – add concerns (retry, logging, caching) without touching core
    logic.
-   **Adapter** – convert between incompatible interfaces.
-   **Bridge** – separate abstraction from implementation.
-   **Composite** – compose objects into tree structures.
-   **Facade** – provide a simplified interface to a complex subsystem.
-   **Proxy** – provide a placeholder for another object.
-   **Chain of Responsibility** – pass requests along a chain of handlers.
-   **Command** – encapsulate a request as an object.
-   **Iterator** – access elements of a collection without exposing its
    underlying representation.

---

## 5. Eradicating Code Smells 🚩

-   **Long parameter lists** → consolidate into value objects (Pydantic models).
-   **Feature envy** → move behavior next to the data it needs.
-   **God classes** → split into cohesive, SRP-aligned units.

## 6. How to Use Pydantic V2

-   If validation checks can be done at the pydantic model level, do it there
    and not do it in the business logic.

## 7. Quirks

-   Do not import inside a function, import at the top of the file.
-   Minimize any dictionary usage, use Pydantic models instead.

---

---

## 📌 Final Admonition — The Elegance of a Clean Core

A **small, impeccably clean, strongly-typed core** outperforms any sprawling
system. Master your types, champion modular independence, apply proven patterns,
and remain SOLID. Only after that spotless foundation is in place should you
layer on other concerns.

## ✨ Crafting Super Elegant Python ✨

The essence of elegant Python, as your principles highlight, lies in a **small,
impeccably clean, strongly-typed core.** This means every piece of code has a
clear purpose, types are explicit and leveraged, and the overall structure is
logical and decoupled.

---

### Mastering `TypeVar` and Generics with Finesse 🧬

Generics, implemented with `TypeVar` and `typing.Generic`, are pivotal for
writing reusable and type-safe components. Their elegant application hinges on
understanding _when_ and _how_ to use them precisely.

1.  **Centralized `TypeVar` Definitions (`types.py`)**:

    -   Your principle of defining `TypeVar`s in a central `types.py` is key.
        This promotes reuse and a single source of truth for your generic type
        parameters.
    -   **Variance (`covariant`, `contravariant`, `invariant`)**:
        -   `T_co = TypeVar("T_co", covariant=True)`: Use for types that are
            "producers" or outputs. If a function returns `list[Shape]`, and
            `Circle` is a subtype of `Shape`, then `list[Circle]` can be used
            where `list[Shape]` is expected. Think read-only collections or
            return types.
        -   `T_contra = TypeVar("T_contra", contravariant=True)`: Use for types
            that are "consumers" or inputs. If a function accepts a
            `Callable[[Shape], None]`, and `Figure` is a supertype of `Shape`,
            then a `Callable[[Figure], None]` can be used. Think function
            arguments, particularly callbacks or write-only scenarios.
        -   `T = TypeVar("T")` (invariant by default): Use when a type parameter
            is both an input and an output, or when exact type matching is
            crucial. Most mutable collections fall here. For example, a
            `list[Shape]` cannot be safely interchanged with a `list[Circle]` if
            you intend to add new elements, as you might try to add a `Square`
            to a `list[Circle]`.

2.  **`TypeVar` in Functions**:

    -   Use `TypeVar`s to establish relationships between parameter types and
        return types.
    -   Example:
        `def process_item(item: T, processor: Callable[[T], R]) -> R: return processor(item)`.
        Here, `T` links the `item` and the input to the `processor`, and `R`
        defines the return type based on the `processor`'s output.
    -   Remember if you use `TypeVar`, always append `T` or `T_co` or `T_contra`
        to the end of the type variable name.
    -   Use `from __future__ import annotations` at the top of the file to
        enable forward references and not `string` references.
    -   Use `TYPE_CHECKING` to check if the code is running in type checking
        mode. This is useful to avoid circular imports.

3.  **`Generic` for Classes**:

    -   When a class itself is designed to work with a variety of types in a
        structured way, inherit from `Generic[T]`.
    -   Example:
        `class Container(Generic[T]): def __init__(self, content: T): self.content: T = content`.
        This clearly defines that a `Container` instance holds content of a
        specific, yet parameterizable, type.

4.  **`type` for Simplicity**:
    -   Your directive to use `type ItemId = int` instead of `TypeAlias` for
        simple aliases is excellent for modern Python (3.12+). It's cleaner and
        more direct for straightforward type synonyms. `TypeAlias` remains
        useful for more complex definitions, especially when you need to
        annotate its nature explicitly, but for simple cases, `type` is more
        elegant.

---

### Elevating Design with Patterns 🏗️

SOLID principles and design patterns are the blueprints for elegant
architecture.

**SOLID, Re-emphasized**:

-   **S – Single Responsibility Principle (SRP)**: Beyond framework-agnostic
    services, ensure each class and function has one, and only one, reason to
    change. This means a laser focus on its core responsibility.
-   **O – Open/Closed Principle (OCP)**: The **Strategy** pattern is a prime
    example. Elegance here means you can introduce new behaviors (e.g., a new
    LLM provider) by adding new code (a new strategy class) rather than
    modifying existing, tested code.
-   **L – Liskov Substitution Principle (LSP)**: Programming to `Protocol`s
    (structural typing) is fantastic. True elegance means that any
    implementation of a protocol can be substituted anywhere the protocol is
    expected, without any surprising behavior. This requires careful contract
    definition in your protocols.
-   **I – Interface Segregation Principle (ISP)**: Creating cohesive `Protocol`s
    means clients only depend on the methods they actually use. This avoids
    "fat" interfaces that force unnecessary dependencies.
-   **D – Dependency Injection (DI)**: Constructor injection is generally the
    cleanest. Factories can abstract away the _how_ of object creation,
    especially when object setup is complex or involves choices based on
    configuration. This keeps your core logic cleaner by offloading setup
    responsibilities.

**Key Patterns for Elegance**:

-   **Factory / Builder**: Elegance comes from separating the construction logic
    of a complex object from its representation. A client needs an object but
    shouldn't be burdened with the details of its creation.
-   **Observer (Pub/Sub)**: Decouples event producers from consumers. An elegant
    implementation ensures that adding new subscribers or new event types
    doesn't require changes to the publisher or other subscribers.
-   **Decorator**: Adds responsibilities to objects dynamically and
    transparently. Elegant decorators are focused (SRP) and compose well.
-   **Adapter**: Makes incompatible interfaces work together. Elegance means the
    adapter is thin and focused solely on translation.
-   **Bridge**: Decouples an abstraction from its implementation so the two can
    vary independently. This is powerful for handling multiple platforms or
    versions.
-   **Composite**: Allows you to treat individual objects and compositions of
    objects uniformly. Elegant use simplifies client code when dealing with
    tree-like structures.
-   **Facade**: Provides a single, simplified interface to a complex subsystem.
    Elegance is achieved by making the subsystem easier to use without hiding
    essential flexibility.
-   **Proxy**: Controls access to an object. An elegant proxy is
    indistinguishable from the real object from the client's perspective,
    transparently adding behavior like lazy loading or access control.
-   **Chain of Responsibility**: Decouples sender and receiver. An elegant chain
    is easy to configure and allows handlers to be dynamically added or removed.
-   **Command**: Turns a request into a stand-alone object. This allows for
    parameterizing clients with different requests, queuing requests, and
    supporting undoable operations. Elegance lies in the clear separation of
    invoker, command, and receiver.
-   **Iterator**: Provides a standard way to traverse a collection. Elegant
    iterators hide the internal structure of the collection.

---

### Eradicating Code Smells for Pristine Code 🚩

Code smells are indicators of deeper problems. Addressing them directly leads to
more robust and understandable code.

-   **Long Parameter Lists → Pydantic Models**:

    -   This is a powerful technique. When a function takes more than three or
        four arguments, especially if some are optional or frequently passed
        together, grouping them into a Pydantic model provides:
        -   **Clarity**: The model's name describes the group of parameters.
        -   **Validation**: Pydantic handles validation at the boundary.
        -   **Readability**: `my_function(config=RequestConfig(...))` is often
            clearer than `my_function(a, b, None, d, None, f)`.
        -   **Ease of Modification**: Adding a new related parameter means
            changing the model, not every function signature.

-   **Feature Envy**:

    -   A method on one class seems more interested in the data of another class
        than its own.
    -   **Elegant Solution**: Move the method (or the relevant part of it) to
        the class whose data it "envies." This usually improves cohesion and
        reduces coupling, aligning with SRP. If the method needs data from both,
        consider a third class or a function that takes both objects as
        parameters.

-   **God Classes / Objects**:

    -   Classes that know or do too much. They violate SRP and OCP and become
        bottlenecks for change.
    -   **Elegant Solution**: Break them down. Identify distinct
        responsibilities within the god class. Extract these responsibilities
        into new, smaller classes. Each new class will be more focused, easier
        to test, and easier to understand. Use DI to connect these smaller,
        focused units.

-   **Primitive Obsession**:

    -   Over-reliance on primitive types (strings, integers, booleans) to
        represent domain concepts.
    -   **Elegant Solution**: Introduce small value objects or Pydantic models
        for these concepts. For example, instead of `email: str`, use
        `email: EmailAddress` where `EmailAddress` is a Pydantic model that
        validates the email format. This adds type safety and encapsulates
        domain-specific logic.

-   **Shotgun Surgery**:

    -   One change requires making small changes in many classes.
    -   **Elegant Solution**: This often indicates poor distribution of
        responsibilities (related to SRP and coupling). Try to consolidate the
        responsibility that's changing into fewer classes, or use patterns like
        Observer or Mediator to decouple the classes involved.

-   **Duplicated Code**:
    -   The most straightforward smell.
    -   **Elegant Solution**: Extract the common code into a new function or
        method. If the duplication is more complex, consider patterns like
        Template Method or Strategy.

---

### Pydantic V2: Validation at the Gates 🛡️

Your point is crucial: **If validation checks can be done at the Pydantic model
level, do it there and not in the business logic.**

-   This keeps your business logic focused on _what_ to do, not on _whether the
    data is valid_ to do it with.
-   Pydantic models act as a strong "anti-corruption layer" at the boundaries of
    your system (API inputs, configuration, database interactions).
-   Use Pydantic's validators (`@field_validator`, `@model_validator`), type
    annotations, and `Field` constraints to define the shape and validity of
    data declaratively.

---

### The Unspoken Eloquence of Self-Documenting Code 📖

With the "Critical Constraint: No Comments or Docstrings," the burden of clarity
falls entirely on the code itself. This is a powerful motivator for:

-   **Extremely Precise Naming**: Variable names, function names, and class
    names must clearly and unambiguously convey their purpose and meaning.
    `user_list` is okay, `active_users_retrieved_from_database` is better if
    that's what it is, but perhaps a class `UserRepository` with a method
    `get_active_users()` is best.
-   **Logical Structure and Flow**: Code should read like well-written prose.
    Functions should be short and do one thing. Classes should be small and
    cohesive.
-   **Strong Typing as Documentation**: Your strict type hinting becomes a
    primary source of understanding. `def process_data(data: dict[str, Any])` is
    vague.
    `def generate_report(entries: list[ValidatedLogEntry]) -> ReportOutput:` is
    much clearer.
-   **Pattern Explicitness**: The choice and implementation of design patterns
    should be evident from the structure and naming, guiding the reader to
    understand the architectural intent.

---

Run below commands for lint.

1. uv run ruff format .
1. uv run ruff check --fix .
1. uv run mypy .
1. uv run pyright .

I want you to be SMART about fixing the problems. For type-related problems
identified by mypy, understand the actual types involved and fix them properly -
never just add type: ignore or use Any as a band-aid. For linting issues from
ruff, don't just disable rules - understand why the rule exists and fix the
underlying issue. If there's an unused import or variable, figure out if it
should be used somewhere or safely removed.

Make all edits to the existing code files-- don't ever create a duplicative code
file with the changes and give it some silly name; for instance, don't correct a
problem in module_xyz.py in a newly created file called module_xyz_fixed.py or
module_xyz_new.py-- always just revise module_xyz.py in place!

CRITICALLY IMPORTANT: Follow Python best practices and PEP 8 style guidelines.
Use type hints properly throughout the codebase. This code is still in
development so we don't care about backwards compatibility - fix things the
RIGHT WAY. Note that we use uv as our package manager, not pip.

Make sure remove all redundant code or files after you have completed the task
and do not need to maintain backward compatibility.

## Notes

-   If refactor, no need consider backwards compatibility.
-   If docstring, use numpy/sphinx style.
-   Always run `uv run ruff check --fix` and `uv run ruff format` and
    `uv run mypy` and `uv run pyright` after tool call.
-   Read
    [design patterns](/Users/gaohn/gaohn/fatum/playbook/design_patterns_guide.md)
    and
    [solid principles](/Users/gaohn/gaohn/fatum/playbook/solid_principles_guide.md)
    if you need to do designing.
