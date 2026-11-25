# Phase 1 — Scope and setup

**Status:** Approved baseline for implementation
**Date:** 2026-11-25

## Product requirement

The primary workflow is **repository link only**. After initial account setup, a user pastes a GitHub repository URL and starts a run. The user should not need to supply a deployed URL, app framework, install command, start command, or port for a supported project.

The system will infer those values from repository metadata and validate them through a preflight. A deployed URL, test credentials, custom start command, or environment variables are optional inputs for special cases—not mandatory setup for every run. If a prerequisite cannot be inferred safely, TestAtlas must describe the uncertainty and ask only for the missing detail.

### Initial authentication behavior

- Public GitHub repositories: URL is sufficient for source access.
- Private GitHub repositories: the user authorizes TestAtlas through a GitHub App before checkout.
- AI provider: the user configures their chosen provider and API key once in account settings. The key must stay in the trusted platform service and never enter the repository runner.

## What a repo-only run must do

1. Parse and validate the repository URL.
2. Fetch the repository using read-only, least-privilege access and pin the run to a commit SHA.
3. Inspect README files, manifests, lockfiles, runtime version files, Dockerfiles, compose files, CI workflows, existing tests, routes, and API schemas.
4. Produce a setup plan with detected language/framework, package manager, runtime version, install/build/start commands, likely port, and confidence/evidence for each guess.
5. Create an isolated disposable environment and install dependencies using lockfile-aware, reproducible commands where possible.
6. Start the app using a detected command; wait for a health check and capture startup logs. Do not assume localhost:3000 or any one framework convention.
7. Discover modules and generate candidate tests with explicit assumptions and source/evidence links.
8. Execute tests using pytest and Playwright for Python (initial UI path), then save reports, screenshots, traces, console messages, and network errors.
9. Show module coverage, passes, failures, blocked items, and evidence in the dashboard.
10. Offer the same generated test bundle for download and local execution.

## Selected public fixture

Use the official Sauce Labs sample web application as the first external fixture:

- Repository: <https://github.com/saucelabs/sample-app-web>
- License: MIT (as shown on the repository page).
- The repository README documents Node.js 24.9 or newer, dependency installation with `npm install`, and starting the Vite development server with `npm run start` at `http://localhost:3000/`.
- The repo includes runtime metadata (`.nvmrc`, `package.json`), a lockfile, a Dockerfile, app source, existing tests, and CI configuration. These files let us test repository-based setup inference instead of relying on a user-supplied command.
- This is a JavaScript/React target app. That does not change TestAtlas’s Python-first platform stack; it intentionally tests that the platform can run browser tests against an app whose language differs from the platform’s language.

**Known fixture constraint:** the fixture currently declares Node `>=24.9.0`. The runner must respect declared runtime versions and must report a runtime/toolchain blocker clearly if it cannot provision the required version. Do not silently use a different Node version.

The first acceptance run should use the repo URL above as the only per-run project input (assuming the AI provider is already configured). It must show its detected setup plan before executing. It must not require the deployed Sauce Demo URL.

## MVP boundary

### Included first

- Public GitHub URL input, with commit pinning.
- Automatic setup inference for one initial web-app profile: Node-based React/Vite app with a supported lockfile and a declared Node version.
- Python platform implementation: FastAPI + PydanticAI + pytest + Playwright for Python.
- Browser smoke/exploration tests and selected user journeys, with deterministic assertions generated from observable behavior and declared app conventions.
- Test result and evidence dashboard; export as normal pytest/Playwright source and config.
- Hosted execution and a local downloadable test bundle.

### Not promised in the first milestone

- That every possible language, framework, repo layout, or build system runs from a URL with no user input.
- Correctly inferring undocumented business rules or guaranteeing full module/behavior coverage.
- Testing applications that require undisclosed secrets, third-party services, CAPTCHA, MFA, or complex organization SSO without setup.
- Running a repo’s own scripts outside the sandbox or allowing project code to access platform/AI credentials.
- Automatically editing the repo, opening pull requests, or merging changes.

When detection finds an unsupported build system, absent runtime, unavailable service, or ambiguous start command, the product must identify the exact blocker and give the user an optional override path. The repo URL remains the only required input for repos in the declared supported profile.

## Security constraints

- Treat repositories, dependency install scripts, build scripts, and web content as untrusted.
- Use an isolated, disposable runner with CPU, memory, disk, process, network, and wall-clock limits.
- Do not expose platform database credentials, GitHub write credentials, AI provider keys, or other tenants’ data to the runner.
- Use temporary read-only checkout credentials; remove them before package installation and test execution.
- Default to restricted outbound network access; explicitly block cloud metadata and internal platform services.
- Make test secrets optional and separately scoped. Warn before testing destructive or production-impacting workflows.
- Keep evidence access private and authorized; use expiring artifact links and configurable retention.

## Phase 1 acceptance checklist

- [x] Define repo URL as the only normal per-run project input.
- [x] Separate one-time GitHub/private-repo and AI-provider setup from per-run inputs.
- [x] Select a public fixture with documented setup metadata.
- [x] Record supported-profile boundaries and no-guarantee language.
- [x] Set sandbox and credential-isolation requirements.
- [x] Review and approve this scope before starting the foundation/runner implementation.
- [ ] Perform the fixture preflight in an isolated runner once the runner exists; verify automatic detection of Node version, `npm install`, start command, and port/health check.

## Reference links

- Sauce Labs sample app: <https://github.com/saucelabs/sample-app-web>
- Sauce Labs sample app README: <https://github.com/saucelabs/sample-app-web#readme>
- Raw `package.json`: <https://raw.githubusercontent.com/saucelabs/sample-app-web/main/package.json>
- Raw `.nvmrc`: <https://raw.githubusercontent.com/saucelabs/sample-app-web/main/.nvmrc>
