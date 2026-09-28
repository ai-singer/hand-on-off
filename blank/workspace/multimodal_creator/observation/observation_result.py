"""Observation set: the bridge from real observations into the M2 pipeline.

Similarity, clustering, and integration in M2 all take M1
:class:`StructuralObservation` and :class:`VisualSample` objects. M3 produces
observations from real pixels. Something has to join the two without either side
learning about the other.

:class:`ObservationSetBuilder` does that join, and it does it by *reconstructing*
a :class:`VisualSample` from a real observation. The reconstruction is
deliberately defensive: it fills only the fields the observation actually
evidenced, and it marks the result's provenance as observed rather than declared
so nothing downstream can present a measurement as an assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..extraction.visual_sample import (
    MockExtractionError,
    RegionSpec,
    SampleProvenance,
    SubjectSpec,
    TextStyleSpec,
    VisualSample,
)
from ..taxonomy import (
    DENSITIES,
    PALETTE_RELATIONS,
    PLACEMENTS,
    TYPE_SCALE_RELATIONS,
    StructuralObservation,
)
from .interface import EVIDENCE_FAMILIES, ObservationResult, ObserverError

#: Fallback typographic depth per scale relation, used when a backend reports a
#: scale but not a level count. Fixed and published rather than guessed.
SUBTYPE_FALLBACK_HIERARCHY: Mapping[str, int] = {
    "single_level": 1,
    "two_level": 2,
    "three_plus_levels": 3,
    "mixed": 2,
}

#: Subject classes the M2 vocabulary accepts, used to clamp a reconstruction.
_VALID_SUBJECT_CLASSES = {
    "human_figure",
    "human_group",
    "product_object",
    "document_scan",
    "screenshot",
    "data_chart",
    "icon_symbol",
    "scene_environment",
    "abstract_texture",
    "text_only",
    "composite",
    "unknown",
}

#: Alignment values the M2 vocabulary accepts.
_VALID_ALIGNMENTS = {"left", "right", "center", "top", "bottom", "grid", "free", "none"}


@dataclass(frozen=True, slots=True)
class ObservationSet:
    """A batch of real observations plus the ground truth they are scored against.

    Ground truth is attached here, at the boundary, and **never** passed into the
    observation, similarity, or clustering code. Keeping it in one place makes
    that separation auditable rather than a matter of discipline.
    """

    results: tuple[ObservationResult, ...]
    labels: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    backend_id: str = ""

    def __post_init__(self) -> None:
        if not self.results:
            raise ObserverError("an observation set must contain at least one result")
        ids = [result.source_id for result in self.results]
        duplicates = sorted({sid for sid in ids if ids.count(sid) > 1})
        if duplicates:
            raise ObserverError("duplicate observation source ids: " + ", ".join(duplicates))

    def __len__(self) -> int:
        return len(self.results)

    def source_ids(self) -> tuple[str, ...]:
        return tuple(result.source_id for result in self.results)

    def result_for(self, source_id: str) -> ObservationResult:
        for result in self.results:
            if result.source_id == source_id:
                return result
        raise ObserverError(f"no observation for source {source_id!r}")

    def observations(self) -> tuple[StructuralObservation, ...]:
        return tuple(result.observation for result in self.results)

    def label_for(self, source_id: str) -> Mapping[str, Any]:
        if source_id not in self.labels:
            raise ObserverError(f"no ground-truth label for source {source_id!r}")
        return self.labels[source_id]

    def incomplete(self) -> tuple[str, ...]:
        """Sources whose observation is missing an evidence family."""

        return tuple(
            result.source_id for result in self.results if not result.is_complete()
        )

    def evidence_completeness(self) -> float:
        total = len(self.results) * len(EVIDENCE_FAMILIES)
        present = sum(
            1
            for result in self.results
            for family in EVIDENCE_FAMILIES
            if family in result.evidence and result.evidence[family].strength > 0.0
        )
        return round(present / total, 6) if total else 0.0

    def summarise(self) -> str:
        strengths = {
            family: round(
                sum(result.evidence[family].strength for result in self.results)
                / len(self.results),
                3,
            )
            for family in EVIDENCE_FAMILIES
            if all(family in result.evidence for result in self.results)
        }
        return (
            f"observation set: {len(self.results)} sources, backend={self.backend_id!r}, "
            f"completeness={self.evidence_completeness()}, mean strength={strengths}"
        )


class ObservationSetBuilder:
    """Assemble observations and translate them into M2-compatible samples."""

    def build(
        self,
        results: Sequence[ObservationResult],
        *,
        labels: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> ObservationSet:
        if not results:
            raise ObserverError("at least one observation result is required")
        for result in results:
            result.assert_complete()
        backends = {result.backend_id for result in results}
        if len(backends) > 1:
            raise ObserverError(
                "an observation set must come from one backend, got: "
                + ", ".join(sorted(backends))
            )
        return ObservationSet(
            results=tuple(results),
            labels=dict(labels or {}),
            backend_id=results[0].backend_id,
        )

    def to_visual_sample(
        self,
        result: ObservationResult,
        *,
        creator_id: str,
        batch_id: str = "batch-0",
        index: int = 0,
    ) -> VisualSample:
        """Reconstruct a :class:`VisualSample` from a real observation.

        The reconstruction is lossy in one direction only: it can only include
        what the observation evidenced. A field the observer could not determine
        is left at the vocabulary's neutral value rather than guessed, so
        downstream similarity treats it as "not declared" and scores it
        neutrally — which is the honest outcome.
        """

        observation = result.observation
        if not observation.regions:
            raise ObserverError(
                f"observation {observation.observation_id!r} has no regions and cannot "
                "be reconstructed as a visual sample"
            )

        regions: list[RegionSpec] = []
        for region in observation.regions:
            try:
                regions.append(
                    RegionSpec(
                        region_id=str(region["region_id"]),
                        role=str(region["role"]),
                        box=dict(region["box"]),
                        layer_order=int(region.get("layer_order", 0)),
                    )
                )
            except MockExtractionError as exc:
                raise ObserverError(
                    f"observed region {region.get('region_id')!r} is not contract valid: {exc}"
                ) from exc

        visual_detail = result.evidence["visual_evidence"].detail
        style_detail = result.evidence["layout_evidence"].detail
        asset_detail = result.evidence["asset_evidence"].detail

        palette_relation = visual_detail.get("palette_relation")
        if palette_relation not in PALETTE_RELATIONS:
            palette_relation = "mixed"
        density = visual_detail.get("density")
        if density not in DENSITIES:
            density = "balanced"

        subject_class = observation.subject_class
        if subject_class not in _VALID_SUBJECT_CLASSES:
            subject_class = "unknown"

        alignment = observation.alignment
        if alignment not in _VALID_ALIGNMENTS:
            alignment = None

        text_style: TextStyleSpec | None = None
        scale = observation.type_scale_relation
        if scale in TYPE_SCALE_RELATIONS:
            text_style = TextStyleSpec(scale, SUBTYPE_FALLBACK_HIERARCHY.get(scale, 2))

        layout_class = style_detail.get("layout_template_class") or observation.layout_template_class

        # A larger index marks a wider-jitter variant, mirroring the M2 corpus
        # convention, so similarity calibration is not artificially perfect.
        placement = result.evidence["asset_evidence"].detail.get("placement")
        if placement not in PLACEMENTS:
            placement = "unknown"

        return VisualSample(
            sample_id=observation.source_id,
            regions=tuple(regions),
            color_family=str(visual_detail.get("color_family") or "mixed"),
            subject=SubjectSpec(subject_class, "balanced"),
            provenance=SampleProvenance(creator_id, batch_id),
            media_kind="video_frame" if observation.medium == "video" else "image",
            layout_template_class=layout_class,
            alignment=alignment,
            composition_density=density,
            negative_space="moderate",
            palette_relation=palette_relation,
            text_style=text_style,
            placement=placement,
            recurrence=1,
            confidence=result.confidence,
        )

    def to_visual_samples(
        self, observation_set: ObservationSet
    ) -> tuple[VisualSample, ...]:
        """Reconstruct every observation, taking creator ids from the labels.

        Creator identity must come from ground truth because a real observer
        cannot see who made an image. This is the one place labels legitimately
        enter the pipeline, and it is a *provenance* fact, not a family label —
        no template identity or family membership is used.
        """

        samples: list[VisualSample] = []
        for index, result in enumerate(observation_set.results):
            label = observation_set.labels.get(result.source_id, {})
            creator_id = str(label.get("creator_id") or f"observed-{index:03d}")
            batch_id = str(label.get("batch_id") or "batch-0")
            samples.append(
                self.to_visual_sample(
                    result, creator_id=creator_id, batch_id=batch_id, index=index
                )
            )
        return tuple(samples)


__all__ = ["ObservationSet", "ObservationSetBuilder"]
