# Pluggable Agent Backends & Prompt Engineering

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 9. Pluggable Agent Backends

### 9.1 Interface

Every agent backend must support two operations: **execute** (run a task to completion, return result) and **stream** (emit real-time events during execution). The streaming interface is not optional — the control room needs agent-level events in real time.

### 9.2 Backends

| Backend | Model Support | Key Strengths | Licensing |
|---------|--------------|---------------|-----------|
| **Claude Agent SDK** | Anthropic only | Built-in tools, agentic search, subagents, prompt caching | Anthropic |
| **OpenCode SDK** | Claude, GPT, Gemini, local | Model-agnostic, MIT licensed, cost optimisation | MIT |
| **Codex SDK** | OpenAI only | Cloud sandbox, AGENTS.md, native GitHub integration | OpenAI |

Backends can be mixed per stage and per repo.

### 9.3 LLM Resilience & Failover

At 20 concurrent CRs with 3+ parallel agents each, the pipeline makes hundreds of LLM API calls per hour. Provider outages, rate limits, and transient errors are not edge cases — they're operational reality. The pipeline treats LLM availability as a first-class architectural concern.

**Provider chain:** Every agent role is configured with an ordered list of providers, not just one. The pipeline tries them in order until one succeeds. This is fully configurable per role, per stage, even per repo.

```
Agent call
   │
   ▼
Primary provider (e.g. Anthropic Claude Sonnet)
   │
   ├── success ──▶ continue
   │
   ├── transient error (503, 429, timeout) ──▶ retry with backoff
   │       │
   │       ├── recovered ──▶ continue
   │       │
   │       └── exhausted retries ──▼
   │
   └── hard error (auth, invalid request) ──▶ fail immediately (no fallback)
                                               │
                                        ┌──────▼──────┐
                                        │  Fallback 1  │ (e.g. OpenAI GPT)
                                        └──────┬──────┘
                                               │ same retry logic
                                        ┌──────▼──────┐
                                        │  Fallback 2  │ (e.g. Google Gemini)
                                        └──────┬──────┘
                                               │
                                        All providers exhausted
                                               │
                                        ┌──────▼──────┐
                                        │  Pause CR    │ → alert operator
                                        └─────────────┘
```

**Retry policy (per provider):**

| Parameter | Default | Configurable | Description |
|-----------|---------|:---:|-------------|
| Max retries | 3 | ✅ | Attempts before moving to next provider |
| Initial backoff | 5s | ✅ | First retry delay |
| Backoff multiplier | 2× | ✅ | Exponential: 5s → 10s → 20s |
| Max backoff | 60s | ✅ | Cap on retry delay |
| Timeout per call | 120s | ✅ | Max wait for a single LLM response |
| Rate limit handling | auto | ✅ | Respect `Retry-After` header; back-pressure across all agents sharing the same API key |

**Failover scope:** When a provider fails, only the specific agent call fails over — not the entire pipeline. CR-142's Code Writer might be using the fallback while CR-143's Spec Writer is still on the primary. Each agent call makes its own failover decision independently.

**Rate limit coordination:** Multiple agents across multiple CRs share API keys. The pipeline maintains a per-key token bucket that tracks rate limit headers from the provider. When approaching limits, it throttles new calls rather than hitting 429s. This is especially important for Anthropic (tokens-per-minute limits) and OpenAI (requests-per-minute limits).

**Provider health tracking:** The pipeline tracks success rates, latency, and error rates per provider. This feeds into the system observability dashboards (§18). If a provider is degraded (>20% error rate over 5 minutes), the pipeline can be configured to proactively route new agent calls to the fallback without waiting for individual call failures.

**What failover does NOT do:** It does not switch providers mid-conversation. If an agent call involves a multi-turn tool-use loop (e.g. Code Writer iterating through test failures), the entire loop stays on one provider. Failover happens at the granularity of a complete agent invocation, not individual API calls within a tool-use session.

**Prompt compatibility:** Different providers may need different prompt formatting. The prompt template system (§11) supports provider-specific variants. A role prompt can have a primary version (optimised for Claude) and a fallback version (adapted for GPT). If no variant exists, the primary prompt is used — most prompts work across providers with some quality degradation.

### 9.4 Three-Phase Agent Execution

Agent invocations can run in up to three phases, each using a different model optimised for its task. This spreads load across separate rate-limit pools, keeps exploration tokens out of the action context, and uses Opus for one high-quality strategic planning call.

| Phase | Default Model | Tools | Purpose |
|-------|--------------|-------|---------|
| **Explore** | Haiku ($0.80/$4) | `read_file`, `list_directory` (read-only) | Discover codebase structure, read relevant files |
| **Plan** | Opus ($15/$75) | None (single API call) | Analyse exploration results, produce implementation plan |
| **Act** | Sonnet ($3/$15) | All tools | Execute the plan with focused tool calls |

**Benefits:**
- Three separate rate-limit pools (30k input tokens/min each = 90k effective)
- Exploration tokens stay in Haiku context, never re-sent to Sonnet
- Opus produces a high-quality plan that focuses Sonnet's work
- Cheaper overall: Haiku for bulk reading, Opus for one strategic call

**Per-role phase configuration:**

| Role | Phases | Rationale |
|------|--------|-----------|
| `intake_parser` | None | Single structured-output call, no exploration |
| `spec_writer` | Explore → Plan → Act | Read repo, plan spec coverage, write .feature files |
| `spec_verifier` | Explore → Act | Read specs + CR, verify (plan adds little) |
| `test_writer` | Explore → Plan → Act | Discover test patterns, plan tests, write tests |
| `code_writer` | Explore → Plan → Act | Understand codebase, plan implementation, write code |
| `security_reviewer` | Explore only | Reads diff + files, outputs JSON |
| `quality_reviewer` | Explore only | Reads diff + files, outputs JSON |
| `spec_compliance_reviewer` | Explore only | Reads diff + files, outputs JSON |
| `conflict_resolver` | Explore → Act | Read conflicts, resolve them |

Phases are controlled by `explore_model` and `plan_model` fields on `AgentTask`. Empty string skips the phase. When neither is set, the agent runs identically to a single-phase invocation (backwards compatible).

---

## 11. Prompt Engineering & Agent Context

### 11.1 Prompt Composition Model

Every agent prompt is assembled from four layers:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: ROLE SYSTEM PROMPT                                │
│  Who you are, what you produce, what "done" looks like.     │
│  Static per agent role. Versioned in the pipeline repo.     │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: REPO CONTEXT                                      │
│  AGENTS.md, directory structure, tech stack, conventions.    │
│  Auto-discovered from the worktree at runtime.              │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: TASK PAYLOAD                                      │
│  The CR, behaviour specs, code under review, etc.           │
│  Different per pipeline run. Assembled from PipelineState.  │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: LOOP CONTEXT (conditional)                        │
│  Previous feedback, CI logs, human override instructions.   │
│  Only present when re-entering a stage from a feedback loop.│
└─────────────────────────────────────────────────────────────┘
```

Each layer changes at a different rate: Layer 1 evolves with prompt tuning, Layer 2 is per-repo, Layer 3 is per-CR, Layer 4 is per-iteration. Separating them enables independent evolution.

### 11.2 Repo Context Discovery

Before any agent runs against a repo, the pipeline reads context from the worktree:

| Content | Typical size | Included for |
|---------|-------------|-------------|
| AGENTS.md / CLAUDE.md (conventions file) | 500–2000 tokens | All agents |
| Directory tree (3 levels) | 200–800 tokens | All agents |
| Tech stack summary | 50–200 tokens | All agents |
| Retrospective learnings from past CRs | 200–1000 tokens | All agents |
| Existing test pattern samples | 500–1500 tokens | Test and spec writers only |
| Existing .feature file samples | 500–1500 tokens | Spec writers only |

Static context is capped (~12k tokens) to leave room for agent tool use and reasoning. Agents use their built-in tools (file search, grep, glob) for dynamic discovery during execution. The prompt sets the *strategy* ("follow the repo's test patterns"); the agent's tool use provides the full *context* on demand.

### 11.3 The AGENTS.md Convention

Each repo can include an `AGENTS.md` file at its root — explicit instructions for AI agents. This is the team's primary lever for controlling agent behaviour in their codebase without touching pipeline code. A good AGENTS.md covers: architecture overview, coding conventions, testing conventions, behaviour spec conventions, common gotchas, and what not to change.

### 11.4 Agent Roles

| Role | Stage | What it does | Key quality criteria |
|------|-------|-------------|---------------------|
| **Input Screener** | Intake | Analyses CR description for prompt injection patterns, flags suspicious content | Catches low-effort injection; no false-blocks on legitimate CRs |
| **Spec Writer** | Behaviour Translation | Writes Gherkin .feature files from the structured CR | Every acceptance criterion covered; testable assertions; negative and boundary cases |
| **Completeness Checker** | Behaviour Verification | Verifies every CR criterion has scenarios | Lists gaps with specific suggestions |
| **Consistency Checker** | Behaviour Verification | Verifies cross-repo specs don't contradict | Checks API contracts, data formats, sequences |
| **Test Writer** | TDD Development (RED) | Writes failing tests from behaviour specs | Tests fail for the right reasons; existing tests still pass |
| **Code Writer** | TDD Development (GREEN) | Implements code to make tests pass | All tests green; follows repo conventions; clean code |
| **Diff Scope Analyser** | Code Review (pre-pass) | Deterministic check: flags files, endpoints, dependencies outside expected scope | No LLM — can't be prompt-injected. Flags, not blocks |
| **Security Reviewer** | Code Review | Finds security vulnerabilities; runs in **adversarial mode** (§12.5) — treats CR as untrusted input | Flags code that doesn't match specs regardless of CR justification |
| **Quality Reviewer** | Code Review | Assesses correctness, architecture, maintainability | Correctness, patterns, error handling, performance |
| **Spec Compliance Reviewer** | Code Review | Verifies code matches behaviour specs | Every scenario has a corresponding test and implementation |
| **Merge Conflict Agent** | Rebase & Conflict Resolution | Resolves git merge conflicts using CR intent, specs, and both sides' changes | Conflict resolved correctly; tests pass after resolution; no regressions |
| **Retrospective Agent** | Post-CR Retrospective | Summarises what went wrong/right, distils learnings for the Knowledge Store | Actionable, repo-specific insights; no hallucinated issues |
| **Sync Agent** | Human-to-AI Handover | Analyses human's changes (diff), updates behaviour specs to match, validates baseline | Accurate diff summary; specs match code; tests pass |

Each role has a versioned system prompt stored on disk. Prompts are the product's core IP — they evolve based on metrics, not intuition.

### 11.5 Loop Context

When an agent re-enters a stage from a feedback loop, it receives additional context:

| Loop | Context provided |
|------|-----------------|
| Verification → Translation | Specific gaps and suggestions from the checker |
| Review → Development | Critical findings with file locations and fix suggestions |
| Conflict resolution → Development | Conflicting files, what changed on main, how the conflict was resolved, which tests broke |
| CI failure → Development | Failed check names, log output, common CI-only failure patterns |
| Human override | Free-text instructions from the operator (highest priority) |
| Human-to-AI handover | Diff summary of human's changes, updated behaviour specs, fresh test baseline (from Sync Node) |

### 11.6 Prompt Evolution

Prompts are version-controlled (`prompts/v1/`, `prompts/v2/`, ...) with a config file mapping which version is active per role. A/B testing routes a percentage of CRs to experimental versions. Key metrics per prompt version: first-pass verification rate, first-pass review rate, first-pass CI rate, loop counts, token usage, human override frequency. The process: hypothesis → new version → 20% traffic → measure over 50 CRs → promote or discard.

**Provider-specific variants:** A role prompt can have variants optimised for different providers (e.g. `spec_writer.claude.md`, `spec_writer.openai.md`). When the provider chain fails over, the pipeline uses the variant for the fallback provider if one exists, otherwise falls back to the primary prompt. This allows tuning for each provider's strengths without requiring it — most prompts work across providers with acceptable quality.
