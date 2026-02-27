# Configuration

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 21. Configuration

### 21.1 Design Principle

Configuration lives in the **database**, not in files. All pipeline settings — repos, agent chains, circuit breaker thresholds, notification routing, cost limits — are editable on the fly through the dashboard or API without redeployment. Changes take effect immediately for new CRs. Running CRs continue with their snapshot (see §21.4).

Only a minimal **bootstrap config** exists as a file or environment variables — the things the system needs to connect to its infrastructure and start up. Everything else is database-backed, tenant-scoped, and version-tracked.

### 21.2 Bootstrap Config (File / Environment)

The Controller needs these to start. They cannot be in the database because the database connection is one of them:

```yaml
# bootstrap.yaml — the only config file
infrastructure:
  postgres_url: "${POSTGRES_URL}"
  redis_url: "${REDIS_URL}"
  keycloak_url: "${KEYCLOAK_URL}"

auth:
  provider: "keycloak"
  issuer_url: "https://keycloak.yourcompany.com/realms/hadron"
  client_id: "hadron-dashboard"
  api_client_id: "hadron-api"
  api_client_secret: "${OIDC_API_CLIENT_SECRET}"

multi_tenancy:
  enabled: true

controller:
  image: "${REGISTRY}/hadron-controller:latest"
  replicas: 2

worker:
  image: "${REGISTRY}/hadron-worker:latest"
  sizing:                                     # base resources; scaled by repo count × weight
    small:  { cpu: "1",  memory: "4Gi"  }     # 1 repo
    medium: { cpu: "2",  memory: "8Gi"  }     # 2-3 repos
    large:  { cpu: "4",  memory: "16Gi" }     # 4-6 repos
    xl:     { cpu: "6",  memory: "24Gi" }     # 7+ repos

scanner:
  image: "${REGISTRY}/hadron-scanner:latest"
```

This is small, stable, and changes only when infrastructure changes (new database, new IdP, different K8s resources). Deployed via Helm values, ConfigMap, or environment variables.

### 21.3 Runtime Config (Database)

Everything else lives in PostgreSQL, scoped per tenant, editable via the dashboard (Admin role) or the API (`PUT /api/config/{section}`). The dashboard provides forms for each config section — no YAML editing required.

| Config section | What it controls | Editable by | Tenant-scoped |
|---------------|-----------------|-------------|:---:|
| **Pipeline defaults** | Max loops, max time, max cost, concurrency | Admin | ✅ |
| **Repos & applications** | Registered repos, URLs, branches, domains, tech stack, test commands, delivery strategy, secret refs, monorepo paths | Admin | ✅ |
| **Agent providers** | API keys, models, retry policies, provider chains per role, health thresholds | Admin | ✅ |
| **Source connectors** | Jira/GitHub/ADO/Slack config, poll intervals, status mappings, substantive change fields | Admin | ✅ |
| **Repo identification** | Phase (1/2/3), component maps, auto-confirm threshold | Admin | ✅ |
| **Notifications** | Channels (Slack, Teams, email, etc.), routing rules, subscription defaults | Admin | ✅ |
| **Cost tracking** | Max per CR, alert thresholds, pricing overrides | Admin | ✅ |
| **Secret providers** | Default provider, Vault/AWS/Azure/GCP connection details | Admin | ✅ |
| **Prompts** | Active version per role, A/B test splits, static context limits | Admin | ✅ |
| **Circuit breakers** | Loop limits, cost thresholds, timeout values, stale event alert window | Admin | ✅ |
| **Scanner** | Schedule, incremental triggers, embedding model | Admin | ✅ |
| **Landscape overrides** | Manual repo descriptions, domain assignments, dependency overrides | Admin | ✅ |
| **Security** | Input screening, spec firewall, adversarial review, diff scope analysis settings (§12.10) | Admin | ✅ |
| **Data retention** | Retention periods per data type, cleanup scheduling, compliance mode | Admin | ✅ |

**Example: changing a circuit breaker threshold.** Admin opens the dashboard → Settings → Circuit Breakers → changes "max review-dev loops" from 3 to 5 → saves. The change writes to PostgreSQL immediately. The next CR to hit the review stage uses the new limit. No restart, no redeploy.

**Example: adding a new repo.** Admin opens Settings → Repos → Add → fills in the form (URL, branch, domain, test command, delivery strategy) → saves. The Knowledge Store queues a scan. The repo is available for the next CR.

### 21.4 Config Snapshots for Running CRs

A running CR should not be affected by config changes mid-flight. When a CR starts, the worker takes a **snapshot** of the relevant configuration (pipeline defaults, repo config, agent chains, circuit breaker thresholds) and stores it in the PipelineState. The CR runs against this snapshot for its entire lifetime.

This means:
- Changing the max review loops from 3 to 5 doesn't affect CRs already in review
- Adding a new provider to the chain doesn't affect CRs already running
- Changing a repo's delivery strategy doesn't switch a CR that's already mid-delivery

New CRs pick up the latest config. This is the same principle as the CR description snapshot (§15.5) — the pipeline works from a known, stable state.

### 21.5 Config Versioning & Audit

Every config change is recorded in the audit trail (§3.7):

| What's recorded | Details |
|----------------|---------|
| Who changed it | User ID from JWT |
| What changed | Section, field, before/after values |
| When | Timestamp |
| Tenant | Which tenant's config was modified |

The dashboard shows config change history. Admins can view previous versions and revert if needed — revert is just a new change that restores old values.

### 21.6 Config API

All runtime config is accessible via REST:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/config` | GET | All config sections for current tenant |
| `/api/config/{section}` | GET | Specific section (e.g. `repos`, `agents`, `notifications`) |
| `/api/config/{section}` | PUT | Update a section. Validates before saving. |
| `/api/config/{section}/history` | GET | Change history for a section |
| `/api/config/{section}/revert/{version}` | POST | Revert to a previous version |

All endpoints require the Admin role and are tenant-scoped.

### 21.7 Reference: Runtime Config Structure

The examples below show the logical structure of each config section as it exists in the database. The dashboard renders these as forms; the API accepts/returns them as JSON.

**Pipeline defaults:**
```yaml
pipeline:
  max_concurrent_crs: 20
  max_verification_loops: 2
  max_review_dev_loops: 3
  max_ci_dev_loops: 3
  max_total_time_hours: 4
  max_cost_per_cr_usd: 50.00
```

**Repos** (one entry per repo/application):
```yaml
repos:
  - name: "auth-service"
    url: "git@github.com:org/auth-service.git"
    base_branch: "main"
    description: "Handles authentication, sessions, password reset, OAuth2, JWT."
    domain: "identity"
    owns: ["authentication", "sessions", "password-reset", "oauth2"]
    api_surface: ["POST /auth/login", "POST /auth/reset", "DELETE /auth/session/{id}"]
    depends_on: ["email-service", "user-store"]
    tech_stack: "TypeScript, Express, PostgreSQL, Jest"
    behaviour_path: "specs/behaviour/"
    test_command: "npm test"
    test_secrets:
      provider: "vault"
      path: "secret/data/auth-service/test"
    delivery:
      strategy: "push_and_wait"
      push: { mode: "pull_request", labels: ["ai-generated"] }
      ci_integration: { wait_for: "all_checks", timeout_minutes: 30, on_failure: "loop_to_dev" }
      release: { mode: "merge_pr", merge_strategy: "squash" }

  # Monorepo application
  - name: "billing-api"
    url: "git@github.com:org/platform-monorepo.git"
    base_branch: "main"
    path_prefix: "services/billing-api"
    description: "Billing API for subscription management and invoicing."
    domain: "payments"
```

**Agent providers & chains:**
```yaml
agents:
  providers:
    anthropic:
      api_key: "${ANTHROPIC_API_KEY}"
      models: { default: "claude-sonnet-4-5-20250929", premium: "claude-opus-4-6" }
      retry: { max_retries: 3, initial_backoff_seconds: 5, backoff_multiplier: 2, max_backoff_seconds: 60, timeout_seconds: 120 }
    openai:
      api_key: "${OPENAI_API_KEY}"
      models: { default: "gpt-4.1" }
      retry: { max_retries: 3, initial_backoff_seconds: 5 }
    google:
      api_key: "${GOOGLE_API_KEY}"
      models: { default: "gemini-2.5-pro", cheap: "gemini-2.5-flash" }
  default_chain: ["anthropic", "openai"]
  roles:
    spec_writer:          { chain: ["anthropic"], model_tier: "premium" }
    code_writer:          { chain: ["anthropic", "openai"] }
    merge_conflict_agent: { chain: ["anthropic"], model_tier: "premium" }
  health:
    degraded_error_rate_pct: 20
    health_window_minutes: 5
    proactive_failover: true
```

**Source connectors, notifications, cost, secrets, prompts, scanner, repo identification:**
```yaml
intake:
  source: "jira"
  jira:
    server: "https://yourcompany.atlassian.net"
    email: "bot@yourcompany.com"
    api_token: "${JIRA_API_TOKEN}"
    jql_filter: 'project = PROJ AND label = "ai-ready"'
    poll_interval_seconds: 30
    substantive_fields: ["description", "acceptance_criteria"]

notifications:
  channels:
    - type: "slack"
      webhook_url: "${SLACK_WEBHOOK_URL}"
      default_channel: "#hadron-alerts"
    - type: "github"
      enabled: true
  routing:
    circuit_breaker: ["slack"]
    release_gate: ["slack", "github"]

cost:
  max_per_cr_usd: 50.00
  alert_threshold_pct: 80

secrets:
  default_provider: "k8s"
  vault: { address: "${VAULT_ADDR}", auth_method: "kubernetes" }

prompts:
  templates_dir: "prompts/"
  max_static_context_tokens: 12000
  repo_context:
    convention_files: ["AGENTS.md", "CLAUDE.md", "COPILOT.md", "CONTRIBUTING.md"]

repo_identification:
  phase: 1
  auto_confirm_threshold: 0.9
  min_history_for_auto: 50

landscape_scanner:
  nightly_schedule: "0 2 * * *"
  incremental_on_push: true

control_room:
  event_retention_hours: 168

security:
  input_screening:
    enabled: true
    auto_pause_on_high_risk: true
  spec_firewall:
    strict_mode: true
  adversarial_review:
    enabled: true
    cr_description_in_review: "marked"
  diff_scope_analysis:
    enabled: true
    flag_infra_changes: true
    flag_unknown_endpoints: true
    flag_new_dependencies: true
  require_human_review_repos: []

data_retention:
  cr_records_days: 365
  event_streams_days: 90
  audit_trail_days: 730
  cost_detail_days: 180
  stale_branches_days: 90
  cleanup_enabled: true
  compliance_mode: false
```
