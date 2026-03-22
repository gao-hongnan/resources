# Quality Checklist for Spec Validation

Default quality items checked during the `platonic` sub-command and enforced by
compliance gates, organized into conformance tiers.

---

## Conformance Tiers

Each tier builds on the previous. The `/spec analyze` command reports which tier
a spec satisfies.

| Tier | Name                 | Purpose                  | Blocks          |
| ---- | -------------------- | ------------------------ | --------------- |
| L1   | Minimum Viable       | Enough to start planning | `dialectic`     |
| L2   | Plan-Ready           | Enough to generate tasks | `praxis`        |
| L3   | Implementation-Ready | Enough for harness runs  | harness launch  |
| L4   | Autonomous-Ready     | Unattended execution     | nothing (ideal) |

---

## L1: Minimum Viable (blocks dialectic)

Core structural checks. A spec that fails L1 is not ready for any downstream
work.

| #    | Check                                                                  | Min  | Gate       |
| ---- | ---------------------------------------------------------------------- | ---- | ---------- |
| Q-01 | All `*(mandatory)*` sections have real content (not just placeholders) | --   | platonic   |
| Q-02 | Functional Requirements count                                          | >= 2 | platonic   |
| Q-06 | `[NEEDS CLARIFICATION]` marker count                                   | <= 3 | platonic   |
| Q-10 | All optional sections use "N/A -- [reason]" not silent deletion        | --   | platonic   |

**Pass criteria**: All 4 checks pass. Failure blocks `/spec dialectic`.

---

## L2: Plan-Ready (blocks praxis)

Content quality sufficient for architecture decisions. Includes all L1 checks.

| #    | Check                                                               | Min  | Gate       |
| ---- | ------------------------------------------------------------------- | ---- | ---------- |
| Q-03 | Acceptance Criteria count (Given/When/Then format)                  | >= 2 | dialectic  |
| Q-04 | Success Criteria count (measurable outcomes)                        | >= 2 | dialectic  |
| Q-05 | Edge Cases count (with AC mapping)                                  | >= 2 | dialectic  |
| Q-07 | No orphaned cross-references (every AC-NNN in EC maps to a real AC) | --   | dialectic  |
| Q-08 | Given/When/Then format in ALL Acceptance Criteria                   | --   | dialectic  |
| Q-09 | Every SC-NNN contains at least one number                           | --   | dialectic  |
| Q-11 | Technical Context table fully populated (no empty Value cells)      | --   | dialectic  |
| Q-25 | Glossary terms (if present) appear in spec body text                | >= 3 | dialectic  |

**Pass criteria**: L1 + all 8 checks pass. Failure blocks `/spec praxis`.

---

## L3: Implementation-Ready (blocks harness)

Full traceability and task sizing. Includes all L2 checks.

| #    | Check                                                                  | Condition                                       | Gate       |
| ---- | ---------------------------------------------------------------------- | ----------------------------------------------- | ---------- |
| Q-12 | At least one Architecture Decision with non-empty Context AND Decision | --                                              | praxis     |
| Q-13 | Verification Strategy references at least one AC-NNN                   | --                                              | praxis     |
| Q-14 | Every AC-NNN from spec appears in Verification Strategy                | --                                              | praxis     |
| Q-15 | Implementation Approach workstreams match Architecture Decisions scope | --                                              | praxis     |
| Q-16 | Every FR-NNN appears in at least one task's "What to implement"        | --                                              | analyze    |
| Q-17 | Every AC-NNN appears in at least one task's "Acceptance"               | --                                              | analyze    |
| Q-18 | Every Decision appears in at least one task's "Traceability"           | --                                              | analyze    |
| Q-19 | Coverage Validation table filled with no "NO" entries                  | --                                              | analyze    |
| Q-20 | Quick View mirrors detailed task cards (count and IDs match)           | --                                              | analyze    |
| Q-21 | PR Scope file count                                                    | <= 3 files per task                             | analyze    |
| Q-22 | Service count per task                                                 | <= 1 service (exception: shared lib + consumer) | analyze    |
| Q-23 | Task size                                                              | No "L" tasks without justification comment      | analyze    |
| Q-24 | At least one inline sequence diagram (`### SEQ-NNN:`) in plan.md       | >= 1 within a Decision section                  | dialectic  |
| Q-26 | Before/After Visualization uses fenced code blocks                     | --                                              | praxis     |
| Q-36 | Architecture Decisions with external claims have non-empty Sources     | No [UNVERIFIED] markers remain                  | praxis     |
| Q-32 | All diagram blocks use fenced ` ```mermaid ` syntax                    | --                                              | dialectic  |
| Q-33 | Every sequence diagram references at least one FR-NNN or AC-NNN        | --                                              | dialectic  |
| Q-34 | Diagram Inventory row count matches actual diagram headings            | --                                              | analyze    |
| Q-35 | Conditional diagram sections in synthesis.md use "N/A -- [reason]"     | --                                              | synthesis  |

**Pass criteria**: L2 + all 19 checks pass. Failure blocks harness launch.

---

## L4: Autonomous-Ready (unattended execution)

Hardened for fully autonomous harness runs without human intervention. Includes
all L3 checks.

| #    | Check                                               | Condition                                     | Gate     |
| ---- | --------------------------------------------------- | --------------------------------------------- | -------- |
| Q-27 | Every task has a smoke test                         | At least 1 test in every task's "Tests (TDD)" | advisory |
| Q-28 | No L-size tasks                                     | All tasks are S or M                          | advisory |
| Q-29 | No cycles in dependency graph                       | DAG validation on task dependencies           | advisory |
| Q-30 | Definition of Done checklist complete               | All DoD items in tasks.md are actionable      | advisory |
| Q-31 | All file paths in "Files to touch" resolve via Glob | No unresolvable paths                         | advisory |

**Pass criteria**: L3 + all 5 checks pass. This is the gold standard for
unattended execution.

---

## How Checks Map to Tiers and Gates

```
L1 (platonic):    Q-01, Q-02, Q-06, Q-10
     |
     v
L1 (aporia):      Resolve [NEEDS CLARIFICATION] markers (Q-06 -> 0)
     |
     v
L2 (dialectic):   Q-03, Q-04, Q-05, Q-07, Q-08, Q-09, Q-11, Q-25, Q-24, Q-32, Q-33
     |
     v
L3 (synthesis):   Q-35
     |
     v
L3 (praxis):      Q-12, Q-13, Q-14, Q-15, Q-21, Q-22, Q-23, Q-26, Q-36
     |
     v
L3 (analyze):     Q-16, Q-17, Q-18, Q-19, Q-20, Q-34
     |
     v
L4 (advisory):    Q-27, Q-28, Q-29, Q-30, Q-31
```

---

## Rejection Patterns

The `/spec` skill MUST reject the following patterns in Acceptance Criteria:

- "should work correctly" -- not testable
- "must be fast" -- not measurable
- "should handle errors gracefully" -- not observable
- "must be scalable" -- no metric
- "should be user-friendly" -- subjective

Replace with Given/When/Then format with specific, measurable outcomes.
