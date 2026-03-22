# Frontmatter Schema Reference

Typed field definitions for all SDD document types.

This document defines structure only: field names, types, enums, and required fields. Lifecycle semantics for `status`, `phase`, and `transitions` live in `${CLAUDE_SKILL_DIR}/references/lifecycle-model.md`.

---

## spec.md Frontmatter

| Field              | Type   | Required | Default    | Description                                                      |
| ------------------ | ------ | -------- | ---------- | ---------------------------------------------------------------- |
| `ticket`           | string | yes      | --         | Jira ticket ID. Pattern: `[A-Z]+-\d+` or `DRAFT-\d{4}`          |
| `branch`           | string | yes      | --         | Git branch. Supports `${GIT_BRANCH}` env var                     |
| `status`           | enum   | yes      | `Draft`    | Lifecycle state. See `lifecycle-model.md`                        |
| `phase`            | enum   | yes      | `platonic` | Last mutating document-generation step. See `lifecycle-model.md` |
| `date`             | date   | yes      | today      | ISO 8601 format: `YYYY-MM-DD`                                    |
| `template_version` | int    | yes      | `1`        | Template schema version                                          |
| `transitions`      | list   | no       | `[]`       | Lifecycle status change log after initialization                 |

## plan.md Frontmatter

| Field                    | Type   | Required | Default | Description                                       |
| ------------------------ | ------ | -------- | ------- | ------------------------------------------------- |
| `spec`                   | string | yes      | --      | Relative path to spec.md (always `./spec.md`)     |
| `date`                   | date   | yes      | today   | ISO 8601 format: `YYYY-MM-DD`                     |
| `author`                 | string | no       | --      | Author name or `${AUTHOR}` env var                |
| `inline_diagram_count`   | int    | no       | 0       | Number of inline SEQ diagrams within Decisions    |

## tasks.md Frontmatter

| Field                | Type   | Required | Default | Description                 |
| -------------------- | ------ | -------- | ------- | --------------------------- |
| `spec`               | string | yes      | --      | Relative path to spec.md    |
| `plan`               | string | yes      | --      | Relative path to plan.md    |
| `task_count`         | int    | yes      | --      | Total number of task cards  |
| `aggregate_estimate` | enum   | yes      | --      | One of: `S`, `M`, `L`, `XL` |

## synthesis.md Frontmatter

| Field           | Type   | Required | Default | Description                                                  |
| --------------- | ------ | -------- | ------- | ------------------------------------------------------------ |
| `spec`          | string | yes      | --      | Relative path to spec.md                                     |
| `plan`          | string | yes      | --      | Relative path to plan.md                                     |
| `date`          | date   | yes      | today   | ISO 8601 format: `YYYY-MM-DD`                                |
| `diagram_count` | int    | yes      | --      | Total number of cross-cutting diagrams in document           |
| `diagram_types` | list   | yes      | `[]`    | Types present: `data_flow`, `component`, `state`             |

---

## socratic-output.md Frontmatter

| Field             | Type   | Required | Default | Description                         |
| ----------------- | ------ | -------- | ------- | ----------------------------------- |
| `ticket`          | string | yes      | --      | Jira ticket ID                      |
| `date`            | date   | yes      | today   | ISO 8601 format                     |
| `interviewer`     | string | yes      | --      | Always "/spec socratic"             |
| `questions_asked` | int    | yes      | --      | Number of questions in this session |

---

## Transitions Log Schema

Each entry in the `transitions` list records a lifecycle `status` change after initial spec creation:

```yaml
transitions:
    - date: 2026-03-19
      from: Draft
      to: Clarified
      reason: "All clarification markers resolved"
      by: "/spec transition Clarified"
    - date: 2026-03-20
      from: Clarified
      to: Ready
      reason: "analyze reported 0 CRITICAL findings and L3+ readiness"
      by: "/spec transition Ready"
```

| Field    | Type   | Required | Description                             |
| -------- | ------ | -------- | --------------------------------------- |
| `date`   | date   | yes      | ISO 8601 date of the transition         |
| `from`   | enum   | yes      | Previous status value                   |
| `to`     | enum   | yes      | New status value                        |
| `reason` | string | yes      | Why the transition occurred             |
| `by`     | string | yes      | Sub-command or person that triggered it |

---

## Enum Values

### status

| Value         | Description                           |
| ------------- | ------------------------------------- |
| `Draft`       | Spec has markers or missing sections  |
| `Clarified`   | All ambiguities resolved              |
| `Ready`       | Plan + tasks complete, analyze passes |
| `In Progress` | Tasks being executed (PRs open)       |
| `Done`        | All tasks merged, spec archived       |

### phase

| Value        | Description                                    |
| ------------ | ---------------------------------------------- |
| `platonic`   | Initial scaffolding                            |
| `aporia`     | Resolving ambiguities                          |
| `dialectic`  | Generating implementation plan + inline diagrams |
| `synthesis`  | Generating cross-cutting architecture diagrams |
| `praxis`     | Decomposing into PR-sized work units           |

---

## Environment Variable Support

Frontmatter fields support `${ENV_VAR}` syntax for dynamic resolution:

| Variable          | Resolved To                           |
| ----------------- | ------------------------------------- |
| `${GIT_BRANCH}`   | Output of `git branch --show-current` |
| `${JIRA_PROJECT}` | Jira project key prefix               |
| `${AUTHOR}`       | Git user name                         |

Env vars are resolved at write time. Unresolved vars are left as-is and flagged as warnings during `analyze`.

---

## Validation Rules

1. **Type check**: Every field must match its declared type
2. **Required check**: All required fields must be present and non-empty
3. **Enum check**: Enum fields must contain one of the listed values
4. **Date check**: Date fields must be valid ISO 8601 (`YYYY-MM-DD`)
5. **Pattern check**: `ticket` must match `[A-Z]+-\d+` or `DRAFT-\d{4}`
6. **Lifecycle ownership check**: Commands that mutate `status`, `phase`, or `transitions` MUST follow `${CLAUDE_SKILL_DIR}/references/lifecycle-model.md`
