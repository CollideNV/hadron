# Hadron — Architecture Document

**Hadron: AI-Powered SDLC Pipeline by Collide**

**Version 5.0 — February 2026**

---

## 1. Executive Summary

This document describes the architecture for a fully AI-driven Software Development Lifecycle (SDLC) pipeline. Change requests — from Jira, GitHub Issues, Azure DevOps, Slack, or a direct API — are transformed into production-ready, reviewed code through a sequence of AI agent teams, with real-time observability and human intervention at any point.

**CR Intake (pluggable head):** Connectors poll or receive webhooks from external issue trackers, normalise the CR, and trigger the pipeline. Configurable per deployment.

**Orchestration:** LangGraph (directed graph with persistent state, human-in-the-loop, subgraph composition). State checkpointed in PostgreSQL.

**Agent Backends (pluggable):** Claude Agent SDK, OpenCode SDK, or OpenAI Codex SDK — configurable per stage, per repo. Each agent role has an ordered provider chain for automatic failover, with retry policies, rate limit coordination, and proactive degradation routing.

**Repo Management:** Git worktrees — one branch per repo per change request, pod-local fast storage, zero-copy stage handoffs.

**Execution Sandboxing:** Kubernetes pods. Each change request runs in an ephemeral pod with process isolation, resource limits, and stage-aware network policies. AI-generated code runs egress-locked during TDD (LLM APIs and git only); full egress unlocked after Security Review passes. Test infrastructure (databases, caches) runs as ephemeral sidecars — no shared staging environments. Pod resources scale dynamically with CR complexity.

**Prompt Injection Defense:** Six-layer defense model. Input risk screening at intake catches low-effort attacks. Behaviour specs act as a sanitised firewall between untrusted CR text and code-writing agents. Security Reviewer operates in adversarial mode — treats the CR as hostile, flags code that doesn't match specs regardless of stated justification. Deterministic diff scope analysis catches out-of-scope changes. Runtime containment (egress lock, command boundaries) limits blast radius. Optional human PR review as final layer.

**Prompt Engineering:** Agent prompts are the product's core IP. Four-layer composition (role system prompt → repo context → task payload → loop feedback), version-controlled templates, A/B testing, and metrics-driven iteration.

**Landscape Intelligence:** A background Scanner continuously builds knowledge of the application ecosystem — what each service does, what it owns, how services connect. The pipeline queries this knowledge at intake time to determine affected repos.

**Delivery (pluggable tail):** Pluggable delivery strategies — the pipeline always produces code on a branch; what happens next (self-verify, push-and-wait-for-CI, push-and-forget) is configuration. PRs include a structured summary (specs, tests, review findings, cost). Optional human code review: teams can require PR approval before the release gate, with review comments feeding back into the TDD loop.

**Control Room:** Real-time event stream via Redis Streams and Server-Sent Events (SSE), with three levels of observability (pipeline → subgraph → agent tool calls). Pause, redirect, skip, take over, or abort at any moment (via REST API). Pluggable notifications (Slack, Teams, email, GitHub, custom webhooks) ensure humans stay informed.

**Multi-Repo Coordination:** When a CR affects multiple repos, agent instances run in parallel (one per repo) within the same worker pod. All repos share filesystem visibility. Fan-out/fan-in at each stage ensures coordinated progress.

**Cost Tracking:** Token costs accumulated per agent call in real-time. Dashboard shows running cost per CR. Circuit breakers auto-pause when thresholds are exceeded.

**Authentication:** OIDC-based, with Keycloak as the default identity provider. Role-based access controls who can view, intervene, approve releases, and administer the system. Multi-tenant: a single installation supports multiple teams with full logical isolation of repos, CRs, costs, and configuration.

**Deployment:** Kubernetes-native. Three process types — a lightweight always-on **Controller** (intake, dashboard, webhooks), ephemeral **Worker** pods (one per CR, LangGraph executor + agents), and a **Landscape Scanner** (background knowledge-building). Runs on any cloud (EKS, GKE, AKS), on-prem, or local (k3s, kind).

---

## 2. Pipeline Overview

### 2.1 Pluggable Head → Fixed Core → Pluggable Tail

```
┌─ PLUGGABLE HEAD ─────────┐    ┌─ FIXED CORE ─────────────────────────────────────────────────┐    ┌─ PLUGGABLE TAIL ──────┐
│                           │    │                                                               │    │                       │
│  Jira                     │    │  Intake → Repo ID → Worktrees → Behaviour → Verify →         │    │  self_contained       │
│  GitHub Issues            │───▶│                                  Translation                  │───▶│  push_and_wait        │
│  Azure DevOps             │    │                     TDD → Review → Delivery → Release         │    │  push_and_forget      │
│  Manual / API             │    │                                                               │    │                       │
│  Slack                    │    │  (with feedback loops: verify↔translate, review↔dev, CI↔dev)  │    │                       │
└───────────────────────────┘    └───────────────────────────────────────────────────────────────┘    └───────────────────────┘
                                                          ▲
                                                          │
                                                ┌─────────┴─────────┐
                                                │   CONTROL ROOM    │
                                                │  Real-time events │
                                                │  Pause / Redirect │
                                                │  Skip / Takeover  │
                                                └───────────────────┘
```

### 2.2 Stage Summary

| # | Stage | Input | Output | Agents | Feedback Loop |
|---|-------|-------|--------|--------|---------------|
| 0 | CR Source Connector | External event (Jira, GH, etc.) | Raw CR text + metadata | None (connector) | — |
| 1 | Change Request Intake | Raw CR text | Structured CR object + risk flags | LLM parse + Input Screener (§12.3) | ← auto-pause on high-risk injection patterns |
| 1b | Repo Identification | Structured CR + landscape knowledge | Confirmed list of affected repos | Phase 1: none. Phase 2+: LLM | ← human correction |
| 2 | Behaviour Translation | Structured CR + repo context | Gherkin specs per repo | Analyst → Mapper → Writer | ← from Verification |
| 3 | Behaviour Verification | Behaviour specs | Verified / rejected + feedback | Completeness + Consistency + Regression | → to Translation |
| 4 | TDD Development | Verified specs (+ review/CI feedback) | Passing code + tests on branch | Test Writer → Code Writer → Runner | ← from Review or CI |
| 5 | Code Review | Code + tests + specs + risk flags | Review verdict + scope warnings | Diff Scope Analyser + Security (adversarial) + Quality + Spec Compliance | → to Development |
| 5b | Rebase & Conflict Resolution | Reviewed code on branch | Clean branch on latest main | Merge Conflict Agent (if needed) | ← human take-over if unresolvable |
| 6 | Delivery | Rebased code on branch | Verification result | Depends on strategy | ← optional CI loop |
| 7 | Release Gate | Verification passed | Human approval | — (interrupt) | — |
| 7b | Atomic Merge Check | Approval granted | Fresh-or-stale verdict | None (git check) | ← auto-loop to Rebase if stale |
| 8 | Release | Approved + fresh code | Merged PR / deployed artefact | Scripted (not AI) | — |
| 8b | Retrospective | Completed or failed CR | Learnings per repo → Knowledge Store | Retrospective Agent | — (non-blocking) |

---

## Document Index

| Topic | File | Sections |
|-------|------|----------|
| Authentication & Authorization | [auth.md](auth.md) | §3 |
| CR Intake & Repo Management | [intake.md](intake.md) | §4, §6 |
| Orchestration (LangGraph) | [orchestration.md](orchestration.md) | §5 |
| Execution Sandboxing (K8s Pods) | [sandboxing.md](sandboxing.md) | §7 |
| Detailed Stage Design | [stages.md](stages.md) | §8 |
| Pluggable Agent Backends & Prompt Engineering | [agents.md](agents.md) | §9, §11 |
| Landscape Intelligence | [landscape.md](landscape.md) | §10 |
| Prompt Injection Defense | [security.md](security.md) | §12 |
| Delivery Strategy & CR Lifecycle | [delivery.md](delivery.md) | §13, §15 |
| Control Room, Cost, Notifications & Observability | [control-room.md](control-room.md) | §14, §16, §17, §18 |
| System Architecture & Scaling | [infrastructure.md](infrastructure.md) | §19, §20 |
| Configuration | [configuration.md](configuration.md) | §21 |
| Implementation Roadmap & Risks | [roadmap.md](roadmap.md) | §22, §24 |

---

## 23. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Pluggable CR sources | Pipeline doesn't own issue tracking — integrates with whatever exists |
| LangGraph + PostgreSQL checkpointing | Durable state survives pod failures; any worker can resume any CR |
| Redis for events + interventions | Decouples workers from controller; real-time pub/sub + persistent streams |
| Ephemeral K8s worker pods | One pod per CR — perfect isolation, auto-cleanup, cloud-agnostic |
| Pod IS the sandbox | No Docker-in-Docker; K8s provides all isolation natively |
| emptyDir workspace | Pod-local fast SSD; no shared filesystem complexity |
| Push to remote after every stage | All work survives pod failure; human take-over via git clone |
| Controller / Worker / Scanner split | Controller lightweight HA, workers heavy ephemeral, scanner independent background |
| Same manifests everywhere | kind → staging → production: only resource limits change |
| Database-backed runtime config | All pipeline settings editable via dashboard/API without redeployment. Only infrastructure bootstrap in files |
| Config snapshot per CR | Running CRs use the config they started with. Changes only affect new CRs. Same principle as CR description snapshots |
| Config versioned with audit trail | Every change tracked (who, what, when, before/after). Revert is just a new change restoring old values |
| SSE instead of WebSocket | Event stream is one-directional; interventions use REST. SSE is plain HTTP — auto-reconnects, no sticky sessions, no connection upgrade. Rolling updates become trivial |
| Controller rolling updates | SSE drops on pod drain; client auto-reconnects to new pod, replays from Redis Stream. Workers are ephemeral (new image on next spawn). Scanner is a CronJob (picks up new image on next run). Zero-downtime deploys with no special machinery |
| OIDC for authentication, pipeline DB for authorization | IdP tells us who you are. Our database decides what you can do and where. No dependency on IdP admin for day-to-day user/role management |
| Multi-tenant on shared infrastructure | Single Controller, single DB, tenant ID on every row. No per-tenant deployment overhead. Scales from 1 team to N teams without architectural change |
| One pod per CR, not one pod per repo | Cross-repo visibility (shared filesystem), single checkpoint, simple fan-out/fan-in. Pod-per-repo trades correctness simplicity for marginal parallelism — deferred until evidence of bottleneck |
| Per-tenant roles in pipeline DB | A user can be Admin in one tenant and Viewer in another. Managed via dashboard, not the IdP |
| Tenant switcher in dashboard | User selects active tenant. All views, actions, and events scope to it. `X-Tenant-ID` header on every API call |
| Role-based access with Approver gate | Release approval is the critical safety checkpoint — only authorised humans |
| Infrastructure-as-a-Sidecar | Test databases and caches are ephemeral pod sidecars. No shared staging. All state wiped when the pod dies |
| Stage-aware network policy (egress locking) | AI-generated code runs network-locked during TDD. Full egress unlocked only after Security Review passes |
| Dynamic worker sizing | Pod resources scale with CR complexity (repo count × weight). 1-repo fix gets a small pod; 5-repo feature gets a large one |
| Atomic Merge Check (stale approval protection) | After approval, verify main hasn't moved. If it has, auto-rebase and re-test before merging — no human re-approval needed unless tests fail |
| Agent Retrospective (post-CR knowledge distillation) | Lightweight LLM call after every CR extracts repo-specific learnings. Future CRs benefit from past mistakes |
| Resume-with-Validation (Sync Node) | After human take-over, pipeline diffs, updates specs, and re-runs tests before the AI continues. Never operates on stale assumptions |
| PR body as first-class output | Human reviewers outside the pipeline see a structured summary: CR, specs, test results, review findings, cost. Not an afterthought |
| Optional human PR review in delivery loop | Teams that don't trust AI-only review can require PR approval before release gate. Human review comments loop back to TDD like any other feedback |
| Git auth via short-lived tokens (GitHub App preferred) | Per-tenant, auto-rotated, scoped to repos. Workers never see raw credentials. SSH keys as fallback |
| Agent command boundaries (defense in depth) | Non-root user + seccomp + filesystem permissions + egress lock + SDK allowlists. Agents can run tests and builds but not inspect the pod or exfiltrate data |
| Configurable data retention with cleanup CronJob | Event streams 90 days, audit 2 years, cost detail 6 months, stale branches 90 days. All configurable per tenant. Compliance mode disables cleanup |
| Six-layer prompt injection defense | No single layer stops injection. Input screening + spec firewall + adversarial review + diff scope analysis + runtime containment + optional human review. Each catches what the others miss |
| Behaviour specs as sanitised intermediary | Code agents work from specs, not raw CR text. Malicious instructions must survive spec generation AND verification to affect code — two independent checkpoints |
| Adversarial Security Reviewer | Security Reviewer has a fundamentally different trust model than code-writing agents. CR description marked as untrusted. "The CR asked for it" is not a valid justification for suspicious code |
| Diff scope analysis is deterministic, not LLM | Can't be prompt-injected. Flags files/endpoints/dependencies outside expected scope. Structural check, not semantic |
| Four-layer prompt composition | Each layer changes at different rate — enables independent evolution |
| AGENTS.md convention | Teams control agent behaviour in their codebase — primary customisation lever |
| Versioned prompts with A/B testing | Prompts evolve based on metrics, not intuition |
| Scanner as separate process | Knowledge-building never blocks pipeline; improves continuously |
| Repo identification: manual → LLM → auto | Progressive trust: start safe, earn confidence, automate when proven |
| Feedback loop on repo identification | System gets smarter with every human correction |
| Parallel agent instances per repo | Multi-repo CRs run N agents in parallel — all repos in one pod, one graph, shared visibility |
| Fan-out / fan-in per stage | All repos complete a stage before any advances to the next — ensures coordinated feedback loops |
| Checkpoint-and-terminate during waits | Worker pods release compute during CI and approval waits; new pod resumes from checkpoint |
| Duplicate CR detection on external ID | Prevents double-processing from webhook retries or multi-source triggers |
| Pluggable secret providers | Vault, AWS SM, Azure KV, GCP SM, or K8s Secrets — whatever the deployment needs |
| Pluggable notification channels | Slack, Teams, email, GitHub, custom webhooks — all hookable, user-subscribable |
| Token cost tracking per agent call | Accumulated in real-time, visible in dashboard, drives circuit breakers |
| Monorepo as directory-scoped applications | Same model — one worktree, agents scoped to application directories |
| Graduated test scope during TDD | Narrow tests for fast iteration loops, full suite before review gate. Agent widens scope based on codebase understanding. Pre-existing failures excluded by diffing against main |
| Rebase before delivery, not at merge time | Catches conflicts while the pipeline still has full context (CR intent, specs, code). Agent or human can resolve immediately rather than discovering conflicts after PR is opened |
| Merge Conflict Agent with human fallback | Automated resolution for common cases; pause + notify for complex conflicts. Human always has the option to take over the branch |
| Provider chain per agent role | Ordered failover list, not single provider. Each role can have different chains — spec writing may demand Claude, quality review can use anything |
| Failover at agent-call granularity | Individual calls fail over independently. One degraded CR doesn't drag others to the fallback. Mid-conversation tool-use loops stay on one provider |
| Rate limit coordination across CRs | Shared token bucket per API key prevents 429 storms. Throttles proactively rather than hitting limits |
| Proactive failover on provider degradation | Don't wait for every call to fail and retry — route new calls to fallback when error rate exceeds threshold |
| Pipeline never auto-deletes artifacts | Branches, PRs, and commits always survive cancel/abort. Human decides cleanup via guided wizard |
| Source changes notify, don't control | Jira issue closed mid-run → notification, not cancellation. Human always makes the call |
| Substantive source changes auto-pause | Description/criteria edits pause the pipeline immediately — continuing against stale requirements is wasteful. Human decides: re-trigger, redirect, or continue |
| Pipeline never transitions directly to failed | Always pauses first. Human sees failure context and decides: retry, redirect, take over, or give up |
| Re-run from scratch or checkpoint | Operator chooses: full restart, resume from checkpoint, or resume from specific stage. Previous attempt artifacts preserved |
| Partial success is failure | Multi-repo CRs are atomic — no repo advances to delivery until all pass. You can't ship half a feature |

---

*Version 5.0 — February 2026*
