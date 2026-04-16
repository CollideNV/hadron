---
paths:
  - "k8s/**/*.yaml"
  - "k8s/**/*.yml"
---

# Kubernetes Conventions

- Base manifests in `k8s/base/`, local overlay in `k8s/local/`
- Seven process types: Frontend (nginx, always-on, ~32Mi, port 8080), Dashboard API (always-on, 1 replica), Orchestrator (KEDA-managed, 0→N replicas), SSE Gateway (always-on, ~64Mi), Worker (ephemeral Job, one per repo per CR), E2E Runner (persistent Job, one per CR-repo when E2E detected, ttl 1h), Scanner (CronJob)
- Same Docker image for Dashboard, Orchestrator, and Gateway — different entrypoint commands. Frontend uses its own nginx image (`hadron-frontend:latest`) and is the single browser-facing origin — it reverse-proxies `/api/events/*` to the gateway, mutation paths to the orchestrator, everything else to the dashboard
- Workers checkpoint to PostgreSQL and terminate during CI waits — new pod resumes from checkpoint
- Orchestrator coordinates release gate across multi-repo CRs; only orchestrator SA has job-manager RBAC
- Gateway proxies CI webhooks to orchestrator (not dashboard)
- Observability: ConfigMap includes `HADRON_LOG_FORMAT=json`, `HADRON_OTEL_ENABLED`, `HADRON_OTLP_ENDPOINT`
- Dashboard and Orchestrator pods have Prometheus scrape annotations (`/metrics` on port 8000/8002)
- Trace context propagated orchestrator → worker via `TRACEPARENT` env var in Job spec
- E2E Runner pods are labeled `app=hadron-e2e-runner,cr-id=<id>,repo-name=<repo>`; worker spawns at Worktree Setup, sends Redis-dispatched tarballs per iteration, sends sentinel at Release; polyglot image bundles Node (Playwright base), Python, JDK, Maven, Gradle; runtime `npx playwright install chromium` matches target repo's pinned version
