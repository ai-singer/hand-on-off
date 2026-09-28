"""Validating a standalone skill package, one upload at a time.

Thirteen packages means thirteen chances to ship something wrong, and a reviewer
uploading one of them has only that file to judge. So each package is checked on its
own, from its own bytes, against the same rules the whole library is held to:

| # | Check | Refuses |
| --- | --- | --- |
| 1 | :func:`validate_package_structure` | a member layout that is not the package layout |
| 2 | :func:`validate_package_manifest` | a manifest that disagrees with the skill, or carries a forbidden key |
| 3 | :func:`validate_package_isolation` | runtime, credentials, prompts, forbidden references |
| 4 | :func:`validate_package_layer` | a universal skill carrying domain knowledge |
| 5 | :func:`validate_package_matches_library` | a package whose bytes differ from the library's copy of the same skill |

Check 5 is the one that makes a split trustworthy. The library archive and the
thirteen packages are two representations of one thing; if they disagree, one of them
is wrong and a reviewer has no way to tell which. So both are built from the same
declarations and the check asserts the shared files are identical.

The library archive and a package key the same three files differently — the library
under ``creator_skill_library/<layer>_skills/<name>/``, the package under
``<name>/`` — so the comparison is by **suffix and content**, not by path.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from creator_plugin_builder import (
    DOMAIN_MARKERS,
    FORBIDDEN_MODULES,
    PROMPT_KEYS,
    PROMPT_PHRASES,
    RUNTIME_KEYS,
    UNIVERSAL_SKILLS,
)

from .errors import (
    LibraryCredentialError,
    LibraryIsolationError,
    LibraryLayerError,
    LibraryManifestError,
    LibraryPromptError,
    LibraryRuntimeError,
    LibraryStructureError,
)
from .manifest import FORBIDDEN_MANIFEST_KEYS
from .paths import (
    SKILL_FILES,
    STANDALONE_FILES,
    archive_classify,
    archive_members,
    package_members,
    package_root,
)
from .skill_package import PACKAGE_MANIFEST_KEYS, SkillPackage
from .validation import (
    CREDENTIAL_ALLOWLIST,
    CREDENTIAL_PATTERNS,
    PLACEHOLDER_MARKERS,
    _is_concept_reference,
)

#: The three files a skill archive carries, all at its root.
SHARED_FILES: tuple[str, ...] = ("SKILL.md", "manifest.json", "skill.json")

#: The files that must be **byte-identical** between an archive and the library.
#:
#: ``SKILL.md`` and ``skill.json`` are context-free by construction. ``SKILL.md``
#: lists the whole library's skills rather than the subset an archive carries, and
#: ``skill.json`` is the declaration with no packaging metadata in it — so both are
#: the same bytes wherever the skill is packaged, and the check can be exact.
IDENTICAL_FILES: tuple[str, ...] = ("SKILL.md", "skill.json")

#: Keys an archive's manifest carries that the library's copy does not.
#:
#: Empty, and deliberately so. The two manifests are the same document: an earlier
#: version added ``library_id`` and ``package_filename`` to the archive's copy, which
#: made the two disagree about the same skill. ``library_id`` moved into both;
#: ``package_filename`` was dropped, because the filename is already visible in the
#: name of the file a reader is holding.
PACKAGE_ONLY_MANIFEST_KEYS: tuple[str, ...] = ()

#: Keys a package manifest must never carry.
FORBIDDEN_PACKAGE_KEYS: tuple[str, ...] = FORBIDDEN_MANIFEST_KEYS + ("adapter",)


@dataclass(frozen=True, slots=True)
class PackageValidationReport:
    """The result of validating one standalone package."""

    skill: str
    version: str
    filename: str
    checks: Mapping[str, str]
    findings: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return all(value == "PASS" for value in self.checks.values())

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def as_dict(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "skill": self.skill,
            "version": self.version,
            "filename": self.filename,
            "status": self.status,
            "checks": dict(self.checks),
        }
        if self.findings:
            document["findings"] = list(self.findings)
        return document


def read_package(payload: bytes) -> dict[str, bytes]:
    """Read a package's members back out of its bytes."""

    from .errors import LibraryArchiveError

    members: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                members[info.filename] = archive.read(info)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise LibraryArchiveError(f"cannot read skill package: {exc}") from exc
    return members


# --------------------------------------------------------------------------
# 1. Structure
# --------------------------------------------------------------------------


def validate_package_structure(members: Mapping[str, bytes], *, name: str) -> None:
    """Check 1: the three files, **flat at the archive root**, and nothing else.

    The nesting check is the important one. A shared skill library loads ``SKILL.md``
    from the archive root, so an archive that wraps its files in a directory looks
    perfectly well-formed and still cannot be loaded. That failure is silent, which is
    why it is checked explicitly rather than left to a comment — a directory component
    in *any* member is refused, even one that also has the right files at the root.
    """

    expected = set(archive_members().keys())

    nested = sorted(member for member in members if "/" in member)
    missing = sorted(expected - set(members))

    # A nested archive is *also* missing all three files at its root, so the plain
    # "missing members" message would bury the real defect behind a list of names. When
    # the files are present but one level down, say exactly that.
    if nested and missing:
        raise LibraryStructureError(
            f"archive {name!r} nests its files in a directory",
            detail=(
                "a shared skill library reads SKILL.md from the archive root; the "
                f"files are at {nested[0]!r} instead"
            ),
        )

    if nested:
        raise LibraryStructureError(
            f"archive {name!r} nests its files in a directory",
            detail=(
                "a shared skill library reads SKILL.md from the archive root; found: "
                + ", ".join(nested[:4])
            ),
        )

    unknown = sorted(
        member for member in members if archive_classify(member) == "unknown"
    )
    if unknown:
        raise LibraryStructureError(
            f"archive {name!r} carries unexpected members",
            detail=", ".join(unknown),
        )

    if missing:
        raise LibraryStructureError(
            f"archive {name!r} is missing {len(missing)} member(s)",
            detail=", ".join(missing),
        )

    if "SKILL.md" not in members:
        raise LibraryStructureError(
            f"archive {name!r} has no SKILL.md at its root",
            detail="without it the skill cannot be matched or loaded",
        )


# --------------------------------------------------------------------------
# 2. Manifest
# --------------------------------------------------------------------------


def validate_package_manifest(
    members: Mapping[str, bytes], *, name: str, version: str
) -> dict[str, Any]:
    """Check 2: the manifest agrees with the skill, and carries no forbidden key."""

    payload = members.get("manifest.json")
    if payload is None:
        raise LibraryManifestError(f"package {name!r} carries no manifest.json")

    try:
        manifest = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LibraryManifestError(
            f"package {name!r} manifest is not valid JSON", detail=str(exc)
        ) from exc
    if not isinstance(manifest, dict):
        raise LibraryManifestError(f"package {name!r} manifest must be an object")

    found = sorted(_all_keys(manifest) & set(FORBIDDEN_PACKAGE_KEYS))
    if found:
        raise LibraryManifestError(
            f"package {name!r} manifest carries forbidden keys: " + ", ".join(found)
        )

    missing = sorted(set(PACKAGE_MANIFEST_KEYS) - set(manifest))
    if missing:
        raise LibraryManifestError(
            f"package {name!r} manifest is missing keys: " + ", ".join(missing)
        )

    if manifest["name"] != name:
        raise LibraryManifestError(
            f"package {name!r} manifest names {manifest['name']!r}"
        )
    if manifest["version"] != version:
        raise LibraryManifestError(
            f"package {name!r} manifest version is {manifest['version']!r}, "
            f"expected {version!r}"
        )
    if manifest["entrypoint"] != "SKILL.md":
        raise LibraryManifestError(
            f"package {name!r} entrypoint must be SKILL.md, "
            f"found {manifest['entrypoint']!r}"
        )
    if not manifest["capabilities"]:
        raise LibraryManifestError(f"package {name!r} declares no capabilities")

    # The manifest and the declaration must agree about which layer this is.
    document = _json(members, "skill.json", name, "skill.json")
    if document.get("library_layer") != manifest["library_layer"]:
        raise LibraryManifestError(
            f"package {name!r} manifest and skill.json disagree on the layer"
        )
    if document.get("name") != name:
        raise LibraryManifestError(
            f"package {name!r} skill.json names {document.get('name')!r}"
        )

    return manifest


def _all_keys(node: Any) -> set[str]:
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                found.add(str(key))
                walk(child)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    walk(node)
    return found


def _json(
    members: Mapping[str, bytes], path: str, name: str, what: str
) -> dict[str, Any]:
    payload = members.get(path)
    if payload is None:
        raise LibraryManifestError(f"package {name!r} carries no {what}")
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LibraryManifestError(
            f"package {name!r} {what} is not valid JSON", detail=str(exc)
        ) from exc
    if not isinstance(document, dict):
        raise LibraryManifestError(f"package {name!r} {what} must be an object")
    return document


# --------------------------------------------------------------------------
# 3. Isolation
# --------------------------------------------------------------------------


def validate_package_isolation(members: Mapping[str, bytes], *, name: str) -> None:
    """Check 3: no runtime, no credential, no prompt, no forbidden reference.

    A package is entirely declarative content — four files, one of them prose — so
    every rule the library archive is held to applies here without exception. There
    are no root documents in a package that legitimately name what they exclude, so
    the module-name check applies to all four files rather than being scoped to the
    skill directory as it is in the library.
    """

    runtime: list[str] = []
    credentials: list[str] = []
    prompts: list[str] = []

    for member in sorted(members):
        try:
            text = members[member].decode("utf-8")
        except UnicodeDecodeError:
            runtime.append(f"{member}: not valid UTF-8")
            continue
        lowered = text.lower()
        filename = member.rsplit("/", 1)[-1]

        for module in FORBIDDEN_MODULES:
            if re.search(rf"(?<![\w-]){re.escape(module)}(?![\w-])", lowered):
                runtime.append(f"{member}: references module {module!r}")

        if filename.endswith(".json"):
            for key in _all_keys(json.loads(text) if _is_json(text) else {}):
                if key.lower() in RUNTIME_KEYS and not (
                    key == "entrypoint" and '"SKILL.md"' in text
                ):
                    runtime.append(f"{member}: runtime key {key!r}")
                if key.lower() in PROMPT_KEYS:
                    prompts.append(f"{member}: prompt key {key!r}")

        for phrase in PROMPT_PHRASES:
            if phrase in lowered:
                prompts.append(f"{member}: prompt phrase {phrase!r}")

        for rule, pattern in CREDENTIAL_PATTERNS:
            for match in re.finditer(pattern, text):
                if _is_concept_reference(match.group(0), rule):
                    continue
                credentials.append(f"{member}: [{rule}] credential-shaped value")

    if runtime:
        raise LibraryRuntimeError(
            f"package {name!r} carries {len(runtime)} runtime violation(s)",
            detail="; ".join(sorted(set(runtime))[:6]),
        )
    if credentials:
        raise LibraryCredentialError(
            f"package {name!r} carries {len(credentials)} credential-shaped value(s)",
            detail="; ".join(sorted(set(credentials))[:6]),
        )
    if prompts:
        raise LibraryPromptError(
            f"package {name!r} carries {len(prompts)} prompt violation(s)",
            detail="; ".join(sorted(set(prompts))[:6]),
        )


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return False
    return True


# --------------------------------------------------------------------------
# 4. Layer
# --------------------------------------------------------------------------


def validate_package_layer(members: Mapping[str, bytes], *, name: str) -> None:
    """Check 4: a universal skill carries no domain knowledge."""

    manifest = _json(members, "manifest.json", name, "manifest.json")
    layer = str(manifest["library_layer"])

    expected = "universal" if name in UNIVERSAL_SKILLS else "meta"
    if layer != expected:
        raise LibraryLayerError(
            f"package {name!r} declares layer {layer!r}, expected {expected!r}"
        )

    if layer != "universal":
        return

    offenders: list[str] = []
    for filename in STANDALONE_FILES:
        payload = members.get(filename)
        if payload is None:
            continue
        blob = payload.decode("utf-8").lower()
        hits = sorted({marker for marker in DOMAIN_MARKERS if marker in blob})
        if hits:
            offenders.append(f"{filename}: {', '.join(hits)}")
    if offenders:
        raise LibraryLayerError(
            f"universal package {name!r} carries domain vocabulary",
            detail="; ".join(offenders),
        )


# --------------------------------------------------------------------------
# 5. Agreement with the library archive
# --------------------------------------------------------------------------


def shared_files(members: Mapping[str, bytes], *, name: str) -> dict[str, bytes]:
    """The three files a package shares with the library, keyed by filename."""

    found: dict[str, bytes] = {}
    for filename in SHARED_FILES:
        payload = members.get(filename)
        if payload is not None:
            found[filename] = payload
    return found


def validate_package_matches_library(
    package: SkillPackage,
    library_build: Any,
) -> None:
    """Check 5: the package and the library agree about the same skill.

    The two are built from the same declarations and must not drift, but they are not
    the same artefact and the check says so precisely rather than demanding equality
    it cannot honestly have:

    - ``SKILL.md`` and ``skill.json`` must be **byte-identical**.
    - ``manifest.json`` must agree on every key the two share. A package manifest
      additionally records ``library_id`` and ``package_filename`` — facts about the
      archive a reader is holding, which the library's own manifest has no use for.

    ``library.json`` exists only in a package, and the library's root documents exist
    only in the library, so neither is compared.
    """

    from .paths import skill_members

    layer = str(package.layer)
    library_paths = skill_members(layer, package.name)
    ours = shared_files(package.members, name=package.name)

    for filename in IDENTICAL_FILES:
        theirs = library_build.members.get(library_paths[filename])
        if theirs is None:
            raise LibraryStructureError(
                f"the library archive carries no {filename} for {package.name!r}"
            )
        if ours[filename] != theirs:
            raise LibraryStructureError(
                f"package {package.name!r} and the library disagree on {filename}",
                detail="the two must be built from the same declarations",
            )

    theirs_manifest = library_build.members.get(library_paths["manifest.json"])
    if theirs_manifest is None:
        raise LibraryStructureError(
            f"the library archive carries no manifest.json for {package.name!r}"
        )
    library_manifest = json.loads(theirs_manifest.decode("utf-8"))
    package_manifest_doc = json.loads(ours["manifest.json"].decode("utf-8"))

    disagreements: list[str] = []
    for key, value in sorted(library_manifest.items()):
        if package_manifest_doc.get(key) != value:
            disagreements.append(
                f"{key}: package {package_manifest_doc.get(key)!r} "
                f"vs library {value!r}"
            )
    if disagreements:
        raise LibraryStructureError(
            f"package {package.name!r} and the library disagree on its manifest",
            detail="; ".join(disagreements[:6]),
        )

    extra = sorted(
        set(package_manifest_doc) - set(library_manifest)
    )
    unexpected = [key for key in extra if key not in PACKAGE_ONLY_MANIFEST_KEYS]
    if unexpected:
        raise LibraryStructureError(
            f"package {package.name!r} manifest carries unexpected keys",
            detail=", ".join(unexpected),
        )


# --------------------------------------------------------------------------
# Combined
# --------------------------------------------------------------------------


def validate_package(
    package: SkillPackage,
    *,
    library_build: Any = None,
) -> PackageValidationReport:
    """Run every check against one package, from its own bytes."""

    members = read_package(package.payload)
    checks: dict[str, str] = {}

    validate_package_structure(members, name=package.name)
    checks["structure"] = "PASS"

    validate_package_manifest(members, name=package.name, version=package.version)
    checks["manifest"] = "PASS"

    validate_package_isolation(members, name=package.name)
    checks["isolation"] = "PASS"

    validate_package_layer(members, name=package.name)
    checks["layer"] = "PASS"

    if library_build is not None:
        validate_package_matches_library(package, library_build)
        checks["library_agreement"] = "PASS"

    return PackageValidationReport(
        skill=package.name,
        version=package.version,
        filename=package.filename,
        checks=checks,
    )


def validate_packages(
    packages: Sequence[SkillPackage],
    *,
    library_build: Any = None,
) -> tuple[PackageValidationReport, ...]:
    """Validate every package, in order."""

    return tuple(
        validate_package(package, library_build=library_build)
        for package in packages
    )


def describe_packages(
    packages: Sequence[SkillPackage],
    *,
    library_build: Any = None,
) -> dict[str, Any]:
    """One document summarising a batch: thirteen verdicts and a total."""

    reports = validate_packages(packages, library_build=library_build)
    return {
        "package_count": len(reports),
        "passed": sum(1 for r in reports if r.passed),
        "failed": sum(1 for r in reports if not r.passed),
        "status": "PASS" if all(r.passed for r in reports) else "FAIL",
        "checks": sorted({name for r in reports for name in r.checks}),
        "packages": [r.as_dict() for r in reports],
    }


def verify_package_bytes(payload: bytes, *, name: str, version: str) -> None:
    """Verify a package read back from disk, without the in-memory object."""

    members = read_package(payload)
    validate_package_structure(members, name=name)
    validate_package_manifest(members, name=name, version=version)
    validate_package_isolation(members, name=name)
    validate_package_layer(members, name=name)


__all__ = [
    "FORBIDDEN_PACKAGE_KEYS",
    "PackageValidationReport",
    "SHARED_FILES",
    "describe_packages",
    "read_package",
    "shared_files",
    "validate_package",
    "validate_package_isolation",
    "validate_package_layer",
    "validate_package_manifest",
    "validate_package_matches_library",
    "validate_package_structure",
    "validate_packages",
    "verify_package_bytes",
]
