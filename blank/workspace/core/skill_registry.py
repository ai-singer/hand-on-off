"""Discovery for independently versioned workspace skill packages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SkillManifest:
    name: str
    version: str
    entrypoint: str
    capabilities: tuple[str, ...]
    test_command: str
    package_dir: Path


def discover_skills(skills_root: str | Path) -> dict[str, SkillManifest]:
    """Discover skill manifests without importing or executing skill code."""

    root = Path(skills_root)
    discovered: dict[str, SkillManifest] = {}
    if not root.exists():
        return discovered

    for path in sorted(root.glob("*/manifest.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        required = {"name", "version", "entrypoint", "capabilities", "test_command"}
        missing = required - payload.keys()
        if missing:
            raise ValueError(
                f"{path} is missing manifest fields: {', '.join(sorted(missing))}"
            )
        entrypoint = path.parent / payload["entrypoint"]
        if not entrypoint.is_file():
            raise ValueError(f"skill entrypoint does not exist: {entrypoint}")
        manifest = SkillManifest(
            name=payload["name"],
            version=payload["version"],
            entrypoint=payload["entrypoint"],
            capabilities=tuple(payload["capabilities"]),
            test_command=payload["test_command"],
            package_dir=path.parent,
        )
        if manifest.name in discovered:
            raise ValueError(f"duplicate skill name: {manifest.name}")
        discovered[manifest.name] = manifest
    return discovered
