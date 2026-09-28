"""Error types for the Creator Projection layer.

Every projection error extends :class:`creator_contract.CreatorContractError`, so
a caller that already handles contract failures catches projection failures too,
and a failed projection is never mistaken for a runtime bug.
"""

from __future__ import annotations

from creator_contract import CreatorContractError


class ProjectionError(CreatorContractError):
    """Base class for projection failures."""


class ProjectionAssetError(ProjectionError):
    """Raised when the asset registry is malformed or an asset is unknown."""


class ProjectionAssetUnavailableError(ProjectionError):
    """Raised when a mapper requires an asset that is not available.

    Catching this error is how a caller distinguishes "the projection is wrong"
    from "the capability does not exist yet".
    """


class ProjectionParseError(ProjectionError):
    """Raised when a Markdown or YAML document cannot be parsed structurally."""


class ProjectionCapabilityError(ProjectionError):
    """Raised when the projection would claim a capability that does not exist."""


class ProjectionProvenanceError(ProjectionError):
    """Raised when a projected field cannot be traced to a declared asset."""


__all__ = [
    "ProjectionAssetError",
    "ProjectionAssetUnavailableError",
    "ProjectionCapabilityError",
    "ProjectionError",
    "ProjectionParseError",
    "ProjectionProvenanceError",
]
