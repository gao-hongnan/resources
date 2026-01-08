# Retry Patterns in Distributed Systems

```{epigraph}
Design with skepticism, and you will achieve resilience.

-- Michael T. Nygard, *Release It!* {cite:p}`nygard2018releaseit`
```

---

## Definitions

Before diving in, let's establish precise definitions for terms used throughout
this guide. These definitions are referenced via `{term}` links.

```{glossary}
Transient Failure
    A temporary environmental issue—network congestion, server overload, GC
    pause, brief outage—where the **request is valid** but the environment
    couldn't handle it *right now*. Time passing naturally resolves the issue.
    Contrast with {term}`Permanent Failure`.

Permanent Failure
    An inherent problem with the **request itself**—invalid credentials,
    malformed data, missing resource. No amount of waiting or retrying will fix
    it; you must fix the request. Contrast with {term}`Transient Failure`.

Idempotency
    The property of an operation that produces the **same result** whether
    executed once or multiple times. `SET user.email = 'x'` is idempotent
    (running it 5× leaves email as 'x'). `INCREMENT balance BY 100` is **not**
    idempotent (running it 5× adds $500). Retries are only safe for idempotent
    operations. See [Idempotency Requirements](#idempotency-requirements).

Exponential Backoff
    A retry strategy where wait time **grows exponentially** with each attempt:
    $t = t_{\text{base}} \times b^{n}$, where $b$ is typically 2 (doubling).
    Prevents overwhelming a recovering service. Always combined with
    {term}`Jitter` in production.

Jitter
    **Random variation** added to retry delays to spread requests over time.
    Without jitter, all clients retry at the same instant, causing
    {term}`Thundering Herd`. See [Backoff Strategy Deep Dive](#backoff-strategy-deep-dive).

Thundering Herd
    When many clients retry **simultaneously** after a service recovers,
    immediately overwhelming it again. Caused by fixed retry intervals without
    {term}`Jitter`. See [Anti-Patterns: Thundering Herd](#2-thundering-herd-synchronized-retries).

Retry Amplification
    The **multiplicative effect** when multiple system layers each implement
    retries. With $n$ layers and $r$ retries per layer: $\text{total} = r^n$.
    Four layers × 4 retries = 256 requests from one user click.
    See [Anti-Patterns: Retry Amplification](#1-retry-amplification-the-cascade-effect).
```

```{admonition} Prerequisites
:class: note

This guide assumes familiarity with:
- **Async Python** (`async`/`await`, `asyncio`)
- **HTTP status codes** (4xx vs 5xx semantics)
- **Basic distributed systems concepts** (network partitions, partial failures)
```

---

## Overview

Retries are a fundamental resilience pattern for handling
{term}`transient failures <Transient Failure>` in distributed systems. A request
that fails now may succeed moments later due to network blips, temporary
overload, or service restarts. {cite:p}`google2017sre-cascading`

```{prf:observation} The Google SRE Insight
:label: obs-not-all-failures-permanent

**Not all failures are permanent.** Retries exploit this asymmetry—but naive
implementations can **amplify failures** rather than mitigate them.
{cite:p}`nygard2018releaseit`
```

```{admonition} Why Resilience Matters
:class: note

Peter Deutsch's [Eight Fallacies of Distributed Computing](https://en.wikipedia.org/wiki/Fallacies_of_distributed_computing) remind us that networks are unreliable, latency is not zero, and topology changes constantly. Every assumption about network reliability is false—resilience patterns like retry exist precisely because these fallacies describe reality. {cite:p}`deutsch1994fallacies`
```

## Why Retry Matters for Resilience

In distributed systems, **partial failures are the norm, not the exception**.
Your database might be reachable but slow. Your payment provider might timeout
but still process the transaction. The network might drop packets randomly.

```{prf:definition} Failure Classification
:label: def-failure-classification

Failures in distributed systems fall into exactly two categories:

1. **{term}`Transient Failure`**: The request is valid; the environment failed.
   *Retry makes sense.*

2. **{term}`Permanent Failure`**: The request is flawed; the server correctly
   rejected it. *Retry is wasteful.*

The fundamental question when an error occurs:

> "If I send the **exact same request** again, could it possibly succeed?"

If yes → transient. If no → permanent.
```

Retries are your **first line of defense** against transient failures. A request
that fails at 10:00:00.000 might succeed at 10:00:00.500—the network route
cleared, the overloaded server caught up, the GC pause ended.

But implementing retries incorrectly can transform a minor hiccup into a
catastrophic cascade. Naive retry logic can:

- **Amplify load** on an already struggling service (see
  {term}`Retry Amplification`)
- **Create thundering herds** that prevent recovery (see
  {term}`Thundering Herd`)
- **Waste resources** retrying errors that will never succeed
- **Increase latency** for operations that should fail fast

```{prf:remark} Document Structure
:label: rem-doc-structure

This guide proceeds as follows:

1. **[Implementation](#implementation)** — Quick reference for the retry
   decorator API
2. **[How It Works](#how-it-works)** — Sequence diagram and decision flow
3. **[Error Classification](#retryable-vs-non-retryable-errors)** — Which errors
   to retry (the critical decision)
4. **[Best Practices](#google-sre-best-practices)** — Google SRE recommendations
5. **[Backoff Strategies](#backoff-strategy-deep-dive)** — Mathematical
   foundations of jitter
6. **[Idempotency](#idempotency-requirements)** — Why retries require idempotent
   operations
7. **[Anti-Patterns](#anti-patterns-to-avoid)** — What NOT to do (read this!)
8. **[Practical Examples](#putting-it-all-together-building-a-resilient-user-service)** —
   Complete working code
```

---

## Implementation

This project provides a simple retry decorator wrapper around
[tenacity](https://tenacity.readthedocs.io/) that implements Google SRE best
practices out of the box.

### Configuration

```python
from leitmotif.resilience.retry import RetryConfig, retry

config = RetryConfig(
    max_attempts=3,           # Total attempts including initial (3 = 1 try + 2 retries)
    wait_min=1.0,             # Minimum wait time in seconds (default: 1.0)
    wait_max=60.0,            # Maximum wait time in seconds (default: 60.0)
    multiplier=1.0,           # Wait multiplier (default: 1.0)
    exp_base=2.0,             # Exponential base (default: 2.0)
    retry_on_exceptions=None, # Exception types to retry (None = all)
    never_retry_on=None,      # Exception types to never retry (takes precedence)
    reraise=True,             # Reraise exception after exhausting retries
)
```

### Basic Usage

```python
from leitmotif.resilience.retry import RetryConfig, retry

@retry(
    config=RetryConfig(
        max_attempts=5,
        wait_min=0.5,
        wait_max=30.0,
        retry_on_exceptions=(httpx.TimeoutException, httpx.NetworkError),
    )
)
async def deposit() -> dict:
    ...
```

---

## How It Works

The sequence diagram below shows the retry decorator in action. Pay attention to
the **decision point**: when an error occurs, the decorator must decide whether
to retry or fail immediately. This decision—{term}`Transient Failure` vs.
{term}`Permanent Failure`—is the foundation of correct retry logic (detailed in
[Retryable vs Non-Retryable Errors](#retryable-vs-non-retryable-errors)).

```{mermaid}
sequenceDiagram
    participant C as Client
    participant R as @retry Decorator
    participant F as Function
    participant S as Service

    C->>R: Call decorated function

    loop Until success or max_attempts
        R->>F: Execute function
        F->>S: Make request

        alt Success
            S-->>F: 200 OK
            F-->>R: Return result
            R-->>C: Return result
        else Transient Error (retry_on_exceptions)
            S-->>F: 503 Service Unavailable
            F-->>R: Raise exception
            R->>R: Wait (exponential backoff + jitter)
            Note over R: wait = random(0, min(wait_max, wait_min × 2^attempt))
        else Non-Retryable Error (never_retry_on)
            S-->>F: 401 Unauthorized
            F-->>R: Raise exception
            R-->>C: Raise immediately (no retry)
        end
    end

    Note over R,C: After max_attempts exhausted
    R-->>C: Raise final exception (if reraise=True)
```

```{prf:remark} The Critical Question
:label: rem-critical-question

The diagram reveals the question at the heart of every retry:

> **"Is this error transient or permanent?"**

Getting this classification wrong is the difference between a resilient system
and one that amplifies failures ({term}`Retry Amplification`). The next section
explores this in depth.
```

---

## Retryable vs Non-Retryable Errors

The most critical decision in retry logic is determining **which errors to
retry**. Get this wrong, and you either waste resources retrying impossible
operations or give up too early on recoverable failures.

```{prf:criterion} The Retry Decision Test
:label: crit-retry-decision

When an error occurs, ask:

> **"If I send the exact same request again, could it possibly succeed?"**

- **Yes** → {term}`Transient Failure` → **Retry**
- **No** → {term}`Permanent Failure` → **Fail fast**

This single question cuts through the complexity of error classification.
```

### Environment Problems vs Request Problems

```{prf:property} Retryable Error Characteristics
:label: prop-retryable-errors

**Retryable errors** ({term}`Transient Failure`) occur when the problem is with
the **environment**, not your request:

- ✅ Your request is perfectly valid
- ✅ It just hit bad timing (network congestion, server overload, GC pause)
- ✅ Time passing or trying a different server naturally resolves the issue
- ✅ **Retry makes sense**
```

```{prf:property} Non-Retryable Error Characteristics
:label: prop-non-retryable-errors

**Non-retryable errors** ({term}`Permanent Failure`) occur when the problem is
**inherent to your request**:

- ❌ Your request is fundamentally flawed (wrong credentials, invalid data,
  missing resource)
- ❌ The server correctly rejected it based on its content
- ❌ No amount of waiting or retrying will fix it—you must fix the REQUEST
  itself
- ❌ **Retrying is wasteful and wrong**
```

### Concrete Scenarios

**Scenario A: Network Timeout** ✅ RETRY

```text
Your request:    GET /users/123 (valid request, valid auth token)
What happened:   Network congestion dropped your packet
Same request
in 1 second:     Would succeed (network cleared)
Verdict:         RETRY—the environment failed, not your request
```

**Scenario B: Authentication Error (401)** ❌ DON'T RETRY

```text
Your request:    GET /users/123 (with expired/invalid token)
What happened:   Server rejected your credentials
Same request
in 1 second:     Would still fail (token doesn't magically become valid)
Verdict:         DON'T RETRY—your request is the problem
```

**Scenario C: Rate Limited (429)** ✅ RETRY (with care)

```text
Your request:    GET /users/123 (valid request, valid auth)
What happened:   You've made too many requests too fast
Same request
after waiting:   Would succeed (rate limit window resets)
Verdict:         RETRY—but respect the Retry-After header
```

**Scenario D: Not Found (404)** ❌ DON'T RETRY

```text
Your request:    GET /users/999999 (valid request, valid auth)
What happened:   User 999999 doesn't exist
Same request
in 1 second:     Would still fail (user won't materialize)
Verdict:         DON'T RETRY—the resource genuinely doesn't exist
```

### HTTP Status Code Classification

#### 4xx Client Errors

Most 4xx errors are **non-retryable**—they indicate something wrong with your
request.

| Status Code           | Meaning                     | Retryable? | Reason                                                          |
| --------------------- | --------------------------- | ---------- | --------------------------------------------------------------- |
| 400 Bad Request       | Invalid input               | ❌ No      | Malformed request won't become valid                            |
| 401 Unauthorized      | Missing/invalid credentials | ❌ No      | Credentials won't magically appear                              |
| 403 Forbidden         | Access denied               | ❌ No      | Permissions won't change mid-request                            |
| 404 Not Found         | Resource doesn't exist      | ❌ No      | Resource won't materialize                                      |
| 408 Request Timeout   | Server timed out waiting    | ✅ Yes     | Transient; retry after delay (respect `Retry-After` if present) |
| 409 Conflict          | State conflict              | ⚠️ Maybe   | Depends on conflict type (optimistic locking vs. business rule) |
| 422 Unprocessable     | Business rule violation     | ❌ No      | Business logic won't change                                     |
| 429 Too Many Requests | Rate limited                | ✅ Yes     | Rate limit will reset—respect `Retry-After` header              |

#### 5xx Server Errors

Most 5xx errors are **retryable**—they indicate something wrong with the server,
not your request.

| Status Code             | Meaning          | Retryable? | Reason                                                 |
| ----------------------- | ---------------- | ---------- | ------------------------------------------------------ |
| 500 Internal Error      | Server bug       | ✅ Yes     | May be transient (race condition, resource exhaustion) |
| 502 Bad Gateway         | Upstream error   | ✅ Yes     | Upstream service may recover                           |
| 503 Service Unavailable | Overloaded       | ✅ Yes     | Overload is temporary—back off aggressively            |
| 504 Gateway Timeout     | Upstream timeout | ✅ Yes     | Upstream may recover                                   |

### Exception Classification

Use `retry_on_exceptions` for an **allow-list** (only retry these):

```python
@retry(
    config=RetryConfig(
        retry_on_exceptions=(
            httpx.TimeoutException,
            httpx.NetworkError,
            ServiceUnavailableError,
        )
    )
)
async def fetch_data():
    ...
```

Use `never_retry_on` for a **deny-list** (never retry these, even if in
allow-list):

```python
@retry(
    config=RetryConfig(
        # Retry all exceptions EXCEPT these
        never_retry_on=(
            AuthenticationError,
            ValidationError,
            PermissionDeniedError,
        )
    )
)
async def process_request():
    ...
```

The `never_retry_on` **takes precedence** over `retry_on_exceptions`:

```python
@retry(
    config=RetryConfig(
        retry_on_exceptions=(Exception,),  # Retry everything...
        never_retry_on=(ValueError,),      # ...except ValueError
    )
)
async def mixed_config():
    ...
```

---

## Google SRE Best Practices

The implementation follows Google SRE recommendations for retry logic.
{cite:p}`google2017sre-cascading,google2017sre-overload`

### 1. Always Use Exponential Backoff with Jitter

```{prf:algorithm} Full Jitter (Recommended Default)
:label: alg-full-jitter

**Never use fixed retry intervals.** Fixed intervals cause {term}`Thundering
Herd`—when a service recovers, all clients retry simultaneously, immediately
overloading it again. {cite:p}`google2017sre-cascading`

The Full Jitter algorithm randomizes over the entire backoff range:

$$
t_{\text{wait}} = \mathcal{U}\bigl(0, \min(t_{\text{cap}}, t_{\text{base}} \times 2^{n})\bigr)
$$

where:
- $\mathcal{U}(a,b)$ = uniform random distribution over $[a,b]$
- $t_{\text{base}}$ = initial delay (e.g., 1 second)
- $t_{\text{cap}}$ = maximum delay cap (e.g., 60 seconds)
- $n \in \mathbb{N}_0$ = attempt number (0, 1, 2, ...)

The implementation uses `wait_random_exponential` from tenacity which implements
this algorithm. See [Backoff Strategy Deep Dive](#backoff-strategy-deep-dive)
for comparison with other jitter strategies.
```

### 2. Limit Retries Per Request

````{prf:property} Bounded Retries
:label: prop-bounded-retries

**Don't retry indefinitely.** Set a maximum number of attempts.
{cite:p}`google2017sre-cascading`

```python
RetryConfig(max_attempts=3)  # Default: 3 attempts
```

Three attempts is a common default—it provides resilience without excessive
latency.
````

### 3. Implement a Retry Budget (Server-Wide)

```{prf:property} Process-Wide Retry Budget
:label: prop-retry-budget

Individual retry limits don't prevent global overload. If every request retries
3×, and 50% fail, your backend receives **2× normal load** from retries alone.
{cite:p}`google2017sre-overload`
```

For production systems, consider implementing a **process-wide retry budget**:

```python
class RetryBudget:
    def __init__(self, max_retries_per_minute: int = 60):
        self.max_retries = max_retries_per_minute
        self.window_seconds = 60
        self.attempts: list[float] = []

    def can_retry(self) -> bool:
        now = time.time()
        self.attempts = [t for t in self.attempts if now - t < self.window_seconds]
        return len(self.attempts) < self.max_retries

    def record_retry(self) -> None:
        self.attempts.append(time.time())
```

When the retry budget is exceeded, **fail the request immediately** rather than
retrying. This protects the backend during cascading failures.

### 4. Retry at One Layer Only

````{prf:property} Single-Layer Retry Rule
:label: prop-single-layer-retry

**Avoid {term}`Retry Amplification`.** If every layer retries 3×:
{cite:p}`google2017sre-cascading`

```text
┌────────────┐      ┌──────────┐      ┌─────────┐      ┌──────────┐
│ JavaScript │─────▶│ Frontend │─────▶│ Backend │─────▶│ Database │
│    (3×)    │      │   (3×)   │      │   (3×)  │      │   (3×)   │
└────────────┘      └──────────┘      └─────────┘      └──────────┘

                    3 × 3 × 3 × 3  =  81 requests!
```

Implement retries at **one layer only**—typically the outermost layer with
sufficient context.
````

### 5. Distinguish Retryable from Non-Retryable Errors

Use `retry_on_exceptions` and `never_retry_on` to classify errors:
{cite:p}`nygard2018releaseit`

```python
# Retryable: transient failures
RETRYABLE = (
    httpx.TimeoutException,
    httpx.NetworkError,
    asyncio.TimeoutError,
    ConnectionError,
)

# Non-retryable: permanent failures
NON_RETRYABLE = (
    httpx.HTTPStatusError,  # Handle status codes separately
    ValidationError,
    AuthenticationError,
)
```

---

## Backoff Strategy Deep Dive

```{prf:remark} Section Summary
:label: rem-backoff-summary

**Recommendation**: Use **Full Jitter** ({prf:ref}`alg-full-jitter`). This is
the default in our implementation via tenacity's `wait_random_exponential`.

This section explains *why* Full Jitter is recommended. If you just need the
answer, skip to [Which Strategy Is Used?](#which-strategy-is-used). If you want
to understand the trade-offs, read on.
```

This section provides a detailed analysis of backoff strategies based on the AWS
Architecture Blog's excellent research on exponential backoff and jitter.
{cite:p}`brooker2015backoff`

### The Core Problem

When multiple clients compete for a shared resource and experience failures,
their retry behavior determines whether the system recovers or collapses.

### Exponential Backoff (Without Jitter)

```{prf:definition} Basic Exponential Backoff
:label: def-exp-backoff

The basic {term}`Exponential Backoff` formula:

$$
t_{\text{delay}} = \min\bigl(t_{\text{cap}}, t_{\text{base}} \times 2^{n}\bigr)
$$

where:

-   $t_{\text{base}}$ = initial delay (e.g., 1 second)
-   $t_{\text{cap}}$ = maximum delay cap (e.g., 60 seconds)
-   $n \in \mathbb{N}_0$ = attempt number (0, 1, 2, ...)

This produces delays: 1s, 2s, 4s, 8s, 16s, 32s, 60s, 60s, ...

**Problem**: Without {term}`Jitter`, all clients that fail at the same time will
retry at the same time → {term}`Thundering Herd`.
```

```{prf:observation} Why Thundering Herd Occurs
:label: obs-thundering-herd-cause

When a server goes down, all clients fail simultaneously. With fixed delays,
they all use the same formula—so 1,000 clients that failed at $t=0$ will ALL
retry at $t=1\text{s}$, then ALL retry again at $t=3\text{s}$, etc.

The recovering server gets hit by synchronized waves of requests, potentially
crashing again.

**Solution**: {term}`Jitter` randomizes each client's delay, spreading retries
over time instead of synchronized spikes.
```

### Three Jitter Strategies

The AWS blog analyzes three approaches to adding randomness:
{cite:p}`brooker2015backoff`

````{prf:algorithm} Full Jitter
:label: alg-full-jitter-detail

Randomize over the entire range $[0, \text{delay}]$:

$$
t_{\text{wait}} = \mathcal{U}\bigl(0, \min(t_{\text{cap}}, t_{\text{base}} \times 2^{n})\bigr)
$$

```python
def full_jitter(base: float, cap: float, attempt: int) -> float:
    exp_delay = min(cap, base * (2 ** attempt))
    return random.uniform(0, exp_delay)
```

| Pros                                       | Cons                                   |
| ------------------------------------------ | -------------------------------------- |
| Maximum spread                             | Can produce very short delays early on |
| Best at preventing {term}`Thundering Herd` |                                        |

**Verdict**: ✅ **Recommended for general use** (our default).
````

````{prf:algorithm} Equal Jitter
:label: alg-equal-jitter

Randomize over the upper half of the range:

$$
t_{\text{wait}} = \frac{t_{\text{delay}}}{2} + \mathcal{U}\Bigl(0, \frac{t_{\text{delay}}}{2}\Bigr)
$$

```python
def equal_jitter(base: float, cap: float, attempt: int) -> float:
    exp_delay = min(cap, base * (2 ** attempt))
    return exp_delay / 2 + random.uniform(0, exp_delay / 2)
```

| Pros                       | Cons                         |
| -------------------------- | ---------------------------- |
| Guarantees minimum backoff | Less spread than Full Jitter |
| Predictable lower bound    |                              |

**Verdict**: Use when you need a guaranteed minimum delay.
````

````{prf:algorithm} Decorrelated Jitter
:label: alg-decorrelated-jitter

Each wait is based on the previous wait, not the attempt number:

$$
t_{\text{wait}} = \min\bigl(t_{\text{cap}}, \mathcal{U}(t_{\text{base}}, t_{\text{prev}} \times 3)\bigr)
$$

where $t_{\text{prev}}$ is the previous wait duration. Note: the $\min$ caps the
*result* after sampling; the upper bound of $\mathcal{U}$ can exceed $t_{\text{cap}}$.

```python
def decorrelated_jitter(base: float, cap: float, prev_sleep: float) -> float:
    return min(cap, random.uniform(base, prev_sleep * 3))
```

| Pros                                    | Cons                      |
| --------------------------------------- | ------------------------- |
| Best distribution under high contention | Requires tracking state   |
| Adaptive to actual conditions           | More complex to implement |

**Verdict**: Consider for extreme contention scenarios.
````

### Strategy Comparison

```{mermaid}
:zoom:

xychart-beta
    title "Retry Delay Distribution (10 attempts)"
    x-axis [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    y-axis "Delay (seconds)" 0 --> 60
    line [1, 2, 4, 8, 16, 32, 60, 60, 60, 60]
    line [0.5, 1, 2, 4, 8, 16, 30, 30, 30, 30]
    line [0.75, 1.5, 3, 6, 12, 24, 45, 45, 45, 45]
```

| Strategy        | Spread   | Min Delay | Complexity | Best For                     |
| --------------- | -------- | --------- | ---------- | ---------------------------- |
| No Jitter       | None     | Full      | Simple     | ❌ Never use in production   |
| **Full Jitter** | Maximum  | Zero      | Simple     | ✅ General use (our default) |
| Equal Jitter    | Moderate | Half      | Simple     | When minimum delay required  |
| Decorrelated    | Adaptive | Base      | Moderate   | High-contention scenarios    |

### AWS Simulation Results

The AWS blog's simulations showed that under contention:
{cite:p}`brooker2015backoff`

1. **Full Jitter** completes work fastest in most scenarios
2. **Decorrelated Jitter** performs best under extreme contention
3. **No Jitter** performs worst—often causing system collapse

### Which Strategy Is Used?

This implementation uses **Full Jitter** via tenacity's
`wait_random_exponential`:

```python
from tenacity import wait_random_exponential

# Full Jitter: random between 0 and min(max, base * 2^attempt)
wait_random_exponential(multiplier=1, max=60)
```

This is the recommended default for most use cases.

---

## Idempotency Requirements

Recall {term}`Idempotency` from the Definitions section: an operation that
produces the same result whether executed once or multiple times.

```{prf:property} Retry Safety Requirement
:label: prop-retry-safety

**Retries are only safe for idempotent operations.**

If a request times out but actually succeeded on the server, retrying a
non-idempotent operation will execute it twice—potentially charging a customer
twice or creating duplicate records.
```

```{prf:example} Idempotent vs Non-Idempotent
:label: ex-idempotency

| Operation | Idempotent? | Why |
|-----------|-------------|-----|
| `SET user.email = "alice@example.com"` | ✅ Yes | Running 5× leaves email as "alice@example.com" |
| `INCREMENT balance BY 100` | ❌ No | Running 5× adds $500 |
| `DELETE FROM orders WHERE id = 123` | ✅ Yes | Second delete is a no-op |
| `INSERT INTO orders (...)` | ❌ No | Creates duplicate rows |
```

| Operation | Idempotent? | Safe to Retry?                     |
| --------- | ----------- | ---------------------------------- |
| GET       | ✅ Yes      | ✅ Yes                             |
| PUT       | ✅ Yes      | ✅ Yes (replaces entire resource)  |
| DELETE    | ✅ Yes      | ✅ Yes (already deleted = success) |
| POST      | ❌ No       | ⚠️ Only with idempotency key       |

For non-idempotent operations, use **idempotency keys**:

```python
@retry(config=RetryConfig(max_attempts=3))
async def create_payment(
    payment_data: dict,
    idempotency_key: str,
) -> PaymentResult:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.stripe.com/v1/payments",
            json=payment_data,
            headers={"Idempotency-Key": idempotency_key},
        )
        return PaymentResult.model_validate(response.json())
```

---

## The Retry-After Header

When a server is rate-limiting you or temporarily unavailable, it often tells
you **exactly when to come back**. This is the `Retry-After` header—the server's
explicit instruction on when retrying makes sense.

### What Is Retry-After?

`Retry-After` is an HTTP response header that tells clients how long to wait
before making another request. You'll see it in responses with:

- **429 Too Many Requests**: "You've hit your rate limit. Wait X seconds."
- **503 Service Unavailable**: "We're doing maintenance. Try again at Y time."
- **301/302/307 Redirects**: Occasionally used for temporary redirects

### The Two Formats

The header can appear in two forms:

#### Format 1: Seconds (most common)

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 120
```

Meaning: "Wait 120 seconds before retrying."

#### Format 2: HTTP-date (absolute time)

```http
HTTP/1.1 503 Service Unavailable
Retry-After: Wed, 21 Oct 2025 07:28:00 GMT
```

Meaning: "Don't retry until this specific time."

### Why You Must Respect It

Ignoring `Retry-After` is counterproductive for several reasons:

1. **Wasted compute**: Your retries will fail until the time passes
   anyway—you're burning CPU cycles for nothing
2. **Extended rate limits**: Many APIs **extend** your rate limit window if you
   keep hammering them
3. **IP blocking**: Aggressive retry behavior after a 429 can escalate to IP
   blacklisting
4. **Poor citizenship**: You're degrading the service for everyone else

**The server is telling you the optimal retry strategy—use it.**

### Implementation Patterns

#### Pattern 1: Simple Wait-and-Retry

```python
import asyncio
from datetime import datetime
from email.utils import parsedate_to_datetime

async def fetch_with_retry_after():
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")

        if response.status_code == 429:
            wait_seconds = parse_retry_after(response.headers.get("Retry-After"))
            await asyncio.sleep(wait_seconds)
            return await fetch_with_retry_after()  # Retry after waiting

        response.raise_for_status()
        return response.json()

def parse_retry_after(header_value: str | None, default: int = 60) -> float:
    """Parse Retry-After header (handles both formats)."""
    if header_value is None:
        return default

    # Try parsing as integer (seconds)
    try:
        return float(header_value)
    except ValueError:
        pass

    # Try parsing as HTTP-date
    try:
        from datetime import timezone

        retry_date = parsedate_to_datetime(header_value)
        # Handle both timezone-aware and timezone-naive datetimes
        if retry_date.tzinfo is None:
            now = datetime.now()
        else:
            now = datetime.now(retry_date.tzinfo)
        return max(0, (retry_date - now).total_seconds())
    except (TypeError, ValueError):
        return default
```

#### Pattern 2: Integrate with Retry Logic

For a more robust approach, integrate `Retry-After` with your existing retry
mechanism by raising a custom exception that carries the wait time:

```python
class RateLimitError(Exception):
    """Raised when rate limited, carries the wait time."""

    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Rate limited. Retry after {retry_after}s")

async def fetch_data(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)

        if response.status_code == 429:
            wait_time = parse_retry_after(response.headers.get("Retry-After"))
            raise RateLimitError(retry_after=wait_time)

        response.raise_for_status()
        return response.json()
```

Then configure your retry decorator to handle this exception specially—waiting
the exact time specified rather than using exponential backoff.

---

## Putting It All Together: Building a Resilient User Service

Let's apply everything from this guide to a real-world scenario. We'll build a
**User Profile Service** that fetches data from an external identity provider—a
common pattern in modern applications.

### The Scenario

Your application needs to fetch user profiles from a third-party identity
provider (like Auth0, Okta, or a partner API). This external dependency can fail
in multiple ways:

- **Timeout during peak hours**: Their servers are overloaded
- **Rate limiting during high traffic**: You're making too many requests
- **503 during their deployments**: Scheduled maintenance
- **401 if your API key expires**: Configuration issue on your side

**Your mission**: Build resilient data fetching that handles all these failure
modes gracefully, without making things worse.

### Step 1: Define Your Exception Hierarchy

First, we create custom exceptions that map to our retry strategy. This is
**crucial**—it separates "what happened" from "what to do about it":

```python
class APIError(Exception):
    """Base exception for API errors."""
    pass


class RateLimitError(APIError):
    """Rate limit exceeded (HTTP 429).

    RETRYABLE: Yes—rate limit will reset, wait and try again.
    """
    pass


class ServiceUnavailableError(APIError):
    """Service temporarily unavailable (HTTP 503).

    RETRYABLE: Yes—server is overloaded or in maintenance, will recover.
    """
    pass


class AuthenticationError(APIError):
    """Authentication failed (HTTP 401).

    RETRYABLE: No—credentials are invalid, retrying won't help.
    Must fix the request (refresh token, update API key, etc.)
    """
    pass
```

**Why custom exceptions?** Because they encode your retry policy into the type
system. When you catch `RateLimitError`, you know immediately it's retryable.
When you catch `AuthenticationError`, you know to fail fast.

### Step 2: Add Observability

Retries without visibility are dangerous. You need to know when retries happen,
how often, and what's causing them:

```python
import structlog
from tenacity import RetryCallState

logger = structlog.get_logger()


def log_retry(state: RetryCallState) -> None:
    """Log every retry attempt for debugging and alerting."""
    if state.outcome and state.outcome.failed:
        exc = state.outcome.exception()
        logger.warning(
            "retry_attempt",
            attempt=state.attempt_number,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            next_wait_seconds=state.next_action.sleep if state.next_action else 0,
        )
```

This logging enables:

- **Debugging**: "Why is this endpoint slow?" → Check retry logs
- **Alerting**: Set up alerts when retry rate spikes
- **Metrics**: Track retry success rates over time

### Step 3: Configure Retry Behavior

Now we configure the retry decorator with intentional choices for each
parameter:

```python
from leitmotif.resilience.retry import RetryConfig, retry
import httpx


@retry(
    config=RetryConfig(
        max_attempts=5,           # 5 attempts: balance between resilience and latency
        wait_min=0.5,             # Start with 500ms delay
        wait_max=30.0,            # Cap at 30 seconds (don't wait forever)
        retry_on_exceptions=(     # ONLY retry these transient failures:
            RateLimitError,
            ServiceUnavailableError,
            httpx.TimeoutException,
        ),
        never_retry_on=(          # NEVER retry these permanent failures:
            AuthenticationError,
        ),
    ),
    before_sleep=log_retry,       # Log every retry for observability
)
async def fetch_user_data(user_id: str) -> dict:
    """Fetch user profile from external identity provider."""
    ...
```

### Step 4: Map HTTP Responses to Exceptions

Inside the function, we translate HTTP status codes into our exception
hierarchy:

```python
async def fetch_user_data(user_id: str) -> dict:
    """Fetch user profile from external identity provider."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"https://identity.example.com/users/{user_id}"
        )

        # Map HTTP status codes to exception types
        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded")
        elif response.status_code == 503:
            raise ServiceUnavailableError("Service unavailable")
        elif response.status_code == 401:
            raise AuthenticationError("Invalid credentials")

        response.raise_for_status()  # Catch any other errors
        return response.json()
```

### The Complete Implementation

Here's everything together:

```python
from leitmotif.resilience.retry import RetryConfig, retry
from tenacity import RetryCallState
import httpx
import structlog

logger = structlog.get_logger()


# --- Exceptions (encode retry policy in types) ---

class APIError(Exception):
    """Base exception for API errors."""
    pass


class RateLimitError(APIError):
    """Retryable: Rate limit will reset."""
    pass


class ServiceUnavailableError(APIError):
    """Retryable: Server will recover."""
    pass


class AuthenticationError(APIError):
    """Non-retryable: Credentials are invalid."""
    pass


# --- Observability ---

def log_retry(state: RetryCallState) -> None:
    """Log every retry attempt."""
    if state.outcome and state.outcome.failed:
        exc = state.outcome.exception()
        logger.warning(
            "retry_attempt",
            attempt=state.attempt_number,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            next_wait_seconds=state.next_action.sleep if state.next_action else 0,
        )


# --- The Resilient Function ---

@retry(
    config=RetryConfig(
        max_attempts=5,
        wait_min=0.5,
        wait_max=30.0,
        retry_on_exceptions=(RateLimitError, ServiceUnavailableError, httpx.TimeoutException),
        never_retry_on=(AuthenticationError,),
    ),
    before_sleep=log_retry,
)
async def fetch_user_data(user_id: str) -> dict:
    """Fetch user profile from external identity provider."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"https://identity.example.com/users/{user_id}")

        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded")
        elif response.status_code == 503:
            raise ServiceUnavailableError("Service unavailable")
        elif response.status_code == 401:
            raise AuthenticationError("Invalid credentials")

        response.raise_for_status()
        return response.json()
```

### What This Achieves

This implementation embodies every principle from this guide:

| Principle                           | How It's Applied                                                                                    |
| ----------------------------------- | --------------------------------------------------------------------------------------------------- |
| **Retry only transient failures**   | `RateLimitError` and `ServiceUnavailableError` are retried; `AuthenticationError` fails immediately |
| **Exponential backoff with jitter** | `RetryConfig` uses Full Jitter by default                                                           |
| **Limit retry attempts**            | `max_attempts=5` prevents infinite loops                                                            |
| **Observability**                   | `log_retry` callback logs every retry for debugging                                                 |
| **Fail fast on permanent errors**   | `never_retry_on=(AuthenticationError,)` ensures immediate failure                                   |
| **Cap maximum wait time**           | `wait_max=30.0` prevents excessive delays                                                           |

**Result**: Your service stays responsive even when the upstream identity
provider is flaky. Transient failures are handled gracefully with automatic
retry. Permanent failures surface immediately so you can fix the root cause. And
you have full visibility into what's happening.

---

## LLM API Integration Patterns

LLM APIs (OpenAI, Anthropic, Google Gemini) present unique challenges for retry
logic that warrant dedicated patterns.

### Why LLM APIs Are Different

| Challenge                         | Impact                                  | Pattern Required                           |
| --------------------------------- | --------------------------------------- | ------------------------------------------ |
| **Aggressive rate limiting**      | 60-500 requests/minute typical          | Semaphore-based concurrency control        |
| **Varied transient errors**       | Network, timeout, overload, rate limit  | Deny-list pattern (can't enumerate all)    |
| **Well-defined permanent errors** | Auth, invalid request, content policy   | Fail-fast on known permanent errors        |
| **Cost accumulation**             | Failed retries may still consume tokens | Careful retry budgeting                    |
| **Long response times**           | 5-60+ seconds per request               | Higher timeouts, fewer concurrent requests |

### Pattern 1: Semaphore + Retry for Concurrent Rate Limiting

When calling LLM APIs, you need **both** retry logic AND concurrency control.
The semaphore limits how many requests are in-flight simultaneously, while retry
handles transient failures.

**Critical**: Place the semaphore **inside** the retried function so each retry
attempt also respects the rate limit.

```python
import asyncio
import httpx
from tenacity import RetryCallState

from leitmotif.resilience.retry import RetryConfig, retry

# Global semaphore - limits concurrent API calls
LLM_SEMAPHORE = asyncio.Semaphore(10)  # Max 10 concurrent requests


# --- LLM-Specific Exceptions ---

class LLMPermanentError(Exception):
    """Base class for non-retryable LLM errors."""
    pass


class LLMAuthenticationError(LLMPermanentError):
    """Invalid API key (401)."""
    pass


class LLMInvalidRequestError(LLMPermanentError):
    """Bad request payload (400)."""
    pass


class LLMContentPolicyError(LLMPermanentError):
    """Content blocked by safety filters."""
    pass


class LLMQuotaExceededError(LLMPermanentError):
    """Monthly quota exceeded (not rate limit) - 403."""
    pass


# --- Retry Callbacks for Observability ---

async def log_before_retry(state: RetryCallState) -> None:
    """Log before each retry attempt."""
    print(f"[Retry] Attempt {state.attempt_number}")


async def log_after_retry(state: RetryCallState) -> None:
    """Log after each retry attempt."""
    if state.outcome and state.outcome.failed:
        exc = state.outcome.exception()
        print(f"[Retry] Attempt {state.attempt_number} failed: {exc}")


async def log_before_sleep(state: RetryCallState) -> None:
    """Log before sleeping between retries."""
    sleep_time = state.next_action.sleep if state.next_action else 0
    print(f"[Retry] Sleeping {sleep_time:.2f}s before next attempt...")


# --- Retry Configuration ---

LLM_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    wait_min=1.0,
    wait_max=60.0,
    exp_base=2.0,
    # Deny-list pattern: retry ALL exceptions EXCEPT permanent failures
    retry_on_exceptions=None,  # None = retry on all Exception
    never_retry_on=(
        LLMPermanentError,  # Auth, invalid request, content policy, quota
        ValueError,         # Programming errors
        TypeError,
        KeyError,
    ),
    reraise=True,
)


@retry(
    config=LLM_RETRY_CONFIG,
    before=log_before_retry,
    after=log_after_retry,
    before_sleep=log_before_sleep,
)
async def call_llm_api(prompt: str) -> str:
    """Call LLM API with semaphore rate limiting and retry."""
    async with LLM_SEMAPHORE:  # Rate limiting applied to EACH attempt
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": "Bearer sk-xxx"},
                json={
                    "model": "gpt-4o",
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

            # Map HTTP status to appropriate exception
            match response.status_code:
                case 401:
                    raise LLMAuthenticationError("Invalid API key")
                case 403:
                    raise LLMQuotaExceededError("Monthly quota exceeded")
                case 400:
                    body = response.json()
                    # Check error type via structured field (more robust than string matching)
                    error_type = body.get("error", {}).get("type", "")
                    if "content_policy" in error_type or "content_filter" in error_type:
                        raise LLMContentPolicyError("Content blocked")
                    raise LLMInvalidRequestError(f"Bad request: {body}")
                case 429:
                    # Rate limit - WILL be retried (not in never_retry_on)
                    raise httpx.HTTPStatusError(
                        "Rate limited",
                        request=response.request,
                        response=response,
                    )
                case code if code >= 500:
                    # Server error - WILL be retried
                    response.raise_for_status()

            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
```

```{mermaid}
sequenceDiagram
    participant C as Client
    participant R as @retry Decorator
    participant S as Semaphore
    participant F as Function
    participant API as LLM API

    C->>R: call_llm_api(prompt)

    loop Until success or max_attempts
        R->>S: Acquire semaphore
        Note over S: Wait if 10 already in-flight
        S->>F: Semaphore acquired
        F->>API: POST /chat/completions

        alt Success (200)
            API-->>F: Response
            F-->>S: Release semaphore
            S-->>R: Return result
            R-->>C: Return result
        else Rate Limited (429)
            API-->>F: 429 Too Many Requests
            F-->>S: Release semaphore
            S-->>R: Raise HTTPStatusError
            R->>R: Wait (exponential backoff + jitter)
        else Permanent Error (401/400)
            API-->>F: 401 Unauthorized
            F-->>S: Release semaphore
            S-->>R: Raise LLMPermanentError
            R-->>C: Raise immediately (no retry)
        end
    end
```

### Pattern 2: Deny-List for Unknown Transient Errors

When you **can't enumerate all transient errors** (common with LLM APIs due to
varied network/server behaviors), use the deny-list pattern:

```python
# Pattern: Retry ALL exceptions EXCEPT known permanent failures
LLM_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    # Don't specify retry_on_exceptions -> defaults to ALL exceptions
    retry_on_exceptions=None,
    # Only specify what should NEVER be retried
    never_retry_on=(
        LLMPermanentError,  # Base class catches all subclasses
        ValueError,
        TypeError,
    ),
    reraise=True,
)
```

**Why this works**: The retry module logic is:

1. `retry_on_exceptions=None` → retry on any `Exception`
2. `never_retry_on` subtracts from that set (takes precedence)

**When to use allow-list vs deny-list**:

| Pattern        | Config                                              | Use When                                                  |
| -------------- | --------------------------------------------------- | --------------------------------------------------------- |
| **Allow-list** | `retry_on_exceptions=(Exc1, Exc2)`                  | You know exactly which errors are transient               |
| **Deny-list**  | `retry_on_exceptions=None` + `never_retry_on=(...)` | Many/unknown transient errors, but clear permanent errors |

### Pattern 3: Understanding `reraise` Behavior

The `reraise` config option controls what exception is raised after all retries
are exhausted:

#### `reraise=True` (Default)

The **original exception** is raised. Callers handle specific exception types:

```python
LLM_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    reraise=True,  # Default behavior
)

@retry(config=LLM_RETRY_CONFIG)
async def call_api() -> str:
    ...

# Usage
try:
    result = await call_api()
except httpx.TimeoutException:
    # Handle timeout specifically
    print("Request timed out after all retries")
except LLMPermanentError as e:
    # Handle permanent errors (not retried)
    print(f"Permanent failure: {e}")
```

#### `reraise=False`

A `tenacity.RetryError` wraps the original exception. Useful for uniform error
handling or accessing retry metadata:

```python
from tenacity import RetryError

LLM_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    reraise=False,
)

@retry(config=LLM_RETRY_CONFIG)
async def call_api() -> str:
    ...

# Usage
try:
    result = await call_api()
except RetryError as e:
    # Access retry metadata
    print(f"All {e.last_attempt.attempt_number} retries failed")

    # Get the original exception
    original = e.last_attempt.exception()
    print(f"Last error was: {type(original).__name__}: {original}")

    # Can still re-raise the original if needed
    raise original from e
```

**Decision guide**:

| `reraise` | Exception Type        | Use Case                                   |
| --------- | --------------------- | ------------------------------------------ |
| `True`    | Original exception    | Caller handles specific error types        |
| `False`   | `tenacity.RetryError` | Uniform handling, access to retry metadata |

### Pattern 4: Batch Processing Strategies

When processing multiple LLM requests, choose between **partial results** and
**all-or-nothing**:

#### Option A: Continue on Failure (Partial Results OK)

Use when some failures are acceptable (e.g., summarizing 100 documents—95%
success is fine):

```python
from dataclasses import dataclass


@dataclass
class LLMResult:
    """Result wrapper for batch processing."""
    prompt: str
    response: str | None
    error: Exception | None

    @property
    def success(self) -> bool:
        return self.error is None


async def call_llm_safe(prompt: str) -> LLMResult:
    """Wrapper that returns Result instead of raising."""
    try:
        response = await call_llm_api(prompt)
        return LLMResult(prompt=prompt, response=response, error=None)
    except Exception as e:
        return LLMResult(prompt=prompt, response=None, error=e)


async def process_batch_continue(prompts: list[str]) -> tuple[list[LLMResult], list[LLMResult]]:
    """Process batch, continue even if some fail."""
    tasks = [call_llm_safe(prompt) for prompt in prompts]
    results = await asyncio.gather(*tasks)

    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]

    print(f"Batch: {len(successes)} succeeded, {len(failures)} failed")
    return successes, failures


# Usage
successes, failures = await process_batch_continue(prompts)
for result in successes:
    print(f"✓ {result.response[:50]}...")
for result in failures:
    print(f"✗ {result.prompt[:30]}... -> {result.error}")
```

#### Option B: Fail Fast (All or Nothing)

Use when all results are required (e.g., financial reconciliation):

```python
async def process_batch_fail_fast(prompts: list[str]) -> list[str]:
    """Process batch, fail entire batch if any request fails."""
    tasks = [call_llm_api(prompt) for prompt in prompts]
    # gather with return_exceptions=False (default) raises on first failure
    return await asyncio.gather(*tasks)


# Usage
try:
    responses = await process_batch_fail_fast(prompts)
    print(f"All {len(responses)} requests succeeded")
except Exception as e:
    print(f"Batch failed: {e}")
    # Options: retry entire batch, fall back to sequential, return cached
    raise
```

### LLM Retry Decision Matrix

| Scenario                      | `reraise` | Batch Strategy            | Rationale                             |
| ----------------------------- | --------- | ------------------------- | ------------------------------------- |
| Single critical request       | `True`    | N/A                       | Caller must handle failure explicitly |
| Batch with partial results OK | `True`    | Continue (Result wrapper) | 95% success acceptable                |
| Batch requiring ALL results   | `True`    | Fail fast                 | All-or-nothing semantics              |
| Background job processing     | `False`   | Continue                  | Log and continue with next task       |
| Interactive user request      | `True`    | N/A                       | Show specific error to user           |

---

## Anti-Patterns to Avoid

```{prf:remark} Why This Section Matters
:label: rem-antipatterns-importance

Understanding these anti-patterns is essential **before** implementing retries.
Naive implementations can **amplify failures** rather than mitigate them.
{cite:p}`google2017sre-cascading`

These are not edge cases—they are common mistakes that have caused production
outages at scale.
```

### 1. Retry Amplification (The Cascade Effect)

Recall {term}`Retry Amplification` from the Definitions: the multiplicative
effect when multiple layers each implement retries.

**The Problem in Plain English**: When multiple layers of your system each
implement retries, failures don't just add up—they _multiply_. One failed user
request can generate dozens or even hundreds of downstream requests.

```{prf:theorem} Retry Amplification Factor
:label: thm-retry-amplification

Let $n$ be the number of layers, and $r$ be the total attempts per layer
(1 original + retries; e.g., 3 retries means $r = 4$). The total requests
generated by a single user action is:

$$
\text{Total requests} = r^n
$$

**Example**: With 4 layers (JavaScript → Frontend → Backend → Database) and 4
attempts per layer (1 original + 3 retries):

$$
4^4 = 256 \text{ database requests from ONE user click!}
$$
```

#### Visual: The Multiplication Effect

```{mermaid}
:zoom:

flowchart LR
    subgraph "User Action"
        U["👤 Single Click"]
    end

    subgraph "JavaScript Layer"
        JS["4 attempts"]
    end

    subgraph "Frontend Layer"
        FE["× 4 attempts"]
    end

    subgraph "Backend Layer"
        BE["× 4 attempts"]
    end

    subgraph "Database"
        DB["256 requests!"]
    end

    U --> JS --> FE --> BE --> DB

    style DB fill:#ff6b6b,stroke:#333,stroke-width:2px
```

**ASCII representation**:

```text
User → JS(4×) → Frontend(4×) → Backend(4×) → DB
         ↓           ↓            ↓          ↓
       4 req    × 4 = 16     × 4 = 64   × 4 = 256 requests!
```

#### Why This Destroys Your System

When the database is overloaded and returning errors _because_ it's overloaded,
retry amplification creates a vicious cycle:

1. Database overloaded → returns errors
2. Each layer retries → more requests to database
3. Database even more overloaded → more errors
4. Even more retries → **system collapse**

#### ❌ Bad: Retries at Every Layer

```python
# Each layer retries 3× = 4³ = 64 total requests per user action!
@retry(max_attempts=4)
async def api_gateway():
    return await backend()

@retry(max_attempts=4)
async def backend():
    return await database()

@retry(max_attempts=4)
async def database():
    ...
```

#### ✅ Good: Retry at ONE Layer Only

```python
@retry(max_attempts=4)
async def api_gateway():
    return await backend()  # No retry - fail fast

async def backend():
    return await database()  # No retry - fail fast

async def database():
    ...  # No retry - fail fast, return clear error code
```

**The Rule**: Implement retries at **exactly one layer**—typically the outermost
layer that has sufficient context to make retry decisions. All other layers
should **fail fast** and return clear error codes.
{cite:p}`google2017sre-cascading`

---

### 2. Thundering Herd (Synchronized Retries)

Recall {term}`Thundering Herd` from the Definitions: when many clients retry
simultaneously after a service recovers.

```{prf:observation} The Stampede Analogy
:label: obs-stampede

Imagine a concert venue where everyone rushes to the exit at once—a stampede.
The same thing happens when a service recovers from an outage: all waiting
clients retry simultaneously, immediately overwhelming it again.

It's like everyone hitting refresh at the exact same moment after a website goes
down.
```

#### Why This Happens

When you use **fixed retry intervals** (e.g., retry after exactly 1s, then 2s,
then 4s), all clients that failed at the same time will retry at the same time:

```{mermaid}
:zoom:

gantt
    title Thundering Herd: Synchronized Retry Waves
    dateFormat X
    axisFormat %Ls

    section Service Status
    Outage (Down)     :crit, a1, 0, 10
    Recovery (Up)     :active, a2, 10, 50

    section Client Retries (No Jitter)
    Client A retry    :b1, 10, 11
    Client B retry    :b2, 10, 11
    Client C retry    :b3, 10, 11
    All retry at t=15 :b4, 15, 16
    All retry at t=20 :b5, 20, 21

    section Result
    Overloaded Again! :crit, c1, 10, 12
```

#### The Timeline of Disaster

```text
Time 0s:   Service goes DOWN
           1000 clients get errors, start retry timers

Time 10s:  Service comes back UP
           ALL 1000 clients retry at once! 💥
           Service immediately crashes again

Time 15s:  Service tries to recover
           ALL 1000 clients retry at once! 💥
           Crash again...

[Repeat indefinitely]
```

#### The Solution: Randomized Jitter

**Jitter** adds randomness to retry delays, spreading requests over time:

```text
WITHOUT JITTER (Bad):           WITH JITTER (Good):
All 1000 clients at t=10s       ~100 clients per second spread over 10s
        ↓                                    ↓
   │████████████│                │█│█│█│█│█│█│█│█│█│█│
   t=10s                         t=10s ──────────────→ t=20s
```

#### ❌ Bad: Fixed Delays (No Jitter)

```python
# All clients retry at exactly the same times → thundering herd
for attempt in range(3):
    try:
        return await make_request()
    except TransientError:
        await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s - everyone in sync!
```

#### ✅ Good: Randomized Delays (Full Jitter)

```python
import random

for attempt in range(3):
    try:
        return await make_request()
    except TransientError:
        max_delay = 2 ** attempt
        jittered_delay = random.uniform(0, max_delay)  # Spread out!
        await asyncio.sleep(jittered_delay)
```

#### ✅ Best: Use Retry Wrapper (Jitter Built-In)

```python
@retry()  # Uses Full Jitter algorithm by default
async def fetch():
    ...
```

The implementation uses `wait_random_exponential` from tenacity which implements
proper jitter automatically. {cite:p}`brooker2015backoff`

---

### 3. Infinite Retry Loops (Retrying the Unretryable)

**The Problem in Plain English**: Some errors will **NEVER** succeed no matter
how many times you retry. Retrying them forever wastes resources and delays
failure detection.

```{prf:property} The Unretryable Principle
:label: prop-unretryable

{term}`Permanent Failures <Permanent Failure>` cannot be fixed by retrying.
Retrying them:

1. **Wastes compute resources** — CPU cycles with zero chance of success
2. **Delays failure detection** — User waits longer for inevitable failure
3. **Masks root cause** — Logs flooded with retry noise
4. **May worsen state** — Some failures degrade with repeated attempts
```

#### Permanent vs Transient Errors

```{mermaid}
:zoom:

flowchart TD
    E["Error Occurred"] --> Q{"What type<br/>of error?"}

    Q -->|"Transient"| T["✅ RETRY"]
    Q -->|"Permanent"| P["❌ FAIL FAST"]

    T --> T1["Network timeout"]
    T --> T2["503 Service Unavailable"]
    T --> T3["429 Rate Limited"]
    T --> T4["Connection reset"]

    P --> P1["400 Bad Request"]
    P --> P2["401 Unauthorized"]
    P --> P3["404 Not Found"]
    P --> P4["ValidationError"]

    style T fill:#90EE90
    style P fill:#ff6b6b
```

| Error Type    | Examples                            | Will Retry Help?           | Action             |
| ------------- | ----------------------------------- | -------------------------- | ------------------ |
| **Transient** | Timeout, 503, 429, connection reset | ✅ Yes - may succeed later | Retry with backoff |
| **Permanent** | 400, 401, 403, 404, ValidationError | ❌ No - will never succeed | Fail immediately   |

#### The Decision Flowchart

```text
Should I retry this error?
│
├── Is it a network/connection error?
│   └── YES → ✅ Retry (transient)
│
├── Is it HTTP 5xx (server error)?
│   └── YES → ✅ Retry (server may recover)
│
├── Is it HTTP 429 (rate limited)?
│   └── YES → ✅ Retry (after Retry-After delay)
│
├── Is it HTTP 4xx (client error)?
│   └── YES → ❌ Don't retry (your request is wrong)
│
├── Is it a validation/authentication error?
│   └── YES → ❌ Don't retry (credentials won't magically appear)
│
└── Unknown error?
    └── ⚠️ Log and fail fast (investigate later)
```

#### ❌ Bad: Retry Everything

```python
@retry()  # Retries EVERYTHING including validation errors!
async def process(user_input: str):
    data = validate(user_input)  # ValidationError will NEVER succeed on retry
    return await external_api(data)
```

#### ✅ Good: Explicit Exception Classification

```python
@retry(
    config=RetryConfig(
        retry_on_exceptions=(httpx.TimeoutException, httpx.NetworkError),
        never_retry_on=(ValidationError, AuthenticationError, PermissionDeniedError),
    )
)
async def process(user_input: str):
    data = validate(user_input)  # Fails fast if invalid
    return await external_api(data)  # Only network errors are retried
```

**The Rule**: Always be explicit about which errors to retry. When in doubt,
**fail fast**—it's better to surface errors quickly than to waste time retrying
the impossible. {cite:p}`nygard2018releaseit`

---

## Conclusion: Retries as Part of Your Resilience Strategy

Retries are one tool in your resilience toolkit—**powerful but dangerous if
misused**. The difference between a retry implementation that saves your system
and one that destroys it lies in the details we've covered throughout this
guide.

```{prf:remark} Key Takeaways
:label: rem-key-takeaways

1. **Retries exploit {term}`Transient Failures <Transient Failure>`**—but only
   transient failures. Ask: "Will the same request succeed if I try again?"
   ({prf:ref}`crit-retry-decision`)

2. **{term}`Exponential Backoff` with {term}`Jitter` is non-negotiable**. Fixed
   delays create {term}`Thundering Herd`. Full Jitter provides the best
   protection. ({prf:ref}`alg-full-jitter`)

3. **Classify errors explicitly**. Create exception hierarchies that encode your
   retry policy. Retry transient failures; fail fast on permanent ones.
   ({prf:ref}`def-failure-classification`)

4. **Respect server signals**. When a server sends `Retry-After`, it's telling
   you exactly when retrying makes sense. Use that information.

5. **Retry at one layer only**. {term}`Retry Amplification` ($r^n$ total
   requests for $n$ layers with $r$ retries each) can turn a minor issue into a
   catastrophic cascade. ({prf:ref}`thm-retry-amplification`)

6. **Ensure {term}`Idempotency`**—or use idempotency keys. Retries are only safe
   when repeated execution produces the same result.
   ({prf:ref}`prop-retry-safety`)

7. **Observability is essential**. Log every retry. Track retry rates. Alert on
   anomalies. Without visibility, you're flying blind.
```

### Retries in the Broader Resilience Ecosystem

Retries work best when combined with other resilience patterns:

| Pattern             | How It Complements Retries                                                                   |
| ------------------- | -------------------------------------------------------------------------------------------- |
| **Circuit Breaker** | Stop retrying when a service is confirmed down—don't pile on to a struggling system          |
| **Timeout**         | Bound how long you wait for each attempt—prevent requests from hanging indefinitely          |
| **Bulkhead**        | Isolate failures to prevent cascade—don't let retry storms consume all your resources        |
| **Fallback**        | Provide degraded functionality when all retries fail—graceful degradation over total failure |
| **Health Check**    | Detect service recovery early—resume normal operation faster                                 |

```{prf:remark} The Resilience Mindset
:label: rem-resilience-mindset

Resilience isn't about preventing failures—it's about **graceful recovery**.

- Networks **will** fail
- Services **will** overload
- Databases **will** timeout

Your system's job isn't to stop these failures from happening; it's to **bend
but not break** when they do.

Retries are your first line of defense, but they're not a silver bullet. Use
them thoughtfully, in combination with other patterns, and always with full
visibility into their behavior.
```

Together, these patterns create systems that **survive the chaos** of
distributed computing. The goal isn't perfection—it's resilience.

---

## References

### Primary Sources

- **Google SRE Book, Chapter 22**:
  [Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/)
  — The definitive guide on retry patterns, circuit breakers, and preventing
  cascade failures in distributed systems.

- **Google SRE Book, Chapter 21**:
  [Handling Overload](https://sre.google/sre-book/handling-overload/) — Covers
  retry budgets, load shedding, and graceful degradation strategies.

- **AWS Architecture Blog**:
  [Exponential Backoff and Jitter](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
  — Marc Brooker's seminal analysis of jitter strategies with simulation
  results.

### Books

- Nygard, M. T. (2018). _Release It! Design and Deploy Production-Ready
  Software_ (2nd ed.). Pragmatic Bookshelf. — Essential reading on stability
  patterns including retries, circuit breakers, and bulkheads.

- Kleppmann, M. (2017). _Designing Data-Intensive Applications_. O'Reilly
  Media. — Comprehensive coverage of distributed systems fundamentals and
  failure modes.

### Additional Resources

- [Stripe: Idempotent Requests](https://stripe.com/docs/api/idempotent_requests)
  — Practical guide to implementing idempotency keys for safe retries.

- [tenacity Documentation](https://tenacity.readthedocs.io/) — The Python
  library used for retry logic.

- [Eight Fallacies of Distributed Computing](https://en.wikipedia.org/wiki/Fallacies_of_distributed_computing)
  — Peter Deutsch's foundational insight into why distributed systems are
  hard.

### Related Documentation

- [Circuit Breaker Pattern](./cb.md) — Fail-fast and fault isolation
- [Timeout Patterns](./timeout.md) — Timeouts and deadline propagation
- [Bulkhead Pattern](./bulkhead.md) — Resource isolation and concurrency
  limiting
