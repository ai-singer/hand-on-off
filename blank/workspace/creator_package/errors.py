"""Error types for the Creator Skill Package Builder.

Every error extends :class:`creator_contract.CreatorContractError`, so a caller that
already handles contract, projection, skill, mapping or loader failures catches a
package failure too.

Each error carries a **machine-readable code**, so a caller branches on
``PACKAGE_CAPABILITY_INVENTED`` rather than parsing a message.
"""

from __future__ import annotations

from creator_contract import CreatorContractError

#: Error codes the builder may raise. Stable strings, safe to match on.
PACKAGE_INPUT_INVALID = "PKG_INPUT_INVALID"
PACKAGE_NOT_FOUND = "PKG_NOT_FOUND"
PACKAGE_UNREADABLE = "PKG_UNREADABLE"
PACKAGE_SCHEMA_INVALID = "PKG_SCHEMA_INVALID"
PACKAGE_MANIFEST_INVALID = "PKG_MANIFEST_INVALID"
PACKAGE_SKILL_INVALID = "PKG_SKILL_INVALID"
PACKAGE_SKILL_MISSING = "PKG_SKILL_MISSING"
PACKAGE_INSTANCE_INVALID = "PKG_INSTANCE_INVALID"
PACKAGE_PROVENANCE_INVALID = "PKG_PROVENANCE_INVALID"
PACKAGE_CAPABILITY_INVENTED = "PKG_CAPABILITY_INVENTED"
PACKAGE_ISOLATION_VIOLATION = "PKG_ISOLATION_VIOLATION"
PACKAGE_CREDENTIAL_DETECTED = "PKG_CREDENTIAL_DETECTED"
PACKAGE_RUNTIME_DETECTED = "PKG_RUNTIME_DETECTED"
PACKAGE_CHECKSUM_MISMATCH = "PKG_CHECKSUM_MISMATCH"
PACKAGE_STRUCTURE_INVALID = "PKG_STRUCTURE_INVALID"
PACKAGE_NOT_REPRODUCIBLE = "PKG_NOT_REPRODUCIBLE"
PACKAGE_ARCHIVE_INVALID = "PKG_ARCHIVE_INVALID"

#: Every code, for a test that asserts the set is stable.
ERROR_CODES: tuple[str, ...] = (
    PACKAGE_INPUT_INVALID,
    PACKAGE_NOT_FOUND,
    PACKAGE_UNREADABLE,
    PACKAGE_SCHEMA_INVALID,
    PACKAGE_MANIFEST_INVALID,
    PACKAGE_SKILL_INVALID,
    PACKAGE_SKILL_MISSING,
    PACKAGE_INSTANCE_INVALID,
    PACKAGE_PROVENANCE_INVALID,
    PACKAGE_CAPABILITY_INVENTED,
    PACKAGE_ISOLATION_VIOLATION,
    PACKAGE_CREDENTIAL_DETECTED,
    PACKAGE_RUNTIME_DETECTED,
    PACKAGE_CHECKSUM_MISMATCH,
    PACKAGE_STRUCTURE_INVALID,
    PACKAGE_NOT_REPRODUCIBLE,
    PACKAGE_ARCHIVE_INVALID,
)


class PackageError(CreatorContractError):
    """Base class for package failures. ``args[0]`` begins with a stable code.

    ``codes`` lists every code the class may raise, so a caller can branch on a
    machine-readable string rather than parse a message.
    """

    code = "PKG_ERROR"

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


class PackageInputError(PackageError):
    """A supplied input is not something the builder can pack."""

    code = PACKAGE_INPUT_INVALID


class PackageNotFoundError(PackageError):
    """The instance artifact or package file does not exist."""

    code = PACKAGE_NOT_FOUND


class PackageUnreadableError(PackageError):
    """A document exists but could not be read or parsed."""

    code = PACKAGE_UNREADABLE


class PackageSchemaError(PackageError):
    """A package document does not match the package schema."""

    code = PACKAGE_SCHEMA_INVALID


class PackageManifestError(PackageError):
    """The manifest is incomplete, or carries a key it must never carry."""

    code = PACKAGE_MANIFEST_INVALID


class PackageSkillError(PackageError):
    """A skill in the bundle is invalid, or could not be packaged."""

    code = PACKAGE_SKILL_INVALID


class PackageSkillMissingError(PackageError):
    """A skill the package needs has no document to write."""

    code = PACKAGE_SKILL_MISSING


class PackageInstanceError(PackageError):
    """The instance artifact fails its own contract validation."""

    code = PACKAGE_INSTANCE_INVALID


class PackageProvenanceError(PackageError):
    """Provenance is incomplete: a field cannot be traced to its origin."""

    code = PACKAGE_PROVENANCE_INVALID


class PackageCapabilityError(PackageError):
    """A capability is claimed that does not exist.

    The builder never invents a persona, a data source, a generation capability or a
    publishing capability. An absent capability is declared ``available=false`` with
    a reason; claiming otherwise raises this.
    """

    code = PACKAGE_CAPABILITY_INVENTED


class PackageIsolationError(PackageError):
    """The package carries something a configuration asset must not carry."""

    code = PACKAGE_ISOLATION_VIOLATION


class PackageCredentialError(PackageError):
    """A credential-, token- or key-shaped value was found in the package."""

    code = PACKAGE_CREDENTIAL_DETECTED


class PackageRuntimeError(PackageError):
    """An executable entry point or runtime artefact was found in the package."""

    code = PACKAGE_RUNTIME_DETECTED


class PackageChecksumError(PackageError):
    """A recorded checksum does not match the file it describes."""

    code = PACKAGE_CHECKSUM_MISMATCH


class PackageStructureError(PackageError):
    """The archive's member layout is not the package layout."""

    code = PACKAGE_STRUCTURE_INVALID


class PackageReproducibilityError(PackageError):
    """Two builds of the same inputs produced different bytes."""

    code = PACKAGE_NOT_REPRODUCIBLE


class PackageArchiveError(PackageError):
    """The archive could not be written or read as a zip."""

    code = PACKAGE_ARCHIVE_INVALID


__all__ = [
    "ERROR_CODES",
    "PKG_ARCHIVE_INVALID",
    "PKG_CAPABILITY_INVENTED",
    "PKG_CHECKSUM_MISMATCH",
    "PKG_INPUT_INVALID",
    "PKG_INSTANCE_INVALID",
    "PKG_ISOLATION_VIOLATION",
    "PKG_MANIFEST_INVALID",
    "PKG_NOT_FOUND",
    "PKG_NOT_REPRODUCIBLE",
    "PKG_PROVENANCE_INVALID",
    "PKG_RUNTIME_DETECTED",
    "PKG_SCHEMA_INVALID",
    "PKG_CREDENTIAL_DETECTED",
    "PKG_SKILL_INVALID",
    "PKG_SKILL_MISSING",
    "PKG_STRUCTURE_INVALID",
    "PKG_UNREADABLE",
    "PackageArchiveError",
    "PackageCapabilityError",
    "PackageChecksumError",
    "PackageError",
    "PackageInputError",
    "PackageInstanceError",
    "PackageIsolationError",
    "PackageManifestError",
    "PackageNotFoundError",
    "PackageProvenanceError",
    "PackageReproducibilityError",
    "PackageRuntimeError",
    "PackageSchemaError",
    "PackageCredentialError",
    "PackageSkillError",
    "PackageSkillMissingError",
    "PackageStructureError",
    "PackageUnreadableError",
]
