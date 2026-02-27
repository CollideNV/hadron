# Orchestration — LangGraph

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 5. Orchestration — LangGraph

### 5.1 Why LangGraph

LangGraph provides: directed graph execution (nodes = stages, edges = transitions), persistent state checkpointing (PostgreSQL), conditional routing (feedback loops), human-in-the-loop interrupts, and subgraph composition (each stage can be its own graph). The checkpointing is critical — it means any worker pod can resume any pipeline run from the last completed node.

### 5.2 Pipeline State

The pipeline carries a state object through all nodes. Key state groups:

| Group | Fields | Purpose |
|-------|--------|---------|
| **CR Source** | source, external ID, external URL | Traceability back to origin |
| **Change Request** | CR ID, raw text, structured CR | The work to be done |
| **Repo Context** | affected repos, repo identification result, worktree paths, delivery configs | What repos, where on disk, how to deliver |
| **Behaviour** | specs per repo, verified flag, verification feedback | What to build |
| **Development** | code changes, test results, dev iteration count | The building |
| **Review** | findings per repo, critical flag, review iteration count | Quality checks |
| **Delivery** | push results, verification results, all-verified flag | Getting it out |
| **Release** | approved flag, release results | Final gate |
| **Cost** | accumulated token cost per model, total cost USD | Budget tracking |
| **Config** | snapshot of pipeline defaults, repo config, agent chains, circuit breakers at CR start | Stable config for CR lifetime (§21.4) |
| **Intervention** | human override instructions | Control room input |

State is checkpointed to PostgreSQL after every node completes.

### 5.3 Graph Structure

```
                        ┌─────────┐
                        │  START  │  ← RawChangeRequest from source connector
                        └────┬────┘
                             │
                     ┌───────▼───────┐
                     │    Intake     │  → acknowledge("pipeline_started")
                     └───────┬───────┘
                             │
                  ┌──────────▼──────────┐
                  │ Repo Identification │  ← Phase 1: explicit tags
                  │                     │  ← Phase 2+: LLM + landscape knowledge
                  └─────┬─────────┬─────┘
                        │         │ needs confirmation
                        │   ┌─────▼──────────────┐
                        │   │ Await Confirmation  │  ← interrupt → dashboard / source
                        │   └─────┬──────────────┘
                        │         │ human confirms
                        ◄─────────┘
                        │
                   ┌─────────▼─────────┐
                   │  Setup Worktrees  │
                   └─────────┬─────────┘
                             │
              ┌──────────────▼──────────────┐
         ┌───▶│  Behaviour Translation      │
         │    └──────────────┬──────────────┘
         │    ┌──────────────▼──────────────┐
         │    │  Behaviour Verification     │
         │    └──────────┬────────┬─────────┘
         └── issues ─────┘        │ verified
                                  │
         ┌────────────────────────▼──────────────────────┐
    ┌───▶│  TDD Development                              │◀── CI failure
    │    └────────────────────────┬───────────────────────┘
    │    ┌────────────────────────▼──────────────────────┐
    │    │  Code Review                                  │
    │    └────────────┬───────────────────┬──────────────┘
    └── critical ─────┘                   │ pass
                                          │
                   ┌──────────────────────▼─────────────────────┐
                   │  Rebase onto latest main (per repo)        │
                   └──────┬───────────────────────┬─────────────┘
                     clean │                       │ conflicts
                          │          ┌─────────────▼─────────────┐
                          │          │ Merge Conflict Agent       │
                          │          └──┬──────────────────┬─────┘
                          │    resolved │                  │ unresolvable
                          │          ┌──▼──────────┐   ┌──▼──────────────┐
                          │          │ Re-run tests │   │ Pause → human   │
                          │          └──┬──────┬───┘   │ takes over      │
                          │        pass │      │ fail  └─────────────────┘
                          ◄─────────────┘      └──────▶ loop to TDD Dev
                          │
                   ┌──────▼────────────────────────────────────┐
                   │  Delivery (strategy-dependent)             │
                   └──────┬───────────────┬──────────┬─────────┘
                     forget│          pass │     fail │
                          ▼               ▼          │
                       Cleanup    ┌───────────┐      │
                                  │  Release  │──────┘
                                  │  Gate     │
                                  └─────┬─────┘
                                        │ approved
                                  ┌─────▼─────────────────────┐
                                  │  Atomic Merge Check       │
                                  │  (main moved? → re-rebase)│
                                  └─────┬─────────────────────┘
                                        │ fresh
                              ┌─────────▼──────────┐
                              │  Release            │
                              └─────────┬──────────┘
                              ┌─────────▼──────────┐
                              │  Retrospective      │  → learnings → Knowledge Store
                              └─────────┬──────────┘
                              ┌─────────▼──────────┐
                              │  Cleanup            │ → report_result()
                              └────────────────────┘
```

**Conditional edges:** Behaviour Verification loops back to Translation on issues. Code Review loops back to TDD Development on critical findings. Rebase routes to Merge Conflict Agent on conflicts, which loops back to TDD Development if resolution breaks tests, or pauses for human take-over if unresolvable. Delivery loops back to TDD Development on CI failure. Release Gate routes to Release on approval or back to Cleanup on rejection. After approval, the Atomic Merge Check loops back to Rebase if `main` has moved since the last test cycle. After Release (or failure), the Retrospective Agent distils learnings into the Knowledge Store.
