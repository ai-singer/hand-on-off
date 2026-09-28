"""Hashing, and the deterministic archive clock.

.. note::

   **Not yet wired to a caller.** This module is parked work from the earlier
   Package Builder direction, kept because it is correct and because the Release
   Layer (C0.6) will need exactly this: canonical hashing over a deterministic
   archive, with the two digests a package manifest must carry. It is committed so
   the work is not lost, and it is deliberately not imported by
   :mod:`creator_plugin_builder` — generating domain plugins and packaging them for
   upload are different phases, and this phase is the former.

Two digests identify a package, and they answer different questions:

``instance_hash``
    What instance does this package carry? Computed over the canonical JSON of the
    seven modules plus the provenance block — the instance *content*, not its
    on-disk layout, so the same instance hashes identically whether it was read from
    an aggregate document or from per-module files.

``package_hash``
    What package is this? Computed over every archive member **except**
    ``manifest.json`` and ``checksums.json``, because both of those record the
    digest and cannot contain it. The rule is stated once, here, and
    :func:`verify_package_hash` re-derives it independently so a reader can check
    the claim rather than trust it.

Reproducibility rests on three fixed things: canonical JSON (sorted keys, fixed
separators, no trailing whitespace), the ZIP epoch as the archive clock, and sorted
member order. Nothing in this package reads the wall clock.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

from .errors import PackageArchiveError

#: Members excluded from ``package_hash``, because they carry it.
SELF_REFERENTIAL_MEMBERS: tuple[str, ...] = ("manifest.json", "checksums.json")

#: The timestamp every archive member carries: the ZIP epoch, 1980-01-01.
#:
#: ZIP cannot store a date before 1980, so this is the earliest expressible value
#: and the one that makes two builds byte-identical. The package's own
#: ``created_at`` records the same instant rather than the wall clock.
ARCHIVE_TIMESTAMP: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0)

#: The ISO-8601 form of :data:`ARCHIVE_TIMESTAMP`, for package metadata.
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"

#: The package format version.
PACKAGE_FORMAT_VERSION = "1.0.0"

#: The builder's own version, recorded in the manifest and in ``version.json``.
BUILDER_VERSION = "c0.5"


def canonical_json(document: Any) -> str:
    """Serialise a document the one way this package writes JSON.

    Sorted keys, two-space indent, ASCII-safe, and a trailing newline. Any change
    to this function changes every digest, which is why it has its own tests.
    """

    return (
        json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    )


def canonical_bytes(document: Any) -> bytes:
    """The bytes :func:`canonical_json` produces."""

    return canonical_json(document).encode("utf-8")


def digest_bytes(payload: bytes) -> str:
    """SHA256 of a byte string, as lowercase hex."""

    return hashlib.sha256(payload).hexdigest()


def digest_document(document: Any) -> str:
    """SHA256 of a document's canonical JSON."""

    return digest_bytes(canonical_bytes(document))


def instance_document_hash(document: Mapping[str, Any]) -> str:
    """The hash of an instance document's content.

    Only the contract's own keys are hashed: the seven modules, the provenance
    block and the contract version. A loader-private key is dropped, so an instance
    hashes the same whether it was read through the loader or straight from disk.
    """

    from .content import instance_document

    return digest_document(instance_document(document))


def package_hash(members: Mapping[str, bytes]) -> str:
    """The hash of a package's content, excluding the members that record it.

    Each member contributes ``<path>\\0<sha256 of its bytes>\\n``, in sorted path
    order. Hashing the *names* as well as the contents means a member cannot be
    renamed without changing the digest.

    The two self-referential members are matched by **basename**, not by full path.
    A package written at the archive root names them ``manifest.json``; a library
    written one directory down names them ``creator_skill_library/manifest.json``.
    Matching on the bare name would silently include the library's own manifest in
    its content hash, which is the bug this comment exists to prevent.
    """

    lines: list[str] = []
    for path in sorted(members):
        if _is_self_referential(path):
            continue
        lines.append(f"{path}\0{digest_bytes(members[path])}\n")
    return digest_bytes("".join(lines).encode("utf-8"))


def _is_self_referential(path: str) -> bool:
    """Whether a member is one of the files that record a digest."""

    return PurePosixPath(path).name in SELF_REFERENTIAL_MEMBERS


def verify_package_hash(
    members: Mapping[str, bytes],
    expected: str,
) -> bool:
    """Re-derive a package hash and compare it, never trusting the recorded value."""

    if not isinstance(expected, str) or not expected:
        raise PackageArchiveError("no package hash was supplied to verify")
    return package_hash(members) == expected


def checksum_ledger(
    members: Mapping[str, bytes],
    *,
    null_digest_for: Iterable[str] | None = None,
) -> dict[str, Any]:
    """The ``checksums.json`` document for a set of members.

    A file cannot contain its own digest, so some rows must record ``sha256: null``.
    Which rows those are is **passed in**, not guessed: the content hash excludes two
    members, but a ledger written last has only one member it cannot digest. Defaulting
    to the content-hash exclusion list would put a digest for ``checksums.json`` in the
    very document that digest describes, which can never be right.
    """

    nulls = set(SELF_REFERENTIAL_MEMBERS if null_digest_for is None else null_digest_for)
    rows: dict[str, Any] = {}
    for path in sorted(members):
        payload = members[path]
        rows[path] = {
            "sha256": None if path in nulls else digest_bytes(payload),
            "bytes": len(payload),
        }
    return {
        "algorithm": "sha256",
        "self_reference": sorted(nulls),
        "excluded_from_package_hash": list(SELF_REFERENTIAL_MEMBERS),
        "file_count": len(rows),
        "files": rows,
    }


def member_digests(members: Mapping[str, bytes]) -> dict[str, str]:
    """A plain ``{path: sha256}`` map, for tests and for diffing two packages."""

    return {path: digest_bytes(members[path]) for path in sorted(members)}


def combine_hashes(pairs: Iterable[tuple[str, str]]) -> str:
    """Hash a labelled list of digests into one.

    Used where several digests must be summarised into a single value — the request
    digest, for instance. Labels are included so two different label sets cannot
    collide.
    """

    lines = [f"{label}\0{value}\n" for label, value in sorted(pairs)]
    return digest_bytes("".join(lines).encode("utf-8"))


__all__ = [
    "ARCHIVE_TIMESTAMP",
    "BUILDER_VERSION",
    "DEFAULT_TIMESTAMP",
    "PACKAGE_FORMAT_VERSION",
    "SELF_REFERENTIAL_MEMBERS",
    "canonical_bytes",
    "canonical_json",
    "checksum_ledger",
    "combine_hashes",
    "digest_bytes",
    "digest_document",
    "instance_document_hash",
    "member_digests",
    "package_hash",
    "verify_package_hash",
]
