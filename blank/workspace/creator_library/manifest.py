"""The release manifest, and the other library-root documents.

The manifest is what makes an uploaded library *accountable*. It answers, in one
document: which library is this, which version, when was it released, what is inside
it, which domains can it build, and what is its digest.

```text
manifest.json
    library_id            "creator_skill_library"
    library_version       1.0.0
    format_version        1.0.0
    builder               who produced the archive
    created_at            deterministic, never the wall clock
    layers                universal + meta, with counts
    skills[]              every skill, with its layer, version and paths
    domain_plugins        the published registry summary
    schemas[]             the contracts a consumer validates against
    hashes                content_hash, artifact_hash
    exclusions            what is deliberately absent, and why
    integrity             the checksum rule, stated so it can be re-derived
```

## The two hashes, and why they are two

``content_hash``
    Over every member except ``manifest.json`` and ``checksums.json`` — the two files
    that record a digest and therefore cannot contain one. This identifies the
    library's *content*.

``artifact_hash``
    Over the finished ``.zip`` bytes. This identifies the *file* a user uploads, so a
    consumer can verify a download without unpacking it first.

Both are re-derivable, and :func:`creator_library.validation.verify_library_hash`
re-derives them rather than trusting the recorded values.

## What the manifest must never carry

No prompt, no model, no provider, no credential, no API key, no runtime, no
endpoint. A library manifest describes a configuration asset; those keys have no
meaning in one, and :mod:`creator_library.validation` refuses a manifest that carries
any of them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from creator_package.hashing import (
    ARCHIVE_TIMESTAMP,
    BUILDER_VERSION,
    DEFAULT_TIMESTAMP,
    PACKAGE_FORMAT_VERSION,
    canonical_bytes,
)

from .errors import LibraryManifestError, LibrarySchemaError

#: The library's own identifier.
LIBRARY_ID = "creator_skill_library"

#: The library format version.
LIBRARY_FORMAT_VERSION = "1.0.0"

#: The manifest schema version.
MANIFEST_SCHEMA_VERSION = "1.0.0"

#: The builder identity recorded in the manifest.
GENERATED_BY = f"creator_library.builder {BUILDER_VERSION}"

#: Keys every release manifest must carry.
REQUIRED_MANIFEST_KEYS: tuple[str, ...] = (
    "library_id",
    "library_version",
    "format_version",
    "manifest_schema_version",
    "generated_by",
    "created_at",
    "layers",
    "skills",
    "domain_plugins",
    "schemas",
    "hashes",
    "integrity",
    "exclusions",
)

#: Keys a release manifest must never carry.
#:
#: Note what is deliberately *absent*: ``entrypoint``. Every skill manifest in this
#: repository carries one naming the markdown document a reader opens, and the
#: release manifest's skill entries do too, so forbidding the key would forbid the
#: repository's own convention. The isolation check distinguishes them by value
#: instead — an entrypoint to a markdown document is documentation, an entrypoint to
#: anything else is an executable.
FORBIDDEN_MANIFEST_KEYS: tuple[str, ...] = (
    "prompt",
    "prompts",
    "system_prompt",
    "prompt_template",
    "model",
    "model_id",
    "provider",
    "api_key",
    "apikey",
    "api_secret",
    "credentials",
    "credential",
    "secret",
    "secrets",
    "token",
    "tokens",
    "access_token",
    "refresh_token",
    "password",
    "passwd",
    "private_key",
    "api_secret",
    "runtime",
    "entry_point",
    "executor",
    "handler",
    "callback",
    "code",
    "script",
    "deploy",
    "deployment",
    "endpoint",
    "webhook",
    "test_command",
)

#: The checksum rule, stated once so a consumer can re-derive it.
INTEGRITY_RULE = (
    "content_hash: sha256 over '<path>\\0<sha256 of member bytes>\\n' for every "
    "archive member in sorted path order, excluding manifest.json and checksums.json. "
    "artifact_hash: sha256 over the finished .zip bytes."
)


def build_manifest(
    *,
    library_version: str,
    skills: Sequence[Mapping[str, Any]],
    domain_plugins: Mapping[str, Any],
    schemas: Sequence[Mapping[str, Any]],
    content_hash: str,
    artifact_hash: str,
    member_summary: Mapping[str, Any],
    exclusions: Sequence[Mapping[str, str]],
    generated_by: str = GENERATED_BY,
    created_at: str = DEFAULT_TIMESTAMP,
) -> dict[str, Any]:
    """Build the release manifest."""

    if not library_version:
        raise LibraryManifestError("a release manifest needs a library version")
    if not content_hash or not artifact_hash:
        raise LibraryManifestError(
            "a release manifest needs both a content hash and an artifact hash",
            detail="one identifies the content, the other the uploaded file",
        )

    layers: dict[str, Any] = {}
    for skill in skills:
        layer = str(skill["library_layer"])
        entry = layers.setdefault(layer, {"count": 0, "skills": []})
        entry["count"] += 1
        entry["skills"].append(skill["name"])

    manifest = {
        "library_id": LIBRARY_ID,
        "library_version": library_version,
        "format_version": LIBRARY_FORMAT_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_by": generated_by,
        "created_at": created_at,
        "layers": {
            key: {
                "count": value["count"],
                "skills": sorted(value["skills"]),
            }
            for key, value in sorted(layers.items())
        },
        "skills": [dict(skill) for skill in skills],
        "domain_plugins": dict(domain_plugins),
        "schemas": [dict(schema) for schema in schemas],
        "hashes": {
            "algorithm": "sha256",
            "content_hash": content_hash,
            "artifact_hash": artifact_hash,
        },
        "integrity": {
            "rule": INTEGRITY_RULE,
            "self_reference": ["manifest.json", "checksums.json"],
            "member_summary": dict(member_summary),
        },
        "exclusions": [dict(entry) for entry in exclusions],
    }
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest: Mapping[str, Any]) -> None:
    """Refuse a manifest that is incomplete or carries a forbidden key."""

    if not isinstance(manifest, Mapping):
        raise LibraryManifestError("a release manifest must be an object")

    forbidden = sorted(set(manifest) & set(FORBIDDEN_MANIFEST_KEYS))
    if forbidden:
        raise LibraryManifestError(
            "a release manifest carries forbidden keys: " + ", ".join(forbidden),
            detail="a library manifest describes a configuration asset",
        )

    missing = sorted(set(REQUIRED_MANIFEST_KEYS) - set(manifest))
    if missing:
        raise LibraryManifestError(
            "a release manifest is missing keys: " + ", ".join(missing)
        )

    if manifest["library_id"] != LIBRARY_ID:
        raise LibraryManifestError(
            f"library_id must be {LIBRARY_ID!r}, found {manifest['library_id']!r}"
        )

    for key in ("content_hash", "artifact_hash"):
        value = manifest["hashes"].get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise LibraryManifestError(
                f"manifest hashes.{key} must be a sha256 hex digest"
            )

    if not manifest["skills"]:
        raise LibraryManifestError("a release manifest lists no skills")


def build_version_document(
    *,
    library_version: str,
    skill_count: int,
    domain_count: int,
    built_at: str = DEFAULT_TIMESTAMP,
) -> dict[str, Any]:
    """The ``version.json`` document."""

    return {
        "library_id": LIBRARY_ID,
        "library_version": library_version,
        "format_version": LIBRARY_FORMAT_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "archive_clock": list(ARCHIVE_TIMESTAMP),
        "built_at": built_at,
        "counts": {
            "skills": skill_count,
            "domain_plugins": domain_count,
        },
    }


def build_readme(
    *,
    library_version: str,
    skills: Sequence[Mapping[str, Any]],
    domain_plugins: Mapping[str, Any],
) -> str:
    """The library's own ``LIBRARY.md``: what it is, and how to use it.

    The README deliberately does **not** quote a digest. A document cannot contain the
    hash of the archive that contains it, and the first attempt at this file quoted the
    content hash — which meant writing the README changed the hash it quoted, so the
    released library disagreed with its own manifest. The digests live in
    ``manifest.json`` and ``checksums.json``, where they can be correct.
    """

    universal = [s for s in skills if s["library_layer"] == "universal"]
    meta = [s for s in skills if s["library_layer"] == "meta"]
    domains = list(domain_plugins.get("domains", ()))

    lines: list[str] = ["---"]
    lines.append(f"name: {LIBRARY_ID}")
    lines.append(f"version: {library_version}")
    lines.append("description: A shared skill library for building creator agents.")
    lines.append("---")
    lines.append("")
    lines.append(f"# {LIBRARY_ID}")
    lines.append("")
    lines.append(
        "A **skill library**, not a creator and not a runtime. Upload it once; from "
        "then on a domain request is answered by the library itself."
    )
    lines.append("")
    lines.append(f"- version: `{library_version}`")
    lines.append(f"- skills: {len(skills)} ({len(universal)} universal, {len(meta)} meta)")
    lines.append(f"- buildable domains: {len(domains)}")
    lines.append("- digests: `manifest.json` (`hashes`), and `checksums.json` per member")
    lines.append("")
    lines.append("## How it is used")
    lines.append("")
    lines.append("1. Upload this library to the Shared Skill Library.")
    lines.append("2. A user asks for a creator in some domain.")
    lines.append(
        "3. `domain-plugin-builder` turns that request into a domain plugin."
    )
    lines.append(
        "4. `domain-plugin-validator` checks the plugin before anything uses it."
    )
    lines.append("5. The agent is configured from the plugin and the universal skills.")
    lines.append("")
    lines.append(
        "Generated domain plugins are **not** in this archive. They are produced at "
        "run time and live with the creator they configure."
    )
    lines.append("")
    lines.append(f"## Universal Creator Skills ({len(universal)})")
    lines.append("")
    lines.append(
        "The same skills for every domain. Each carries no domain knowledge."
    )
    lines.append("")
    for skill in sorted(universal, key=lambda s: s["name"]):
        lines.append(f"- `{skill['name']}` — {_one_line(skill.get('purpose', ''))}")
    lines.append("")
    lines.append(f"## Meta Skills ({len(meta)})")
    lines.append("")
    lines.append("The skills that build and check the plugins.")
    lines.append("")
    for skill in sorted(meta, key=lambda s: s["name"]):
        lines.append(f"- `{skill['name']}` — {_one_line(skill.get('purpose', ''))}")
    lines.append("")
    lines.append(f"## Buildable Domains ({len(domains)})")
    lines.append("")
    lines.append(
        "Domains this library can build a plugin for. Each is a registry entry, not "
        "a shipped skill set: adding a domain adds a row here, not a new library."
    )
    lines.append("")
    for domain in domains:
        lines.append(
            f"- `{domain.get('domain')}` → `{domain.get('plugin_name')}` "
            f"(v{domain.get('version')})"
        )
    lines.append("")
    lines.append("## Layout")
    lines.append("")
    lines.append("```text")
    lines.append("creator_skill_library/")
    lines.append("├── LIBRARY.md")
    lines.append("├── manifest.json")
    lines.append("├── checksums.json")
    lines.append("├── version.json")
    lines.append("├── universal_skills/<skill>/{SKILL.md,manifest.json,skill.json}")
    lines.append("├── meta_skills/<skill>/{SKILL.md,manifest.json,skill.json}")
    lines.append("├── domain_plugins/registry.json")
    lines.append("└── schemas/domain_plugin.schema.json")
    lines.append("```")
    lines.append("")
    lines.append("## What this library does not contain")
    lines.append("")
    lines.append("- no runtime, no entry point, no executable code")
    lines.append("- no prompt")
    lines.append("- no credential, token or key")
    lines.append("- no generated domain plugin")
    lines.append("")
    return "\n".join(lines)


def build_domain_registry(
    *,
    catalog_version: str,
    entries: Sequence[Mapping[str, Any]],
    library_version: str,
) -> dict[str, Any]:
    """The published ``domain_plugins/registry.json``.

    This is the *published view* of the builder's catalog: which domains this library
    version can build a plugin for, and what each plugin will declare. It is not the
    catalog itself — the catalog lives in the builder skill, inside the archive.
    """

    domains: list[dict[str, Any]] = []
    for entry in entries:
        domain = str(entry["domain"])
        domains.append(
            {
                "domain": domain,
                "display_name": str(entry.get("display_name", domain)),
                "plugin_name": f"domain_{domain}_plugin",
                "version": str(entry.get("version", "1.0.0")),
                "requirements": list(entry.get("requirements", ())),
                "platforms": list(entry.get("platforms", ())),
                "buildable": True,
                "note": (
                    "produced at run time by meta_skills/domain-plugin-builder; "
                    "not shipped in this archive"
                ),
            }
        )

    return {
        "library_id": LIBRARY_ID,
        "library_version": library_version,
        "catalog_version": catalog_version,
        "domain_count": len(domains),
        "generated_at_runtime": True,
        "domains": sorted(domains, key=lambda d: d["domain"]),
    }


def build_schema_entry(
    *,
    name: str,
    version: str,
    member: str,
    validates: str,
) -> dict[str, Any]:
    """One entry in the manifest's ``schemas`` list."""

    return {
        "name": name,
        "version": version,
        "member": member,
        "validates": validates,
    }


def standard_exclusions() -> tuple[dict[str, str], ...]:
    """What the archive deliberately does not carry, and why.

    Recorded in the manifest so a reviewer sees the gaps rather than having to notice
    their absence.
    """

    return (
        {
            "absent": "generated domain plugins",
            "reason": (
                "produced at run time by meta_skills/domain-plugin-builder; a shipped "
                "plugin would be stale the moment a domain is added"
            ),
        },
        {
            "absent": "adapter.json",
            "reason": (
                "the repository's OpenClaw skills carry an adapter binding; these "
                "skills are pure declarations and bind to nothing"
            ),
        },
        {
            "absent": "test_command",
            "reason": (
                "every existing skill manifest names one; a released declaration has "
                "nothing to run, so naming a test would be a broken instruction"
            ),
        },
        {
            "absent": "runtime, prompts, credentials",
            "reason": "a skill library is a configuration asset, never an execution environment",
        },
    )


def _one_line(value: Any) -> str:
    return " ".join(str(value).split())


__all__ = [
    "FORBIDDEN_MANIFEST_KEYS",
    "GENERATED_BY",
    "INTEGRITY_RULE",
    "LIBRARY_FORMAT_VERSION",
    "LIBRARY_ID",
    "MANIFEST_SCHEMA_VERSION",
    "REQUIRED_MANIFEST_KEYS",
    "build_domain_registry",
    "build_manifest",
    "build_readme",
    "build_schema_entry",
    "build_version_document",
    "standard_exclusions",
    "validate_manifest",
]
