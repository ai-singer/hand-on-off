"""Discovery and loading for OpenClaw Skill adapters."""

from .adapter_registry import (
    OpenClawSkillAdapter,
    discover_openclaw_skills,
    load_openclaw_skill,
)

__all__ = [
    "OpenClawSkillAdapter",
    "discover_openclaw_skills",
    "load_openclaw_skill",
]
