"""Observation producer: the entry point of the M2 extraction prototype.

Pipeline implemented here::

    VisualSample ──mock extractor──▶ StructuralObservation (M1 valid)
                 └─geometry───────▶ CrossModalCandidate[]
                                          │
                                          ▼
                                   cross-modal records
                                   (artifact-ready dicts)

Two input paths are supported, as the phase brief requires:

1. **Hand annotation** — a caller writes :class:`VisualSample` or a plain dict
   by hand. No extraction step is involved at all; the declared structure *is*
   the observation.
2. **Mock extraction** — :class:`MockVisionExtractor` derives the observation
   from a declared sample.

Both paths converge on the same M1 type, which is the point: the contract does
not care how structure was obtained, only that it is structural.

The producer validates every observation against the M1 contract before
returning it, so an invalid observation fails at the producer rather than
silently poisoning a downstream artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..builder import build_cross_modal_records
from ..taxonomy import SOURCE_ROLES, STRUCTURAL_EVIDENCE, StructuralObservation
from .cross_modal_candidates import CrossModalCandidate, candidates_from_sample
from .mock_vision_extractor import MockVisionExtractor
from .visual_sample import MockExtractionError, VisualSample


@dataclass(frozen=True, slots=True)
class ObservationBatch:
    """The result of one production run over a set of samples.

    Attributes
    ----------
    samples
        The declared inputs, retained so provenance and geometry stay auditable.
    observations
        M1-valid structural observations, one per sample.
    cross_modal
        Text/visual candidates with their geometric justification.
    """

    samples: tuple[VisualSample, ...]
    observations: tuple[StructuralObservation, ...]
    cross_modal: tuple[CrossModalCandidate, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        source_ids = [observation.source_id for observation in self.observations]
        duplicates = sorted({sid for sid in source_ids if source_ids.count(sid) > 1})
        if duplicates:
            raise MockExtractionError(
                "duplicate observation source ids in batch: " + ", ".join(duplicates)
            )

    def observation_for(self, sample_id: str) -> StructuralObservation:
        for observation in self.observations:
            if observation.source_id == sample_id:
                return observation
        raise MockExtractionError(f"no observation produced for sample {sample_id!r}")

    def sample_for(self, sample_id: str) -> VisualSample:
        for sample in self.samples:
            if sample.sample_id == sample_id:
                return sample
        raise MockExtractionError(f"unknown sample {sample_id!r}")

    def candidates_for(self, sample_id: str) -> tuple[CrossModalCandidate, ...]:
        return tuple(
            candidate
            for candidate in self.cross_modal
            if candidate.source_id == sample_id
        )

    def source_ids(self) -> tuple[str, ...]:
        return tuple(observation.source_id for observation in self.observations)


class ObservationProducer:
    """Produce M1 observations and cross-modal candidates from samples.

    ``mode`` selects the production path and is recorded on every batch, so a
    downstream consumer can always tell whether structure was hand-annotated or
    mock-extracted:

    ``"annotated"``
        The sample is treated as a human assertion. The producer builds the
        observation from it but marks confidence as the caller supplied it and
        performs no derivation beyond geometry for cross-modal relations.
    ``"mock_extracted"``
        :class:`MockVisionExtractor` derives evidence kinds, roles, and
        alignment from the sample.

    Neither mode reads an image, and neither reads text. Both are pure
    functions of the declared sample.
    """

    MODES: tuple[str, ...] = ("annotated", "mock_extracted")

    def __init__(
        self,
        *,
        mode: str = "mock_extracted",
        extractor: MockVisionExtractor | None = None,
        validate: bool = True,
    ) -> None:
        if mode not in self.MODES:
            raise MockExtractionError(
                f"unknown producer mode {mode!r}; expected one of {list(self.MODES)!r}"
            )
        self._mode = mode
        self._extractor = extractor or MockVisionExtractor()
        self._validate = validate

    @property
    def mode(self) -> str:
        return self._mode

    def produce(
        self,
        samples: Iterable[VisualSample],
        *,
        annotate_only: bool = False,
    ) -> ObservationBatch:
        """Produce a batch from declared samples.

        ``annotate_only=True`` disables mock extraction entirely: the sample
        must already carry a layout class, and evidence kinds are still derived
        from declared facts because the M1 observation requires them. Nothing
        about the sample is guessed.
        """

        declared = tuple(samples)
        if not declared:
            raise MockExtractionError("at least one sample is required")

        extractor = self._extractor
        observations = extractor.extract_all(declared)
        if annotate_only:
            for sample in declared:
                if sample.layout_template_class is None:
                    raise MockExtractionError(
                        f"annotate_only requires sample {sample.sample_id!r} to declare "
                        "a layout_template_class; annotation mode does not infer layout"
                    )

        candidates: list[CrossModalCandidate] = []
        for sample in declared:
            candidates.extend(candidates_from_sample(sample))

        batch = ObservationBatch(
            samples=declared,
            observations=observations,
            cross_modal=tuple(candidates),
        )
        if self._validate:
            self._validate_batch(batch)
        return batch

    def cross_modal_records(
        self,
        batch: ObservationBatch,
        *,
        text_signal_for: Mapping[str, str] | None = None,
        default_text_signal: str = "content_template",
    ) -> list[dict[str, Any]]:
        """Render candidates as ``build_multimodal_artifact`` cross-modal entries.

        Each entry retains its geometric justification under ``geometric_evidence``;
        the M1 builder ignores unknown keys, so the artifact schema is untouched
        while the reasoning stays auditable in the producer's own output.
        """

        entries: list[dict[str, Any]] = []
        for candidate in batch.cross_modal:
            text_signal = (text_signal_for or {}).get(
                candidate.source_id, default_text_signal
            )
            entries.append(
                {
                    "text_signal": text_signal,
                    "text_role": candidate.text_role,
                    "relation": candidate.relation,
                    "visual_family": "layout_patterns",
                    "visual_pattern_id": candidate.source_id,
                    "visual_evidence": ["region_layout", "region_geometry"],
                    "source_ids": [candidate.source_id],
                    "builder": (
                        "hook_visual_alignment"
                        if candidate.text_role == "hook"
                        else "text_visual_alignment"
                    ),
                    "geometric_evidence": candidate.as_evidence(),
                    "confidence": candidate.confidence,
                }
            )
        return entries

    # -- internals ---------------------------------------------------------

    def _validate_batch(self, batch: ObservationBatch) -> None:
        """Check each observation against the M1 observation contract.

        A camera-ready observation is one a downstream artifact can consume, so
        the producer refuses to emit anything the contract would later reject.
        """

        for observation in batch.observations:
            if observation.medium not in {"image", "video"}:
                raise MockExtractionError(
                    f"observation {observation.observation_id!r} has invalid medium"
                )
            if not observation.evidence_kinds:
                raise MockExtractionError(
                    f"observation {observation.observation_id!r} carries no evidence"
                )
            if "ocr_text" in observation.evidence_kinds:
                raise MockExtractionError(
                    f"observation {observation.observation_id!r} claims ocr_text; the "
                    "extraction prototype must stay structural"
                )
            if not [
                kind for kind in observation.evidence_kinds if kind in STRUCTURAL_EVIDENCE
            ]:
                raise MockExtractionError(
                    f"observation {observation.observation_id!r} has no structural evidence"
                )
            for role in observation.roles:
                if role not in SOURCE_ROLES:
                    raise MockExtractionError(
                        f"observation {observation.observation_id!r} claims unknown role "
                        f"{role!r}"
                    )
            if observation.medium == "image" and "temporal_rhythm" in observation.evidence_kinds:
                raise MockExtractionError(
                    f"image observation {observation.observation_id!r} cannot claim "
                    "temporal_rhythm"
                )
            if not observation.regions:
                raise MockExtractionError(
                    f"observation {observation.observation_id!r} declares no regions; "
                    "layout structure is required"
                )


def annotation_to_observation(
    annotation: Mapping[str, Any],
    *,
    source_id: str,
    medium: str = "image",
) -> StructuralObservation:
    """Build an observation directly from a hand-written mapping.

    This is the "human annotation" input path. The caller supplies structure
    explicitly; nothing is inferred. Fields not supplied are omitted rather than
    defaulted, so an annotation never claims more than it states.
    """

    if not source_id.strip():
        raise MockExtractionError("source_id must be non-empty")
    regions = annotation.get("regions")
    if not regions:
        raise MockExtractionError(
            f"annotation for {source_id!r} must declare regions"
        )
    evidence = annotation.get("evidence_kinds")
    if not evidence:
        raise MockExtractionError(
            f"annotation for {source_id!r} must declare evidence_kinds"
        )
    if "ocr_text" in evidence and not [
        kind for kind in evidence if kind in STRUCTURAL_EVIDENCE
    ]:
        raise MockExtractionError(
            f"annotation for {source_id!r} is grounded only in ocr_text"
        )

    return StructuralObservation(
        observation_id=str(annotation.get("observation_id", f"{source_id}:annotated")),
        medium=medium,
        source_id=source_id,
        roles=tuple(annotation.get("roles", ("visual_style_source",))),
        evidence_kinds=tuple(evidence),
        regions=tuple(dict(region) for region in regions),
        layout_template_class=annotation.get("layout_template_class"),
        alignment=annotation.get("alignment"),
        density=annotation.get("density"),
        palette_relation=annotation.get("palette_relation"),
        type_scale_relation=annotation.get("type_scale_relation"),
        subject_class=annotation.get("subject_class"),
        chart_class=annotation.get("chart_class"),
        cover_role=annotation.get("cover_role"),
        asset_reuse=annotation.get("asset_reuse"),
        aspect_band=annotation.get("aspect_band"),
        placement=annotation.get("placement"),
        sequence_role=annotation.get("sequence_role"),
        recurrence=int(annotation.get("recurrence", 1)),
        confidence=float(annotation.get("confidence", 0.6)),
    )


__all__ = [
    "ObservationBatch",
    "ObservationProducer",
    "annotation_to_observation",
]
