"""Error types for the Creator Instance Contract layer."""

from __future__ import annotations

from core.errors import ArtifactValidationError


class CreatorContractError(ArtifactValidationError):
    """Raised when a Creator Instance document is invalid.

    Subclasses :class:`core.errors.ArtifactValidationError` so existing callers
    that already handle artifact validation failures keep working unchanged, and
    so a contract failure is never mistaken for a runtime bug.
    """


class CreatorContractSchemaError(CreatorContractError):
    """Raised when the contract schema itself cannot be read or is malformed."""


class CreatorContractIsolationError(CreatorContractError):
    """Raised when an instance contains code or runtime behaviour.

    An instance is configuration. Code, model calls, crawling and publishing
    belong to the runtime and its injected adapters, never to an instance
    document.
    """


class CreatorContractDependencyError(CreatorContractError):
    """Raised when a cross-module reference inside an instance does not resolve."""


__all__ = [
    "CreatorContractDependencyError",
    "CreatorContractError",
    "CreatorContractIsolationError",
    "CreatorContractSchemaError",
]
