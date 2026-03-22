---
name: socratic
description: >-
    Socratic requirements interviewer that discovers what you actually need before implementation begins. Use this skill BEFORE writing any code when the task is ambiguous, large, or involves architectural decisions. Triggers on "help me think through", "what should I build", "requirements for", "interview me", "let's figure out", "I want to build", "what do I need", or /socratic.
argument-hint: "[topic or feature description]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Glob, Grep, Read, Write, AskUserQuestion, mcp__plugin_code-review-graph_code-review-graph__list_graph_stats_tool, mcp__plugin_code-review-graph_code-review-graph__query_graph_tool, mcp__plugin_code-review-graph_code-review-graph__find_large_functions_tool, mcp__plugin_code-review-graph_code-review-graph__semantic_search_nodes_tool, mcp__plugin_code-review-graph_code-review-graph__get_review_context_tool, mcp__plugin_code-review-graph_code-review-graph__get_impact_radius_tool, mcp__plugin_code-review-graph_code-review-graph__get_docs_section_tool
hooks:
    PostToolUse:
        - matcher: "AskUserQuestion"
          hooks:
              - type: command
                command: "uv run python .claude/skills/socratic/scripts/socratic-transcript.py"
---

# Socratic Requirements Interviewer

This skill conducts a multi-turn Socratic interview to discover requirements before implementation.

## How It Works

1. Parse `$ARGUMENTS` as the topic or feature description. If empty, ask the user what they want to explore.
2. Read the interviewer instructions from `${CLAUDE_SKILL_DIR}/../../agents/socratic.md` and follow them exactly — that file is the single source of truth for all interviewer behavior (homework phase, Anchor-Fork-Lean-Ask questioning, depth progression, tradeoff surfacing, convergence signals).
3. **Prefer MCP tools for homework.** During the homework phase, use the code-review-graph MCP tools (`list_graph_stats_tool`, `query_graph_tool`, `semantic_search_nodes_tool`, `find_large_functions_tool`, `get_review_context_tool`, `get_impact_radius_tool`) before falling back to Glob/Grep/Read. These tools provide structural understanding of the codebase with far fewer tokens than manual file scanning.
    - Record your homework findings — they go into the "Homework Findings" section of the output. Include file paths, current behavior, and architectural context you discovered.
4. Conduct the interview one question at a time via `AskUserQuestion`.
    - Do not ask interview questions in normal assistant text.
    - Use normal assistant text only for homework findings, progress framing, and the final contract summary.
    - If `AskUserQuestion` is unavailable, fall back to plain-text questions and say that you are falling back.
5. At convergence (Phase 4 — Contract), do all of:
    - **Interview Transcript**: Check if `interview-transcript.jsonl` exists in the working directory. If it does, read it and use the exact Q&A records (question, options, answer) to populate the Interview Transcript table in the output — this is the authoritative record. Persist the JSONL file after incorporating it. If the file does not exist, reconstruct the transcript from conversation context and note "(reconstructed from context)" in the transcript section header.
    - Render the full interview summary inline in the conversation
    - Save the summary to a file using the template at `${CLAUDE_SKILL_DIR}/templates/socratic-output.md`. Write the file to the working directory as `socratic-output-{slugified-topic}.md`.
    - **Also write a structured JSON companion** using the schema at `${CLAUDE_SKILL_DIR}/templates/socratic-output.json`. Write it to the working directory as `socratic-output-{slugified-topic}.json`. Populate all fields from the same interview data used for the markdown file.
6. **STOP after saving the output.** Do NOT proceed to implementation, planning, code writing, or launching Plan/Explore agents. Your final message should be the contract summary and a note that the output file was saved.
