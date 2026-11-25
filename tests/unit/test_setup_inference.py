import json

from testatlas.domain.setup import SetupSnapshot
from testatlas.services.setup_inference import infer_repository_setup

COMMIT_SHA = "a" * 40
SAUCE_PACKAGE_JSON = """
{
  "engines": {"node": ">=24.9.0"},
  "dependencies": {"react": "^19.0.0"},
  "devDependencies": {"vite": "^8.3.5"},
  "scripts": {"start": "vite", "build": "vite build"},
  "volta": {"node": "24.9.0"}
}
"""
VITE_CONFIG = """
export default defineConfig({
  server: {
    port: 3000,
    open: true,
  },
  preview: { port: 3000 },
});
"""


def sample_snapshot(**overrides: object) -> SetupSnapshot:
    values: dict[str, object] = {
        "commit_sha": COMMIT_SHA,
        "root_files": frozenset({"package.json", "package-lock.json", ".nvmrc", "vite.config.js"}),
        "package_json": SAUCE_PACKAGE_JSON,
        "nvmrc": "24.9.0\n",
        "vite_config_path": "vite.config.js",
        "vite_config": VITE_CONFIG,
    }
    values.update(overrides)
    return SetupSnapshot(**values)


def package_without_volta() -> str:
    manifest = json.loads(SAUCE_PACKAGE_JSON)
    manifest.pop("volta")
    return json.dumps(manifest)


def test_infers_sauce_fixture_setup_with_source_evidence() -> None:
    plan = infer_repository_setup(sample_snapshot())

    assert plan.status == "ready"
    assert plan.profile == "node-npm-vite"
    assert plan.commit_sha == COMMIT_SHA
    assert plan.runtime == "node"
    assert plan.runtime_version == "24.9.0"
    assert plan.package_manager == "npm"
    assert plan.install_command == "npm ci"
    assert plan.build_command == "npm run build"
    assert plan.start_command == "npm run start"
    assert plan.port == 3000
    assert plan.health_check_path == "/"
    assert plan.blockers == ()
    assert {entry.source_path for entry in plan.evidence} >= {
        ".nvmrc",
        "package.json#engines.node",
        "package.json#scripts.start",
        "package.json#scripts.build",
        "package-lock.json",
        "vite.config.js",
    }
    assert (
        next(item for item in plan.evidence if item.field == "health_check_path").confidence
        == "low"
    )


def test_does_not_guess_an_exact_node_version_from_an_engine_range() -> None:
    plan = infer_repository_setup(sample_snapshot(nvmrc=None, package_json=package_without_volta()))

    assert plan.status == "needs_review"
    assert plan.runtime_version is None
    assert any("exact Node runtime" in blocker for blocker in plan.blockers)


def test_detects_conflicting_lockfiles_instead_of_choosing_one() -> None:
    plan = infer_repository_setup(
        sample_snapshot(
            root_files=frozenset(
                {"package.json", "package-lock.json", "yarn.lock", ".nvmrc", "vite.config.js"}
            )
        )
    )

    assert plan.status == "unsupported"
    assert plan.package_manager is None
    assert plan.install_command is None
    assert any("Conflicting" in blocker for blocker in plan.blockers)


def test_detects_node_pin_that_conflicts_with_engine_minimum() -> None:
    plan = infer_repository_setup(
        sample_snapshot(nvmrc="20.0.0\n", package_json=package_without_volta())
    )

    assert plan.status == "needs_review"
    assert plan.runtime_version == "20.0.0"
    assert any("does not satisfy" in blocker for blocker in plan.blockers)


def test_missing_lockfile_is_not_reported_as_reproducible() -> None:
    plan = infer_repository_setup(
        sample_snapshot(root_files=frozenset({"package.json", ".nvmrc", "vite.config.js"}))
    )

    assert plan.status == "needs_review"
    assert plan.install_command == "npm install"
    assert any("not reproducible" in blocker for blocker in plan.blockers)


def test_malformed_manifest_is_unsupported_and_never_executed() -> None:
    plan = infer_repository_setup(sample_snapshot(package_json="process.exit(1)"))

    assert plan.status == "unsupported"
    assert plan.start_command is None
    assert any("not valid UTF-8 JSON" in blocker for blocker in plan.blockers)


def test_multiple_server_ports_are_reported_as_ambiguous() -> None:
    config = "export default { server: { port: 3000, port: 4444 } };"
    plan = infer_repository_setup(sample_snapshot(vite_config=config))

    assert plan.status == "needs_review"
    assert plan.port is None
    assert any("Multiple server ports" in blocker for blocker in plan.blockers)


def test_non_npm_lockfile_is_unsupported_for_the_initial_profile() -> None:
    plan = infer_repository_setup(
        sample_snapshot(
            root_files=frozenset({"package.json", "pnpm-lock.yaml", ".nvmrc", "vite.config.js"})
        )
    )

    assert plan.status == "unsupported"
    assert plan.package_manager is None
    assert any("non-npm lockfile" in blocker for blocker in plan.blockers)


def test_uses_volta_exact_pin_and_accepts_pinned_npm_package_manager() -> None:
    manifest = json.loads(SAUCE_PACKAGE_JSON)
    manifest["packageManager"] = "npm@11.6.1"
    plan = infer_repository_setup(sample_snapshot(nvmrc=None, package_json=json.dumps(manifest)))

    assert plan.status == "ready"
    assert plan.runtime_version == "24.9.0"
    assert any(item.source_path == "package.json#volta.node" for item in plan.evidence)
    assert any(item.source_path == "package.json#packageManager" for item in plan.evidence)


def test_conflicting_node_pins_require_review() -> None:
    plan = infer_repository_setup(sample_snapshot(nvmrc="22.0.0\n"))

    assert plan.status == "needs_review"
    assert plan.runtime_version is None
    assert any("different exact Node versions" in blocker for blocker in plan.blockers)


def test_unsupported_package_manager_field_cannot_choose_an_install_command() -> None:
    manifest = json.loads(SAUCE_PACKAGE_JSON)
    manifest["packageManager"] = "pnpm@9.0.0"
    plan = infer_repository_setup(sample_snapshot(package_json=json.dumps(manifest)))

    assert plan.status == "unsupported"
    assert plan.package_manager is None
    assert plan.install_command is None
    assert any("other than a supported npm version" in blocker for blocker in plan.blockers)


def test_non_string_package_manager_and_inexact_node_pin_are_not_coerced() -> None:
    manifest = json.loads(package_without_volta())
    manifest["packageManager"] = 11
    plan = infer_repository_setup(sample_snapshot(package_json=json.dumps(manifest), nvmrc="24\n"))

    assert plan.status == "unsupported"
    assert plan.runtime_version is None
    assert plan.install_command is None
    assert any("exact Node runtime" in blocker for blocker in plan.blockers)


def test_non_object_manifest_is_unsupported() -> None:
    plan = infer_repository_setup(sample_snapshot(package_json="[]"))

    assert plan.status == "unsupported"
    assert any("not a JSON object" in blocker for blocker in plan.blockers)


def test_missing_start_script_and_vite_profile_require_review() -> None:
    manifest = json.loads(SAUCE_PACKAGE_JSON)
    manifest["scripts"].pop("start")
    manifest["devDependencies"].pop("vite")
    plan = infer_repository_setup(
        sample_snapshot(package_json=json.dumps(manifest), vite_config_path=None)
    )

    assert plan.status == "unsupported"
    assert plan.start_command is None
    assert any("No non-empty root" in blocker for blocker in plan.blockers)
    assert any("does not match" in blocker for blocker in plan.blockers)
