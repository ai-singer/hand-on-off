"""Standalone skill packages: one skill, one uploadable zip.

A Shared Skill Library ingests skills **one at a time**, so ``creator_skill_library.zip``
cannot be uploaded as a single object. This module splits it into the units the
upload actually takes:

```text
    creator_skill_library.zip          (the whole library, for reference)
                 |
                 |  build_skill_packages()
                 v
    creator-identity-rules.zip         ┐
    creator-source-discovery.zip       │
    creator-source-normalization.zip   │  10 universal
    creator-text-distillation.zip      │  + 3 meta
    ...                                │  = 13 uploadable units
    creator-domain-plugin-builder.zip  │
    ...                                ┘
```

Each package contains exactly one skill directory:

```text
<skill_name>/
├── SKILL.md          front matter + prose
├── manifest.json     name, version, library_layer, entrypoint, capabilities
├── skill.json        the declaration, machine-readable
└── library.json      where it came from
```

## Why the layout differs from the library archive

Three deliberate differences, each with a reason:

**No ``creator_skill_library/`` wrapper.** Thirteen packages repeating the library
name would tell a reader handling one of them nothing they need. The single
top-level directory is the skill's own name, which also matches ``skills/<name>/``
in this repository — the convention a skill directory already has here.

**A ``library.json`` in each package.** A skill uploaded alone would otherwise lose
the context that makes it reviewable: which library version it came from, which
layer it belongs to, what its companions are, and which contract version the
library was built against. Roughly 500 bytes per package buys that back.

**No per-package ``checksums.json``.** The library archive carries a ledger because
it has 45 members and a consumer needs to verify all of them. A package has four
files whose digests are published in ``skills/CHECKSUMS.json`` at the repository
root — one index a reviewer can check against, instead of thirteen files each
describing itself.

## What a package still is, and is not

It is a **declaration**: no prompt, no executable body, no credential. It carries no
implementation, which is deliberate and carried forward from C0.5 — a skill library
is a configuration asset. And it is byte-for-byte reproducible, so re-running the
build yields identical archives.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from creator_package.hashing import (
    ARCHIVE_TIMESTAMP,
    canonical_bytes,
    digest_bytes,
)
from creator_plugin_builder import (
    META_SKILLS,
    UNIVERSAL_SKILLS,
    library_document,
)

from .emitter import (
    emit_skill,
    skill_capabilities,
    validate_emitted_manifest,
)
from .errors import (
    LibraryError,
    LibraryInputError,
    LibrarySkillMissingError,
    LibraryStructureError,
)
from .manifest import (
    GENERATED_BY,
    LIBRARY_ID,
    LIBRARY_FORMAT_VERSION,
    MANIFEST_SCHEMA_VERSION,
)
from .paths import (
    LIBRARY_FILE,
    PACKAGE_SUFFIX,
    STANDALONE_FILES,
    package_classify,
    package_filename,
    package_member_sort_key,
    package_members,
    package_root,
)

#: The prefix every standalone package filename carries.
FILENAME_PREFIX = "creator-"

#: The compression method and level, matching the library archive.
COMPRESSION = zipfile.ZIP_DEFLATED
COMPRESS_LEVEL = 9
EXTERNAL_ATTR = 0o644 << 16

#: The keys a standalone package's own ``manifest.json`` may carry.
#:
#: A superset of the skill manifest's keys: a standalone package also records where
#: in the library it sits and what the archive is called, because a reader holding
#: one file has no other way to learn those.
PACKAGE_MANIFEST_KEYS: tuple[str, ...] = (
    "name",
    "version",
    "library_layer",
    "library_version",
    "library_id",
    "package_filename",
    "entrypoint",
    "capabilities",
    "produces",
    "note",
)


@dataclass(frozen=True, slots=True)
class SkillPackage:
    """One built, uploadable skill package."""

    name: str
    layer: str
    version: str
    filename: str
    members: Mapping[str, bytes]
    payload: bytes
    entry: Mapping[str, Any]

    @property
    def size_bytes(self) -> int:
        return len(self.payload)

    @property
    def sha256(self) -> str:
        return digest_bytes(self.payload)

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def root(self) -> str:
        return package_root(self.name)

    @property
    def skill_md(self) -> str:
        return self.members[package_members(self.name)["SKILL.md"]].decode("utf-8")

    @property
    def manifest(self) -> dict[str, Any]:
        return json.loads(
            self.members[package_members(self.name)["manifest.json"]].decode("utf-8")
        )

    @property
    def skill_document(self) -> dict[str, Any]:
        return json.loads(
            self.members[package_members(self.name)["skill.json"]].decode("utf-8")
        )

    @property
    def library_metadata(self) -> dict[str, Any]:
        return json.loads(
            self.members[package_members(self.name)[LIBRARY_FILE]].decode("utf-8")
        )

    def report(self) -> dict[str, Any]:
        """The package's entry in an upload index."""

        return {
            "skill": self.name,
            "layer": self.layer,
            "version": self.version,
            "filename": self.filename,
            "sha256": self.sha256,
            "bytes": self.size_bytes,
            "members": self.member_count,
            "root": self.root,
            "entrypoint": f"{self.root}/SKILL.md",
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "report": self.report(),
            "manifest": self.manifest,
            "skill": self.skill_document,
            "library": self.library_metadata,
        }


def skill_layer(name: str) -> str:
    """Which layer a skill belongs to, rejecting an unknown name."""

    if name in UNIVERSAL_SKILLS:
        return "universal"
    if name in META_SKILLS:
        return "meta"
    raise LibrarySkillMissingError(
        f"the library declares no skill {name!r}",
        detail="declared skills: "
        + ", ".join(sorted(set(UNIVERSAL_SKILLS) | set(META_SKILLS))),
    )


def library_metadata(
    *,
    name: str,
    layer: str,
    library_version: str,
    companions: Sequence[str],
) -> dict[str, Any]:
    """The ``library.json`` that travels inside one standalone package.

    Records what a skill uploaded alone would otherwise lose: the library it came
    from, its version, the layer the skill sits on, its companions, and the contract
    version the library was built against.
    """

    doc = library_document()
    return {
        "library_id": LIBRARY_ID,
        "library_version": library_version,
        "format_version": LIBRARY_FORMAT_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "skill": name,
        "library_layer": layer,
        "universal_skill_count": doc["universal_skill_count"],
        "meta_skill_count": doc["meta_skill_count"],
        "companions": sorted(c for c in companions if c != name),
        "packaged_alone": True,
        "partition_note": (
            "this package is one skill of the library, packaged alone for upload; "
            "the whole library also ships as creator_skill_library.zip"
        ),
    }


def package_manifest(
    *,
    name: str,
    layer: str,
    library_version: str,
    capabilities: Sequence[str],
    produces: str,
    note: str,
) -> dict[str, Any]:
    """The standalone package's ``manifest.json``."""

    return {
        "name": name,
        "version": library_version,
        "library_layer": layer,
        "library_version": library_version,
        "library_id": LIBRARY_ID,
        "package_filename": package_filename(name, prefix=FILENAME_PREFIX),
        "entrypoint": "SKILL.md",
        "capabilities": list(capabilities),
        "produces": produces,
        "note": note,
    }


def _write_zip(members: Mapping[str, bytes]) -> bytes:
    """Write a standalone package's zip, deterministically."""

    buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(
            buffer,
            mode="w",
            compression=COMPRESSION,
            compresslevel=COMPRESS_LEVEL,
        ) as archive:
            for path in sorted(members, key=package_member_sort_key):
                info = zipfile.ZipInfo(filename=path, date_time=ARCHIVE_TIMESTAMP)
                info.compress_type = COMPRESSION
                info.external_attr = EXTERNAL_ATTR
                info.create_system = 0
                archive.writestr(info, members[path])
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        from .errors import LibraryArchiveError

        raise LibraryArchiveError(f"cannot write skill package: {exc}") from exc
    return buffer.getvalue()


def build_skill_package(
    name: str,
    *,
    library_version: str = LIBRARY_FORMAT_VERSION,
    companions: Sequence[str] | None = None,
) -> SkillPackage:
    """Build one standalone, uploadable skill package.

    Raises:
        LibrarySkillMissingError: the library declares no such skill.
    """

    if not isinstance(name, str) or not name.strip():
        raise LibraryInputError("a skill package needs a skill name")
    if not library_version:
        raise LibraryInputError("a skill package needs a library version")

    layer = skill_layer(name)
    # The whole library, so one skill's document reads the same wherever it is
    # packaged. See the same note in :mod:`creator_library.builder`.
    peers = tuple(
        sorted(set(UNIVERSAL_SKILLS) | set(META_SKILLS))
        if companions is None
        else companions
    )

    declaration = _declaration(name)
    emitted = emit_skill(
        name,
        declaration,
        layer=layer,
        library_version=library_version,
        companions=peers,
    )

    # The library's own emitted files are keyed under creator_skill_library/...;
    # this package keys them under the skill's own name instead.
    members: dict[str, bytes] = {}
    library_paths = package_members(name)
    for filename in ("SKILL.md", "manifest.json", "skill.json"):
        source = next(p for p in emitted if p.endswith("/" + filename))
        members[library_paths[filename]] = emitted[source]

    manifest = package_manifest(
        name=name,
        layer=layer,
        library_version=library_version,
        capabilities=skill_capabilities(name, declaration),
        produces=str(declaration.get("produces", "")),
        note=_note_from(emitted),
    )
    members[library_paths["manifest.json"]] = canonical_bytes(manifest)

    members[library_paths[LIBRARY_FILE]] = canonical_bytes(
        library_metadata(
            name=name,
            layer=layer,
            library_version=library_version,
            companions=peers,
        )
    )

    payload = _write_zip(members)
    package = SkillPackage(
        name=name,
        layer=layer,
        version=library_version,
        filename=package_filename(name, prefix=FILENAME_PREFIX),
        members={k: v for k, v in sorted(
            members.items(), key=lambda item: package_member_sort_key(item[0])
        )},
        payload=payload,
        entry={
            "name": name,
            "library_layer": layer,
            "version": library_version,
            "skill_type": str(declaration.get("skill_type", "")),
            "purpose": str(declaration.get("purpose", "")),
            "produces": str(declaration.get("produces", "")),
            "capabilities": list(manifest["capabilities"]),
        },
    )
    return package


def _declaration(name: str) -> dict[str, Any]:
    from .builder import declaration_for

    return declaration_for(name)


def _note_from(emitted: Mapping[str, bytes]) -> str:
    """Read the no-test-command note out of the skill manifest the emitter wrote."""

    path = next(p for p in emitted if p.endswith("/manifest.json"))
    return str(json.loads(emitted[path].decode("utf-8")).get("note", ""))


def build_skill_packages(
    *,
    library_version: str = LIBRARY_FORMAT_VERSION,
    universal: Sequence[str] | None = None,
    meta: Sequence[str] | None = None,
) -> tuple[SkillPackage, ...]:
    """Build every standalone package: 10 universal skills and 3 meta skills."""

    universal_names = tuple(UNIVERSAL_SKILLS if universal is None else universal)
    meta_names = tuple(META_SKILLS if meta is None else meta)
    companions = tuple(sorted(universal_names + meta_names))

    packages = [
        build_skill_package(
            name, library_version=library_version, companions=companions
        )
        for name in universal_names + meta_names
    ]
    if not packages:
        raise LibraryInputError("no skills were selected to package")
    return tuple(packages)


def upload_index(
    packages: Sequence[SkillPackage],
    *,
    library_version: str = LIBRARY_FORMAT_VERSION,
) -> dict[str, Any]:
    """The ``INDEX.json`` a reviewer checks the upload against.

    Records every package's filename, size and digest, so verifying thirteen
    downloads is one comparison each rather than thirteen self-describing ledgers.
    """

    entries = [package.report() for package in packages]
    return {
        "library_id": LIBRARY_ID,
        "library_version": library_version,
        "format_version": LIBRARY_FORMAT_VERSION,
        "generated_by": GENERATED_BY,
        "package_count": len(entries),
        "universal_skill_count": sum(1 for e in entries if e["layer"] == "universal"),
        "meta_skill_count": sum(1 for e in entries if e["layer"] == "meta"),
        "total_bytes": sum(e["bytes"] for e in entries),
        "filename_prefix": FILENAME_PREFIX,
        "purpose": (
            "one skill per archive, for upload to a Shared Skill Library that "
            "ingests skills individually"
        ),
        "packages": entries,
    }


def checksum_index(packages: Sequence[SkillPackage]) -> dict[str, Any]:
    """The ``CHECKSUMS.json`` for the upload directory."""

    return {
        "algorithm": "sha256",
        "package_count": len(packages),
        "packages": {
            package.filename: {
                "sha256": package.sha256,
                "bytes": package.size_bytes,
                "skill": package.name,
                "library_layer": package.layer,
            }
            for package in sorted(packages, key=lambda p: p.filename)
        },
    }


def write_skill_packages(
    packages: Sequence[SkillPackage],
    out_root: str | Path,
) -> list[Path]:
    """Write every package, plus the two index files, into ``out_root``."""

    target = Path(out_root)
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for package in packages:
        path = target / package.filename
        path.write_bytes(package.payload)
        written.append(path)

    version = packages[0].version if packages else LIBRARY_FORMAT_VERSION

    index_path = target / "INDEX.json"
    index_path.write_text(
        json.dumps(
            upload_index(packages, library_version=version),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(index_path)

    checksums_path = target / "CHECKSUMS.json"
    checksums_path.write_text(
        json.dumps(
            checksum_index(packages),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(checksums_path)

    return written


__all__ = [
    "COMPRESSION",
    "COMPRESS_LEVEL",
    "EXTERNAL_ATTR",
    "FILENAME_PREFIX",
    "PACKAGE_MANIFEST_KEYS",
    "PACKAGE_SUFFIX",
    "SkillPackage",
    "build_skill_package",
    "build_skill_packages",
    "checksum_index",
    "library_metadata",
    "package_manifest",
    "skill_layer",
    "upload_index",
    "write_skill_packages",
]
