---
ticket: $1
branch: !`git branch --show-current`
status: Draft
phase: platonic
date: !`date +%Y-%m-%d`
template_version: 1
transitions: []
---

# $1: {TITLE}

<!-- WHAT and WHY only. No implementation code. -->

## Problem Statement _(mandatory)_

<!-- spec type determines sub-structure. DELETE the block that does not apply.
     RULE: Every claim MUST include a metric, error code, or citation. Vague statements are rejected.
     BAD:  "The system is slow"
     GOOD: "p95 latency for POST /orders exceeds 8s on carts with >100 items (SLO target: 2s, measured 2026-03-20)" -->

<!-- ═══════════════════ BUG / OPTIMIZATION (delete if FEATURE) ═══════════════════ -->

### Observed Symptom

<!-- WHAT: What is the user or system experiencing right now?
     MUST include: service name + observable behaviour + frequency/scope.
     BAD:  "Worker crashes sometimes"
     GOOD: "<service-worker> exits with SIGKILL (OOM) on ~15% of batch orders with >500 line items; first observed 2026-03-10" -->

### Root Cause

<!-- WHAT: Why is this happening? Mark [HYPOTHESIS] if unconfirmed; mark [CONFIRMED] if traced.
     MUST include: code path or data flow that causes the symptom.
     BAD:  "Memory leak somewhere"
     GOOD: "[HYPOTHESIS] order_line_cache in processor.py accumulates all line items in-memory without eviction (see line 214)" -->

### Impact

<!-- WHAT: Who is affected, how badly, and what is the business cost?
     MUST quantify: user count or job %, error code surfaced, downstream effect.
     BAD:  "Users are unhappy"
     GOOD: "Affects ~15% of batch orders >500 line items; merchants receive HTTP 503 (ORDER_PROC_ERROR); estimated 20 retries/hour adding $X/day in compute" -->

<!-- ═══════════════════ FEATURE (delete if BUG / OPTIMIZATION) ════════════════════ -->

### Motivation

<!-- WHAT: Why does this feature need to exist? What pain or opportunity drives it?
     MUST be user- or business-facing, not technical.
     BAD:  "We should add caching"
     GOOD: "Merchants re-submit identical orders after minor edits, causing duplicate processing; 35% of orders are re-submissions within 1 hour (measured Q1 2026)" -->

### Current Behavior

<!-- WHAT: What does the system do today that is inadequate?
     MUST be observable — what a user or operator can see right now.
     BAD:  "No caching exists"
     GOOD: "Every POST /orders call creates a new order regardless of prior submissions; no deduplication check occurs at ingestion" -->

### Desired Behavior

<!-- WHAT: What should the system do after this change?
     MUST be outcome-framed, not implementation-framed.
     BAD:  "Add a Redis cache keyed by SHA-256"
     GOOD: "Identical orders submitted within 1 hour return the existing order ID; clients see a `duplicate: true` flag in the response" -->

### Impact

<!-- WHAT: Who benefits, by how much, and what is the business value?
     MUST quantify expected improvement or cite the success metric it targets.
     BAD:  "Will be faster"
     GOOD: "Eliminates duplicate processing for ~35% of orders; projected to reduce compute cost by $Y/month and p95 latency from 8s to <200ms for deduplicated requests" -->

## Requirements _(mandatory)_

### Functional Requirements

<!-- WHAT: Numbered requirements with RFC 2119 verbs (MUST/SHOULD/MAY).
     Each FR has a priority (P1/P2/P3) for MVP scope-cut decisions.
     Max 3 [NEEDS CLARIFICATION] markers allowed. Beyond 3, make informed guesses
     and document in Assumptions. Prioritize: scope > security > UX > technical.
     WHEN TO OMIT: Never.
     EXAMPLE: "FR-001 (P1): System MUST return HTTP 409 with duplicate: true when an identical order is re-submitted within 1 hour"
     EXAMPLE: "FR-002 (P2): System MUST allow clients to retrieve order status via GET /orders/{id} at any point after creation" -->

-   **FR-001** (P1): System MUST ...
-   **FR-002** (P2): System MUST ...
-   **FR-003** (P1): [NEEDS CLARIFICATION: How should partial failures be handled?]

### Non-Functional Requirements

<!-- WHAT: Performance, reliability, observability, security constraints.
     WHEN TO OMIT: Never -- even if only one NFR, document it.
     EXAMPLE: "NFR-001: Order validation MUST complete within 2s for orders with <=500 line items"
     EXAMPLE: "NFR-002: <service-worker> MUST process a batch of 500 line items without exceeding 512 MB peak memory" -->

-   **NFR-001**: ...

### Out of Scope

<!-- WHAT: Explicitly list what this spec does NOT cover. Prevents scope creep.
     WHEN TO OMIT: Never -- even a single bullet prevents misunderstanding.
     EXAMPLE: "Changing the pricing engine selection logic (separate spec)" -->

-   ...

## Edge Cases _(mandatory -- min 2)_

<!-- WHAT: Boundary conditions, error scenarios, concurrency scenarios.
     Each edge case MUST reference the AC-NNN that covers it.
     WHEN TO OMIT: Never.
     EXAMPLE: "[EC-001] Empty cart submitted -> AC-003" -->

1. **[EC-001]** ... -> AC-001
2. **[EC-002]** ... -> AC-003

## Standards Basis _(include only when external standards, protocols, or distributed systems theory apply)_

<!-- WHAT: External standards, protocols, or theoretical foundations that inform this spec.
     WHY: Bridges the gap between "what we need" and "why this approach is sound."
     WHEN TO OMIT: Never silently delete. If not applicable, replace content with:
     "N/A -- no external standards apply to this change."
     EXAMPLE:
     - **RFC 7234** (HTTP Caching): Informs cache-control strategy for order deduplication responses.
     - **W3C Trace Context**: Defines the propagation format for distributed trace headers across services.
     - **CAP Theorem**: Justifies eventual-consistency model for cross-region inventory sync. -->

-   ...

## Service Impact _(mandatory for multi-service changes)_

<!-- WHAT: Which monorepo services are affected? Helps estimate blast radius.
     WHEN TO OMIT: Only for changes scoped to a single service with no cross-service effects.
     If not applicable, replace content with: "N/A -- single-service change to {service-name}."
     EXAMPLE: "<service-worker> | code | Add retry logic to DB query" -->

| Service            | Change Type | Description                                  |
| ------------------ | ----------- | -------------------------------------------- |
| `<service-worker>` | code        | <!-- e.g., "Add retry logic to DB query" --> |

## Key Entities _(include only if schema changes -- mark N/A with justification if not)_

<!-- WHAT: Database schema changes required by this spec.
     WHEN TO OMIT: Never silently delete. If not applicable, replace content with:
     "N/A -- this change is logic-only; no schema modifications required."
     EXAMPLE: "order | idempotency_key | ADD | UUID, nullable, client-provided key for deduplication" -->

| Entity  | Column/Field      | Change | Notes                                                                  |
| ------- | ----------------- | ------ | ---------------------------------------------------------------------- |
| `order` | `idempotency_key` | ADD    | <!-- e.g., "UUID, nullable, client-provided key for deduplication" --> |

## Critical Algorithm _(include only for race conditions, CAS, complex state machines)_

<!-- WHAT: Pseudocode for complex logic that needs precise specification.
     WHEN TO OMIT: Never silently delete. If not applicable, replace content with:
     "N/A -- no complex algorithmic logic; standard CRUD operations only."
     EXAMPLE: Optimistic locking pattern for concurrent state transitions -->

```pseudocode
-- Example: optimistic locking pattern
LOOP:
  row = SELECT ... WHERE state = X FOR UPDATE SKIP LOCKED
  IF row IS NULL THEN RETURN
  -- process row
  UPDATE ... SET state = Y WHERE id = row.id AND version = row.version
  IF rows_affected = 0 THEN RETRY
```

## Acceptance Criteria _(mandatory -- min 2)_

<!-- WHAT: Observable, testable conditions in Given/When/Then format.
     WHEN TO OMIT: Never.
     EXAMPLE: "Given a cart with 50 items, When checkout is submitted,
              Then inventory is reserved and order ID is returned within 2s" -->

-   [ ] **AC-001**: **Given** [precondition], **When** [action], **Then** [expected outcome]
-   [ ] **AC-002**: **Given** [precondition], **When** [action], **Then** [expected outcome]

## Success Criteria _(mandatory -- min 2)_

<!-- WHAT: Measurable, technology-agnostic outcomes. NOT the same as Acceptance Criteria.
     ACs are binary pass/fail test conditions. SCs are measurable outcomes over time.
     WHEN TO OMIT: Never for features. May omit for pure bug fixes with "N/A -- bug fix."
     BAD: "API responds in under 200ms" (implementation detail)
     GOOD: "Merchants see order confirmation within 3 seconds for carts under 50 items" -->

-   **SC-001**: ...
-   **SC-002**: ...

## Assumptions

<!-- WHAT: Reasonable defaults chosen where spec was ambiguous.
     Document so reviewers can challenge informed guesses.
     WHEN TO OMIT: Only if zero ambiguity existed (rare).
     EXAMPLE: "Assumed max order size of 500 line items based on current production P99" -->

-   ...

## References

<!-- WHAT: Links to internal docs, external standards, and internet sources that informed this spec.
     Include URLs for anything a reviewer would need to verify claims or understand context.
     WHEN TO OMIT: Only if truly no related documentation exists.
     EXAMPLES:
     - [Design Doc: Order Pipeline](../../docs/order-pipeline.md)
     - [RFC 7234 — HTTP Caching](https://httpwg.org/specs/rfc7234.html)
     - [Stripe Idempotency Keys](https://stripe.com/docs/api/idempotent_requests) -->

## Glossary _(include only when spec introduces 3+ domain-specific terms)_

<!-- WHAT: Definitions for domain-specific terms introduced in this spec.
     WHY: Prevents terminology drift across spec/plan/tasks. Ensures all readers
     share the same understanding of specialized vocabulary.
     WHEN TO OMIT: Never silently delete. If not applicable, replace content with:
     "N/A -- no specialized terminology introduced."
     EXAMPLE:
     | Term           | Definition                                                        |
     | -------------- | ----------------------------------------------------------------- |
     | Lease          | A time-bounded exclusive lock on a resource (row, queue message). |
     | Line item      | A single product and quantity within an order.                    |
     | Trace context  | W3C-standard propagation headers (traceparent, tracestate).       | -->

| Term | Definition |
| ---- | ---------- |
| ...  | ...        |
