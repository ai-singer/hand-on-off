"""Deterministic mock vision extractor: sample in, M1 observation out.

The name is deliberate. This is a **mock**: it performs no perception. It is a
pure function from a declared :class:`VisualSample` to an M1
:class:`StructuralObservation`, and it exists so the extraction and
representation pipeline can be verified without conflating that verification
with model accuracy.

Every evidence kind it reports is derived from a declared structural fact:

===========================  ==========================================
Declared fact                Structural evidence kind
===========================  ==========================================
region boxes                 ``region_layout``, ``region_geometry``
multiple layer orders        ``dominance_order``
``layout_template_class``    ``reading_order``
an image/chart subject       ``subject_salience``
``chart_class``              ``chart_encoding``
``palette_relation``         ``color_distribution``, ``palette_relation``
``text_style``               ``type_placement``, ``type_scale_relation``
``negative_space``           ``negative_space_ratio``
``alignment``                ``alignment_relation``
``media_kind == video_frame``  ``temporal_rhythm``
page sequence roles          ``page_rhythm``
===========================  ==========================================

``ocr_text`` is never emitted. The extractor has no text to read and no path by
which to read it, so the M1 anti-OCR boundary holds by construction rather than
by a check that could be forgotten.
"""

from __future__ import annotations

from typing import Sequence

from ..taxonomy import STRUCTURAL_EVIDENCE, StructuralObservation
from .visual_sample import MockExtractionError, VisualSample, region_to_dict

#: Palette relation to the contrast role the ground plays.
_CONTRAST_ROLE_BY_PALETTE: dict[str, str] = {
    "monochrome": "ground",
    "analogous": "neutral",
    "complementary": "figure",
    "triadic": "figure",
    "high_contrast_accent": "accent",
    "muted": "ground",
    "mixed": "neutral",
}

#: Colour families whose conventional signal role is a warning or alert ground.
_WARNING_COLOR_FAMILIES = frozenset({"warm_red", "warm_orange"})

#: Subjective classes that make the sample's subject the pictorial anchor.
_IMAGE_SUBJECT_CLASSES = frozenset(
    {
        "human_figure",
        "human_group",
        "product_object",
        "scene_environment",
        "abstract_texture",
        "composite",
    }
)


def contrast_role_for(color_family: str, palette_relation: str) -> str:
    """Resolve the declared colour structure to a contrast role.

    A warm-red or warm-orange ground with a high-contrast accent is the
    canonical warning composition, so it is reported as ``warning``. Otherwise
    the palette relation decides.
    """

    if (
        color_family in _WARNING_COLOR_FAMILIES
        and palette_relation == "high_contrast_accent"
    ):
        return "warning"
    return _CONTRAST_ROLE_BY_PALETTE.get(palette_relation, "neutral")


def derive_evidence_kinds(sample: VisualSample) -> tuple[str, ...]:
    """Derive structural evidence kinds from what the sample actually declares.

    Only kinds justified by a declared fact are returned, and every one is drawn
    from the M1 :data:`STRUCTURAL_EVIDENCE` vocabulary. A fact that is absent
    yields no kind, so the observation never overstates what was observed.
    """

    kinds: list[str] = []

    if sample.regions:
        kinds.append("region_layout")
        kinds.append("region_geometry")
    if sample.has_overlay_layers():
        kinds.append("dominance_order")
    if sample.layout_template_class is not None:
        kinds.append("reading_order")
    if sample.subject.subject_class in _IMAGE_SUBJECT_CLASSES or sample.visual_regions():
        kinds.append("subject_salience")
    if sample.chart_class is not None or any(
        region.role == "chart" for region in sample.regions
    ):
        kinds.append("chart_encoding")
    if sample.palette_relation != "mixed":
        kinds.append("color_distribution")
    kinds.append("palette_relation")
    if sample.text_style is not None:
        kinds.append("type_placement")
        kinds.append("type_scale_relation")
    if sample.negative_space != "moderate":
        kinds.append("negative_space_ratio")
    if sample.alignment is not None:
        kinds.append("alignment_relation")
    if sample.media_kind == "video_frame":
        kinds.append("temporal_rhythm")
    if sample.page_sequence_roles():
        kinds.append("page_rhythm")

    # Preserve first-seen order while removing duplicates, so the result is
    # deterministic and diffable.
    seen: dict[str, None] = {}
    for kind in kinds:
        seen.setdefault(kind, None)
    ordered = tuple(seen)

    unknown = [kind for kind in ordered if kind not in STRUCTURAL_EVIDENCE]
    if unknown:
        raise MockExtractionError(
            f"extractor derived non-structural evidence kinds: {unknown}"
        )
    if not ordered:
        raise MockExtractionError(
            f"sample {sample.sample_id!r} yielded no structural evidence; a sample "
            "must carry at least one structural fact"
        )
    return ordered


class MockVisionExtractor:
    """Translate declared samples into contract-valid structural observations.

    Stateless and pure: the same sample always produces the same observation, in
    the same field order, with no clock, randomness, or external call.
    """

    def __init__(self, *, origin: str = "common") -> None:
        if origin not in {"common", "framework"}:
            raise MockExtractionError(
                "extraction origin must be 'common' or 'framework'; the universal "
                "layer does not originate from a plugin"
            )
        self._origin = origin

    @property
    def origin(self) -> str:
        return self._origin

    def extract(self, sample: VisualSample) -> StructuralObservation:
        """Produce one observation covering every structural facet of the sample."""

        observation = StructuralObservation(
            observation_id=f"{sample.sample_id}:obs",
            medium="video" if sample.media_kind == "video_frame" else "image",
            source_id=sample.sample_id,
            roles=self._roles_for(sample),
            evidence_kinds=derive_evidence_kinds(sample),
            regions=tuple(region_to_dict(region) for region in sample.regions),
            layout_template_class=sample.layout_template_class,
            alignment=sample.alignment or self._derive_alignment(sample),
            density=sample.composition_density,
            palette_relation=sample.palette_relation,
            type_scale_relation=(
                sample.text_style.scale_relation if sample.text_style else None
            ),
            subject_class=sample.subject.subject_class,
            chart_class=sample.chart_class,
            cover_role=sample.cover_role,
            asset_reuse=sample.asset_reuse,
            aspect_band=sample.aspect_band,
            placement=sample.placement,
            sequence_role=sample.dominant_sequence_role(),
            recurrence=sample.recurrence,
            confidence=sample.confidence,
        )
        self._assert_structural_only(observation)
        return observation

    # -- internals ---------------------------------------------------------

    def _roles_for(self, sample: VisualSample) -> tuple[str, ...]:
        """The multi-role set this sample's structure justifies.

        Roles follow the *structure*, not the declared subject label: a sample
        carrying a ``chart`` region is a chart source whether or not it also
        declares a chart class, because the region role is the direct structural
        fact.
        """

        roles: list[str] = ["visual_style_source"]
        if sample.regions:
            roles.append("layout_source")

        region_roles = {region.role for region in sample.regions}
        if "subject" in region_roles or sample.subject.subject_class != "unknown":
            roles.append("subject_source")
        if "chart" in region_roles or sample.chart_class is not None:
            roles.append("chart_source")
        if sample.cover_role is not None:
            roles.append("cover_source")
        if sample.text_style is not None:
            roles.append("typography_source")
        if sample.palette_relation != "mixed":
            roles.append("color_source")
        if sample.media_kind == "video_frame" or sample.page_sequence_roles():
            roles.append("sequence_source")
        if sample.text_regions():
            roles.append("hook_source")
        return tuple(roles)

    def _derive_alignment(self, sample: VisualSample) -> str | None:
        """Derive alignment from the text block's horizontal position.

        Falls back to ``"grid"`` when the sample declares several text regions
        at different horizontal anchors, which is a grid rather than a single
        alignment.
        """

        text = sample.text_regions()
        if not text:
            return None
        lefts = [round(float(region.box["x"]), 2) for region in text]
        if len(set(lefts)) > 1:
            return "grid"
        left = lefts[0]
        width = float(text[0].box["w"])
        if width >= 0.8:
            return "center"
        if left <= 0.2:
            return "left"
        if left + width >= 0.8:
            return "right"
        return "center"

    def _assert_structural_only(self, observation: StructuralObservation) -> None:
        """Refuse to emit an observation grounded in transcription."""

        if "ocr_text" in observation.evidence_kinds:
            raise MockExtractionError(
                f"observation {observation.observation_id!r} claims ocr_text; the "
                "extraction prototype never reads text"
            )
        structural = [
            kind
            for kind in observation.evidence_kinds
            if kind in STRUCTURAL_EVIDENCE
        ]
        if not structural:
            raise MockExtractionError(
                f"observation {observation.observation_id!r} has no structural evidence"
            )

    def extract_all(
        self, samples: Sequence[VisualSample]
    ) -> tuple[StructuralObservation, ...]:
        """Extract over a batch, rejecting duplicate sample ids."""

        ids = [sample.sample_id for sample in samples]
        duplicates = sorted({sid for sid in ids if ids.count(sid) > 1})
        if duplicates:
            raise MockExtractionError(
                "duplicate sample ids in batch: " + ", ".join(duplicates)
            )
        return tuple(self.extract(sample) for sample in samples)


__all__ = [
    "MockVisionExtractor",
    "contrast_role_for",
    "derive_evidence_kinds",
]
