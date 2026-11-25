# TestAtlas

**AI-assisted testing for GitHub repositories.** The product goal is to accept a repository link, discover and test supported applications, and report failures with evidence. The current implementation is limited to safe repository inspection and static setup inference; execution, test generation, and the dashboard are future milestones.

## Product promise

The normal run should require only a GitHub repository URL. Public repositories can be inspected without connecting GitHub. Private repositories require GitHub authorization. After the account has an AI provider configured, a user should not have to provide a deployed URL or manually type build/start commands for supported projects.

TestAtlas should infer project setup from repository files such as manifests, lockfiles, runtime-version files, Dockerfiles, CI workflows, and README instructions. If it cannot safely determine or satisfy a prerequisite, it should explain the blocker and ask only for the missing information.

## User run choices

- **Hosted run:** click **Run** in the dashboard and receive results and evidence there.
- **Local run:** download a portable pytest/Playwright test bundle and run it on the user's own machine or CI.

The downloadable artifact is the generated test suite and its runner configuration, not the proprietary source code of the TestAtlas hosted service.

## Planned stack

Python-first platform: FastAPI, PydanticAI, pytest, Playwright for Python, PostgreSQL, Redis-backed background jobs, object storage for evidence, and disposable isolated test-runner containers.

## Local development

Use Python 3.12 and `uv`. From the repository root:

```bash
uv sync --extra dev
uv run uvicorn testatlas.main:app --reload
```

The current inspection endpoint is `POST /api/v1/repositories/inspect`. Example body:

```json
{"repository_url":"https://github.com/saucelabs/sample-app-web"}
```

Run the same core checks used by CI with:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest --cov=testatlas --cov-report=term-missing --cov-fail-under=95 -q
```

## Current milestone

The current endpoint validates a GitHub repository URL, reads public repository metadata from GitHub's fixed API origin, resolves the default branch to a commit SHA, and reads only bounded root setup files at that commit. For the initial Node/npm/Vite profile it returns an evidence-backed static plan, including runtime version, lockfile-based install strategy, declared build/start scripts, and a statically detected Vite port. Unsupported or ambiguous cases return blockers for review.

This is not a preflight: no repository is cloned, no dependency is installed, no configuration or script is evaluated, and no repository code is executed. A backend-neutral, fail-closed runner request/result contract and security threat model are now documented, but there is no Docker executor and execution remains disabled. Private-repository authorization, run persistence/orchestration, generated tests, runtime results/evidence capture, and the dashboard are not implemented yet. See the [runner threat model and enablement gates](docs/runner-threat-model.md) and the [fixture setup evidence](docs/fixture-setup-evidence.md).

See [Phase 1 scope and acceptance criteria](docs/phase-1-scope.md), [runner threat model](docs/runner-threat-model.md), [fixture setup evidence](docs/fixture-setup-evidence.md), and [implementation TODO](TODO.md).

## Important boundary

A run reports what TestAtlas discovered and tested, plus items blocked or left uncovered. It does not claim complete coverage of every possible behavior. Repository code is untrusted and must execute only in a constrained disposable environment.
