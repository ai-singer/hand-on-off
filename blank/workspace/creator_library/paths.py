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

#: The three files a skill carries.
#:
#: ``SKILL.md`` is what a shared skill library reads: it matches a skill by the
#: description in the front matter and then loads this file.
#:
#: **In an uploaded archive these sit at the archive root, with no wrapper
#: directory.** That is the whole point of :func:`archive_members` — zipping a skill
#: *directory* puts the files one level down, and a library looking for ``SKILL.md``
#: at the root would not find it.
#:
#: ``manifest.json`` is the convention every skill in this repository follows and
#: carries the capability list. ``skill.json`` is the declaration, machine-readable.
SKILL_FILES: tuple[str, ...] = ("SKILL.md", "manifest.json", "skill.json")

#: Every file a skill carries.
STANDALONE_FILES: tuple[str, ...] = SKILL_FILES

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
# One skill, one archive
# --------------------------------------------------------------------------
#
# A shared skill library ingests one skill at a time. It matches a skill by the
# description in ``SKILL.md``'s front matter and then loads that file — **from the
# archive root**.
#
#     creator-text-distillation.zip
#     ├── SKILL.md          ← at the root, where the library looks
#     ├── manifest.json
#     └── skill.json
#
# **Flat. No wrapper directory.** This is the whole subtlety, and getting it wrong is
# silent: zipping a skill *directory* produces ``text-distillation/SKILL.md``, which
# is one level deeper than the library looks. The archive looks correct in a file
# listing and still fails to load, because the library finds no entrypoint at the
# root. So members are written by :func:`archive_members` at the top level, and
# :func:`creator_library.skill_package_validation.validate_package_structure`
# refuses any archive that has a directory in it at all.
#
# The on-disk form is still a directory — ``skills/<name>/`` — because that is the
# convention this repository already uses and it is what a person reads. The
# directory is the readable form; the flat archive is the uploadable form. Both are
# built from the same three files.

#: The suffix an uploaded archive's filename carries.
PACKAGE_SUFFIX = ".zip"


def package_root(name: str) -> str:
    """The skill's own directory name, for the readable on-disk form."""

    _assert_safe_name(name, what="skill name")
    return name


def package_filename(name: str, *, prefix: str = "") -> str:
    """The filename of one skill's archive.

    ``creator-`` by default, so the thirteen files sort together and are obviously
    one family when they land in an upload directory.
    """

    _assert_safe_name(name, what="skill name")
    return f"{prefix}{name}{PACKAGE_SUFFIX}"


def archive_members(_name: str = "") -> dict[str, str]:
    """``{filename: archive path}`` for one skill's archive — **flat**.

    Every file sits at the archive root. The ``_name`` argument is accepted and
    ignored so a caller cannot make the unwrapper mistake of prefixing a directory:
    there is deliberately no way to express a nested layout here.
    """

    return {filename: filename for filename in STANDALONE_FILES}


def directory_members(name: str) -> dict[str, str]:
    """``{filename: path}`` for the readable on-disk form: ``<name>/<file>``."""

    root = package_root(name)
    return {filename: f"{root}/{filename}" for filename in STANDALONE_FILES}


def package_members(name: str) -> dict[str, str]:
    """Alias for :func:`directory_members`, the on-disk layout."""

    return directory_members(name)


def archive_classify(member: str) -> str:
    """What kind of member this is inside a skill archive.

    Anything with a directory component is ``nested`` — not merely unexpected, but
    the specific defect that makes a skill unloadable.
    """

    if "/" in member:
        return "nested"
    if member not in STANDALONE_FILES:
        return "unknown"
    return "skill"


def package_classify(member: str) -> str:
    """What kind of member this is inside the on-disk skill directory."""

    parts = member.split("/")
    if len(parts) != 2:
        return "unknown"
    if parts[1] not in STANDALONE_FILES:
        return "unknown"
    return "skill"


def package_member_sort_key(member: str) -> tuple[str, str]:
    """The deterministic write order: ``SKILL.md`` first, then the manifest, then
    the declaration.
    """

    filename = member.rsplit("/", 1)[-1]
    order = {"SKILL.md": "0", "manifest.json": "1", "skill.json": "2"}
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
    "archive_classify",
    "archive_members",
    "directory_members",
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
