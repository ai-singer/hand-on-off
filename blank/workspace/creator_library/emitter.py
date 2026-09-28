"""Emitting a skill declaration as a real skill directory.

A declaration in :mod:`creator_plugin_builder.library` is data: a name, a layer, a
purpose, what it produces. This module turns one into the three files a Shared Skill
Library ingests:

```text
    universal_skills/text-distillation/
    ├── SKILL.md          front matter + what the skill does, in prose
    ├── manifest.json     name, version, entrypoint, capabilities
    └── skill.json        the declaration itself, machine-readable
```

The conventions are the repository's own, deliberately. ``skills/quality_review/``
already ships a ``SKILL.md`` with ``name``/``version``/``description`` front matter
and a ``manifest.json`` with ``name``, ``version``, ``entrypoint``, ``capabilities``.
A library whose skills used a different shape would be a second, incompatible
convention, and a consumer would have to learn both.

## Two deliberate divergences

**No ``test_command``.** Every existing manifest carries one. These do not, because a
released skill is a pure declaration: there is nothing to run, and naming a Python
test that does not exist inside the archive would be a broken instruction rather than
a helpful one. The reason is recorded in the manifest itself rather than left as an
omission.

**``library_layer`` and ``library_version`` are added.** Which half of the library a
skill belongs to is the single most important fact about it — a universal skill must
be domain-free — so it travels with the skill instead of being inferred from the
directory it happens to sit in.

## What a released skill never carries

No prompt, no runtime, no entry point, no credential. The prose documents the
capability and the contract; it never instructs a model.
"""

from __future__ import annotations

from typing import Any, Mapping

from creator_package.hashing import BUILDER_VERSION, canonical_bytes

from .errors import LibrarySkillError
from .paths import skill_members

#: The skill manifest schema version these files are written at.
SKILL_MANIFEST_VERSION = "1.0.0"

#: The reason a released skill carries no ``test_command``.
NO_TEST_COMMAND_REASON = (
    "a released skill is a declaration: there is nothing to run"
)

#: Keys the emitted manifest carries.
MANIFEST_KEYS: tuple[str, ...] = (
    "name",
    "version",
    "library_layer",
    "library_version",
    "entrypoint",
    "capabilities",
    "produces",
    "note",
)

#: Keys a *skill* manifest must never carry.
#:
#: Distinct from :data:`creator_library.manifest.FORBIDDEN_MANIFEST_KEYS`, which
#: governs the release manifest. The two lists differ because the two documents do:
#: a skill manifest must not carry ``test_command`` — there is nothing to run — while
#: the release manifest *does* name ``test_command``, under ``exclusions``, to say
#: that it is absent. Sharing one name between them hid the release manifest's list
#: behind the skill manifest's, which is why they are named apart.
FORBIDDEN_SKILL_MANIFEST_KEYS: tuple[str, ...] = (
    "prompt",
    "prompts",
    "system_prompt",
    "prompt_template",
    "model",
    "model_id",
    "provider",
    "api_key",
    "credentials",
    "secret",
    "token",
    "endpoint",
    "webhook",
    "runtime",
    "entry_point",
    "executor",
    "handler",
    "callback",
    "code",
    "script",
    "deploy",
    "deployment",
    "test_command",
)


def skill_capabilities(name: str, declaration: Mapping[str, Any]) -> tuple[str, ...]:
    """The capabilities a skill declares.

    A skill's capability name is its own name — the library declares capabilities,
    not implementations, so the honest capability list is the skill itself plus what
    it produces. Inventing finer-grained capability names would be inventing
    capability.
    """

    produces = declaration.get("produces")
    capabilities = [name]
    if isinstance(produces, str) and produces.strip() and produces != name:
        capabilities.append(f"produces:{produces.strip()}")
    return tuple(capabilities)


def skill_manifest(
    name: str,
    declaration: Mapping[str, Any],
    *,
    layer: str,
    library_version: str,
) -> dict[str, Any]:
    """The ``manifest.json`` for one emitted skill."""

    if not isinstance(declaration, Mapping):
        raise LibrarySkillError(f"skill {name!r} has no declaration")
    purpose = str(declaration.get("purpose", "")).strip()
    produces = str(declaration.get("produces", "")).strip()
    if not purpose:
        raise LibrarySkillError(
            f"skill {name!r} declares no purpose",
            detail="a skill with no stated purpose cannot be reviewed",
        )

    manifest: dict[str, Any] = {
        "name": name,
        "version": library_version,
        "library_layer": layer,
        "library_version": library_version,
        "entrypoint": "SKILL.md",
        "capabilities": list(skill_capabilities(name, declaration)),
        "produces": produces,
        "note": NO_TEST_COMMAND_REASON,
    }
    return manifest


def skill_document(
    name: str,
    declaration: Mapping[str, Any],
    *,
    layer: str,
    library_version: str,
) -> dict[str, Any]:
    """The ``skill.json`` for one emitted skill: the declaration, plus its layer."""

    document = {
        "name": name,
        "library_layer": layer,
        "library_version": library_version,
        "skill_type": str(declaration.get("skill_type", "")),
        "purpose": str(declaration.get("purpose", "")),
        "produces": str(declaration.get("produces", "")),
        "accepts": str(declaration.get("accepts", "")),
        "capabilities": list(skill_capabilities(name, declaration)),
        "declaration_version": SKILL_MANIFEST_VERSION,
    }
    if not document["accepts"]:
        document.pop("accepts")
    return document


def skill_markdown(
    name: str,
    declaration: Mapping[str, Any],
    *,
    layer: str,
    library_version: str,
    companions: tuple[str, ...] = (),
) -> str:
    """The ``SKILL.md`` for one emitted skill.

    Follows the repository's existing skill-document shape — front matter, then
    prose — and documents the capability. It contains no instruction to a model:
    a skill is a declaration of what is possible, not a procedure for doing it.
    """

    purpose = _one_line(declaration.get("purpose", ""))
    produces = _one_line(declaration.get("produces", ""))
    skill_type = _one_line(declaration.get("skill_type", ""))
    accepts = _one_line(declaration.get("accepts", ""))

    lines: list[str] = ["---"]
    lines.append(f"name: {name}")
    lines.append(f"version: {library_version}")
    lines.append(f"library_layer: {layer}")
    lines.append(f"description: {purpose}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {name}")
    lines.append("")
    lines.append(purpose)
    lines.append("")

    lines.append("## Layer")
    lines.append("")
    if layer == "universal":
        lines.append(
            "**Universal Creator Skill.** This skill is the same for every domain, "
            "and it carries no domain knowledge. If a domain fact is needed here, it "
            "belongs in a domain plugin instead."
        )
    else:
        lines.append(
            "**Meta Skill.** This skill operates on domain plugin documents and on "
            "the library itself. A generated plugin is built and checked *by* the "
            "meta skills; it never runs them."
        )
    lines.append("")

    lines.append("## Capability")
    lines.append("")
    lines.append(f"- skill type: `{skill_type}`")
    lines.append(f"- produces: {produces}")
    if accepts:
        lines.append(f"- accepts: `{accepts}`")
    lines.append("")

    lines.append("## Declaration")
    lines.append("")
    lines.append(
        "This skill is a **declaration**, not an implementation. It states what is "
        "possible and what it consumes. It carries no prompt to send to a model, no "
        "executable body and no credential of any kind; its machine-readable form is "
        "`skill.json` beside this file."
    )
    lines.append("")

    if companions:
        lines.append("## Companions")
        lines.append("")
        lines.append(
            "The library's skills, as of this version. A skill is selected alongside "
            "these, never instead of them. The list is the whole library rather than "
            "whichever subset a given archive happens to carry, so one skill's "
            "document is the same document wherever it is packaged."
        )
        lines.append("")
        for companion in companions:
            if companion != name:
                lines.append(f"- `{companion}`")
        lines.append("")

    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- library version: `{library_version}`")
    lines.append(f"- layer: `{layer}`")
    lines.append("- manifest: `manifest.json`")
    lines.append("")

    return "\n".join(lines)


def emit_skill(
    name: str,
    declaration: Mapping[str, Any],
    *,
    layer: str,
    library_version: str,
    companions: tuple[str, ...] = (),
) -> dict[str, bytes]:
    """Emit one skill's three files, keyed by their archive path."""

    members = skill_members(layer, name)
    manifest = skill_manifest(
        name, declaration, layer=layer, library_version=library_version
    )
    document = skill_document(
        name, declaration, layer=layer, library_version=library_version
    )
    markdown = skill_markdown(
        name,
        declaration,
        layer=layer,
        library_version=library_version,
        companions=companions,
    )

    return {
        members["SKILL.md"]: markdown.encode("utf-8"),
        members["manifest.json"]: canonical_bytes(manifest),
        members["skill.json"]: canonical_bytes(document),
    }


def validate_emitted_manifest(manifest: Mapping[str, Any]) -> None:
    """Refuse an emitted manifest that carries a key it must never carry."""

    forbidden = sorted(set(manifest) & set(FORBIDDEN_SKILL_MANIFEST_KEYS))
    if forbidden:
        raise LibrarySkillError(
            "an emitted skill manifest carries forbidden keys: "
            + ", ".join(forbidden),
            detail="a released skill is a declaration, not an execution unit",
        )

    missing = sorted(set(MANIFEST_KEYS) - set(manifest))
    if missing:
        raise LibrarySkillError(
            "an emitted skill manifest is missing keys: " + ", ".join(missing)
        )


def _one_line(value: Any) -> str:
    """Collapse a value to one line, so front matter cannot be broken."""

    return " ".join(str(value).split())


__all__ = [
    "FORBIDDEN_SKILL_MANIFEST_KEYS",
    "MANIFEST_KEYS",
    "NO_TEST_COMMAND_REASON",
    "SKILL_MANIFEST_VERSION",
    "emit_skill",
    "skill_capabilities",
    "skill_document",
    "skill_manifest",
    "skill_markdown",
    "validate_emitted_manifest",
]
