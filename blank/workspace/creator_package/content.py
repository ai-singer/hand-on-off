"""The content of a package: what each member is, and what it contains.

A skill package is a **configuration asset, not an execution environment**. Every
member this module produces is a declarative document — the instance's own modules,
the skills' declarations, and provenance records. There is no code, no prompt, no
entry point, and nothing that could be run.

The layout:

```text
creator_<id>/
├── SKILL.md                     the package's own front matter and contents
├── manifest.json                the identity block (see :mod:`creator_package.manifest`)
├── version.json                 format, builder and skill versions
├── creator_instance/            the eight instance documents
│   ├── identity.json … publishing.json
│   └── provenance.json
├── skills/
│   ├── identity/<skill_id>/{SKILL.md,skill.json}
│   ├── domain/…
│   ├── source/…
│   ├── distillation/…
│   ├── visual/…                 (a `distillation` skill that emits visual_rules)
│   ├── risk/…                   (a `review` skill)
│   ├── generation/…
│   └── publishing/…
├── provenance/                  the per-skill chains, as one canonical document
└── checksums.json               every member's digest
```

Two naming decisions are worth stating because they are not obvious:

- The **type directories** name a *slot*, not a taxonomy id. ``risk/`` holds
  ``review`` skills and ``visual/`` holds ``distillation`` skills that emit
  ``visual_rules``, because "which skill covers this module" is the question a
  reader of a package is asking. ``SKILL_TYPE_SLOTS`` is the mapping and
  ``skill_slot`` resolves it deterministically.
- ``creator_instance/`` holds the instance **as eight documents**, never as the
  aggregate. The aggregate is a packaging convenience for readers on disk; inside a
  package the split form is the contract's own module layout, and it is what a
  consumer loads.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from creator_contract import CONTRACT_VERSION, MODULE_NAMES
from creator_mapping import MAPPED_MODULES

from .errors import PackageInputError, PackageStructureError

#: The seven configuration modules, in contract order.
CREATOR_MODULES: tuple[str, ...] = MAPPED_MODULES

#: The eight instance documents a package carries: seven modules plus provenance.
INSTANCE_DOCUMENTS: tuple[str, ...] = CREATOR_MODULES + ("provenance",)

#: Fields the instance hash covers, in the order it covers them.
INSTANCE_HASH_FIELDS: tuple[str, ...] = ("contract_version",) + INSTANCE_DOCUMENTS

#: Skill type → the directory slot it occupies inside ``skills/``.
SKILL_TYPE_SLOTS: Mapping[str, str] = {
    "identity": "identity",
    "domain": "domain",
    "source": "source",
    "distillation": "distillation",
    "generation": "generation",
    "review": "risk",
    "publishing": "publishing",
}

#: The directory slots, in composition order. ``visual`` is a refinement of
#: ``distillation``: a distillation skill that emits ``visual_rules`` is filed under
#: ``visual/`` so a reader can find the visual capability without reading every
#: skill document.
SKILL_SLOTS: tuple[str, ...] = (
    "identity",
    "domain",
    "source",
    "distillation",
    "visual",
    "risk",
    "generation",
    "publishing",
)

#: Files inside one skill directory.
SKILL_FILES: tuple[str, ...] = ("SKILL.md", "skill.json")

#: The module a slot's skill exists to produce. ``None`` for ``domain``, which
#: contributes to two modules and is filed by type rather than by module.
SLOT_PRIMARY_MODULE: Mapping[str, str] = {
    "identity": "identity",
    "source": "source",
    "distillation": "text_rules",
    "visual": "visual_rules",
    "risk": "risk_policy",
    "generation": "generation",
    "publishing": "publishing",
}

#: Files that are never acceptable inside a package, by exact name.
FORBIDDEN_FILENAMES: tuple[str, ...] = (
    ".env",
    ".env.local",
    ".env.production",
    ".netrc",
    "credentials",
    "credentials.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "id_rsa",
    "id_ed25519",
    "requirements.txt",
    "setup.py",
    "pyproject.toml",
    "Makefile",
    "Dockerfile",
)

#: Directory names that are never acceptable inside a package.
FORBIDDEN_DIRECTORIES: tuple[str, ...] = (
    "runtime",
    "production",
    "workflows",
    "risk_evaluation",
    "multimodal_creator",
    "distillation_core",
    "plugins",
    "__pycache__",
    ".git",
    ".github",
    "node_modules",
)

#: File suffixes that mean executable code, or something that runs.
FORBIDDEN_SUFFIXES: tuple[str, ...] = (
    ".py",
    ".pyc",
    ".pyo",
    ".pyd",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".cmd",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".rb",
    ".pl",
    ".jar",
    ".wasm",
)

#: The only suffixes a member of this package may have.
ALLOWED_SUFFIXES: tuple[str, ...] = (".json", ".md")


def package_dir_name(creator_id: str) -> str:
    """The single top-level directory inside the archive.

    Rejects anything that could escape the archive root or collide with a sibling,
    because the name becomes a path component.
    """

    if not isinstance(creator_id, str) or not creator_id.strip():
        raise PackageInputError("creator_id must be a non-empty string")
    if creator_id != creator_id.strip():
        raise PackageInputError("creator_id must not have surrounding whitespace")
    forbidden = set('\\/:*?"<>|') | {"."}
    if forbidden & set(creator_id) or creator_id in {".", ".."}:
        raise PackageInputError(
            f"creator_id {creator_id!r} is not usable as a directory name"
        )
    return f"creator_{creator_id}"


def instance_member_paths(package_dir: str) -> dict[str, str]:
    """``{document name: archive path}`` for the eight instance documents."""

    return {
        name: f"{package_dir}/creator_instance/{name}.json"
        for name in INSTANCE_DOCUMENTS
    }


def skill_dir(package_dir: str, slot: str, skill_id: str) -> str:
    """The archive directory for one skill, rejecting an unknown slot."""

    if slot not in SKILL_SLOTS:
        raise PackageStructureError(
            f"unknown skill slot {slot!r}",
            detail="expected one of: " + ", ".join(SKILL_SLOTS),
        )
    return f"{package_dir}/skills/{slot}/{skill_id}"


def skill_member_paths(package_dir: str, slot: str, skill_id: str) -> dict[str, str]:
    """``{filename: archive path}`` for one skill's two files."""

    base = skill_dir(package_dir, slot, skill_id)
    return {name: f"{base}/{name}" for name in SKILL_FILES}


def skill_slot(skill_type: str, outputs: Sequence[str] = ()) -> str:
    """Resolve which slot a skill belongs in.

    A ``distillation`` skill whose declared outputs include ``visual_rules`` is filed
    under ``visual/`` rather than ``distillation/``: it is the visual capability, and
    a reader looking for it should not have to open every distillation skill to find
    it. Every other type maps through :data:`SKILL_TYPE_SLOTS`.
    """

    if skill_type == "distillation" and "visual_rules" in tuple(outputs):
        return "visual"
    try:
        return SKILL_TYPE_SLOTS[skill_type]
    except KeyError as exc:
        raise PackageStructureError(
            f"skill type {skill_type!r} has no package slot",
            detail="expected one of: " + ", ".join(sorted(SKILL_TYPE_SLOTS)),
        ) from exc


def instance_document(instance: Mapping[str, Any]) -> dict[str, Any]:
    """The hashable, packable content of an instance.

    Only the contract's own keys: ``contract_version``, the seven modules and the
    provenance block. Anything else — a loader-private key, an unknown extra — is
    dropped rather than packed, so a package cannot smuggle a non-contract key into
    the instance it ships, and an instance hashes the same however it was read.
    """

    if not isinstance(instance, Mapping):
        raise PackageInputError("an instance must be a mapping")

    document: dict[str, Any] = {
        "contract_version": str(instance.get("contract_version", CONTRACT_VERSION))
    }
    for name in INSTANCE_DOCUMENTS:
        value = instance.get(name)
        if value is None:
            continue
        document[name] = _plain(value)
    return document


def _plain(value: Any) -> Any:
    """Convert a frozen structure back to plain JSON-compatible data."""

    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def skill_document(skill: Any) -> dict[str, Any]:
    """The ``skill.json`` content for one skill.

    Built from the skill object's own declaration, so nothing is added to it. The
    package records what the skill says, not what a package would like it to say.
    """

    try:
        document = skill.as_dict()
    except AttributeError as exc:
        raise PackageInputError(
            "a packageable skill must be a CreatorSkill"
        ) from exc
    if not isinstance(document, Mapping):
        raise PackageInputError("a skill's document must be a mapping")
    return _plain(document)


def skill_markdown(skill: Any) -> str:
    """The ``SKILL.md`` content for one skill.

    Follows this repository's existing skill-document convention — YAML front matter
    with ``name``, ``version`` and ``description``, then prose — because a package
    whose skills did not match the repository's own skill documents would be a
    second, incompatible convention.

    The body documents the declaration and nothing more. A skill is a capability
    statement, so its document says what the capability is and what it needs; it
    carries no instruction to a model and no procedure to execute.
    """

    document = skill_document(skill)
    lines: list[str] = ["---"]
    lines.append(f"name: {document['skill_id']}")
    lines.append(f"version: {document['version']}")
    lines.append(f"skill_type: {document['skill_type']}")
    lines.append(f"status: {document['status']}")
    lines.append(f"description: {_one_line(document['description'])}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {document['skill_id']}")
    lines.append("")
    lines.append(_one_line(document["description"]))
    lines.append("")
    lines.append("## Capabilities")
    lines.append("")
    for capability in document.get("capabilities", ()):
        lines.append(f"- `{capability}`")
    lines.append("")

    if document.get("inputs"):
        lines.append("## Inputs")
        lines.append("")
        for item in document["inputs"]:
            lines.append(f"- `{item}`")
        lines.append("")

    if document.get("outputs"):
        lines.append("## Outputs")
        lines.append("")
        for item in document["outputs"]:
            lines.append(f"- `{item}`")
        lines.append("")

    dependencies = document.get("dependencies") or ()
    lines.append("## Dependencies")
    lines.append("")
    if dependencies:
        for dependency in dependencies:
            reason = dependency.get("reason", "")
            suffix = f" — {_one_line(reason)}" if reason else ""
            lines.append(f"- `{dependency['kind']}` `{dependency['target']}`{suffix}")
    else:
        lines.append("None.")
    lines.append("")

    lines.append("## Provenance")
    lines.append("")
    provenance = document["provenance"]
    lines.append(f"- source kind: `{provenance['source_kind']}`")
    lines.append(f"- source asset: `{provenance['source_ref']}`")
    lines.append(f"- skill version: `{provenance['skill_version']}`")
    lines.append(f"- confidence: {provenance['confidence']}")
    if provenance.get("note"):
        lines.append(f"- note: {_one_line(provenance['note'])}")
    lines.append("")

    compatibility = document["compatibility"]
    lines.append("## Compatibility")
    lines.append("")
    for key in ("domains", "platforms", "styles"):
        values = compatibility.get(key) or ()
        rendered = ", ".join(f"`{value}`" for value in values) if values else "any"
        lines.append(f"- {key}: {rendered}")
    lines.append(
        f"- requires contract version: `{compatibility['requires_contract_version']}`"
    )
    lines.append("")

    if document["status"] != "available":
        lines.append("## Availability")
        lines.append("")
        lines.append(
            "This capability is **declared but not implemented** in this repository."
        )
        if document.get("reason"):
            lines.append("")
            lines.append(f"Reason: {_one_line(document['reason'])}")
        lines.append("")

    return "\n".join(lines)


def package_markdown(
    *,
    package_id: str,
    creator_id: str,
    version: str,
    skills: Sequence[Mapping[str, Any]],
    instance_hash: str,
    provenance_reference: str,
) -> str:
    """The package's own ``SKILL.md``: what this package is and what is inside it."""

    available = [s for s in skills if s.get("available") is True]
    declared = [s for s in skills if s.get("available") is not True]

    lines: list[str] = ["---"]
    lines.append(f"name: {package_id}")
    lines.append(f"version: {version}")
    lines.append(f"creator_id: {creator_id}")
    lines.append(f"description: Creator Skill Package for {creator_id}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {package_id}")
    lines.append("")
    lines.append(
        "A declared Creator configuration: the instance's own modules, the skills "
        "that produced them, and the provenance chain between the two."
    )
    lines.append("")
    lines.append(
        "This package is a **configuration asset**. It contains no runtime, no "
        "entry point, no prompt and no credential."
    )
    lines.append("")
    lines.append(f"- instance hash: `{instance_hash}`")
    lines.append(f"- provenance: `{provenance_reference}`")
    lines.append("")
    lines.append("## Skills")
    lines.append("")
    lines.append(f"### Available ({len(available)})")
    lines.append("")
    if available:
        for skill in available:
            lines.append(
                f"- `{skill['skill_id']}` ({skill['skill_type']}) "
                f"v{skill['version']} — {skill['path']}"
            )
    else:
        lines.append("None.")
    lines.append("")
    lines.append(f"### Declared but not implemented ({len(declared)})")
    lines.append("")
    if declared:
        for skill in declared:
            reason = skill.get("reason") or "no reason recorded"
            lines.append(
                f"- `{skill['skill_id']}` ({skill['skill_type']}) "
                f"v{skill['version']} — {_one_line(reason)}"
            )
    else:
        lines.append("None.")
    lines.append("")
    lines.append("## Instance")
    lines.append("")
    lines.append(
        "The eight instance documents are under `creator_instance/`. Each module "
        "records where it came from; the provenance block records which skill, asset "
        "and rule produced each field."
    )
    lines.append("")
    return "\n".join(lines)


def _one_line(text: Any) -> str:
    """Collapse a value to one line, so front matter cannot be broken by a newline."""

    return " ".join(str(text).split())


__all__ = [
    "ALLOWED_SUFFIXES",
    "CREATOR_MODULES",
    "FORBIDDEN_DIRECTORIES",
    "FORBIDDEN_FILENAMES",
    "FORBIDDEN_SUFFIXES",
    "INSTANCE_DOCUMENTS",
    "INSTANCE_HASH_FIELDS",
    "SKILL_FILES",
    "SKILL_SLOTS",
    "SKILL_TYPE_SLOTS",
    "SLOT_PRIMARY_MODULE",
    "instance_document",
    "instance_member_paths",
    "package_dir_name",
    "package_markdown",
    "skill_dir",
    "skill_document",
    "skill_markdown",
    "skill_member_paths",
    "skill_slot",
]
