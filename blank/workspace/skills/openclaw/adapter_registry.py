"""Strict metadata registry for deployable OpenClaw Skill adapters."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True, slots=True)
class OpenClawSkillAdapter:
    metadata: Mapping[str, Any]
    version: str
    description: str
    entrypoint: str
    dependencies: tuple[str, ...]
    runtime_requirements: Mapping[str, Any]
    test: str
    package_dir: Path

    @property
    def name(self) -> str:
        return str(self.metadata["name"])

    def load_instructions(self) -> str:
        return (self.package_dir / self.entrypoint).read_text(encoding="utf-8")


def discover_openclaw_skills(
    root: str | Path | None = None,
) -> dict[str, OpenClawSkillAdapter]:
    adapter_root = Path(root) if root is not None else Path(__file__).resolve().parent
    discovered: dict[str, OpenClawSkillAdapter] = {}
    for path in sorted(adapter_root.glob("*/adapter.json")):
        adapter = _load_adapter(path)
        if adapter.name in discovered:
            raise ValueError(f"duplicate OpenClaw Skill adapter: {adapter.name}")
        discovered[adapter.name] = adapter
    return discovered


def load_openclaw_skill(
    name: str, root: str | Path | None = None
) -> OpenClawSkillAdapter:
    skills = discover_openclaw_skills(root)
    try:
        return skills[name]
    except KeyError as exc:
        raise KeyError(f"unknown OpenClaw Skill adapter: {name}") from exc


def _load_adapter(path: Path) -> OpenClawSkillAdapter:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "metadata",
        "version",
        "description",
        "entrypoint",
        "dependencies",
        "runtime_requirements",
        "test",
    }
    missing = required - payload.keys()
    if missing:
        raise ValueError(
            f"{path} is missing adapter fields: {', '.join(sorted(missing))}"
        )
    metadata = payload["metadata"]
    if not isinstance(metadata, dict):
        raise ValueError(f"{path} metadata must be an object")
    name = metadata.get("name")
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise ValueError(f"{path} has an invalid OpenClaw Skill name")
    version = payload["version"]
    if not isinstance(version, str) or not _SEMVER.fullmatch(version):
        raise ValueError(f"{path} has an invalid semantic version")
    entrypoint = payload["entrypoint"]
    entrypoint_path = path.parent / entrypoint
    if not entrypoint_path.is_file():
        raise ValueError(f"Skill adapter entrypoint does not exist: {entrypoint_path}")
    instructions = entrypoint_path.read_text(encoding="utf-8")
    if f"name: {name}" not in instructions:
        raise ValueError(f"{entrypoint_path} frontmatter name does not match {name}")
    dependencies = payload["dependencies"]
    if not isinstance(dependencies, list):
        raise ValueError(f"{path} dependencies must be an array")
    if not isinstance(payload["runtime_requirements"], dict):
        raise ValueError(f"{path} runtime_requirements must be an object")
    test = payload["test"]
    if not isinstance(test, str) or not test.strip():
        raise ValueError(f"{path} test must be a non-empty command")
    return OpenClawSkillAdapter(
        metadata=dict(metadata),
        version=version,
        description=str(payload["description"]),
        entrypoint=str(entrypoint),
        dependencies=tuple(str(item) for item in dependencies),
        runtime_requirements=dict(payload["runtime_requirements"]),
        test=test,
        package_dir=path.parent,
    )
