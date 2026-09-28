"""Derive text/visual relations from region geometry, never from text content.

This module is where the M1 anti-OCR rule is most tempting to break. The easy
way to relate a title to an image is to read the title and match its meaning to
the picture. That is OCR-plus-text-distillation wearing a cross-modal costume,
and it is exactly what the contract forbids.

What is computed here instead is **spatial relation**: a text region and a
visual region stand in a relation (``left_of``, ``above``, ``overlaps``,
``contains``, ``contained_by``, ``same_band``, ``diagonal``) determined purely by
their normalized boxes and layer orders. That relation is falsifiable,
explainable, and derived from structure alone.

Semantic relations (``reinforces``, ``contrasts``) can still be expressed, but
only when a caller **declares** them explicitly on the sample. The prototype
never infers meaning, only geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..taxonomy import ALIGNMENT_RELATIONS, StructuralObservation
from .visual_sample import MockExtractionError, VisualSample

#: Spatial relations this prototype can derive from geometry.
GEOMETRIC_RELATIONS: tuple[str, ...] = (
    "left_of",
    "right_of",
    "above",
    "below",
    "overlaps",
    "same_band",
    "diagonal",
    "contains",
    "contained_by",
)

#: Band tolerance: boxes whose vertical centres differ by less than this share a band.
_BAND_TOLERANCE = 0.12

#: Priority weight per visual role when choosing the composition anchor.
#:
#: ``background`` is deliberately last. A full-frame background box has the
#: largest area of anything in the sample, so ranking by area alone would always
#: pick it and every relation would read "contained_by the background" — which
#: is true but useless. The anchor should be the region the composition is
#: *about*: the subject, chart, or table.
_ANCHOR_WEIGHT: dict[str, float] = {
    "subject": 4.0,
    "chart": 4.0,
    "data_table": 4.0,
    "logo": 1.0,
    "background": 0.25,
}


def _anchor_score(region: Mapping[str, Any]) -> float:
    box = region["box"]
    area = float(box["w"]) * float(box["h"])
    role = str(region.get("role"))
    return area * _ANCHOR_WEIGHT.get(role, 1.0)


@dataclass(frozen=True, slots=True)
class CrossModalCandidate:
    """A text region, a visual region, and the structural relation between them.

    ``relation`` is always a semantic relation from the M1 closed vocabulary
    (because that is what the artifact stores). ``geometric_relation`` records
    the spatial fact the semantic relation rests on, and ``declared`` records
    whether a human supplied the semantic relation or the prototype mapped it
    from geometry. Keeping both means a reader can always tell interpretation
    from measurement.
    """

    candidate_id: str
    source_id: str
    text_region_id: str
    visual_region_id: str
    relation: str
    geometric_relation: str
    declared: bool
    confidence: float
    rationale: str
    text_role: str
    visual_role: str

    def as_evidence(self) -> dict[str, Any]:
        """Render the structural facts this candidate rests on."""

        return {
            "text_region_id": self.text_region_id,
            "visual_region_id": self.visual_region_id,
            "geometric_relation": self.geometric_relation,
            "declared": self.declared,
            "text_role": self.text_role,
            "visual_role": self.visual_role,
        }


def _centre(box: Mapping[str, float]) -> tuple[float, float]:
    return (float(box["x"]) + float(box["w"]) / 2.0, float(box["y"]) + float(box["h"]) / 2.0)


def _overlap_area(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    dx = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    dy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    if dx <= 0.0 or dy <= 0.0:
        return 0.0
    return float(dx) * float(dy)


def geometric_relation(
    text_box: Mapping[str, float],
    visual_box: Mapping[str, float],
    *,
    text_layer: int = 0,
    visual_layer: int = 0,
) -> str:
    """Classify the spatial relation between a text box and a visual box.

    Containment is checked before overlap, and overlap before direction, so the
    most specific true relation wins. Ties are broken deterministically by the
    order of the checks below.
    """

    text_area = float(text_box["w"]) * float(text_box["h"])
    visual_area = float(visual_box["w"]) * float(visual_box["h"])
    overlap = _overlap_area(text_box, visual_box)

    # Containment, with a small tolerance so a box flush to an edge still counts.
    tol = 1e-9
    if (
        overlap > 0.0
        and text_area > 0.0
        and overlap >= text_area - tol
        and text_area <= visual_area
    ):
        return "contained_by"
    if (
        overlap > 0.0
        and visual_area > 0.0
        and overlap >= visual_area - tol
        and visual_area < text_area
    ):
        return "contains"

    # Partial overlap: text sits on the visual, which is a distinct composition
    # from text beside it.
    if overlap > 0.0:
        coverage = overlap / min(text_area, visual_area) if min(text_area, visual_area) else 0.0
        if coverage >= 0.5:
            # A text box on top of a visual is an overlay; layer order confirms it.
            return "overlaps"

    text_cx, text_cy = _centre(text_box)
    visual_cx, visual_cy = _centre(visual_box)

    # Vertical ranges overlap, so the two regions share a horizontal strip. That
    # makes a left/right relation the meaningful one even when the boxes are
    # different heights — a short title beside a tall image reads as "text on
    # the left", not as a diagonal.
    vertical_overlap = (
        min(text_box["y"] + text_box["h"], visual_box["y"] + visual_box["h"])
        - max(text_box["y"], visual_box["y"])
    )
    same_band = abs(text_cy - visual_cy) <= _BAND_TOLERANCE
    if same_band and vertical_overlap > 0.0:
        if text_box["x"] + text_box["w"] <= visual_box["x"] + 1e-9:
            return "left_of"
        if visual_box["x"] + visual_box["w"] <= text_box["x"] + 1e-9:
            return "right_of"
        return "same_band"
    if vertical_overlap > 0.0:
        if text_box["x"] + text_box["w"] <= visual_box["x"] + 1e-9:
            return "left_of"
        if visual_box["x"] + visual_box["w"] <= text_box["x"] + 1e-9:
            return "right_of"

    # Vertically stacked: check the pure stacking cases before falling back to a
    # diagonal, so "above"/"below" win whenever the strips do not overlap.
    horizontally_separated = (
        text_box["x"] + text_box["w"] <= visual_box["x"] + 1e-9
        or visual_box["x"] + visual_box["w"] <= text_box["x"] + 1e-9
    )
    if not horizontally_separated:
        if text_box["y"] + text_box["h"] <= visual_box["y"] + 1e-9:
            return "above"
        if visual_box["y"] + visual_box["h"] <= text_box["y"] + 1e-9:
            return "below"
    return "diagonal"


#: Maps a geometric relation onto the semantic relation the artifact stores.
#: These mappings are *interpretive but fixed*: adjacency label text next to a
#: chart is labelled by it; a text block above a visual is a caption-style
#: sequence, not a claim about meaning.
_SEMANTIC_BY_GEOMETRIC: dict[str, str] = {
    "left_of": "labels",
    "right_of": "labels",
    "above": "illustrates",
    "below": "illustrates",
    "overlaps": "reinforces",
    "same_band": "illustrates",
    "diagonal": "illustrates",
    "contains": "labels",
    "contained_by": "reinforces",
}


def _semantic_for(geometric: str) -> str:
    return _SEMANTIC_BY_GEOMETRIC.get(geometric, "illustrates")


def _text_role_for(role: str) -> str:
    """Map a universal region role onto a cross-modal text role."""

    return {
        "title": "title",
        "subtitle": "subtitle",
        "body": "body",
        "caption": "caption",
        "label": "label",
        "annotation": "label",
        "header": "title",
        "footer": "cta",
    }.get(role, "body")


def candidates_from_sample(sample: VisualSample) -> tuple[CrossModalCandidate, ...]:
    """Pair each declared text region with the sample's dominant visual region.

    Only pairs the sample actually supports are emitted. A sample with no text
    region, or no visual region, yields no candidates — the prototype never
    invents a cross-modal claim to fill a required slot.
    """

    text_regions = sample.text_regions()
    visual_regions = sample.visual_regions()
    if not text_regions or not visual_regions:
        return ()

    anchor = max(
        visual_regions,
        key=lambda region: (
            _anchor_score(
                {
                    "role": region.role,
                    "box": region.box,
                }
            ),
            # Deterministic tie-break: stable region id ordering.
            region.region_id,
        ),
    )

    explicit = dict(sample.cross_modal_relations)
    candidates: list[CrossModalCandidate] = []
    for text_region in sorted(text_regions, key=lambda region: region.region_id):
        geometric = geometric_relation(
            text_region.box,
            anchor.box,
            text_layer=text_region.layer_order,
            visual_layer=anchor.layer_order,
        )
        declared = text_region.region_id in explicit
        relation = explicit[text_region.region_id] if declared else _semantic_for(geometric)
        if relation not in ALIGNMENT_RELATIONS:
            raise MockExtractionError(
                f"sample {sample.sample_id!r} declares unknown cross-modal relation "
                f"{relation!r} for region {text_region.region_id!r}"
            )
        candidates.append(
            CrossModalCandidate(
                candidate_id=f"{sample.sample_id}:{text_region.region_id}:{anchor.region_id}",
                source_id=sample.sample_id,
                text_region_id=text_region.region_id,
                visual_region_id=anchor.region_id,
                relation=relation,
                geometric_relation=geometric,
                declared=declared,
                confidence=sample.confidence if declared else round(sample.confidence * 0.9, 6),
                rationale=(
                    "Relation declared by the sample author."
                    if declared
                    else f"Text region is {geometric} the dominant visual region "
                    f"({anchor.role}); mapped structurally."
                ),
                text_role=_text_role_for(text_region.role),
                visual_role=anchor.role,
            )
        )
    return tuple(candidates)


def candidates_from_observation(
    observation: StructuralObservation,
    *,
    declared_relations: Mapping[str, str] | None = None,
    confidence: float | None = None,
) -> tuple[CrossModalCandidate, ...]:
    """Derive candidates from an already-built observation.

    Provided for callers that already hold M1 observations. It reuses the
    observation's own region list, so the geometry being related is the geometry
    that will be stored — no recomputation drift.
    """

    regions = [dict(region) for region in observation.regions]
    if not regions:
        return ()

    text_roles = {
        "title",
        "subtitle",
        "body",
        "caption",
        "label",
        "annotation",
        "header",
        "footer",
    }
    visual_roles = {"subject", "chart", "data_table", "background", "logo"}
    text_regions = [region for region in regions if region.get("role") in text_roles]
    visual_regions = [region for region in regions if region.get("role") in visual_roles]
    if not text_regions or not visual_regions:
        return ()

    anchor = max(
        visual_regions,
        key=lambda region: (
            _anchor_score(region),
            str(region.get("region_id")),
        ),
    )
    explicit = dict(declared_relations or {})
    base_confidence = observation.confidence if confidence is None else confidence

    candidates: list[CrossModalCandidate] = []
    for text_region in sorted(text_regions, key=lambda region: str(region.get("region_id"))):
        geometric = geometric_relation(
            text_region["box"],
            anchor["box"],
            text_layer=int(text_region.get("layer_order", 0)),
            visual_layer=int(anchor.get("layer_order", 0)),
        )
        region_id = str(text_region.get("region_id"))
        declared = region_id in explicit
        relation = explicit[region_id] if declared else _semantic_for(geometric)
        if relation not in ALIGNMENT_RELATIONS:
            raise MockExtractionError(
                f"declared unknown cross-modal relation {relation!r} for region {region_id!r}"
            )
        candidates.append(
            CrossModalCandidate(
                candidate_id=f"{observation.observation_id}:{region_id}:{anchor.get('region_id')}",
                source_id=observation.source_id,
                text_region_id=region_id,
                visual_region_id=str(anchor.get("region_id")),
                relation=relation,
                geometric_relation=geometric,
                declared=declared,
                confidence=base_confidence,
                rationale=f"Text region is {geometric} the dominant visual region.",
                text_role=_text_role_for(str(text_region.get("role"))),
                visual_role=str(anchor.get("role")),
            )
        )
    return tuple(candidates)


__all__ = [
    "GEOMETRIC_RELATIONS",
    "CrossModalCandidate",
    "candidates_from_observation",
    "candidates_from_sample",
    "geometric_relation",
]
