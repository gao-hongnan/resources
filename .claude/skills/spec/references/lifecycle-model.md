# Lifecycle Model Reference

Canonical source of truth for `/spec` lifecycle ownership.

If `SKILL.md`, `frontmatter-schema.md`, or a template comment conflicts with this document, this document wins.

---

## Field Ownership

| Field         | Meaning                                                                | Changed By                                                                              |
| ------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `status`      | Lifecycle state of the spec                                            | `/spec platonic` initializes it; `/spec transition` changes it afterward                |
| `phase`       | Last mutating document-generation step that updated spec artifacts     | `/spec platonic`, `/spec aporia`, `/spec dialectic`, `/spec synthesis`, `/spec praxis`  |
| `transitions` | Append-only audit log of lifecycle status changes after initialization | `/spec transition` only                                                                 |

Rules:

-   `status` is lifecycle only. It MUST NOT be used to describe document-generation progress.
-   `phase` is workflow progress only. It MUST NOT be used as a lifecycle proxy.
-   `transitions` records `status` changes only. It does not log `phase` changes.
-   `/spec analyze` may recommend a lifecycle transition, but it does not perform one.
-   `/spec platonic` initializes `status: Draft`, `phase: platonic`, and `transitions: []`.

---

## Canonical Values

### status

`Draft -> Clarified -> Ready -> In Progress -> Done`

### phase

`platonic`, `aporia`, `dialectic`, `synthesis`, `praxis`

`socratic` is tracked in `socratic-output.md` and `history.json`, not in `spec.md` frontmatter.

There is no `done` phase. Lifecycle completion is represented by `status`, not `phase`.

---

## Lifecycle Transitions

Only `/spec transition` changes `status`.

### Forward

| From          | To            | Guard                                                                                            |
| ------------- | ------------- | ------------------------------------------------------------------------------------------------ |
| `Draft`       | `Clarified`   | L1 checks pass and there are 0 `[NEEDS CLARIFICATION]` markers                                   |
| `Clarified`   | `Ready`       | Required artifacts exist, `/spec analyze` reports 0 CRITICAL findings, and the spec achieves L3+ |
| `Ready`       | `In Progress` | Implementation has actually started                                                              |
| `In Progress` | `Done`        | Definition of Done is satisfied                                                                  |

### Backward

| From          | To            | Guard                                                                |
| ------------- | ------------- | -------------------------------------------------------------------- |
| `Clarified`   | `Draft`       | Clarification work uncovered missing or incorrect requirements       |
| `Ready`       | `Clarified`   | Design or planning changes invalidate readiness                      |
| `In Progress` | `Ready`       | Execution paused because the plan must be refreshed                  |
| `Done`        | `In Progress` | Follow-up implementation work reopens the ticket                     |
| `Done`        | `Clarified`   | A merged implementation invalidates the spec and requires replanning |

Backward transitions require a reason.

---

## Command Ownership

| Command      | Lifecycle Effect                                                                      |
| ------------ | ------------------------------------------------------------------------------------- |
| `socratic`   | Writes `socratic-output.md` only. Does not touch `status`, `phase`, or `transitions`. |
| `platonic`   | Creates `spec.md`; initializes `status: Draft`, `phase: platonic`, `transitions: []`. |
| `aporia`     | Updates `phase: aporia` only.                                                         |
| `dialectic`  | Updates `phase: dialectic` only.                                                      |
| `synthesis`  | Updates `phase: synthesis` only.                                                      |
| `praxis`     | Updates `phase: praxis` only.                                                         |
| `analyze`    | Read-only. May recommend `/spec transition ...`, but changes nothing.                 |
| `transition` | Updates `status` and appends one `transitions` entry. Does not change `phase`.        |
| `status`     | Read-only.                                                                            |
| `export`     | Writes `features.json` only. Does not change `status` or `phase`.                     |
| `import`     | Updates `tasks.md` task state only. Does not change `status` or `phase`.              |
| `reconcile`  | Read-only.                                                                            |
| `config`     | Read-only.                                                                            |

---

## Practical Consequences

-   `Ready` no longer depends on a vague "suggested" behavior. `analyze` can only recommend readiness; `/spec transition ... Ready ...` is the explicit state change.
-   `phase` and `status` do not need a hard-coded compatibility matrix. Examples of valid combinations include:
    -   `status: Clarified`, `phase: praxis`
    -   `status: Ready`, `phase: praxis`
    -   `status: In Progress`, `phase: praxis`
-   Implementation workstreams inside `plan.md` and `tasks.md` should avoid the label "Phase" to reduce confusion with frontmatter `phase`.
