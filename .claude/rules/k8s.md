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
