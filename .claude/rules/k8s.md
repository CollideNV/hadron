---
paths:
  - "k8s/**/*.yaml"
  - "k8s/**/*.yml"
---

# Kubernetes Conventions

- Base manifests in `k8s/base/`, local overlay in `k8s/local/`
- Three process types: Controller (Deployment, 2+ replicas), Worker (ephemeral Job, one per repo per CR), Scanner (CronJob)
- Workers checkpoint to PostgreSQL and terminate during CI waits — new pod resumes from checkpoint
- Controller coordinates release gate across multi-repo CRs
- Observability: ConfigMap includes `HADRON_LOG_FORMAT=json`, `HADRON_OTEL_ENABLED`, `HADRON_OTLP_ENDPOINT`
- Controller pod has Prometheus scrape annotations (`/metrics` on port 8000)
- Trace context propagated controller → worker via `TRACEPARENT` env var in Job spec
