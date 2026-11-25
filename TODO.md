# Build TODO

Status follows repository evidence, not intention. Complete items only when the outcome is implemented and verified.

## 1. Repository-only intake and metadata

- [x] A user can submit a GitHub repository URL as the only per-run project input for the supported initial profile.
- [x] Public repository links can be inspected without GitHub authorization.
- [ ] Private links require a user-authorized GitHub connection before source access.
- [x] Inspection resolves the default branch to a commit SHA and pins all setup-file reads to that revision.
- [x] The service rejects malformed URLs, non-GitHub hosts, embedded credentials, unexpected ports, and unsupported link forms before making outbound requests.
- [x] Repository/access, rate-limit, and upstream failures map to bounded client responses without exposing upstream bodies.

## 2. Setup inference and preflight

- [x] For the initial Node/npm/Vite profile, the service reads bounded root `package.json`, npm lockfile names, `.nvmrc`, and a root Vite config; it does not yet inspect Docker/compose files, CI workflows, READMEs, existing tests, or route/API definitions.
- [x] For supported setup fields, the response includes the detected runtime, package manager, install/build/start commands, port/health-check assumption, evidence sources, and confidence before any execution.
- [ ] A deployed URL, custom command, environment variable, or test credential is optional and requested only when the repo cannot be safely run without it.
- [x] The initial profile respects exact Node pins and npm lockfiles, reports conflicting/unsupported lockfiles, and does not treat an engine range as an exact runtime version.

## 3. Secure run orchestration

- [x] The API inspection path and disabled runner placeholder never execute repository-defined commands; no run orchestrator exists yet.
- [ ] A future orchestrator dispatches untrusted commands only through the isolated backend and never executes them in the API/worker process.
- [x] A backend-neutral runner contract constrains immutable run identity, supported argv/provenance, security-policy settings, resource limits, and bounded result artifacts; its default runner fails closed.
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
- [x] Safe repository-intake slice: typed FastAPI app, strict GitHub URL parser, fixed-origin public metadata client, and `POST /api/v1/repositories/inspect`; no clone or code execution.
- [x] Commit-pinned bounded setup inspection and deterministic Node/npm/Vite inference; the live public Sauce fixture returned a ready static plan at the recorded SHA in [fixture evidence](docs/fixture-setup-evidence.md).
- [x] Backend-neutral sandbox contract and threat model: strict initial-profile argv, immutable commit, bounded policy/result schemas, and a fail-closed placeholder; no Docker executor is configured.
- [x] Verification: 65 unit/API/contract tests pass, Ruff and locked dependency checks pass, and total coverage is 97.15% against the 95% CI gate.
- [ ] Remaining foundation: private-repository authorization, persistence, run lifecycle/queue, and an independently reviewed isolated execution backend.
- [ ] Fixture preflight: deferred until an isolated runner is available; no repository-defined scripts have been run in the API process or this sandbox.
