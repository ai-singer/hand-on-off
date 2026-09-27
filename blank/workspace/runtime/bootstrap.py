"""Single initialization entry point for a Creator Agent runtime.

    runtime config
      -> bootstrap()
      -> RuntimeContext
      -> component initialization
      -> agent runtime

Bootstrap owns every cross-check that turns configuration *data* into a
running *selection*: which plugins are constructed, which skills are
discovered and enabled, which executable workflow is bound, and whether the
configured version is compatible with this runtime. Nothing downstream needs
to re-read the configuration or re-resolve a component.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from config.runtime import RuntimeConfig, load_runtime_config
from core import load_plugin
from core.skill_registry import SkillManifest, discover_skills
from plugin_interface.base import CreatorDistillationPlugin
from skills.openclaw import OpenClawSkillAdapter, discover_openclaw_skills

from .context import RuntimeContext, WorkflowBinding
from .errors import RuntimeBootstrapError

#: Runtime configuration contract version implemented by this runtime.
SUPPORTED_CONFIG_VERSION = "1.0.0"

#: Deployable skill packages are OpenClaw adapters under this directory.
SKILL_PACKAGE_PARTS = ("skills", "openclaw")

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def bootstrap(
    config_path: str | Path | None = None,
    workspace_root: str | Path | None = None,
) -> RuntimeContext:
    """Build a validated :class:`RuntimeContext` from runtime configuration.

    ``config_path`` defaults to ``config/runtime/default.json`` and
    ``workspace_root`` defaults to the workspace that contains this package.
    Every failure raises :class:`RuntimeBootstrapError` with the originating
    exception chained as ``__cause__``.
    """

    root = _resolve_workspace_root(workspace_root)
    config = _load_config(config_path)
    _validate_version(config)
    plugins = _load_plugins(config)
    skills = _load_skills(config, root)
    workflow = _load_workflow(config, root)

    return RuntimeContext(
        instance=config.instance.name,
        version=config.version,
        plugins=MappingProxyType(plugins),
        skills=MappingProxyType(skills),
        workflow=workflow,
        config=config,
    )


def _resolve_workspace_root(explicit: str | Path | None) -> Path:
    if explicit is not None:
        root = Path(explicit)
    else:
        root = Path(__file__).resolve().parents[1]
    if not root.is_dir():
        raise RuntimeBootstrapError(f"workspace root is not a directory: {root}")
    return root


def _load_config(config_path: str | Path | None) -> RuntimeConfig:
    try:
        return load_runtime_config(config_path)
    except ValueError as exc:
        raise RuntimeBootstrapError(f"invalid runtime config: {exc}") from exc


def _validate_version(config: RuntimeConfig) -> None:
    """Reject configuration written for an incompatible runtime contract."""

    match = _SEMVER.fullmatch(config.version)
    if match is None:
        raise RuntimeBootstrapError(
            f"runtime config version {config.version!r} is not semantic version X.Y.Z"
        )
    supported_major = int(SUPPORTED_CONFIG_VERSION.split(".", 1)[0])
    if int(match.group(1)) != supported_major:
        raise RuntimeBootstrapError(
            f"runtime config version {config.version!r} is not compatible with "
            f"runtime config contract {SUPPORTED_CONFIG_VERSION!r}"
        )


def _load_plugins(config: RuntimeConfig) -> dict[str, CreatorDistillationPlugin]:
    """Construct exactly the plugins named by `plugins.enabled`."""

    loaded: dict[str, CreatorDistillationPlugin] = {}
    identity_owner: dict[str, str] = {}
    for module_path in config.plugins.enabled:
        try:
            plugin = load_plugin(module_path)
        except Exception as exc:  # plugin construction is an integration boundary
            raise RuntimeBootstrapError(
                f"cannot load configured plugin {module_path!r}: {exc}"
            ) from exc
        identity = plugin.identity.name
        if identity in identity_owner:
            raise RuntimeBootstrapError(
                f"plugin identity {identity!r} is claimed by both "
                f"{identity_owner[identity]!r} and {module_path!r}"
            )
        identity_owner[identity] = module_path
        loaded[module_path] = plugin

    if config.plugins.default not in loaded:
        # load_runtime_config already enforces this; kept as a bootstrap-level
        # invariant so a hand-built RuntimeConfig cannot bypass it.
        raise RuntimeBootstrapError(
            f"plugins.default {config.plugins.default!r} was not loaded"
        )
    return loaded


def _load_skills(
    config: RuntimeConfig, root: Path
) -> dict[str, SkillManifest]:
    """Discover deployable skills and keep exactly `skills.enabled`."""

    package_root = root.joinpath(*SKILL_PACKAGE_PARTS)
    try:
        discovered = discover_skills(package_root)
        adapters = discover_openclaw_skills(package_root)
    except (OSError, ValueError) as exc:
        raise RuntimeBootstrapError(
            f"cannot discover skills under {package_root}: {exc}"
        ) from exc

    missing = [name for name in config.skills.enabled if name not in discovered]
    if missing:
        raise RuntimeBootstrapError(
            "configured skills have no discoverable manifest.json: "
            + ", ".join(missing)
        )

    selected: dict[str, SkillManifest] = {}
    for name in config.skills.enabled:
        manifest = discovered[name]
        _cross_validate_skill(manifest, adapters.get(name))
        selected[name] = manifest
    return selected


def _cross_validate_skill(
    manifest: SkillManifest, adapter: OpenClawSkillAdapter | None
) -> None:
    """Reject drift between a skill manifest and its OpenClaw adapter.

    A skill package may omit `adapter.json`; when present it must agree with
    the manifest, otherwise two sources of truth would disagree at runtime.
    """

    if adapter is None:
        return
    mismatches: list[str] = []
    if manifest.name != adapter.name:
        mismatches.append(f"name {manifest.name!r} != {adapter.name!r}")
    if manifest.version != adapter.version:
        mismatches.append(f"version {manifest.version!r} != {adapter.version!r}")
    if manifest.entrypoint != adapter.entrypoint:
        mismatches.append(
            f"entrypoint {manifest.entrypoint!r} != {adapter.entrypoint!r}"
        )
    if mismatches:
        raise RuntimeBootstrapError(
            f"skill manifest and adapter disagree for {manifest.name!r}: "
            + "; ".join(mismatches)
        )


def _load_workflow(config: RuntimeConfig, root: Path) -> WorkflowBinding:
    configured = Path(config.workflow.default)
    path = configured if configured.is_absolute() else root / configured
    if not path.is_file():
        raise RuntimeBootstrapError(f"workflow definition does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeBootstrapError(
            f"cannot parse workflow definition {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeBootstrapError(f"workflow definition must be an object: {path}")

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise RuntimeBootstrapError(f"workflow definition has no name: {path}")

    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RuntimeBootstrapError(f"workflow definition has no steps: {path}")
    step_ids: list[str] = []
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            raise RuntimeBootstrapError(
                f"workflow step {index} must be an object: {path}"
            )
        step_id = step.get("id")
        command = step.get("command")
        if not isinstance(step_id, str) or not step_id.strip():
            raise RuntimeBootstrapError(
                f"workflow step {index} has no id: {path}"
            )
        if not isinstance(command, str) or not command.strip():
            raise RuntimeBootstrapError(
                f"workflow step {index} ({step_id}) has no command: {path}"
            )
        if step_id in step_ids:
            raise RuntimeBootstrapError(f"duplicate workflow step id {step_id!r}: {path}")
        step_ids.append(step_id)

    return WorkflowBinding(
        name=name.strip(),
        path=path.resolve(),
        steps=tuple(step_ids),
        payload=MappingProxyType(dict(payload)),
    )
