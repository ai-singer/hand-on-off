"""Paths inside the released library archive.

Every path in the artefact is declared here, once, so the builder, the validator and
the tests cannot disagree about the layout:

```text
creator_skill_library/
├── LIBRARY.md                          what this library is
├── manifest.json                       the release manifest
├── checksums.json                      every member's digest
├── version.json                        format, library and builder versions
├── universal_skills/<skill>/          10 skills, domain-free
│   ├── SKILL.md
│   ├── manifest.json
│   └── skill.json
├── meta_skills/<skill>/               3 skills that build and check plugins
│   ├── SKILL.md
│   ├── manifest.json
│   └── skill.json
├── domain_plugins/
│   └── registry.json                   which domains this library can build
└── schemas/
    └── domain_plugin.schema.json       the plugin contract a consumer validates against
```

Two decisions worth stating.

**Skills are directories, not files.** ``universal_skills/text-distillation/`` with a
``SKILL.md`` inside it is the convention this repository already uses for every skill
in ``skills/``, and it is what a Shared Skill Library ingests. A flat
``text-distillation.md`` would be a second, incompatible convention.

**Generated domain plugins are not in the archive.** They are produced *at run time*
by ``meta_skills/domain-plugin-builder``, from a request, and they live with the
creator they configure. Shipping them here would make the library stale the moment a
domain is added — which is the whole failure mode this architecture exists to prevent.
What the archive carries is the builder, the schema and the **registry** that says
what it can build.
"""

from __future__ import annotations

from typing import Any

from .errors import LibraryPathError

#: The single top-level directory inside the archive.
LIBRARY_DIR = "creator_skill_library"

#: The archive filename.
ARCHIVE_FILENAME = f"{LIBRARY_DIR}.zip"

#: Root members.
README_MEMBER = f"{LIBRARY_DIR}/LIBRARY.md"
MANIFEST_MEMBER = f"{LIBRARY_DIR}/manifest.json"
CHECKSUMS_MEMBER = f"{LIBRARY_DIR}/checksums.json"
VERSION_MEMBER = f"{LIBRARY_DIR}/version.json"

#: Skill directories.
UNIVERSAL_SKILLS_DIR = f"{LIBRARY_DIR}/universal_skills"
META_SKILLS_DIR = f"{LIBRARY_DIR}/meta_skills"

#: Domain plugin registry and schema.
REGISTRY_MEMBER = f"{LIBRARY_DIR}/domain_plugins/registry.json"
SCHEMA_MEMBER = f"{LIBRARY_DIR}/schemas/domain_plugin.schema.json"

#: The three files inside one skill directory, in write order.
SKILL_FILES: tuple[str, ...] = ("SKILL.md", "manifest.json", "skill.json")

#: The shared-metadata member that accompanies a skill in a standalone package.
LIBRARY_FILE = "library.json"

#: Every file inside one *standalone* skill package, in write order.
STANDALONE_FILES: tuple[str, ...] = SKILL_FILES + (LIBRARY_FILE,)

#: The top-level directories a member may live under.
ALLOWED_TOP_LEVEL: tuple[str, ...] = (
    "universal_skills",
    "meta_skills",
    "domain_plugins",
    "schemas",
)

#: The five members that sit directly at the library root.
ROOT_MEMBERS: tuple[str, ...] = (
    "LIBRARY.md",
    "manifest.json",
    "checksums.json",
    "version.json",
)

#: Layers a skill may declare.
LAYERS: tuple[str, ...] = ("universal", "meta")

#: Layer → its directory.
LAYER_DIRS: dict[str, str] = {
    "universal": UNIVERSAL_SKILLS_DIR,
    "meta": META_SKILLS_DIR,
}

#: Directories that must never appear inside the archive.
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
    "venv",
    ".venv",
)

#: Filenames that must never appear inside the archive.
FORBIDDEN_FILENAMES: tuple[str, ...] = (
    ".env",
    ".env.local",
    ".env.production",
    ".netrc",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "credentials.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
    "requirements.txt",
    "setup.py",
    "pyproject.toml",
    "Makefile",
    "Dockerfile",
)

#: Suffixes that mean executable code.
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

#: The only suffixes a member of this archive may have.
ALLOWED_SUFFIXES: tuple[str, ...] = (".json", ".md")


def library_root() -> str:
    """The archive's root directory."""

    return LIBRARY_DIR


def skill_dir(layer: str, name: str) -> str:
    """The archive directory for one skill, rejecting an unknown layer or name."""

    if layer not in LAYERS:
        raise LibraryPathError(
            f"unknown library layer {layer!r}",
            detail="expected one of: " + ", ".join(LAYERS),
        )
    _assert_safe_name(name, what="skill name")
    return f"{LAYER_DIRS[layer]}/{name}"


def skill_members(layer: str, name: str) -> dict[str, str]:
    """``{filename: archive path}`` for one skill's three files."""

    base = skill_dir(layer, name)
    return {filename: f"{base}/{filename}" for filename in SKILL_FILES}


def skill_md_member(layer: str, name: str) -> str:
    return skill_members(layer, name)["SKILL.md"]


def skill_manifest_member(layer: str, name: str) -> str:
    return skill_members(layer, name)["manifest.json"]


def skill_document_member(layer: str, name: str) -> str:
    return skill_members(layer, name)["skill.json"]


def skill_directory_of(member: str) -> str:
    """The skill directory a member belongs to, or ``""`` if it is not one."""

    for layer in LAYERS:
        prefix = f"{LAYER_DIRS[layer]}/"
        if member.startswith(prefix):
            rest = member[len(prefix):]
            return f"{prefix}{rest.split('/', 1)[0]}"
    return ""


def layer_of(member: str) -> str:
    """Which layer a member belongs to, or ``""``."""

    for layer in LAYERS:
        if member.startswith(f"{LAYER_DIRS[layer]}/"):
            return layer
    return ""


def is_skill_member(member: str) -> bool:
    """Whether a member is one of a skill's three files."""

    directory = skill_directory_of(member)
    if not directory:
        return False
    filename = member[len(directory) + 1:]
    return filename in SKILL_FILES


def classify_member(member: str) -> str:
    """What kind of member this is, for structure checking.

    Returns one of ``root``, ``skill``, ``registry``, ``schema`` or ``unknown``.
    """

    if member in (README_MEMBER, MANIFEST_MEMBER, CHECKSUMS_MEMBER, VERSION_MEMBER):
        return "root"
    if member == REGISTRY_MEMBER:
        return "registry"
    if member == SCHEMA_MEMBER:
        return "schema"
    if is_skill_member(member):
        return "skill"
    return "unknown"


def expected_members(
    skills: dict[str, tuple[str, ...]],
) -> set[str]:
    """Every member a well-formed archive must contain.

    ``skills`` maps a layer to the skill names in it.
    """

    members = {README_MEMBER, MANIFEST_MEMBER, CHECKSUMS_MEMBER, VERSION_MEMBER,
               REGISTRY_MEMBER, SCHEMA_MEMBER}
    for layer, names in skills.items():
        for name in names:
            members.update(skill_members(layer, name).values())
    return members


def _assert_safe_name(name: str, *, what: str) -> None:
    """Reject a name that could escape its directory or collide with a sibling."""

    if not isinstance(name, str) or not name.strip():
        raise LibraryPathError(f"a {what} must be a non-empty string")
    if name != name.strip():
        raise LibraryPathError(f"a {what} must not have surrounding whitespace")
    forbidden = set('\\/:*?"<>|') | {"."}
    if forbidden & set(name) or name in {".", ".."}:
        raise LibraryPathError(f"{what} {name!r} is not usable as a directory name")


def member_sort_key(member: str) -> tuple[str, str]:
    """The deterministic order members are written in.

    Root files first, then skills by layer and name, then the registry and schema.
    Sorting the *names* is not enough: an archive whose entries are in a different
    order is a different file, and reproducibility depends on this being fixed.
    """

    kind = classify_member(member)
    rank = {"root": "0", "skill": "1", "registry": "2", "schema": "3"}.get(kind, "4")
    return (rank, member)


def summarise_members(members: dict[str, bytes]) -> dict[str, Any]:
    """A count of members by kind, for a manifest's own summary."""

    counts: dict[str, int] = {}
    for member in members:
        kind = classify_member(member)
        counts[kind] = counts.get(kind, 0) + 1
    return {
        "member_count": len(members),
        "by_kind": {key: counts[key] for key in sorted(counts)},
        "bytes": sum(len(payload) for payload in members.values()),
    }


# --------------------------------------------------------------------------
# Standalone skill packages
# --------------------------------------------------------------------------
#
# A Shared Skill Library ingests one skill at a time, so each skill also ships as
# its own small zip. The layout is deliberately flatter than the library's: a single
# top-level directory named for the skill.
#
#     <skill_name>/
#     ├── SKILL.md          front matter + prose
#     ├── manifest.json     name, version, library_layer, entrypoint, capabilities
#     ├── skill.json        the declaration, machine-readable
#     └── library.json      where it came from
#
# **No** ``creator_skill_library/`` wrapper, unlike the library archive. Repetition
# across thirteen packages is cheap; a reader handling one of them at a time would
# gain nothing from being told thirteen times which library it belongs to before
# reaching the skill itself. And the layout matches ``skills/<name>/`` in this
# repository, which is the convention a skill directory already has here.

#: The suffix a standalone package's filename carries.
PACKAGE_SUFFIX = ".zip"


def package_root(name: str) -> str:
    """The single top-level directory inside a standalone skill package."""

    _assert_safe_name(name, what="skill name")
    return name


def package_filename(name: str, *, prefix: str = "") -> str:
    """The filename of a standalone skill package.

    ``creator-`` by default, so the thirteen files sort together and are obviously
    one family when they land in an upload directory.
    """

    _assert_safe_name(name, what="skill name")
    return f"{prefix}{name}{PACKAGE_SUFFIX}"


def package_members(name: str) -> dict[str, str]:
    """``{filename: archive path}`` for one standalone skill package."""

    root = package_root(name)
    return {filename: f"{root}/{filename}" for filename in STANDALONE_FILES}


def package_classify(member: str) -> str:
    """What kind of member this is inside a standalone package."""

    parts = member.split("/")
    if len(parts) != 2:
        return "unknown"
    if parts[1] not in STANDALONE_FILES:
        return "unknown"
    if parts[1] == LIBRARY_FILE:
        return "library"
    return "skill"


def package_member_sort_key(member: str) -> tuple[str, str]:
    """The deterministic write order for a standalone package.

    ``SKILL.md`` first — it is the entrypoint a reader opens — then the two machine
    documents, then the shared metadata.
    """

    order = {
        "SKILL.md": "0",
        "manifest.json": "1",
        "skill.json": "2",
        LIBRARY_FILE: "3",
    }
    filename = member.rsplit("/", 1)[-1]
    return (order.get(filename, "9"), member)


__all__ = [
    "ALLOWED_SUFFIXES",
    "ALLOWED_TOP_LEVEL",
    "ARCHIVE_FILENAME",
    "CHECKSUMS_MEMBER",
    "FORBIDDEN_DIRECTORIES",
    "FORBIDDEN_FILENAMES",
    "FORBIDDEN_SUFFIXES",
    "LAYERS",
    "LAYER_DIRS",
    "LIBRARY_DIR",
    "LIBRARY_FILE",
    "MANIFEST_MEMBER",
    "META_SKILLS_DIR",
    "PACKAGE_SUFFIX",
    "README_MEMBER",
    "REGISTRY_MEMBER",
    "ROOT_MEMBERS",
    "SCHEMA_MEMBER",
    "SKILL_FILES",
    "STANDALONE_FILES",
    "UNIVERSAL_SKILLS_DIR",
    "VERSION_MEMBER",
    "classify_member",
    "expected_members",
    "is_skill_member",
    "layer_of",
    "library_root",
    "member_sort_key",
    "package_classify",
    "package_filename",
    "package_member_sort_key",
    "package_members",
    "package_root",
    "skill_dir",
    "skill_directory_of",
    "skill_document_member",
    "skill_manifest_member",
    "skill_md_member",
    "skill_members",
    "summarise_members",
]
