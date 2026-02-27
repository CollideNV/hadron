# Landscape Intelligence

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 10. Landscape Intelligence

### 10.1 Design Principle

The pipeline needs to understand the application ecosystem: what each service does, what it owns, how services connect, and which repos tend to be affected by which types of changes. This knowledge is built and maintained by a **separate background process** — the **Landscape Scanner** — that runs independently from the pipeline (nightly and on-push), writing to a shared **Knowledge Store** that the pipeline queries at intake time.

This separation means knowledge-building never blocks pipeline throughput, and understanding improves continuously whether or not any CRs are running.

### 10.2 What the Scanner Knows

For each repo, the Scanner maintains a profile covering:

| Category | Fields | Source |
|----------|--------|--------|
| **Identity** | Description, domain, capabilities owned | LLM analysis of README + AGENTS.md |
| **Surface** | API endpoints, events published/consumed, DB schemas | OpenAPI specs, route files, migration files, event configs |
| **Relationships** | Depends-on, depended-on-by, shared data | Cross-referencing all repos + static analysis of imports/configs |
| **Structure** | Directory summary, key files, conventions | AGENTS.md + directory tree + LLM analysis |
| **Tech Stack** | Language, framework, test framework, DB | Deterministic detection from package manifests |
| **History** | Recent merged PRs, change frequency by area | Git log analysis |
| **Learnings** | Gotchas, edge cases, patterns discovered by past CRs | Retrospective Agent (§8.12) |
| **Freshness** | Last scanned, confidence score | Scanner metadata |

### 10.3 Knowledge Sources

| Source | What it provides |
|--------|-----------------|
| `AGENTS.md` / `CLAUDE.md` | Architecture, conventions, gotchas, what not to change |
| `README.md` | Service description, setup, API overview |
| OpenAPI / Swagger specs | API endpoints, request/response schemas |
| Route files | API endpoints when no OpenAPI exists |
| Package manifests | Tech stack, dependencies, test commands |
| Database migrations | Schema ownership, table names |
| Event configs | Published/consumed events |
| Git log | Recent changes, change frequency, key files |
| Past CR outcomes | Which CRs touched this repo (from pipeline feedback) |

The Scanner combines **deterministic analysis** (tech stack detection, API parsing, git stats) with **LLM synthesis** (inferring purpose, capabilities, and dependencies from code and documentation).

### 10.4 Scan Triggers

| Trigger | Scope | When |
|---------|-------|------|
| Nightly CronJob | Full scan of all repos | Configurable (default 2am) |
| Main branch webhook | Incremental — only the changed repo, only if knowledge-relevant files changed | On push to main |
| New repo registered | Full scan of the new repo | On config change |
| Manual API trigger | Full or targeted scan | `POST /api/landscape/scan` |
| Post-pipeline feedback | CR history + identification accuracy update | After every completed CR |

Knowledge-relevant files that trigger incremental scans: README, AGENTS.md, OpenAPI specs, package manifests, route files, migration files.

### 10.5 Knowledge Store

The Knowledge Store is a PostgreSQL schema with pgvector for embedding-based similarity search:

| Table | Purpose |
|-------|---------|
| `repo_knowledge` | Current understanding of each repo (full profile as JSON + embedding) |
| `repo_dependencies` | Service dependency graph (source, target, method) |
| `cr_repo_history` | Past CR → repo mappings with human corrections, for similarity search |

The pipeline reads from this store at intake time. The Scanner writes to it during scans. The pipeline also writes identification feedback (human corrections) after each CR.

### 10.6 Accuracy Flywheel

```
Scanner scans repos ──▶ Knowledge Store has landscape understanding
                                  │
Pipeline queries at intake ───────┤
                                  │
LLM suggests repos ──────────────┤
                                  │
Human confirms / corrects ────────┤
                                  │
Corrections stored ───────────────┤
                                  │
Next CR uses corrections  ◀───────┘
as context for better suggestions
```

Key metrics: identification accuracy (% accepted without changes), false negative rate (human had to add repos), false positive rate (human removed repos), knowledge freshness (avg days since scan).
