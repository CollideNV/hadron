# Implementation Roadmap & Risks

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 22. Implementation Roadmap

### Phase 1 — Foundation (Weeks 1–2)
- [ ] Project skeleton: LangGraph app, FastAPI controller, bootstrap config loader
- [ ] Runtime config schema in PostgreSQL (tenant-scoped, versioned)
- [ ] Config API (CRUD + history + revert)
- [ ] PipelineState (including cost accumulation), PostgreSQL checkpointer
- [ ] WorktreeManager (clone, worktree, commit, push, recover)
- [ ] Agent backend interface + Claude SDK (with streaming + token usage tracking)
- [ ] Distributed event bus (Redis Streams + Pub/Sub)
- [ ] Distributed intervention manager (Redis)
- [ ] Prompt template system + repo context builder
- [ ] Explicit repo identification (Phase 1)
- [ ] Duplicate CR detection (external ID check)
- [ ] CR lifecycle state model (running → completed / failed / cancelled)
- [ ] Direct API intake endpoint
- [ ] Basic CLI for local testing

### Phase 2 — Core Stages (Weeks 3–5)
- [ ] v1 prompt templates for all agent roles (including Retrospective Agent, Sync Agent, Input Screener)
- [ ] AGENTS.md convention: discovery, parsing, injection
- [ ] Intake node (structured output + source reporting + input risk screening)
- [ ] Multi-repo fan-out / fan-in execution model
- [ ] Behaviour Translation + Verification subgraphs (with cross-repo consistency, spec firewall design)
- [ ] TDD Development subgraph (with intervention checks, per-repo parallelism)
- [ ] Code Review subgraph (per-repo parallelism, cross-repo spec compliance, adversarial Security Reviewer prompt)
- [ ] Diff scope analyser (deterministic pre-pass before Code Review)
- [ ] Conditional edges, feedback loops
- [ ] Push-to-remote after each stage
- [ ] E2E test: single repo, API intake, in-process worker

### Phase 3 — Delivery + CI (Weeks 6–7)
- [ ] self_contained, push_and_forget, push_and_wait strategies
- [ ] Checkpoint-and-terminate for push_and_wait (pod release during CI)
- [ ] CI webhook handler + polling fallback
- [ ] Release gate with checkpoint-and-terminate (pod release during approval wait)
- [ ] Atomic Merge Check (stale approval detection + auto-rebase loop)
- [ ] Release, cleanup nodes
- [ ] Retrospective Agent node (post-CR knowledge distillation → Knowledge Store)
- [ ] Cancel/abort: graceful shutdown + artifact preservation
- [ ] Re-run: from scratch, from checkpoint, from stage
- [ ] Source status reporting at all checkpoints
- [ ] PR description generator (structured body from PipelineState, configurable template)
- [ ] External human review wait (webhook for PR approval events, loop on changes requested)

### Phase 4 — Control Room (Weeks 8–9)
- [ ] SSE event endpoint on controller (with Redis Stream replay)
- [ ] Dashboard: pipeline list, per-repo agent streams, stage progress, running cost
- [ ] Intervention: pause, resume, redirect, skip, abort
- [ ] Circuit breakers with auto-pause
- [ ] Release approval UI (Approver role)
- [ ] Cleanup wizard (post-cancel/abort: branch, PR, source status choices)
- [ ] Re-run UI (from scratch / checkpoint / stage)
- [ ] Multi-repo failure UI (per-repo status, redirect/take-over failing repo, whole-CR decisions)
- [ ] Human take-over + Sync Node (resume-with-validation: diff, spec update, test baseline)
- [ ] Settings UI: config forms for all runtime config sections (Admin role)
- [ ] Config change history and revert UI

### Phase 5 — Authentication, Notifications & Multi-Tenancy (Weeks 10–11)
- [ ] OIDC integration on Controller (JWT validation, identity only)
- [ ] User auto-provisioning on first login (OIDC subject → pipeline user record)
- [ ] Internal authorization: users, tenants, tenant_memberships tables
- [ ] Tenant management API (create, list, invite members, assign roles)
- [ ] Tenant switcher in dashboard (X-Tenant-ID header)
- [ ] Role-based access on all API endpoints + SSE (per-tenant roles from DB)
- [ ] Dashboard login flow (Authorization Code + PKCE)
- [ ] Service account tokens for CI webhooks + source connectors (tenant-scoped)
- [ ] Super-admin role + cross-tenant views
- [ ] Audit trail (all actions with user + tenant context)
- [ ] Notification channel adapters (Slack, Teams, email, GitHub, webhook)
- [ ] Notification routing + user subscription model
- [ ] Source issue change detection (update, close, delete → notify subscribers)
- [ ] Per-tenant LLM API key support (optional)

### Phase 6 — Kubernetes Deployment (Weeks 11–12)
- [ ] Controller Deployment + Service + Ingress manifests
- [ ] Worker Job template + stage-aware NetworkPolicy (egress-locked TDD → full egress after review)
- [ ] Ephemeral test infrastructure: sidecar container injection from repo config / test-compose.yaml
- [ ] Dynamic worker sizing: Job Spawner calculates pod resources from repo count × weight
- [ ] Agent command boundaries: non-root user, seccomp profile, filesystem permissions, command allowlist
- [ ] Git authentication: GitHub App token generation, per-tenant credential injection
- [ ] Pluggable secret provider integration (K8s Secrets, Vault, AWS SM, etc.)
- [ ] Job spawner with concurrency limiting
- [ ] Pod failure recovery (checkpoint resume + worktree recovery)
- [ ] Monorepo support (path_prefix, directory-scoped agents)
- [ ] Helm chart or Kustomize base
- [ ] Local dev setup (kind cluster)
- [ ] Jira + GitHub Issues connectors
- [ ] OpenCode + Codex agent backends
- [ ] E2E: multi-repo, mixed delivery, pod failure recovery

### Phase 7 — Production (Week 13)
- [ ] System observability: Prometheus metrics, Grafana dashboards
- [ ] Data retention CronJob (DB pruning, stale branch cleanup, configurable per tenant)
- [ ] Structured logging + log aggregation
- [ ] Alerting rules (Alertmanager → notification channels)
- [ ] Deploy to target cloud cluster
- [ ] Load test with 10+ concurrent CRs (including multi-repo CRs)
- [ ] Cluster autoscaler tuning
- [ ] Prompt A/B testing infrastructure
- [ ] Documentation, runbooks, onboarding
- [ ] AGENTS.md templates for common tech stacks
- [ ] First real change request through the pipeline

### Phase 8 — Landscape Intelligence (Weeks 14–17, Post-Launch)
- [ ] Landscape Scanner process (nightly CronJob + incremental)
- [ ] Knowledge Store schema (PostgreSQL + pgvector)
- [ ] LLM-assisted repo identification (Phase 2)
- [ ] Human confirmation UI in dashboard
- [ ] Feedback loop (corrections → improved suggestions)
- [ ] Auto-confirm for high-confidence suggestions (Phase 3)
- [ ] Landscape health + identification accuracy dashboards

---

## 24. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Agent loops indefinitely | Circuit breakers → auto-pause → human decides |
| Agent going wrong direction | Real-time events in control room; redirect early |
| Incorrect code passes review | TDD + multi-reviewer + CI + human gate (5 layers) |
| Token costs spiral | Per-call tracking, running total in dashboard, auto-pause at threshold |
| Cross-repo conflicts | Consistency checker + shared worktree visibility + CI integration tests |
| Cross-repo dependency during TDD | Agents share filesystem — can read sibling repos for API contracts |
| CI webhook never arrives | Controller polls CI API as fallback after timeout |
| Worker pod dies mid-pipeline | K8s Job restart; resume from PostgreSQL checkpoint + git remote |
| Worker pod idle during CI wait | Checkpoint-and-terminate releases pod; new pod resumes on webhook |
| Redis goes down | Pipelines continue; dashboard temporarily dark |
| PostgreSQL goes down | Pipeline halts; managed HA Postgres recommended |
| Secrets leaked in worker pod | K8s Secrets + NetworkPolicy; pluggable vault providers |
| Repo-specific test secrets mismanaged | Pluggable provider (Vault, AWS SM, etc.); secrets injected at pod creation, not in config |
| Prompts produce low-quality code | Metrics-driven iteration; A/B testing over time |
| Config change breaks running CRs | Config snapshot taken at CR start; running CRs unaffected by changes |
| Config change has unintended effect | Full audit trail with before/after; one-click revert to any previous version |
| Context window overflow | Static context capped; agents use tools for dynamic discovery |
| Full suite surfaces pre-existing test failures | Diff against main's test results; exclude pre-existing failures from pass/fail; report them in review summary |
| Landscape knowledge goes stale | Nightly + incremental scans; human corrections trigger refresh |
| LLM suggests wrong repos | Human confirmation in Phase 2; feedback improves accuracy |
| Unauthorised release approval | OIDC + Approver role required; audit trail records who approved |
| Stale approval: main moved after approval | Atomic Merge Check auto-rebases and re-tests before merge. No manual re-approval unless tests fail |
| AI-generated code exfiltrates data via network | Egress-locked during TDD — only LLM APIs and git allowed. Full egress after Security Review pass |
| Test infrastructure leaks to shared staging | Infrastructure-as-a-Sidecar enforced — only ephemeral pod sidecars. NetworkPolicy blocks external DB access |
| Small CRs waste cluster resources | Dynamic worker sizing — pod resources scale with complexity. 1-repo CR gets a small pod |
| Human manually breaks code, AI continues blindly | Sync Node diffs changes, updates specs, re-runs full test suite before AI resumes. Pipeline re-pauses if tests fail |
| Retrospective Agent hallucinates learnings | Non-blocking (skip on failure); learnings are additive context, not hard rules. Admins can prune via Knowledge Store |
| Same mistake repeated across CRs | Retrospective learnings injected into Layer 2 context for future CRs touching the same repo |
| PR opened with no useful description | PR body is a structured first-class output generated from PipelineState. Template configurable per tenant |
| Human reviewer blocks PR indefinitely | Configurable timeout (default 48h). Pipeline pauses and notifies operator after timeout |
| Git credentials leak from worker pod | Short-lived tokens (GitHub App: 1h expiry). Credentials injected at pod creation, scoped to tenant's repos. Agents never see raw tokens |
| Tenant A pushes to Tenant B's repo | Git credentials are per-tenant, scoped to that tenant's repos. Cross-tenant push is impossible at the credential level |
| Agent exfiltrates secrets via shell | Agents run as non-root with filtered env vars. LLM API keys not in agent's shell scope. Seccomp + filesystem permissions + egress lock stack |
| Agent runs destructive commands | Command allowlist enforced by agent SDK. Filesystem permissions block writes outside workspace. Non-root can't modify system |
| Database grows unbounded | Retention CronJob enforces configurable policies. Event detail pruned, summaries preserved. Compliance mode available |
| Stale branches accumulate on git remotes | Cleanup CronJob prunes branches for failed/cancelled CRs older than retention period. Dashboard warns before deletion |
| Prompt injection via CR description (low sophistication) | Input Screener flags suspicious patterns at intake. High-risk detections auto-pause for operator review before agents see the input |
| Prompt injection via CR description (medium sophistication) | Behaviour spec firewall: code agents work from specs, not raw CR text. Adversarial Security Reviewer flags code that doesn't match specs |
| Prompt injection via CR description (high sophistication) | Diff scope analysis catches out-of-scope changes. Runtime containment limits blast radius. Optional human PR review as final check. Transparent about limits — see §12.9 |
| Malicious code written that passes AI review | Egress lock prevents exfiltration during TDD. Agent command boundaries prevent secret access. Human PR review catches what AI misses for critical repos |
| Security Reviewer itself is prompt-injected | Reviewer context is isolated: receives diff + specs + risk flags. CR description is marked "untrusted." Different system prompt than code-writing agents |
| Duplicate CR processed | External ID dedup check before spawning worker |
| Tenant data leaks across tenants | Tenant ID on every DB row + every Redis key prefix; Controller scopes all queries by active tenant from X-Tenant-ID header; user's tenant membership verified on every request |
| Noisy neighbour (one tenant's CRs starve others) | Per-tenant resource quotas on K8s (optional); per-tenant concurrency limits in config |
| Nobody notices release gate waiting | Pluggable notifications; Approver role gets auto-notified on preferred channel |
| Monorepo: agents step on each other | Agents scoped to application directories; shared visibility prevents conflicts |
| Parallel agents exhaust pod resources | Resource limits per agent; fan-out degree bounded by pod CPU/memory |
| Primary LLM provider goes down | Provider chain fails over to next provider automatically; retry with backoff first |
| All LLM providers down simultaneously | Pipeline pauses affected CRs; alerts operator; resumes when any provider recovers |
| Rate limits hit across concurrent CRs | Shared token bucket per API key; proactive throttling before hitting 429s |
| Fallback provider produces lower quality | Prompt variants per provider; quality metrics tracked per provider; operator can force primary-only for critical CRs |
| Provider cost varies after failover | Cost tracking uses actual model pricing regardless of which provider handled the call |
| Concurrent CRs conflict on same repo | Rebase before delivery catches conflicts early; Merge Conflict Agent resolves automatically; human take-over for complex cases |
| Merge conflict resolution introduces regression | Full test re-run after resolution; failure loops back to TDD Development |
| CR cancelled but artifacts left behind | Cleanup wizard guides operator; can be revisited later. Stale branches visible in dashboard |
| Source issue changed mid-pipeline | Substantive changes (description, criteria) auto-pause pipeline with decision screen. Non-substantive changes notify only |
| Failed CR re-run conflicts with old branch | Re-run uses new branch suffix (`-r2`); old artifacts preserved for reference |
| Multi-repo partial failure blocks release | CR is atomic — entire CR pauses. Human redirects or takes over the failing repo, or retries/fails the whole CR |

---

*Version 5.0 — February 2026*
