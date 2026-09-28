"""Dataset provenance and manifest (Phase M4, phase 6).

The brief asks for 20–50 **real** creator posts with recorded provenance. M4 has
no network access and cannot legitimately obtain them, and fabricating material
and labelling it real would poison every downstream number in this phase.

So this module does two things instead:

1. It defines the manifest contract the real collection must satisfy —
   ``source_id``, ``creator_id``, ``collection_method``, ``permission_status`` —
   so the collection is a data-entry task rather than a design task.
2. It makes **origin a required, typed field**, so a synthetic corpus can never
   be quietly presented as a real one. :class:`ProvenanceRecord` refuses to exist
   without an origin, and :func:`assert_real_collection` fails loudly when a
   report tries to claim real-world provenance it does not have.

That last point is the module's real value. The risk in a phase like this is not
failing to collect data; it is forgetting that you did not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: Where a sample actually came from. Required on every record.
ORIGINS: tuple[str, ...] = ("real_creator_post", "synthetic_rendered", "manual_annotation")

#: How a sample was obtained.
COLLECTION_METHODS: tuple[str, ...] = (
    "creator_authorised_export",
    "public_post_manual_capture",
    "platform_api_with_permission",
    "synthetic_generation",
    "manual_annotation_by_author",
)

#: Publication status of the material.
PERMISSION_STATUSES: tuple[str, ...] = (
    "explicit_written_permission",
    "public_domain",
    "research_exemption_assumed",
    "permission_pending",
    "not_applicable_synthetic",
)

#: Statuses that permit analysis. Anything else blocks the sample.
PERMITTED_STATUSES: frozenset[str] = frozenset(
    {"explicit_written_permission", "public_domain", "not_applicable_synthetic"}
)

MANIFEST_VERSION = "m4.0.0"


class ProvenanceError(Exception):
    """Raised when provenance is missing, inconsistent, or overstated."""


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Where one sample came from, and whether it may be used."""

    source_id: str
    creator_id: str
    origin: str
    collection_method: str
    permission_status: str
    collected_at: str
    source_reference: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        for name in ("source_id", "creator_id"):
            if not getattr(self, name).strip():
                raise ProvenanceError(f"{name} must be non-empty")
        if self.origin not in ORIGINS:
            raise ProvenanceError(
                f"origin must be one of {list(ORIGINS)!r}, got {self.origin!r}; a "
                "sample with no declared origin cannot be reported honestly"
            )
        if self.collection_method not in COLLECTION_METHODS:
            raise ProvenanceError(
                f"unknown collection_method {self.collection_method!r}"
            )
        if self.permission_status not in PERMISSION_STATUSES:
            raise ProvenanceError(
                f"unknown permission_status {self.permission_status!r}"
            )
        if not self.collected_at.strip():
            raise ProvenanceError("collected_at must be non-empty")

        # Consistency: a synthetic sample cannot claim a real collection method,
        # and a real post cannot claim synthetic generation.
        if self.origin == "synthetic_rendered":
            if self.collection_method != "synthetic_generation":
                raise ProvenanceError(
                    "a synthetic_rendered sample must use collection_method="
                    "'synthetic_generation'"
                )
            if self.permission_status != "not_applicable_synthetic":
                raise ProvenanceError(
                    "a synthetic_rendered sample must use permission_status="
                    "'not_applicable_synthetic'"
                )
        if self.origin == "real_creator_post" and self.collection_method in {
            "synthetic_generation",
            "manual_annotation_by_author",
        }:
            raise ProvenanceError(
                f"a real_creator_post cannot be collected by {self.collection_method!r}"
            )

    @property
    def is_real(self) -> bool:
        return self.origin == "real_creator_post"

    @property
    def is_permitted(self) -> bool:
        return self.permission_status in PERMITTED_STATUSES

    def assert_usable(self) -> None:
        if not self.is_permitted:
            raise ProvenanceError(
                f"sample {self.source_id!r} has permission_status "
                f"{self.permission_status!r} and must not be analysed"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "creator_id": self.creator_id,
            "origin": self.origin,
            "collection_method": self.collection_method,
            "permission_status": self.permission_status,
            "collected_at": self.collected_at,
            "source_reference": self.source_reference,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    """A manifest of samples with their provenance."""

    dataset_id: str
    records: tuple[ProvenanceRecord, ...]
    version: str = MANIFEST_VERSION
    description: str = ""

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise ProvenanceError("dataset_id must be non-empty")
        if not self.records:
            raise ProvenanceError("a manifest must contain at least one record")
        ids = [record.source_id for record in self.records]
        duplicates = sorted({sid for sid in ids if ids.count(sid) > 1})
        if duplicates:
            raise ProvenanceError("duplicate source_ids: " + ", ".join(duplicates))

    def __len__(self) -> int:
        return len(self.records)

    def origins(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.origin] = counts.get(record.origin, 0) + 1
        return counts

    def creators(self) -> tuple[str, ...]:
        return tuple(sorted({record.creator_id for record in self.records}))

    def real_records(self) -> tuple[ProvenanceRecord, ...]:
        return tuple(record for record in self.records if record.is_real)

    def synthetic_records(self) -> tuple[ProvenanceRecord, ...]:
        return tuple(record for record in self.records if not record.is_real)

    @property
    def is_real_collection(self) -> bool:
        """True only when *every* record is a real creator post."""

        return all(record.is_real for record in self.records)

    def permitted_records(self) -> tuple[ProvenanceRecord, ...]:
        return tuple(record for record in self.records if record.is_permitted)

    def assert_real_collection(self, *, minimum: int = 20) -> None:
        """Assert this manifest can support a claim of real-world validation.

        Called by any report that wants to say "validated on real creator posts".
        Fails loudly rather than allowing a synthetic corpus to be described as
        real — which is the single most damaging thing this phase could do.
        """

        real = self.real_records()
        if len(real) < minimum:
            raise ProvenanceError(
                f"this manifest has {len(real)} real creator posts but {minimum} are "
                "required; real-world validation cannot be claimed"
            )
        for record in real:
            record.assert_usable()
        if len(self.creators()) < 2:
            raise ProvenanceError(
                "a real collection needs more than one creator to support any claim "
                "about creator strategy"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.version,
            "dataset_id": self.dataset_id,
            "description": self.description,
            "record_count": len(self.records),
            "creator_count": len(self.creators()),
            "origins": self.origins(),
            "is_real_collection": self.is_real_collection,
            "records": [record.as_dict() for record in self.records],
        }

    def render(self) -> str:
        return (
            f"dataset manifest {self.dataset_id}: {len(self.records)} records, "
            f"{len(self.creators())} creators, origins={self.origins()}, "
            f"real_collection={self.is_real_collection}"
        )


def synthetic_manifest(
    sample_ids: Iterable[str],
    *,
    creator_ids: Mapping[str, str] | None = None,
    dataset_id: str = "m4-synthetic-corpus",
    collected_at: str = "2026-01-01T00:00:00Z",
) -> DatasetManifest:
    """Build an honestly-labelled manifest for a generated corpus.

    Every record is marked ``synthetic_rendered``, which makes
    :meth:`DatasetManifest.assert_real_collection` fail by construction.
    """

    creators = dict(creator_ids or {})
    records = [
        ProvenanceRecord(
            source_id=sample_id,
            creator_id=creators.get(sample_id, "synthetic-creator"),
            origin="synthetic_rendered",
            collection_method="synthetic_generation",
            permission_status="not_applicable_synthetic",
            collected_at=collected_at,
            source_reference="multimodal_creator.observation.corpus",
            notes="generated structural corpus; not real creator material",
        )
        for sample_id in sorted(sample_ids)
    ]
    return DatasetManifest(
        dataset_id=dataset_id,
        records=tuple(records),
        description=(
            "Synthetic corpus rendered from template specifications. Reported as "
            "synthetic everywhere; supports no claim about real creator behaviour."
        ),
    )


def write_manifest(manifest: DatasetManifest, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def read_manifest(path: str | Path) -> DatasetManifest:
    """Read a manifest back, re-validating every record's provenance."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = tuple(
        ProvenanceRecord(
            source_id=str(item["source_id"]),
            creator_id=str(item["creator_id"]),
            origin=str(item["origin"]),
            collection_method=str(item["collection_method"]),
            permission_status=str(item["permission_status"]),
            collected_at=str(item["collected_at"]),
            source_reference=str(item.get("source_reference", "")),
            notes=str(item.get("notes", "")),
        )
        for item in payload["records"]
    )
    return DatasetManifest(
        dataset_id=str(payload["dataset_id"]),
        records=records,
        version=str(payload.get("manifest_version", MANIFEST_VERSION)),
        description=str(payload.get("description", "")),
    )


#: The collection protocol a real dataset must follow. Published so the work is
#: a checklist rather than a research question.
COLLECTION_PROTOCOL: tuple[Mapping[str, str], ...] = (
    {
        "step": "1. authorisation",
        "detail": "Obtain explicit written permission from each creator, or confirm "
        "the material is public domain. Record the status verbatim.",
    },
    {
        "step": "2. scope",
        "detail": "20-50 posts per creator cohort, minimum 2 creators, so that "
        "cross-creator agreement is possible at all.",
    },
    {
        "step": "3. capture",
        "detail": "Store the image and its source reference. Do not re-encode: "
        "compression changes the pixel statistics the observer reads.",
    },
    {
        "step": "4. provenance",
        "detail": "One manifest record per sample with source_id, creator_id, "
        "collection_method, permission_status, collected_at.",
    },
    {
        "step": "5. separation",
        "detail": "Keep the real set in its own directory. Never mix it with the "
        "synthetic corpus, so no run can average across the two.",
    },
    {
        "step": "6. validation",
        "detail": "Run DatasetManifest.assert_real_collection before any report "
        "claims real-world validation.",
    },
)


__all__ = [
    "COLLECTION_METHODS",
    "COLLECTION_PROTOCOL",
    "MANIFEST_VERSION",
    "ORIGINS",
    "PERMISSION_STATUSES",
    "PERMITTED_STATUSES",
    "DatasetManifest",
    "ProvenanceError",
    "ProvenanceRecord",
    "read_manifest",
    "synthetic_manifest",
    "write_manifest",
]
