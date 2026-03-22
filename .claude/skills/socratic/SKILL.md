---
name: socratic
description: >-
    Socratic requirements interviewer that discovers what you actually need
    before implementation begins. Use this skill BEFORE writing any code when
    the task is ambiguous, large, or involves architectural decisions. Triggers
    on "help me think through", "what should I build", "requirements for",
    "interview me", "let's figure out", "I want to build", "what do I need", or
    /socratic.
argument-hint: "<TICKET> [description]"
disable-model-invocation: false
user-invocable: true
allowed-tools:
    Glob, Grep, Read, Write, AskUserQuestion, Bash, ExitPlanMode,
    mcp__code-review-graph__list_graph_stats_tool,
    mcp__code-review-graph__query_graph_tool,
    mcp__code-review-graph__find_large_functions_tool,
    mcp__code-review-graph__semantic_search_nodes_tool,
    mcp__code-review-graph__get_review_context_tool,
    mcp__code-review-graph__get_impact_radius_tool,
    mcp__code-review-graph__get_docs_section_tool,
    mcp__code-review-graph__build_or_update_graph_tool,
    mcp__code-review-graph__embed_graph_tool
hooks:
    PostToolUse:
        - matcher: "AskUserQuestion"
          hooks:
              - type: command
                command:
                    "uv run python
                    .claude/skills/socratic/scripts/socratic-transcript.py"
---

# Socratic Requirements Interviewer

This skill conducts a multi-turn Socratic interview to discover requirements
before implementation.

## Parsing

-   `$1` -> TICKET: first argument (e.g., `DESTINED-999`) -- required
-   `$ARGUMENTS` -> everything after TICKET is the DESCRIPTION

Examples:

-   `/socratic DESTINED-999 "graceful shutdown for workers"` ->
    `$1`=DESTINED-999, description from `$ARGUMENTS`
-   `/socratic DRAFT-0001 "new caching layer"` -> `$1`=DRAFT-0001, description
    from `$ARGUMENTS`

## Effective Configuration

!`bash ${CLAUDE_SKILL_DIR}/../spec/scripts/load-defaults.sh`

## Workflow

1. **If plan mode is active, call `ExitPlanMode` immediately.** The Socratic
   skill must write files to `sdd/`, which plan mode blocks. Exit plan mode
   before doing anything else.
2. Parse TICKET from `$1` and DESCRIPTION from remaining `$ARGUMENTS`. If
   DESCRIPTION is empty, ask the user what they want to explore.
3. Validate TICKET format (see Workspace Safety below). Generate slug from
   DESCRIPTION: lowercase, hyphenated, 3-5 words.
4. Create directories: `sdd/{TICKET}-{slug}/` and
   `sdd/{TICKET}-{slug}/socratic/`
5. Initialize `sdd/{TICKET}-{slug}/history.json` with the first event (see
   Logging below).
6. Read the interviewer instructions from
   `${CLAUDE_SKILL_DIR}/../../agents/socratic.md` and follow them exactly — that
   file is the single source of truth for all interviewer behavior (homework
   phase, Anchor-Fork-Lean-Ask questioning, depth progression, tradeoff
   surfacing, convergence signals).
7. **Do homework** per the agent instructions (three-tier strategy: graph
   self-heal → MCP tools → fallback reads). Record all findings for the
   "Homework Findings" section of the output.
8. Conduct the interview one question at a time via `AskUserQuestion`.
    - Do not ask interview questions in normal assistant text.
    - Use normal assistant text only for homework findings, progress framing,
      and the final contract summary.
    - If `AskUserQuestion` is unavailable, fall back to plain-text questions and
      say that you are falling back.
9. At convergence (Phase 4 — Contract), do all of:
    - **Interview Transcript**: **Call `Glob` for `interview-transcript.jsonl`
      in the working directory.** If the glob returns a match, **call `Read` on
      the file** and use the exact Q&A records (question, options, answer) to
      populate the Interview Transcript table in the output — this is the
      authoritative record. Only fall back to "(reconstructed from context)" if
      the glob returns no match.
    - Render the full interview summary inline in the conversation.
    - Save the summary using the template at
      `${CLAUDE_SKILL_DIR}/templates/socratic-output.md`. Write to
      `sdd/{TICKET}-{slug}/socratic/socratic-output.md`.
    - **Also write a structured JSON companion** using the schema at
      `${CLAUDE_SKILL_DIR}/templates/socratic-output.json`. Write to
      `sdd/{TICKET}-{slug}/socratic/socratic-output.json`.
    - **Call `Bash` with
      `mv interview-transcript.jsonl sdd/{TICKET}-{slug}/socratic/interview-transcript.jsonl`.**
      This step is mandatory — do not skip it. If the glob above returned no
      match, log a warning in history.json but do not fail.
    - Append convergence event to `sdd/{TICKET}-{slug}/history.json`.
10. **STOP after saving the output.** Do NOT proceed to implementation,
    planning, code writing, or launching Plan/Explore agents. Your final message
    should be the contract summary, a note that output was saved, and suggest
    running `/platonic {TICKET}` next.

## Workspace Safety

All operations enforce these invariants:

1. **Ticket format**: TICKET must match `[A-Z]+-\d+` (Jira) or `DRAFT-\d{4}`
   (exploratory). Reject anything else.
2. **Slug format**: Slug must match `[a-z0-9]+(-[a-z0-9]+){2,4}` (3-5 hyphenated
   segments, lowercase alphanumeric only).
3. **Path containment**: All file writes MUST target inside
   `sdd/{TICKET}-{slug}/`. Never write outside the SDD directory.

If any invariant fails, STOP and report the violation.

## Logging

Every mutating invocation appends a structured event to
`sdd/{TICKET}-{slug}/history.json`.

Event schema:

```json
{
    "timestamp": "2026-03-19T14:30:00Z",
    "command": "socratic",
    "ticket": "DESTINED-999",
    "phase": { "from": null, "to": "socratic" },
    "gates": {
        "checked": [],
        "passed": [],
        "failed": []
    },
    "findings": { "critical": 0, "high": 0, "medium": 0, "low": 0 },
    "files_written": [
        "socratic/socratic-output.md",
        "socratic/socratic-output.json"
    ],
    "conformance_tier": null
}
```

On first run: create `history.json` with the first event.
