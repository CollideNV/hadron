# Execution Sandboxing — Kubernetes Pods

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 7. Execution Sandboxing — Kubernetes Pods

### 7.1 The Pod IS the Sandbox

Each change request runs in its own ephemeral K8s pod. The pod provides all isolation — no Docker-in-Docker or nested containers.

| Concern | How the K8s Pod Handles It |
|---------|---------------------------|
| Process isolation | Pod boundary — agent processes can't escape |
| Filesystem isolation | `emptyDir` volume — pod-local, dies with the pod |
| Resource limits | Pod `resources.limits` — CPU, memory caps enforced by kubelet |
| Execution timeout | `activeDeadlineSeconds` on the Job spec (4 hours default) |
| Network isolation | Stage-aware `NetworkPolicy` — TDD runs egress-locked (LLM APIs + git + sidecars only). Full egress unlocked after Security Review passes (§7.4) |
| Credential isolation | Only pipeline secrets mounted — no production credentials |
| CR-to-CR isolation | Separate pods, separate volumes, separate network identity |

### 7.2 Secret Management

Worker pods need two categories of secrets:

**Pipeline secrets** (same for all CRs): LLM API keys, git SSH keys, PostgreSQL/Redis credentials. Mounted from K8s Secrets into every worker pod.

**Repo-specific test secrets** (per repo): Database URLs for integration tests, API keys for test environments, service account credentials. These vary by repo and are sensitive — they should not be baked into the pipeline config.

The pipeline uses a **pluggable secret provider** to inject repo-specific secrets at pod creation time:

| Provider | Use case |
|----------|---------|
| K8s Secrets | Default. Simple. Secrets created per repo, referenced in repo config. |
| HashiCorp Vault | Enterprise. Dynamic secrets, automatic rotation, audit trail. |
| AWS Secrets Manager | AWS deployments. Integrates via CSI driver or init container. |
| Azure Key Vault | Azure deployments. CSI driver integration. |
| GCP Secret Manager | GCP deployments. Workload identity integration. |

Repo config references secret names, not values:

```yaml
repos:
  - name: "auth-service"
    test_secrets:
      provider: "vault"                    # or "k8s", "aws-sm", "azure-kv", "gcp-sm"
      path: "secret/data/auth-service/test"
```

The Job Spawner resolves secrets at pod creation time and injects them as environment variables. Worker pods never see how secrets are stored — they only see environment variables.

### 7.3 Ephemeral Test Infrastructure

The pipeline mandates **Infrastructure-as-a-Sidecar**. No pipeline agent is ever permitted to run tests against persistent shared environments (staging, dev, QA). All test infrastructure is ephemeral and dies with the pod.

Each repo declares the infrastructure its tests need. The Worker pod spins up isolated instances as K8s sidecar containers:

| Repo declares | Pod gets |
|--------------|---------|
| `test_infra: [postgres:16]` | Sidecar: `postgres:16` container, empty database, accessible at `localhost:5432` |
| `test_infra: [redis:7, postgres:16]` | Two sidecars, both localhost-accessible |
| `test_infra: [mysql:8, localstack]` | MySQL + S3/SQS emulation via LocalStack |
| `test-compose.yaml` in repo | Job Spawner translates compose services into pod sidecars at pod creation time |

```yaml
# Repo config (in runtime config DB)
repos:
  - name: "auth-service"
    test_infra:
      sidecars:
        - image: "postgres:16"
          env: { POSTGRES_DB: "test", POSTGRES_PASSWORD: "test" }
          port: 5432
        - image: "redis:7"
          port: 6379
      # OR: reference repo's own compose file
      compose_file: "test-compose.yaml"   # translated to sidecars at pod creation
```

**Safety guarantees:**

- Sidecar containers share the pod's lifecycle — they start with the pod and are killed when the pod terminates. No state persists.
- Each sidecar uses `emptyDir` storage — no persistent volumes, no shared data across CRs.
- Connection strings are injected as environment variables (`TEST_DATABASE_URL=postgresql://test:test@localhost:5432/test`), matching what the repo expects from its `AGENTS.md` or test configuration.
- NetworkPolicy prevents sidecars from reaching anything outside the pod — they are truly isolated.

For repos using **testcontainers**: The pod runs with the `sysbox` runtime or `testcontainers-cloud` agent, allowing the testcontainers library to launch containers inside the pod without Docker-in-Docker. For Kaniko-based container builds, a Kaniko sidecar handles daemonless image building.

### 7.4 Stage-Aware Network Policy (Egress Locking)

AI-generated code is untrusted until reviewed. The pod's network policy changes by stage to minimise the blast radius:

```
┌─────────────────────────────────────────────────────────────────────┐
│  TDD Development (egress-locked)                                     │
│                                                                      │
│  ALLOWED:                              BLOCKED:                      │
│   ✅ LLM API endpoints (HTTPS)          ❌ Public internet           │
│   ✅ Git remote (SSH/HTTPS)             ❌ Package registries         │
│   ✅ Internal sidecars (localhost)      ❌ External APIs              │
│   ✅ PostgreSQL/Redis (pipeline infra)  ❌ Everything else            │
│   ✅ DNS                                                             │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  Delivery + Release (full egress)                                    │
│                                                                      │
│  Unlocked AFTER Security Reviewer gives "Pass" verdict.              │
│  Needed for: package registries, external CI triggers, deploy APIs.  │
└─────────────────────────────────────────────────────────────────────┘
```

**Implementation:** The pod starts with a restrictive `NetworkPolicy`. When the Security Reviewer agent returns a "Pass" verdict on the generated diff, the worker signals the Controller. The Controller updates the pod's `NetworkPolicy` (or annotates the pod for Istio/Cilium to apply a new egress profile). This unlocks package registries and external endpoints for the Delivery stage.

**Package installation during TDD:** Dependencies declared in `package.json`, `requirements.txt`, etc. are installed during the Setup Worktrees stage (before egress is locked), since they're part of the existing codebase. If the Code Writer adds new dependencies, the install runs against a pre-warmed cache or vendored dependencies. If a new dependency genuinely requires a registry fetch, the agent must declare it — the pipeline can temporarily unlock egress for a scoped `npm install` / `pip install`, logged and auditable.

### 7.5 Dynamic Worker Sizing

Instead of static resource limits for every pod, the Job Spawner is **complexity-aware**. It calculates pod requests/limits based on the CR's characteristics, determined during the Repo Identification phase:

```
Pod Resources = Base_Resources + (Affected_Repos × Repo_Weight)
```

| CR complexity | Affected repos | Pod size | CPU request | Memory request |
|--------------|---------------|----------|-------------|----------------|
| Small | 1 repo | Small | 1 CPU | 4Gi |
| Medium | 2–3 repos | Medium | 2 CPU | 8Gi |
| Large | 4–6 repos | Large | 4 CPU | 16Gi |
| XL | 7+ repos | XL | 6 CPU | 24Gi |

The weight can be further adjusted by repo characteristics: monorepos with large test suites get more memory, repos with heavy compilation (Rust, Java) get more CPU. This is configurable per repo:

```yaml
repos:
  - name: "auth-service"
    worker_weight: 1.0          # default
  - name: "platform-monorepo"
    worker_weight: 2.5          # large test suite, heavy builds
```

**Why this matters:** A 1-repo typo fix shouldn't claim 4 CPUs and 16Gi from the cluster while a 5-repo feature change is queued. Dynamic sizing improves cluster density and reduces queueing delays. The Controller calculates the size before spawning the Job, using information available from Repo Identification.

### 7.6 Agent Command Boundaries

Agent SDKs give agents shell access and file tools. Without restrictions, a Code Writer could run `curl`, `cat /proc/self/environ`, or `rm -rf /workspace`. The pod boundary provides process and network isolation, but **within** the pod, agents are further constrained:

**Filesystem restrictions:**

| Path | Access | Why |
|------|--------|-----|
| `/workspace/runs/cr-{id}/` | Read + Write | The agent's working directory — repos, worktrees, generated code |
| `/workspace/repos/` | Read only | Bare clones — agents can read but not corrupt |
| `/tmp` | Read + Write | Temporary files during builds/tests |
| `/home`, `/etc`, `/proc`, `/sys` | Blocked | No access to pod metadata, environment inspection, or system config |
| Environment variables | Filtered | Only `TEST_*` and `LANG`/`PATH` exposed. LLM API keys, git tokens, and pipeline secrets are **not** visible to agents — the agent backend handles API calls, agents never see raw credentials. |

**Implementation:** The agent process runs as a non-root user with a restricted shell profile. Sensitive environment variables are only set in the agent backend's process scope (the wrapper that calls the LLM API), not in the shell the agent controls. File access is enforced via Linux permissions and `seccomp` profiles on the pod.

**Command allowlist (TDD stage):**

| Allowed | Examples | Why |
|---------|---------|-----|
| Language runtimes | `node`, `python`, `java`, `go`, `cargo` | Running tests and code |
| Package managers | `npm`, `pip`, `mvn`, `cargo` (with egress lock, §7.4) | Installing dependencies |
| Test runners | `jest`, `pytest`, `go test`, `mvn test` | Running test suites |
| Build tools | `tsc`, `webpack`, `gradle`, `make` | Compiling code |
| Git | `git diff`, `git log`, `git status` (read-only operations) | Code inspection |
| File tools | `cat`, `grep`, `find`, `ls`, `wc`, `diff`, `head`, `tail` | Code exploration |

| Blocked | Examples | Why |
|---------|---------|-----|
| Network tools | `curl`, `wget`, `nc`, `ssh` | Egress locked — agents use LLM SDK for API calls |
| System inspection | `ps`, `env`, `printenv`, `mount`, `whoami` | No pod introspection |
| Destructive ops | `rm -rf` outside workspace, `kill`, `chmod`, `chown` | Prevent sabotage |
| Package managers (global) | `npm install -g`, `pip install --user` (outside workspace) | No persistent system changes |

**Enforcement layers:** These restrictions stack:
1. **Non-root user** — can't modify system files
2. **Seccomp profile** — blocks dangerous syscalls
3. **Filesystem permissions** — workspace only
4. **Egress lock (§7.4)** — no network for blocked tools anyway
5. **Agent SDK configuration** — most SDKs support tool/command allowlists natively

The goal is defense in depth. Any single layer can fail — the combination makes exploitation significantly harder.
