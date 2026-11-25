# TestAtlas implementation plan

## Product and implementation approach

Build TestAtlas as a Python-first, API-led repository testing platform. A supported run begins with a GitHub repository URL as the only per-run project input. The service validates and canonicalizes the GitHub URL, pins the source to a commit, derives a setup plan from repository metadata, and hands execution to a separate isolated runner. The runner starts the target app, collects a module map, executes generated pytest/Playwright tests, and uploads structured results and evidence. A dashboard will expose both hosted runs and downloadable local test bundles.

The target repository is untrusted. The API must never execute repository scripts. The web API, orchestration worker, and repository sandbox are separate trust boundaries. The production runner will use disposable, resource-limited environments with restricted egress and short-lived checkout access. The production-grade sandbox adapter remains an explicit milestone; the current development sandbox has no Docker runtime, so only safe API/domain code that does not execute repository code will be run here.

The service will use FastAPI and Pydantic for the API and data contracts, PydanticAI for bounded structured planning/diagnosis, PostgreSQL for durable application records, Redis with Celery for background runs, and object storage for artifacts. Browser checks use pytest and Playwright for Python. The dashboard should initially be served from FastAPI using accessible server-rendered pages and HTMX; if the UI later needs richer client-side state, a separate React client can be introduced without changing API contracts.

## Material constraints and defaults

- Supported runtime profiles are explicit and versioned. The first acceptance fixture is Sauce Labs' public `sample-app-web` repository, which declares Node.js 24.9.0+, has npm manifests/lockfile and documents its Vite start script. The platform itself remains Python-first.
- The repo link is the only normal per-run project input. Public source access works without GitHub sign-in. Private sources require a user-authorized, read-only GitHub App installation. AI provider credentials are configured separately and stay outside the runner.
- The system infers build/start commands from manifests, runtime-version files, Docker/compose files, CI workflows, and repository documentation. Any inferred plan is displayed with evidence and confidence before execution. A deployed URL or command override is an optional fallback.
- The API must be independently runnable for local development. Production database, queue, object store, secret management, and isolated execution infrastructure are deployment concerns; credentials must be supplied through environment/secret management, not committed.
- Source execution is blocked until a production sandbox backend is configured. Never fall back to running unknown repository code in the API or worker process.

## Architecture boundaries

1. **HTTP/API service:** authentication, project/run lifecycle, URL validation, provider configuration references, report retrieval, exports, and dashboard responses. It performs no arbitrary repository execution.
2. **Repository metadata service:** accepts only HTTPS GitHub repository URLs, resolves repository metadata and a commit SHA through GitHub's API, observes rate limits, and reports access errors.
3. **Orchestrator:** stores state transitions, applies quotas/budgets, dispatches immutable run plans, receives progress, and ensures cancellation/timeouts.
4. **Sandbox adapter:** contract for creating/destroying an isolated environment, checking out a pinned commit, provisioning only declared runtimes, starting the app, and capturing artifacts. A backend must prove isolation and egress controls before being enabled.
5. **AI adapter:** selects the user's configured provider/model, passes minimal redacted context, validates Pydantic schemas, enforces per-run budgets, and records usage metadata.
6. **Test and evidence pipeline:** pytest/Playwright execution, JUnit/JSON results, screenshot/trace/log collection, module-to-test links, and private object storage.
7. **Dashboard:** project listing, repo-link start, detected setup preview, run progress, module coverage map, failure details, and local bundle download.

## Design direction

### Style options considered

- **CI Control Room — 0.04:** a dense engineering console focused on run state, evidence, and operational clarity.
- **Terminal Field Guide — 0.03:** a dark developer shell aesthetic with logs and command-like controls.
- **Minimal Swiss QA Console — 0.02:** a calm, bright editorial interface that prioritizes clarity and auditability.

### Selected style: Minimal Swiss QA Console

- **Design movement:** Swiss editorial information design adapted for a developer tool.
- **Core principles:** explicit state; evidence adjacent to claims; readable density; restrained color for status.
- **Color philosophy:** near-white and graphite surfaces for long inspection sessions, with a crisp indigo signature color for actions and links. Green, amber, and red are reserved for outcome states and always paired with text/icons.
- **Layout paradigm:** a persistent left project rail and wide evidence canvas; run summary and module map sit above a two-column result/evidence workspace. Avoid generic hero cards and decorative dashboards.
- **Signature elements:** commit-pinned run header; a route/module coverage rail; a compact evidence timeline that links each failure to its trace/screenshot.
- **Interaction philosophy:** users can inspect and reproduce before acting. Destructive or write-capable actions are separated and explicitly described; table rows and error states link directly to their evidence.
- **Animation:** brief progress transitions for queued/running states; no looping decorative motion; honor reduced-motion settings.
- **Typography system:** system sans or Inter for UI text, a readable monospaced face for commit IDs, commands, and raw errors; hierarchical headings with tabular numerals for counts.
- **Brand essence:** “Traceable tests for real repositories.” Personality: clear, careful, developer-first.
- **Brand voice:** direct, evidence-led, no inflated AI claims. Examples: “We detected Node 24.9 from `.nvmrc`.” “This module is untested because its database service was unavailable.”
- **Wordmark/logo concept:** a compact route-map mark made from three connected nodes, with one highlighted path ending in a check; pair it with the TestAtlas wordmark.
- **Signature brand color:** saturated indigo, used sparingly for primary actions and active navigation.

## Initial project structure

```text
TestAtlas/
├── README.md
├── plan.md
├── TODO.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── alembic.ini
├── alembic/
│   └── versions/
├── src/testatlas/
│   ├── main.py                 # FastAPI application and lifespan
│   ├── config.py               # typed environment configuration
│   ├── api/                    # versioned routers and request/response schemas
│   ├── domain/                 # repository/run/module/test contracts and states
│   ├── services/               # GitHub metadata, setup detection, orchestration
│   ├── workers/                # Celery tasks; no direct execution of repo scripts
│   ├── sandbox/                # runner contract and isolated backend adapters
│   ├── ai/                     # provider adapter, planning and diagnosis agents
│   ├── persistence/            # SQLAlchemy models, sessions, repositories
│   ├── security/               # URL validation, secret redaction, policy helpers
│   └── web/                    # dashboard routes/templates and static assets
├── tests/
│   ├── unit/
│   ├── api/
│   └── security/
├── docs/
│   └── phase-1-scope.md
└── infra/                      # local service config and production deployment examples
```

## Development and production boundaries

Local development uses `uv` and a local test database or disposable PostgreSQL/Redis services. CI runs formatting/lint, typing where practical, and unit/API/security tests without repository execution. Production requires TLS, authenticated organization-scoped APIs, least-privilege GitHub access, managed PostgreSQL/Redis, private evidence storage, encryption for provider credentials, audit logs, rate/cost limits, and an independently reviewed sandbox backend. Do not deploy an untrusted-code runner until its isolation, network egress, credential boundaries, resource quotas, and cleanup are verified.

## Project delivery approach

Keep each change small and reviewable. Establish typed domain/API boundaries first; implement public repository metadata inspection without executing code; add database/run persistence and job lifecycle; implement setup inference; integrate sandbox only after a real isolated execution environment is available; add AI planning after schemas and deterministic runner output exist; then build the dashboard and local export. Run applicable tests and static checks before each commit. Do not call a prototype production-ready until authentication, tenant isolation, sandboxing, retention, observability, backup, and deployment are implemented and verified.
