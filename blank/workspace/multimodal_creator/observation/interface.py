"""Observer contract for real visual input (Phase M3).

The M2 pipeline accepted a declarative :class:`VisualSample` — a human assertion
of structure. M3 replaces that with a **real observer** that receives actual
image bytes and must recover structure from pixels.

The seam is unchanged, and that is the point: the observer still produces the M1
:class:`StructuralObservation`. Similarity, clustering, and artifact integration
are untouched and unaware that anything changed, which is what M1's
contract-first design was for.

Two types carry the new surface
-------------------------------

:class:`VisualSource`
    What is handed *in*: an asset reference and metadata. Never a description of
    the structure — if the caller had to describe the structure, the observer
    would not be observing anything.

:class:`ObservationResult`
    What comes *out*: the M1 observation plus the evidence provenance M1 did not
    have. Every result names the backend that produced it, the strength of each
    evidence family, and whether any backend failed.

The observer is deliberately **not** bound to a vision model. It depends only on
a :class:`VisionBackend`, so a mock backend, a manual-annotation backend, and a
real pixel backend are interchangeable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..taxonomy import STRUCTURAL_EVIDENCE, StructuralObservation, MultimodalContractError

#: Evidence families a complete observation must report. M3 requires all four
#: so a "visual" observation cannot quietly be a layout-only or OCR-only result.
EVIDENCE_FAMILIES: tuple[str, ...] = (
    "layout_evidence",
    "visual_evidence",
    "asset_evidence",
    "cross_modal_evidence",
)

#: How an observation's structure was obtained. Recorded on every result so a
#: downstream consumer can always tell real pixels from an assertion.
EVIDENCE_SOURCES: tuple[str, ...] = (
    "pixel_analysis",
    "manual_annotation",
    "mock_backend",
)


class ObserverError(MultimodalContractError):
    """Raised when a source cannot be observed or an observation is incomplete."""


@dataclass(frozen=True, slots=True)
class VisualSource:
    """A real visual input handed to an observer.

    ``asset_reference`` is a filesystem path, URL, or opaque handle. The observer
    resolves it; nothing about the *content* is pre-declared, because a declared
    structure would defeat the purpose of observing.
    """

    source_id: str
    source_type: str
    asset_reference: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ObserverError("source_id must be non-empty")
        if self.source_type not in {"image", "video_frame"}:
            raise ObserverError(
                f"source_type must be image or video_frame, got {self.source_type!r}"
            )
        if not str(self.asset_reference).strip():
            raise ObserverError("asset_reference must be non-empty")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "asset_reference": str(self.asset_reference),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Provenance for one evidence family.

    ``strength`` is a 0..1 self-assessment by the backend, not a calibrated
    probability. It exists so a weak observation can be identified and excluded
    rather than silently trusted.
    """

    family: str
    sources: tuple[str, ...]
    strength: float
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.family not in EVIDENCE_FAMILIES:
            raise ObserverError(f"unknown evidence family {self.family!r}")
        if not self.sources:
            raise ObserverError(f"evidence family {self.family!r} must name a source")
        for source in self.sources:
            if source not in EVIDENCE_SOURCES:
                raise ObserverError(
                    f"evidence family {self.family!r} names unknown source {source!r}"
                )
        # OCR is deliberately absent from EVIDENCE_SOURCES: transcription is not
        # an admissible provenance for visual structure.
        if not 0.0 <= self.strength <= 1.0:
            raise ObserverError(
                f"evidence strength must be within 0..1, got {self.strength!r}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "sources": list(self.sources),
            "strength": self.strength,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True, slots=True)
class ObservationResult:
    """An M1 observation plus the provenance M1 does not carry.

    ``observation`` is the unchanged M1 type, so everything downstream keeps
    working. The extra fields answer questions M1 could not: which backend
    produced this, how strong is the evidence, and did anything fail.
    """

    observation: StructuralObservation
    source: VisualSource
    backend_id: str
    evidence_source: str
    evidence: Mapping[str, EvidenceRecord]
    confidence: float
    warnings: tuple[str, ...] = ()
    backend_failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.evidence_source not in EVIDENCE_SOURCES:
            raise ObserverError(
                f"evidence_source must be one of {list(EVIDENCE_SOURCES)!r}, "
                f"got {self.evidence_source!r}"
            )
        if not self.backend_id.strip():
            raise ObserverError("backend_id must be non-empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ObserverError("confidence must be within 0..1")

    @property
    def observation_id(self) -> str:
        return self.observation.observation_id

    @property
    def source_id(self) -> str:
        return self.observation.source_id

    def evidence_families(self) -> tuple[str, ...]:
        return tuple(sorted(self.evidence))

    def is_complete(self) -> bool:
        """True when all four evidence families are present and non-empty."""

        return all(
            family in self.evidence and self.evidence[family].strength > 0.0
            for family in EVIDENCE_FAMILIES
        )

    def missing_families(self) -> tuple[str, ...]:
        return tuple(
            family
            for family in EVIDENCE_FAMILIES
            if family not in self.evidence or self.evidence[family].strength <= 0.0
        )

    def assert_complete(self) -> None:
        """Raise unless the observation is properly evidenced.

        Rules, in order of strictness:

        1. No observation may exist without an ``evidence_source``.
        2. No observation may rest on transcription alone.
        3. Every family must be *present*. A family a backend could not determine
           must still appear as a zero-strength record, so the gap is visible in
           the artifact rather than silently absent.
        4. ``layout_evidence``, ``visual_evidence``, and ``asset_evidence`` must
           be non-zero. These are what make an observation an observation.
        5. ``cross_modal_evidence`` is the one family allowed to be zero, because
           it describes a *relation* and some compositions genuinely do not
           exhibit one — a full-bleed image whose overlaid text is below the
           detection floor has no text/visual relation to report. Demanding a
           non-zero value there would force the observer to fabricate a relation,
           which is exactly the failure mode this contract exists to prevent.
           A zero-strength cross-modal family is only accepted when the other
           three families are intact, and it must be accompanied by a warning.
        """

        if not self.evidence_source:
            raise ObserverError(
                f"observation {self.observation_id!r} has no evidence_source"
            )
        missing = [
            family for family in EVIDENCE_FAMILIES if family not in self.evidence
        ]
        if missing:
            raise ObserverError(
                f"observation {self.observation_id!r} is missing evidence families: "
                + ", ".join(missing)
            )

        structural = [
            kind
            for kind in self.observation.evidence_kinds
            if kind in STRUCTURAL_EVIDENCE
        ]
        if not structural:
            raise ObserverError(
                f"observation {self.observation_id!r} carries no structural evidence; "
                "transcription alone cannot ground a visual observation"
            )

        required = ("layout_evidence", "visual_evidence", "asset_evidence")
        empty = [
            family for family in required if self.evidence[family].strength <= 0.0
        ]
        if empty:
            raise ObserverError(
                f"observation {self.observation_id!r} has zero-strength evidence for "
                "required families: " + ", ".join(empty)
            )

        cross = self.evidence["cross_modal_evidence"]
        if cross.strength <= 0.0 and not any(
            "cross_modal" in warning for warning in self.warnings
        ):
            raise ObserverError(
                f"observation {self.observation_id!r} reports no cross-modal evidence "
                "without recording a warning explaining why; an unexplained gap is "
                "indistinguishable from an omission"
            )

    def to_structural(self) -> StructuralObservation:
        """Return the bare M1 observation."""

        return self.observation

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "source": self.source.as_dict(),
            "backend_id": self.backend_id,
            "evidence_source": self.evidence_source,
            "confidence": self.confidence,
            "evidence": {name: record.as_dict() for name, record in self.evidence.items()},
            "warnings": list(self.warnings),
            "backend_failures": list(self.backend_failures),
            "observation": {
                "source_id": self.observation.source_id,
                "medium": self.observation.medium,
                "roles": list(self.observation.roles),
                "evidence_kinds": list(self.observation.evidence_kinds),
                "layout_template_class": self.observation.layout_template_class,
                "alignment": self.observation.alignment,
                "density": self.observation.density,
                "palette_relation": self.observation.palette_relation,
                "type_scale_relation": self.observation.type_scale_relation,
                "subject_class": self.observation.subject_class,
                "chart_class": self.observation.chart_class,
                "placement": self.observation.placement,
                "regions": [dict(region) for region in self.observation.regions],
            },
        }


# --------------------------------------------------------------------------
# Backend contract
# --------------------------------------------------------------------------


@runtime_checkable
class VisionBackend(Protocol):
    """Adapter interface for a source of structural vision facts.

    A backend answers four structural questions and nothing else. It never
    returns text content: the contract has no field for it, so an OCR-only
    backend cannot satisfy this interface even if someone wrote one.
    """

    @property
    def backend_id(self) -> str:
        """Stable identifier, recorded on every observation."""

    @property
    def evidence_source(self) -> str:
        """One of :data:`EVIDENCE_SOURCES`."""

    def detect_regions(self, source: VisualSource) -> Sequence[Mapping[str, Any]]:
        """Return region descriptors: ``region_id``, ``role``, ``box``, ``layer_order``."""

    def detect_visual_roles(self, source: VisualSource) -> Mapping[str, Any]:
        """Return palette relation, contrast role, and composition density."""

    def detect_style_features(self, source: VisualSource) -> Mapping[str, Any]:
        """Return type-scale relation, hierarchy depth, and alignment."""

    def detect_text_visual_alignment(
        self, source: VisualSource
    ) -> Sequence[Mapping[str, Any]]:
        """Return text/visual region relations derived from structure."""


__all__ = [
    "EVIDENCE_FAMILIES",
    "EVIDENCE_SOURCES",
    "EvidenceRecord",
    "ObservationResult",
    "ObserverError",
    "VisionBackend",
    "VisualSource",
]
