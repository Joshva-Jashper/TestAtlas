# Isolated runner: threat model and enablement gates

**Status:** Contract and policy validation only. No Docker adapter is implemented or enabled.
**Execution boundary:** Repository code, dependency installation hooks, generated tests, application behavior, browser content, and returned artifacts are untrusted.

## Assets and trust boundaries

TestAtlas must protect GitHub and AI-provider credentials, platform database/queue/object-store credentials, other tenants' data, the host kernel and control plane, and the integrity of commit-pinned results. The API and orchestration services may validate plans and dispatch work, but must never evaluate repository-defined commands. Only a separately reviewed sandbox backend may execute them.

The current development environment has no Docker CLI or daemon. This phase therefore implements a backend-neutral request/result contract and a fail-closed disabled runner; it does not establish that any container configuration is safe.

## Intended data flow

1. The trusted GitHub metadata service resolves a branch to a full commit SHA and creates an evidence-backed setup plan.
2. A trusted checkout component retrieves only that exact commit. Any short-lived, read-only private-repository capability is used outside the workload and removed before untrusted commands begin.
3. The orchestrator creates a versioned `SandboxRunRequest`. The initial profile translates only the supported npm steps to fixed argv arrays with manifest/lockfile provenance. The request contains no token, secret values, arbitrary environment variables, shell string, branch name, or backend override.
4. A future approved backend provisions an ephemeral constrained environment, verifies the checked-out commit, and executes the steps there. The API and worker do not fall back to local execution if the backend is missing or fails.
5. The backend returns a typed result with the same run ID and commit SHA. Artifact paths, media types, item count, individual sizes, aggregate size, and duration are validated before storage. Artifact bytes remain hostile and require independent scanning/redaction and private storage controls.

## Contract controls implemented now

`src/testatlas/sandbox/contracts.py` validates the initial Node/npm/Vite request shape, full lowercase commit identity, fixed argv/provenance for `npm ci`, optional `npm run build`, and `npm run start`, and exact app port/health-check assumptions. Unknown fields are forbidden. The policy schema requires a digest-pinned image reference, explicit Linux platform, non-root UID, read-only root filesystem, no-new-privileges, dropped capabilities, private user/PID/IPC/network namespaces, and an ephemeral workspace. It rejects privileged mode, host namespaces/mounts, devices, Docker socket access, platform secrets, checkout credentials, and unbounded or wildcard egress entries. Resource metadata is bounded for CPU, memory, processes, wall time, workspace, network bytes/connections, file descriptors, logs, and aggregate artifacts. Result metadata is tied to the requested run and commit. `DisabledSandboxRunner` raises an explicit disabled error and never starts a local process.

These checks validate a data contract only. A Pydantic object cannot enforce kernel isolation, network policy, credential removal, quota enforcement, image provenance, or cleanup. A passing contract test is not evidence that a Docker backend is safe.

## Backend requirements before enabling execution

- **Immutable source and image identity:** fetch and verify the full commit SHA immediately before execution; reject mismatch rather than re-resolving a branch. Use approved OCI images by immutable digest and platform/architecture. Verify provenance and update images through a reviewed process. Treat repository Dockerfiles and compose files as evidence only; never build or run them as trusted platform configuration.
- **Credential separation:** no platform, tenant, AI-provider, GitHub-write, or broad artifact credentials in the workload. A private checkout capability must be short-lived, read-only, repository-scoped, used only by the trusted checkout component, and unavailable to install/start/test steps. If tests later need credentials, they must be explicit, least-privilege, separately scoped, and redacted from every output.
- **Network isolation:** default deny egress. If dependency access is required, force traffic through a trusted enforcing proxy with exact approved destinations and byte/connection/time budgets. Enforcement must block IPv4 and IPv6 loopback, private, link-local, host, control-plane, and cloud-metadata destinations at connection time; defend against DNS rebinding, redirects, alternate protocols, and direct-egress bypass. A hostname allowlist in the request model is not an egress firewall.
- **Filesystem and process isolation:** run as a non-root UID with no-new-privileges, all Linux capabilities dropped, a restrictive seccomp/AppArmor/SELinux policy, read-only root filesystem, and only an ephemeral quota-limited writable workspace/tmpfs. Do not mount host paths, devices, the Docker socket, or shared tenant data. Use separate PID, IPC, and network namespaces; validate symlink and path boundaries when exporting artifacts.
- **Hard resource and output limits:** enforce CPU, memory, disk, process/thread count, network bytes/connections, open files, wall-clock deadline, log size, artifact count, per-artifact size, and aggregate evidence size outside the untrusted process. Add per-step ceilings, concurrency/quota controls, and bounded retries. Record limit exhaustion as a distinct outcome.
- **Command handling:** pass argv arrays, fixed working directories, and provenance. Never interpolate a shell string or accept an AI/repository/README/API caller command override. Still treat `npm ci`, its lifecycle hooks, `npm run start`, and later test commands as arbitrary code; fixed argv reduces command-injection risk but does not make those programs trusted.
- **Cancellation and teardown:** cancellation must reach the backend, terminate the full process tree, stop later steps/uploads, revoke temporary capabilities, and clean up workspace/container/network state. Enforce deadlines and cleanup independently of a surviving worker; reconcile stale runs rather than blindly re-dispatching them.
- **Evidence handling:** treat file names, symlinks, media types, logs, screenshots, traces, and reports as hostile. Validate path containment and types, redact secrets, cap and explicitly mark truncated output, store privately with tenant checks and expiring links, and enforce retention/deletion. Do not trust runner-reported counters without backend-side bounds and identity checks.

## Required validation before fixture preflight

A future Docker/backend adapter remains blocked until an independent review verifies deployment settings and a disposable adversarial test environment demonstrates: no credential observability; no direct egress or metadata access, including IPv6 and DNS-rebinding cases; isolation from host, control plane, and other tenants; hard resource limits under load; image/runtime identity; descendant cancellation and cleanup after worker/backend failure; and bounded private artifact handling. Only after those gates pass should the pinned Sauce Labs commit be used for the first controlled preflight. That preflight must verify runtime provisioning, `npm ci`, startup, port/health check, cancellation, and teardown.

Until then, execution is disabled. No fixture code, dependency installation, or repository-defined command has been run by this phase.
