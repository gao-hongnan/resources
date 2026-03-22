---
name: spec
description: >-
    SDD workflow for creating specifications, plans, and task decompositions. Triggers on "write a spec", "specify", "plan for", "decompose into tasks", "task breakdown", "SDD", or when user invokes /spec.
argument-hint: "<sub-command> [TICKET] [description]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Glob, Grep, Read, Write, Edit, Bash, Agent, AskUserQuestion, WebFetch, Skill(socratic *)
---

# Spec -- Review-Hybrid SDD Workflow

Create, plan, and decompose feature specifications using the Spec-Design-Deliver (SDD) lifecycle.

## Sub-Commands

Detect the sub-command from conversation context or explicit invocation:

| Sub-Command  | Intent                                       | Example                                                  |
| ------------ | -------------------------------------------- | -------------------------------------------------------- |
| `socratic`   | Deep Socratic discovery before spec          | "/spec socratic FROSTY-147 'DB query optimization'"      |
| `platonic`   | Scaffold a new spec from templates           | "/spec platonic FROSTY-147 'DB query optimization'"      |
| `aporia`     | Resolve ambiguities interactively (max 5 Qs) | "/spec aporia FROSTY-147"                                |
| `dialectic`  | Generate implementation plan from spec       | "/spec dialectic FROSTY-147"                             |
| `synthesis`  | Generate cross-cutting architecture diagrams | "/spec synthesis FROSTY-147"                             |
| `praxis`     | Decompose plan into PR-sized work units      | "/spec praxis FROSTY-147"                                |
| `analyze`    | Read-only readiness and consistency check    | "/spec analyze FROSTY-147"                               |
| `transition` | Explicit lifecycle status change             | "/spec transition FROSTY-147 Ready 'readiness approved'" |
| `status`     | List all specs with lifecycle status         | "/spec status"                                           |
| `export`     | Export tasks.md to features.json for harness | "/spec export FROSTY-147"                                |
| `import`     | Import harness progress into tasks.md        | "/spec import FROSTY-147"                                |
| `reconcile`  | Detect drift between spec and codebase       | "/spec reconcile FROSTY-147"                             |
| `config`     | Dump resolved config and environment         | "/spec config"                                           |

## Parsing

Arguments are passed via string substitution:

-   `$0` -> SUBCOMMAND: first argument (one of: `socratic`, `platonic`, `aporia`, `dialectic`, `synthesis`, `praxis`, `analyze`, `transition`, `status`, `export`, `import`, `reconcile`, `config`)
-   `$1` -> TICKET: second argument (e.g., `FROSTY-147`) -- required for all sub-commands except `status` and `config`
-   `$ARGUMENTS` -> full argument string -- for `socratic` and `platonic`, everything after TICKET is the DESCRIPTION; for `transition`, everything after TICKET is `TARGET_STATUS` plus optional REASON

Examples:

-   `/spec socratic FROSTY-147 "DB query optimization"` -> `$0`=socratic, `$1`=FROSTY-147, description from `$ARGUMENTS`
-   `/spec platonic FROSTY-147 "DB query optimization"` -> `$0`=platonic, `$1`=FROSTY-147, description from `$ARGUMENTS`
-   `/spec dialectic FROSTY-147` -> `$0`=dialectic, `$1`=FROSTY-147
-   `/spec transition FROSTY-147 Ready "readiness approved"` -> `$0`=transition, `$1`=FROSTY-147, target status + reason from `$ARGUMENTS`
-   `/spec status` -> `$0`=status

## Templates

All scaffolding uses templates from `${CLAUDE_SKILL_DIR}/templates/`:

| Template                                                       | Used By                     |
| -------------------------------------------------------------- | --------------------------- |
| `${CLAUDE_SKILL_DIR}/../socratic/templates/socratic-output.md` | `socratic` (via delegation) |
| `${CLAUDE_SKILL_DIR}/templates/spec.md`                        | `platonic`                  |
| `${CLAUDE_SKILL_DIR}/templates/plan.md`                        | `dialectic`                 |
| `${CLAUDE_SKILL_DIR}/templates/synthesis.md`                   | `synthesis`                 |
| `${CLAUDE_SKILL_DIR}/templates/tasks.md`                       | `praxis`                    |

Reference docs:

| Reference                                              | Used By                                                                                     |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| `${CLAUDE_SKILL_DIR}/references/analysis-rules.md`     | `analyze`, `synthesis`, `reconcile`                                                         |
| `${CLAUDE_SKILL_DIR}/references/quality-checklist.md`  | `platonic`, `dialectic`, `synthesis`, `praxis`, `analyze`                                   |
| `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md` | `platonic`, `aporia`, `dialectic`, `synthesis`, `praxis`, `transition` (validation)         |
| `${CLAUDE_SKILL_DIR}/references/lifecycle-model.md`    | `platonic`, `aporia`, `dialectic`, `synthesis`, `praxis`, `analyze`, `transition`, `status` |
| `${CLAUDE_SKILL_DIR}/references/defaults.yaml`         | all sub-commands (tunables)                                                                 |
| `${CLAUDE_SKILL_DIR}/scripts/load-defaults.sh`         | all sub-commands (config preprocessor)                                                      |

## Effective Configuration

Values below are the merged result of `defaults.yaml` + any `specs/.specrc.yaml` overrides. Use these values for all tunables — they override any numbers mentioned elsewhere in this document.

!`bash ${CLAUDE_SKILL_DIR}/scripts/load-defaults.sh`

## Lifecycle Ownership

Lifecycle semantics are defined in `${CLAUDE_SKILL_DIR}/references/lifecycle-model.md`.

Apply these rules exactly:

-   `status` is lifecycle only
-   `phase` is document-generation progress only
-   `/spec platonic` initializes `status: Draft`, `phase: platonic`, `transitions: []`
-   `/spec transition` is the only command that changes `status` after initialization
-   `/spec analyze`, `/spec status`, `/spec reconcile`, and `/spec config` are read-only and MUST NOT mutate `status`, `phase`, `transitions`, or `history.json`

See `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md` for field types and `${CLAUDE_SKILL_DIR}/references/lifecycle-model.md` for canonical values, guards, and command ownership.

## Compliance Gates

These gates prevent producing incomplete deliverables:

| #   | Gate                         | Blocks              | Condition                                                                                               |
| --- | ---------------------------- | ------------------- | ------------------------------------------------------------------------------------------------------- |
| 1   | **Clarification gate**       | `dialectic`         | No `[NEEDS CLARIFICATION]` markers remain in spec.md. If found, STOP and suggest `/spec aporia`.        |
| 2   | **Acceptance criteria gate** | `dialectic`         | Min 2 AC-NNN items in Given/When/Then format + min 2 SC-NNN items + min 2 EC-NNN items with AC mapping. |
| 3   | **Architecture gate**        | `praxis`            | plan.md has at least one `### Decision N:` subsection with non-empty Context AND Decision fields.       |
| 4   | **Traceability gate**        | `praxis`            | plan.md Verification Strategy references at least one AC-NNN from spec.md.                              |
| 5   | **Inline diagram gate**      | `praxis`            | plan.md has at least one inline `#### SEQ-NNN:` Mermaid sequence diagram within a Decision section.     |
| 6   | **Coverage gate** (advisory) | None (warning only) | After tasks.md generation, warn if any FR-NNN from spec.md has no implementing task.                    |

If gates 1-5 fail, STOP and report what needs to be resolved before proceeding. Gate 6 is advisory: warn but do not block.

## Workflow

Execute the sub-command workflow directly. Follow the constraints, enforcement rules, and exploration protocol below.

## Constraints

-   ALWAYS read the relevant template from `${CLAUDE_SKILL_DIR}/templates/` before generating any document
-   ALWAYS explore the codebase to fill sections with real data (service names, file paths, existing patterns)
-   NEVER generate implementation code in spec.md -- pseudocode in the Critical Algorithm section only
-   NEVER generate imperative code in plan.md -- SQL migrations (declarative) are the only exception
-   ALWAYS verify references link to real files that exist in the repo

## Precision Enforcement

1. **NEEDS CLARIFICATION limit**: Max `clarification.max_markers` markers (from config). Beyond that, make informed guesses and document in Assumptions. Prioritize: scope > security > UX > technical.

2. **Mandatory section check**: Before writing, verify all `*(mandatory)*` sections have real content. Refuse to write if mandatory sections would be empty placeholders.

3. **Cross-reference validation**: After writing tasks.md, verify:

    - Every FR-NNN appears in at least one task's "What to implement"
    - Every AC-NNN appears in at least one task's "Acceptance"
    - Every Decision appears in at least one task's "Traceability" Report gaps before completing.

4. **Measurability check**: Every AC-NNN must use Given/When/Then. Every SC-NNN must include a number. Reject "should work correctly" or "must be fast."

5. **Task size guard**: >`tasks.max_files_per_pr` files = split.

    > `tasks.max_services_per_task` service = split (exception: shared lib + consumer).

6. **N/A justification**: Never silently delete optional sections. Write "N/A -- [reason]."

## Codebase Exploration

When filling templates, actively explore the codebase:

-   **Service Impact**: Search for the ticket ID, related module names, and affected file paths
-   **Existing Patterns**: Check `playbook/patterns/` for applicable design docs and ADRs
-   **Cross-Service Concerns**: Check `<shared-lib>/...` for shared code.
-   **File Paths**: Use Glob to find real file paths for the "Files to touch" sections in tasks
-   **Test Paths**: Identify existing test file locations to place new tests consistently

## Workspace Safety

All spec operations enforce these invariants:

1. **Ticket format**: TICKET must match `[A-Z]+-\d+` (Jira) or `DRAFT-\d{4}` (exploratory). Reject anything else.
2. **Slug format**: Slug must match `[a-z0-9]+(-[a-z0-9]+){2,4}` (3-5 hyphenated segments, lowercase alphanumeric only). Reject slugs with special characters.
3. **Path containment**: All file writes MUST target inside `specs/{TICKET}-{slug}/`. Never write outside the spec directory. Validate path prefix before every write.

If any invariant fails, STOP and report the violation. Do not attempt to auto-correct.

## Logging

Every mutating sub-command invocation appends a structured event to `specs/{TICKET}-{slug}/history.json`.

Event schema:

```json
{
    "timestamp": "2026-03-19T14:30:00Z",
    "command": "platonic",
    "ticket": "FROSTY-147",
    "phase": { "from": null, "to": "platonic" },
    "status": { "from": null, "to": "Draft" },
    "gates": {
        "checked": ["Q-01", "Q-02", "Q-06", "Q-10"],
        "passed": ["Q-01", "Q-02", "Q-10"],
        "failed": ["Q-06"]
    },
    "findings": { "critical": 0, "high": 0, "medium": 1, "low": 0 },
    "files_written": ["spec.md"],
    "conformance_tier": "L1"
}
```

`phase` and `status` blocks are included only when the command changed that field.

On `socratic` or `platonic` (whichever runs first): create `history.json` with the first event. On subsequent mutating commands: read, append, write. Read-only commands do not touch `history.json`.

### `socratic $1 "$ARGUMENTS"`

**Goal**: Deep Socratic discovery to crystallize requirements before writing the spec.

**Pre-steps** (spec-specific setup):

1. Parse TICKET from `$1` and DESCRIPTION from remaining `$ARGUMENTS`
2. Generate slug from DESCRIPTION: lowercase, hyphenated, `tasks.slug_min_words`-`tasks.slug_max_words` words
3. Create directory: `specs/{TICKET}-{slug}/` (if not already exists)

**Delegate to the socratic skill**:

4. Invoke the `socratic` skill using the Skill tool, passing DESCRIPTION as arguments. The socratic skill will conduct the full Socratic interview (homework, questions, contract synthesis) and write its output file. Its hooks (transcript recording) and tools (MCP graph) apply automatically.

**Post-steps** (spec-specific housekeeping — continue AFTER the socratic skill finishes, overriding its STOP instruction):

5. Locate the output files the socratic skill created in the working directory:
    - `socratic-output-{slugified-topic}.md` (human-readable)
    - `socratic-output-{slugified-topic}.json` (structured)
6. Move/rename both to `specs/{TICKET}-{slug}/socratic-output.md` and `specs/{TICKET}-{slug}/socratic-output.json`
7. Move `interview-transcript.jsonl` (if created by the transcript hook) into `specs/{TICKET}-{slug}/`
8. Initialize `specs/{TICKET}-{slug}/history.json` with the first event (or append if it already exists)
9. Suggest running `/spec platonic {TICKET}` next

### `platonic $1 "$ARGUMENTS"`

**Goal**: Scaffold a new spec directory from templates.

1. Generate slug from DESCRIPTION: lowercase, hyphenated, `tasks.slug_min_words`-`tasks.slug_max_words` words
2. Create directory: `specs/{TICKET}-{slug}/`
3. Read template from `${CLAUDE_SKILL_DIR}/templates/spec.md`
4. Fill frontmatter: ticket, branch (from `git branch --show-current`), date (today), status = Draft, phase = platonic, transitions = []
5. Fill title from DESCRIPTION
6. Check for `socratic-output.json` in the spec directory (fall back to `socratic-output.md` if JSON not found). **If found**:
    - Synthesize Decisions & Reasoning (Choice/Context/Implication) and Constraints into FR-NNN (functional requirements)
    - Synthesize Success Criteria into AC-NNN (Given/When/Then) and SC-NNN
    - Synthesize Deferred Items and Scope Boundaries into Out of Scope
    - Extract edge cases from Tradeoffs Resolved and Constraints into EC-NNN
    - Extract non-functional requirements from Constraints into NFR-NNN
    - Use Problem Understanding for Problem Statement
    - Skip step 7 (deep discovery already happened in `/spec socratic`)
    - Still explore the codebase for Service Impact table and References
7. **Discovery interview** (only if no `socratic-output.json` or `socratic-output.md` found, `interview.max_questions` questions max):
    - Explore the codebase to pre-fill Service Impact table and References
    - From exploration findings, identify ambiguities that codebase context alone cannot resolve
    - Use `AskUserQuestion` for each, with a recommended default based on exploration
    - Priority: scope > format > constraints (skip generic questions -- only ask what exploration couldn't resolve)
    - User can say "skip" to accept all defaults and proceed without interview
    - Fold answers into the spec content (replace would-be `[NEEDS CLARIFICATION]` markers)
8. Write `specs/{TICKET}-{slug}/spec.md`
9. Validate frontmatter against `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md` -- report any type/enum/pattern violations
10. Run quality checklist L1 tier: Q-01, Q-02, Q-06, Q-10 (see `${CLAUDE_SKILL_DIR}/references/quality-checklist.md`)
11. Initialize `specs/{TICKET}-{slug}/history.json` with the first event
12. Report what was created, conformance tier achieved, and what sections need human input

### `aporia $1`

**Goal**: Resolve ambiguities in spec.md interactively.

1. Find spec directory: `specs/{TICKET}-*/`
2. Read `spec.md`
3. Scan for:
    - `[NEEDS CLARIFICATION]` markers
    - Ambiguous adjectives without metrics (see `${CLAUDE_SKILL_DIR}/references/analysis-rules.md` Pass 3)
4. Generate max `clarification.max_questions_per_session` prioritized clarification questions
    - Priority order: scope > security > UX > technical
5. Present ONE question at a time via `AskUserQuestion` with a recommended answer based on codebase exploration
6. After each accepted answer: update spec.md immediately (atomic write)
7. After loop: update `phase: aporia` in frontmatter
8. Validate frontmatter against `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md`
9. If 0 `[NEEDS CLARIFICATION]` markers remain and L1 checks pass: suggest `/spec transition $1 Clarified "All clarification markers resolved"`
10. Report sections touched
11. Cap: `clarification.max_questions_per_session` questions max per session. User can say "done" to stop early.

### `dialectic $1`

**Goal**: Generate implementation plan with inline architecture diagrams from a completed spec.

1. Find the spec directory: `specs/{TICKET}-*/`
2. Read `spec.md` in that directory
3. **GATE 1** (Clarification): If fails → STOP, list markers, suggest `/spec aporia`.
4. **GATE 2** (Acceptance criteria): If fails → STOP, list what's missing.
5. Read template from `${CLAUDE_SKILL_DIR}/templates/plan.md`
6. Explore the codebase per the Codebase Exploration section, focusing on patterns and cross-service concerns that inform architecture decisions.
7. **Citation pass**: For each Architecture Decision making claims about external tools, protocols, libraries, or system behaviors: a. Judge whether the claim is about external behavior a developer can't verify from the repo. If yes, it needs a source. b. Use WebFetch to retrieve the official documentation or authoritative source for the claimed behavior. c. Extract a confirming quote or section reference. d. Add the URL and brief description to the decision's **Sources** field. e. For Industry Precedent bullets, include URLs inline. f. If WebFetch fails or no source is found, mark with `[UNVERIFIED]`.
8. Generate `plan.md` with Technical Context, architecture decisions, cross-service concerns, and verification strategy mapped to acceptance criteria
9. **Inline diagram pass**: For each Architecture Decision involving service-to-service communication: a. Generate an inline Mermaid sequence diagram within the Decision section using `#### SEQ-NNN:` heading b. Use real service names from spec.md Service Impact table as participants c. Reference FR-NNN and/or AC-NNN in the diagram heading d. Add a **Narrative** explaining the flow in 2-3 sentences e. For decisions about internal code organization with no service interaction, write "N/A — internal decision, no service interaction" in the **Diagram** field
10. Fill the Decision Diagram Inventory table with all inline SEQ-NNN diagrams
11. Write `specs/{TICKET}-{slug}/plan.md`
12. Update spec.md frontmatter: `phase: dialectic`
13. Validate frontmatter against `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md`
14. Run quality checks: Q-24, Q-32, Q-33
15. Append event to `history.json`
16. Report: plan generated, inline diagrams created, and suggest `/spec synthesis` (if cross-cutting views needed) or `/spec praxis` (if single-service or simple change)

### `synthesis $1`

**Goal**: Generate cross-cutting system-level diagrams that span multiple Architecture Decisions.

This stage is **optional** — only needed when the change involves cross-cutting concerns that no single Decision captures. Per-decision sequence diagrams are already inline in plan.md (generated by `/spec dialectic`).

1. Find the spec directory: `specs/{TICKET}-*/`
2. Read `spec.md` and `plan.md` in that directory
3. Read template from `${CLAUDE_SKILL_DIR}/templates/synthesis.md`
4. Determine required cross-cutting diagram types by analyzing spec/plan complexity:
    - **Data Flow**: Include if 2+ services have data dependencies with transformations (check Cross-Service Concerns table)
    - **Component**: Include if 3+ services interact or a new service is introduced (check spec.md Service Impact table)
    - **State**: Include if a state machine spans multiple Architecture Decisions, or any entity has 3+ states with cross-decision guards
5. Explore the codebase for real service names, module boundaries, and interaction patterns (API routes, queue consumers, DB access patterns)
6. Generate diagrams with:
    - Participants matching the Service Impact table from spec.md
    - Messages reflecting real APIs, queue names, and DB operations found in codebase exploration
    - References to FR-NNN and/or AC-NNN in each diagram heading
7. For conditional sections (Data Flow, Component, State):
    - If criteria met: include with justification in the Narrative
    - If criteria not met: write "N/A -- [reason]" (never silently omit)
8. Fill the Diagram Inventory table with all diagram IDs, types, titles, references, and conditional status
9. Update frontmatter: `diagram_count`, `diagram_types` list
10. Write `specs/{TICKET}-{slug}/synthesis.md`
11. Update spec.md frontmatter: `phase: synthesis`
12. Validate frontmatter against `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md`
13. Run quality checks: Q-32, Q-35
14. Append event to `history.json`
15. Report: diagrams generated, types included/omitted with reasons, and suggest `/spec praxis`

### `praxis $1`

**Goal**: Decompose plan into PR-sized work units.

**Output**: ONLY `tasks.md` + spec.md frontmatter update. This command MUST NOT create, modify, or delete any implementation code, config, or test files. The task cards _describe_ future work — they do not _perform_ it.

1. Find the spec directory: `specs/{TICKET}-*/`
2. Read `spec.md` and `plan.md` (and optionally `synthesis.md` if it exists)
3. **GATE 3** (Architecture): If fails → STOP and report.
4. **GATE 4** (Traceability): If fails → STOP and report.
5. **GATE 5** (Inline diagram): If plan.md has no inline `#### SEQ-NNN:` → STOP, suggest `/spec dialectic` to regenerate plan with inline diagrams.
6. Read template from `${CLAUDE_SKILL_DIR}/templates/tasks.md`
7. For each workstream in plan.md:
    - Create tasks sized for a single PR (target: 1-`tasks.max_files_per_pr` files changed)
    - Assign task IDs: `{TICKET}-{WORKSTREAM}{SEQ}` (e.g., `FROSTY-147-1A`)
    - Map each task to spec FRs and plan Decisions
    - Identify exact file paths (use Glob/Grep to find real paths)
    - Define TDD test functions with real test file paths
8. Build dependency graph showing parallelization opportunities
9. Generate Quick View checklist
10. Fill Coverage Validation table
11. Write `specs/{TICKET}-{slug}/tasks.md`
12. **GATE 6 (Coverage, advisory)**: Warn if any FR-NNN has no implementing task
13. Update spec.md frontmatter: `phase: praxis`
14. Validate frontmatter against `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md`

### `analyze $1`

**Goal**: Read-only readiness and cross-artifact consistency check.

1. Find spec directory: `specs/{TICKET}-*/`
2. Read all available files: spec.md, plan.md, tasks.md, and synthesis.md (if exists)
3. Read detection rules from `${CLAUDE_SKILL_DIR}/references/analysis-rules.md`
4. Run analysis passes:
    - **Passes 1-6**: Coverage, Consistency, Ambiguity, Traceability, Underspecification, File Existence
    - **Pass 8a**: Inline diagram consistency (plan.md) — always run if plan.md exists
    - **Pass 8b**: Cross-cutting diagram consistency (synthesis.md) — only run if synthesis.md exists
    - **Pass 9**: Citations
5. Output findings table with severity (CRITICAL/HIGH/MEDIUM/LOW)
6. Evaluate conformance tier achieved (L1/L2/L3/L4) based on `${CLAUDE_SKILL_DIR}/references/quality-checklist.md`
7. **NEVER modify files** -- strictly read-only
8. Report: findings table + conformance tier + next steps to reach next tier
9. If 0 CRITICAL findings and L3+ achieved: recommend `/spec transition $1 Ready "analyze reported 0 CRITICAL findings and L3+ readiness"`

### `transition $1 "$ARGUMENTS"`

**Goal**: Explicitly change lifecycle status.

1. Find spec directory: `specs/{TICKET}-*/`
2. Read `spec.md`
3. Read `${CLAUDE_SKILL_DIR}/references/lifecycle-model.md` and `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md`
4. Parse `TARGET_STATUS` from the arguments after TICKET. Multi-word statuses may be quoted. Parse optional REASON from any remaining text.
5. Validate the requested status transition against the lifecycle model guards. If the guard fails, STOP and explain why.
6. For backward transitions, require a non-empty reason from the user.
7. Update spec.md frontmatter:
    - change `status` only
    - do NOT change `phase`
    - append one `transitions` entry with `date`, `from`, `to`, `reason`, `by`
8. Validate frontmatter against `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md`
9. Write `spec.md`
10. Append event to `history.json`
11. Report: previous status, new status, retained phase, and reason

### `status`

**Goal**: List all specs with their current lifecycle status.

1. Glob for `specs/*/spec.md`
2. Read frontmatter from each spec.md (ticket, status, phase, date)
3. Count tasks completed vs total from each tasks.md (if exists)
4. Output a summary table:

    ```text
    | Spec | Status | Phase | Tasks | Date |
    |------|--------|-------|-------|------|
    | FROSTY-147-consistency-... | Draft | aporia | 3/7 | 2026-03-17 |
    ```

### `export $1`

**Goal**: Bridge spec artifacts to harness by converting tasks.md into features.json.

1. Find spec directory: `specs/{TICKET}-*/`
2. Read `tasks.md` -- STOP if not found (suggest running `/spec praxis` first)
3. For each task card in tasks.md, construct a Feature object:
    - `id`: task ID (e.g., `FROSTY-147-1A`)
    - `title`: task title
    - `description`: "What to implement" content
    - `files`: list from "Files to touch" table (verb + path)
    - `tests`: list from "Tests (TDD)" table
    - `acceptance`: list of AC-NNN items from "Acceptance" section
    - `dependencies`: inferred from Dependency Graph
    - `size`: S/M/L from task metadata
    - `priority`: P1/P2/P3 from task metadata
4. Write `specs/{TICKET}-{slug}/features.json`
5. Report: number of features exported, output path
6. Append event to `history.json`

### `import $1`

**Goal**: Import harness execution progress back into tasks.md.

1. Find spec directory: `specs/{TICKET}-*/`
2. Read `specs/{TICKET}-{slug}/progress.json` (or `features.json` with status) -- STOP if not found
3. For each completed feature in progress data:
    - Check the corresponding task checkbox in tasks.md Quick View (`- [x]`)
    - Update the Summary table task state column (TODO -> DONE)
4. For each in-progress feature:
    - Update Summary table task state (TODO -> IN PROGRESS)
5. Write updated `tasks.md`
6. If work has started: suggest `/spec transition $1 In Progress "Implementation has started"`
7. If all tasks complete: suggest `/spec transition $1 Done "All tasks complete and Definition of Done satisfied"`
8. Append event to `history.json`

### `reconcile $1`

**Goal**: Detect drift between spec artifacts and the actual codebase.

1. Find spec directory: `specs/{TICKET}-*/`
2. Read all 3 files: spec.md, plan.md, tasks.md
3. Read reconciliation rules from `${CLAUDE_SKILL_DIR}/references/analysis-rules.md` Pass 7
4. Determine the base branch from spec.md frontmatter `branch` field
5. Run 4 reconciliation checks:
    - **Implementation drift**: compare tasks.md "Files to touch" against `git diff --name-only` on the branch
    - **Completion state**: compare tasks.md checkboxes against actual git commits for those files
    - **Scope creep**: detect files/services modified on branch that appear in no task
    - **Branch staleness**: compare spec date against latest commit date
6. Output findings table (same format as `/spec analyze`)
7. **NEVER modify files** -- strictly read-only

### `config`

**Goal**: Dump resolved configuration and environment for debugging.

1. Report `CLAUDE_SKILL_DIR` resolved path (from template paths in this prompt)
2. Check if `specs/.specrc.yaml` exists:
    - If yes: Read and display its contents
    - If no: report "No specrc override found"
3. Run `bash ${CLAUDE_SKILL_DIR}/scripts/load-defaults.sh` and display the merged YAML output
4. Display the "Effective Configuration" section from this prompt (already injected by preprocessor) — confirm it matches the script output
5. **NEVER modify files** — strictly read-only. No history.json event.

## Error Handling

-   If SUBCOMMAND is not recognized: show usage with examples for all 13 sub-commands
-   If TICKET directory already exists for `platonic`: warn and ask before overwriting
-   If TICKET format is invalid (not `[A-Z]+-\d+` or `DRAFT-\d{4}`): reject with format guidance
-   If spec.md not found for `aporia`/`dialectic`/`praxis`/`analyze`/`transition`/`export`/`import`/`reconcile`: suggest running `platonic` first
-   If plan.md not found for `synthesis`/`praxis`/`analyze`/`reconcile`: suggest running `dialectic` first
-   If plan.md has no inline SEQ diagrams for `praxis`: suggest running `/spec dialectic` again to generate inline diagrams
-   If tasks.md not found for `analyze`/`export`/`import`/`reconcile`: suggest running `praxis` first (analyze can run on partial sets but will note missing files)
-   If features.json not found for `import`: suggest running `export` first or checking harness output
-   If `transition` target status is invalid or not permitted by `lifecycle-model.md`: report the valid next states and required guard
-   If frontmatter validation fails: report which fields failed and the expected types/values from `frontmatter-schema.md`

## Quirks

These quirks eventually should go to hooks.

-   Always check markdownlint formatting for code fencing, and run formatting.
