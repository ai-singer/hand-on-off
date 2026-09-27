"""Immutable runtime context produced by the Creator Agent bootstrap.

`RuntimeContext` is the only runtime entry point a caller needs after
initialization: every component the runtime configuration selected is already
resolved, validated and reachable from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from config.runtime import RuntimeConfig
from core.skill_registry import SkillManifest
from plugin_interface.base import CreatorDistillationPlugin


@dataclass(frozen=True, slots=True)
class WorkflowBinding:
    """The executable workflow selected by the runtime configuration."""

    name: str
    path: Path
    steps: tuple[str, ...]
    payload: Mapping[str, Any]

    def step_ids(self) -> tuple[str, ...]:
        return self.steps


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    """Validated runtime state returned by `runtime.bootstrap.bootstrap()`.

    Fields mirror the runtime configuration one-to-one:

    - `instance`   <- `instance.name`
    - `version`    <- `version` (after compatibility validation)
    - `plugins`    <- `plugins.enabled`, keyed by configured module path
    - `skills`     <- `skills.enabled`, keyed by configured skill name
    - `workflow`   <- `workflow.default`, parsed and structurally validated
    - `config`     <- the immutable `RuntimeConfig` this context was built from
    """

    instance: str
    version: str
    plugins: Mapping[str, CreatorDistillationPlugin]
    skills: Mapping[str, SkillManifest]
    workflow: WorkflowBinding
    config: RuntimeConfig

    @property
    def default_plugin(self) -> CreatorDistillationPlugin:
        """The plugin configured as `plugins.default`."""

        return self.plugins[self.config.plugins.default]

    def plugin(self, module_path: str) -> CreatorDistillationPlugin:
        """Return a configured plugin by module path."""

        try:
            return self.plugins[module_path]
        except KeyError as exc:
            raise KeyError(f"plugin is not enabled by the runtime config: {module_path}") from exc

    def skill(self, name: str) -> SkillManifest:
        """Return a configured skill manifest by name."""

        try:
            return self.skills[name]
        except KeyError as exc:
            raise KeyError(f"skill is not enabled by the runtime config: {name}") from exc
