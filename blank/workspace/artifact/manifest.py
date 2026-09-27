"""Artifact manifest generation for deployable Creator Agent instances.

A manifest gives a deployment artifact a verifiable identity: which runtime
contract it needs, which runtime configuration it ships, which plugins and
skills it enables, and the SHA-256 of every file it contains.

The manifest never lists itself, so a manifest can live inside the artifact it
describes without becoming self-referential.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from config.runtime import load_runtime_config
from runtime import SUPPORTED_CONFIG_VERSION

#: Conventional manifest filename, skipped by scanning and validation.
MANIFEST_NAME = "artifact-manifest.json"

#: Version of the manifest format itself.
MANIFEST_VERSION = "1.0.0"

#: Runtime configuration location inside an artifact.
CONFIG_RELATIVE = ("config", "runtime", "default.json")

IGNORED_DIRECTORY_NAMES = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache"})
IGNORED_FILE_SUFFIXES = (".pyc", ".pyo")

_HASH_CHUNK_BYTES = 1024 * 1024
_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class ArtifactManifestError(Exception):
    """Raised when a manifest cannot be generated for an artifact."""


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    path: str
    sha256: str
    size: int

    def as_dict(self) -> dict[str, Any]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


def major_version(value: str) -> int | None:
    """Return the major component of a semantic version, or None."""

    match = _SEMVER.fullmatch(value) if isinstance(value, str) else None
    return int(match.group(1)) if match else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_ignored(relative: Path) -> bool:
    """Interpreter and tooling caches are never part of an artifact."""

    if any(part in IGNORED_DIRECTORY_NAMES for part in relative.parts):
        return True
    return relative.suffix in IGNORED_FILE_SUFFIXES


def is_excluded(relative: Path, excluded: Sequence[str]) -> bool:
    """Match a POSIX relative path against directory prefixes such as 'tests'."""

    posix = relative.as_posix()
    for pattern in excluded:
        trimmed = pattern.strip("/")
        if not trimmed:
            continue
        if posix == trimmed or posix.startswith(trimmed + "/"):
            return True
    return False


def iter_artifact_files(
    artifact_dir: str | Path,
    *,
    exclude: Sequence[str] = (),
) -> list[Path]:
    """Return the manifest-eligible files of an artifact, stably sorted.

    Symlinks are skipped: a manifest describes regular file content, and a
    symlink target may not exist on the deployment host.
    """

    root = Path(artifact_dir)
    if not root.is_dir():
        raise ArtifactManifestError(f"artifact directory does not exist: {root}")

    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.name == MANIFEST_NAME:
            continue
        if is_ignored(relative) or is_excluded(relative, exclude):
            continue
        files.append(relative)
    return sorted(files, key=lambda item: item.as_posix())


def build_manifest(
    artifact_dir: str | Path,
    *,
    artifact_id: str | None = None,
    version: str | None = None,
    created_at: str | None = None,
    runtime_version: str | None = None,
    exclude: Sequence[str] = (),
    extra_exclude: Sequence[str] = (),
) -> dict[str, Any]:
    """Build the manifest payload for an artifact directory."""

    root = Path(artifact_dir)
    config_path = root.joinpath(*CONFIG_RELATIVE)
    try:
        config = load_runtime_config(config_path)
    except ValueError as exc:
        raise ArtifactManifestError(
            f"cannot read artifact runtime config {config_path}: {exc}"
        ) from exc

    entries: list[ManifestEntry] = []
    for relative in iter_artifact_files(root, exclude=(*exclude, *extra_exclude)):
        absolute = root / relative
        entries.append(
            ManifestEntry(
                path=relative.as_posix(),
                sha256=sha256_file(absolute),
                size=absolute.stat().st_size,
            )
        )
    if not entries:
        raise ArtifactManifestError(f"artifact contains no manifest-eligible files: {root}")

    return {
        "manifest_version": MANIFEST_VERSION,
        "artifact_id": artifact_id or config.instance.name,
        "version": version or config.version,
        "created_at": created_at or datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "runtime_version": runtime_version or SUPPORTED_CONFIG_VERSION,
        "config_version": config.version,
        "enabled_plugins": list(config.plugins.enabled),
        "enabled_skills": list(config.skills.enabled),
        "files": [entry.as_dict() for entry in entries],
    }


def generate_manifest(
    artifact_dir: str | Path,
    *,
    manifest_path: str | Path | None = None,
    **manifest_fields: Any,
) -> Path:
    """Write a manifest for ``artifact_dir`` and return its path.

    Defaults to ``<artifact_dir>/artifact-manifest.json``. A manifest stored
    inside the artifact is excluded from its own file list, including when a
    non-conventional ``manifest_path`` is used inside the artifact.
    """

    root = Path(artifact_dir)
    target = Path(manifest_path) if manifest_path is not None else root / MANIFEST_NAME

    extra_exclude: tuple[str, ...] = ()
    try:
        inside = target.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        inside = False
    if inside:
        extra_exclude = (target.resolve().relative_to(root.resolve()).as_posix(),)

    manifest = build_manifest(root, extra_exclude=extra_exclude, **manifest_fields)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a verifiable manifest for a deployable Creator Agent artifact."
        )
    )
    parser.add_argument("artifact_dir", help="Directory to describe")
    parser.add_argument("--manifest", dest="manifest_path", default=None)
    parser.add_argument("--artifact-id", dest="artifact_id", default=None)
    parser.add_argument("--version", dest="version", default=None)
    parser.add_argument("--created-at", dest="created_at", default=None)
    parser.add_argument("--runtime-version", dest="runtime_version", default=None)
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Relative directory prefix to omit; repeatable",
    )
    args = parser.parse_args(argv)

    try:
        target = generate_manifest(
            args.artifact_dir,
            manifest_path=args.manifest_path,
            artifact_id=args.artifact_id,
            version=args.version,
            created_at=args.created_at,
            runtime_version=args.runtime_version,
            exclude=tuple(args.exclude),
        )
    except ArtifactManifestError as exc:
        print(f"Artifact manifest FAIL: {exc}", file=sys.stderr)
        return 1

    manifest = json.loads(target.read_text(encoding="utf-8"))
    print(f"Artifact manifest: {target}")
    print(f"Files: {len(manifest['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
