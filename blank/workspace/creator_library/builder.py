"""The Skill Library builder: declarations in, ``creator_skill_library.zip`` out.

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

The builder is the last step of the factory's production chain and the first step of
distribution. It assembles an archive; it does not upload it, does not call Lobster,
does not create an agent, and does not generate content.

## The order the build has to happen in

Two hashes are recorded, and each depends on something the other cannot know:

```text
    1. emit every member            (skills, registry, schema, README, version)
    2. checksums.json               over the emitted members
    3. content_hash                 over the members, excluding the two self-referential files
    4. manifest.json                records content_hash, plus artifact_hash
    5. write the zip                ← artifact_hash is only knowable here
    6. artifact_hash                over the finished bytes
    7. rewrite manifest.json        with artifact_hash, re-checksum, re-hash
```

Step 7 looks circular and is: the manifest cannot contain the digest of a file that
contains the manifest. It is resolved the honest way — **content_hash is the
load-bearing digest and artifact_hash is advisory**. ``content_hash`` is computed
before the manifest exists and never changes afterwards, so it is truly verifiable;
``artifact_hash`` is recomputed after the final write and recorded for a downloader's
convenience. :func:`verify_artifact` re-derives both from the finished bytes and
reports which one holds.

## What the builder will not do

- **It will not ship a generated plugin.** Domains are a registry, not content. A
  shipped plugin would be stale the moment a domain is added, which is the failure
  mode the whole architecture exists to prevent.
- **It will not invent a skill.** Every skill comes from
  :mod:`creator_plugin_builder.library`; a declared skill with no declaration is an
  error, never an empty directory.
- **It will not carry a runtime, a prompt or a credential**, and the archive is
  checked for all three before it is returned.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from creator_package.hashing import canonical_bytes
from creator_plugin_builder import (
    META_SKILLS,
    PLUGIN_FORMAT_VERSION,
    UNIVERSAL_SKILLS,
    catalog_document,
    catalog_domains,
    skill_declarations,
)
from creator_plugin_builder.schema import build_schema

from .archive import (
    add_ledger,
    archive_names,
    artifact_digest,
    finalise,
    read_archive,
    write_archive,
)
from .emitter import emit_skill, validate_emitted_manifest
from .errors import LibraryInputError, LibrarySkillMissingError
from .manifest import (
    GENERATED_BY,
    LIBRARY_FORMAT_VERSION,
    LIBRARY_ID,
    build_domain_registry,
    build_manifest,
    build_readme,
    build_schema_entry,
    build_version_document,
    standard_exclusions,
)
from .paths import (
    ARCHIVE_FILENAME,
    CHECKSUMS_MEMBER,
    MANIFEST_MEMBER,
    README_MEMBER,
    REGISTRY_MEMBER,
    SCHEMA_MEMBER,
    VERSION_MEMBER,
    member_sort_key,
)

#: The default library version.
DEFAULT_LIBRARY_VERSION = LIBRARY_FORMAT_VERSION


@dataclass(frozen=True, slots=True)
class LibraryBuild:
    """A built library: the bytes, the members, and everything needed to audit it."""

    library_version: str
    members: Mapping[str, bytes]
    payload: bytes
    manifest: Mapping[str, Any]
    checksums: Mapping[str, str]
    version_document: Mapping[str, Any]
    registry: Mapping[str, Any]
    artifact_digest: str = ""

    @property
    def filename(self) -> str:
        return ARCHIVE_FILENAME

    @property
    def content_hash(self) -> str:
        return str(self.manifest["hashes"]["content_hash"])

    @property
    def recorded_artifact_hash(self) -> str:
        """The artifact hash recorded *inside* the archive.

        Advisory: writing a manifest that records a file's digest changes that file,
        so this never equals :attr:`actual_artifact_hash`.
        """

        return str(self.manifest["hashes"]["artifact_hash"])

    @property
    def actual_artifact_hash(self) -> str:
        """The SHA256 of the released bytes — what a downloader should verify."""

        return self.artifact_digest or artifact_digest(self.payload)

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def skill_names(self) -> tuple[str, ...]:
        return tuple(sorted(str(s["name"]) for s in self.manifest["skills"]))

    @property
    def universal_skill_names(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                str(s["name"])
                for s in self.manifest["skills"]
                if s["library_layer"] == "universal"
            )
        )

    @property
    def meta_skill_names(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                str(s["name"])
                for s in self.manifest["skills"]
                if s["library_layer"] == "meta"
            )
        )

    @property
    def domains(self) -> tuple[str, ...]:
        return tuple(
            sorted(str(d["domain"]) for d in self.registry["domains"])
        )

    @property
    def size_bytes(self) -> int:
        return len(self.payload)

    def report(self) -> dict[str, Any]:
        """The release report: what was built, and its digests."""

        return {
            "library_id": LIBRARY_ID,
            "library_version": self.library_version,
            "filename": self.filename,
            "status": "PASS",
            "members": self.member_count,
            "size_bytes": self.size_bytes,
            "universal_skills": list(self.universal_skill_names),
            "meta_skills": list(self.meta_skill_names),
            "domains": list(self.domains),
            "content_hash": self.content_hash,
            "recorded_artifact_hash": self.recorded_artifact_hash,
            "actual_artifact_hash": self.actual_artifact_hash,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest": dict(self.manifest),
            "version": dict(self.version_document),
            "registry": dict(self.registry),
            "checksums": dict(self.checksums),
            "report": self.report(),
        }


def declaration_for(name: str) -> dict[str, Any]:
    """The library declaration for one skill, rejecting an unknown name."""

    declarations = skill_declarations()
    try:
        return dict(declarations[name])
    except KeyError as exc:
        raise LibrarySkillMissingError(
            f"the library declares no skill {name!r}",
            detail="declared skills: " + ", ".join(sorted(declarations)),
        ) from exc


def emit_skills(
    *,
    library_version: str,
    universal: Sequence[str] | None = None,
    meta: Sequence[str] | None = None,
) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    """Emit every skill, returning the members and the manifest's skill entries."""

    universal_names = tuple(UNIVERSAL_SKILLS if universal is None else universal)
    meta_names = tuple(META_SKILLS if meta is None else meta)
    # The *whole* library, not the selected subset. A skill's companions are what the
    # library contains, and its document must say the same thing whether it is read
    # from an archive that carries all thirteen or from one that carries a few.
    companions = tuple(sorted(set(UNIVERSAL_SKILLS) | set(META_SKILLS)))

    members: dict[str, bytes] = {}
    entries: list[dict[str, Any]] = []

    for layer, names in (("universal", universal_names), ("meta", meta_names)):
        for name in names:
            declaration = declaration_for(name)
            emitted = emit_skill(
                name,
                declaration,
                layer=layer,
                library_version=library_version,
                companions=companions,
            )
            members.update(emitted)

            skill_manifest = json.loads(
                emitted[
                    next(p for p in emitted if p.endswith("/manifest.json"))
                ].decode("utf-8")
            )
            validate_emitted_manifest(skill_manifest)

            entries.append(
                {
                    "name": name,
                    "library_layer": layer,
                    "version": library_version,
                    "skill_type": str(declaration.get("skill_type", "")),
                    "purpose": str(declaration.get("purpose", "")),
                    "produces": str(declaration.get("produces", "")),
                    "entrypoint": "SKILL.md",
                    "capabilities": list(skill_manifest["capabilities"]),
                    "directory": next(
                        p for p in sorted(emitted) if p.endswith("/SKILL.md")
                    ).rsplit("/", 1)[0],
                }
            )

    if not members:
        raise LibraryInputError("the library emitted no skills")
    return members, entries


def build_library(
    *,
    library_version: str = DEFAULT_LIBRARY_VERSION,
    validate: bool = True,
    universal: Sequence[str] | None = None,
    meta: Sequence[str] | None = None,
) -> LibraryBuild:
    """Build ``creator_skill_library.zip`` in memory.

    Args:
        library_version: the version to release as.
        validate: run every check before returning. On by default.
        universal: which universal skills to release. Defaults to the whole library.
        meta: which meta skills to release. Defaults to the whole library.

    Raises:
        LibraryError: with a stable code, on any failed check.
    """

    if not isinstance(library_version, str) or not library_version.strip():
        raise LibraryInputError("a library needs a version")

    members, skill_entries = emit_skills(
        library_version=library_version, universal=universal, meta=meta
    )

    registry = build_domain_registry(
        catalog_version=str(catalog_document()["catalog_version"]),
        entries=_catalog_entries(),
        library_version=library_version,
    )
    members[REGISTRY_MEMBER] = canonical_bytes(registry)

    members[SCHEMA_MEMBER] = canonical_bytes(build_schema())

    members[VERSION_MEMBER] = canonical_bytes(
        build_version_document(
            library_version=library_version,
            skill_count=len(skill_entries),
            domain_count=registry["domain_count"],
        )
    )

    members[README_MEMBER] = build_readme(
        library_version=library_version,
        skills=skill_entries,
        domain_plugins=registry,
    ).encode("utf-8")

    schemas = [
        build_schema_entry(
            name="domain_plugin",
            version=PLUGIN_FORMAT_VERSION,
            member=SCHEMA_MEMBER,
            validates="a domain plugin produced by meta_skills/domain-plugin-builder",
        )
    ]

    content_hash = finalise(members)["content_hash"]

    def assemble(
        artifact_hash: str,
        *,
        with_ledger: bool,
    ) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
        """Build the manifest and add the ledger, for a given artifact hash.

        Called twice: once to produce the bytes the artifact hash is measured from,
        once with that hash recorded. The manifest is excluded from ``content_hash``,
        so this loop cannot change the content digest.

        ``with_ledger`` says whether ``checksums.json`` exists yet. The member summary
        counts it when it does — and the first call happens before it does, which is
        why the count cannot simply be taken from the member set.
        """

        manifest = build_manifest(
            library_version=library_version,
            skills=skill_entries,
            domain_plugins=_registry_summary(registry),
            schemas=schemas,
            content_hash=content_hash,
            artifact_hash=artifact_hash,
            member_summary=_member_summary(
                {**members, MANIFEST_MEMBER: b""}, ledger_member=with_ledger
            ),
            exclusions=standard_exclusions(),
            generated_by=GENERATED_BY,
        )
        staged = dict(members)
        staged[MANIFEST_MEMBER] = canonical_bytes(manifest)
        staged, ledger = add_ledger(staged)
        return staged, manifest, ledger

    # Pass 1: manifest with a placeholder hash, to obtain bytes the hash can cover.
    staged, _, _ = assemble(content_hash, with_ledger=False)
    payload = write_archive(staged)
    artifact_hash = artifact_digest(payload)

    # Pass 2: the real manifest, the real ledger, the released bytes.
    staged, manifest, ledger = assemble(artifact_hash, with_ledger=True)
    payload = write_archive(staged)
    # The artifact hash is advisory by construction: recording it changes the bytes,
    # so the released file's own digest differs from the one recorded inside it.
    released_artifact_hash = artifact_digest(payload)

    build = LibraryBuild(
        library_version=library_version,
        members={
            key: value
            for key, value in sorted(
                staged.items(), key=lambda item: member_sort_key(item[0])
            )
        },
        payload=payload,
        manifest=manifest,
        checksums={
            path: (row["sha256"] or "")
            for path, row in ledger["files"].items()
        },
        version_document=json.loads(staged[VERSION_MEMBER].decode("utf-8")),
        registry=registry,
        artifact_digest=released_artifact_hash,
    )

    if validate:
        verify_artifact(build, require_complete=universal is None and meta is None)

    return build


def verify_artifact(
    build: LibraryBuild,
    *,
    require_complete: bool = True,
) -> dict[str, str]:
    """Re-derive every claim the archive makes about itself, from its own bytes.

    Re-reads the members out of the finished zip rather than trusting the in-memory
    copy, so a discrepancy between what was built and what was written is caught.
    """

    from .validation import (
        validate_archive,
        verify_library_hash,
    )

    written = read_archive(build.payload)
    if set(written) != set(build.members):
        from .errors import LibraryStructureError

        missing = sorted(set(build.members) - set(written))
        extra = sorted(set(written) - set(build.members))
        raise LibraryStructureError(
            "the written archive does not match the built members",
            detail=f"missing: {missing}; extra: {extra}",
        )

    for member, payload in written.items():
        if build.members[member] != payload:
            from .errors import LibraryArchiveError

            raise LibraryArchiveError(
                f"member {member!r} differs between the build and the archive"
            )

    report = validate_archive(
        build.payload,
        catalog_domains=catalog_domains(),
        require_complete_library=require_complete,
    )
    if not verify_library_hash(written, build.manifest):
        from .errors import LibraryChecksumError

        raise LibraryChecksumError(
            "the archive's content does not match the content_hash it records",
            detail="re-derived the digest from the written members",
        )

    # artifact_hash is advisory: writing the manifest that records it changes the
    # bytes. Re-derive it from the finished payload and report which of the two holds.
    recorded = build.recorded_artifact_hash
    actual = build.actual_artifact_hash
    checks = dict(report.checks)
    checks["content_hash"] = "PASS"
    checks["artifact_hash"] = "PASS" if recorded == actual else "ADVISORY"
    return checks


def write_library(
    build: LibraryBuild,
    out_root: str | Path = ".",
    *,
    filename: str = "",
) -> Path:
    """Write the archive to disk and return its path."""

    target = Path(out_root)
    target.mkdir(parents=True, exist_ok=True)
    path = target / (filename or build.filename)
    path.write_bytes(build.payload)
    return path


def build_and_write(
    out_root: str | Path = ".",
    **kwargs: Any,
) -> tuple[LibraryBuild, Path]:
    """Build the library and write it, returning both."""

    build = build_library(**kwargs)
    return build, write_library(build, out_root)


def describe_library(build: LibraryBuild) -> dict[str, Any]:
    """The release report as a document."""

    return build.report()


def member_listing(build: LibraryBuild) -> tuple[str, ...]:
    """Every member, in the archive's own order."""

    return archive_names(build.payload)


def _catalog_entries() -> list[dict[str, Any]]:
    """The builder's catalog, as the registry publisher reads it."""

    from creator_plugin_builder import default_registry

    registry = default_registry()
    entries: list[dict[str, Any]] = []
    for domain in registry.domains():
        entry = registry.get(domain)
        entries.append(
            {
                "domain": entry.domain,
                "display_name": entry.display_name,
                "version": entry.version,
                "requirements": list(entry.requirements),
                "platforms": list(entry.platforms),
            }
        )
    return entries


def _registry_summary(registry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "registry_member": REGISTRY_MEMBER,
        "catalog_version": registry["catalog_version"],
        "domain_count": registry["domain_count"],
        "domains": [
            {
                "domain": entry["domain"],
                "plugin_name": entry["plugin_name"],
                "version": entry["version"],
                "buildable": entry["buildable"],
            }
            for entry in registry["domains"]
        ],
        "generated_at_runtime": True,
    }


def _member_summary(
    members: Mapping[str, bytes],
    *,
    ledger_member: bool = False,
) -> dict[str, Any]:
    """The manifest's own count of the archive's members.

    ``ledger_member`` adds the one member that does not exist yet when the manifest
    is first assembled. Counting only what is present would under-report the archive
    by exactly one file, and an off-by-one in a manifest is the kind of thing that
    makes the whole document untrustworthy.

    The byte total is the honest sum of the members that exist. The ledger is *not*
    counted in it, and the field's name says so rather than implying a total it
    cannot know: the ledger's own length depends on the ledger.
    """

    from .paths import summarise_members

    summary = summarise_members(dict(members))
    if ledger_member:
        summary["member_count"] += 1
        summary["by_kind"]["root"] = summary["by_kind"].get("root", 0) + 1
    summary["bytes_note"] = (
        "sum of every member except checksums.json, whose own length depends on itself"
    )
    return summary


__all__ = [
    "DEFAULT_LIBRARY_VERSION",
    "LibraryBuild",
    "build_and_write",
    "build_library",
    "declaration_for",
    "describe_library",
    "emit_skills",
    "member_listing",
    "verify_artifact",
    "write_library",
]
