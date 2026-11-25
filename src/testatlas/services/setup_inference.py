from __future__ import annotations

import json
import re
from typing import Any

from testatlas.domain.setup import RepositorySetupPlan, SetupEvidence, SetupSnapshot

_EXACT_NODE_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_NODE_MINIMUM = re.compile(r"^\s*>=\s*v?(\d+)\.(\d+)\.(\d+)\s*$")
_SERVER_BLOCK = re.compile(r"\bserver\s*:\s*\{(?P<body>[^{}]{0,4096})\}", re.DOTALL)
_SERVER_PORT_VALUE = re.compile(r"\bport\s*:\s*(\d{1,5})")
_VITE_CONFIG = re.compile(r"^vite\.config\.(?:[cm]?[jt]s)$")


def _exact_node_version(value: str | None) -> str | None:
    if value is None:
        return None
    match = _EXACT_NODE_VERSION.fullmatch(value.strip())
    if match is None:
        return None
    return ".".join(match.groups())


def _is_npm_package_manager(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value == "npm" or re.fullmatch(r"npm@\d+\.\d+\.\d+(?:\+[^\s]+)?", value) is not None


def infer_repository_setup(snapshot: SetupSnapshot) -> RepositorySetupPlan:
    """Infer a conservative initial setup plan from bounded file contents and names."""
    evidence: list[SetupEvidence] = []
    blockers: list[str] = list(snapshot.warnings)
    blockers.extend(
        f"Could not inspect {path} within the configured file-size or text limits."
        for path in snapshot.unreadable_files
    )

    manifest: dict[str, Any] | None = None
    if snapshot.package_json is None:
        blockers.append("A root package.json was not available for setup inference.")
    else:
        try:
            parsed = json.loads(snapshot.package_json)
            if isinstance(parsed, dict):
                manifest = parsed
            else:
                blockers.append("The root package.json is not a JSON object.")
        except (json.JSONDecodeError, UnicodeDecodeError):
            blockers.append("The root package.json is not valid UTF-8 JSON.")

    if manifest is None:
        return RepositorySetupPlan(
            status="unsupported",
            commit_sha=snapshot.commit_sha,
            evidence=tuple(evidence),
            blockers=tuple(dict.fromkeys(blockers)),
        )

    scripts = manifest.get("scripts")
    scripts = scripts if isinstance(scripts, dict) else {}
    dependencies = manifest.get("dependencies")
    dev_dependencies = manifest.get("devDependencies")
    dependencies = dependencies if isinstance(dependencies, dict) else {}
    dev_dependencies = dev_dependencies if isinstance(dev_dependencies, dict) else {}
    engines = manifest.get("engines")
    engines = engines if isinstance(engines, dict) else {}
    volta = manifest.get("volta")
    volta = volta if isinstance(volta, dict) else {}

    npm_lockfiles = {
        name for name in ("package-lock.json", "npm-shrinkwrap.json") if name in snapshot.root_files
    }
    other_lockfiles = {
        name for name in ("pnpm-lock.yaml", "yarn.lock") if name in snapshot.root_files
    }
    package_manager_field = manifest.get("packageManager")
    if npm_lockfiles and other_lockfiles:
        package_manager = None
        install_command = None
        blockers.append(
            "Conflicting npm and non-npm lockfiles were found; package-manager selection "
            "is ambiguous."
        )
    elif npm_lockfiles:
        package_manager = "npm"
        lock_file = (
            "npm-shrinkwrap.json" if "npm-shrinkwrap.json" in npm_lockfiles else "package-lock.json"
        )
        install_command = "npm ci"
        evidence.append(
            SetupEvidence(
                field="package_manager",
                value="npm",
                source_path=lock_file,
                confidence="high",
                note="An npm lockfile is present; npm ci is selected for a lockfile-based install.",
            )
        )
    elif other_lockfiles:
        package_manager = None
        install_command = None
        blockers.append(
            "A non-npm lockfile was detected; this initial profile supports npm lockfiles only."
        )
    else:
        package_manager = "npm"
        install_command = "npm install"
        blockers.append(
            "No npm lockfile was found, so dependency installation is not reproducible."
        )
        evidence.append(
            SetupEvidence(
                field="package_manager",
                value="npm (tentative)",
                source_path="package.json",
                confidence="low",
                note="No lockfile identifies a package-manager install strategy.",
            )
        )

    if package_manager_field is not None and not _is_npm_package_manager(package_manager_field):
        blockers.append(
            "package.json declares a package manager other than a supported npm version."
        )
        package_manager = None
        install_command = None
    elif package_manager_field is not None:
        evidence.append(
            SetupEvidence(
                field="package_manager",
                value=str(package_manager_field)[:128],
                source_path="package.json#packageManager",
                confidence="high",
            )
        )

    nvmrc_version = _exact_node_version(snapshot.nvmrc)
    volta_version = _exact_node_version(volta.get("node"))
    if nvmrc_version and volta_version and nvmrc_version != volta_version:
        blockers.append(".nvmrc and package.json#volta declare different exact Node versions.")
        runtime_version = None
    else:
        runtime_version = nvmrc_version or volta_version

    if runtime_version:
        runtime_source = ".nvmrc" if nvmrc_version else "package.json#volta.node"
        evidence.append(
            SetupEvidence(
                field="runtime_version",
                value=runtime_version,
                source_path=runtime_source,
                confidence="high",
                note="An exact Node version is declared in the repository.",
            )
        )
        runtime = "node"
        evidence.append(
            SetupEvidence(
                field="runtime",
                value="Node.js",
                source_path=runtime_source,
                confidence="high",
            )
        )
    else:
        runtime = None
        blockers.append(
            "An exact Node runtime version was not found; the runner must not guess one."
        )

    node_engine = engines.get("node")
    if isinstance(node_engine, str) and len(node_engine) <= 256:
        evidence.append(
            SetupEvidence(
                field="runtime_constraint",
                value=node_engine,
                source_path="package.json#engines.node",
                confidence="high",
                note="This is a compatibility range, not an exact runtime selection.",
            )
        )
        minimum_match = _NODE_MINIMUM.fullmatch(node_engine)
        version_match = _EXACT_NODE_VERSION.fullmatch(runtime_version or "")
        if minimum_match and version_match:
            minimum = tuple(int(component) for component in minimum_match.groups())
            selected = tuple(int(component) for component in version_match.groups())
            if selected < minimum:
                blockers.append(
                    "The exact Node version does not satisfy package.json#engines.node."
                )

    start_script = scripts.get("start")
    if isinstance(start_script, str) and start_script.strip():
        start_command = "npm run start"
        evidence.append(
            SetupEvidence(
                field="start_command",
                value=start_command,
                source_path="package.json#scripts.start",
                confidence="high",
                note=(
                    "The command is represented as an npm script; its code is not executed "
                    "during inference."
                ),
            )
        )
    else:
        start_command = None
        blockers.append("No non-empty root package.json start script was found.")

    build_script = scripts.get("build")
    build_command = (
        "npm run build" if isinstance(build_script, str) and build_script.strip() else None
    )
    if build_command:
        evidence.append(
            SetupEvidence(
                field="build_command",
                value=build_command,
                source_path="package.json#scripts.build",
                confidence="high",
            )
        )

    vite_config_path = snapshot.vite_config_path
    has_vite_config = bool(vite_config_path and _VITE_CONFIG.fullmatch(vite_config_path))
    has_vite_dependency = "vite" in dependencies or "vite" in dev_dependencies
    is_vite = has_vite_config and (has_vite_dependency or "vite" in str(start_script))
    if is_vite:
        evidence.append(
            SetupEvidence(
                field="framework",
                value="Vite",
                source_path=vite_config_path or "package.json",
                confidence="high",
            )
        )
    else:
        blockers.append("The repository does not match the initial Vite-based web-app profile.")

    port: int | None = None
    if snapshot.vite_config and has_vite_config:
        port_declarations = [
            int(value)
            for block in _SERVER_BLOCK.finditer(snapshot.vite_config)
            for value in _SERVER_PORT_VALUE.findall(block.group("body"))
        ]
        if len(port_declarations) == 1 and 1 <= port_declarations[0] <= 65535:
            port = port_declarations[0]
            evidence.append(
                SetupEvidence(
                    field="port",
                    value=str(port),
                    source_path=vite_config_path or "vite.config.js",
                    confidence="high",
                    note=(
                        "Read from the Vite server configuration; configuration code was not "
                        "evaluated."
                    ),
                )
            )
        elif len(port_declarations) > 1:
            blockers.append(
                "Multiple server ports were found in the Vite config; the port is ambiguous."
            )
    if port is None:
        blockers.append("A supported server port was not statically identified in the Vite config.")

    health_check_path: str | None = None
    if port is not None and is_vite:
        health_check_path = "/"
        evidence.append(
            SetupEvidence(
                field="health_check_path",
                value="/",
                source_path="inference",
                confidence="low",
                note="The app root is a preflight assumption, not a verified health endpoint.",
            )
        )

    ready = (
        package_manager == "npm"
        and install_command == "npm ci"
        and runtime == "node"
        and runtime_version is not None
        and start_command is not None
        and is_vite
        and port is not None
        and not blockers
    )
    if ready:
        status = "ready"
        profile = "node-npm-vite"
    elif package_manager is None or not is_vite:
        status = "unsupported"
        profile = None
    else:
        status = "needs_review"
        profile = "node-npm-vite"

    return RepositorySetupPlan(
        status=status,
        profile=profile,
        commit_sha=snapshot.commit_sha,
        runtime=runtime,
        runtime_version=runtime_version,
        package_manager=package_manager,
        install_command=install_command,
        build_command=build_command,
        start_command=start_command,
        port=port,
        health_check_path=health_check_path,
        evidence=tuple(evidence),
        blockers=tuple(dict.fromkeys(blockers)),
    )
