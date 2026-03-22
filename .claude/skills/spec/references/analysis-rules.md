# Analysis Rules for `/spec analyze`

Detection rules for 9 analysis passes (Passes 1-6 + Pass 8a inline diagrams +
Pass 8b cross-cutting diagrams + Pass 9 for citations; Pass 7 for
reconciliation). Each pass produces findings with severity levels: **CRITICAL**
(blocks Ready status), **HIGH**, **MEDIUM**, **LOW**.

---

## Pass 1: Coverage

**Goal**: Every FR-NNN has a task, every AC-NNN has verification.

### FR Coverage

- Regex: `\*\*FR-(\d{3})\*\*` in spec.md
- For each FR-NNN found, search tasks.md for the same `FR-NNN` string
- **CRITICAL** if any FR-NNN has no implementing task
- Check the Coverage Validation table at the bottom of tasks.md for completeness

### AC Coverage

- Regex: `\*\*AC-(\d{3})\*\*` in spec.md
- For each AC-NNN, search:
    - plan.md Verification Strategy `Covers` column for `AC-NNN`
    - tasks.md `Acceptance` sections for `AC-NNN`
- **CRITICAL** if any AC-NNN appears in neither plan.md nor tasks.md
- **HIGH** if AC-NNN appears in tasks.md but not in plan.md Verification
  Strategy

### SC Coverage

- Regex: `\*\*SC-(\d{3})\*\*` in spec.md
- Success Criteria are not required to map to tasks (they are outcomes, not
  tests)
- **MEDIUM** if fewer than 2 SC-NNN items exist in spec.md

### EC Coverage

- Regex: `\*\*\[EC-(\d{3})\]\*\*` in spec.md
- Each EC must reference an AC-NNN: look for `-> AC-\d{3}` or `→ AC-\d{3}` on
  the same line
- **HIGH** if any EC-NNN has no AC mapping

---

## Pass 2: Consistency

**Goal**: No terminology drift or conflicting statements across the spec files.

### Terminology Drift

- Extract key nouns from spec.md Problem Statement (service names, entity names,
  feature names)
- Search for those same terms in plan.md and tasks.md
- **MEDIUM** if a term appears in spec.md but a variant spelling appears in
  plan.md/tasks.md
    - Examples: "pyworker" vs "py-worker", "consistency check" vs
      "consistency-check" vs "ConsistencyCheck"

### State Conflicts

- Extract task states referenced (e.g., TRANSFORMED, CONSISTENCY_DONE) from all
  spec files
- Cross-reference against `<shared-lib>/src/const.ts` if state names are used
- **HIGH** if a state name in specs doesn't match the canonical name in const.ts

### Priority Conflicts

- If an FR is marked P1 in spec.md, any task implementing it should not be
  marked P3
- **MEDIUM** if priority mismatches detected

### Glossary Drift

- If spec.md has a Glossary section (not "N/A"), extract all defined terms from
  the Term column
- Search plan.md and tasks.md for each term; flag variant spellings
  (case-insensitive fuzzy match)
- Examples: "lease" vs "Lease" is OK (case), but "time-bound lease" vs "timeout
  lock" is drift
- **MEDIUM** if a glossary term is absent or replaced by a variant in plan.md or
  tasks.md

---

## Pass 3: Ambiguity

**Goal**: No vague adjectives without metrics.

### Vague Adjective Detection

Search all spec files for terms listed in `defaults.yaml` under
`analysis.vague_adjectives` when NOT followed by a number/metric within
`analysis.vague_context_window` characters.

- **MEDIUM** for each occurrence in spec.md (requirements should be precise)
- **LOW** for each occurrence in plan.md or tasks.md (descriptive context is
  more acceptable)
- Exception: terms inside HTML comments (`<!-- -->`) are ignored (they are
  guidance, not content)

### Unquantified NFRs

- For each NFR-NNN in spec.md, check if it contains at least one number
  (latency, throughput, percentage, count)
- **HIGH** if an NFR has no quantitative measure

---

## Pass 4: Traceability

**Goal**: Complete FR -> Decision -> Task chain.

### Forward Traceability (spec -> plan -> tasks)

- For each FR-NNN in spec.md:
    1. Check plan.md Architecture Decisions reference it (in Context or
       Rationale)
    2. Check tasks.md has a task with `FR-NNN` in "What to implement" or
       "Traceability"
- **HIGH** if FR-NNN has no corresponding Decision context
- **CRITICAL** if FR-NNN has no implementing task

### Backward Traceability (tasks -> plan -> spec)

- For each task's "Traceability" field in tasks.md:
    1. Every FR-NNN listed must exist in spec.md
    2. Every "Decision N" listed must exist in plan.md
- **HIGH** if a task references a non-existent FR or Decision

---

## Pass 5: Underspecification

**Goal**: No tasks referencing files or services not accounted for in the plan.

### Unplanned Files

- Collect all file paths from tasks.md "Files to touch" tables
- Check that the parent service/directory appears in plan.md (Cross-Service
  Concerns or Implementation Approach)
- **MEDIUM** if a file path belongs to a service not mentioned in plan.md

### Unplanned Services

- Collect all services from tasks.md `Service(s)` fields
- Check that each appears in spec.md Service Impact table
- **HIGH** if a task targets a service not in the spec's Service Impact

### Unfenced ASCII Art

- Detect lines containing Unicode box-drawing characters (U+2500-U+257F:
  `┌ ┐ └ ┘ │ ─ ├ ┤ ┬ ┴ ┼` etc.) outside of fenced code blocks
- To determine "outside": track fenced block state by scanning for ` ``` `
  delimiters line-by-line
- **MEDIUM** if box-drawing characters appear in prose (they should be inside
  fenced code blocks for correct rendering)

---

## Pass 6: File Existence

**Goal**: Every file path in "Files to touch" is verifiable.

### Existing File Validation

- For each `MODIFY` verb in tasks.md "Files to touch":
    - Run Glob to verify the file exists
    - **MEDIUM** if file does not exist (might be a typo)
- For each `CREATE` verb:
    - Run Glob to verify the parent directory exists
    - **LOW** if parent directory doesn't exist (might need creation)

### Test File Validation

- For each test file in "Tests (TDD)" tables:
    - If the file already exists, verify the path is correct via Glob
    - **LOW** if test file path doesn't match existing test directory
      conventions

---

## Pass 7: Reconciliation

**Goal**: Detect drift between spec artifacts and actual codebase state. Used by
`/spec reconcile`.

This pass runs ONLY during `/spec reconcile`, not during `/spec analyze` (which
is offline/read-only against the spec documents).

### Implementation Drift

- Collect all file paths from tasks.md "Files to touch" tables (both CREATE and
  MODIFY)
- Run `git diff --name-only {base-branch}...HEAD` to get files actually changed
  on the branch
- Compare the two sets:
    - **HIGH** if a file in tasks.md (MODIFY verb) was NOT changed in git --
      planned work not started
    - **MEDIUM** if a file changed in git does NOT appear in any task --
      unplanned change

### Completion State

- For each task in tasks.md Quick View:
    - If the checkbox is checked (`- [x]`), verify the task's files have
      corresponding commits
    - If the checkbox is unchecked (`- [ ]`), verify the task's files have NOT
      been fully modified
    - **HIGH** if a task is checked but its files show no git changes
    - **MEDIUM** if a task is unchecked but all its files have been modified

### Scope Creep Detection

- Collect all services from tasks.md `Service(s)` fields
- Collect all directories modified in git diff
- Map directories to services (top-level directory = service name)
- **HIGH** if a service appears in git changes but in no task's `Service(s)`
  field

### Branch Staleness

- Compare `spec.md` frontmatter `date` with the most recent commit date on the
  branch
- **MEDIUM** if >14 days have elapsed between spec date and latest commit (spec
  may be stale)

---

## Pass 8a: Inline Diagram Consistency (plan.md)

**Goal**: Validate inline sequence diagrams within Architecture Decision
sections of plan.md.

This pass runs during `/spec analyze` and during `/spec dialectic` (self-check).

### Inline Sequence Diagram Participants

- Extract all `participant` names from `sequenceDiagram` blocks within
  `### Decision N:` sections of plan.md
- Compare against service names in spec.md Service Impact table
- Exempt generic participants: `Client`, `User`, `Browser` (external actors)
- **HIGH** if a participant name does not match any service in the Service
  Impact table

### Decision Diagram Inventory Completeness

- Count all inline diagram headings matching `#### SEQ-\d{3}:` within
  `### Decision N:` sections of plan.md
- Count all rows in the Decision Diagram Inventory table in plan.md
- **MEDIUM** if heading count does not match inventory table row count

### Inline Diagram-to-Spec References

- Extract all `FR-NNN` and `AC-NNN` references from inline diagram headings
  (`#### SEQ-001: ... (FR-001, AC-001)`)
- Verify each referenced FR-NNN exists in spec.md
- Verify each referenced AC-NNN exists in spec.md
- **HIGH** if a diagram references a non-existent FR-NNN or AC-NNN

### Mermaid Syntax Validation (plan.md)

- For each fenced code block with `mermaid` language tag within Decision
  sections:
    - Verify the block contains at least one participant/node declaration
    - Verify the block contains at least one arrow (`->>`, `-->`, `->`)
    - **MEDIUM** if a mermaid block is empty or has no participants/arrows
      (likely a placeholder)

---

## Pass 8b: Cross-Cutting Diagram Consistency (synthesis.md)

**Goal**: Validate cross-cutting diagrams in synthesis.md against spec.md and
plan.md for accuracy and completeness.

This pass runs during `/spec analyze` (when synthesis.md exists) and during
`/spec synthesis` (self-check). **Skip this pass entirely if synthesis.md does
not exist** (it is optional for simple, single-service specs).

### Diagram Participants

- Extract all `participant` and node names from diagram blocks in synthesis.md
- Compare against service names in spec.md Service Impact table
- Exempt generic participants: `Client`, `User`, `Browser`
- **HIGH** if a participant name does not match any service in the Service
  Impact table

### Diagram Inventory Completeness

- Count all diagram headings matching `### (DFD|CMP|STD)-\d{3}:` in
  synthesis.md
- Count all rows in the Diagram Inventory table (excluding header and separator)
- **MEDIUM** if heading count does not match inventory table row count

### Diagram-to-Spec References

- Extract all `FR-NNN` and `AC-NNN` references from diagram headings
- Verify each referenced FR-NNN exists in spec.md
- Verify each referenced AC-NNN exists in spec.md
- **HIGH** if a diagram references a non-existent FR-NNN or AC-NNN

### Conditional Diagram Justification

- For each conditional section (Data Flow, Component, State):
    - Check if it contains a diagram heading (`### DFD-`, `### CMP-`,
      `### STD-`) OR "N/A -- " followed by a reason
    - **MEDIUM** if a conditional section is empty (no diagram and no N/A
      justification)

### Mermaid Syntax Validation (synthesis.md)

- For each fenced code block with `mermaid` language tag:
    - Verify the block contains at least one participant/node declaration
    - Verify the block contains at least one arrow (`->>`, `-->`, `->`)
    - **MEDIUM** if a mermaid block is empty or has no participants/arrows
      (likely a placeholder)

---

## Pass 9: Citations

**Goal**: Architecture Decisions with external claims have verifiable sources.

### External Claim Detection

- For each `### Decision N:` block in plan.md, extract Context + Decision +
  Alternatives + Rationale text
- Identify claims about external tool behavior, protocol semantics, library
  capabilities, or industry practices -- i.e., anything a developer cannot
  verify by reading the repo
- For each such claim:
    - **HIGH** if `**Sources**` field is missing or empty
    - **HIGH** if Sources contains only `[UNVERIFIED]` markers

### Industry Precedent URL Check

- For each bullet in `## Industry Precedent`:
    - **MEDIUM** if bullet has no markdown link `[text](url)`

### Summary

- Report: N decisions checked, N with sources, N [UNVERIFIED], N Industry
  Precedent items with URLs

---

## Output Format

```markdown
## Analysis Results: {TICKET}

| #   | Severity | Pass        | Finding                             | Location                  | Suggestion                    |
| --- | -------- | ----------- | ----------------------------------- | ------------------------- | ----------------------------- |
| 1   | CRITICAL | Coverage    | FR-002 has no implementing task     | spec.md:FR-002            | Add task to Workstream 2      |
| 2   | HIGH     | Ambiguity   | NFR-001 has no quantitative measure | spec.md:NFR-001           | Add latency/throughput target |
| 3   | MEDIUM   | Consistency | "py-worker" vs "pyworker"           | plan.md:L12, tasks.md:L45 | Standardize to "pyworker"     |

**Summary**: {N} CRITICAL, {N} HIGH, {N} MEDIUM, {N} LOW **Status**: {"BLOCKED
-- resolve CRITICAL findings" | "Ready"}
```
