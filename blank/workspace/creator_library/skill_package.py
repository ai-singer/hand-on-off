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

Each skill becomes one archive holding three files **at its root**:

```text
creator-text-distillation.zip
├── SKILL.md          ← at the root, where the library looks
├── manifest.json
└── skill.json
```

## The one thing that must not go wrong

**No wrapper directory.** A shared skill library matches a skill by the description in
``SKILL.md``'s front matter and then loads that file from the **archive root**. Zipping
a skill *directory* by the obvious method produces ``text-distillation/SKILL.md`` —
one level deeper than the library looks. The archive looks right in a file listing and
still fails to load, because the library finds no entrypoint at the root.

So the members are written flat, and
:func:`creator_library.skill_package_validation.validate_package_structure` refuses any
archive with a directory in it at all. The failure is silent otherwise, which is why it
gets a check of its own rather than a comment.

## Three files

``SKILL.md`` is what the library reads. ``manifest.json`` is the convention every skill
in this repository follows and carries the capability list. ``skill.json`` is the
declaration, machine-readable.

`library.json` was tried and removed: nothing read it, it duplicated the manifest, and
its companion list named the other twelve skills — so every skill's file depended on
every other skill in the library, which is the opposite of standalone. The two facts
worth keeping from it, ``library_id`` and ``library_version``, moved into
``manifest.json``.

## What a skill still is, and is not

It is a **declaration**: no prompt, no executable body, no credential. It carries no
implementation, which is deliberate and carried forward from C0.5 — a skill library is
a configuration asset. And it is byte-for-byte reproducible, so re-running the build
yields identical archives.
"""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from creator_package.hashing import (
    ARCHIVE_TIMESTAMP,
    digest_bytes,
)
from creator_plugin_builder import META_SKILLS, UNIVERSAL_SKILLS

from .emitter import MANIFEST_KEYS, emit_skill
from .errors import (
    LibraryInputError,
    LibrarySkillMissingError,
)
from .manifest import (
    GENERATED_BY,
    LIBRARY_ID,
    LIBRARY_FORMAT_VERSION,
)
from .paths import (
    PACKAGE_SUFFIX,
    SKILL_FILES,
    STANDALONE_FILES,
    archive_members,
    directory_members,
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

#: The keys a skill's ``manifest.json`` carries — the same in a skill directory as in
#: the library archive, because they are the same document.
PACKAGE_MANIFEST_KEYS: tuple[str, ...] = MANIFEST_KEYS


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
        return self.members["SKILL.md"].decode("utf-8")

    @property
    def manifest(self) -> dict[str, Any]:
        return json.loads(
            self.members["manifest.json"].decode("utf-8")
        )

    @property
    def skill_type(self) -> str:
        """The declaration's skill type, from the entry."""

        return str(self.entry.get("skill_type", ""))

    @property
    def capabilities(self) -> tuple[str, ...]:
        """What the skill declares it can do — the manifest's capability list."""

        return tuple(self.manifest["capabilities"])

    def report(self) -> dict[str, Any]:
        """The skill's entry in an upload index."""

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
            "files": sorted(
                member.rsplit("/", 1)[-1] for member in self.members
            ),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "report": self.report(),
            "manifest": self.manifest,
            "skill_md": self.skill_md,
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

    # Flat: the three files at the archive root, with no wrapper directory. See the
    # module docstring — a nesting level here makes the skill unloadable.
    members: dict[str, bytes] = {}
    for filename in SKILL_FILES:
        source = next(p for p in emitted if p.endswith("/" + filename))
        members[filename] = emitted[source]

    payload = _write_zip(members)
    manifest = json.loads(members["manifest.json"].decode("utf-8"))
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
    """Write every package as a zip, plus the two index files, into ``out_root``."""

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


def unpack_skill_package(
    package: SkillPackage,
    out_root: str | Path,
) -> Path:
    """Write one package **unpacked** — a skill directory, not an archive.

    This is the form a shared skill library actually reads. It matches a skill by its
    description and then loads ``SKILL.md`` from the skill's directory, so an archive
    has to be extracted before anything can see it. Handing over the directory skips
    that step, and writing the members out directly produces exactly the same tree as
    extracting the zip would.
    """

    target = Path(out_root) / package.root
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    for member in sorted(package.members, key=package_member_sort_key):
        filename = member.rsplit("/", 1)[-1]
        (target / filename).write_bytes(package.members[member])

    return target


def unpack_skill_packages(
    packages: Sequence[SkillPackage],
    out_root: str | Path,
    *,
    with_indexes: bool = True,
) -> list[Path]:
    """Write every package unpacked, into one directory.

    ``out_root`` ends up holding one directory per skill — the shape a shared skill
    library is pointed at — plus the two index files unless ``with_indexes`` is off.
    """

    target = Path(out_root)
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for package in packages:
        written.append(unpack_skill_package(package, target))

    if not with_indexes:
        return written

    version = packages[0].version if packages else LIBRARY_FORMAT_VERSION

    index_path = target / "INDEX.json"
    index_path.write_text(
        json.dumps(
            unpacked_index(packages, library_version=version),
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
            unpacked_checksum_index(packages),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    written.append(checksums_path)

    return written


def unpacked_index(
    packages: Sequence[SkillPackage],
    *,
    library_version: str = LIBRARY_FORMAT_VERSION,
) -> dict[str, Any]:
    """The upload index for an **unpacked** set: directories, not archives.

    Records each skill's directory and the digest of each of its files, because there
    is no archive digest to record: the unit here is a directory.
    """

    entries: list[dict[str, Any]] = []
    for package in packages:
        entries.append(
            {
                "skill": package.name,
                "layer": package.layer,
                "version": package.version,
                "directory": package.root,
                "entrypoint": f"{package.root}/SKILL.md",
                "files": sorted(
                    member.rsplit("/", 1)[-1] for member in package.members
                ),
                "bytes": sum(
                    len(payload) for payload in package.members.values()
                ),
            }
        )

    return {
        "library_id": LIBRARY_ID,
        "library_version": library_version,
        "format_version": LIBRARY_FORMAT_VERSION,
        "generated_by": GENERATED_BY,
        "distribution": "unpacked",
        "skill_count": len(entries),
        "universal_skill_count": sum(1 for e in entries if e["layer"] == "universal"),
        "meta_skill_count": sum(1 for e in entries if e["layer"] == "meta"),
        "total_bytes": sum(e["bytes"] for e in entries),
        "purpose": (
            "one directory per skill, each holding SKILL.md at its root, for a "
            "shared skill library that loads SKILL.md from a skills directory"
        ),
        "note": (
            "an archive would have to be extracted before anything could read "
            "SKILL.md, so these are written out rather than zipped"
        ),
        "skills": entries,
    }


def unpacked_checksum_index(
    packages: Sequence[SkillPackage],
) -> dict[str, Any]:
    """Per-**file** digests for an unpacked set.

    A zipped set has one digest per archive. An unpacked set has one per file, and
    ``SKILL.md`` — the file a library actually reads — is the one worth checking
    first, so it is listed first within each skill.
    """

    files: dict[str, Any] = {}
    for package in packages:
        paths = directory_members(package.name)
        for filename in SKILL_FILES:
            payload = package.members[filename]
            files[paths[filename]] = {
                "sha256": digest_bytes(payload),
                "bytes": len(payload),
                "skill": package.name,
                "library_layer": package.layer,
            }

    return {
        "algorithm": "sha256",
        "distribution": "unpacked",
        "skill_count": len(packages),
        "file_count": len(files),
        "entrypoint_first": True,
        "files": files,
    }


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
    "skill_layer",
    "unpack_skill_package",
    "unpack_skill_packages",
    "unpacked_checksum_index",
    "unpacked_index",
    "upload_index",
    "write_skill_packages",
]
