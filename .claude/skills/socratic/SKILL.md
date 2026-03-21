---
name: socratic
description: >-
    Socratic requirements interviewer that discovers what you actually need before implementation begins. Use this skill BEFORE writing any code when the task is ambiguous, large, or involves architectural decisions. Triggers on "help me think through", "what should I build", "requirements for", "interview me", "let's figure out", "I want to build", "what do I need", or /socratic.
argument-hint: "[topic or feature description]"
disable-model-invocation: false
user-invocable: true
allowed-tools: Glob, Grep, Read, Write, AskUserQuestion
---

# Socratic Requirements Interviewer

This skill conducts a multi-turn Socratic interview to discover requirements before implementation.

## How It Works

1. Parse `$ARGUMENTS` as the topic or feature description. If empty, ask the user what they want to explore.
2. Read the interviewer instructions from `${CLAUDE_SKILL_DIR}/../../agents/socratic.md` and follow them exactly — that file is the single source of truth for all interviewer behavior (homework phase, Anchor-Fork-Lean-Ask questioning, depth progression, tradeoff surfacing, convergence signals).
3. Conduct the interview one question at a time via `AskUserQuestion`.
    - Do not ask interview questions in normal assistant text.
    - Use normal assistant text only for homework findings, progress framing, and the final contract summary.
    - If `AskUserQuestion` is unavailable, fall back to plain-text questions and say that you are falling back.
4. At convergence (Phase 4 — Contract), do both:
    - Render the full interview summary inline in the conversation
    - Save the summary to a file using the template at `${CLAUDE_SKILL_DIR}/templates/socratic-output.md`. Write the file to the working directory as `socratic-output-{slugified-topic}.md`.
