"""Declarative description of a controlled multimodal sample.

A :class:`VisualSample` states what a sample *contains* in structural terms:
which regions exist, where they sit, how they layer, what the colour family is,
how the subject relates to the text, and who the sample came from.

Nothing here reads an image. A sample is an assertion by a caller — a human
annotator or a fixture — and the mock extractor's whole job is to translate
that assertion into contract-valid structure without adding or inventing
anything.

Phase M1 open question #1 ("who produces observations?") is answered here for
the prototype: a declared sample is the input, and the producer is a pure
function over it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..taxonomy import (
    ASPECT_BANDS,
    CHART_CLASSES,
    COVER_ROLES,
    DENSITIES,
    LAYOUT_TEMPLATE_CLASSES,
    PALETTE_RELATIONS,
    PLACEMENTS,
    REGION_ROLES,
    SEQUENCE_ROLES,
    SUBJECT_CLASSES,
    TYPE_SCALE_RELATIONS,
    MultimodalContractError,
)


class MockExtractionError(MultimodalContractError):
    """Raised when a sample cannot be translated into contract-valid structure."""


# --------------------------------------------------------------------------
# Structural vocabularies owned by the extraction prototype.
#
# These are extensions of the M1 contract surface, not replacements. Each is
# deliberately a *closed, coarse* vocabulary so that similarity stays
# explainable: comparing two families from a closed set is auditable, whereas
# comparing free strings or colour histograms is not.
# --------------------------------------------------------------------------

#: Coarse colour family of a sample's ground or dominant fill.
COLOR_FAMILIES: tuple[str, ...] = (
    "warm_red",
    "warm_orange",
    "warm_yellow",
    "cool_blue",
    "cool_teal",
    "cool_green",
    "neutral_grey",
    "neutral_beige",
    "dark_monochrome",
    "light_monochrome",
    "high_saturation_multi",
    "mixed",
)

#: How strongly the subject competes with the text for attention.
SUBJECT_SALIENCE: tuple[str, ...] = (
    "subject_dominant",
    "balanced",
    "text_dominant",
    "none",
)

#: Density of negative space.
NEGATIVE_SPACE: tuple[str, ...] = ("tight", "moderate", "generous")


@dataclass(frozen=True, slots=True)
class RegionSpec:
    """One declared region: identity, role, normalized box, and layer order.

    Boxes are validated against the M1 geometry contract, so a sample that is
    out of frame or uses an unknown role fails here rather than silently
    producing an invalid observation downstream.
    """

    region_id: str
    role: str
    box: Mapping[str, float]
    layer_order: int = 0

    def __post_init__(self) -> None:
        if not self.region_id.strip():
            raise MockExtractionError("region_id must be non-empty")
        if self.role not in REGION_ROLES:
            raise MockExtractionError(
                f"region {self.region_id!r} uses role {self.role!r}; the region "
                "vocabulary is universal and closed"
            )
        if isinstance(self.layer_order, bool) or not isinstance(self.layer_order, int):
            raise MockExtractionError(
                f"region {self.region_id!r} layer_order must be an integer"
            )
        missing = {"x", "y", "w", "h"} - set(self.box)
        if missing:
            raise MockExtractionError(
                f"region {self.region_id!r} box is missing {sorted(missing)}"
            )
        for key in ("x", "y", "w", "h"):
            value = self.box[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise MockExtractionError(
                    f"region {self.region_id!r} box.{key} must be numeric"
                )
            if value < 0.0 or value > 1.0:
                raise MockExtractionError(
                    f"region {self.region_id!r} box.{key} must be normalized to 0..1"
                )
        if self.box["w"] <= 0.0 or self.box["h"] <= 0.0:
            raise MockExtractionError(
                f"region {self.region_id!r} must have positive extent"
            )
        if self.box["x"] + self.box["w"] > 1.0 or self.box["y"] + self.box["h"] > 1.0:
            raise MockExtractionError(
                f"region {self.region_id!r} extends outside the normalized frame"
            )

    @property
    def is_text_region(self) -> bool:
        """True for regions whose *structure* carries text.

        Only the role and geometry are ever consulted. No text is read, and no
        text content exists anywhere in this module — which is what keeps the
        extraction prototype structurally grounded rather than OCR-driven.
        """

        return self.role in {
            "title",
            "subtitle",
            "body",
            "caption",
            "label",
            "annotation",
            "header",
            "footer",
        }

    @property
    def is_visual_region(self) -> bool:
        """True for regions carrying pictorial or encoded-visual content."""

        return self.role in {"subject", "chart", "data_table", "background", "logo"}


def region_to_dict(spec: RegionSpec) -> dict[str, Any]:
    """Render a region spec as the M1 region descriptor."""

    return {
        "region_id": spec.region_id,
        "role": spec.role,
        "box": {
            "x": float(spec.box["x"]),
            "y": float(spec.box["y"]),
            "w": float(spec.box["w"]),
            "h": float(spec.box["h"]),
        },
        "layer_order": int(spec.layer_order),
    }


@dataclass(frozen=True, slots=True)
class SubjectSpec:
    """What the sample's subject is, and how prominent it is."""

    subject_class: str
    salience: str = "balanced"

    def __post_init__(self) -> None:
        if self.subject_class not in SUBJECT_CLASSES:
            raise MockExtractionError(
                f"unknown subject_class {self.subject_class!r}; expected one of "
                f"{list(SUBJECT_CLASSES)!r}"
            )
        if self.salience not in SUBJECT_SALIENCE:
            raise MockExtractionError(
                f"unknown salience {self.salience!r}; expected one of "
                f"{list(SUBJECT_SALIENCE)!r}"
            )


@dataclass(frozen=True, slots=True)
class TextStyleSpec:
    """Declared typographic structure: scale relation and hierarchy depth."""

    scale_relation: str
    hierarchy_levels: int

    def __post_init__(self) -> None:
        if self.scale_relation not in TYPE_SCALE_RELATIONS:
            raise MockExtractionError(
                f"unknown type scale relation {self.scale_relation!r}"
            )
        if isinstance(self.hierarchy_levels, bool) or not isinstance(
            self.hierarchy_levels, int
        ):
            raise MockExtractionError("hierarchy_levels must be an integer")
        if self.hierarchy_levels < 1:
            raise MockExtractionError("hierarchy_levels must be at least 1")


@dataclass(frozen=True, slots=True)
class SampleProvenance:
    """Where a sample came from.

    Provenance exists to make one M1 open question answerable: are two similar
    templates *independently* similar, or is one creator simply repeating
    themselves? The clustering contract can require cross-provenance agreement
    before calling something a discovered family.
    """

    creator_id: str
    batch_id: str = "batch-0"

    def __post_init__(self) -> None:
        if not self.creator_id.strip():
            raise MockExtractionError("creator_id must be non-empty")
        if not self.batch_id.strip():
            raise MockExtractionError("batch_id must be non-empty")


@dataclass(frozen=True, slots=True)
class VisualSample:
    """A controlled structural description of one image, frame, or page.

    Required structural content:
      * ``regions`` — boxes and layer order (layout)
      * ``color_family`` — the colour system (visual)
      * ``subject`` — the subject role (asset)

    Cross-modal relation is derived from region geometry plus optional
    ``text_region_ids``, never from reading text.
    """

    sample_id: str
    regions: Sequence[RegionSpec]
    color_family: str
    subject: SubjectSpec
    provenance: SampleProvenance
    media_kind: str = "image"
    layout_template_class: str | None = None
    composition_density: str = "balanced"
    negative_space: str = "moderate"
    palette_relation: str = "mixed"
    contrast_role: str = "neutral"
    text_style: TextStyleSpec | None = None
    chart_class: str | None = None
    cover_role: str | None = None
    aspect_band: str = "unknown"
    placement: str = "unknown"
    asset_reuse: str = "unknown"
    text_region_ids: Sequence[str] = ()
    alignment: str | None = None
    reading_order: Sequence[str] = ()
    cross_modal_relations: Mapping[str, str] = field(default_factory=dict)
    media_role: str | None = None
    recurrence: int = 1
    confidence: float = 0.6

    def __post_init__(self) -> None:
        if not self.sample_id.strip():
            raise MockExtractionError("sample_id must be non-empty")
        if self.media_kind not in {"image", "video_frame"}:
            raise MockExtractionError(
                f"media_kind must be image or video_frame, got {self.media_kind!r}"
            )
        if not self.regions:
            raise MockExtractionError(
                f"sample {self.sample_id!r} must declare at least one region"
            )
        if self.color_family not in COLOR_FAMILIES:
            raise MockExtractionError(
                f"sample {self.sample_id!r} uses unknown color_family "
                f"{self.color_family!r}"
            )
        if self.composition_density not in DENSITIES:
            raise MockExtractionError(
                f"sample {self.sample_id!r} uses unknown composition_density "
                f"{self.composition_density!r}"
            )
        if self.negative_space not in NEGATIVE_SPACE:
            raise MockExtractionError(
                f"sample {self.sample_id!r} uses unknown negative_space "
                f"{self.negative_space!r}"
            )
        if self.palette_relation not in PALETTE_RELATIONS:
            raise MockExtractionError(
                f"sample {self.sample_id!r} uses unknown palette_relation "
                f"{self.palette_relation!r}"
            )
        if self.layout_template_class is not None and (
            self.layout_template_class not in LAYOUT_TEMPLATE_CLASSES
        ):
            raise MockExtractionError(
                f"sample {self.sample_id!r} uses unknown layout_template_class "
                f"{self.layout_template_class!r}"
            )
        if self.chart_class is not None and self.chart_class not in CHART_CLASSES:
            raise MockExtractionError(
                f"sample {self.sample_id!r} uses unknown chart_class {self.chart_class!r}"
            )
        if self.cover_role is not None and self.cover_role not in COVER_ROLES:
            raise MockExtractionError(
                f"sample {self.sample_id!r} uses unknown cover_role {self.cover_role!r}"
            )
        if self.aspect_band not in ASPECT_BANDS:
            raise MockExtractionError(
                f"sample {self.sample_id!r} uses unknown aspect_band {self.aspect_band!r}"
            )
        if self.placement not in PLACEMENTS:
            raise MockExtractionError(
                f"sample {self.sample_id!r} uses unknown placement {self.placement!r}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise MockExtractionError(
                f"sample {self.sample_id!r} confidence must be within 0..1"
            )
        if self.media_role is not None and self.media_role not in SEQUENCE_ROLES:
            raise MockExtractionError(
                f"sample {self.sample_id!r} uses unknown media_role {self.media_role!r}; "
                f"expected one of {list(SEQUENCE_ROLES)!r}"
            )

        ids = [region.region_id for region in self.regions]
        duplicates = sorted({rid for rid in ids if ids.count(rid) > 1})
        if duplicates:
            raise MockExtractionError(
                f"sample {self.sample_id!r} declares duplicate region ids: "
                + ", ".join(duplicates)
            )

        known = set(ids)
        unknown_text = sorted(set(self.text_region_ids) - known)
        if unknown_text:
            raise MockExtractionError(
                f"sample {self.sample_id!r} references unknown text regions: "
                + ", ".join(unknown_text)
            )
        unknown_order = sorted(set(self.reading_order) - known)
        if unknown_order:
            raise MockExtractionError(
                f"sample {self.sample_id!r} reading_order references unknown regions: "
                + ", ".join(unknown_order)
            )
        unknown_relations = sorted(set(self.cross_modal_relations) - known)
        if unknown_relations:
            raise MockExtractionError(
                f"sample {self.sample_id!r} cross_modal_relations reference unknown "
                "regions: " + ", ".join(unknown_relations)
            )

    # -- derived structural views -----------------------------------------

    def text_regions(self) -> tuple[RegionSpec, ...]:
        """Text-bearing regions, from role alone. No text is read."""

        return tuple(region for region in self.regions if region.is_text_region)

    def visual_regions(self) -> tuple[RegionSpec, ...]:
        """Pictorial or encoded-visual regions."""

        return tuple(region for region in self.regions if region.is_visual_region)

    def resolved_reading_order(self) -> tuple[str, ...]:
        """Declared reading order, or a deterministic derivation from geometry.

        The fallback sorts by ``layer_order`` then top-to-bottom then
        left-to-right, which is what a strict grid reading produces. It is a
        *structural* derivation: no language or text content is involved.
        """

        if self.reading_order:
            return tuple(self.reading_order)
        ordered = sorted(
            self.regions,
            key=lambda region: (
                region.layer_order,
                round(float(region.box["y"]), 6),
                round(float(region.box["x"]), 6),
            ),
        )
        return tuple(region.region_id for region in ordered)

    def dominant_visual_role(self) -> str | None:
        """Role of the largest visual region, used as the composition anchor."""

        visuals = self.visual_regions()
        if not visuals:
            return None
        anchor = max(visuals, key=lambda region: float(region.box["w"]) * float(region.box["h"]))
        return anchor.role

    def has_overlay_layers(self) -> bool:
        """True when regions occupy more than one layer.

        Multiple layers are what make a dominance order meaningful: a sample with
        everything on one layer has no stacking relation to report, so the
        extractor does not claim ``dominance_order`` for it.
        """

        return len({region.layer_order for region in self.regions}) > 1

    def page_sequence_roles(self) -> tuple[str, ...]:
        """Declared position of this sample within a multi-page or multi-shot run."""

        return (self.media_role,) if self.media_role else ()

    def dominant_sequence_role(self) -> str | None:
        return self.media_role


__all__ = [
    "COLOR_FAMILIES",
    "NEGATIVE_SPACE",
    "SUBJECT_SALIENCE",
    "MockExtractionError",
    "RegionSpec",
    "SampleProvenance",
    "SubjectSpec",
    "TextStyleSpec",
    "VisualSample",
    "region_to_dict",
]
