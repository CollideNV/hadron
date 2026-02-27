# System Architecture & Scaling

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 19. System Architecture

### 19.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                               │
│                                    KUBERNETES CLUSTER                                         │
│                                                                                               │
│  ┌────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │  CONTROLLER (Deployment, 2+ replicas, always running)                                  │   │
│  │                                                                                        │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐                     │   │
│  │  │ Source Connectors │  │ Dashboard API    │  │ Webhook Handler  │                     │   │
│  │  │ Jira, GH, ADO,   │  │ REST + SSE       │  │ CI webhooks,     │                     │   │
│  │  │ Slack, API        │  │ Auth (OIDC/JWT)  │  │ source webhooks, │                     │   │
│  │  └────────┬──────────┘  └────────┬─────────┘  │ git push hooks   │                     │   │
│  │           │                      │             └────────┬─────────┘                     │   │
│  │           │         ┌────────────▼──────────┐           │                               │   │
│  │           └────────▶│     Job Spawner       │◀──────────┘                               │   │
│  │                     │  Creates K8s Job/CR   │                                           │   │
│  │                     └───────────────────────┘                                           │   │
│  └────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                               │
│  ┌────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │  WORKER PODS (K8s Jobs, one per CR, ephemeral)                                         │   │
│  │                                                                                        │   │
│  │  ┌─ hadron-cr-142 ──────────────────────┐  ┌─ hadron-cr-143 ──────────────────┐   │   │
│  │  │  LangGraph Executor                     │  │  LangGraph Executor                │   │   │
│  │  │  Agent Backends (Claude/OpenCode/Codex) │  │  (same structure)                  │   │   │
│  │  │  /workspace (emptyDir volume)           │  │                                    │   │   │
│  │  └─────────────────────────────────────────┘  └────────────────────────────────────┘   │   │
│  │  ┌─ hadron-cr-144 ──────┐  ┌─ hadron-cr-145 ──────┐  ...more...                   │   │
│  │  └────────────────────────┘  └────────────────────────┘                                │   │
│  └────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                               │
│  ┌────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │  LANDSCAPE SCANNER (CronJob nightly + incremental on push)                             │   │
│  │                                                                                        │   │
│  │  Repo Scanner ──▶ LLM Analyser ──▶ Dependency Graph Builder ──▶ Knowledge Store        │   │
│  └────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                               │
│  ┌────────────────────────────────────────────────────────────────────────────────────────┐   │
│  │  SHARED INFRASTRUCTURE                                                                 │   │
│  │                                                                                        │   │
│  │  ┌──────────────────────┐   ┌──────────────────────┐   ┌─────────────────┐             │   │
│  │  │ PostgreSQL            │   │ Redis                 │   │ Keycloak        │             │   │
│  │  │ • LangGraph state    │   │ • Event streams       │   │ • OIDC provider │             │   │
│  │  │ • Knowledge Store    │   │ • Pub/Sub             │   │ • User/role mgmt│             │   │
│  │  │   (pgvector)         │   │ • Interventions       │   │ • JWT issuance  │             │   │
│  │  │ • Audit trail        │   │ • CI results          │   │                 │             │   │
│  │  │ • Metrics            │   │                       │   │                 │             │   │
│  │  └──────────────────────┘   └──────────────────────┘   └─────────────────┘             │   │
│  └────────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                               │
└──────────────────────────────────────────────────────────────────────────────────────────────┘

              │                        │                       │
              ▼                        ▼                       ▼
    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
    │ Issue Trackers    │    │ Git Remotes       │    │ External CI      │    │ LLM Providers    │
    │ Jira, GH Issues, │    │ GitHub, GitLab,   │    │ GH Actions,      │    │ Anthropic,       │
    │ ADO, Slack        │    │ Bitbucket         │    │ GitLab CI,       │    │ OpenAI, Google   │
    └──────────────────┘    └──────────────────┘    │ Jenkins           │    └──────────────────┘
                                                    └──────────────────┘
```

### 19.2 Process Types

| Process | Lifecycle | Scaling | Resources | Responsibilities |
|---------|-----------|---------|-----------|-----------------|
| **Controller** | Always running, 2+ replicas | Horizontal (replicas behind Service) | Lightweight: 500m CPU, 1GB RAM | Source connectors, job spawner, dashboard API, webhook handler, auth validation |
| **Worker** | Ephemeral K8s Job, one per CR | Scales with incoming CRs (0 → N) | Heavy: 2–4 CPU, 8–16GB RAM | LangGraph executor, agent backends, worktree management, event emission |
| **Scanner** | CronJob (nightly) + incremental | Single instance | Medium: 1–2 CPU, 4–8GB RAM | Repo scanning, LLM analysis, dependency graph, knowledge store writes |
| **Keycloak** | Always running, HA optional | 1–2 replicas | Medium: 1 CPU, 2GB RAM | OIDC provider, user/role management, JWT issuance |

### 19.3 Data Flow

```
 1. CR arrives (Jira webhook → Controller)
 2. Controller checks for duplicate (same external ID already in-flight)
 3. Controller authenticates request, creates K8s Job (Worker pod)
 4. Worker queries Knowledge Store for landscape context
 5. Repo identification (Phase 1: explicit, Phase 2+: LLM + human confirmation)
 6. Worker creates worktrees for all affected repos
 7. Worker runs LangGraph pipeline with per-repo parallelism:
    a. Each stage fans out to N agent instances (one per repo), fans in when all complete
    b. Each agent call emits events → Redis Streams
    c. Between agent calls, checks Redis for interventions
    d. Each stage pushes commits to git remote
    e. State checkpointed to PostgreSQL after each node
    f. Running cost accumulated from token usage
 8. After review passes: rebase onto latest main per repo
    If conflicts → Merge Conflict Agent resolves (or pauses for human)
    Re-run tests after resolution
 9. If push_and_wait: Worker checkpoints → pod terminates (frees compute)
    CI completes → webhook → Controller → new pod resumes from checkpoint
10. Release gate: Worker checkpoints → pod terminates
    Human approves → Controller → new pod resumes from checkpoint
11. Worker completes → Job cleaned up
12. Controller reports result + cost breakdown to source
13. Repo identification feedback → Knowledge Store
```

### 19.4 Environment Parity

Same architecture everywhere — only backing services and resource limits change:

| Component | Local (kind/k3s) | Staging | Production |
|-----------|-----------------|---------|------------|
| K8s cluster | kind / k3s | Small managed cluster | EKS / GKE / AKS |
| PostgreSQL | Single pod (+ pgvector) | Small managed instance | RDS / CloudSQL (HA) |
| Redis | Single pod | Small managed instance | ElastiCache / Memorystore |
| Keycloak | Single pod | Small instance | Managed or HA deployment |
| Git remote | GitHub (same) | GitHub (same) | GitHub (same) |
| Worker resources | 1 CPU, 2GB | 2 CPU, 8GB | 4 CPU, 16GB |
| Scanner schedule | Manual / on-demand | Nightly | Nightly + incremental on push |
| Max concurrent CRs | 2–3 | 10–20 | 50+ |

---

## 20. Scaling & Recovery

### 20.1 Scaling Model

One worker pod per CR. The cluster scales by allowing more pods.

| Scale factor | Bottleneck | Solution |
|-------------|-----------|---------|
| Concurrent CRs | Worker pod count | Cluster autoscaler or KEDA (scale on pending Jobs) |
| Pod startup time | Git clone, image pull | Pre-pulled images, shallow clones, image caching |
| LLM API throughput | Token rate limits | Multiple API keys, request queuing, model tiering |
| Redis throughput | Event volume at high concurrency | Redis Cluster for 50+ concurrent CRs |
| PostgreSQL connections | Checkpoint writes | Connection pooling (PgBouncer), managed HA |
| Knowledge Store queries | Embedding search at intake | pgvector indexes, cached landscape snapshots |

**Capacity planning** (single installation, may serve multiple tenants):

| Deployment size | CRs/day | Concurrent workers | Tenants | Dominant cost |
|----------------|---------|-------------------|---------|---------------|
| Small (< 5 CRs/day) | 2–3 | 2–3 | 1 | LLM tokens |
| Medium (5–20/day) | 5–10 | 5–10 | 1–3 | LLM tokens |
| Large (20–100/day) | 20–50 | 20–50 | 3–10 | LLM tokens + compute |
| Enterprise (100+/day) | 50+ | 50+ | 10+ | LLM tokens; Redis Cluster, HA Postgres |

### 20.2 Recovery After Pod Failure

No work is lost:

| What | Where it survives | Recovery |
|------|------------------|---------|
| Pipeline state | PostgreSQL (checkpointed after every node) | New pod resumes from last checkpoint |
| Code artifacts | Git remote (pushed after every stage) | New pod clones from remote branch |
| Events | Redis Streams (persistent) | Dashboard replays from Stream |

K8s Job `backoffLimit: 2` auto-restarts failed workers. Worker entrypoint detects an existing checkpoint and recovers worktrees from the remote branch.

**Checkpoint-and-terminate recovery** (push_and_wait, release gate) uses the same mechanism. The only difference is the termination is intentional (to free compute), not a failure. When the CI webhook or approval arrives, the Controller spawns a new Job that resumes identically to a failure recovery.

### 20.3 What Is Stateless vs. Stateful

| Component | Stateless? | Notes |
|-----------|-----------|-------|
| Controller | ✅ Yes | Any replica handles any request |
| Worker pod | ✅ Logically | Workspace reconstructable from git + checkpoint |
| Scanner | ✅ Yes | Can be re-run anytime |
| PostgreSQL | ❌ Stateful | Pipeline state, knowledge store, audit trail, runtime config, users, tenants, memberships. **Critical.** |
| Knowledge Store | ❌ Stateful (in Postgres) | Rebuildable by re-running Scanner |
| Redis | ⚠️ Semi-stateful | Loss = dashboard dark, interventions delayed. Pipelines continue. |
| Git remote | ❌ Stateful | Primary artifact store |
| Keycloak | ⚠️ Semi-stateful | User directory and SSO sessions only (no roles/groups). Use external IdP or HA deployment. |
