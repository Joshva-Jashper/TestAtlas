# Sauce Labs fixture setup evidence

**Checked:** 2026-11-25 using TestAtlas' public, unauthenticated repository-inspection endpoint.
**Repository:** `saucelabs/sample-app-web`
**Commit inspected:** `d5cd655fa8a974f4ddb6fde2868586e0084211d2`

The endpoint returned HTTP 200 and a `ready` static setup plan for the initial `node-npm-vite` profile. It resolved the `main` branch to the commit above, then requested bounded repository metadata and root setup-file contents pinned to that SHA. It did not clone the repository, install dependencies, evaluate configuration, or run repository code.

At the inspected commit, GitHub's root listing contains `package-lock.json`; the package manifest declares Node compatibility `>=24.9.0`, a `start` script of `vite`, a `build` script of `vite build`, and Vite as a development dependency. The root `.nvmrc` pins Node `24.9.0`. The Vite configuration statically declares server port `3000`. TestAtlas therefore inferred `npm ci`, `npm run start`, `npm run build`, and port `3000`. The inferred `/` health-check path is low-confidence and is only a preflight assumption; no endpoint health check has been performed.

## Commit-pinned sources

- [Commit inspected](https://github.com/saucelabs/sample-app-web/commit/d5cd655fa8a974f4ddb6fde2868586e0084211d2)
- [Root listing at the inspected commit](https://github.com/saucelabs/sample-app-web/tree/d5cd655fa8a974f4ddb6fde2868586e0084211d2)
- [`package.json`](https://github.com/saucelabs/sample-app-web/blob/d5cd655fa8a974f4ddb6fde2868586e0084211d2/package.json)
- [`.nvmrc`](https://github.com/saucelabs/sample-app-web/blob/d5cd655fa8a974f4ddb6fde2868586e0084211d2/.nvmrc)
- [`vite.config.js`](https://github.com/saucelabs/sample-app-web/blob/d5cd655fa8a974f4ddb6fde2868586e0084211d2/vite.config.js)

This validates metadata and setup inference only. A real preflight and any test execution remain blocked until TestAtlas has a separately designed, reviewed, disposable isolated runner with appropriate resource and network controls.
