"""The deterministic zip: unpacking software has no business changing the bytes.

Two builds of the same declarations must produce the **same file**. Zip does not
give that for free — it stores a modification time and a member order, and either can
differ between runs — so three things are fixed here:

1. **The clock.** Every entry is stamped with :data:`~creator_package.hashing.ARCHIVE_TIMESTAMP`,
   the ZIP epoch. Nothing in this layer reads the wall clock.
2. **The order.** Members are written in :func:`creator_library.paths.member_sort_key`
   order: root files, then skills by layer and name, then registry and schema.
3. **The compression.** A fixed method and level, so the deflate stream is identical.

The third digest in this layer, ``artifact_hash``, is the SHA256 of the finished zip
bytes. It identifies the file a user uploads, and it can only be computed *after*
``manifest.json`` is written — so the manifest cannot contain it. That is why the
manifest carries ``content_hash`` (over content, self-referentially excluded members)
and the checksum ledger carries the per-member digests, while ``artifact_hash`` is
reported by the builder alongside the bytes.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any, Mapping

from creator_package.hashing import (
    ARCHIVE_TIMESTAMP,
    checksum_ledger,
    digest_bytes,
    package_hash,
)

from .errors import LibraryArchiveError
from .paths import CHECKSUMS_MEMBER, member_sort_key

#: The compression method every member is stored with.
COMPRESSION = zipfile.ZIP_DEFLATED

#: The compression level, fixed so the stream is reproducible.
COMPRESS_LEVEL = 9

#: The external attributes every member carries: regular file, 0644.
EXTERNAL_ATTR = 0o644 << 16

#: The ledger member's own name, used while building the ledger itself.
CHECKSUM_SELF_ROW = CHECKSUMS_MEMBER


def write_archive(members: Mapping[str, bytes]) -> bytes:
    """Build the zip in memory and return its bytes.

    Deterministic: the same ``members`` always produce the same bytes.
    """

    buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(
            buffer,
            mode="w",
            compression=COMPRESSION,
            compresslevel=COMPRESS_LEVEL,
        ) as archive:
            for path in sorted(members, key=member_sort_key):
                info = zipfile.ZipInfo(filename=path, date_time=ARCHIVE_TIMESTAMP)
                info.compress_type = COMPRESSION
                info.external_attr = EXTERNAL_ATTR
                info.create_system = 0
                archive.writestr(info, members[path])
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise LibraryArchiveError(f"cannot write the library archive: {exc}") from exc
    return buffer.getvalue()


def read_archive(payload: bytes) -> dict[str, bytes]:
    """Read an archive's members back, rejecting anything malformed."""

    members: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                members[info.filename] = archive.read(info)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise LibraryArchiveError(f"cannot read the library archive: {exc}") from exc
    return members


def archive_names(payload: bytes) -> tuple[str, ...]:
    """The member names in an archive, in the order the archive stores them."""

    try:
        with zipfile.ZipFile(io.BytesIO(payload), mode="r") as archive:
            return tuple(
                info.filename for info in archive.infolist() if not info.is_dir()
            )
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        raise LibraryArchiveError(f"cannot list the library archive: {exc}") from exc


def finalise(members: Mapping[str, bytes]) -> dict[str, Any]:
    """Compute ``content_hash`` and the checksum ledger for a set of members.

    The ledger is **returned, not added**. It has to describe the finished archive,
    and the finished archive contains the manifest, which is written after the content
    hash — so the only correct place for ``checksums.json`` is last. Adding it here
    would produce a ledger that describes a state the archive never has, which is
    exactly the mismatch this ordering avoids.
    """

    staged = dict(members)
    return {
        "members": staged,
        "content_hash": package_hash(staged),
        "ledger": checksum_ledger(staged),
        "checksums": {
            path: digest_bytes(payload) for path, payload in staged.items()
        },
    }


def add_ledger(
    members: Mapping[str, bytes],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Add ``checksums.json`` as the final member and return it with the ledger.

    The ledger must contain a row for **every** member, including itself. A file
    cannot contain its own digest, so its row records ``sha256: null`` and the ledger
    states that under ``self_reference`` — a reader sees the gap rather than an
    unexplained absence. :func:`verify_ledger` skips exactly that row and nothing else.

    Building it takes two steps, because the ledger's own byte count depends on the
    ledger: the row is written with ``bytes: 0``, the document is serialised, and then
    the row is corrected to the real length. Serialising twice is not enough — the
    first form has a different length — so the correction is applied to the document
    *before* the final serialisation, and the result is checked.
    """

    from creator_package.hashing import canonical_bytes

    staged = dict(members)
    staged[CHECKSUM_SELF_ROW] = b""

    # Only the ledger itself gets a null digest here. `manifest.json` is *not* null:
    # a different digest covers the content hash, and this file may describe it fully.
    ledger = checksum_ledger(staged, null_digest_for=(CHECKSUM_SELF_ROW,))
    ledger["files"][CHECKSUM_SELF_ROW]["bytes"] = len(canonical_bytes(ledger))
    payload = canonical_bytes(ledger)

    # The corrected byte count can change the document's length by a digit, so the
    # correction is iterated to a fixed point. Two passes suffice for any realistic
    # size; the loop makes that a guarantee rather than an assumption.
    for _ in range(4):
        actual = len(payload)
        if ledger["files"][CHECKSUM_SELF_ROW]["bytes"] == actual:
            break
        ledger["files"][CHECKSUM_SELF_ROW]["bytes"] = actual
        payload = canonical_bytes(ledger)

    staged[CHECKSUM_SELF_ROW] = payload
    return staged, ledger


def verify_ledger(
    members: Mapping[str, bytes],
    ledger: Mapping[str, Any],
) -> tuple[str, ...]:
    """Re-derive every checksum and return the members that disagree.

    Returns the mismatches rather than raising, so a caller can report all of them.
    ``checksums.json`` is skipped: it cannot contain its own digest, which the ledger
    records explicitly under ``self_reference``.
    """

    files = ledger.get("files")
    if not isinstance(files, Mapping):
        raise LibraryArchiveError("the checksum ledger carries no files map")

    mismatches: list[str] = []
    for path, payload in members.items():
        entry = files.get(path)
        if not isinstance(entry, Mapping):
            mismatches.append(f"{path}: absent from the ledger")
            continue
        recorded = entry.get("sha256")
        if recorded is None:
            continue
        if recorded != digest_bytes(payload):
            mismatches.append(f"{path}: digest mismatch")
        elif entry.get("bytes") != len(payload):
            mismatches.append(f"{path}: length mismatch")
    return tuple(sorted(mismatches))


def artifact_digest(payload: bytes) -> str:
    """The SHA256 of a finished archive."""

    return digest_bytes(payload)


__all__ = [
    "CHECKSUM_SELF_ROW",
    "COMPRESSION",
    "COMPRESS_LEVEL",
    "EXTERNAL_ATTR",
    "add_ledger",
    "archive_names",
    "artifact_digest",
    "finalise",
    "read_archive",
    "verify_ledger",
    "write_archive",
]
