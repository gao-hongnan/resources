\*\*# Time-Bound Leases: A Unified Treatment of Crash Detection in Distributed
Systems

_A fault-tolerance mechanism for distributed job processing, grounded in 35
years of distributed systems research._

---

Every distributed systems tutorial tells you the same thing: add retries,
increase timeouts, be resilient.

This advice is backwards.

When a service is down, retrying makes things worse. You're piling up requests
behind a door that won't open. Meanwhile your threads are stuck waiting, your
connection pool is exhausted, and the cascade is spreading. And timeouts? A long
timeout means you wait forever for a response that'll never come. A short
timeout means you'll false-positive on any GC pause.

The counterintuitive fix: _stop trying sooner_. And more importantly, _know when
to give up_.

This is what leases do. A lease is a time-bound contract that says: "I'm working
on this. If you don't hear from me in 30 seconds, assume I'm dead and move on."
It's pessimistic by design. It assumes failure is the norm, not the exception.

Here's the insight that makes everything click:

$$\mathsf{crashed}(j) \triangleq \underbrace{\exists \mathcal{K}_S(j)}_{\text{evidence exists}} \land \underbrace{\neg \exists \mathcal{K}_L(j)}_{\text{heartbeat stopped}}$$

Evidence of work exists, but the heartbeat stopped. That's a crash. No
coordination needed. No consensus protocol. Just the passage of time.

---

## Intuition: The Library Book Analogy

Before diving into formal definitions, let's build intuition with a concrete
analogy that maps precisely to our distributed systems problem.

### The Setup: Borrowing Books from a Library

Imagine a library where patrons borrow books. The library needs to track:

1. **Who has which book** (accountability)
2. **Whether the borrower is still alive** (liveness)
3. **What to do if someone disappears with a book** (recovery)

```text
┌─────────────────────────────────────────────────────────────────────┐
│                    THE LIBRARY SYSTEM                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   BORROWER (Worker)          BOOK (Job)           LIBRARY (Redis)  │
│   ════════════════          ══════════           ═══════════════   │
│                                                                     │
│   You, a person who         A resource that      The coordinator   │
│   wants to read books       can only be held     that tracks who   │
│   and might get hit         by one person at     has what and      │
│   by a bus tomorrow         a time               detects deaths    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Normal Flow: The Weekly Check-In

```text
┌─────────────────────────────────────────────────────────────────────┐
│ NORMAL CHECKOUT (Healthy Processing)                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. You check out a book                                            │
│     → Library puts YOUR NAME on the "checked out" list              │
│     → Library starts a 30-day timer for your next check-in          │
│                                                                     │
│  2. Every week, you visit the library and say "I still have it!"   │
│     → This is the HEARTBEAT                                         │
│     → Timer resets to 30 days                                       │
│                                                                     │
│  3. When done reading, you return the book                          │
│     → Library removes your name from the list                       │
│     → Timer deleted                                                 │
│                                                                     │
│  Timeline:                                                          │
│  ─────────────────────────────────────────────────────────────────  │
│  Day 0        Day 7        Day 14       Day 21       Day 28        │
│    │            │            │            │            │            │
│    ▼            ▼            ▼            ▼            ▼            │
│  [Checkout]  [Check-in]  [Check-in]  [Check-in]  [Return book]     │
│              "Still      "Still      "Still       Done!            │
│              have it!"   have it!"   have it!"                     │
│                                                                     │
│  Timer:  30→   30→         30→         30→         [deleted]       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Mapping to our system:**

| Library Concept    | Distributed System Concept |
| ------------------ | -------------------------- |
| Book               | Job/Task to process        |
| Borrower           | Worker process             |
| "Checked out" list | Processing state in Redis  |
| Weekly check-in    | Heartbeat every 10 seconds |
| 30-day timer       | Lease TTL (30 seconds)     |
| Return book        | Mark job completed         |

### The Crash Scenario: Getting Hit by a Bus

Now, the interesting case—what happens when the borrower _dies_?

```text
┌─────────────────────────────────────────────────────────────────────┐
│ THE CRASH SCENARIO (Worker Dies)                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. You check out a book (Day 0)                                    │
│     → Your name goes on the list                                    │
│     → 30-day timer starts                                           │
│                                                                     │
│  2. You check in once (Day 7)                                       │
│     → Timer reset to 30 days                                        │
│                                                                     │
│  3. ☠️  YOU GET HIT BY A BUS (Day 12)                               │
│     → You stop visiting the library                                 │
│     → NO MORE CHECK-INS                                             │
│     → You can't tell anyone—you're dead!                            │
│                                                                     │
│  4. Days pass... (Day 12 → Day 37)                                  │
│     → No check-in at Day 14, 21, 28...                              │
│     → Timer keeps counting down: 25... 18... 11... 4... 0          │
│                                                                     │
│  5. Timer expires (Day 37, i.e., 30 days after last check-in)       │
│     → Library says: "This person hasn't checked in for 30 days"    │
│     → Conclusion: "They're probably DEAD, mark book as LOST"       │
│                                                                     │
│  Timeline:                                                          │
│  ─────────────────────────────────────────────────────────────────  │
│  Day 0     Day 7     Day 12        Day 37                          │
│    │         │         │             │                              │
│    ▼         ▼         ▼             ▼                              │
│  [Checkout] [Check-in]  ☠️          [Timer expires!]                │
│             Timer=30   CRASH!        DETECTED AS DEAD               │
│                        (silent)                                     │
│                                                                     │
│  Notice: 25 days passed between crash and detection!                │
│  This is unavoidable—we can't know they're dead until they         │
│  fail to check in.                                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**The key insight**: We can't know _immediately_ when someone dies. We can only
know when they've been _silent for too long_. This is the fundamental limitation
that makes perfect failure detection impossible—and why we use timeouts.

### The Two-Key Insight: Why We Need Both a Timer AND a Record

Here's where it gets subtle. A naive library system might work like this:

```text
┌─────────────────────────────────────────────────────────────────────┐
│ NAIVE APPROACH: Single "Checkout Card" with Expiry                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  The library has ONE card per book:                                 │
│                                                                     │
│    ┌─────────────────────────────┐                                  │
│    │ CHECKOUT CARD               │                                  │
│    │ Book: "War and Peace"       │                                  │
│    │ Borrower: Alice             │                                  │
│    │ Expires: Day 37             │  ← Single card with TTL         │
│    └─────────────────────────────┘                                  │
│                                                                     │
│  PROBLEM: When the card expires (Day 37), it VANISHES!              │
│                                                                     │
│    Day 36:  Card exists → "Alice has the book"                      │
│    Day 37:  Card GONE   → "???"                                     │
│                                                                     │
│  We know SOMETHING happened, but:                                   │
│    - Who had the book? (card is gone, no record!)                   │
│    - When did they check it out? (no record!)                       │
│    - Is this the 1st time this book got lost? The 5th? (no record!) │
│                                                                     │
│  We're BLIND. We detected death but lost all evidence.              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**The solution**: Separate the _liveness signal_ from the _evidence record_.

```text
┌─────────────────────────────────────────────────────────────────────┐
│ SMART APPROACH: Two Separate Records                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  KEY 1: HEARTBEAT TIMER (short-lived, 30 days)                      │
│  ═══════════════════════════════════════════════                    │
│  "Proof that borrower is ALIVE right now"                           │
│                                                                     │
│    ┌─────────────────────────────┐                                  │
│    │ LIVENESS PING               │                                  │
│    │ Borrower: Alice             │                                  │
│    │ Status: ALIVE               │  ← Expires in 30 days           │
│    │ Expires: Day 37             │    If this vanishes = DEAD      │
│    └─────────────────────────────┘                                  │
│                                                                     │
│  KEY 2: CHECKOUT RECORD (long-lived, 1 year)                        │
│  ═══════════════════════════════════════════════                    │
│  "Permanent record of WHO started WHAT and WHEN"                    │
│                                                                     │
│    ┌─────────────────────────────┐                                  │
│    │ CHECKOUT LOG                │                                  │
│    │ Book: "War and Peace"       │                                  │
│    │ Borrower: Alice             │                                  │
│    │ Checked out: Day 0          │  ← Survives for 1 year!         │
│    │ Borrower's address: 123 St  │    Evidence persists            │
│    └─────────────────────────────┘                                  │
│                                                                     │
│  NOW WHEN ALICE DIES:                                               │
│  ═══════════════════                                                │
│                                                                     │
│    Day 37: Liveness ping EXPIRES (key vanishes)                     │
│            Checkout record REMAINS                                  │
│                                                                     │
│    Library checks:                                                  │
│      ∃ Checkout record for "War and Peace"?  YES (Alice has it)    │
│      ∃ Liveness ping for Alice?              NO  (expired!)         │
│                                                                     │
│    Conclusion: Record exists BUT heartbeat stopped = CRASH!         │
│                                                                     │
│    We know:                                                         │
│      - WHO had it (Alice)                                           │
│      - WHAT they had (War and Peace)                                │
│      - WHEN they started (Day 0)                                    │
│      - WHERE to send the bill (123 St)                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**This is the core insight of the Two-Key Pattern**:

$$\mathsf{crashed}(j) \triangleq \underbrace{\exists \mathcal{K}_S(j)}_{\text{evidence exists}} \land \underbrace{\neg \exists \mathcal{K}_L(j)}_{\text{heartbeat stopped}}$$

The heartbeat tells us _if_ someone died. The evidence tells us _who_ and _what
they were doing_.

### Breaking the Crash Loop: The Quarantine System

One more scenario: what if a particular book is _cursed_?

```text
┌─────────────────────────────────────────────────────────────────────┐
│ THE POISON BOOK PROBLEM                                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Some books are cursed—anyone who reads them DIES.                  │
│                                                                     │
│  Without protection:                                                │
│                                                                     │
│    Alice checks out "Necronomicon"  →  Alice dies                   │
│    Library detects Alice's death    →  Book available again         │
│    Bob checks out "Necronomicon"    →  Bob dies                     │
│    Library detects Bob's death      →  Book available again         │
│    Carol checks out "Necronomicon"  →  Carol dies                   │
│    ...                                                              │
│    INFINITE DEATH LOOP! 💀💀💀                                       │
│                                                                     │
│  SOLUTION: Track crash counts per book                              │
│                                                                     │
│    ┌─────────────────────────────────────────────────┐              │
│    │ CRASH COUNTER: "Necronomicon"                   │              │
│    │ Deaths caused: 1 (Alice)     ← After Alice     │              │
│    │ Deaths caused: 2 (Bob)       ← After Bob       │              │
│    │ Deaths caused: 3 (Carol)     ← THRESHOLD!      │              │
│    │ STATUS: 🚫 QUARANTINED                          │              │
│    └─────────────────────────────────────────────────┘              │
│                                                                     │
│    After 3 deaths, the book is QUARANTINED:                         │
│      - No one can check it out                                      │
│      - Human librarian must investigate                             │
│      - Loop is BROKEN                                               │
│                                                                     │
│  Dave tries to check out "Necronomicon":                            │
│    Library: "Is this book quarantined?" → YES → REJECT              │
│    Dave is saved! The loop is broken.                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

With this mental model in place, the formal definitions that follow should feel
natural. We're simply making these intuitions mathematically precise.

---

## Notation Reference

This document uses mathematical typography following semantic conventions. Each
font choice conveys the nature of the mathematical object.

| Symbol                                                   | Font            | Meaning                                 |
| -------------------------------------------------------- | --------------- | --------------------------------------- |
| $\mathcal{P}$                                            | Calligraphic    | Set of processes (workers)              |
| $\mathcal{J}$                                            | Calligraphic    | Set of jobs                             |
| $\mathcal{C}$                                            | Calligraphic    | Set of communication channels           |
| $\mathcal{S}$                                            | Calligraphic    | Shared state store                      |
| $\mathcal{L}$                                            | Calligraphic    | Lease (as a tuple)                      |
| $\mathcal{K}_L$, $\mathcal{K}_S$                         | Calligraphic    | Liveness key, State key                 |
| $\mathscr{D}$                                            | Script          | Failure detector oracle                 |
| $\mathsf{valid}$, $\mathsf{crashed}$                     | Sans-serif      | System predicates                       |
| $\mathsf{acquire}$, $\mathsf{renew}$, $\mathsf{release}$ | Sans-serif      | Protocol operations                     |
| $\mathbb{R}^+$                                           | Blackboard bold | Positive real numbers                   |
| $\mathbb{N}$                                             | Blackboard bold | Natural numbers                         |
| $\Diamond$                                               | Modal operator  | "Eventually" (temporal logic)           |
| $\Box$                                                   | Modal operator  | "Always" (temporal logic)               |
| $T_{\text{short}}$, $T_{\text{long}}$                    | Roman subscript | TTL parameters                          |
| $\delta$, $\phi$, $\rho$, $\varepsilon$                  | Greek           | Bounds on delay, step time, drift, skew |

---

## Part I: Pattern Definition and Guarantees

### The Time-Bound Lease Pattern

> **Definition (Time-Bound Lease Pattern).** A _fault-tolerance mechanism_ for
> distributed job processing that implements an **Eventually Perfect failure
> detector** ($\Diamond \mathcal{P}$) by decomposing a lease $\mathcal{L}$ into
> two keys with distinct time-to-live (TTL) values:
>
> 1. A **liveness key** $\mathcal{K}_L$ with short TTL ($T_{\text{short}}$)
>    serving as a heartbeat
> 2. A **state key** $\mathcal{K}_S$ with long TTL ($T_{\text{long}}$)
>    preserving forensic evidence
>
> Crash detection is determined by the predicate:
>
> $$\mathsf{crashed}(j) \triangleq \exists \mathcal{K}_S(j) \land \neg \exists \mathcal{K}_L(j)$$
>
> _Evidence exists, but heartbeat stopped._

### Problem Addressed

**Failure detection in asynchronous distributed systems**, where the FLP
impossibility result proves that distinguishing a crashed process from a slow
one is fundamentally impossible without timing assumptions.

### Formal Guarantees

The Time-Bound Lease Pattern provides four correctness properties:

| Property            | Category           | Formal Statement                                                    |
| ------------------- | ------------------ | ------------------------------------------------------------------- |
| **Safety**          | Mutual Exclusion   | At most one process holds a valid lease on any job at any time      |
| **Liveness**        | Eventual Detection | Every crashed process is eventually suspected (completeness)        |
| **Bounded Latency** | Timeliness         | Crash detection occurs within bounded time                          |
| **Bounded Impact**  | Fault Containment  | Any single job causes at most $N_{\text{threshold}}$ worker crashes |

**Formal specifications:**

**Property 1 (Safety).** _Mutual exclusion_—at most one worker processes each
job:

$$\forall j \in \mathcal{J}, \; \forall t \in \mathbb{R}^+ : \left| \left\{ p \in \mathcal{P} : \mathsf{processing}(p, j, t) \right\} \right| \leq 1$$

**Property 2 (Liveness).** _Eventual crash detection_—every crash is eventually
detected:

$$\forall p \in \mathcal{P}, \; \forall j \in \mathcal{J} : \mathsf{crash}(p) \land \mathsf{processing}(p, j) \implies \Diamond \, \mathsf{detected}(j)$$

**Property 3 (Bounded Latency).** _Detection occurs within a bounded window_:

$$t_{\text{detect}} - t_{\text{crash}} \leq T_{\text{short}} + T_{\text{scan}}$$

**Property 4 (Bounded Impact).** _Poison jobs cause bounded failures_:

$$\forall j \in \mathcal{J} : \mathsf{attempts}(j) \leq N_{\text{threshold}}$$

### CAP Theorem Position

The pattern chooses **AP** (Availability + Partition tolerance) with eventual
consistency:

- **Availability**: Jobs keep processing even when some workers crash
- **Partition Tolerance**: Network partitions handled via lease expiry
- **Eventual Consistency**: Crash detection may have delay
  $\leq T_{\text{short}}$

### Fault Tolerance Classification

> **Definition (Fault Tolerance).** A system $\Sigma$ is _fault tolerant_ for a
> class of faults $\mathcal{F}$ if it maintains correctness despite the
> occurrence of faults $f \in \mathcal{F}$.

**What faults does this pattern tolerate?**

| Fault Type          | Tolerated? | Rationale                                                                                   |
| ------------------- | ---------- | ------------------------------------------------------------------------------------------- |
| **Crash fault**     | ✓          | Core design goal—worker halts permanently                                                   |
| **Omission fault**  | ✓          | Heartbeat timeout handles missed messages                                                   |
| **Timing fault**    | Partial    | Bounded clock skew assumed ($\varepsilon < T_{\text{short}} - \Delta t_{\text{heartbeat}}$) |
| **Byzantine fault** | ✗          | Would require BFT protocols (PBFT, etc.)                                                    |

The pattern is specifically designed for **crash-stop fault tolerance**—the most
common failure mode in distributed job processing where workers terminate
unexpectedly (OOM, segfaults, container eviction).

---

## Part II: Theoretical Foundation

### The System Model

> **Definition 1 (Distributed System).** A distributed system $\Sigma$ consists
> of:
>
> - A finite set of **processes** $\mathcal{P} = \{p_1, p_2, \ldots, p_n\}$
> - A set of **communication channels** >
>   $\mathcal{C} \subseteq \mathcal{P} \times \mathcal{P}$
> - A **shared state store** $\mathcal{S}$ (in practice, Redis)

Each process $p_i \in \mathcal{P}$ has:

- A **local clock** $\tau_i : \mathbb{R}^+ \to \mathbb{R}^+$ that may drift
  from real time $t$
- A **process state**
  $\sigma_i \in \{\mathsf{running}, \mathsf{crashed}, \mathsf{unknown}\}$

> **Definition 2 (Crash-Stop Failure Model).** We assume processes fail
> according to the _crash-stop_ model:
>
> 1. A process may halt at any time (no Byzantine failures)
> 2. A crashed process does not recover during the detection window
> 3. Crashes are _permanent_ within the detection epoch
>
> Formally, for process $p$ crashing at time $t_c$:
>
> $$\mathsf{crash}(p, t_c) \implies \forall t \geq t_c : \sigma_p(t) = \mathsf{crashed}$$

This model is weaker than crash-recovery but sufficient for job processing where
we want to reassign work.

### Why Perfect Detection Is Impossible

In 1985, Fischer, Lynch, and Paterson proved the **FLP Impossibility Result**:

> **Theorem (FLP, 1985).** _No deterministic algorithm can solve consensus in an
> asynchronous system if even one process may fail._

The critical insight: in a purely _asynchronous_ system—one with no timing
bounds—you cannot distinguish a crashed process from a slow one:

$$\forall T \in \mathbb{R}^+, \; \exists \text{ execution } E : p \text{ is alive but response time } > T$$

$$\implies p \text{ is indistinguishable from } \mathsf{crashed}$$

Concretely:

- Worker #7 hasn't responded in 30 seconds
- Is it **dead**? Or just **slow** (GC pause, network congestion, CPU
  throttling)?
- In an asynchronous model, _you literally cannot know_

This isn't a "we haven't figured it out yet" situation. It's **mathematically
proven impossible**.

### Failure Detectors: A Theoretical Framework

In 1996, Chandra and Toueg introduced **unreliable failure detectors** as a way
to circumvent FLP.

> **Definition 3 (Failure Detector).** A failure detector $\mathscr{D}$ is a
> distributed oracle that provides each process $p \in \mathcal{P}$ with a set
> $\mathsf{suspected}_p(t) \subseteq \mathcal{P}$ of processes it suspects to
> have crashed at time $t$.

Failure detectors are classified by two properties:

| Property         | Definition                                                             |
| ---------------- | ---------------------------------------------------------------------- |
| **Completeness** | Every crashed process is eventually suspected by every correct process |
| **Accuracy**     | Constraints on false suspicions (suspecting correct processes)         |

The key failure detector classes are:

| Class              | Symbol                 | Completeness | Accuracy                                             |
| ------------------ | ---------------------- | ------------ | ---------------------------------------------------- |
| Perfect            | $\mathcal{P}$          | Strong       | Strong (no false suspicions ever)                    |
| Eventually Perfect | $\Diamond \mathcal{P}$ | Strong       | Eventually strong (false suspicions stop eventually) |
| Strong             | $\mathcal{S}$          | Strong       | Weak (some correct process is never suspected)       |
| Eventually Strong  | $\Diamond \mathcal{S}$ | Strong       | Eventually weak                                      |

> **Theorem (Chandra-Toueg, 1996).** $\Diamond \mathcal{S}$ is the _weakest_
> failure detector class sufficient to solve consensus.

**Our lease-based approach implements an Eventually Perfect
($\Diamond \mathcal{P}$) failure detector**: after the lease timeout, crashed
processes are always suspected (completeness), and given stable network
conditions, we stop suspecting alive processes (eventual accuracy).

### Why Leases Instead of Consensus?

A natural question: why not use a consensus protocol like Paxos or Raft for
crash detection?

| Approach   | Complexity         | Latency            | Fault Model | Fit for Job Processing  |
| ---------- | ------------------ | ------------------ | ----------- | ----------------------- |
| **Leases** | $\mathcal{O}(1)$   | $T_{\text{short}}$ | Crash       | ✓ Ideal—single Redis op |
| **Paxos**  | $\mathcal{O}(n)$   | 2 RTT              | Crash       | ✗ Overkill              |
| **Raft**   | $\mathcal{O}(n)$   | 1-2 RTT            | Crash       | ✗ Overkill              |
| **PBFT**   | $\mathcal{O}(n^2)$ | 3 RTT              | Byzantine   | ✗ Wrong model           |

**Key insight**: Crash detection $\neq$ consensus. We need only an
$\Diamond \mathcal{P}$ failure detector, not agreement among replicas. Consensus
protocols solve a harder problem—agreeing on a value across nodes—but we simply
need to detect _absence of liveness signals_. Leases achieve this with
$\mathcal{O}(1)$ operations (a single Redis `EXPIRE`), no leader election, and
no quorum round-trips.

### The Timing Assumption: Partial Synchrony

Since perfect failure detection is impossible in asynchronous systems, we
introduce a **partial synchrony** assumption:

> **Definition 4 (Partial Synchrony).** There exists an unknown _Global
> Stabilization Time_ (GST) after which:
>
> - Message delays are bounded by $\delta$
> - Process step times are bounded by $\phi$
> - Clock drift is bounded by $\rho$
>
> Formally:
>
> $$\exists \, \text{GST} \in \mathbb{R}^+ : \forall t \geq \text{GST}, \; \forall p, q \in \mathcal{P} :$$
>
> $$\text{delay}(p \to q, t) \leq \delta \;\land\; \text{step\_time}(p, t) \leq \phi \;\land\; |\tau_p(t) - t| \leq \rho \cdot t$$

This is formalized in Dwork, Lynch, and Stockmeyer (1988)—the theoretical
foundation for practical consensus protocols like Paxos and Raft.

In plain English: _we agree that if something doesn't respond within $T$
seconds, we'll treat it as dead—even if it might just be slow._

This is our "cheat." And it works remarkably well in practice.

---

## Part III: The Lease Abstraction

### Formal Definition of a Lease

In 1989, Gray and Cheriton at Stanford published the foundational paper on
leases for distributed cache consistency. Let's formalize their contribution:

> **Definition 5 (Lease).** A lease $\mathcal{L}$ is a tuple
> $(\mathsf{holder}, \mathsf{resource}, \mathsf{expiry})$ where:
>
> - $\mathsf{holder} \in \mathcal{P}$ is the process holding the lease
> - $\mathsf{resource} \in \mathcal{J}$ is the protected resource (in our
>   case, a job)
> - $\mathsf{expiry} \in \mathbb{R}^+$ is the wall-clock time when the lease
>   expires
>
> A lease satisfies the validity predicate:
>
> $$\mathsf{valid}(\mathcal{L}, t) \triangleq (t < \mathcal{L}.\mathsf{expiry}) \land \neg \mathsf{crashed}(\mathcal{L}.\mathsf{holder})$$

> **Definition 6 (Lease Protocol).** The lease protocol $\Pi_{\mathcal{L}}$
> consists of three operations:

| Operation                       | Precondition                                                                                                   | Effect                                                            |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| $\mathsf{acquire}(p, r)$        | $\neg \exists \mathcal{L} : \mathsf{valid}(\mathcal{L}, \mathsf{now}) \land \mathcal{L}.\mathsf{resource} = r$ | Creates $\mathcal{L} = (p, r, \mathsf{now} + T_{\text{ttl}})$     |
| $\mathsf{renew}(\mathcal{L})$   | $\mathsf{valid}(\mathcal{L}, \mathsf{now}) \land \mathsf{caller} = \mathcal{L}.\mathsf{holder}$                | $\mathcal{L}.\mathsf{expiry} \gets \mathsf{now} + T_{\text{ttl}}$ |
| $\mathsf{release}(\mathcal{L})$ | $\mathsf{caller} = \mathcal{L}.\mathsf{holder}$                                                                | Deletes $\mathcal{L}$                                             |

The key invariant (informally, the _parking meter analogy_): _if you don't feed
the meter, the system can safely assume you're gone._

### System-Design Principles Addressed by Leases

#### Fault Tolerance via Time Bounds

**Principle:** _Use bounded time to limit the impact of failures._

Traditional distributed locking requires explicit release or failure detection.
Leases sidestep this by making **time the ultimate arbiter**: if a client fails,
crashes, or is partitioned, its lease simply expires. The server regains control
without needing to detect or handle the failure explicitly.

| Failure Scenario  | Lease Behavior                                       |
| ----------------- | ---------------------------------------------------- |
| Client crash      | Lease expires; server reclaims resource              |
| Network partition | Lease expires on both sides; safe recovery           |
| Server crash      | Client lease expires; client retries with new server |
| Clock skew        | Managed via conservative lease durations             |

**Net effect:** Failures are **bounded in time**, not unbounded in scope.

#### Automatic Recovery Without Coordination

**Principle:** _Design systems that recover automatically without explicit
coordination protocols._

Unlike distributed consensus or two-phase commit, lease expiration requires no
message exchange for recovery. When a lease expires:

1. The **client** knows it can no longer rely on cached state
2. The **server** knows it can grant the lease to someone else

This **unilateral recovery** property makes leases particularly valuable in
systems where network partitions are common or where minimizing coordination
overhead is critical.

**Net effect:** Recovery is **implicit and automatic**, driven by the passage of
time.

### The Safety-Liveness Trade-off

Leases inherently trade off two desirable properties:

> **Definition 7 (Detection Latency).** The time between a crash occurring and
> being detected:
>
> $$\mathsf{latency}_{\text{detection}} = T_{\text{ttl}} - (\mathsf{now} - t_{\text{last\_renewal}})$$
>
> - **Worst case**: $T_{\text{ttl}}$ (crash immediately after renewal)
> - **Best case**: $0$ (crash immediately before expiry)
> - **Expected**: $T_{\text{ttl}} / 2$

| $T_{\text{ttl}}$ Too Short                      | $T_{\text{ttl}}$ Too Long      |
| ----------------------------------------------- | ------------------------------ |
| $\uparrow$ False positives (slow $\neq$ dead)   | $\uparrow$ Detection latency   |
| $\uparrow$ Wasted work (unnecessary retries)    | $\uparrow$ Job starvation time |
| $\uparrow$ Network overhead (frequent renewals) | $\uparrow$ Resource lock-up    |

This is a manifestation of the fundamental **accuracy vs. completeness**
trade-off in failure detectors.

### Comparison with Alternatives

| Mechanism          | Fault Tolerance        | Complexity | Coordination Required |
| ------------------ | ---------------------- | ---------- | --------------------- |
| **Leases**         | Automatic (time-bound) | Low        | Minimal (renewal)     |
| **Heartbeats**     | Explicit detection     | Medium     | Continuous            |
| **2PC/3PC**        | Blocking possible      | High       | Heavy                 |
| **Paxos/Raft**     | Consensus-based        | High       | Quorum                |
| **Infinite locks** | Manual release         | Low        | Explicit release      |

Leases occupy a sweet spot: **simpler than consensus, safer than infinite locks,
more efficient than continuous heartbeats**.

---

## Part IV: The Two-Key Pattern

> _Recall from our library analogy: the naive approach uses a single checkout
> card that vanishes when it expires, leaving us blind to what happened. Our
> solution separates the "liveness ping" (short-lived timer) from the "checkout
> log" (long-lived evidence)._

### The Problem with Naive Leases

A simple lease approach uses one key:

```text
lease:{job_id} = worker_id, TTL=30s
```

When the lease expires, the key vanishes. Simple, right?

**Problem**: This violates the _forensic property_ we need. When the lease
expires:

- $\nexists$ record of which worker held the job
- $\nexists$ record of when processing started
- $\nexists$ record of crash history

We're flying blind. We've detected _that_ something died, but not _what_.

### Our Solution: Separating Liveness from Evidence

> **Definition 8 (Two-Key Lease Pattern).** We decompose the lease $\mathcal{L}$
> into two keys with distinct TTLs:

| Key              | Symbol          | Purpose             | TTL                      | Formal Role            |
| ---------------- | --------------- | ------------------- | ------------------------ | ---------------------- |
| **Liveness Key** | $\mathcal{K}_L$ | Heartbeat signal    | $T_{\text{short}}$ (30s) | Failure detector probe |
| **State Key**    | $\mathcal{K}_S$ | Processing metadata | $T_{\text{long}}$ (1h)   | Forensic evidence      |

> **Definition 9 (Crash Predicate).** A job $j \in \mathcal{J}$ is in crashed
> state if and only if:
>
> $$\mathsf{crashed}(j) \triangleq \exists \mathcal{K}_S(j) \land \neg \exists \mathcal{K}_L(j)$$

In words: _evidence exists, but heartbeat stopped_.

This is the **forensic insight**: the heartbeat tells us _if_ someone died, the
evidence tells us _who_ and _what they were doing_.

### Visual: The Two-Key Timeline

```text
TIME ────────────────────────────────────────────────────────────────────►

         t₀              t₁              t₂           t_crash        t_detect
         │               │               │               │               │
         │               │               │               │               │
         ▼               ▼               ▼               ▼               ▼

    [ACQUIRE]       [HEARTBEAT]     [HEARTBEAT]      [CRASH]       [DETECTED]
         │               │               │               │               │
         │               │               │               │               │
         │               │               │               │               │
 K_L:    ████████████████████████████████████████░░░░░░░░│               │
         │  TTL=30s      │  TTL=30s      │  TTL=30s      │    EXPIRED    │
         │  (reset)      │  (reset)      │  (reset)      │               │
         │               │               │               │               │
         │               │               │               │               │
 K_S:    ████████████████████████████████████████████████████████████████████
         │                               TTL=3600s (1 hour)              │
         │               │               │               │               │
         │               │               │               │               │
         └───────────────┴───────────────┴───────────────┴───────────────┘

At t_detect:
  ∃ K_S? YES (evidence exists)
  ∃ K_L? NO  (expired 30s after crash)
  ∴ crashed(j) = TRUE

We know WHO (worker_id in K_S), WHAT (job_id), WHEN (started_at).
```

### Information-Theoretic Justification

Why two keys instead of one with embedded metadata?

> **Lemma 1 (Atomic Expiration).** In Redis, key expiration is atomic but hash
> field expiration is not supported (until Redis 7.4 with HEXPIRE).

Therefore:

- A single hash key with TTL loses _all_ fields on expiry
- Two separate keys allow _independent_ expiration semantics

> **Corollary (Minimality).** The two-key pattern is the _minimal_ design that
> provides both:
>
> 1. Automatic liveness timeout (via $\mathcal{K}_L$ expiry)
> 2. Persistent forensic evidence (via $\mathcal{K}_S$ longer TTL)

---

## Part V: Implementation

Let's trace through the protocol, mapping formal definitions to code. The
implementation uses async Python with Redis, but the patterns are
language-agnostic.

### Lua Scripts for Atomicity

Redis operations must be atomic to prevent race conditions. We use Lua scripts:

```lua
-- Conditional release: only delete if holder matches
local key = KEYS[1]
local expected_holder = ARGV[1]
local current_holder = redis.call('GET', key)
if current_holder == expected_holder then
    redis.call('DEL', key)
    return 1
else
    return 0
end
```

```lua
-- Conditional renew: only extend TTL if holder matches
local key = KEYS[1]
local expected_holder = ARGV[1]
local ttl = tonumber(ARGV[2])
local current_holder = redis.call('GET', key)
if current_holder == expected_holder then
    redis.call('EXPIRE', key, ttl)
    return 1
else
    return 0
end
```

### Operation 1: Acquire Lease

```python
async def acquire_lease(
    redis: Redis,
    job_id: str,
    worker_id: str,
    lease_ttl: int = 30,
    state_ttl: int = 3600,
) -> bool:
    """
    Implements: acquire(p, r) from Definition 6
    Creates: K_L (liveness key) and K_S (state key) from Definition 8
    """
    lease_key = f"lease:{job_id}"      # K_L
    state_key = f"processing:{job_id}"  # K_S

    # K_L: Liveness signal with T_short (SET NX EX for atomicity)
    acquired = await redis.set(lease_key, worker_id, nx=True, ex=lease_ttl)

    if not acquired:
        return False  # Lease already held by another worker

    # K_S: Forensic evidence with T_long
    await redis.hset(state_key, mapping={
        "job_id": job_id,
        "worker_id": worker_id,
        "started_at": datetime.now(UTC).isoformat(),
        "hostname": socket.gethostname(),
    })
    await redis.expire(state_key, state_ttl)

    return True
```

**Formal mapping:**

- $\mathcal{L} = (\mathsf{worker\_id}, \mathsf{job\_id}, \mathsf{now} + 30\text{s})$
- $\mathcal{K}_S$ stores the forensic tuple:
  $(\mathsf{holder}, \mathsf{resource}, \mathsf{start\_time}, \mathsf{location})$

### Operation 2: Renew Lease (Heartbeat)

```python
async def renew_lease(
    redis: Redis,
    job_id: str,
    worker_id: str,
    lease_ttl: int = 30,
) -> bool:
    """
    Implements: renew(L) from Definition 6
    Returns: valid(L, now) — whether the lease was successfully renewed

    CRITICAL: Caller MUST check return value and abort if False!
    """
    lease_key = f"lease:{job_id}"

    # Use Lua script for atomic holder check + TTL extension
    result = await redis.evalsha(
        renew_script_sha,
        1,              # number of keys
        lease_key,      # KEYS[1]
        worker_id,      # ARGV[1]
        str(lease_ttl), # ARGV[2]
    )

    return result == 1  # True ⟺ valid(L, now)
```

**The heartbeat contract:**

$$\forall p \in \mathcal{P} \text{ processing } j \in \mathcal{J} :$$
$$p \text{ must call } \mathsf{renew}(j) \text{ every } \Delta t \text{ where } \Delta t < T_{\text{short}}$$

$$\mathsf{renew}(j) = \mathsf{false} \implies p \text{ has lost lease} \implies p \text{ must abort immediately}$$

This is the **self-invalidation property**: a worker can detect its own lease
loss.

### Operation 3: Release Lease

```python
async def release_lease(
    redis: Redis,
    job_id: str,
    worker_id: str,
) -> bool:
    """
    Implements: release(L) from Definition 6
    Atomically removes all keys associated with the job
    """
    lease_key = f"lease:{job_id}"
    state_key = f"processing:{job_id}"
    crash_count_key = f"crash_count:{job_id}"

    # Release lease atomically (only if we still hold it)
    released = await redis.evalsha(
        release_script_sha,
        1,
        lease_key,
        worker_id,
    )

    if released:
        # Clean up state and crash count on success
        await redis.delete(state_key, crash_count_key)

    return released == 1
```

### Operation 4: Crash Detection

```python
async def detect_crashes(redis: Redis) -> list[dict]:
    """
    Implements the crash predicate from Definition 9:
        crashed(j) ≝ ∃K_S(j) ∧ ¬∃K_L(j)
    """
    crashed_jobs = []

    # Scan for all state keys (evidence of in-progress jobs)
    async for state_key in redis.scan_iter("processing:*"):
        job_id = state_key.split(":")[1]
        lease_key = f"lease:{job_id}"

        # Evaluate: ∃K_S(j) ∧ ¬∃K_L(j)
        lease_exists = await redis.exists(lease_key)

        if not lease_exists:  # K_S exists (we're iterating it), K_L doesn't
            # CRASHED!
            state = await redis.hgetall(state_key)
            crash_info = await handle_crashed_job(redis, job_id, state)
            crashed_jobs.append(crash_info)

    return crashed_jobs
```

**The detection predicate in action:**
$\exists \mathcal{K}_S(j) \land \neg \exists \mathcal{K}_L(j) \implies \mathsf{CRASHED}$

---

## Part VI: The Quarantine Pattern

> _Recall the "cursed book" from our library analogy: some books kill every
> reader. Without protection, we'd have an infinite death loop. The solution is
> to track deaths per book and quarantine books that exceed a threshold._

### The Poison Pill Problem

Some jobs are _poison pills_—they deterministically crash any worker that
processes them. This creates a **livelock**:

$$\exists j \in \mathcal{J} : \forall p \in \mathcal{P}, \; \mathsf{process}(p, j) \implies \mathsf{crash}(p)$$

$$\implies \text{infinite crash-detect-retry cycles}$$

This is a form of **cascading failure** documented in Google's SRE book.

### Formal Solution: Bounded Retry with Quarantine

> **Definition 10 (Crash Counter).** For each job $j \in \mathcal{J}$, maintain:
>
> $$\mathsf{crash\_count} : \mathcal{J} \to \mathbb{N}, \quad \text{initialized to } 0$$

> **Definition 11 (Quarantine Predicate).** A job is quarantined when:
>
> $$\mathsf{quarantined}(j) \triangleq \mathsf{crash\_count}(j) \geq N_{\text{threshold}}$$

**Implementation:**

```python
async def handle_crashed_job(
    redis: Redis,
    job_id: str,
    state: dict,
    threshold: int = 3,
) -> dict:
    """
    Implements: Bounded retry with quarantine (Definitions 10-11)
    Invariant: crash_count monotonically increases until reset
    """
    crash_count_key = f"crash_count:{job_id}"
    state_key = f"processing:{job_id}"

    # Atomic increment
    crash_count = await redis.incr(crash_count_key)
    await redis.expire(crash_count_key, 86400)  # 24h TTL for counter

    # Clean up state key (evidence consumed)
    await redis.delete(state_key)

    exceeded_threshold = crash_count >= threshold

    if exceeded_threshold:
        logger.warning(f"Job {job_id} QUARANTINED after {crash_count} crashes")

    return {
        "job_id": job_id,
        "crash_count": crash_count,
        "quarantined": exceeded_threshold,
        "worker_id": state.get("worker_id"),
        "started_at": state.get("started_at"),
    }
```

> **Theorem 1 (Bounded Crash Impact).** A single poison job causes at most
> $N_{\text{threshold}}$ crashes.
>
> _Proof._ Each crash increments $\mathsf{crash\_count}(j)$. After
> $N_{\text{threshold}}$ increments, $\mathsf{quarantined}(j) = \mathsf{true}$,
> excluding $j$ from processing. $\square$

### Visual: The Quarantine Progression

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ POISON JOB TIMELINE (threshold = 3)                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Worker A picks up Job 123                                                  │
│     │                                                                       │
│     ▼                                                                       │
│  ☠️ Worker A CRASHES (OOM)                                                  │
│     │                                                                       │
│     ├──► crash_count(123) = 1    [Still below threshold]                   │
│     │                                                                       │
│     ▼                                                                       │
│  Worker B picks up Job 123 (retrying)                                       │
│     │                                                                       │
│     ▼                                                                       │
│  ☠️ Worker B CRASHES (same bug!)                                            │
│     │                                                                       │
│     ├──► crash_count(123) = 2    [Still below threshold]                   │
│     │                                                                       │
│     ▼                                                                       │
│  Worker C picks up Job 123 (retrying again)                                 │
│     │                                                                       │
│     ▼                                                                       │
│  ☠️ Worker C CRASHES (pattern confirmed)                                    │
│     │                                                                       │
│     ├──► crash_count(123) = 3    [THRESHOLD REACHED!]                       │
│     │                                                                       │
│     ▼                                                                       │
│  🚫 Job 123 QUARANTINED                                                     │
│     │                                                                       │
│     ▼                                                                       │
│  Worker D checks: "Is Job 123 quarantined?" → YES → SKIP                   │
│  Worker E checks: "Is Job 123 quarantined?" → YES → SKIP                   │
│  ...                                                                        │
│                                                                             │
│  ✓ Loop BROKEN. Human investigates. System stable.                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key insight**: The bounded retry counter prevents a single problematic job
from consuming infinite resources. Three dead workers is bad; one hundred is
catastrophic. The quarantine threshold is a circuit breaker for poison jobs.

---

## Part VII: Correctness Proofs

### Property 1: Mutual Exclusion (Safety)

> **Theorem 2 (Safety).** At most one worker processes job $j$ at any time $t$:
>
> $$\forall j \in \mathcal{J}, \; \forall t \in \mathbb{R}^+ : \left| \left\{ p \in \mathcal{P} : \mathsf{processing}(p, j, t) \right\} \right| \leq 1$$

_Proof._ By contradiction. Assume $p_1 \neq p_2$ both process $j$ at time $t$.

1. Both hold valid leases: $\mathcal{K}_L(j).\mathsf{value} = p_1.\mathsf{id}$
   AND $\mathcal{K}_L(j).\mathsf{value} = p_2.\mathsf{id}$
2. Redis keys have unique values $\implies p_1.\mathsf{id} = p_2.\mathsf{id}$
3. Contradiction. $\square$

**Caveat (Clock Skew Bound).** Safety holds iff clock skew
$\varepsilon < T_{\text{short}} - \Delta t_{\text{heartbeat}}$

### Property 2: Crash Detection (Liveness)

> **Theorem 3 (Liveness).** Every crash is eventually detected:
>
> $$\forall p \in \mathcal{P}, \; \forall j \in \mathcal{J} : \mathsf{crash}(p) \land \mathsf{processing}(p, j) \implies \Diamond \, \mathsf{detected}(j)$$

_Proof._

1. $\mathsf{crash}(p)$ at $t_{\text{crash}} \implies p$ stops calling
   $\mathsf{renew}()$
2. $\mathcal{K}_L(j)$ expires at $t_{\text{crash}} + T_{\text{short}}$
3. $\mathcal{K}_S(j)$ persists (since $T_{\text{long}} \gg T_{\text{short}}$)
4. Next scan evaluates:
   $\exists \mathcal{K}_S(j) \land \neg \exists \mathcal{K}_L(j) \implies \mathsf{crashed}(j) = \mathsf{true}$
   $\square$

**Detection bound:**
$t_{\text{detect}} - t_{\text{crash}} \leq T_{\text{short}} + T_{\text{scan}}$

### Property 3: Bounded Retry

> **Theorem 4 (Bounded Retry).** No job executes more than
> $N_{\text{threshold}}$ times:
>
> $$\forall j \in \mathcal{J} : \mathsf{attempts}(j) \leq N_{\text{threshold}}$$

_Proof._ Direct from Theorem 1 and the quarantine predicate. $\square$

---

## Part VIII: Complexity Analysis

### Time Complexity

| Operation        | Complexity       | Redis Commands           |
| ---------------- | ---------------- | ------------------------ |
| `acquire_lease`  | $\mathcal{O}(1)$ | SET NX EX, HSET, EXPIRE  |
| `renew_lease`    | $\mathcal{O}(1)$ | EVALSHA (Lua)            |
| `release_lease`  | $\mathcal{O}(1)$ | EVALSHA, DEL             |
| `detect_crashes` | $\mathcal{O}(n)$ | SCAN + $n \times$ EXISTS |

Where $n = |\{j \in \mathcal{J} : \mathsf{in\_progress}(j)\}|$ (typically
small).

### Space Complexity

Per job $j \in \mathcal{J}$:

- $\mathcal{K}_L(j)$: $\mathcal{O}(|\mathsf{worker\_id}|) \approx 36$ bytes
  (UUID)
- $\mathcal{K}_S(j)$: $\mathcal{O}(1) \approx 200$ bytes (fixed schema hash)
- $\mathcal{K}_{\text{count}}(j)$: $\mathcal{O}(1) \approx 8$ bytes (integer)

**Total per job:** $\sim 250$ bytes

### Network Complexity

Heartbeat overhead per worker:

$$\text{messages/second} = \frac{1}{\Delta t_{\text{heartbeat}}} = \frac{1}{10} = 0.1 \text{ msg/s}$$

With 100 workers: 10 Redis operations/second for heartbeats—negligible.

---

## Part IX: Failure Modes and Mitigations

### Failure Mode 1: Clock Skew

**Problem formalization:** Let $\tau_w(t)$ be worker's clock, $\tau_r(t)$ be
Redis's clock. Clock skew $\varepsilon = |\tau_w(t) - \tau_r(t)|$.

If $\varepsilon > T_{\text{short}} - \Delta t_{\text{heartbeat}}$, the worker
may believe its lease is valid when Redis has expired it.

**Formal safety condition:**

$$\varepsilon < T_{\text{short}} - \Delta t_{\text{heartbeat}}$$

With defaults: $\varepsilon < 30\text{s} - 10\text{s} = 20\text{s}$

**Mitigation:** NTP synchronization typically achieves
$\varepsilon < 100\text{ms}$. We have $200\times$ safety margin.

### Failure Mode 2: Network Partitions

**Problem:** Worker $w$ is partitioned from Redis. It continues processing while
$\mathcal{K}_L(j)$ expires. Another worker $w'$ detects crash and begins
processing $\implies$ **duplicate execution**.

**Formal model (asynchronous partition):**

$$\mathsf{partition}(w, \text{Redis}) \text{ at time } t_p$$
$$\mathcal{K}_L(j) \text{ expires at } t_p + T_{\text{short}}$$
$$w' \text{ detects crash at } t_p + T_{\text{short}} + T_{\text{scan}}$$
$$w \text{ continues until } t_p + T_{\text{process}}$$

If $T_{\text{process}} > T_{\text{short}} + T_{\text{scan}} \implies$ duplicate
execution.

**Mitigation (Fencing Token Pattern):** From Kleppmann's analysis:

```python
# Before committing results
if not await renew_lease(redis, job_id, worker_id):
    raise LeaseExpiredError("Lost lease - aborting to prevent duplicate work")
# Only then commit
```

### Failure Mode 3: Thundering Herd

**Problem:** $N$ workers start simultaneously (K8s rollout). All evaluate
$\mathsf{crashed}(j) = \mathsf{true}$ for the same jobs.

**Formal:** Let $\mathcal{W} = \{w_1, \ldots, w_n\}$ start at time $t$. All call
`detect_crashes()` concurrently:

$$\forall w_i \in \mathcal{W} : \text{detect\_crashes}() \text{ returns } \mathsf{crashed\_jobs} = \{j_1, j_2, \ldots\}$$

All attempt to requeue the same jobs.

**Mitigation options:**

1. **Leader election**: Only leader runs crash detection (adds complexity)
2. **Distributed lock**: Acquire lock before crash scan (adds latency)
3. **Idempotent recovery**: Accept duplicate detection, ensure idempotent
   requeue $\leftarrow$ _recommended_

### Failure Mode 4: Redis Unavailability

**Problem:** Redis failure $\implies$ all lease renewals fail $\implies$ all
workers believe they've lost leases $\implies$ mass abort.

**Formal:**

$$\mathsf{availability}(\text{Redis}) = \mathsf{false} \implies \forall w \in \mathcal{P} : \mathsf{renew\_lease}() = \mathsf{false}$$

**Mitigation stack:**

1. **Redis Sentinel/Cluster**: Automatic failover (RPO $\approx 0$, RTO $< 30$s)
2. **Circuit breaker**: Prevent cascading failures to application layer
3. **Graceful degradation**: Continue processing with degraded crash detection

**Note on Redlock:** For critical sections requiring stronger guarantees,
consider Redlock—but understand its limitations per Kleppmann's critique.

---

## Part X: CAP Theorem Implications

Our system makes explicit trade-offs in the CAP theorem space:

### CAP Position

| Property                | Our Choice  | Implication                                            |
| ----------------------- | ----------- | ------------------------------------------------------ |
| **Consistency**         | Eventual    | Crash detection may have delay $\leq T_{\text{short}}$ |
| **Availability**        | Prioritized | System continues if some workers crash                 |
| **Partition Tolerance** | Required    | Network partitions handled via lease expiry            |

We choose **AP with eventual consistency**—appropriate for job processing where:

- Temporary duplicate detection is acceptable
- Job queues provide natural consistency boundaries
- Availability (jobs keep processing) $>$ strong consistency

### PACELC Extension

Under PACELC:

- **Partition**: Choose A (availability)
- **Else**: Choose L (latency) over C (consistency)

Lease renewal is optimized for low latency (single Redis EXPIRE), accepting
eventual consistency in crash detection.

---

## Part XI: Tuning Guide

### Formal Tuning Constraints

$$\Delta t_{\text{heartbeat}} < \frac{T_{\text{short}}}{3} \quad \text{(two missed heartbeats before expiry)}$$

$$T_{\text{long}} > T_{\text{short}} + T_{\text{scan}} \quad \text{(evidence survives detection window)}$$

$$N_{\text{threshold}} \geq 2 \quad \text{(allow for transient failures)}$$

### Parameter Reference

| Parameter                                            | Default | Constraint                               | Rationale                           |
| ---------------------------------------------------- | ------- | ---------------------------------------- | ----------------------------------- |
| $T_{\text{short}}$ (`lease_ttl_seconds`)             | 30s     | $> 3 \times \Delta t_{\text{heartbeat}}$ | Detection speed vs. false positives |
| $\Delta t_{\text{heartbeat}}$ (`heartbeat_interval`) | 10s     | $< T_{\text{short}} / 3$                 | Safety margin for missed heartbeats |
| $T_{\text{long}}$ (`state_ttl_seconds`)              | 3600s   | $> T_{\text{short}} + T_{\text{scan}}$   | Evidence preservation               |
| $N_{\text{threshold}}$ (`crash_threshold`)           | 3       | $\geq 2$                                 | Transient fault tolerance           |

### Derivation: Optimal Heartbeat Interval

Minimize network overhead while maintaining safety:

$$\min_{\Delta t} \frac{1}{\Delta t_{\text{heartbeat}}} \quad \text{(messages/second)}$$

$$\text{subject to: } \Delta t_{\text{heartbeat}} < \frac{T_{\text{short}}}{3}$$

$$\text{optimal: } \Delta t_{\text{heartbeat}} = \frac{T_{\text{short}}}{3} - \varepsilon$$

With $T_{\text{short}} = 30$s: $\Delta t_{\text{heartbeat}} \approx 10$s
$\implies 0.1$ msg/s per worker.

---

## Appendix: The Full State Machine

```text
                    ┌─────────────┐
                    │             │
            ┌──────▶│    IDLE     │◀──────┐
            │       │             │       │
            │       └──────┬──────┘       │
            │              │               │
            │    acquire_lease()           │
            │              │               │
            │              ▼               │
            │       ┌─────────────┐       │
            │       │             │       │
            │       │ PROCESSING  │───────┤ release_lease()
            │       │             │       │
            │       └──────┬──────┘       │
            │              │               │
            │     lease expires           │
            │     (no heartbeat)          │
            │              │               │
            │              ▼               │
            │       ┌─────────────┐       │
      crash_count   │             │       │
      < threshold   │   CRASHED   │       │
            │       │             │       │
            │       └──────┬──────┘       │
            │              │               │
            └──────────────┤               │
                           │               │
                  crash_count              │
                  >= threshold             │
                           │               │
                           ▼               │
                    ┌─────────────┐       │
                    │             │       │
                    │ QUARANTINED │───────┘
                    │             │   (manual intervention)
                    └─────────────┘
```

**State transition predicates:**

- IDLE $\to$ PROCESSING: $\mathsf{acquire}(p, j)$ succeeds
- PROCESSING $\to$ IDLE: $\mathsf{release}(\mathcal{L})$ called
- PROCESSING $\to$ CRASHED: $\mathsf{crashed}(j) = \mathsf{true}$
  (Definition 9)
- CRASHED $\to$ IDLE: $\mathsf{crash\_count}(j) < N_{\text{threshold}}$
  (retry)
- CRASHED $\to$ QUARANTINED: $\mathsf{quarantined}(j) = \mathsf{true}$
  (Definition 11)
- QUARANTINED $\to$ IDLE: Manual intervention resets
  $\mathsf{crash\_count}(j)$

---

## Conclusion: Embrace the Uncertainty

### Summary

We've presented a **Two-Key Time-Bound Lease Pattern** for crash detection in
distributed job processing. The key contributions:

| Contribution              | Formal Basis                                                          |
| ------------------------- | --------------------------------------------------------------------- |
| **System model**          | Crash-stop failure model with partial synchrony                       |
| **Failure detection**     | Implements Eventually Perfect ($\Diamond \mathcal{P}$) detector       |
| **Two-key decomposition** | Separates liveness ($\mathcal{K}_L$) from forensics ($\mathcal{K}_S$) |
| **Quarantine pattern**    | Bounded retry prevents cascading failures                             |
| **Correctness proofs**    | Safety, liveness, bounded retry with formal proofs                    |

### Theoretical Position

We navigate impossibility results by making explicit trade-offs:

$$\text{FLP Impossibility} \xrightarrow{\text{relax}} \text{Partial synchrony assumption}$$

$$\text{CAP Theorem} \xrightarrow{\text{choose}} \text{AP with eventual consistency}$$

$$\text{Accuracy vs. Completeness} \xrightarrow{\text{tune}} T_{\text{short}} \text{ parameter}$$

The lease pattern doesn't solve these impossibilities—it _embraces_ them. It
says:

> "I can't know if you're dead, but I can know if you've been silent too long.
> And that's good enough."

### Practical Impact

Is it perfect? No. Nothing in distributed systems is.

But it's:

- **Practical**: $\mathcal{O}(1)$ operations, $\sim 250$ bytes/job overhead
- **Battle-tested**: Leases power Chubby, ZooKeeper, etcd
- **Theoretically grounded**: Rooted in 35+ years of distributed systems
  research

And at 2 AM, when Worker #7 goes silent, you'll know exactly what happened—and
what to do about it.

---

## References

### Foundational Papers

- **Fischer, Lynch, Paterson (1985)** — "Impossibility of Distributed
  Consensus with One Faulty Process." The FLP impossibility result.
  [Link](https://groups.csail.mit.edu/tds/papers/Lynch/jacm85.pdf)

- **Chandra & Toueg (1996)** — "Unreliable Failure Detectors for Reliable
  Distributed Systems." Failure detector classification
  ($\Diamond \mathcal{P}$, $\Diamond \mathcal{S}$).
  [Link](https://www.cs.utexas.edu/~lorenzo/corsi/cs380d/papers/p225-chandra.pdf)

- **Dwork, Lynch, Stockmeyer (1988)** — "Consensus in the Presence of Partial
  Synchrony." Theoretical foundation for practical consensus.
  [Link](https://groups.csail.mit.edu/tds/papers/Lynch/jacm88.pdf)

- **Gray & Cheriton (1989)** — "Leases: An Efficient Fault-Tolerant Mechanism
  for Distributed File Cache Consistency." The original leases paper.
  [Link](http://i.stanford.edu/pub/cstr/reports/cs/tr/90/1298/CS-TR-90-1298.pdf)

### Industrial Systems

- **Burrows (2006)** — "The Chubby Lock Service for Loosely-Coupled
  Distributed Systems." Google's production lease-based lock service.
  [Link](https://research.google/pubs/the-chubby-lock-service-for-loosely-coupled-distributed-systems/)

- **Hunt et al. (2010)** — "ZooKeeper: Wait-free Coordination for
  Internet-scale Systems." Ephemeral nodes with session timeouts.
  [Link](https://www.usenix.org/legacy/event/atc10/tech/full_papers/Hunt.pdf)

- **etcd Documentation** — Leases.
  [Link](https://etcd.io/docs/v3.5/dev-guide/interacting_v3/#lease)

### Practical Guidance

- **Redis Distributed Locks** — Official Redis documentation on distributed
  locking patterns.
  [Link](https://redis.io/docs/latest/develop/use/patterns/distributed-locks/)

- **Kleppmann (2016)** — "How to do distributed locking." Critical analysis of
  Redlock safety. Essential reading.
  [Link](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html)

- **Kleppmann (2017)** — _Designing Data-Intensive Applications_. Chapter 8 on
  distributed systems. O'Reilly. [Link](https://dataintensive.net/)

- **Google SRE Book (2016)** — "Addressing Cascading Failures." Production
  patterns for failure isolation.
  [Link](https://sre.google/sre-book/addressing-cascading-failures/)

### Related Patterns

- **Martin Fowler** — "Time-Bound Lease."
  [Link](https://martinfowler.com/articles/patterns-of-distributed-systems/time-bound-lease.html)

- **Martin Fowler** — "Circuit Breaker."
  [Link](https://martinfowler.com/bliki/CircuitBreaker.html)

- **Crash-Only Software** — Candea & Fox, USENIX HotOS '03.
  [Link](https://www.usenix.org/legacy/events/hotos03/tech/full_papers/candea/candea.pdf)

- **AWS SQS Dead Letter Queues** — Poison pill isolation.
  [Link](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
  \*\*
