"""Shared fixtures for the Skill Library release-layer tests.

A full build validates every member, which is not cheap, so the result is cached per
library version for the life of the process.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from creator_library import LibraryBuild, build_library

WORKSPACE = Path(__file__).resolve().parents[2]
PACKAGE = WORKSPACE / "creator_library"

#: The release-layer modules.
PACKAGE_FILES: tuple[str, ...] = (
    "__init__.py",
    "archive.py",
    "builder.py",
    "emitter.py",
    "errors.py",
    "manifest.py",
    "paths.py",
    "skill_package.py",
    "skill_package_validation.py",
    "validation.py",
)
#: The library directory prefix inside the archive.
LIB = "creator_skill_library"

_TEMP_ROOT = Path(tempfile.mkdtemp(prefix="c06_library_tests_"))
atexit.register(shutil.rmtree, _TEMP_ROOT, True)

_CACHE: dict[str, LibraryBuild] = {}
_PACKAGE_CACHE: dict[str, tuple[Any, ...]] = {}


def packages(version: str = "1.0.0") -> tuple[Any, ...]:
    """The thirteen standalone skill packages, cached per version."""

    if version not in _PACKAGE_CACHE:
        from creator_library import build_skill_packages

        _PACKAGE_CACHE[version] = build_skill_packages(library_version=version)
    return _PACKAGE_CACHE[version]


def package(name: str, version: str = "1.0.0") -> Any:
    """One standalone skill package by skill name."""

    for candidate in packages(version):
        if candidate.name == name:
            return candidate
    raise KeyError(name)


def package_members(name: str, version: str = "1.0.0") -> dict[str, bytes]:
    """One archive's members keyed by their readable on-disk path.

    ``<name>/SKILL.md`` and so on — the *directory* form, which is how a person reads
    the skill. The archive itself is flat; use
    :attr:`creator_library.SkillPackage.members` for those names.
    """

    from creator_library import directory_members as dirs

    built = package(name, version)
    return {
        dirs(name)[filename]: built.members[filename]
        for filename in built.members
    }


def scratch_dir(name: str) -> Path:
    """A fresh, empty directory under the test temporary root."""

    target = _TEMP_ROOT / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    return target


def build(version: str = "1.0.0") -> LibraryBuild:
    """A built library, cached per version."""

    if version not in _CACHE:
        _CACHE[version] = build_library(library_version=version)
    return _CACHE[version]


def members(version: str = "1.0.0") -> dict[str, bytes]:
    """The built library's members."""

    return dict(build(version).members)


def member(path: str, version: str = "1.0.0") -> bytes:
    """One member's bytes."""

    return members(version)[path]


def text(path: str, version: str = "1.0.0") -> str:
    """One member's text."""

    return member(path, version).decode("utf-8")


def document(path: str, version: str = "1.0.0") -> Any:
    """One member, parsed as JSON."""

    return json.loads(text(path, version))


def skill_dir(layer: str, name: str) -> str:
    """The archive directory of one skill."""

    folder = "universal_skills" if layer == "universal" else "meta_skills"
    return f"{LIB}/{folder}/{name}"


def universal_names() -> tuple[str, ...]:
    """The universal skill names the library declares."""

    from creator_plugin_builder import UNIVERSAL_SKILLS

    return tuple(sorted(UNIVERSAL_SKILLS))


def meta_names() -> tuple[str, ...]:
    """The meta skill names the library declares."""

    from creator_plugin_builder import META_SKILLS

    return tuple(sorted(META_SKILLS))


def all_skill_names() -> tuple[str, ...]:
    return universal_names() + meta_names()


def digest_tree(root: Path) -> dict[str, str]:
    """SHA256 every file under ``root``, keyed by relative posix path."""

    digests: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digests[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return digests


def mutated(
    path: str,
    new_bytes: bytes,
    version: str = "1.0.0",
) -> dict[str, bytes]:
    """The library's members with one member replaced."""

    staged = members(version)
    staged[path] = new_bytes
    return staged
