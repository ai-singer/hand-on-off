"""Error types for the Skill Bundle → Creator Instance mapping layer.

Every error extends :class:`creator_contract.CreatorContractError`, so a caller
that already handles contract, projection or skill failures catches a mapping
failure too.
"""

from __future__ import annotations

from creator_contract import CreatorContractError


class MappingError(CreatorContractError):
    """Base class for mapping failures."""


class MappingAssetError(MappingError):
    """Raised when a skill's bound asset cannot be resolved or read."""


class MappingRuleError(MappingError):
    """Raised when a rule is malformed or a target path cannot be written."""


class MappingCompletenessError(MappingError):
    """Raised when a bundle skill has no mapping, or a module has no source."""


class MappingHonestyError(MappingError):
    """Raised when an unavailable capability is presented as available.

    The C0.1/C0.2/C0.3 principle: a declaration must never claim a capability
    that does not exist. Auto-filling an unavailable capability is the exact
    failure this error exists to prevent.
    """


class MappingProvenanceError(MappingError):
    """Raised when an instance field cannot be traced to a skill, asset and rule."""


__all__ = [
    "MappingAssetError",
    "MappingCompletenessError",
    "MappingError",
    "MappingHonestyError",
    "MappingProvenanceError",
    "MappingRuleError",
]
