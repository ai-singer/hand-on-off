"""Error types for the Creator Instance Loader.

Every error extends :class:`creator_contract.CreatorContractError`, so a caller
that already handles contract, projection, skill or mapping failures catches a
loader failure too.

Each error carries a **machine-readable code** as its first argument, so a caller
can branch on ``INSTANCE_FIELD_MISSING`` rather than parse a message.
"""

from __future__ import annotations

from creator_contract import CreatorContractError

#: Error codes the loader may raise. Stable strings, safe to match on.
INSTANCE_NOT_FOUND = "INSTANCE_NOT_FOUND"
INSTANCE_NOT_A_DIRECTORY = "INSTANCE_NOT_A_DIRECTORY"
INSTANCE_UNREADABLE = "INSTANCE_UNREADABLE"
INSTANCE_FIELD_MISSING = "INSTANCE_FIELD_MISSING"
INSTANCE_MODULE_MISSING = "INSTANCE_MODULE_MISSING"
INSTANCE_PROVENANCE_MODULE_MISSING = "INSTANCE_PROVENANCE_MODULE_MISSING"
INSTANCE_SCHEMA_INVALID = "INSTANCE_SCHEMA_INVALID"
INSTANCE_CONTRACT_INVALID = "INSTANCE_CONTRACT_INVALID"
INSTANCE_PROVENANCE_INVALID = "INSTANCE_PROVENANCE_INVALID"
INSTANCE_CAPABILITY_INVALID = "INSTANCE_CAPABILITY_INVALID"
INSTANCE_ASSET_REFERENCE_INVALID = "INSTANCE_ASSET_REFERENCE_INVALID"
INSTANCE_DIFF_INVALID = "INSTANCE_DIFF_INVALID"
INSTANCE_IMMUTABLE = "INSTANCE_IMMUTABLE"

#: Every code, for a test that asserts the set is stable.
ERROR_CODES: tuple[str, ...] = (
    INSTANCE_NOT_FOUND,
    INSTANCE_NOT_A_DIRECTORY,
    INSTANCE_UNREADABLE,
    INSTANCE_FIELD_MISSING,
    INSTANCE_MODULE_MISSING,
    INSTANCE_PROVENANCE_MODULE_MISSING,
    INSTANCE_SCHEMA_INVALID,
    INSTANCE_CONTRACT_INVALID,
    INSTANCE_PROVENANCE_INVALID,
    INSTANCE_CAPABILITY_INVALID,
    INSTANCE_ASSET_REFERENCE_INVALID,
    INSTANCE_DIFF_INVALID,
    INSTANCE_IMMUTABLE,
)


class LoaderError(CreatorContractError):
    """Base class for loader failures. ``args[0]`` begins with a stable error code.

    ``codes`` lists every code the class may raise, so a caller can branch on a
    machine-readable string rather than parse a message.
    """

    code = "INSTANCE_ERROR"

    #: All codes this class may carry. Subclasses usually declare exactly one.
    codes: tuple[str, ...] = ()

    def __init__(self, message: str, *, detail: str = "", code: str = "") -> None:
        self.detail = detail
        if code:
            self.code = code
        text = f"[{self.code}] {message}"
        if detail:
            text = f"{text}: {detail}"
        super().__init__(text)


class InstanceNotFoundError(LoaderError):
    """The path does not exist, or is not a directory.

    Carries :data:`INSTANCE_NOT_A_DIRECTORY` as well as :data:`INSTANCE_NOT_FOUND`
    when the path exists but is neither a directory nor a JSON document, so a caller
    can tell "nothing there" from "there, but the wrong kind of thing".
    """

    code = INSTANCE_NOT_FOUND
    codes = (INSTANCE_NOT_FOUND, INSTANCE_NOT_A_DIRECTORY)


class InstanceUnreadableError(LoaderError):
    """A document exists but could not be read or parsed."""

    code = INSTANCE_UNREADABLE


class InstanceFieldMissingError(LoaderError):
    """The artifact is missing a field the contract requires.

    The loader **never repairs** this. A missing field is reported so the artifact
    can be regenerated; filling it would be the fabrication every phase of this
    programme exists to prevent.
    """

    code = INSTANCE_FIELD_MISSING


class InstanceModuleMissingError(LoaderError):
    """A module the instance must carry is absent."""

    code = INSTANCE_MODULE_MISSING


class InstanceProvenanceMissingError(LoaderError):
    """The provenance module, or a required part of it, is absent or corrupted."""

    code = INSTANCE_PROVENANCE_MODULE_MISSING


class InstanceSchemaError(LoaderError):
    """The instance does not match the C0.1 contract schema."""

    code = INSTANCE_SCHEMA_INVALID


class InstanceContractError(LoaderError):
    """The instance fails the C0.1 contract's own validation."""

    code = INSTANCE_CONTRACT_INVALID


class InstanceProvenanceError(LoaderError):
    """The instance's provenance is incomplete or inconsistent."""

    code = INSTANCE_PROVENANCE_INVALID


class InstanceCapabilityError(LoaderError):
    """A capability declaration is invalid, or claims more than it can support.

    The loader never enables a capability. A disagreement between ``enabled`` and
    the recorded availability is reported, not reconciled.
    """

    code = INSTANCE_CAPABILITY_INVALID


class InstanceAssetReferenceError(LoaderError):
    """An asset reference is malformed, or could not be resolved read-only."""

    code = INSTANCE_ASSET_REFERENCE_INVALID


class InstanceDiffError(LoaderError):
    """Two loaded instances cannot be compared."""

    code = INSTANCE_DIFF_INVALID


class InstanceImmutableError(LoaderError):
    """A caller tried to modify a loaded instance."""

    code = INSTANCE_IMMUTABLE


__all__ = [
    "ERROR_CODES",
    "INSTANCE_ASSET_REFERENCE_INVALID",
    "INSTANCE_CAPABILITY_INVALID",
    "INSTANCE_CONTRACT_INVALID",
    "INSTANCE_DIFF_INVALID",
    "INSTANCE_FIELD_MISSING",
    "INSTANCE_IMMUTABLE",
    "INSTANCE_MODULE_MISSING",
    "INSTANCE_NOT_A_DIRECTORY",
    "INSTANCE_NOT_FOUND",
    "INSTANCE_PROVENANCE_INVALID",
    "INSTANCE_PROVENANCE_MODULE_MISSING",
    "INSTANCE_SCHEMA_INVALID",
    "INSTANCE_UNREADABLE",
    "InstanceAssetReferenceError",
    "InstanceCapabilityError",
    "InstanceContractError",
    "InstanceDiffError",
    "InstanceFieldMissingError",
    "InstanceImmutableError",
    "InstanceModuleMissingError",
    "InstanceNotFoundError",
    "InstanceProvenanceError",
    "InstanceProvenanceMissingError",
    "InstanceSchemaError",
    "InstanceUnreadableError",
    "LoaderError",
]
