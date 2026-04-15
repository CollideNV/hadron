---
paths:
  - "k8s/**/*.yaml"
  - "k8s/**/*.yml"
---

# Kubernetes Conventions

- Base manifests in `k8s/base/`, local overlay in `k8s/local/`
- Five process types: Dashboard API (always-on, 1 replica), Orchestrator (KEDA-managed, 0→N replicas), SSE Gateway (always-on, ~64Mi), Worker (ephemeral Job, one per repo per CR), Scanner (CronJob)
- Same Docker image for Dashboard, Orchestrator, and Gateway — different entrypoint commands
- Workers checkpoint to PostgreSQL and terminate during CI waits — new pod resumes from checkpoint
- Orchestrator coordinates release gate across multi-repo CRs; only orchestrator SA has job-manager RBAC
- Gateway proxies CI webhooks to orchestrator (not dashboard)
- Observability: ConfigMap includes `HADRON_LOG_FORMAT=json`, `HADRON_OTEL_ENABLED`, `HADRON_OTLP_ENDPOINT`
- Dashboard and Orchestrator pods have Prometheus scrape annotations (`/metrics` on port 8000/8002)
- Trace context propagated orchestrator → worker via `TRACEPARENT` env var in Job spec
