# SDD Workflow Visual Guide

The Spec-Design-Deliver (SDD) workflow turns a feature idea into a fully traceable, PR-sized task breakdown. It uses `/spec` sub-commands to move a specification through a gated state machine -- from socratic inquiry to implementation-ready tasks -- with conformance tiers (L1-L4) ensuring quality at each stage.

The philosophical arc: **socratic → platonic → aporia → dialectic → synthesis → praxis**

For authoritative references, see:

-   [`references/lifecycle-model.md`](references/lifecycle-model.md) for lifecycle ownership and transitions
-   [`SKILL.md`](SKILL.md) for command workflows, gates, and artifact generation

## Quick Start

```bash
# 1. (Optional) Deep discovery interview
/spec socratic FROSTY-147 "DB query optimization"

# 2. Scaffold the spec (the platonic ideal)
/spec platonic FROSTY-147 "DB query optimization"

# 3. Resolve ambiguities and explicitly mark the spec Clarified
/spec aporia FROSTY-147
/spec transition FROSTY-147 Clarified "All clarification markers resolved"

# 4. Generate implementation plan with inline architecture diagrams
/spec dialectic FROSTY-147

# 5. (Optional) Generate cross-cutting system-level diagrams
/spec synthesis FROSTY-147

# 6. Decompose into PR-sized tasks
/spec praxis FROSTY-147

# 7. Verify readiness and explicitly mark the spec Ready
/spec analyze FROSTY-147
/spec transition FROSTY-147 Ready "analyze reported 0 CRITICAL findings and L3+ readiness"

# 8. Export to harness
/spec export FROSTY-147
```

## Decision Guide

| I want to... | Use | Prerequisites | | ------------------------------------- | ------------------- | ---------------------------------------------------- | | Explore requirements before writing | `/spec socratic` | None | | Create a new spec from scratch | `/spec platonic` | None (`socratic-output.md` is optional) | | Resolve `[NEEDS CLARIFICATION]` items | `/spec aporia` | `spec.md` exists | | Explicitly change lifecycle status | `/spec transition` | `spec.md` exists and the transition guard passes | | Generate an implementation plan | `/spec dialectic` | Gate 1 + Gate 2 pass | | Generate cross-cutting diagrams | `/spec synthesis` | `plan.md` exists (optional stage) | | Break plan into PR-sized tasks | `/spec praxis` | Gate 3 + Gate 4 + Gate 5 pass | | Check cross-artifact consistency |
`/spec analyze` | `spec.md` exists (partial sets OK) | | See all specs and their status | `/spec status` | None | | Export tasks to harness JSON | `/spec export` | `tasks.md` exists | | Import harness progress back | `/spec import` | `features.json` / `progress.json` exists | | Detect drift between spec and code | `/spec reconcile` | `spec.md` + `plan.md` + `tasks.md` exist |

## Diagram 1a: Spec Authoring Sequence

Socratic, platonic, and aporia -- the authoring phase that produces `spec.md`.

```mermaid
sequenceDiagram
    participant U as User
    participant C as Claude (/spec)
    participant CB as Codebase
    participant A as Artifacts
    participant G as Gates

    opt socratic (pre-state, no status set)
        U->>C: /spec socratic TICKET "description"
        C->>CB: Explore ticket context, modules, patterns
        loop 5-8 Socratic Questions
            C->>U: Question with exploration-derived default
            U->>C: Answer (or "skip" / "done")
        end
        C->>A: Write socratic-output.md
        C->>A: Init history.json
        Note over A: No status set yet
    end

    U->>C: /spec platonic TICKET "description"
    C->>CB: Explore service impact, file paths, patterns

    alt socratic-output.md exists
        C->>A: Read socratic-output.md
        Note over C: Pre-fill from interview findings
    else No prior interview
        loop 2-3 Discovery Questions
            C->>U: Ambiguity question with default
            U->>C: Answer (or "skip")
        end
    end

    C->>A: Write spec.md (status: Draft)
    C->>A: Init/append history.json
    C->>G: Run L1 checks (Q-01, Q-02, Q-06, Q-10)
    Note over A: Status -> Draft

    U->>C: /spec aporia TICKET
    C->>A: Read spec.md
    C->>CB: Explore for context on markers
    loop Max 5 Clarification Questions
        C->>U: Prioritized question (scope > security > UX > tech)
        U->>C: Answer (or "done")
        C->>A: Update spec.md (phase: aporia)
    end
    C->>G: Verify Gate 1 (0 markers) + L1 checks
    C->>U: Recommend /spec transition Clarified
    Note over A: Phase -> aporia, status unchanged

    opt lifecycle transition
        U->>C: /spec transition TICKET Clarified "..."
        C->>A: Update spec.md (status: Clarified)
    end
```

## Diagram 1b: Dialectic-to-Praxis Sequence

Dialectic, synthesis, praxis, and analyze -- the design phase that produces implementation artifacts.

```mermaid
sequenceDiagram
    participant U as User
    participant C as Claude (/spec)
    participant CB as Codebase
    participant A as Artifacts
    participant G as Gates

    U->>C: /spec dialectic TICKET
    C->>G: Check Gate 1 (Clarification) + Gate 2 (Acceptance Criteria)

    alt Gates 1+2 pass
        C->>CB: Explore patterns, cross-service concerns
        C->>A: Read spec.md
        C->>A: Write plan.md (with inline SEQ diagrams per Decision)
        C->>A: Update spec.md frontmatter (phase: dialectic)
        Note over A: Conformance: L1 -> L2
    else Gates 1+2 fail
        C->>U: STOP -- list failures, suggest /spec aporia
    end

    opt synthesis (cross-cutting views, optional)
        U->>C: /spec synthesis TICKET
        C->>A: Read spec.md + plan.md
        C->>CB: Explore service names, APIs, DB patterns
        C->>A: Write synthesis.md (DFD/CMP/STD, cross-cutting only)
        C->>G: Run Q-32, Q-35
    end

    U->>C: /spec praxis TICKET
    C->>G: Check Gate 3 (Architecture) + Gate 4 (Traceability) + Gate 5 (Inline Diagram)

    alt Gates 3+4+5 pass
        C->>A: Read spec.md + plan.md (+ synthesis.md if exists)
        C->>CB: Glob for real file paths, test locations
        C->>A: Write tasks.md
        C->>G: Gate 6 (Coverage) -- advisory only
        Note over A: Conformance: L2 -> L3
    else Gates 3+4+5 fail
        C->>U: STOP -- report missing Decision/AC-ref/inline diagram
    end

    U->>C: /spec analyze TICKET
    C->>A: Read all artifacts (spec, plan, synthesis, tasks)
    C->>G: Run analysis passes (1-6, 8a, 8b, 9)
    C->>U: Findings table + conformance tier (L1/L2/L3/L4)
    C->>U: Recommend /spec transition Ready

    opt readiness approved
        U->>C: /spec transition TICKET Ready "..."
        C->>A: Update spec.md (status: Ready, phase unchanged)
    end
```

## Diagram 2: State Machine

Lifecycle states with guarded forward and backward transitions.

```mermaid
stateDiagram-v2
    [*] --> none : Start

    state "( none )" as none
    state "Draft" as draft
    state "Clarified" as clarified
    state "Ready" as ready
    state "In Progress" as inprog
    state "Done" as done

    none --> none : /spec socratic (no status change)
    none --> draft : /spec platonic

    draft --> clarified : /spec transition Clarified\n[after /spec aporia and L1 pass]

    clarified --> ready : /spec transition Ready\n[after /spec analyze and L3+]

    ready --> inprog : /spec transition "In Progress"\n[implementation has started]

    inprog --> done : /spec transition Done\n[Definition of Done met]

    note right of draft
        Backward transitions (reason required):
        Clarified -> Draft (requirements invalidated)
        Ready -> Clarified (design change)
        In Progress -> Ready (scope change)
        Done -> In Progress (follow-up work)
        Done -> Clarified (reopened spec)
    end note

    clarified --> draft : Requirements change\ninvalidates clarification
    ready --> clarified : Design change\ninvalidates plan
    inprog --> ready : Scope change\nrequires re-plan
    done --> inprog : Follow-up work\nreopens execution
    done --> clarified : Merged change\nrequires replanning
```

## Diagram 3: Gates and Conformance Tiers

How the 6 compliance gates map to conformance tiers and which workflow stages they block.

```mermaid
flowchart TD
    subgraph L1["L1: Minimum Viable"]
        Q01["Q-01: Mandatory sections filled"]
        Q02["Q-02: FR count >= 2"]
        Q06["Q-06: Markers <= 3"]
        Q10["Q-10: N/A justifications"]
    end

    subgraph L2["L2: Plan-Ready"]
        Q03["Q-03: AC count >= 2 (GWT)"]
        Q04["Q-04: SC count >= 2"]
        Q05["Q-05: EC count >= 2"]
        Q07["Q-07: No orphaned cross-refs"]
        Q08["Q-08: All AC in GWT format"]
        Q09["Q-09: SC has numbers"]
        Q11["Q-11: Tech Context populated"]
        Q25["Q-25: Glossary terms used"]
        Q24["Q-24: Inline SEQ diagram in plan.md"]
    end

    subgraph L3["L3: Implementation-Ready (19 checks)"]
        Q12["Q-12: Architecture Decision exists"]
        Q13["Q-13: Verification refs AC-NNN"]
        Q14["Q-14: Every AC in Verification Strategy"]
        Q15["Q-15: Workstreams match Decisions scope"]
        Q16["Q-16: Every FR in a task"]
        Q17["Q-17: Every AC in a task"]
        Q18["Q-18: Every Decision in a task"]
        Q19["Q-19: Coverage table complete"]
        Q20["Q-20: Quick View matches task cards"]
        Q21["Q-21: PR scope <= 3 files"]
        Q22["Q-22: <= 1 service per task"]
        Q23["Q-23: No unjustified L-size tasks"]
        Q26["Q-26: Before/After in code blocks"]
        Q32["Q-32: Mermaid fenced syntax"]
        Q33["Q-33: Diagrams ref FR/AC-NNN"]
        Q34["Q-34: Inventory matches headings"]
        Q35["Q-35: Conditional N/A justification"]
        Q36["Q-36: Sources (no UNVERIFIED)"]
    end

    subgraph L4["L4: Autonomous-Ready"]
        Q27["Q-27: Every task has smoke test"]
        Q28["Q-28: No L-size tasks"]
        Q29["Q-29: No cycles in DAG"]
        Q30["Q-30: DoD checklist complete"]
        Q31["Q-31: All file paths resolve"]
    end

    G1{{"Gate 1: Clarification"}}
    G2{{"Gate 2: Acceptance Criteria"}}
    G3{{"Gate 3: Architecture"}}
    G4{{"Gate 4: Traceability"}}
    G5{{"Gate 5: Inline Diagram"}}
    G6{{"Gate 6: Coverage (advisory)"}}

    L1 --> G1
    L1 --> G2
    G1 -->|blocks| dialectic["/spec dialectic"]
    G2 -->|blocks| dialectic

    L2 --> G3
    L2 --> G4
    L2 --> G5
    G3 -->|blocks| praxis["/spec praxis"]
    G4 -->|blocks| praxis
    G5 -->|blocks| praxis

    L3 --> G6
    G6 -.->|warns| post_praxis["Post-task generation"]

    L4 -.->|advisory| harness["Harness launch"]
```

## Diagram 4: Traceability Chain

How identifiers flow across artifacts from spec through to implementation.

```mermaid
flowchart LR
    subgraph spec["spec.md"]
        FR["FR-NNN\nFunctional Req"]
        AC["AC-NNN\nAcceptance Criteria"]
        SC["SC-NNN\nSuccess Criteria"]
        EC["EC-NNN\nEdge Cases"]
        NFR["NFR-NNN\nNon-Functional Req"]
    end

    subgraph plan["plan.md"]
        DEC["Decision N\nArchitecture Decision"]
        VER["Verification Strategy\nCovers: AC-NNN"]
        SRC["Sources\nExternal citations"]
        ISEQ["SEQ-NNN\nInline Sequence Diagrams"]
    end

    subgraph synthesis_doc["synthesis.md (optional)"]
        DFD["DFD-NNN\nData Flow"]
        CMP["CMP-NNN\nComponent"]
        STD["STD-NNN\nState"]
    end

    subgraph tasks["tasks.md"]
        TASK["Task TICKET-1A\nWhat to implement"]
        TRACE["Traceability\nFR + Decision refs"]
        ACCEPT["Acceptance\nAC-NNN items"]
        TDD["Tests (TDD)\nTest functions"]
    end

    subgraph impl["Implementation"]
        PR["Pull Request"]
        TESTS["Test Suite"]
        CODE["Source Code"]
    end

    FR -->|"referenced in"| DEC
    FR -->|"mapped to"| TASK
    AC -->|"covered by"| VER
    AC -->|"verified in"| ACCEPT
    EC -->|"maps to"| AC
    SC -->|"measured post-deploy"| impl
    NFR -->|"constrains"| DEC
    DEC -->|"visualized by"| ISEQ
    DEC -->|"implemented by"| TRACE
    ISEQ -->|"references"| FR
    DFD -->|"spans"| DEC
    TASK -->|"produces"| PR
    ACCEPT -->|"drives"| TESTS
    TDD -->|"validates"| CODE

    style spec fill:#e1f0ff,stroke:#4a90d9
    style plan fill:#fff3e0,stroke:#f5a623
    style synthesis_doc fill:#f3e5f5,stroke:#9c27b0
    style tasks fill:#e8f5e9,stroke:#4caf50
    style impl fill:#fce4ec,stroke:#e91e63
```

## Diagram 5: Implementation Bridge

How `/spec export` connects to the harness execution loop and `/spec import` reconciles.

```mermaid
sequenceDiagram
    participant U as User
    participant S as /spec
    participant A as Artifacts
    participant H as Hooks
    participant HA as Harness
    participant CB as Codebase

    Note over S,A: Spec authoring complete (tasks.md exists)

    U->>S: /spec export TICKET
    S->>A: Read tasks.md
    S->>A: Write features.json
    H->>A: Hook 1 (path guard) validates write path
    H->>A: Hook 3 (schema validator) validates features.json
    Note over A: features.json is the bridge artifact

    U->>U: Human review of features.json

    U->>HA: harness plan
    HA->>A: Read features.json
    H->>A: Hook 3 validates initializer output
    HA->>HA: Generate execution plan

    loop For each feature
        HA->>CB: harness run (implement feature)
        HA->>HA: Safety hook validates changes
        HA->>A: Update progress
    end

    U->>S: /spec import TICKET
    S->>A: Read progress.json / features.json
    S->>A: Update tasks.md checkboxes and status
    H->>A: Hook 1 (path guard) validates write
    H->>A: Hook 4 (status bar) shows progress

    U->>S: /spec reconcile TICKET
    S->>A: Read spec.md + plan.md + tasks.md
    S->>CB: git diff --name-only (implementation drift)
    S->>U: Findings table (drift, scope creep, staleness)
```

### Hook Firing Sequence

From [`hooks-skills-integration.md`](hooks-skills-integration.md) lines 89-101:

| Command | Hooks fired | | ------------------ | ----------------------------------------------------- | | `/spec platonic` | Hook 1 (path guard), Hook 2 (history), Hook 4 | | `/spec aporia` | Hook 1, Hook 2, Hook 4 | | `/spec dialectic` | Hook 1, Hook 2, Hook 4 | | `/spec synthesis` | Hook 1, Hook 2, Hook 4 | | `/spec praxis` | Hook 1, Hook 2, Hook 4 | | `/spec transition` | Hook 1, Hook 2, Hook 4 | | `/spec analyze` | (read-only, no hooks fire) | | `/spec export` | Hook 1, Hook 2, **Hook 3** (features.json validation) | | `/spec import` | Hook 1, Hook 2, Hook 4 | | `/spec reconcile` | (read-only, no hooks fire) |

## Artifact Inventory

| Artifact | Created by | Required? | Key contents | | -------------------- | ------------- | --------- | --------------------------------------------------------------- | | `socratic-output.md` | `socratic` | No | Q&A transcript, synthesized FR/AC/SC/EC/NFR drafts | | `spec.md` | `platonic` | Yes | Requirements, AC (GWT), SC, EC, NFRs, Service Impact | | `plan.md` | `dialectic` | Yes | Architecture Decisions + inline SEQ diagrams, Verification Strategy | | `synthesis.md` | `synthesis` | Optional | Cross-cutting diagrams (DFD/CMP/STD) for multi-service changes | | `tasks.md` | `praxis` | Yes | PR-sized task cards, dependency graph, coverage validation | | `features.json` | `export` | No | Harness-compatible task list (bridge artifact) | | `history.json` | First command | Yes | Structured
event log of all sub-command invocations |

All artifacts live in `specs/{TICKET}-{slug}/`.

## Cross-References

-   **Authoritative workflow**: [`skills/spec/SKILL.md`](../skills/spec/SKILL.md) -- state machine, gates, all sub-commands
-   **Quality checklist**: [`skills/spec/references/quality-checklist.md`](../skills/spec/references/quality-checklist.md) -- conformance tiers L1-L4 and check IDs Q-01 through Q-36
-   **Analysis rules**: [`skills/spec/references/analysis-rules.md`](../skills/spec/references/analysis-rules.md) -- 9 analysis passes (Passes 1-6, 7 reconciliation, 8a inline diagrams, 8b cross-cutting diagrams, 9 citations)
-   **Defaults**: [`skills/spec/references/defaults.yaml`](../skills/spec/references/defaults.yaml) -- tunables (overridden by `specs/.specrc.yaml`)
-   **Hooks integration**: [`docs/hooks-skills-integration.md`](hooks-skills-integration.md) -- hook firing sequence, spec-to-harness pipeline
