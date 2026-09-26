"""Dependency-free loader for instance-owned runtime configuration."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class InstanceConfig:
    name: str


@dataclass(frozen=True, slots=True)
class WorkflowConfig:
    default: str


@dataclass(frozen=True, slots=True)
class PluginConfig:
    enabled: tuple[str, ...]
    default: str


@dataclass(frozen=True, slots=True)
class SkillConfig:
    enabled: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    instance: InstanceConfig
    workflow: WorkflowConfig
    plugins: PluginConfig
    skills: SkillConfig
    version: str
    source_path: Path


def load_runtime_config(path: str | Path | None = None) -> RuntimeConfig:
    config_path = Path(path) if path is not None else _default_config_path()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read runtime config {config_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("runtime config root must be an object")

    instance = _require_mapping(payload, "instance")
    workflow = _require_mapping(payload, "workflow")
    plugins = _require_mapping(payload, "plugins")
    skills = _require_mapping(payload, "skills")

    instance_name = _require_string(instance, "name")
    default_workflow = _require_string(workflow, "default")
    enabled_plugins = _require_string_list(plugins, "enabled")
    default_plugin = _require_string(plugins, "default")
    enabled_skills = _require_string_list(skills, "enabled")
    version = _require_string(payload, "version")

    if default_plugin not in enabled_plugins:
        raise ValueError("plugins.default must be present in plugins.enabled")
    if not _SEMVER.fullmatch(version):
        raise ValueError("version must use semantic version format X.Y.Z")
    invalid_skills = [name for name in enabled_skills if not _SKILL_NAME.fullmatch(name)]
    if invalid_skills:
        raise ValueError(
            "skills.enabled contains invalid OpenClaw skill names: "
            + ", ".join(invalid_skills)
        )

    return RuntimeConfig(
        instance=InstanceConfig(name=instance_name),
        workflow=WorkflowConfig(default=default_workflow),
        plugins=PluginConfig(
            enabled=tuple(enabled_plugins),
            default=default_plugin,
        ),
        skills=SkillConfig(enabled=tuple(enabled_skills)),
        version=version,
        source_path=config_path.resolve(),
    )


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"runtime config field {key!r} must be an object")
    return value


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"runtime config field {key!r} must be a non-empty string")
    return value.strip()


def _require_string_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"runtime config field {key!r} must be a non-empty array")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(
            f"runtime config field {key!r} must contain non-empty strings"
        )
    normalized = [item.strip() for item in value]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"runtime config field {key!r} must not contain duplicates")
    return normalized


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "default.json"
