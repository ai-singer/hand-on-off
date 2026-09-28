"""The Skill Library Release Layer.

The last step of the factory's production chain, and the first step of distribution:

```text
    Universal Skills + Meta Skills + domain-plugin-builder
          + domain-plugin-validator + Registry + Release Manifest
                                |
                                v
                    creator_skill_library.zip
                                |
                                v
                   Lobster Shared Skill Library
```

Upload the archive once. From then on a user asks for a creator in some domain, the
library's own ``domain-plugin-builder`` turns that request into a domain plugin,
``domain-plugin-validator`` checks it, and the agent is configured from the plugin
plus the universal skills. Three domains today, three hundred later, one library.

Modules
-------

``paths``
    Every archive path, declared once so the builder, the validator and the tests
    cannot disagree about the layout.
``errors``
    The typed error surface, with stable machine-readable codes.
``emitter``
    One library declaration in, one real skill directory out — ``SKILL.md``,
    ``manifest.json``, ``skill.json``, in this repository's own skill convention.
``manifest``
    The release manifest, ``version.json``, ``LIBRARY.md`` and the published domain
    registry.
``archive``
    The deterministic zip: fixed clock, fixed order, fixed compression.
``validation``
    Eight checks, including the three that decide whether the artefact is safe to
    upload: no runtime, no credential, no prompt.
``builder``
    :func:`build_library`, :func:`verify_artifact`, :func:`write_library`.

Two digests
-----------

``content_hash`` is the load-bearing one: computed over every member except the two
that record a digest, so it never changes as a result of writing the manifest, and it
is fully re-derivable. ``artifact_hash`` covers the finished ``.zip`` bytes and is
therefore **advisory** — recording it changes the file it describes.
:func:`verify_artifact` re-derives both and says which holds.

What this package is not
------------------------

It does not upload anything, call the Lobster API, create an agent, or generate
content. It assembles bytes and checks them.

This package imports nothing from ``runtime``, ``production``, ``workflows``,
``risk_evaluation``, ``multimodal_creator``, ``distillation_core``, or ``plugins``.
"""

from __future__ import annotations

from .archive import (
    add_ledger,
    archive_names,
    artifact_digest,
    finalise,
    read_archive,
    verify_ledger,
    write_archive,
)
from .builder import (
    DEFAULT_LIBRARY_VERSION,
    LibraryBuild,
    build_and_write,
    build_library,
    declaration_for,
    describe_library,
    emit_skills,
    member_listing,
    verify_artifact,
    write_library,
)
from .emitter import (
    FORBIDDEN_SKILL_MANIFEST_KEYS,
    MANIFEST_KEYS,
    NO_TEST_COMMAND_REASON,
    SKILL_MANIFEST_VERSION,
    emit_skill,
    skill_capabilities,
    skill_document,
    skill_manifest,
    skill_markdown,
    validate_emitted_manifest,
)
from .errors import (
    ERROR_CODES,
    LIBRARY_ARCHIVE_INVALID,
    LIBRARY_CHECKSUM_MISMATCH,
    LIBRARY_CREDENTIAL_DETECTED,
    LIBRARY_INPUT_INVALID,
    LIBRARY_ISOLATION_VIOLATION,
    LIBRARY_LAYER_VIOLATION,
    LIBRARY_MANIFEST_INVALID,
    LIBRARY_NOT_REPRODUCIBLE,
    LIBRARY_PATH_INVALID,
    LIBRARY_PROMPT_DETECTED,
    LIBRARY_REGISTRY_INVALID,
    LIBRARY_RUNTIME_DETECTED,
    LIBRARY_SCHEMA_INVALID,
    LIBRARY_SKILL_INVALID,
    LIBRARY_SKILL_MISSING,
    LIBRARY_STRUCTURE_INVALID,
    LibraryArchiveError,
    LibraryChecksumError,
    LibraryCredentialError,
    LibraryError,
    LibraryInputError,
    LibraryIsolationError,
    LibraryLayerError,
    LibraryManifestError,
    LibraryPathError,
    LibraryPromptError,
    LibraryRegistryError,
    LibraryReproducibilityError,
    LibraryRuntimeError,
    LibrarySchemaError,
    LibrarySkillError,
    LibrarySkillMissingError,
    LibraryStructureError,
)
from .manifest import (
    FORBIDDEN_MANIFEST_KEYS,
    GENERATED_BY,
    INTEGRITY_RULE,
    LIBRARY_FORMAT_VERSION,
    LIBRARY_ID,
    MANIFEST_SCHEMA_VERSION,
    REQUIRED_MANIFEST_KEYS,
    build_domain_registry,
    build_manifest,
    build_readme,
    build_schema_entry,
    build_version_document,
    standard_exclusions,
    validate_manifest,
)
from .paths import (
    ALLOWED_SUFFIXES,
    ARCHIVE_FILENAME,
    CHECKSUMS_MEMBER,
    FORBIDDEN_DIRECTORIES,
    FORBIDDEN_FILENAMES,
    FORBIDDEN_SUFFIXES,
    LAYERS,
    LAYER_DIRS,
    LIBRARY_DIR,
    LIBRARY_FILE,
    MANIFEST_MEMBER,
    META_SKILLS_DIR,
    PACKAGE_SUFFIX,
    README_MEMBER,
    REGISTRY_MEMBER,
    ROOT_MEMBERS,
    SCHEMA_MEMBER,
    SKILL_FILES,
    STANDALONE_FILES,
    UNIVERSAL_SKILLS_DIR,
    VERSION_MEMBER,
    classify_member,
    expected_members,
    layer_of,
    library_root,
    member_sort_key,
    package_classify,
    package_filename,
    package_member_sort_key,
    package_members,
    package_root,
    skill_dir,
    skill_directory_of,
    skill_document_member,
    skill_manifest_member,
    skill_md_member,
    skill_members,
    summarise_members,
)
from .skill_package import (
    FILENAME_PREFIX,
    PACKAGE_MANIFEST_KEYS,
    SkillPackage,
    build_skill_package,
    build_skill_packages,
    checksum_index,
    library_metadata,
    package_manifest,
    skill_layer,
    unpack_skill_package,
    unpack_skill_packages,
    unpacked_checksum_index,
    unpacked_index,
    upload_index,
    write_skill_packages,
)
from .skill_package_validation import (
    FORBIDDEN_PACKAGE_KEYS,
    IDENTICAL_FILES,
    PACKAGE_ONLY_MANIFEST_KEYS,
    SHARED_FILES,
    PackageValidationReport,
    describe_packages,
    read_package,
    shared_files,
    validate_package,
    validate_package_isolation,
    validate_package_layer,
    validate_package_manifest,
    validate_package_matches_library,
    validate_package_structure,
    validate_packages,
    verify_package_bytes,
)
from .validation import (
    CREDENTIAL_ALLOWLIST,
    CREDENTIAL_PATTERNS,
    LibraryValidationReport,
    describe_validation,
    validate_archive,
    validate_checksums,
    validate_isolation,
    validate_layers,
    validate_manifest_member,
    validate_registry,
    validate_reproducibility,
    validate_skills,
    validate_structure,
    verify_library_hash,
)

__all__ = [
    "ALLOWED_SUFFIXES",
    "ARCHIVE_FILENAME",
    "CHECKSUMS_MEMBER",
    "CREDENTIAL_ALLOWLIST",
    "CREDENTIAL_PATTERNS",
    "DEFAULT_LIBRARY_VERSION",
    "ERROR_CODES",
    "FILENAME_PREFIX",
    "FORBIDDEN_DIRECTORIES",
    "FORBIDDEN_FILENAMES",
    "FORBIDDEN_MANIFEST_KEYS",
    "FORBIDDEN_PACKAGE_KEYS",
    "FORBIDDEN_SKILL_MANIFEST_KEYS",
    "FORBIDDEN_SUFFIXES",
    "GENERATED_BY",
    "IDENTICAL_FILES",
    "INTEGRITY_RULE",
    "LAYERS",
    "LAYER_DIRS",
    "LIBRARY_ARCHIVE_INVALID",
    "LIBRARY_CHECKSUM_MISMATCH",
    "LIBRARY_CREDENTIAL_DETECTED",
    "LIBRARY_DIR",
    "LIBRARY_FILE",
    "LIBRARY_FORMAT_VERSION",
    "LIBRARY_ID",
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
    "LibraryBuild",
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
    "LibraryValidationReport",
    "MANIFEST_KEYS",
    "MANIFEST_MEMBER",
    "MANIFEST_SCHEMA_VERSION",
    "META_SKILLS_DIR",
    "NO_TEST_COMMAND_REASON",
    "PACKAGE_MANIFEST_KEYS",
    "PACKAGE_ONLY_MANIFEST_KEYS",
    "PACKAGE_SUFFIX",
    "PackageValidationReport",
    "README_MEMBER",
    "REGISTRY_MEMBER",
    "REQUIRED_MANIFEST_KEYS",
    "ROOT_MEMBERS",
    "SCHEMA_MEMBER",
    "SHARED_FILES",
    "SKILL_FILES",
    "SKILL_MANIFEST_VERSION",
    "STANDALONE_FILES",
    "SkillPackage",
    "UNIVERSAL_SKILLS_DIR",
    "VERSION_MEMBER",
    "add_ledger",
    "archive_names",
    "artifact_digest",
    "build_and_write",
    "build_domain_registry",
    "build_library",
    "build_manifest",
    "build_readme",
    "build_schema_entry",
    "build_skill_package",
    "build_skill_packages",
    "build_version_document",
    "checksum_index",
    "classify_member",
    "declaration_for",
    "describe_library",
    "describe_packages",
    "describe_validation",
    "emit_skill",
    "emit_skills",
    "expected_members",
    "finalise",
    "layer_of",
    "library_metadata",
    "library_root",
    "member_listing",
    "member_sort_key",
    "package_classify",
    "package_filename",
    "package_manifest",
    "package_member_sort_key",
    "package_members",
    "package_root",
    "read_archive",
    "read_package",
    "shared_files",
    "skill_capabilities",
    "skill_dir",
    "skill_directory_of",
    "skill_document",
    "skill_document_member",
    "skill_layer",
    "skill_manifest",
    "skill_manifest_member",
    "skill_markdown",
    "skill_md_member",
    "skill_members",
    "standard_exclusions",
    "summarise_members",
    "unpack_skill_package",
    "unpack_skill_packages",
    "unpacked_checksum_index",
    "unpacked_index",
    "upload_index",
    "validate_archive",
    "validate_checksums",
    "validate_emitted_manifest",
    "validate_isolation",
    "validate_layers",
    "validate_manifest",
    "validate_manifest_member",
    "validate_package",
    "validate_package_isolation",
    "validate_package_layer",
    "validate_package_manifest",
    "validate_package_matches_library",
    "validate_package_structure",
    "validate_packages",
    "validate_registry",
    "validate_reproducibility",
    "validate_skills",
    "validate_structure",
    "verify_artifact",
    "verify_ledger",
    "verify_library_hash",
    "verify_package_bytes",
    "write_archive",
    "write_library",
    "write_skill_packages",
]
