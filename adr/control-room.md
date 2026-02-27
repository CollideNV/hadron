# Control Room, Cost Tracking, Notifications & Observability

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 14. Control Room

### 14.1 Observability Levels

| Level | What you see | Source |
|-------|-------------|--------|
| **Pipeline** | Which graph node is executing | LangGraph state transitions |
| **Subgraph** | Which agent, what iteration | Subgraph node events |
| **Agent** | Tool calls, file edits, reasoning, test results | Agent backend `stream()` |

All three are essential. Level 1 alone just says "TDD for 8 minutes" — you need Level 3 to know if the agent is stuck.

### 14.2 Event System

Events are typed (pipeline started/completed/failed, stage entered/completed/looped, agent started/completed/thinking/tool call/file changed/test run/error, human waiting/intervened, source reported). Every event carries: CR ID, event type, timestamp, stage, repo, agent role, iteration numbers, and detail payload.

### 14.3 Distributed Event Bus — Redis Streams

Workers emit events to Redis. The Controller subscribes and fans out to dashboard clients via **Server-Sent Events (SSE)**.

- **Redis Streams** (per CR): Ordered, persistent event log. Supports replay for late-joining dashboards.
- **Redis Pub/Sub** (per CR): Real-time notification channel for live subscribers.
- **SSE endpoint**: `GET /api/events/stream?cr={id}`. The Controller subscribes to the relevant Redis Pub/Sub channel and pushes events to the client over SSE. Each event includes an `id` field (Redis Stream offset).
- **Auto-reconnect and replay**: When an SSE connection drops (client network, rolling update, pod restart), the browser's `EventSource` API reconnects automatically, sending the `Last-Event-ID` header. The Controller replays missed events from the Redis Stream, then switches to live Pub/Sub — no gaps, no duplicates.

**Why SSE instead of WebSocket:** The event stream is one-directional (server → client). Intervention actions (pause, redirect, skip, abort) go through the REST API, not the event channel. SSE is simpler (plain HTTP, no connection upgrade, no sticky sessions), auto-reconnects natively, and works through every proxy, CDN, and load balancer without special configuration. This makes rolling updates trivial — old pod drains, SSE drops, client reconnects to new pod automatically.

### 14.4 Intervention System

The dashboard writes intervention requests to Redis. Worker pods poll for interventions between agent calls (atomic get-and-delete).

| Action | What happens | Who can do it |
|--------|-------------|--------------|
| **Pause** | Worker blocks until resume signal | Operator, Approver, Admin |
| **Resume** | Paused worker continues | Operator, Approver, Admin |
| **Redirect** | Agent receives new instructions (highest priority in next iteration) | Operator, Approver, Admin |
| **Skip stage** | Pipeline advances to next node | Operator, Approver, Admin |
| **Abort** | Pipeline terminates, reports failure to source | Operator, Approver, Admin |
| **Take over** | Human works on the feature branch directly (via git clone or kubectl exec into pod) | Operator, Approver, Admin |
| **Approve release** | Release gate passes | Approver, Admin only |

### 14.5 CI Result Handling (push_and_wait)

For `push_and_wait` delivery, the worker pod terminates after pushing PRs and triggering CI — no resources are wasted while waiting. CI results arrive via two mechanisms:

- **Webhook (primary):** External CI sends results to the Controller. Partial results accumulate in Redis (hash per CR, keyed by repo). When all expected repos have reported, the Controller spawns a new worker pod that resumes from the checkpoint.
- **Polling (fallback):** If no webhook arrives within the configured timeout, the Controller spawns a lightweight worker to poll the CI system's API for status. This handles cases where webhooks are misconfigured or lost.

The new worker pod recovers the worktree from the git remote branch and continues the pipeline from where it left off. If CI failed, it loops back to TDD Development with the failure logs as context.

### 14.6 Circuit Breakers

| Condition | Action |
|-----------|--------|
| Verification loop > 2 | Auto-pause + alert |
| Dev ↔ review loop > 3 | Auto-pause + alert |
| Dev ↔ CI loop > 3 | Auto-pause + alert |
| Cost > threshold | Auto-pause + alert |
| Agent timeout (30 min) | Retry once, then pause |
| No events for 5 min | Alert: agent may be stuck |

Circuit breakers **pause** (not fail, not abort). The operator sees the failure decision screen (§15.3) and chooses what to do next.

### 14.7 Dashboard

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CR-142: Add password reset flow                          [RUNNING ●]  │
│  Source: Jira PROJ-1234 │ Worker: hadron-cr-142-xxxxx │ Cost: $3.20  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ✅ Intake ── ✅ Repo ID ── ✅ Worktrees ── ✅ Behaviour ── ● TDD Dev │
│                                                                         │
│  ┌─ auth-service ─────────────────────┐  ┌─ api-gateway ────────────┐  │
│  │  Code Writer (iter 2/5)       [●]  │  │  Code Writer (iter 1/5) [●] │
│  │                                    │  │                            │ │
│  │  ► Edited src/auth/reset.ts        │  │  ► Reading routes/auth.ts  │ │
│  │  ► npm test → ✅ 14 ❌ 2          │  │  ► Adding /auth/reset route │ │
│  │  ► Thinking: "Two tests..."        │  │  ► Referencing auth-service │ │
│  └────────────────────────────────────┘  └────────────────────────────┘ │
│                                                                         │
│  [⏸ Pause]  [💬 Redirect]  [⏭ Skip Stage]  [🛑 Abort]  [👁 Follow]   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 16. Cost Tracking

### 16.1 What's Tracked

Every CR accumulates cost from multiple sources:

| Cost source | How it's measured | Granularity |
|------------|------------------|-------------|
| LLM tokens (input + output) | Token counts × model pricing | Per agent call, per stage, per repo |
| LLM tool use | Included in token counts | Per agent call |
| Compute (worker pod) | Pod uptime × resource allocation | Per CR (pod lifetime minus any checkpoint-and-terminate gaps) |
| Compute (Scanner) | Amortised across all CRs | System-level, not per-CR |

Token costs dominate. A typical CR costs $2–15 in tokens, $0.10–1.00 in compute.

### 16.2 Real-Time Cost Accumulation

Each agent call returns token usage (input tokens, output tokens, model used). The worker accumulates these into the pipeline state as they happen. Cost is calculated using the provider's pricing table (maintained in config, updated when model pricing changes).

The dashboard shows running cost per CR. Circuit breakers reference the accumulated cost to trigger auto-pause when the threshold is exceeded (see §14.6).

### 16.3 Cost Reporting

At CR completion, the full cost breakdown is:

- Stored in the audit trail (PostgreSQL)
- Included in the release gate summary (so the Approver sees what this CR cost)
- Reported to the source system (e.g. Jira comment: "Pipeline completed. Cost: $4.20 (tokens: $3.80, compute: $0.40)")
- Available via system-level dashboards for aggregate analysis (cost per CR, cost per repo, cost trends)

---

## 17. Notifications

### 17.1 Design Principle

Notifications are pluggable — the pipeline can notify through any channel. People opt in to what they care about, either by subscribing to specific CRs or by role.

### 17.2 Notification Channels

| Channel | Integration | Use case |
|---------|------------|---------|
| Slack | Webhook or bot (Slack API) | Team channels, DMs to approvers |
| Microsoft Teams | Incoming webhook or bot | Same as Slack for Teams-based orgs |
| Email | SMTP or provider API (SendGrid, SES) | Formal notifications, audit records |
| GitHub | PR comments, review requests, issue comments | Developer-centric, lives in the PR |
| Dashboard | In-app notifications + SSE push | Always available, real-time |
| Custom webhook | HTTP POST to any URL | Integration with other systems |

Multiple channels can be active simultaneously. Channel configuration is at the system level; subscription preferences are per user.

### 17.3 Notification Events

| Event | Who gets notified | Priority |
|-------|------------------|----------|
| CR pipeline started | Subscribers of the CR | Low |
| Circuit breaker triggered (auto-pause) | Operators | High |
| Release gate waiting for approval | Approvers | High |
| Release approved / rejected | CR subscribers | Medium |
| Pipeline completed | CR subscribers + source system | Medium |
| Pipeline failed (after max retries) | Operators + CR subscribers | High |
| Agent stuck (no events for 5+ min) | Operators | Medium |
| Source issue description/criteria updated | CR subscribers + operators (auto-pause) | High |
| Source issue closed while CR running | CR subscribers + operators | High |
| CR cancelled — cleanup wizard pending | CR subscribers | Medium |
| Multi-repo: one repo failing, CR paused | Operators + CR subscribers | High |

### 17.4 Subscription Model

Users can subscribe to notifications through:

- **Following a CR** in the dashboard (button to follow/unfollow)
- **Role-based defaults:** Approvers automatically get release gate notifications. Operators get circuit breaker alerts.
- **Source system integration:** If you're assigned to the Jira issue or mentioned on the GitHub issue, you receive pipeline notifications.
- **Channel-level config:** "Send all circuit breaker alerts to `#hadron-alerts` in Slack."

---

## 18. System Observability

### 18.1 Distinction from Control Room

The Control Room (§14) provides **per-CR observability** — watching individual pipeline runs in real time. System observability provides **aggregate metrics and operational health** across all CRs, all workers, and all infrastructure.

### 18.2 Metrics (Prometheus)

Standard Prometheus metrics exported by the Controller and Workers:

| Category | Metrics |
|----------|---------|
| **Pipeline throughput** | CRs started/completed/failed per hour, CRs in-flight |
| **Stage duration** | Time per stage (p50, p95, p99), broken down by repo |
| **Loop frequency** | Verification loops, review loops, CI loops per CR |
| **Agent performance** | Tokens per agent call, calls per stage, first-pass rates |
| **LLM providers** | Success rate per provider, latency (p50/p95), error rate, failover frequency, rate limit headroom |
| **Cost** | Cost per CR (p50, p95), total daily/weekly cost, cost by model/provider |
| **Infrastructure** | Worker pod count, pod startup latency, Redis/Postgres health |
| **Knowledge Store** | Repo identification accuracy, scan freshness, false negative rate |
| **Prompt quality** | First-pass verification/review/CI rates per prompt version |

### 18.3 Dashboards (Grafana)

Pre-built Grafana dashboards for:

- **Operations:** CRs in-flight, pipeline success rate, average duration, cost trend
- **Agent Quality:** First-pass rates, loop counts, prompt version comparison (A/B testing)
- **Infrastructure:** Pod scaling, Redis/Postgres load, LLM API latency and error rates
- **Landscape Health:** Scan success rate, knowledge freshness, identification accuracy

### 18.4 Logging

Structured JSON logs from all processes (Controller, Workers, Scanner). Log aggregation via the cluster's standard logging stack (e.g. Loki, ELK, CloudWatch Logs). Every log entry carries the CR ID for correlation.

### 18.5 Alerting

Alerts route through Prometheus Alertmanager (or cloud-native equivalents) to the notification channels defined in §17:

| Alert | Condition | Severity |
|-------|-----------|----------|
| Pipeline failure rate spike | >20% failure rate in last hour | Critical |
| Worker pod backlog | >N CRs waiting for pods for >10 min | Warning |
| LLM API errors | >5% error rate to any provider | Critical |
| LLM provider failover active | Primary provider degraded, calls routing to fallback | Warning |
| Cost anomaly | Single CR exceeds 3× median cost | Warning |
| Knowledge Store stale | Any repo not scanned in >7 days | Warning |
| PostgreSQL/Redis down | Health check failure | Critical |

### 18.6 Data Retention

The pipeline generates data continuously — event streams, audit records, cost data, retrospective learnings, and git branches. Without a retention policy, storage grows unbounded. All retention periods are configurable per tenant.

**PostgreSQL:**

| Data | Default retention | Cleanup mechanism |
|------|------------------|-------------------|
| CR records (completed/failed) | 1 year | Archived to cold storage, then deleted. Summary preserved indefinitely. |
| Event streams (per-CR events) | 90 days | Purge events for CRs older than retention. CR summary remains. |
| Audit trail | 2 years (or per compliance requirement) | Archived to cold storage, then deleted. |
| Cost data (per-call detail) | 6 months | Aggregated into monthly summaries, detail deleted. |
| Cost summaries (monthly) | Indefinite | Small — no cleanup needed. |
| Config version history | 1 year | Old versions pruned. Current + last 50 kept regardless. |
| Retrospective learnings | Indefinite (curated) | Admins can prune stale learnings via Knowledge Store UI. |
| Knowledge Store profiles | Indefinite (overwritten on scan) | Only latest profile per repo kept; scan history pruned at 90 days. |

**Redis:**

| Data | Default retention | Cleanup mechanism |
|------|------------------|-------------------|
| Event streams (live CRs) | Duration of CR run | Streams deleted when CR completes + retention buffer (7 days). |
| Pub/Sub channels | Ephemeral | Auto-expire when no subscribers. |
| Rate limit state | Ephemeral | TTL-based keys, expire after health window. |

**Git remotes (branches):**

| Data | Default retention | Cleanup mechanism |
|------|------------------|-------------------|
| Merged feature branches (`ai/cr-{id}`) | Deleted after merge (configurable: keep for N days) | Release node deletes branch post-merge, or cleanup CronJob for aged branches. |
| Unmerged branches (failed/cancelled CRs) | 90 days | Cleanup CronJob lists stale `ai/*` branches, cross-references with CR status. Branches for failed/cancelled CRs older than retention are deleted. Dashboard warns before deletion. |
| Open PRs for failed/cancelled CRs | 90 days | Same CronJob closes stale PRs with a comment linking to the CR record. |

**Cleanup CronJob:** A scheduled job runs daily (configurable), enforcing retention policies. It logs every deletion to the audit trail. Operators can preview what would be cleaned up via the dashboard before enabling automatic cleanup. Manual cleanup is always available via the dashboard for individual CRs.

**Compliance mode:** For regulated environments, retention periods can be set to "indefinite" and cleanup disabled. An export API allows archiving data to external storage (S3, Azure Blob) before deletion.
