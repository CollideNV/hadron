# CR Intake & Repository Management

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 4. Change Request Intake Sources

### 4.1 Design Principle

The pipeline doesn't care where a change request originates. Every source connector produces a normalised **RawChangeRequest** (source, external ID, title, body, labels, priority, author, attachments, metadata) and triggers the pipeline. The intake node parses it into a structured format.

### 4.2 Source Connector Interface

Every connector implements four operations: **start** (begin listening/polling), **stop** (shut down), **acknowledge** (report pipeline status back to the source), and **report_result** (report final outcome).

### 4.3 Connectors

| Source | Trigger mechanism | Status reporting |
|--------|------------------|-----------------|
| **Jira** | JQL poll or webhook | Transitions issue status, adds comments |
| **GitHub Issues** | Webhook on `ai-ready` label | Updates labels, adds comments |
| **Azure DevOps** | WIQL poll or service hooks | Updates work item state |
| **Slack** | `/pipeline` slash command or emoji reaction | Thread replies with status |
| **Direct API** | `POST /api/pipeline/trigger` — always available | Returns result via callback URL or polling |

### 4.4 Source Status Lifecycle

The pipeline reports status back to the source at every checkpoint:

```
pipeline_started → behaviour_specs_ready → development_complete →
ci_waiting → ci_passed/ci_failed → awaiting_approval → completed/failed
```

---

## 6. Repository Management

### 6.1 Git Worktrees

One branch per repo per CR (`ai/cr-{id}`). All stages commit to the same branch. Worktrees live in the pod's `/workspace` emptyDir volume — pod-local fast storage that dies with the pod.

```
/workspace/
├── repos/                                 ← bare clones (fetched at pod start)
│   ├── auth-service/.git/
│   └── api-gateway/.git/
└── runs/
    └── cr-142/                            ← this pod handles exactly one CR
        ├── auth-service/                  ← worktree, branch: ai/cr-142
        └── api-gateway/                   ← worktree, branch: ai/cr-142
```

### 6.2 Git Authentication

Workers need to clone repos and push branches. Authentication is per-tenant — Tenant A's workers must not be able to push to Tenant B's repos.

| Provider | Mechanism | Rotation | Recommended for |
|----------|-----------|----------|----------------|
| **GitHub** | GitHub App installation tokens | Auto-rotated (1 hour expiry). App installed per org, scoped to specific repos. | GitHub orgs. Preferred — short-lived, scoped, auditable. |
| **GitLab** | Project access tokens or Group access tokens | Configurable expiry. Scoped to project or group. | GitLab deployments. |
| **Azure DevOps** | PAT or Service Principal | PAT: manual rotation. SP: auto-rotated via Azure AD. | Azure DevOps repos. |
| **Generic** | SSH deploy keys | Manual rotation. One key per repo, read-write. | Self-hosted Git, Bitbucket. |

The Job Spawner injects git credentials into the worker pod at creation time, resolved from the tenant's secret provider (§7.2). Workers never see how tokens are generated — they receive a pre-configured `~/.git-credentials` file or SSH key.

For **GitHub App tokens** (recommended): The Controller holds the GitHub App private key and generates short-lived installation tokens for the tenant's GitHub org. Each worker pod gets a fresh token scoped to the repos in the CR. The token expires after 1 hour — more than enough for a pipeline run, and if the pod is compromised, the blast radius is limited.

Git credentials are part of the tenant's runtime config:

```yaml
repos:
  - name: "auth-service"
    git_auth:
      provider: "github-app"               # or "ssh", "token"
      github_app_id: 12345
      github_app_key: "${GITHUB_APP_KEY}"   # stored in secret provider
      installation_id: 67890
```

### 6.3 Stage Handoff

Every stage works on the same worktree directory. Behaviour Translation writes `.feature` files → commits. TDD finds them → writes tests and code → commits. Review reads full state. No file copying, no artifact passing — just git. Branches are pushed to the remote after every stage, ensuring all work survives pod failure and enabling human take-over via `git clone`.

### 6.4 Monorepo Support

For monorepos, the "repo" concept maps to a **directory within the monorepo** rather than a separate git repo. The worktree model changes slightly:

- One worktree for the whole monorepo (single branch `ai/cr-{id}`)
- Each "application" is identified by its path within the monorepo (e.g. `packages/auth-service`, `services/api-gateway`)
- Agents are initialised per application directory — one agent instance per affected application, working in parallel (see §8.11)
- The pipeline config registers applications with their path prefix instead of a separate git URL
- Behaviour specs, tests, and code review all scope to the relevant application directories

```
/workspace/
└── runs/
    └── cr-142/
        └── platform-monorepo/             ← single worktree, branch: ai/cr-142
            ├── packages/auth-service/     ← agent instance 1 works here
            ├── services/api-gateway/      ← agent instance 2 works here
            └── shared/common-lib/         ← agent instance 3 if affected
```

This means the Landscape Knowledge Store registers applications (not repos) and the repo identification step maps CRs to application paths.
