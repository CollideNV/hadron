# Authentication & Authorization

*Split from [architecture.md](architecture.md) — sections below preserve original numbering.*

---

## 3. Authentication & Authorization

### 3.1 Design Principle

**Authentication** (who are you?) is handled by an external OIDC provider. **Authorization** (what can you do, in which tenant?) is managed entirely within the pipeline's own database. This separation is deliberate: the identity provider tells us who someone is, but the pipeline itself decides what they're allowed to do and which tenants they can access.

This means an Admin can manage users, roles, and tenant membership from the pipeline dashboard — no Keycloak/Azure AD admin panel needed for day-to-day operations.

### 3.2 Identity Architecture

```
┌──────────────┐     OIDC     ┌──────────────┐     JWT (identity only)
│   Browser /  │◄────────────▶│   Keycloak   │─────────────────────────┐
│   CLI / API  │              │   (or any    │                         │
│              │              │    OIDC IdP)  │                         │
└──────────────┘              └──────────────┘                         │
                                                                       ▼
                                                              ┌──────────────────┐
                                                              │   Controller     │
                                                              │                  │
                                                              │  1. Validate JWT │
                                                              │  2. Look up user │──▶ PostgreSQL
                                                              │     in our DB    │    ┌──────────────┐
                                                              │  3. Load tenant  │    │ users        │
                                                              │     memberships  │    │ tenants      │
                                                              │     + roles      │    │ memberships  │
                                                              └──────────────────┘    │ (user,tenant,│
                                                                                      │  role)       │
                                                                                      └──────────────┘
```

The JWT from the OIDC provider contains only the user's identity (subject ID, email, name). It does **not** contain roles, tenant membership, or permissions — those live in the pipeline's own database and are looked up on every request.

First-time login: when a user authenticates via OIDC for the first time, the Controller creates a user record in the database (auto-provisioning from the JWT claims). The user has no tenant access until a tenant Admin or super-admin grants it.

### 3.3 Roles & Permissions

Roles are assigned **per tenant** within the pipeline's database. A user can have different roles in different tenants.

| Role | View dashboard | Trigger CRs | Pause / redirect / skip | Approve releases | Configure tenant | Manage tenant users |
|------|:-:|:-:|:-:|:-:|:-:|:-:|
| **Viewer** | ✅ | — | — | — | — | — |
| **Operator** | ✅ | ✅ | ✅ | — | — | — |
| **Approver** | ✅ | ✅ | ✅ | ✅ | — | — |
| **Admin** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

Example: Berten is Admin on the "Collide" tenant and Approver on the "Bewire" tenant. When he switches to Collide, he can manage repos and users. When he switches to Bewire, he can approve releases but not change configuration.

**Super-admin:** A platform-level role (not per-tenant). Can see all tenants, create new tenants, manage cross-tenant settings, view system-wide metrics and costs. Assigned in the database by another super-admin or during initial setup.

**Key security boundaries:**

- The **Release Gate** (§8.10) requires the Approver role within the active tenant.
- **Intervention actions** (pause, redirect, skip, abort) require the Operator role.
- **Tenant configuration**, repo registration, and user management require the Admin role within that tenant.
- **API tokens** for machine-to-machine access (CI webhooks, source connectors) are scoped to a specific tenant and role.

### 3.4 Authentication Flows

| Client | Flow | Details |
|--------|------|---------|
| Dashboard (browser) | OIDC Authorization Code + PKCE | Standard browser-based login. IdP login page → redirect with code → exchange for tokens. |
| CLI tool | OIDC Device Code | For terminal-based interaction. User visits a URL, enters a code, approves. |
| Direct API consumers | Client Credentials | Service account with client ID + secret. For CI webhooks, automated triggers. Scoped to a tenant. |
| Source connectors (Jira, GH) | Service Account | Pipeline's own credentials to issue trackers. Not OIDC — connector-specific auth. |

### 3.5 Token Handling

The Controller validates JWTs on every request, then looks up authorization in its own database:

1. **Validate JWT** against the OIDC provider's JWKS endpoint (cached). Extract subject ID and email.
2. **Look up user** in PostgreSQL by subject ID. Auto-provision on first login.
3. **Load tenant memberships** — which tenants the user can access and their role in each.
4. **Determine active tenant** — from the `X-Tenant-ID` header, session cookie, or last-used tenant.
5. **Enforce permissions** — check the user's role in the active tenant against the endpoint's required role.

- **Access token** (short-lived, ~5 min): Carried in `Authorization: Bearer` header. Contains identity only.
- **Refresh token** (longer-lived): Used by the dashboard to obtain new access tokens without re-login.
- **SSE authentication**: Token sent as query parameter on the SSE endpoint (HTTPS only). Validated once at connection time. Events scoped to active tenant.

### 3.6 OIDC Provider Setup

The pipeline works with any OIDC-compliant identity provider. Keycloak is the default for self-hosted deployments, but organisations can point at their existing Azure AD, Okta, Auth0, or Google Workspace.

Required provider configuration:

- A **client** for the browser-based dashboard (public client, Authorization Code + PKCE)
- A **client** for machine-to-machine API access (confidential client, Client Credentials)
- Standard OIDC claims in the JWT: `sub` (subject ID), `email`, `name`

No roles, groups, or custom claims are needed in the OIDC provider — the pipeline manages all of that internally.

For self-hosted Keycloak, the pipeline ships with a realm configuration that creates the two clients above.

### 3.7 Audit Trail

Every authenticated action is recorded with the user's identity and tenant context:

| Event | Recorded data |
|-------|--------------|
| CR triggered | User ID, tenant ID, source, timestamp |
| Intervention (pause/redirect/skip/abort) | User ID, tenant ID, CR ID, action, instructions, timestamp |
| Release approved/rejected | User ID, tenant ID, CR ID, decision, timestamp |
| Configuration changed | User ID, tenant ID, what changed, before/after, timestamp |
| User role changed | Changed by (user ID), target user, tenant, old role, new role, timestamp |
| Tenant created | Super-admin user ID, tenant name, timestamp |

The audit trail is stored in PostgreSQL. Tenant Admins see their tenant's audit trail. Super-admins see everything.

### 3.8 Multi-Tenancy

A single pipeline installation supports multiple tenants (teams, departments, subsidiaries) on shared infrastructure. Tenants are logically isolated — they share the Controller, PostgreSQL, Redis, and the OIDC provider, but cannot see each other's data.

**Tenant model:**

```
┌─────────────────────────────────────────────────────────────────┐
│  Shared Infrastructure                                           │
│  Controller │ PostgreSQL │ Redis │ OIDC Provider │ K8s Cluster   │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─ Tenant: Bewire ──────────┐   ┌─ Tenant: Collide ──────────┐ │
│  │  repos, CRs, config,     │   │  repos, CRs, config,       │ │
│  │  audit, costs, knowledge  │   │  audit, costs, knowledge   │ │
│  │                           │   │                             │ │
│  │  Berten: Admin            │   │  Berten: Approver          │ │
│  │  Alice: Operator          │   │  Charlie: Admin            │ │
│  │  Bob: Approver            │   │  Dana: Operator            │ │
│  └───────────────────────────┘   └─────────────────────────────┘ │
│                                                                  │
│  Berten: super-admin (can see both tenants + create new ones)    │
└──────────────────────────────────────────────────────────────────┘
```

**User-tenant membership** is managed in the pipeline's database, not the OIDC provider:

| Table | Purpose |
|-------|---------|
| `users` | OIDC subject ID, email, name, super-admin flag. Auto-provisioned on first login. |
| `tenants` | Tenant ID, name, created date, settings. |
| `tenant_memberships` | User ID, tenant ID, role. One row per user-tenant pair. A user can be in many tenants. |

**Tenant switcher:** The dashboard shows a tenant selector in the header. When Berten switches from Bewire to Collide, the dashboard sends the tenant ID in the `X-Tenant-ID` header. All API responses, SSE events, and dashboard views scope to the selected tenant. The user's role changes based on their membership in that tenant.

**What's scoped per tenant:**

| Resource | Isolation |
|----------|-----------|
| Repos and applications | Each tenant has its own registered repos. Tenant A cannot see or trigger CRs against Tenant B's repos. |
| CRs and pipeline runs | Tenant-scoped. Dashboard only shows CRs belonging to the active tenant. |
| Source connectors | Configured per tenant (Tenant A's Jira project, Tenant B's GitHub org). |
| User roles | A user's role is per-tenant. Admin in one tenant doesn't grant Admin in another. |
| Audit trail | Filtered per tenant. Super-admins can see across tenants. |
| Cost tracking | Accumulated and reported per tenant. System-wide cost views available to super-admins. |
| Knowledge Store | Landscape knowledge is per tenant — each tenant's scanner builds knowledge of their repos only. |
| Event streams and notifications | Scoped to active tenant. SSE connections only receive events for the selected tenant. |
| Configuration | Pipeline settings, circuit breaker thresholds, notification routing — all per tenant. |

**What's shared:**

| Resource | Sharing model |
|----------|--------------|
| Controller process | Single deployment, routes requests by tenant based on `X-Tenant-ID` header |
| K8s cluster | Worker pods for all tenants run on the same cluster. Resource quotas per tenant if needed. |
| PostgreSQL | Single database, tenant ID column on every table. Row-level isolation. |
| Redis | Key prefix per tenant (`bewire:cr:142:events`, `collide:cr:87:events`) |
| OIDC provider | Single provider. Pipeline maps OIDC subjects to internal user records. |
| LLM API keys | Can be shared (pipeline-owned) or per-tenant (tenant brings their own key) |

**Tenant management API:**

| Endpoint | Who | Description |
|----------|-----|-------------|
| `POST /api/tenants` | Super-admin | Create a new tenant |
| `GET /api/tenants` | Super-admin | List all tenants |
| `GET /api/tenants/{id}/members` | Tenant Admin | List members of a tenant |
| `POST /api/tenants/{id}/members` | Tenant Admin | Invite a user to a tenant (by email). If they haven't logged in yet, the invitation is pending until first login. |
| `PUT /api/tenants/{id}/members/{userId}` | Tenant Admin | Change a user's role within the tenant |
| `DELETE /api/tenants/{id}/members/{userId}` | Tenant Admin | Remove a user from a tenant |

**Tenant onboarding:** A super-admin creates the tenant, then adds the first Admin user. That Admin can then invite others, register repos, configure source connectors, and set up notifications — all from the dashboard.
