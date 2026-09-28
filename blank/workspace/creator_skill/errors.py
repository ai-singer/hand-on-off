"""Error types for the Creator Skill Factory layer.

Every error extends :class:`creator_contract.CreatorContractError`, so a caller
that already handles contract or projection failures catches skill failures too.
"""

from __future__ import annotations

from creator_contract import CreatorContractError


class SkillError(CreatorContractError):
    """Base class for Creator Skill failures."""


class SkillSchemaError(SkillError):
    """Raised when a skill document does not match the skill schema."""


class SkillIsolationError(SkillError):
    """Raised when a skill carries prompt, model-call, or runtime content.

    A skill is a capability declaration. Execution belongs to the runtime.
    """


class SkillRegistryError(SkillError):
    """Raised when a registry operation is invalid (duplicate, unknown id)."""


class SkillDependencyError(SkillError):
    """Raised when a dependency edge cannot be satisfied."""


class SkillCompositionError(SkillError):
    """Raised when a bundle cannot be composed or fails verification."""


class SkillProvenanceError(SkillError):
    """Raised when a skill has no traceable source."""


__all__ = [
    "SkillCompositionError",
    "SkillDependencyError",
    "SkillError",
    "SkillIsolationError",
    "SkillProvenanceError",
    "SkillRegistryError",
    "SkillSchemaError",
]
