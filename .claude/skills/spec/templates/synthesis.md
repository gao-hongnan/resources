---
spec: ./spec.md
plan: ./plan.md
date: !`date +%Y-%m-%d`
diagram_count: { DIAGRAM_COUNT }
diagram_types: []
---

# Cross-Cutting System Views: $1

<!-- Cross-cutting visualizations that span multiple Architecture Decisions.
     Per-decision sequence diagrams live INLINE in plan.md (within each ### Decision N: block).
     This document is for system-level views only: data flows across services, component topology,
     and state machines that span the entire change — not a single decision.
     All diagrams use Mermaid syntax (renders in GitHub, Confluence, VS Code).
     Every diagram MUST reference at least one FR-NNN or AC-NNN from spec.md. -->

## Data Flow Diagrams _(include when data transforms across 2+ services or stores)_

<!-- WHAT: How data moves and transforms between services, queues, and data stores.
     WHY: Shows where data lives, how it changes shape, and where transformations happen.
     WHEN TO INCLUDE: When data passes through 2+ services or stores with transformations
     (e.g., API receives JSON, worker writes to DB, another service reads and re-formats).
     WHEN TO OMIT: Never silently delete. If not applicable, replace content with:
     "N/A -- single service with no cross-boundary data transformations."
     EXAMPLE:

     ### DFD-001: Translation data pipeline (FR-002, FR-003)

     ```mermaid
     flowchart LR
         A[Client Upload] -->|XLIFF file| B(<api-service>)

         B -->|parsed segments| C[(PostgreSQL)]
         C -->|batch query| D(<tm-worker>)
         D -->|TM matches| C
         C -->|enriched segments| E(<export-worker>)
         E -->|translated XLIFF| F[Client Download]
     ```

     **Narrative**: Translation data enters as XLIFF, gets parsed into segments stored
     in PostgreSQL, enriched with TM matches by the pyworker, and re-assembled for export.

-->

### DFD-{NNN}: {Title} ({FR-NNN})

```mermaid
flowchart LR
    A[{Source}] -->|{data}| B({Service})
    B -->|{transformed}| C[({Store})]
    C -->|{query}| D({Consumer})
```

**Narrative**: <!-- 2-3 sentences explaining the data flow. -->

---

## Component Diagrams _(include when 3+ services interact or new services are introduced)_

<!-- WHAT: High-level view of services, their boundaries, and how they connect.
     WHY: Gives new developers a map of which services exist and how they relate.
     WHEN TO INCLUDE: When 3+ services are involved in the change, or when a new
     service is being introduced.
     WHEN TO OMIT: Never silently delete. If not applicable, replace content with:
     "N/A -- change affects fewer than 3 services with no new services introduced."
     EXAMPLE:

     ### CMP-001: Service topology (FR-001, FR-002)

     ```mermaid
     graph TB
         subgraph Frontend
             UI[<ui-service>]
         end
         subgraph Backend
             API[<api-service>]
             CW[<service-worker>]
             TW[<tm-worker>]
         end
         subgraph Data
             DB[(PostgreSQL)]
             Redis[(Redis)]
         end

         UI --> API

         API --> DB
         API --> Redis
         CW --> DB
         TW --> DB
     ```

     **Narrative**: The change spans the API, consistency worker, and TM worker,
     all sharing PostgreSQL. Redis is used for caching API responses.

-->

### CMP-{NNN}: {Title} ({FR-NNN})

```mermaid
graph TB
    subgraph {GroupName}
        {Node1}[{Service1}]
    end
    subgraph {GroupName2}
        {Node2}[{Service2}]
        {Node3}[{Service3}]
    end

    {Node1} --> {Node2}
    {Node2} --> {Node3}
```

**Narrative**: <!-- 2-3 sentences explaining the component relationships. -->

---

## State Diagrams _(include when entities have 3+ states or state transitions have guards)_

<!-- WHAT: State machine showing entity lifecycle with transitions and guards.
     WHY: Makes state logic explicit -- which transitions are valid, what triggers them,
     and what conditions must be met (guards).
     WHEN TO INCLUDE: When an entity has 3+ states, or when state transitions have
     guard conditions (e.g., "only if lease not expired"). Only include here if the
     state machine spans multiple Architecture Decisions. Per-decision state diagrams
     belong inline in plan.md.
     WHEN TO OMIT: Never silently delete. If not applicable, replace content with:
     "N/A -- no entities with 3+ states or guarded transitions spanning multiple decisions."
     EXAMPLE:

     ### STD-001: Task document lifecycle (FR-001, AC-003)

     ```mermaid
     stateDiagram-v2
         [*] --> PENDING: Job created

         PENDING --> PROCESSING: Worker acquires lease
         PROCESSING --> DONE: Checks pass
         PROCESSING --> FAILED: Checks fail
         PROCESSING --> PENDING: Lease expired (timeout)
         FAILED --> PENDING: Manual retry
         DONE --> [*]
     ```

     **Narrative**: A consistency job starts as PENDING, transitions to PROCESSING
     when a worker acquires its lease, and ends as DONE or FAILED. Lease expiry
     returns the job to PENDING for reprocessing.

-->

### STD-{NNN}: {Title} ({FR-NNN}, {AC-NNN})

```mermaid
stateDiagram-v2
    [*] --> {State1}: {trigger}
    {State1} --> {State2}: {event}
    {State2} --> {State3}: {condition}
    {State3} --> [*]
```

**Narrative**: <!-- 2-3 sentences explaining the state transitions. -->

---

## Diagram Inventory

<!-- WHAT: Summary table of all cross-cutting diagrams in this document for quick reference.
     WHY: Lets reviewers verify completeness at a glance -- row count must match heading count.
     NOTE: Per-decision sequence diagrams have their own inventory in plan.md.
     The /spec analyze command (Pass 8b) validates this table against actual diagram headings. -->

| ID      | Type      | Title   | References     | Conditional? |
| ------- | --------- | ------- | -------------- | ------------ |
| DFD-001 | Data Flow | {Title} | FR-002, FR-003 | Yes          |
| CMP-001 | Component | {Title} | FR-001, FR-002 | Yes          |
| STD-001 | State     | {Title} | FR-001, AC-003 | Yes          |
