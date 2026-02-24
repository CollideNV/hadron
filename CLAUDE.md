# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hadron is an AI-powered SDLC pipeline by Collide. It transforms change requests from external sources (Jira, GitHub Issues, Azure DevOps, Slack, direct API) into production-ready, reviewed code through a sequence of AI agent teams, with real-time observability and human intervention at any point.

**Status:** Pre-implementation. The canonical architecture document is `adr/architecture.md` (v5.0, Feb 2026). All design decisions, stage details, and implementation roadmap live there.

## Architecture (High Level)

**Pluggable Head → Fixed Core → Pluggable Tail**

- **Head:** CR source connectors (Jira, GitHub Issues, ADO, Slack, API)
- **Core:** LangGraph-based orchestration with ~12 stages, persistent PostgreSQL checkpointing, feedback loops
- **Tail:** Delivery strategies (`self_contained`, `push_and_wait`, `push_and_forget`)

### Pipeline Stages

Intake → Repo Identification → Worktree Setup → Behaviour Translation (Gherkin) → Behaviour Verification → TDD Development (red/green/refactor) → Code Review (security + quality + spec compliance) → Rebase & Conflict Resolution → Delivery → Release Gate (human approval) → Release → Retrospective

Key feedback loops: Verification↔Translation, Review↔TDD, CI↔TDD.

### Three Process Types

| Process | Lifecycle | Role |
|---------|-----------|------|
| **Controller** | Always-on (2+ replicas), lightweight | Intake, dashboard API (FastAPI), webhooks, job spawning |
| **Worker** | Ephemeral K8s Job (one per CR) | LangGraph executor, agent backends, worktree management |
| **Scanner** | CronJob (nightly + incremental) | Landscape knowledge building via LLM analysis |

### Infrastructure

- **PostgreSQL:** LangGraph state checkpoints, Knowledge Store (pgvector), runtime config, audit trail
- **Redis:** Event streams (Redis Streams), pub/sub, interventions, CI results
- **Keycloak:** OIDC identity provider (any OIDC provider supported)
- **Kubernetes:** Worker isolation, ephemeral pods, stage-aware network policies

### Agent Architecture

- **Backends:** Claude Agent SDK (primary), OpenCode SDK, OpenAI Codex SDK — configurable per stage, per repo, with ordered provider chains for failover
- **Prompt composition (4 layers):** Role system prompt → Repo context (AGENTS.md, tech stack, learnings) → Task payload (CR, specs, code) → Loop feedback
- **Static context capped at ~12k tokens;** agents use tools to discover full context dynamically
- **Trust models vary by role:** Spec Writer trusts CR; Security Reviewer treats CR as hostile

### Key Patterns

- **Checkpoint-and-terminate:** Workers checkpoint to PostgreSQL and terminate during CI/approval waits, freeing compute. New pod resumes from checkpoint.
- **Fan-out/fan-in:** Multi-repo CRs run parallel agent instances (one per repo) within a single pod. All repos must complete a stage before any advances.
- **Config snapshots:** Running CRs use config frozen at intake. Runtime config changes only affect new CRs.
- **Six-layer prompt injection defense:** Input screening → spec firewall → adversarial security review → deterministic diff scope analysis → runtime containment (egress lock) → optional human review.

### Multi-Tenancy

Single installation serves multiple tenants on shared infrastructure. OIDC handles authentication; pipeline's own database manages per-tenant roles (Viewer, Operator, Approver, Admin). Tenant ID scopes all data.

## Implementation Roadmap

The roadmap in `adr/architecture.md` §22 defines 8 phases:

1. **Foundation (Wk 1-2):** Project skeleton (LangGraph + FastAPI), runtime config, PipelineState, WorktreeManager, agent backend interface, event bus, intervention manager, prompt templates
2. **Core Stages (Wk 3-5):** All agent prompts, intake, fan-out/fan-in, Behaviour Translation/Verification, TDD, Code Review, feedback loops
3. **Delivery + CI (Wk 6-7):** Delivery strategies, checkpoint-and-terminate, CI webhooks, release gate, retrospective agent
4. **Control Room (Wk 8-9):** SSE events, dashboard, interventions, circuit breakers, settings UI
5. **Auth & Multi-Tenancy (Wk 10-11):** OIDC, internal authorization, tenant management, audit trail, notifications
6. **K8s Deployment (Wk 11-12):** Manifests, NetworkPolicy, dynamic sizing, agent command boundaries, Helm/Kustomize, local dev (kind)
7. **Production (Wk 13):** Observability, retention, load testing, prompt A/B testing
8. **Landscape Intelligence (Wk 14-17):** Scanner, Knowledge Store with pgvector, LLM-assisted repo identification

## Key Design Decisions

- **LangGraph + PostgreSQL checkpointing** — durable state survives pod failures; any worker can resume any CR
- **One pod per CR, not per repo** — shared filesystem visibility, single checkpoint, simple fan-out/fan-in
- **SSE over WebSocket** — event stream is unidirectional; interventions use REST; no sticky sessions needed
- **OIDC for auth, pipeline DB for authorization** — no dependency on IdP admin for day-to-day role management
- **Database-driven runtime config** — all settings editable via dashboard/API without redeployment
- **AGENTS.md convention** — repos include an `AGENTS.md` (or `CLAUDE.md`) with instructions for AI agents; this is the primary lever for controlling agent behaviour
- **Behaviour specs as firewall** — code agents work from Gherkin specs, not raw CR text
- **Graduated test scope in TDD** — narrow tests for fast iteration, full suite before review gate
- **Pipeline never auto-deletes artifacts** — human always decides cleanup via guided wizard
- **Pipeline never silently fails** — always pauses with a decision screen for the human
