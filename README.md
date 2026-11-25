# TestAtlas

**AI-assisted testing for GitHub repositories.** Give TestAtlas a repository link; it discovers how the app is built, attempts to start it in an isolated environment, maps testable modules, generates tests, runs them, and reports failures with evidence.

## Product promise

The normal run should require only a GitHub repository URL. Public repositories can be inspected without connecting GitHub. Private repositories require GitHub authorization. After the account has an AI provider configured, a user should not have to provide a deployed URL or manually type build/start commands for supported projects.

TestAtlas should infer project setup from repository files such as manifests, lockfiles, runtime-version files, Dockerfiles, CI workflows, and README instructions. If it cannot safely determine or satisfy a prerequisite, it should explain the blocker and ask only for the missing information.

## User run choices

- **Hosted run:** click **Run** in the dashboard and receive results and evidence there.
- **Local run:** download a portable pytest/Playwright test bundle and run it on the user's own machine or CI.

The downloadable artifact is the generated test suite and its runner configuration, not the proprietary source code of the TestAtlas hosted service.

## Planned stack

Python-first platform: FastAPI, PydanticAI, pytest, Playwright for Python, PostgreSQL, Redis-backed background jobs, object storage for evidence, and disposable isolated test-runner containers.

## Current milestone

Phase 1 is defining a repo-link-only workflow and validating the setup/discovery assumptions with a public fixture. See [Phase 1 scope and acceptance criteria](docs/phase-1-scope.md).

## Important boundary

A run reports what TestAtlas discovered and tested, plus items blocked or left uncovered. It does not claim complete coverage of every possible behavior. Repository code is untrusted and must execute only in a constrained disposable environment.
