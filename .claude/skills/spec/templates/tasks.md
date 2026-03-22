---
spec: ./spec.md
plan: ./plan.md
task_count: { TASK_COUNT }
aggregate_estimate: { AGGREGATE_SIZE }
---

# Tasks: $1

<!-- PR-sized work units with TDD verification and traceability. -->

## Dependency Graph

<!-- ASCII diagram. [P] = parallelizable with adjacent tasks. -->

```
$1-1A --> $1-1B
                    |
                    v
$1-2A [P] $1-2B --> $1-2C
                                    |
                                    v
                              $1-3A
```

## Quick View

<!-- Scannable one-liner summary. MUST mirror the detailed task cards below.
     Format: - [ ] {ID} -- [Priority] [P if parallel] {Title} ({Size}) -->

-   [ ] $1-1A -- [P1] {Title} (S)
-   [ ] $1-1B -- [P1] {Title} (M)
-   [ ] $1-2A -- [P2] [P] {Title} (S)

---

## Workstream 1: {Workstream Name from plan.md}

### $1-1A: {Task Title}

| Field          | Value                                           |
| -------------- | ----------------------------------------------- |
| **PR Scope**   | <!-- max 3 files. >3 files = split the task --> |
| **Service(s)** | `<service-worker>`, `<shared-lib>`              |
| **Size**       | S / M / L                                       |
| **Priority**   | P1 / P2 / P3                                    |

**What to implement**: <!-- Precise description. Reference spec FR-NNN. -->

Implements FR-001: ...

**Files to touch**:

| Verb   | Path                              |
| ------ | --------------------------------- |
| CREATE | `migrations/NNNN_description.sql` |
| MODIFY | `<shared-lib>/...`                |

**Tests (TDD)** -- write first, verify they fail:

| Test File              | Test Function           | Verifies |
| ---------------------- | ----------------------- | -------- |
| `tests/test_models.py` | `test_new_field_exists` | FR-001   |

**Acceptance**:

-   [ ] AC-001: ...

**Traceability**: FR-001, Decision 1

---

### $1-1B: {Task Title}

<!-- Repeat the same structure for each task. -->

| Field          | Value        |
| -------------- | ------------ |
| **PR Scope**   |              |
| **Service(s)** |              |
| **Size**       | S / M / L    |
| **Priority**   | P1 / P2 / P3 |

**What to implement**: ...

**Files to touch**:

| Verb   | Path |
| ------ | ---- |
| MODIFY |      |

**Tests (TDD)**:

| Test File | Test Function | Verifies |
| --------- | ------------- | -------- |
|           |               |          |

**Acceptance**:

-   [ ] AC-002: ...

**Traceability**: FR-002, Decision 1

---

## Workstream 2: {Workstream Name from plan.md}

<!-- Continue with Workstream 2 tasks following the same structure. -->

---

## Summary

| Task  | Task State | Size | PR  |
| ----- | ---------- | ---- | --- |
| $1-1A | TODO       | S    |     |
| $1-1B | TODO       | M    |     |

## Coverage Validation

<!-- WHAT: Cross-reference check. EVERY FR-NNN and AC-NNN from spec.md must appear
     in at least one task. Fill AFTER generating tasks. Gaps = missing tasks.
     The /spec analyze command validates this automatically. -->

| Requirement | Task(s) | Covered?           |
| ----------- | ------- | ------------------ |
| FR-001      | $1-1A   | Yes                |
| FR-002      | --      | **NO -- add task** |
| AC-001      | $1-1A   | Yes                |

---

## Definition of Done

<!-- WHAT: Concrete, verifiable conditions that define "Done" for this ticket.
     WHY: Prevents ambiguity about completion. All items must be true before
     status transitions to Done. Cross-cutting items come from workflow.md.
     The /spec reconcile command validates implementation drift against this. -->

### Task Completion

-   [ ] All tasks in Quick View are checked off
-   [ ] `/spec analyze` reports 0 CRITICAL findings
-   [ ] All PRs merged to target branch

### Acceptance Verification

-   [ ] Every AC-NNN has been verified (automated test or manual sign-off)
-   [ ] Every SC-NNN has baseline measurement recorded
-   [ ] Edge cases (EC-NNN) covered by tests

### Cross-Cutting Concerns

-   [ ] `.env.sample` updated (if new env vars introduced)
-   [ ] IAC repo updated (if infrastructure changes required)
-   [ ] Confluence docs updated (if user-facing behavior changed)
-   [ ] Runbook updated (if operational procedures changed)
