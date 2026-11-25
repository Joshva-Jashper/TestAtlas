# Build TODO

Status follows repository evidence, not intention. Complete items only when the outcome is implemented and verified.

## 1. Repository-only intake and metadata

- [ ] A user can submit a GitHub repository URL as the only per-run project input for a supported repository.
- [ ] Public repository links can be inspected without GitHub authorization. Private links require a user-authorized GitHub connection before source access.
- [ ] The run is pinned to a commit SHA so discovery and later execution refer to the same source revision.
- [ ] The service rejects malformed URLs, non-GitHub hosts, embedded credentials, unexpected ports, and unsupported link forms before making outbound requests.
- [ ] If the repository cannot be found or accessed, the response explains the likely cause without exposing credentials or upstream internals.

## 2. Setup inference and preflight

- [ ] The service inspects repository manifests, lockfiles, runtime-version files, Docker/compose files, CI workflows, READMEs, existing tests, and route/API definitions to infer a setup plan.
- [ ] The detected runtime, package manager, install/build/start commands, port/health check, evidence, and confidence are visible to the user before execution.
- [ ] A deployed URL, custom command, environment variable, or test credential is optional and requested only when the repo cannot be safely run without it.
- [ ] The system respects declared runtime versions and lockfiles. If a runtime or dependency service cannot be provided, it reports a specific blocker instead of guessing silently.

## 3. Secure run orchestration

- [ ] The API server and orchestrator never execute repository-defined commands or scripts directly.
- [ ] Repository execution uses a disposable isolated runner with explicit CPU, memory, disk, process, wall-clock, and network-egress controls.
- [ ] GitHub checkout credentials are short-lived, read-only, removed before dependency installation and test execution, and never passed to the app under test.
- [ ] AI provider credentials remain in the trusted service and are never mounted into the repository sandbox.
- [ ] Runs support explicit lifecycle states, cancellation, timeouts, bounded retries, quotas, and cleanup after completion or failure.

## 4. Module map, AI planning, and execution

- [ ] The system identifies routes/pages, important UI components, API endpoints, existing tests, and supported deterministic services, with a source path/URL and discovery confidence for each item.
- [ ] PydanticAI produces validated candidate test cases containing module link, goal, setup assumptions, steps, assertions, rationale, and confidence.
- [ ] Unclear expected behavior is labeled as an assumption or inconclusive; it is not reported as a confirmed product bug.
- [ ] pytest and Playwright for Python execute generated/approved tests deterministically and provide structured pass/fail/skip/block results.
- [ ] Tests and results are stored in a portable form users can review, rerun, and export.

## 5. Dashboard, evidence, and fixes

- [ ] The dashboard shows discovered, tested, passed, failed, not-tested, blocked, and inconclusive modules with explicit definitions and gap reasons.
- [ ] A failure links to the exact test, assertion/error, screenshot, trace, relevant console output, network failure, duration, and commit.
- [ ] AI failure explanations separate likely app defects from setup errors, test defects, flakiness, and unavailable dependencies, and cite the supporting evidence.
- [ ] Suggested code changes remain advisory until the user explicitly enables a reviewed branch/pull-request workflow.
- [ ] Evidence is private, permission-checked, retention-controlled, and served through expiring download links.

## 6. Two run choices and portable bundle

- [ ] A user can click **Run** to execute the suite in a hosted environment and see progress/results in the dashboard.
- [ ] A user can download a portable project containing ordinary pytest/Playwright test files, dependency/configuration examples, instructions, and launch scripts.
- [ ] The downloaded bundle has a clear one-click launch path for supported desktop environments and a normal command suitable for CI.
- [ ] Local artifacts remain local unless the user explicitly chooses to upload results to the service.
- [ ] The interface explains that the download is the generated test bundle, not the private source code of the hosted TestAtlas service.

## 7. Production readiness

- [ ] User and organization authentication, tenant-scoped authorization, audit events, secure key storage, and secret redaction are implemented.
- [ ] CI runs formatting/linting, type checks where practical, unit/API/security tests, and dependency checks on each change.
- [ ] Production deployment includes managed PostgreSQL/Redis, private object storage, backups, TLS, logs/metrics/traces, rate limits, cost budgets, retention, and incident handling.
- [ ] The isolated execution backend has a reviewed threat model and passes isolation, egress, credential-separation, resource-limit, and cleanup checks before arbitrary repositories are executed.

## Current progress

- [x] Phase 1 scope: repo-link-only input, optional fallbacks, public Sauce Labs fixture, security boundaries, and acceptance criteria documented.
- [x] Safe repository-intake slice: typed FastAPI app, strict GitHub URL parser, fixed-origin metadata client, and `POST /api/v1/repositories/inspect`; it does not clone or execute repository code.
- [x] Verification for the intake slice: unit/API tests, formatting, lint, locked dependency resolution, and coverage threshold are configured; CI workflow added.
- [ ] Remaining foundation: setup inference, immutable commit pinning, private-repository authorization, persistence, run lifecycle/queue, and secure runner contract.
- [ ] Fixture preflight: deferred until an isolated runner is available; no repository-defined scripts have been run in the API process or this sandbox.
