"""Error types for the Skill Library Release Layer.

Every error extends :class:`creator_contract.CreatorContractError`, so a caller that
already handles contract, projection, skill, mapping, loader or plugin-builder
failures catches a release failure too.

Each error carries a **machine-readable code**, so a caller branches on
``LIBRARY_RUNTIME_DETECTED`` rather than parsing a message.
"""

from __future__ import annotations

from creator_contract import CreatorContractError

#: Error codes the release layer may raise. Stable strings, safe to match on.
LIBRARY_INPUT_INVALID = "LIBRARY_INPUT_INVALID"
LIBRARY_PATH_INVALID = "LIBRARY_PATH_INVALID"
LIBRARY_STRUCTURE_INVALID = "LIBRARY_STRUCTURE_INVALID"
LIBRARY_SCHEMA_INVALID = "LIBRARY_SCHEMA_INVALID"
LIBRARY_SKILL_INVALID = "LIBRARY_SKILL_INVALID"
LIBRARY_SKILL_MISSING = "LIBRARY_SKILL_MISSING"
LIBRARY_MANIFEST_INVALID = "LIBRARY_MANIFEST_INVALID"
LIBRARY_LAYER_VIOLATION = "LIBRARY_LAYER_VIOLATION"
LIBRARY_ISOLATION_VIOLATION = "LIBRARY_ISOLATION_VIOLATION"
LIBRARY_RUNTIME_DETECTED = "LIBRARY_RUNTIME_DETECTED"
LIBRARY_CREDENTIAL_DETECTED = "LIBRARY_CREDENTIAL_DETECTED"
LIBRARY_PROMPT_DETECTED = "LIBRARY_PROMPT_DETECTED"
LIBRARY_CHECKSUM_MISMATCH = "LIBRARY_CHECKSUM_MISMATCH"
LIBRARY_NOT_REPRODUCIBLE = "LIBRARY_NOT_REPRODUCIBLE"
LIBRARY_ARCHIVE_INVALID = "LIBRARY_ARCHIVE_INVALID"
LIBRARY_REGISTRY_INVALID = "LIBRARY_REGISTRY_INVALID"

#: Every code, for a test that asserts the set is stable.
ERROR_CODES: tuple[str, ...] = (
    LIBRARY_INPUT_INVALID,
    LIBRARY_PATH_INVALID,
    LIBRARY_STRUCTURE_INVALID,
    LIBRARY_SCHEMA_INVALID,
    LIBRARY_SKILL_INVALID,
    LIBRARY_SKILL_MISSING,
    LIBRARY_MANIFEST_INVALID,
    LIBRARY_LAYER_VIOLATION,
    LIBRARY_ISOLATION_VIOLATION,
    LIBRARY_RUNTIME_DETECTED,
    LIBRARY_CREDENTIAL_DETECTED,
    LIBRARY_PROMPT_DETECTED,
    LIBRARY_CHECKSUM_MISMATCH,
    LIBRARY_NOT_REPRODUCIBLE,
    LIBRARY_ARCHIVE_INVALID,
    LIBRARY_REGISTRY_INVALID,
)


class LibraryError(CreatorContractError):
    """Base class for release-layer failures. ``code`` is machine-readable."""

    code = "LIBRARY_ERROR"

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


class LibraryInputError(LibraryError):
    """A supplied input is not something the release layer can package."""

    code = LIBRARY_INPUT_INVALID


class LibraryPathError(LibraryError):
    """An archive path is malformed, or would escape its directory."""

    code = LIBRARY_PATH_INVALID


class LibraryStructureError(LibraryError):
    """The archive's member layout is not the library layout."""

    code = LIBRARY_STRUCTURE_INVALID


class LibrarySchemaError(LibraryError):
    """A library document does not match its schema."""

    code = LIBRARY_SCHEMA_INVALID


class LibrarySkillError(LibraryError):
    """An emitted skill is malformed, or does not match its declaration."""

    code = LIBRARY_SKILL_INVALID


class LibrarySkillMissingError(LibraryError):
    """A skill the library declares has no emitted directory."""

    code = LIBRARY_SKILL_MISSING


class LibraryManifestError(LibraryError):
    """The release manifest is incomplete, or carries a key it must never carry."""

    code = LIBRARY_MANIFEST_INVALID


class LibraryLayerError(LibraryError):
    """A universal skill carries domain knowledge, or a layer is misdeclared."""

    code = LIBRARY_LAYER_VIOLATION


class LibraryIsolationError(LibraryError):
    """The library carries something a configuration asset must not carry."""

    code = LIBRARY_ISOLATION_VIOLATION


class LibraryRuntimeError(LibraryError):
    """An executable entry point or runtime artefact was found in the library."""

    code = LIBRARY_RUNTIME_DETECTED


class LibraryCredentialError(LibraryError):
    """A credential-, token- or key-shaped value was found in the library."""

    code = LIBRARY_CREDENTIAL_DETECTED


class LibraryPromptError(LibraryError):
    """Prompt text or a prompt-shaped key was found in the library."""

    code = LIBRARY_PROMPT_DETECTED


class LibraryChecksumError(LibraryError):
    """A recorded checksum does not match the member it describes."""

    code = LIBRARY_CHECKSUM_MISMATCH


class LibraryReproducibilityError(LibraryError):
    """Two builds of the same declarations produced different bytes."""

    code = LIBRARY_NOT_REPRODUCIBLE


class LibraryArchiveError(LibraryError):
    """The archive could not be written or read as a zip."""

    code = LIBRARY_ARCHIVE_INVALID


class LibraryRegistryError(LibraryError):
    """The published domain registry does not match the builder's catalog."""

    code = LIBRARY_REGISTRY_INVALID


__all__ = [
    "ERROR_CODES",
    "LIBRARY_ARCHIVE_INVALID",
    "LIBRARY_CHECKSUM_MISMATCH",
    "LIBRARY_CREDENTIAL_DETECTED",
    "LIBRARY_INPUT_INVALID",
    "LIBRARY_ISOLATION_VIOLATION",
    "LIBRARY_LAYER_VIOLATION",
    "LIBRARY_MANIFEST_INVALID",
    "LIBRARY_NOT_REPRODUCIBLE",
    "LIBRARY_PATH_INVALID",
    "LIBRARY_PROMPT_DETECTED",
    "LIBRARY_REGISTRY_INVALID",
    "LIBRARY_RUNTIME_DETECTED",
    "LIBRARY_SCHEMA_INVALID",
    "LIBRARY_SKILL_INVALID",
    "LIBRARY_SKILL_MISSING",
    "LIBRARY_STRUCTURE_INVALID",
    "LibraryArchiveError",
    "LibraryChecksumError",
    "LibraryCredentialError",
    "LibraryError",
    "LibraryInputError",
    "LibraryIsolationError",
    "LibraryLayerError",
    "LibraryManifestError",
    "LibraryPathError",
    "LibraryPromptError",
    "LibraryRegistryError",
    "LibraryReproducibilityError",
    "LibraryRuntimeError",
    "LibrarySchemaError",
    "LibrarySkillError",
    "LibrarySkillMissingError",
    "LibraryStructureError",
]
