# Circuit Breaker Pattern in Distributed Systems

```{epigraph}
If at first you don't succeed, back off exponentially.

-- Dan Sandler, Google Software Engineer {cite:p}`google2017sre-cascading`
```

[![Resilience](https://img.shields.io/badge/Resilience-Fault_Isolation-green?style=for-the-badge)](https://sre.google/sre-book/addressing-cascading-failures/)
[![Circuit Breaker](https://img.shields.io/badge/Pattern-Circuit_Breaker-blue?style=for-the-badge)](https://martinfowler.com/bliki/CircuitBreaker.html)
[![SRE](https://img.shields.io/badge/Pattern-Google_SRE-orange?style=for-the-badge)](https://sre.google/sre-book/handling-overload/)
[![Fail-Fast](https://img.shields.io/badge/Principle-Fail_Fast-red?style=for-the-badge)](https://www.martinfowler.com/ieeeSoftware/failFast.pdf)

---

> **Key Sources**:
>
> - Fowler, M. (2014).
>   [CircuitBreaker](https://martinfowler.com/bliki/CircuitBreaker.html)
> - Google SRE Book, Chapter 22:
>   [Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/)
> - Nygard, M. T. (2018). _Release It!_ Second Edition. Pragmatic Bookshelf.
> - Microsoft Azure Architecture Center:
>   [Circuit Breaker Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
> - Netflix:
>   [Hystrix - How it Works](https://github.com/Netflix/Hystrix/wiki/How-it-Works)

---

## Definitions

Before diving in, let's establish precise definitions for terms used throughout
this guide. These definitions are referenced via `{term}` links.

```{glossary}
Circuit Breaker
    A proxy that monitors the health of a downstream dependency and controls
    access to it based on observed failure patterns. It operates as a **state
    machine** with three states: Closed, Open, and Half-Open.
    {cite:p}`fowler2014circuitbreaker`

Closed State
    Normal operation mode where all requests pass through to the downstream
    service. Failures are counted. When the failure count exceeds the
    threshold, the circuit transitions to {term}`Open State`.

Open State
    **{term}`Fail-Fast`** mode. No requests are made to the downstream service.
    All requests fail immediately with a circuit breaker exception. A timeout
    begins; when it expires, the circuit transitions to {term}`Half-Open State`.

Half-Open State
    Recovery testing mode. Limited "probe" requests are allowed through.
    If the probe succeeds, the circuit transitions to {term}`Closed State`
    (service recovered). If it fails, the circuit returns to {term}`Open State`.

Fail-Fast
    The principle of returning an immediate error when a downstream service is
    known to be unhealthy, rather than waiting for it to fail. This protects
    both the caller (freed resources) and the downstream service (breathing
    room to recover). {cite:p}`fowler2014circuitbreaker`

Cascading Failure
    A failure mode where one component's failure causes dependent components
    to fail, which in turn cause their dependents to fail, creating a
    chain reaction that can bring down an entire system.
    {cite:p}`google2017sre-cascading`

Fault Isolation
    The practice of isolating failures so they don't propagate to unrelated
    parts of the system. Achieved by using separate circuit breakers for each
    dependency. {cite:p}`nygard2018releaseit`

Probe Request
    A test request sent during {term}`Half-Open State` to determine if the
    downstream service has recovered. If successful, normal operation resumes;
    if failed, the circuit reopens.

Bulkhead
    A resilience pattern that isolates resources (threads, connections, memory)
    for different dependencies, preventing one failing dependency from
    exhausting all resources. Complementary to circuit breakers.
    {cite:p}`nygard2018releaseit`
```

```{admonition} Prerequisites
:class: note

This guide assumes familiarity with:
- **Retry patterns** (see [Retry Patterns](./retry.md))
- **Async Python** (`async`/`await`, `asyncio`)
- **HTTP status codes** (4xx vs 5xx semantics)
- **Distributed systems concepts** (partial failures, network partitions)
```

---

## Overview

```{prf:observation} The Google SRE Insight
:label: obs-waiting-worse-than-failing

**Waiting for a failing service is worse than failing immediately.**
{cite:p}`google2017sre-cascading`

When a downstream service becomes slow or unresponsive, upstream services that
depend on it accumulate waiting requests. These requests consume threads,
connections, and memory—resources that cannot serve other requests. Eventually,
the upstream service exhausts its resources and fails too, causing _its_ callers
to fail. This {term}`Cascading Failure` continues until the entire system
collapses.
```

Circuit breakers are a fundamental resilience pattern for **preventing
{term}`Cascading Failure`** in distributed systems. When a downstream service
becomes slow or unresponsive, the circuit breaker **fails fast**—returning an
immediate error instead of waiting for a timeout.
{cite:p}`fowler2014circuitbreaker`

```{prf:remark} Document Structure
:label: rem-cb-doc-structure

This guide proceeds as follows:

1. **[Why Circuit Breakers Exist](#why-circuit-breakers-exist)** — The cascading
   failure problem and {term}`Fail-Fast` principle
2. **[The State Machine](#the-state-machine)** — Closed, Open, Half-Open states
   with formal definitions
3. **[Circuit Breaker vs Retry](#circuit-breaker-vs-retry)** — The critical
   distinction (they solve different problems!)
4. **[How They Work Together](#how-circuit-breaker-and-retry-work-together)** —
   The gold standard pattern
5. **[Implementation](#the-transcreation-implementation)** — Purgatory library usage
6. **[LLM API Patterns](#llm-api-integration-patterns)** — Per-provider isolation
7. **[Anti-Patterns](#circuit-breaker-anti-patterns)** — What NOT to do (read this!)
8. **[Best Practices](#best-practices-from-google-sre-and-industry)** — Google SRE
   recommendations
9. **[Monitoring](#monitoring-and-observability)** — Observability essentials
```

---

## 1. Why Circuit Breakers Exist

### 1.1 The Cascading Failure Problem

```{prf:definition} Cascading Failure
:label: def-cascading-failure

A **{term}`Cascading Failure`** occurs when the failure of one component causes
dependent components to fail, creating a chain reaction:

1. Service C becomes slow or unresponsive
2. Service B (which depends on C) accumulates waiting requests
3. Service B's threads/connections become exhausted
4. Service B starts failing
5. Service A (which depends on B) starts accumulating waiting requests
6. The cascade continues until the entire system is down

{cite:p}`google2017sre-cascading`
```

```{mermaid}
:zoom:

sequenceDiagram
    participant U as User
    participant A as Service A
    participant B as Service B
    participant C as Service C (Failing)

    Note over C: Service C becomes slow/unresponsive

    U->>A: Request 1
    A->>B: Forward request
    B->>C: Call downstream
    Note over B: Thread blocked waiting...
    C--xB: Timeout (10s)
    B--xA: Timeout
    A--xU: Error (slow)

    U->>A: Request 2
    A->>B: Forward request
    Note over B: Previous thread still blocked
    B->>C: Call downstream
    Note over B: Two threads blocked...
    C--xB: Timeout
    B--xA: Timeout
    A--xU: Error

    Note over A,B: Thread pools exhausted
    Note over A,B: Services A and B now failing
    Note over U: Cascade complete: entire system down
```

### 1.2 The Fail-Fast Principle

```{prf:definition} Fail-Fast Principle
:label: def-fail-fast

The {term}`Fail-Fast` principle states: **when a downstream service is known to
be unhealthy, don't wait for it to fail—fail immediately** and return an error
or fallback response. {cite:p}`fowler2014circuitbreaker`

This serves two critical purposes:

1. **Protects the caller**: Frees resources (threads, connections, memory) that
   would otherwise be blocked waiting for a timeout
2. **Protects the downstream service**: Gives it breathing room to recover
   instead of overwhelming it with additional requests
```

```{prf:property} Benefits of Fail-Fast
:label: prop-fail-fast-benefits

| Aspect              | Without {term}`Fail-Fast`   | With {term}`Fail-Fast` (Circuit Breaker) |
| ------------------- | --------------------------- | ---------------------------------------- |
| **Response time**   | Waits for timeout (seconds) | Immediate (milliseconds)                 |
| **Resource usage**  | Threads/connections blocked | Resources freed                          |
| **Cascade risk**    | High                        | Contained                                |
| **Recovery chance** | Service stays overwhelmed   | Service gets breathing room              |
| **User experience** | Slow errors                 | Fast errors with fallback                |
```

### 1.3 The Electrical Analogy

```{prf:observation} The Electrical Circuit Breaker Analogy
:label: obs-electrical-analogy

The pattern is named after electrical circuit breakers. In an electrical system,
a circuit breaker detects excessive current (a fault) and **trips open**,
breaking the circuit to prevent fire or equipment damage. Once the fault is
resolved, the circuit breaker can be reset. {cite:p}`fowler2014circuitbreaker`

Software circuit breakers work the same way:

-   **Normal operation ({term}`Closed State`)**: Current (requests) flows through
-   **Fault detected ({term}`Open State`)**: Circuit breaks, no current flows
-   **Testing recovery ({term}`Half-Open State`)**: Allow a test current to check
    if fault is resolved
```

---

## 2. The State Machine

```{prf:definition} Circuit Breaker State Machine
:label: def-circuit-breaker-states

A circuit breaker operates as a **state machine** with three distinct states.
State transitions are triggered by observed failures and timeouts.
{cite:p}`fowler2014circuitbreaker,nygard2018releaseit`
```

```{mermaid}
:zoom:

stateDiagram-v2
    [*] --> Closed

    Closed --> Open: Failure threshold exceeded
    Closed --> Closed: Success / Failure below threshold

    Open --> HalfOpen: Timeout expires
    Open --> Open: Requests fail fast (no call made)

    HalfOpen --> Closed: Probe request succeeds
    HalfOpen --> Open: Probe request fails

    note right of Closed
        Normal operation
        All requests pass through
        Failures counted
    end note

    note right of Open
        FAIL FAST
        No requests to downstream
        Immediate fallback/error
        Protects failing service
    end note

    note right of HalfOpen
        Testing recovery
        Limited probe requests
        Determines if service recovered
    end note
```

### 2.1 The Three States

```{prf:property} Closed State (Normal Operation)
:label: prop-closed-state

In the {term}`Closed State`:

-   All requests **pass through** to the downstream service
-   **Failures are counted** (consecutive or within a time window)
-   When failure count exceeds the **threshold**, transition to {term}`Open State`
-   A single success may reset the failure count (implementation-dependent)
```

```{prf:property} Open State (Fail-Fast)
:label: prop-open-state

In the {term}`Open State`:

-   **No requests are made** to the downstream service
-   All requests **fail immediately** with a circuit breaker exception
-   A **timeout timer** begins
-   When the timeout expires, transition to {term}`Half-Open State`

This is the core of the {term}`Fail-Fast` principle: the circuit breaker knows
the downstream is unhealthy, so it doesn't waste resources trying to reach it.
```

```{prf:property} Half-Open State (Testing Recovery)
:label: prop-half-open-state

In the {term}`Half-Open State`:

-   Limited **{term}`Probe Request`** requests are allowed through
-   If the probe **succeeds**, transition to {term}`Closed State` (service recovered)
-   If the probe **fails**, transition back to {term}`Open State` (still failing)

The half-open state prevents "flapping" (rapidly oscillating between open and
closed) by requiring proof of recovery before resuming normal operation.
```

### 2.2 Mathematical Foundations

```{prf:definition} State Transition Conditions
:label: def-state-transitions

Let:

-   $f$ = consecutive failure count
-   $f_{\text{max}}$ = failure threshold (`threshold` in config)
-   $s$ = consecutive success count in HALF_OPEN
-   $s_{\text{threshold}}$ = success threshold for recovery
-   $t$ = current time
-   $t_{\text{open}}$ = time when circuit opened
-   $\tau_{\text{ttl}}$ = reset timeout (`ttl` in config)

**CLOSED → OPEN transition:**

$$
\text{Trip condition: } f \geq f_{\text{max}}
$$

The circuit trips open when consecutive failures reach the threshold.

**OPEN → HALF_OPEN transition:**

$$
\text{Probe condition: } t - t_{\text{open}} \geq \tau_{\text{ttl}}
$$

The circuit transitions to half-open when the reset timeout expires.

**HALF_OPEN → CLOSED transition:**

$$
\text{Recovery condition: } s \geq s_{\text{threshold}}
$$

The circuit closes when enough probe requests succeed.

**HALF_OPEN → OPEN transition:**

$$
\text{Re-trip condition: any failure in HALF\_OPEN}
$$

Any failure in half-open immediately re-opens the circuit.
```

### 2.3 Key Configuration Parameters

| Parameter               | Description                                  | Config Field  | Typical Value   |
| ----------------------- | -------------------------------------------- | ------------- | --------------- |
| **Failure threshold**   | Consecutive failures to trip open            | `threshold`   | 3-10 failures   |
| **Reset timeout (TTL)** | Time before trying half-open                 | `ttl`         | 30-60 seconds   |
| **Success threshold**   | Successes in half-open to close              | (varies)      | 1-3 successes   |
| **Excluded exceptions** | Exception types that don't count as failures | `exclude`     | 4xx HTTP errors |
| **Circuit name**        | Identifier for logs and metrics              | (per-breaker) | Service name    |

### 2.4 Effective Availability

```{prf:theorem} Effective Availability with Circuit Breaker
:label: thm-effective-availability

The circuit breaker affects your service's effective availability. If
$A_{\text{service}}$ is the downstream service availability and
$P_{\text{fallback}}$ is the probability your fallback returns a
useful response, then:

$$
A_{\text{effective}} = A_{\text{service}} + (1 - A_{\text{service}}) \cdot P_{\text{fallback}}
$$

**Insight**: Good fallbacks improve effective availability beyond what the
downstream service provides. {cite:p}`netflix2017hystrix`

**Example**: If downstream is 99% available and your fallback works 90% of the
time when downstream fails:

$$
A_{\text{effective}} = 0.99 + (1 - 0.99) \times 0.90 = 0.99 + 0.009 = 0.999 = 99.9\%
$$
```

### 2.5 Count-Based vs Time-Based Sliding Windows

```{prf:algorithm} Consecutive Failure Counting
:label: alg-consecutive-failures

The Transcreation implementation uses **count-based** (consecutive failure)
tracking:

$$
\text{State: } f_{\text{consecutive}} = \begin{cases}
f + 1 & \text{if failure} \\
0 & \text{if success}
\end{cases}
$$

**Pros:**

-   Simple to understand and predict
-   Deterministic behavior
-   No time-based race conditions

**Cons:**

-   Doesn't account for request volume
-   A single success resets the count
```

```{prf:algorithm} Time-Based Sliding Window (Alternative)
:label: alg-sliding-window

Alternative implementations (Resilience4j, Hystrix) use time-based windows:
{cite:p}`resilience4j2024docs`

$$
\text{Failure rate} = \frac{\text{failures in window}}{\text{total calls in window}} \times 100\%
$$

For example, with a 60-second window and 50% threshold:

-   10 calls, 6 failures → 60% failure rate → **trip open**
-   100 calls, 40 failures → 40% failure rate → **stay closed**

**Pros:**

-   Tolerates sporadic failures
-   Adapts to traffic patterns
-   More accurate health signal

**Cons:**

-   Requires minimum call volume before decisions
-   More complex to implement and reason about
-   Time-sensitive state management
```

---

## 3. Circuit Breaker vs Retry: Understanding the Difference

```{prf:criterion} The Fundamental Distinction
:label: crit-cb-vs-retry

**{term}`Circuit Breaker`** and **Retry** solve **different problems**:

-   **Retry** handles **transient failures** (request-scoped)
-   **Circuit Breaker** handles **systemic failures** (service-scoped)

They are **complementary, not alternatives**. {cite:p}`microsoft2023circuitbreaker`
```

### 3.1 The Core Distinction

```{mermaid}
:zoom:

flowchart LR
    subgraph Retry[Retry Pattern]
        R1[Request fails] --> R2{Transient?}
        R2 -->|Yes| R3[Wait with backoff]
        R3 --> R4[Try again]
        R4 --> R5{Success?}
        R5 -->|No| R2
        R5 -->|Yes| R6[Return result]
        R2 -->|No/Max attempts| R7[Give up]
    end

    subgraph CircuitBreaker[Circuit Breaker Pattern]
        CB1[Request] --> CB2{Circuit state?}
        CB2 -->|Closed| CB3[Execute request]
        CB3 --> CB4{Success?}
        CB4 -->|Yes| CB5[Return result]
        CB4 -->|No| CB6[Count failure]
        CB6 --> CB7{Threshold?}
        CB7 -->|Exceeded| CB8[OPEN circuit]
        CB2 -->|Open| CB9[Fail fast]
        CB2 -->|Half-Open| CB10[Probe]
    end

    style R6 fill:#90EE90
    style R7 fill:#FFB6C1
    style CB5 fill:#90EE90
    style CB9 fill:#FFB6C1
    style CB8 fill:#FFA500
```

### 3.2 Comparison Table

```{prf:property} Retry vs Circuit Breaker Characteristics
:label: prop-retry-vs-cb-comparison

| Aspect                 | Retry                                    | Circuit Breaker                               |
| ---------------------- | ---------------------------------------- | --------------------------------------------- |
| **Purpose**            | Recover from transient failures          | Prevent cascading failures                    |
| **Problem it solves**  | "This request failed, maybe next time"   | "This service is down, stop hammering it"     |
| **When active**        | After each individual failure            | After failure pattern detected                |
| **Behavior**           | Keep trying (with delays)                | Stop trying immediately                       |
| **Protects**           | The current request's success            | The downstream service and system stability   |
| **Time scale**         | Seconds (within single request lifetime) | Minutes (across many requests)                |
| **State**              | Per-request                              | Shared across all requests to same dependency |
| **Failure assumption** | Failure is temporary and isolated        | Failure is systemic and ongoing               |
| **Without the other**  | Retry storms overwhelm failing services  | No recovery from transient failures           |

{cite:p}`microsoft2023circuitbreaker,nygard2018releaseit`
```

### 3.3 When to Use Each

**Use Retry when:**

- Network blips cause occasional failures
- Database connections reset intermittently
- Rate limiting returns 429 responses
- Cold starts cause initial timeouts
- You believe the next attempt will likely succeed

**Use Circuit Breaker when:**

- A service is completely down
- A service is dangerously slow (resource exhaustion)
- Failures are consistent, not random
- You need to protect the downstream service from overload
- You need to protect your service from {term}`Cascading Failure`

**Use Both when:**

- Building production-grade distributed systems (**this is the default
  answer**)
- You want resilience against both transient and systemic failures

### 3.4 The Key Insight: Time Scale and Scope

```{prf:observation} Time Scale Difference
:label: obs-time-scale-difference

The fundamental difference is **time scale** and **scope**:

-   **Retry** operates **within a single request**: "try, wait, try, wait, try,
    give up" (seconds)
-   **Circuit Breaker** operates **across many requests**: "I've seen 3 failures
    in a row—stop all requests" (minutes)

{cite:p}`nygard2018releaseit`
```

```{mermaid}
:zoom:

gantt
    title Failure Timeline: Retry vs Circuit Breaker
    dateFormat X
    axisFormat %s

    section Request 1
    Attempt 1 (fails)    :a1, 0, 1
    Backoff 1s           :a2, 1, 2
    Attempt 2 (fails)    :a3, 2, 3
    Backoff 2s           :a4, 3, 5
    Attempt 3 (fails)    :crit, a5, 5, 6

    section Request 2
    Attempt 1 (fails)    :b1, 7, 8
    Backoff 1s           :b2, 8, 9
    Attempt 2 (fails)    :b3, 9, 10
    Backoff 2s           :b4, 10, 12
    Attempt 3 (fails)    :crit, b5, 12, 13

    section Request 3
    Attempt 1 (fails)    :c1, 14, 15
    Circuit OPENS        :crit, c2, 15, 15

    section Requests 4-100
    FAIL FAST            :done, d1, 15, 45

    section Recovery
    Timeout expires      :d2, 45, 46
    Half-open probe      :d3, 46, 47
    Circuit CLOSES       :done, d4, 47, 48
```

---

## 4. How Circuit Breaker and Retry Work Together

### 4.1 The Combined Pattern

```{prf:property} The Gold Standard: Retry + Circuit Breaker
:label: prop-gold-standard-pattern

The gold standard for resilient distributed systems is **Retry + Circuit
Breaker** together. {cite:p}`nygard2018releaseit,microsoft2023circuitbreaker`
```

````{prf:criterion} Critical: Wrapping Order
:label: crit-wrapping-order

**Retry MUST wrap Circuit Breaker** (outer to inner).

The order matters because:

1. **CB sees every failure** — if you retry 3 times and all fail, CB records 3
   failures. This is correct because concurrent requests would each fail.
2. **Trips fast** — protects the struggling downstream service sooner
3. **Fail fast on open** — `OpenedState` in `never_retry_on` stops retries
   immediately
4. **Accurate health signal** — CB has true visibility into downstream health

**Critical configuration**: Retry must NOT retry on `OpenedState`:

```python
retry_config = RetryConfig(never_retry_on=(OpenedState,))
```

{cite:p}`google2017sre-cascading`
````

### 4.2 Why This Order?

**Retry wraps Circuit Breaker** for these critical reasons:

| Aspect                   | Retry→CB (Correct)                         | CB→Retry (Wrong)                                    |
| ------------------------ | ------------------------------------------ | --------------------------------------------------- |
| **Visibility**           | CB sees every individual failure           | CB only sees final failure after all retries        |
| **Reaction Speed**       | CB trips fast (3 attempts = 3 CB failures) | CB trips slowly (3 retries = 1 CB failure)          |
| **Load on Downstream**   | Minimizes load once CB opens               | Hammers downstream with N retries before CB notices |
| **OpenedState handling** | Retry can abort immediately                | Retry never sees OpenedState                        |

```{mermaid}
:zoom:

flowchart TB
    subgraph Client[Client Code]
        A[Make Request]
    end

    subgraph Retry[Retry Layer - OUTER]
        B{Attempt #?}
        C[Execute with CB]
        D{Success?}
        E[Wait with backoff]
        F[Return result]
        G[Throw after max attempts]
    end

    subgraph CB[Circuit Breaker Layer - INNER]
        H{CB State?}
        I[Call downstream]
        J{Success?}
        K[Count failure]
        L[Fail fast]
        M[Return response]
    end

    subgraph Downstream[Downstream Service]
        N[Process request]
    end

    A --> B
    B -->|< max| C
    C --> H
    H -->|Closed| I
    H -->|Open| L
    I --> N
    N --> J
    J -->|Yes| M
    M --> D
    J -->|No| K
    K --> D
    L --> D
    D -->|Yes| F
    D -->|No, retriable| E
    E --> B
    D -->|No, CB open| G
    B -->|>= max| G

    style F fill:#90EE90
    style G fill:#FFB6C1
    style L fill:#FFA500
```

### 4.3 Implementation Pattern

```python
from purgatory.domain.model import OpenedState

from transcreation.config.circuit_breaker import CircuitBreakerConfig
from transcreation.config.retry import RetryConfig
from transcreation.resilience import AsyncCircuitBreakerFactory
from transcreation.resilience.retry import build_retry_decorator

# Configuration
retry_config = RetryConfig(max_attempts=3, wait_min=1.0, wait_max=10.0)
cb_config = CircuitBreakerConfig(threshold=5, ttl=30.0)
factory = AsyncCircuitBreakerFactory(
    default_threshold=cb_config.threshold,
    default_ttl=cb_config.ttl,
)


async def call_external_api(request: dict) -> dict:
    # Add OpenedState to never_retry_on (fail fast when circuit is open)
    retry_config_with_cb = retry_config.model_copy(
        update={"never_retry_on": (OpenedState,)}
    )
    retry = build_retry_decorator(retry_config_with_cb)

    @retry  # OUTER: Retry wraps everything
    async def _call() -> dict:
        breaker = await factory.get_breaker("external-api")
        async with breaker:  # INNER: Circuit breaker closest to service
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.example.com/v1/process",
                    json=request,
                )
                response.raise_for_status()
                return response.json()

    return await _call()
```

### 4.4 Sequence Diagram: Combined Pattern in Action

```{mermaid}
:zoom:

sequenceDiagram
    participant C as Client
    participant R as Retry Layer
    participant CB as Circuit Breaker
    participant S as Service (Failing)

    Note over CB: State: CLOSED (0 failures)

    rect rgb(255, 240, 240)
        Note over C,S: Request 1: Transient failure, retry succeeds
        C->>R: Request
        R->>CB: Attempt 1
        CB->>S: Call
        S--xCB: Timeout
        CB->>CB: Failure count: 1
        CB--xR: Error
        R->>R: Wait 1s (backoff)
        R->>CB: Attempt 2
        CB->>S: Call
        S-->>CB: Success!
        CB->>CB: Reset failure count
        CB-->>R: Response
        R-->>C: Success
    end

    Note over CB: State: CLOSED (0 failures)

    rect rgb(255, 200, 200)
        Note over C,S: Requests 2-4: All fail, circuit opens
        C->>R: Request
        R->>CB: Attempts (all fail)
        CB->>S: Calls (all timeout)
        CB->>CB: Failure count: 3
        Note over CB: THRESHOLD EXCEEDED
        CB->>CB: State → OPEN
        CB--xR: CircuitBreakerOpen
        R--xC: Error (not retriable)
    end

    Note over CB: State: OPEN

    rect rgb(255, 220, 180)
        Note over C,S: Request 5: Fail fast (no downstream call)
        C->>R: Request
        R->>CB: Attempt
        Note over CB: Circuit is OPEN
        CB--xR: CircuitBreakerOpen (immediate)
        Note over R: Not retriable!
        R--xC: Error (fast)
    end

    Note over CB: 30 seconds pass...

    rect rgb(200, 255, 200)
        Note over C,S: Request N: Half-open probe succeeds
        Note over CB: State → HALF_OPEN
        C->>R: Request
        R->>CB: Attempt
        CB->>S: Probe request
        S-->>CB: Success!
        Note over CB: State → CLOSED
        CB-->>R: Response
        R-->>C: Success
    end
```

### 4.5 Configuration Harmony

```{prf:property} Harmonized Configuration
:label: prop-config-harmony

For the patterns to work well together, their configurations must be harmonized:

| Configuration                 | Recommendation                                      |
| ----------------------------- | --------------------------------------------------- |
| **Retry timeout per attempt** | Less than downstream's timeout                      |
| **Total retry time**          | Consider circuit breaker's perspective              |
| **Circuit breaker threshold** | High enough to tolerate isolated transients         |
| **Backoff jitter**            | ALWAYS use to prevent synchronized retries          |
| **Circuit open timeout**      | Long enough for service to recover (30-60s typical) |

{cite:p}`google2017sre-cascading`
```

---

## 5. The Transcreation Implementation

Transcreation uses the **Purgatory** library for circuit breaker functionality,
providing an async-native implementation built for production use with LLM APIs
and other external services.

### 5.1 Configuration

```python
from transcreation.config.circuit_breaker import CircuitBreakerConfig

config = CircuitBreakerConfig(
    enabled=True,       # Feature flag to enable/disable circuit breaker
    threshold=5,        # Consecutive failures before opening (default: 5)
    ttl=30.0,           # Seconds before OPEN → HALF_OPEN (default: 30.0)
    exclude=None,       # Exception types that don't count as failures
)
```

### 5.2 Basic Usage

Transcreation uses `AsyncCircuitBreakerFactory` to create per-name circuit
breakers, enabling per-provider {term}`Fault Isolation`.

```python
from transcreation.config.circuit_breaker import CircuitBreakerConfig
from transcreation.resilience import AsyncCircuitBreakerFactory, OpenedState

config = CircuitBreakerConfig(threshold=3, ttl=30.0)
factory = AsyncCircuitBreakerFactory(
    default_threshold=config.threshold,
    default_ttl=config.ttl,
    exclude=config.exclude,
)


async def call_openai(prompt: str) -> str:
    breaker = await factory.get_breaker("llm:openai")

    async with breaker:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}]},
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]


async def safe_call(prompt: str) -> str:
    try:
        return await call_openai(prompt)
    except OpenedState:
        return "Service unavailable. Circuit breaker is open."
```

### 5.3 Context Manager Pattern

Purgatory uses the context manager pattern for circuit breaker execution:

```python
from transcreation.resilience import AsyncCircuitBreakerFactory, OpenedState

factory = AsyncCircuitBreakerFactory(default_threshold=3, default_ttl=30.0)


async def translate_text(text: str, target_lang: str) -> str:
    breaker = await factory.get_breaker("llm:openai")

    async with breaker:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.example.com/translate",
                json={"text": text, "target": target_lang},
            )
            response.raise_for_status()
            return response.json()["translation"]
```

### 5.4 Sequence Diagram

```{mermaid}
:zoom:

sequenceDiagram
    participant C as Client
    participant CB as CircuitBreaker
    participant F as Function
    participant S as Service

    Note over CB: State: CLOSED (0 failures)

    C->>CB: async with breaker
    CB->>CB: Check state: CLOSED
    CB->>F: Execute function
    F->>S: Make request
    S--xF: Error
    F--xCB: Raise exception
    CB->>CB: Increment failure count
    CB--xC: Raise exception

    Note over CB: Repeat until threshold reached...

    C->>CB: async with breaker
    CB->>CB: Check state: CLOSED
    CB->>F: Execute function
    F->>S: Make request
    S--xF: Error
    F--xCB: Raise exception
    CB->>CB: Failure count >= threshold
    CB->>CB: Transition to OPEN
    CB--xC: Raise exception

    Note over CB: State: OPEN (failing fast)

    C->>CB: async with breaker
    CB->>CB: Check state: OPEN
    Note over CB: No downstream call!
    CB--xC: OpenedState (immediate)

    Note over CB: ttl seconds pass...

    C->>CB: async with breaker
    CB->>CB: Check state: OPEN, timeout expired
    CB->>CB: Transition to HALF_OPEN
    CB->>F: Execute probe request
    F->>S: Make request
    S-->>F: Success!
    F-->>CB: Return result
    CB->>CB: Transition to CLOSED
    CB-->>C: Return result
```

### 5.5 Per-Provider Circuit Breakers

Transcreation creates **one circuit breaker per LLM provider** for
{term}`Fault Isolation`. If OpenAI is struggling, Anthropic requests are
unaffected.

```python
from transcreation.resilience import AsyncCircuitBreakerFactory

factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)

# Each provider gets its own circuit breaker
openai_breaker = await factory.get_breaker("llm:openai")
anthropic_breaker = await factory.get_breaker("llm:anthropic")
gemini_breaker = await factory.get_breaker("llm:gemini")
```

### 5.6 Storage Options: In-Memory vs Redis

```{prf:observation} The Distributed State Problem
:label: obs-distributed-state

**Why would you need Redis for a circuit breaker?**

The answer lies in understanding that circuit breaker state must be **shared
across all instances** that call the same downstream service. Otherwise, each
instance learns independently that the service is failing—defeating the entire
purpose of {term}`Fail-Fast`.
```

#### The Problem: Independent State

Consider a typical production deployment with multiple application instances
behind a load balancer:

```text
Without Shared State (In-Memory):
                    Load Balancer
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    Instance 1      Instance 2      Instance 3
    CB State:       CB State:       CB State:
    failures=5      failures=0      failures=0
    state=OPEN      state=CLOSED    state=CLOSED
         │               │               │
         └───────────────┴───────────────┘
                         ▼
                   OpenAI API (DOWN)
```

**The Problem:** Instance 1 saw 5 consecutive failures and correctly opened its
circuit. But Instances 2 and 3 have no idea! They continue hammering the failing
API, wasting resources and preventing the downstream service from recovering.

Each instance maintains its own failure count:

- Instance 1: Saw failures 1, 4, 7, 10, 13 → Opens circuit → Fails fast ✓
- Instance 2: Saw failures 2, 5, 8, 11 → Only 4 failures → Still calling API ✗
- Instance 3: Saw failures 3, 6, 9, 12 → Only 4 failures → Still calling API ✗

**The cascade protection is broken.** Two-thirds of your instances are still
overwhelming the failing service.

#### The Solution: Shared State

```text
With Shared State (Redis):
                    Load Balancer
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    Instance 1      Instance 2      Instance 3
         │               │               │
         └───────────────┴───────────────┘
                         │
                         ▼
                   ┌─────────────┐
                   │    Redis    │
                   │ failures=5  │
                   │ state=OPEN  │
                   └─────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    All instances see state=OPEN → ALL fail fast immediately
```

With Redis as the storage backend:

1. **Failure 5** (any instance) → Circuit opens in Redis
2. **All subsequent requests** (any instance) → Check Redis → See OPEN → Fail
   fast
3. **Downstream service** → Gets breathing room to recover
4. **After TTL** → One probe request allowed → If success, circuit closes for
   ALL

#### When to Use Each Storage Backend

| Deployment Scenario                  | Storage   | Reason                                   |
| ------------------------------------ | --------- | ---------------------------------------- |
| Single instance (dev laptop)         | In-memory | Simple, no external dependency           |
| Local development/testing            | In-memory | No Redis setup needed                    |
| Multiple replicas (Kubernetes, ECS)  | **Redis** | Shared state across pods                 |
| Serverless (Lambda, Cloud Functions) | **Redis** | No persistent memory between invocations |
| Auto-scaling deployments             | **Redis** | Instances come and go dynamically        |
| Blue-green/canary deployments        | **Redis** | Both versions share circuit state        |

```{prf:criterion} Redis vs In-Memory Decision
:label: crit-storage-decision

**If you have more than one instance calling the same downstream service,
you need shared storage (Redis).**

The only exception is if you intentionally want per-instance circuit breakers
(rare, usually a mistake).
```

#### Configuration with Transcreation

Transcreation's `circuit_breaker()` function automatically selects the storage
backend based on configuration:

```python
from transcreation.config.circuit_breaker import CircuitBreakerConfig
from transcreation.resilience import circuit_breaker

# Development: in-memory storage (default when redis_url is None)
dev_config = CircuitBreakerConfig(
    threshold=5,
    ttl=30.0,
)
factory = circuit_breaker(dev_config)  # Uses AsyncInMemoryUnitOfWork

# Production: Redis storage for distributed state
prod_config = CircuitBreakerConfig(
    threshold=5,
    ttl=30.0,
    redis_url="redis://redis:6379/0",
)
factory = circuit_breaker(prod_config)  # Uses AsyncRedisUnitOfWork
```

#### Direct Purgatory Usage

If using Purgatory directly:

```python
from purgatory import (
    AsyncCircuitBreakerFactory,
    AsyncInMemoryUnitOfWork,
    AsyncRedisUnitOfWork,
)

# In-memory storage - single process only
factory = AsyncCircuitBreakerFactory(
    default_threshold=5,
    default_ttl=30.0,
    uow=AsyncInMemoryUnitOfWork(),
)

# Redis storage - distributed deployments
factory = AsyncCircuitBreakerFactory(
    default_threshold=5,
    default_ttl=30.0,
    uow=AsyncRedisUnitOfWork(url="redis://localhost:6379"),
)

# Important: Initialize Redis storage before use
await factory.initialize()
```

#### Redis Storage Considerations

| Consideration          | Recommendation                                                                               |
| ---------------------- | -------------------------------------------------------------------------------------------- |
| **Redis availability** | Circuit breaker becomes dependent on Redis. Consider fallback to in-memory if Redis is down. |
| **Latency**            | Each state check adds Redis round-trip. Use connection pooling.                              |
| **Key expiration**     | Purgatory handles TTL automatically.                                                         |
| **Redis cluster**      | Supported—circuit breaker keys are independent.                                              |
| **Persistence**        | Not required—circuit state is transient. Use `appendonly no`.                                |

### 5.7 Event Listeners

Purgatory provides events for circuit breaker state changes:

```python
from transcreation.resilience import (
    AsyncCircuitBreakerFactory,
    CircuitBreakerCreated,
    CircuitBreakerFailed,
    CircuitBreakerRecovered,
    ContextChanged,
)


def on_circuit_breaker_event(event: ContextChanged) -> None:
    if isinstance(event, CircuitBreakerFailed):
        logger.error(f"Circuit '{event.name}' OPENED: service is failing")
    elif isinstance(event, CircuitBreakerRecovered):
        logger.info(f"Circuit '{event.name}' CLOSED: service recovered")
    elif isinstance(event, CircuitBreakerCreated):
        logger.debug(f"Circuit '{event.name}' created")


factory = AsyncCircuitBreakerFactory(
    default_threshold=5,
    default_ttl=30.0,
    listeners=[on_circuit_breaker_event],
)
```

---

## 6. LLM API Integration Patterns

LLM APIs present unique challenges that warrant dedicated patterns.

### 6.1 Per-Provider Isolation

```{prf:property} Per-Provider Circuit Breakers
:label: prop-per-provider-isolation

**Never share circuit breakers across providers.** Each provider should have
independent failure tracking. {cite:p}`nygard2018releaseit`
```

```python
from transcreation.resilience import AsyncCircuitBreakerFactory

# All circuits share a factory (and its storage backend)
factory = AsyncCircuitBreakerFactory(default_threshold=3, default_ttl=60.0)

# Each provider gets its own circuit breaker
openai_breaker = await factory.get_breaker("llm:openai")
anthropic_breaker = await factory.get_breaker("llm:anthropic")
google_breaker = await factory.get_breaker("llm:google")
```

```{mermaid}
:zoom:

flowchart TB
    subgraph Shared Storage
        S[(AsyncInMemoryUnitOfWork)]
    end

    subgraph Independent Circuits
        CB1[openai circuit<br/>State: OPEN]
        CB2[anthropic circuit<br/>State: CLOSED]
        CB3[google circuit<br/>State: CLOSED]
    end

    CB1 --> S
    CB2 --> S
    CB3 --> S

    subgraph Requests
        R1[Translation Request]
    end

    R1 -->|OpenAI fails fast| CB1
    R1 -->|Fallback succeeds| CB2

    style CB1 fill:#FFB6C1
    style CB2 fill:#90EE90
    style CB3 fill:#90EE90
```

### 6.2 Exception Classification for LLMs

```{prf:criterion} LLM Error Classification
:label: crit-llm-error-classification

| HTTP Status | LLM Meaning         | Count as Failure? | Retry? | Notes                       |
| ----------- | ------------------- | ----------------- | ------ | --------------------------- |
| 400         | Invalid request     | **No**            | No     | Fix request, don't count    |
| 401         | Invalid API key     | **No**            | No     | Fix credentials             |
| 403         | Quota exceeded      | **No**            | No     | Wait for quota reset        |
| 429         | Rate limited        | **Yes**           | Yes    | Respect Retry-After header  |
| 500         | Server error        | **Yes**           | Yes    | Provider issue, may recover |
| 502         | Bad gateway         | **Yes**           | Yes    | Infrastructure issue        |
| 503         | Service unavailable | **Yes**           | Yes    | Maintenance or overload     |
| Timeout     | No response         | **Yes**           | Yes    | Network or slow response    |
```

```python
CB_CONFIG = CircuitBreakerConfig(
    threshold=3,
    ttl=30.0,
    exclude=[
        LLMAuthenticationError,
        LLMInvalidRequestError,
        LLMQuotaExceededError,
        LLMContentPolicyError,
    ],
)
```

### 6.3 Composition with Semaphores

For LLM APIs, you typically need three layers of protection:

```python
from purgatory.domain.model import OpenedState

LLM_SEMAPHORE = asyncio.Semaphore(10)
factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)


async def call_llm_with_protection(prompt: str) -> str:
    # Retry config with OpenedState in never_retry_on
    retry_config = RetryConfig(never_retry_on=(OpenedState,))
    retry = build_retry_decorator(retry_config)

    @retry  # OUTER: Retry wraps everything
    async def _call() -> str:
        breaker = await factory.get_breaker("llm:openai")
        async with breaker:  # INNER: Circuit breaker
            async with LLM_SEMAPHORE:  # INNERMOST: Semaphore
                return await _raw_llm_call(prompt)

    return await _call()
```

The order from outer to inner:

1. **Retry**: Handles transient failures, aborts on `OpenedState`
2. **Circuit Breaker**: Prevents {term}`Cascading Failure`, raises `OpenedState`
   when open
3. **Semaphore**: Limits concurrent requests

### 6.4 Fallback Strategy: Fail Fast (No Provider Fallback)

```{prf:property} Transcreation Fallback Strategy
:label: prop-fail-fast-no-fallback

Transcreation **does NOT implement automatic provider fallback** when a circuit
breaker opens. Instead, it **fails fast** with `OpenedState` exception.
```

**Rationale:**

- **Simpler implementation** — no complex fallback chain management
- **Clearer error handling** — caller knows exactly which provider failed
- **Explicit control** — caller can decide to use a different provider if
  needed
- **No hidden behavior** — system behavior is predictable and debuggable

**What happens when circuit trips:**

1. `OpenedState` exception raised immediately (no downstream call)
2. Retry aborts (`OpenedState` in `never_retry_on`)
3. Exception propagates to caller
4. Caller decides: retry later, use different provider, or return error to user

**If you need provider fallback**, implement it at a higher level:

```python
from purgatory.domain.model import OpenedState

from transcreation.services.generative_service import GenerativeService


async def translate_with_fallback(
    service: GenerativeService,
    text: str,
    models: list[SupportedModel],
) -> str:
    """Example: caller-level fallback (NOT built into GenerativeService)."""
    for model in models:
        try:
            return await service.agenerate(messages=[...], model=model)
        except OpenedState:
            logger.warning(f"Circuit open for {model}, trying next")
            continue

    raise LLMServiceUnavailableError("All providers unavailable")
```

### 6.5 LLM Circuit Breaker Decision Matrix

| Scenario                        | threshold | ttl  | exclude                             |
| ------------------------------- | --------- | ---- | ----------------------------------- |
| **High-volume translation**     | 5         | 30s  | Auth, Invalid, Quota, ContentPolicy |
| **Critical single requests**    | 3         | 60s  | Auth, Invalid, Quota                |
| **Batch processing (tolerant)** | 10        | 120s | Auth, Invalid, Quota, ContentPolicy |
| **Real-time chat**              | 2         | 15s  | Auth, Invalid                       |

---

## 7. Circuit Breaker Anti-Patterns

```{prf:remark} Why Anti-Patterns Matter
:label: rem-cb-antipatterns-importance

Understanding these anti-patterns is essential **before** implementing circuit
breakers. Naive implementations can **worsen {term}`Cascading Failure`** rather
than prevent them. {cite:p}`google2017sre-cascading`

These are not edge cases—they are common mistakes that have caused production
outages at scale.
```

### 7.1 Circuit Breaker Without Retry

```{prf:property} The Complementary Relationship
:label: prop-cb-needs-retry

**Problem:** Treating every failure as a circuit breaker failure, even transient
ones.

Without retry, a single network blip counts against the circuit breaker
threshold. If you have a threshold of 5, five network blips in a minute (which
is normal in distributed systems) will open the circuit—even though the
downstream service is perfectly healthy. {cite:p}`nygard2018releaseit`
```

```python
# ❌ Bad: No retry, every failure counts
factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)


async def call_service():
    breaker = await factory.get_breaker("downstream")
    async with breaker:
        return await downstream.request()
```

```python
# ✅ Good: Retry handles transient failures before they count
from purgatory.domain.model import OpenedState

factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)
retry_config = RetryConfig(max_attempts=3, never_retry_on=(OpenedState,))


async def call_service():
    @build_retry_decorator(retry_config)
    async def _call():
        breaker = await factory.get_breaker("downstream")
        async with breaker:
            return await downstream.request()

    return await _call()
```

### 7.2 Retry Without Circuit Breaker (Retry Storms)

```{prf:observation} Retry Amplification Without Circuit Breaker
:label: obs-retry-storms

**Problem:** When a service fails, all clients keep retrying, overwhelming it
further.

This is the **retry amplification** problem. Without a circuit breaker, retries
continue indefinitely, multiplying load on the failing service and preventing
recovery. {cite:p}`google2017sre-cascading`
```

```{mermaid}
:zoom:

graph TD
    subgraph Without Circuit Breaker
        S[Service Down]
        C1[Client 1: Retry, Retry, Retry]
        C2[Client 2: Retry, Retry, Retry]
        C3[Client 3: Retry, Retry, Retry]
        C4[Client N: Retry, Retry, Retry]

        C1 -->|3x load| S
        C2 -->|3x load| S
        C3 -->|3x load| S
        C4 -->|3x load| S

        S -->|N * 3 = Retry Storm| Overwhelmed[Service Cannot Recover]
    end

    style Overwhelmed fill:#FF6B6B
```

**Solution:** Circuit breaker stops the retry storm. Once open, all clients fail
fast, giving the service breathing room to recover.

### 7.3 Shared Circuit Breaker Across Unrelated Services

```{prf:property} Fault Isolation Violation
:label: prop-fault-isolation-violation

**Problem:** One circuit breaker for multiple downstream dependencies.

If Service A and Service B share a circuit breaker, failures in Service A will
open the circuit and block requests to healthy Service B. This violates
{term}`Fault Isolation`. {cite:p}`nygard2018releaseit`
```

```python
# ❌ Bad: Using the SAME circuit breaker name for different services
factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)


async def call_service_a():
    breaker = await factory.get_breaker("shared")  # Same name!
    async with breaker:
        return await service_a.request()


async def call_service_b():
    breaker = await factory.get_breaker("shared")  # Same name = shared state!
    async with breaker:
        return await service_b.request()
```

```python
# ✅ Good: Per-dependency circuit breakers (different names)
factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)


async def call_service_a():
    breaker = await factory.get_breaker("service_a")  # Unique name
    async with breaker:
        return await service_a.request()


async def call_service_b():
    breaker = await factory.get_breaker("service_b")  # Different name = isolated
    async with breaker:
        return await service_b.request()
```

### 7.4 Wrong Threshold Configuration

```{prf:criterion} Threshold Selection Criteria
:label: crit-threshold-selection

**Too Low Threshold:**

-   Circuit opens on minor fluctuations
-   False positives cause unnecessary failures
-   System becomes overly sensitive ("flapping")

**Too High Threshold:**

-   Circuit takes too long to open
-   Resources exhausted before protection kicks in
-   {term}`Cascading Failure` still possible

**Solution:** Base thresholds on:

-   Normal failure rate (baseline)
-   SLO requirements
-   Recovery time of downstream service
-   Empirical observation and tuning
```

### 7.5 No Fallback Strategy

```{prf:property} Graceful Degradation
:label: prop-graceful-degradation

**Problem:** Circuit breaker opens, requests fail fast... and users see errors.

{term}`Fail-Fast` is better than failing slow, but **failing with a fallback is
better than failing**. {cite:p}`netflix2017hystrix`
```

```python
# ❌ Bad: No fallback
factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)


async def get_recommendations():
    breaker = await factory.get_breaker("recommendations")
    async with breaker:
        return await recommendation_service.get()
```

```python
# ✅ Good: Fallback provides graceful degradation
from purgatory.domain.model import OpenedState

factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)


async def get_recommendations_safe(user_id: str) -> list[Recommendation]:
    breaker = await factory.get_breaker("recommendations")
    try:
        async with breaker:
            return await recommendation_service.get(user_id)
    except OpenedState:
        cached = await cache.get(f"recommendations:{user_id}")
        if cached:
            return cached
        return DEFAULT_RECOMMENDATIONS
```

### 7.6 Ignoring Circuit Breaker State in Monitoring

```{prf:observation} Operational Visibility
:label: obs-operational-visibility

**Problem:** Circuit breaker opens, nobody notices, users suffer.

**Solution:** Alert on circuit state transitions. An open circuit is an
operational event that may require intervention.
{cite:p}`google2017sre-cascading`
```

```python
from transcreation.resilience import ContextChanged


def on_circuit_event(name: str, event_type: str, event: object) -> None:
    if isinstance(event, ContextChanged):
        state_values = {"closed": 0, "opened": 1, "half_opened": 2}
        metrics.gauge(f"circuit_breaker.{name}.state", state_values.get(event.state, -1))

        if event.state == "opened":
            alerting.send_alert(
                severity="warning",
                message=f"Circuit breaker '{name}' is OPEN",
                runbook="https://runbook/circuit-breaker-open",
            )


factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)
factory.add_listener(on_circuit_event)
```

---

## 8. Best Practices from Google SRE and Industry

### 8.1 Circuit Breaker Per Dependency

```{prf:property} Per-Dependency Isolation
:label: prop-per-dependency-isolation

Each external dependency should have its own circuit breaker. This provides
**{term}`Fault Isolation`**—a failing database doesn't affect your ability to
call a healthy cache. {cite:p}`nygard2018releaseit,google2017sre-cascading`
```

### 8.2 Consider Slow Calls as Failures

```{prf:property} Slow Calls as Failures
:label: prop-slow-calls-failures

A service that responds in 10 seconds instead of 100ms is effectively failing
from the caller's perspective. The Transcreation implementation counts timeouts
as failures automatically (via `httpx.TimeoutException`).
{cite:p}`resilience4j2024docs`
```

### 8.3 Integrate with Load Shedding

```{prf:property} Load Shedding Integration
:label: prop-load-shedding

Circuit breakers complement **load shedding** at the service level. When your
service is overloaded, shed load proactively rather than waiting for downstream
failures. {cite:p}`google2017sre-overload`
```

```python
factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)


async def handle_request(request):
    if current_load > max_capacity * 0.8:
        raise ServiceOverloaded("Shedding load")

    breaker = await factory.get_breaker("downstream")
    async with breaker:
        return await downstream.process(request)
```

### 8.4 Test Circuit Breaker Behavior

Chaos engineering should verify that:

1. Circuit opens when expected
2. Requests fail fast when open
3. Half-open probing works correctly
4. Circuit closes after recovery
5. Fallbacks activate properly

```python
from purgatory.domain.model import OpenedState


async def test_circuit_breaker_opens():
    factory = AsyncCircuitBreakerFactory(default_threshold=3, default_ttl=60.0)
    breaker = await factory.get_breaker("test-service")

    for _ in range(3):
        with pytest.raises(ConnectionError):
            async with breaker:
                raise ConnectionError("Service down")

    # Circuit should now be open - next call fails fast
    with pytest.raises(OpenedState):
        async with breaker:
            pass  # Never reached - circuit is open
```

---

## 9. Implementation Considerations

### 9.1 Thread Safety

Circuit breaker state is shared across all requests. In concurrent environments,
state transitions must be thread-safe. The Purgatory library handles concurrency
internally via `AsyncInMemoryUnitOfWork` (for single-process) or
`AsyncRedisUnitOfWork` (for distributed deployments).
{cite:p}`resilience4j2024docs,polly2024docs`

### 9.2 Timeout Integration

Circuit breakers should respect and integrate with timeouts. A call that times
out is a failure from the circuit breaker's perspective. The Transcreation
implementation automatically counts `httpx.TimeoutException` as failures.

### 9.3 Bulkhead Integration

```{prf:property} Bulkhead Complementarity
:label: prop-bulkhead-integration

Circuit breakers protect against {term}`Cascading Failure`. **{term}`Bulkhead`**
(resource isolation) provide complementary protection by limiting concurrent
calls to a dependency. {cite:p}`nygard2018releaseit`
```

```python
class ResilientClient:
    def __init__(self):
        self.factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)
        self.bulkhead = asyncio.Semaphore(10)

    async def call_service(self, request):
        breaker = await self.factory.get_breaker("service_a")
        async with self.bulkhead:
            async with breaker:
                return await self.service.request(request)
```

### 9.4 Fallback Strategies

| Strategy                | Description                                   | Use Case             |
| ----------------------- | --------------------------------------------- | -------------------- |
| **Cached value**        | Return last known good response               | Read operations      |
| **Default value**       | Return a sensible default                     | Optional features    |
| **Stub response**       | Return empty/minimal response                 | Graceful degradation |
| **Queue for later**     | Accept request, process when service recovers | Write operations     |
| **Alternative service** | Call backup/secondary service                 | Critical operations  |

---

## 10. Monitoring and Observability

### 10.1 Key Metrics

| Metric                        | Description                                   | Alert Threshold       |
| ----------------------------- | --------------------------------------------- | --------------------- |
| **circuit_breaker.state**     | Current state (0=closed, 1=open, 2=half_open) | State = open          |
| **circuit_breaker.calls**     | Total calls per state                         | —                     |
| **circuit_breaker.failures**  | Failure count in current window               | Approaching threshold |
| **circuit_breaker.opens**     | Count of open transitions                     | > 0 in 5 minutes      |
| **circuit_breaker.fallbacks** | Fallback activations                          | High rate             |

### 10.2 Prometheus Integration

```python
from prometheus_client import Counter, Gauge

circuit_state = Gauge(
    "circuit_breaker_state",
    "Current circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["circuit_name"],
)

circuit_transitions = Counter(
    "circuit_breaker_transitions_total",
    "Total circuit breaker state transitions",
    ["circuit_name", "from_state", "to_state"],
)

circuit_failures = Counter(
    "circuit_breaker_failures_total",
    "Total failures counted by circuit breaker",
    ["circuit_name"],
)


def on_circuit_event(name: str, event_type: str, event: object) -> None:
    if isinstance(event, ContextChanged):
        state_values = {"closed": 0, "opened": 1, "half_opened": 2}
        circuit_state.labels(circuit_name=name).set(state_values.get(event.state, -1))
        circuit_transitions.labels(
            circuit_name=name,
            from_state=event.previous_state or "unknown",
            to_state=event.state,
        ).inc()
    elif isinstance(event, CircuitBreakerFailed):
        circuit_failures.labels(circuit_name=name).inc()


factory = AsyncCircuitBreakerFactory(default_threshold=5, default_ttl=30.0)
factory.add_listener(on_circuit_event)
```

### 10.3 Structured Logging

```python
import structlog

from transcreation.resilience import ContextChanged

logger = structlog.get_logger()


def on_circuit_event(name: str, event_type: str, event: object) -> None:
    if isinstance(event, ContextChanged):
        logger.warning(
            "circuit_breaker_state_change",
            circuit_name=name,
            new_state=event.state,
            event_type="circuit_breaker",
        )
```

### 10.4 Dashboard Essentials

A circuit breaker dashboard should show:

1. **State timeline**: When did circuits open/close?
2. **Failure rate**: Trending toward threshold?
3. **Open duration**: How long are circuits staying open?
4. **Recovery success**: Are half-open probes succeeding?
5. **Fallback usage**: Are fallbacks hiding problems?

### 10.5 Alerting Strategy

```python
from transcreation.resilience import ContextChanged


# Alert on state changes via listener callback
def on_circuit_event(name: str, event_type: str, event: object) -> None:
    if isinstance(event, ContextChanged) and event.state == "opened":
        alert(
            severity="warning",
            message=f"Circuit '{name}' is OPEN",
            runbook="https://runbook/circuit-breaker-open",
        )


# Alert on flapping circuits (track opens over time in your metrics system)
# Example: Query Prometheus for circuit open transitions in last hour
# if circuit_opens_last_hour > 3:
#     alert(severity="high", message=f"Circuit '{name}' flapping")
```

---

## 11. Putting It All Together: Building a Resilient LLM Service

Let's apply everything from this guide to build a **production-ready LLM
translation service** that handles multiple providers with proper resilience.

### 11.1 The Scenario

Your application needs to translate text using LLM APIs. You have multiple
providers (OpenAI, Anthropic) and need to handle:

- **Rate limiting**: Providers enforce request limits
- **Transient failures**: Network issues, temporary 5xx errors
- **Systemic failures**: Provider outages, quota exhaustion
- **Cost optimization**: Don't waste money retrying impossible requests

**Your mission**: Build resilient LLM integration that maximizes availability
while protecting both your service and the providers.

### 11.2 Exception Hierarchy

First, we create custom exceptions that encode our resilience strategy:

```python
class LLMError(Exception):
    """Base exception for LLM API errors."""


class LLMTransientError(LLMError):
    """Transient error that may succeed on retry.

    RETRYABLE: Yes
    CIRCUIT BREAKER: Counts as failure
    """


class LLMPermanentError(LLMError):
    """Permanent error that will not succeed on retry.

    RETRYABLE: No
    CIRCUIT BREAKER: Does NOT count as failure (excluded)
    """


class LLMRateLimitError(LLMTransientError):
    """Rate limit exceeded (HTTP 429).

    RETRYABLE: Yes - rate limit will reset
    """

    def __init__(self, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after}s" if retry_after else "Rate limited")


class LLMServiceUnavailableError(LLMTransientError):
    """Service temporarily unavailable (HTTP 503).

    RETRYABLE: Yes - server will recover
    """


class LLMAuthenticationError(LLMPermanentError):
    """Authentication failed (HTTP 401).

    RETRYABLE: No - credentials are invalid
    """


class LLMInvalidRequestError(LLMPermanentError):
    """Bad request payload (HTTP 400).

    RETRYABLE: No - request is malformed
    """


class LLMContentPolicyError(LLMPermanentError):
    """Content blocked by safety filters.

    RETRYABLE: No - content violates policy
    """


class LLMQuotaExceededError(LLMPermanentError):
    """Monthly quota exceeded (HTTP 403).

    RETRYABLE: No - quota won't reset mid-request
    """
```

### 11.3 Per-Provider Circuit Breakers

Each provider gets its own circuit breaker for **{term}`Fault Isolation`**:

```python
import structlog

from transcreation.resilience import (
    AsyncCircuitBreakerFactory,
    ContextChanged,
)

logger = structlog.get_logger()


def on_circuit_event(name: str, event_type: str, event: object) -> None:
    if isinstance(event, ContextChanged):
        logger.warning(
            "circuit_breaker_state_change",
            circuit=name,
            new_state=event.state,
        )
        if event.state == "opened":
            metrics.increment(f"circuit_breaker.{name}.opened")
        elif event.state == "closed":
            metrics.increment(f"circuit_breaker.{name}.closed")


# Create factory with shared configuration
factory = AsyncCircuitBreakerFactory(
    default_threshold=3,
    default_ttl=60.0,
    exclude=[LLMPermanentError],  # 4xx errors don't count as failures
)
factory.add_listener(on_circuit_event)

# Each provider gets its own circuit breaker (different names = isolated state)
openai_breaker = await factory.get_breaker("llm:openai")
anthropic_breaker = await factory.get_breaker("llm:anthropic")


# Usage pattern with retry + circuit breaker
async def call_openai(prompt: str) -> str:
    breaker = await factory.get_breaker("llm:openai")
    async with breaker:
        return await openai_client.chat(prompt)
```

### 11.4 What This Implementation Achieves

| Principle                                 | How It's Applied                                         |
| ----------------------------------------- | -------------------------------------------------------- |
| **{term}`Fail-Fast` on systemic failure** | Circuit breaker opens after 3 consecutive failures       |
| **Retry transient errors**                | Retry wrapper handles 429, 503, network errors           |
| **Proper wrapping order**                 | Retry (outer) wraps circuit breaker (inner)              |
| **{term}`Fault Isolation`**               | OpenAI failure doesn't affect Anthropic                  |
| **Exclude permanent errors**              | 401, 400 don't count against circuit breaker             |
| **Fallback strategy**                     | Fails fast; caller implements fallback (see Section 6.4) |
| **Rate limiting protection**              | Semaphore limits concurrent requests                     |
| **Observability**                         | State change callbacks, retry logging                    |

---

## 12. Summary: Key Takeaways

```{prf:remark} Key Takeaways
:label: rem-cb-key-takeaways

1. **Circuit breakers prevent {term}`Cascading Failure`**—by {term}`Fail-Fast`
   when downstream is unhealthy
   {cite:p}`nygard2018releaseit,fowler2014circuitbreaker`

2. **Work WITH retry, not instead of**—retry handles transient failures, circuit
   breaker handles systemic failures {cite:p}`microsoft2023circuitbreaker`

3. **One circuit breaker per dependency**—for proper {term}`Fault Isolation`
   {cite:p}`nygard2018releaseit`

4. **Exclude permanent errors**—4xx errors shouldn't count against the threshold

5. **Provide fallback responses**—{term}`Fail-Fast` is good; failing with a
   useful response is better {cite:p}`netflix2017hystrix`

6. **Monitor state transitions**—an open circuit is an operational event
   {cite:p}`google2017sre-cascading`

7. **Test circuit breaker behavior**—including open, half-open, and close
   transitions

8. **Integrate with {term}`Bulkhead`**—for comprehensive resource protection
   {cite:p}`nygard2018releaseit`
```

---

## 13. Quick Reference: Retry + Circuit Breaker Decision Matrix

| Scenario                            | Use Retry? | Use Circuit Breaker? | Notes                           |
| ----------------------------------- | ---------- | -------------------- | ------------------------------- |
| Network timeout (isolated)          | Yes        | No                   | Transient, retry will handle it |
| Service returning 503 consistently  | Yes        | Yes                  | Combined protection             |
| Database connection reset           | Yes        | Maybe                | Depends on frequency            |
| Service completely down             | Limited    | Yes                  | Circuit should open fast        |
| Rate limited (429 with Retry-After) | Yes        | No                   | Honor Retry-After header        |
| Service intermittently slow         | Maybe      | Yes                  | Slow calls count as failures    |
| External API with hard SLA          | Yes        | Yes                  | Full resilience stack           |
| Internal microservice call          | Yes        | Yes                  | Prevent internal cascades       |
| Fire-and-forget async operation     | Yes        | Optional             | DLQ might be more appropriate   |

---

## 14. References

### Primary Sources

- **Martin Fowler**:
  [CircuitBreaker](https://martinfowler.com/bliki/CircuitBreaker.html) — The
  original pattern definition.

- **Google SRE Book, Chapter 22**:
  [Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/)
  — The definitive guide on preventing cascading failures in distributed
  systems.

- **Google SRE Book, Chapter 21**:
  [Handling Overload](https://sre.google/sre-book/handling-overload/) — Covers
  load shedding and graceful degradation.

- **Microsoft Azure Architecture Center**:
  [Circuit Breaker Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
  — Comprehensive pattern documentation with implementation guidance.

### Books

- Nygard, M. T. (2018). _Release It! Design and Deploy Production-Ready
  Software_ (2nd ed.). Pragmatic Bookshelf. — Essential reading on stability
  patterns including circuit breakers, bulkheads, and timeout.

### Libraries

- [Resilience4j](https://resilience4j.readme.io/) — Java circuit breaker
  library with comprehensive features.

- [Polly](https://github.com/App-vNext/Polly) — .NET resilience library.

- [Netflix Hystrix](https://github.com/Netflix/Hystrix) (archived) — Original
  inspiration for many circuit breaker implementations.
