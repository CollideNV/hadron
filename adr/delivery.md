# Delivery Strategy & CR Lifecycle

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 13. Delivery Strategy Reference

| | self_contained | push_and_wait | push_and_wait + human review | push_and_forget |
|---|---|---|---|---|
| Who runs CI | Pipeline (in-pod) | External CI | External CI | External CI |
| Human PR review | No (internal AI review) | No (internal AI review) | **Yes** — waits for PR approval | Yes (after pipeline completes) |
| Worker during CI | Running (in-pod verification) | **Terminated** (checkpoint + release pod) | **Terminated** | Terminated (done) |
| CI result handling | Immediate (same pod) | Webhook → Controller → new pod resumes | Same + waits for PR approval | N/A |
| Feedback to dev? | Yes | Yes (if CI fails, new pod loops) | Yes (CI failure + human review comments) | No |
| Release gate? | Yes | Yes | Yes | No (human reviews PR manually) |
| Best for | No existing CI | Existing CI, trust AI review | Existing CI + want human approval before merge | Existing CI + fully manual approval |
| Cost efficiency | Pod active throughout | Pod released during CI wait | Pod released during CI + review wait | Pod released immediately |

---

## 15. CR Lifecycle

### 15.1 Design Principle

The pipeline never silently gives up. Every failure, every dead end, every circuit breaker results in a **pause and a decision screen** — the human always chooses what happens next. The pipeline proposes; the human disposes.

### 15.2 State Model

```
                          ┌──────────┐
              trigger ───▶│ running  │◄──────── resume / retry
                          └────┬─────┘
                               │
                          (completes, or pipeline can't continue)
                               │
                          ┌────▼──────┐
                          │  paused   │  ← circuit breaker, max loops, provider down,
                          │ (decision │    unresolvable conflict, approval wait, CI wait
                          │  needed)  │
                          └────┬──────┘
                               │
                    human decides (via dashboard)
                               │
              ┌────────────────┼────────────────┐
              │                │                │
         ┌────▼────┐    ┌─────▼──────┐    ┌────▼─────┐
         │completed│    │  failed    │    │ cancelled│
         └─────────┘    └────────────┘    └──────────┘
```

| State | Meaning | Who transitions here | Artifacts on remote |
|-------|---------|---------------------|-------------------|
| **running** | Pipeline is actively executing | Trigger or human resume/retry | Feature branches being built, possibly PRs open |
| **paused** | Pipeline stopped, waiting for human decision | Pipeline (circuit breaker, completion, conflict, wait) | Work in progress preserved |
| **completed** | Released successfully | Human (approved release) | Branches merged (or deleted per release config) |
| **failed** | Human decided to give up on this CR | Human (explicit choice) | Branches and PRs remain until human cleans up |
| **cancelled** | Human chose to stop this CR before it could finish | Human (explicit choice) | Branches and PRs remain until human cleans up |

**The pipeline never transitions directly to `failed`.** It always pauses first. The human sees the failure context — what went wrong, at which stage, for which repo — and chooses:

### 15.3 Failure Decision Screen

When the pipeline pauses due to a problem (circuit breaker, max retries, unresolvable conflict, all providers down), the dashboard presents a **decision screen** with the failure context and available actions:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CR-142: Add password reset flow                         [PAUSED ⏸]    │
│  Source: Jira PROJ-1234 │ Paused at: TDD Development │ Cost: $8.40    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ⚠ Circuit breaker: dev ↔ review loop exceeded 3 iterations            │
│                                                                         │
│  auth-service: Code Writer stuck on token expiry edge case.             │
│  Review keeps finding the same issue. Last review feedback:             │
│  "Token refresh logic doesn't handle concurrent sessions."              │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  What would you like to do?                                      │   │
│  │                                                                  │   │
│  │  [🔄 Retry with instructions]  Redirect the agent with guidance  │   │
│  │  [⏪ Restart from stage]        Pick a stage to go back to       │   │
│  │  [🔁 Retry from scratch]       Fresh start, new branch           │   │
│  │  [🖐 Take over manually]       Work on the branch yourself       │   │
│  │  [❌ Mark as failed]           Give up, open cleanup wizard      │   │
│  │  [🚫 Cancel CR]               Stop entirely, open cleanup wizard │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

| Action | What happens |
|--------|-------------|
| **Retry with instructions** | Operator provides guidance text. Pipeline resumes current stage with the instructions injected as highest-priority context. |
| **Restart from stage** | Operator picks a stage (e.g. go back to Behaviour Translation). Everything from that stage onward re-runs. Earlier artifacts preserved. |
| **Retry from scratch** | New pipeline attempt, same CR ID, fresh branch (`ai/cr-{id}-r2`). Previous artifacts remain for reference. |
| **Take over manually** | Human works on the branch directly (via `git clone`). Can mark stages as manually completed in the dashboard when done. When the human clicks "Resume," the pipeline runs a **Sync Node** before the AI continues (see below). |
| **Mark as failed** | CR moves to `failed`. Cleanup wizard opens (see §15.4). Source updated. |
| **Cancel CR** | CR moves to `cancelled`. Cleanup wizard opens (see §15.4). Source updated. |

This same decision screen appears for *every* pause reason — circuit breakers, provider outages, unresolvable merge conflicts, partial multi-repo failures. The context section at the top changes; the action options remain consistent.

Notifications (§17) alert the operator when a CR enters `paused` state, so decision screens don't go unnoticed.

**Resume-with-Validation (Sync Node):** When a human takes over a branch, works on it manually, and then clicks "Resume" in the dashboard, the pipeline does **not** assume the code is valid. The human may have changed anything — added files, refactored code, fixed tests, or introduced new issues. The pipeline runs a Sync Node before the AI continues:

```
Human clicks "Resume"
         │
    ┌────▼───────────────────────────────────────────────────────┐
    │  Sync Node                                                  │
    │                                                             │
    │  1. git diff: compare current branch against last           │
    │     AI-known state (the commit when the pipeline paused)    │
    │                                                             │
    │  2. LLM analysis: summarise what the human changed and      │
    │     update Behaviour Specs if the changes affect them       │
    │                                                             │
    │  3. Full test suite: run all tests to establish a clean     │
    │     baseline before the AI continues                        │
    │                                                             │
    │  4. Update PipelineState: inject the diff summary, updated  │
    │     specs, and test results into the pipeline context       │
    └────┬───────────────────────────────────────────────────────┘
         │
    Pipeline resumes from the next stage with full awareness
    of what the human did
```

If the test suite fails after the human's changes, the pipeline pauses again (same decision screen) — the human's work introduced a regression, and the operator needs to decide whether to fix it manually or let the AI try.

This handover sync ensures the AI never operates on stale assumptions about the codebase. The diff summary becomes part of the Loop Context (Layer 4) for subsequent agents, so they understand what changed and why.

### 15.4 Cancel / Abort

When an operator explicitly cancels a CR — either from the decision screen or directly from the control room — the CR moves to `cancelled` or `failed`. **The pipeline never auto-deletes artifacts.** Branches and PRs remain on the remote.

The dashboard presents a **cleanup wizard** — a guided form that lets the operator decide what to do with the leftovers:

| Artifact | Options presented | Default |
|----------|------------------|---------|
| Feature branches (`ai/cr-{id}`) | Keep (for reference) / Delete | Keep |
| Open pull requests | Close (with comment) / Leave open / Close and delete branch | Close with comment |
| Source issue status | Report cancelled (or failed) / Leave as-is | Report status |

The operator picks per artifact. The pipeline executes the chosen cleanup. If the operator dismisses the wizard, everything stays — they can come back to it later from the CR detail page.

### 15.5 Source System Changes

The pipeline works from a **snapshot** of the CR taken at intake — it never auto-restarts or auto-updates from a moving target. If the source issue changes while the pipeline is running, the response depends on what changed:

**Substantive changes (auto-pause):** If the CR description or acceptance criteria change, the pipeline is working against stale requirements. Continuing is likely wasteful. The pipeline **auto-pauses** and presents a decision screen:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CR-142: Add password reset flow                         [PAUSED ⏸]    │
│  Source: Jira PROJ-1234 │ Paused at: TDD Development │ Cost: $4.10    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ⚠ Source issue was updated while pipeline is running.                  │
│                                                                         │
│  Changes detected:                                                      │
│  - Description: added "also send a confirmation email to the user"      │
│  - Acceptance criteria: added "user receives email within 30 seconds"   │
│                                                                         │
│  The pipeline was working from the original version taken at intake.    │
│  Continuing will produce code that doesn't match the updated CR.        │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  What would you like to do?                                      │   │
│  │                                                                  │   │
│  │  [🔁 Cancel and re-trigger]   Recommended — start fresh with     │   │
│  │                                updated requirements               │   │
│  │  [🔄 Redirect agent]          Inject the new requirements into   │   │
│  │                                the current stage                  │   │
│  │  [▶ Continue anyway]          Ignore the update, finish as-is    │   │
│  │  [❌ Cancel CR]               Stop entirely, open cleanup wizard │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Cancel and re-trigger** is the recommended default for description changes — the pipeline starts a fresh attempt with the updated requirements. But the human always decides. Redirecting the agent is viable for small additions if the pipeline is early enough. Continuing is valid if the change is cosmetic.

**Non-substantive changes (notify only):** Status, priority, assignment, and label changes don't affect what the pipeline is building. These generate a notification but don't pause the pipeline:

| Source event | Pipeline reaction |
|-------------|------------------|
| Issue description / acceptance criteria edited | **Auto-pause** + decision screen (above) |
| Issue closed / resolved externally | **Notify** CR subscribers: "Source issue was closed. Consider cancelling this CR." |
| Issue deleted | **Notify** CR subscribers: "Source issue was deleted. Consider cancelling this CR." |
| Issue re-assigned | **Notify** new assignee: "This issue has an active pipeline run." |
| Issue priority / labels changed | **Notify** CR subscribers. No pipeline effect. |

The pipeline never cancels itself based on source changes — the human always makes that call. Source connectors poll or receive webhooks for these changes and emit notification events. This requires the connector to watch for *updates* on tracked issues, not just new issues.

What counts as "substantive" is configurable per source connector. For Jira: description and acceptance criteria fields. For GitHub Issues: issue body. For the direct API: the `description` and `acceptance_criteria` fields.

### 15.6 Partial Success (Multi-Repo)

A multi-repo CR is **one unit of change**. If any repo fails, the CR has not succeeded — you cannot release half a feature. If `auth-service` passes review but `api-gateway` loops 3 times and triggers a circuit breaker, the entire CR is paused.

The operator sees the per-repo status in the dashboard and gets the standard decision screen (§15.3), with the failure context showing which repo is stuck and why. The actions apply to the **whole CR**:

| Action | What happens |
|--------|-------------|
| **Redirect the failing repo** | Operator provides new instructions for the stuck repo's agent. Pipeline retries that repo. Successful repos wait. |
| **Take over the failing repo** | Human works on the failing repo's branch directly. Marks it done manually. Pipeline resumes for all repos from the next stage. |
| **Retry from stage (all repos)** | Operator picks a stage to restart from. All repos re-run from that stage. |
| **Retry from scratch** | Fresh attempt, new branches for all repos. |
| **Mark as failed** | Entire CR fails. Cleanup wizard for all repos' artifacts. |

The key constraint: **no repo advances to delivery until all repos have passed all stages.** The fan-out/fan-in model (§8.11) already enforces this — but it's worth stating explicitly that this applies to the failure case too. A CR either ships completely or not at all.
