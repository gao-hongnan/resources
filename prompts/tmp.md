# The Jobs That Outlive Their Workers

_Crash recovery for ECS workers, with Postgres as the source of truth._

> “If a job can outlive a task, then ownership can’t live in memory.”

**Owner:** <you>
**Last updated:** 2026-01-13
**Status:** Draft / In review
**System:** <name>
**Source of truth:** **Postgres** (job state + progress + events)

---

## 1. Context

ECS is good at restarting tasks. That’s the easy part.

What ECS does **not** give you is continuity: if a worker dies mid-job, the workflow needs a way to decide—without guesswork—**when it’s safe to move on, and what “move on” even means**.

This document describes the crash-recovery mechanism we use when a worker disappears (OOMKilled, SIGKILL, node drain, deploy stop). It deliberately does **not** try to solve request-level transient failures inside a healthy worker; those are a separate layer (timeouts, retries, circuit breakers).

---

## 2. Two failure stories (the ones that matter)

### 2.1 The limbo milestone

### 2.2 The crash loop

Some inputs don’t fail gently. They kill the process (OOM, fatal bug, pathological payload). ECS restarts the task; the new task picks up the same poison job; repeat. Left unchecked, this becomes capacity collapse and incidental cascading failure. ([sre.google][1])

---

## 3. The design stance

We want the system to be boring in the presence of crashes. That leads to three principles:

1. **Postgres is the memory.** If progress is real, it must be recorded in Postgres.
2. **Ownership is time-bound.** A dead task cannot be relied upon to clean up.
3. **Recovery is repeatable.** Because detection is observation-based and can race.

That last point is where “idempotent” comes from—not as ideology, but as the mechanism that allows **eventual convergence**.

---

## 4. Consistency model (what we accept, what we guarantee)

This system is **eventually consistent about ownership**, and **convergent about workflow state**.

- **Eventually consistent ownership:** We infer death from silence. That’s inherently delayed and occasionally wrong in the short term (slow vs dead). This is the classic failure-detector tradeoff. ([UT Austin Computer Science][2])
- **Eventual convergence:** Even if two actors briefly disagree (e.g., due to a partition), the system is built to converge to one correct outcome via fencing + idempotent transitions + reconciliation. (More on these below.)

We don’t pretend the system can know the truth instantly. We bound the uncertainty window and make the end state inevitable.

---

## 5. Semantics (the honest version)

- **Job execution:** at-least-once (a job may be attempted again after a crash).
- **Workflow state in Postgres:** monotonic (state moves forward; recovery never moves it backward).
- **Milestone publication:** exactly-once _effects within the Postgres boundary_ using a transactional outbox (duplicates become no-ops downstream). ([microservices.io][3])
- **External side effects:** at-least-once unless the external system supports idempotency keys.

If someone asks “Is it exactly once?”, the correct answer is: **exactly-once effects are achievable at the boundary we control**. “Exactly-once execution” is not the goal.

---

## 6. Overview of the mechanism

We split the problem into two parts:

### 6.1 Authority: time-bound leases + fencing tokens

A worker can only advance a job if it holds a lease, and each lease acquisition yields a monotonically increasing **fencing token** (epoch/generation). Writes must carry the token; stale tokens are rejected by Postgres. This is the standard way to make TTL-based locks safe. ([Martin Kleppmann][4])

### 6.2 Visibility: transactional outbox in Postgres

Any milestone that downstream depends on must be published _as part of the same database transaction_ that advances the job state. We do this with a transactional outbox. ([microservices.io][3])

This addresses the limbo story directly: “committed but not published” becomes “committed and will be delivered eventually.”

---

## 7. Data model (minimal, but deliberate)

### 7.1 `jobs` (source of truth)

Typical fields:

- `job_id`
- `state` (e.g., `x..x`)
- `lease_epoch` (or `owner_epoch`) — fencing token last accepted by the job row
- `updated_at`, `last_progress_at`
- `crash_count`, `quarantined`, `quarantine_reason`

### 7.2 `job_leases` (optional, depending on implementation)

Either:

- Redis TTL key: `lease:{job_id} -> owner_id` (fast liveness signal), or
- Postgres: `job_leases(job_id, owner_id, epoch, expires_at)` (queryable)

The key requirement is time-bound expiry.

### 7.3 `outbox_events`

- `event_id`
- `aggregate_id` (= job_id)
- `event_type` (e.g., `Milestone12000Reached`)
- `payload`
- `dedupe_key` (unique)
- `created_at`, `delivered_at`

Outbox is a durability trick: it turns “publish now” into “publish eventually, guaranteed,” as long as Postgres is healthy. ([microservices.io][3])

---

## 8. The commit rule: fence-or-reject

This is the heart of correctness.

**Rule:** only the latest epoch may advance the job.

Practically:

- Worker acquires lease → gets `epoch`.
- Any state transition uses a conditional update like:
  `UPDATE jobs SET state=..., lease_epoch=:epoch ... WHERE job_id=:id AND lease_epoch=:epoch AND state=:expected;`
- If 0 rows updated → you’re stale, abort.

This ensures a “zombie” worker (still running after losing lease) cannot commit progress. This is exactly what fencing tokens are for. ([Martin Kleppmann][4])

---

[1]: https://sre.google/sre-book/addressing-cascading-failures/?utm_source=chatgpt.com "Cascading Failures: Reducing System Outage"
[2]: https://www.cs.utexas.edu/~lorenzo/corsi/cs380d/papers/p225-chandra.pdf?utm_source=chatgpt.com "Unreliable Failure Detectors for Reliable Distributed Systems"
[3]: https://microservices.io/patterns/data/transactional-outbox.html?utm_source=chatgpt.com "Pattern: Transactional outbox"
[4]: https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html?utm_source=chatgpt.com "How to do distributed locking"
[5]: https://sre.google/sre-book/tracking-outages/?utm_source=chatgpt.com "Outage Monitoring with Outalator: Boost Safety"
