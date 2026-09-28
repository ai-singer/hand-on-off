"""The Visual Pattern Similarity Contract.

Four explainable dimensions
---------------------------

``geometry`` (weight 0.30)
    Region position, size, and layer ordering. Regions are matched **by role**,
    not by index, so two templates that describe the same structure with regions
    declared in a different order score identically.

``structure`` (weight 0.30)
    The layout graph: the set of adjacency relations between region pairs, plus
    template class, alignment, and density. This is what distinguishes "text on
    the left of the image" from "text above the image" even when the boxes are
    numerically similar.

``style`` (weight 0.22)
    Colour family, palette relation, contrast role, and type scale structure.
    Coarse closed vocabularies only — no colour histograms, because a histogram
    score cannot be argued with.

``asset`` (weight 0.18)
    Subject class, subject salience, and asset placement.
    Weighted lowest because asset identity is the most volatile part of a
    template: creators reuse a layout with different subjects far more readily
    than they change a layout.

Provenance
----------

:class:`~multimodal_creator.extraction.visual_sample.SampleProvenance` exists so
this contract can distinguish two very different claims:

``provenance_only``
    Similarity between samples from the *same* creator. Useful, but a creator
    repeating their own layout is not evidence of a shared template.
``cross_provenance``
    Similarity is only meaningful when the two samples come from *different*
    creators. Required for template discovery, because that is the only mode in
    which agreement is informative.

The mode is an explicit parameter, never a default assumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..extraction.visual_sample import MockExtractionError, RegionSpec, VisualSample

# --------------------------------------------------------------------------
# Contract constants
# --------------------------------------------------------------------------

#: The four comparison dimensions, in canonical order.
DIMENSIONS: tuple[str, ...] = ("geometry", "structure", "style", "asset")

#: Weight per dimension. Sums to exactly 1.0.
#:
#: Layout carries 65% (geometry + structure) because a "template" is
#: fundamentally a spatial arrangement. Style carries 20%, and asset only 15%:
#: creators swap subjects far more readily than they change a layout, so asset
#: identity is the weakest evidence of a shared template.
DIMENSION_WEIGHTS: Mapping[str, float] = {
    "geometry": 0.35,
    "structure": 0.30,
    "style": 0.20,
    "asset": 0.15,
}

#: Permitted provenance comparison modes.
PROVENANCE_MODES: tuple[str, ...] = ("provenance_agnostic", "provenance_only", "cross_provenance")

#: Minimum number of members before a cluster may be called a recurring template.
STRUCTURAL_RECURRENCE_MIN = 3

#: Decimal places every score is rounded to, so results are byte-comparable.
SCORE_PRECISION = 6

#: Weight applied to layer-order agreement inside the geometry dimension.
_LAYER_ORDER_WEIGHT = 0.15
#: Position and size are weighted separately so a moved region and a resized
#: region are both visible in the score rather than averaging each other out.
_POSITION_WEIGHT = 0.45
_SIZE_WEIGHT = 0.40

#: Weight applied to layout-graph agreement inside the structure dimension.
_GRAPH_WEIGHT = 0.60
_TEMPLATE_CLASS_WEIGHT = 0.25
_ALIGNMENT_WEIGHT = 0.15
_DENSITY_WEIGHT = 0.10

#: Score used when a comparable field is absent on one side only. "Not declared"
#: is weaker evidence than "agrees" but is not the same as "differs", so it is
#: scored neutrally rather than as a mismatch.
_UNDECLARED = 0.5

#: Weight applied to colour agreement inside the style dimension.
_COLOR_WEIGHT = 0.55
_TYPOGRAPHY_WEIGHT = 0.45

#: Weight applied to subject agreement inside the asset dimension.
_SUBJECT_WEIGHT = 0.7
_PLACEMENT_WEIGHT = 0.3


class SimilarityContractError(MockExtractionError):
    """Raised when a similarity comparison is asked for something undefined."""


def _round(value: float) -> float:
    return round(float(value), SCORE_PRECISION)


def _clamp(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def dimension_weights() -> dict[str, float]:
    """Return the dimension weights, asserting they sum to 1.0."""

    total = sum(DIMENSION_WEIGHTS.values())
    if abs(total - 1.0) > 1e-9:
        raise SimilarityContractError(
            f"dimension weights must sum to 1.0, got {total!r}"
        )
    return dict(DIMENSION_WEIGHTS)


@dataclass(frozen=True, slots=True)
class DifferenceCode:
    """A machine-readable reason two samples are not identical."""

    code: str
    dimension: str
    detail: str


@dataclass(frozen=True, slots=True)
class Contribution:
    """One dimension's weighted contribution to the final score."""

    dimension: str
    raw_score: float
    weight: float
    weighted_score: float
    agreements: tuple[str, ...] = ()
    differences: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DimensionScore:
    """The raw score of one dimension before weighting."""

    dimension: str
    score: float
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SimilarityResult:
    """A fully decomposable similarity score.

    ``score`` alone is never enough to act on; ``contributions`` and
    ``difference_codes`` are what let a reader audit or contest the number.
    """

    left_id: str
    right_id: str
    score: float
    provenance_mode: str
    dimensions: tuple[DimensionScore, ...]
    contributions: tuple[Contribution, ...]
    difference_codes: tuple[DifferenceCode, ...]
    comparable: bool
    suppressed_reason: str | None = None

    def dimension(self, name: str) -> DimensionScore:
        for item in self.dimensions:
            if item.dimension == name:
                return item
        raise SimilarityContractError(f"unknown dimension {name!r}")

    def codes(self) -> tuple[str, ...]:
        return tuple(code.code for code in self.difference_codes)

    def explain(self) -> str:
        """Render a human-readable explanation of the score."""

        lines = [
            f"{self.left_id} vs {self.right_id}: "
            f"similarity={self.score:.3f} ({self.provenance_mode})",
            f"  comparable={self.comparable}"
            + (f" ({self.suppressed_reason})" if self.suppressed_reason else ""),
        ]
        for contribution in self.contributions:
            lines.append(
                f"  {contribution.dimension:<10} raw={contribution.raw_score:.3f} "
                f"x {contribution.weight:.2f} = {contribution.weighted_score:.4f}"
            )
            for agreement in contribution.agreements:
                lines.append(f"      + {agreement}")
            for difference in contribution.differences:
                lines.append(f"      - {difference}")
        if self.difference_codes:
            lines.append("  differences: " + ", ".join(self.codes()))
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "score": self.score,
            "provenance_mode": self.provenance_mode,
            "comparable": self.comparable,
            "suppressed_reason": self.suppressed_reason,
            "dimensions": [
                {"dimension": item.dimension, "score": item.score, "detail": dict(item.detail)}
                for item in self.dimensions
            ],
            "contributions": [
                {
                    "dimension": item.dimension,
                    "raw_score": item.raw_score,
                    "weight": item.weight,
                    "weighted_score": item.weighted_score,
                    "agreements": list(item.agreements),
                    "differences": list(item.differences),
                }
                for item in self.contributions
            ],
            "difference_codes": [
                {"code": code.code, "dimension": code.dimension, "detail": code.detail}
                for code in self.difference_codes
            ],
        }


# --------------------------------------------------------------------------
# Structural views used by the dimensions
# --------------------------------------------------------------------------


def regions_by_role(sample: VisualSample) -> dict[str, tuple[RegionSpec, ...]]:
    """Group regions by role, each group deterministically ordered.

    Grouping by role is what makes geometry comparison order-independent: two
    samples describing the same layout with regions listed in different orders
    produce identical groupings.
    """

    grouped: dict[str, list[RegionSpec]] = {}
    for region in sample.regions:
        grouped.setdefault(region.role, []).append(region)
    return {
        role: tuple(
            sorted(
                regions,
                key=lambda r: (
                    round(float(r.box["y"]), 6),
                    round(float(r.box["x"]), 6),
                    r.region_id,
                ),
            )
        )
        for role, regions in grouped.items()
    }


def _box_distance(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    """Mean absolute normalized difference across the four box components."""

    return sum(abs(float(a[k]) - float(b[k])) for k in ("x", "y", "w", "h")) / 4.0


def _box_similarity(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    return _clamp(1.0 - _box_distance(a, b))


def _position_similarity(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    """Agreement of where a region sits, ignoring how large it is."""

    distance = (abs(float(a["x"]) - float(b["x"])) + abs(float(a["y"]) - float(b["y"]))) / 2.0
    return _clamp(1.0 - distance)


def _size_similarity(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    """Agreement of how large a region is, ignoring where it sits.

    Uses area ratio so a region that doubles in area scores consistently
    regardless of which side is larger.
    """

    area_a = float(a["w"]) * float(a["h"])
    area_b = float(b["w"]) * float(b["h"])
    if area_a <= 0.0 and area_b <= 0.0:
        return 1.0
    if area_a <= 0.0 or area_b <= 0.0:
        return 0.0
    ratio = min(area_a, area_b) / max(area_a, area_b)
    # Also consider aspect, so a wide strip and a tall strip of equal area differ.
    aspect_a = float(a["w"]) / float(a["h"])
    aspect_b = float(b["w"]) / float(b["h"])
    aspect_ratio = min(aspect_a, aspect_b) / max(aspect_a, aspect_b)
    return _clamp(0.5 * ratio + 0.5 * aspect_ratio)


def layout_edges(sample: VisualSample) -> frozenset[tuple[str, str, str]]:
    """The layout graph: relations between region-role pairs.

    Each edge is ``(role_a, relation, role_b)`` with roles sorted, so the graph
    is directly comparable across samples.

    Region pairs are canonicalised by **region id** before the relation is
    computed. ``geometric_relation`` is not symmetric in its arguments —
    ``contained_by`` only becomes ``contains`` when the boxes are swapped — so
    without canonicalisation, reversing the order in which a sample declares its
    regions would change its layout graph and therefore its similarity score.
    Ordering by id makes the graph a property of the structure rather than of the
    declaration order.
    """

    from ..extraction.cross_modal_candidates import geometric_relation

    # Sort by region id so the graph cannot depend on declaration order, and
    # compute each unordered pair exactly once.
    regions = sorted(sample.regions, key=lambda region: region.region_id)
    edges: set[tuple[str, str, str]] = set()
    for index, first in enumerate(regions):
        for second in regions[index + 1 :]:
            relation = geometric_relation(
                first.box,
                second.box,
                text_layer=first.layer_order,
                visual_layer=second.layer_order,
            )
            role_a, role_b = sorted((first.role, second.role))
            edges.add((role_a, relation, role_b))
    return frozenset(edges)


def _jaccard(left: frozenset, right: frozenset) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


# --------------------------------------------------------------------------
# The four dimensions
# --------------------------------------------------------------------------


def geometry_dimension(
    left: VisualSample, right: VisualSample
) -> tuple[float, dict[str, Any]]:
    """Position, size, and layer-order agreement, matched by region role."""

    left_roles = regions_by_role(left)
    right_roles = regions_by_role(right)
    shared = sorted(set(left_roles) & set(right_roles))
    all_roles = sorted(set(left_roles) | set(right_roles))

    if not all_roles:
        return 1.0, {"shared_roles": 0, "coverage": 1.0, "mean_box_similarity": 1.0}

    if not shared:
        return 0.0, {
            "shared_roles": 0,
            "coverage": 0.0,
            "mean_box_similarity": 0.0,
            "left_roles": sorted(left_roles),
            "right_roles": sorted(right_roles),
        }

    position_scores: list[float] = []
    size_scores: list[float] = []
    box_scores: list[float] = []
    layer_scores: list[float] = []
    position_weights: list[float] = []
    for role in shared:
        left_group = left_roles[role]
        right_group = right_roles[role]
        # Pair by position within the role group, so a repeated role (three
        # cards) is compared like-for-like rather than all-against-all.
        for index in range(min(len(left_group), len(right_group))):
            left_box = left_group[index].box
            right_box = right_group[index].box
            # Displacement is weighted by how much of the frame the role
            # occupies: moving the main image across the canvas changes the
            # layout far more than nudging a caption, and the score should say so.
            span = max(
                float(left_box["w"]) * float(left_box["h"]),
                float(right_box["w"]) * float(right_box["h"]),
            )
            position_scores.append(_position_similarity(left_box, right_box))
            position_weights.append(span)
            size_scores.append(_size_similarity(left_box, right_box))
            box_scores.append(_box_similarity(left_box, right_box))
            layer_scores.append(
                1.0
                if left_group[index].layer_order == right_group[index].layer_order
                else 0.0
            )
        # A role present on one side with more instances is a structural
        # difference, not a free pass: charge the unmatched instances.
        extra = abs(len(left_group) - len(right_group))
        position_scores.extend([0.0] * extra)
        position_weights.extend([0.25] * extra)
        size_scores.extend([0.0] * extra)
        box_scores.extend([0.0] * extra)
        layer_scores.extend([0.0] * extra)

    def mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def weighted_mean(values: list[float], weights: list[float]) -> float:
        total_weight = sum(weights)
        if total_weight <= 0.0:
            return mean(values)
        return sum(v * w for v, w in zip(values, weights)) / total_weight

    mean_position = weighted_mean(position_scores, position_weights)
    mean_size = mean(size_scores)
    mean_box = mean(box_scores)
    mean_layer = mean(layer_scores)
    coverage = len(shared) / len(all_roles)
    agreement = (
        _POSITION_WEIGHT * mean_position
        + _SIZE_WEIGHT * mean_size
        + _LAYER_ORDER_WEIGHT * mean_layer
    )
    score = coverage * agreement

    return _clamp(score), {
        "shared_roles": len(shared),
        "coverage": _round(coverage),
        "mean_position_similarity": _round(mean_position),
        "mean_size_similarity": _round(mean_size),
        "mean_box_similarity": _round(mean_box),
        "mean_layer_agreement": _round(mean_layer),
    }


def structure_dimension(
    left: VisualSample, right: VisualSample
) -> tuple[float, dict[str, Any]]:
    """Layout graph, template class, alignment, and density agreement."""

    left_edges = layout_edges(left)
    right_edges = layout_edges(right)
    graph = _jaccard(left_edges, right_edges)

    if left.layout_template_class and right.layout_template_class:
        template_class = (
            1.0 if left.layout_template_class == right.layout_template_class else 0.0
        )
    else:
        # Absent on either side: no evidence either way, so score neutral rather
        # than punishing the sample for not declaring it. When one side declares
        # and the other does not, that is weaker agreement than a match but
        # stronger than a contradiction.
        template_class = _UNDECLARED

    if left.alignment and right.alignment:
        alignment = 1.0 if left.alignment == right.alignment else 0.0
    elif left.alignment is None and right.alignment is None:
        alignment = _UNDECLARED
    else:
        alignment = _UNDECLARED

    density = 1.0 if left.composition_density == right.composition_density else 0.0

    score = (
        _GRAPH_WEIGHT * graph
        + _TEMPLATE_CLASS_WEIGHT * template_class
        + _ALIGNMENT_WEIGHT * alignment
        + _DENSITY_WEIGHT * density
    )
    return _clamp(score), {
        "graph_jaccard": _round(graph),
        "template_class": _round(template_class),
        "alignment": _round(alignment),
        "density": _round(density),
        "left_edges": len(left_edges),
        "right_edges": len(right_edges),
        "shared_edges": len(left_edges & right_edges),
    }


def style_dimension(
    left: VisualSample, right: VisualSample
) -> tuple[float, dict[str, Any]]:
    """Colour system and typographic structure agreement."""

    color_parts = [
        1.0 if left.color_family == right.color_family else 0.0,
        1.0 if left.palette_relation == right.palette_relation else 0.0,
        1.0 if left.contrast_role == right.contrast_role else 0.0,
    ]
    color = sum(color_parts) / len(color_parts)

    if left.text_style and right.text_style:
        scale = 1.0 if left.text_style.scale_relation == right.text_style.scale_relation else 0.0
        level_gap = abs(left.text_style.hierarchy_levels - right.text_style.hierarchy_levels)
        # One level of hierarchy difference is a near-miss, not a mismatch: a
        # three-level design and a four-level design are still the same family.
        levels = 1.0 if level_gap == 0 else (0.5 if level_gap == 1 else 0.0)
        typography = (scale + levels) / 2.0
    elif left.text_style is None and right.text_style is None:
        # Neither declares typography: nothing to compare, so stay neutral.
        typography = _UNDECLARED
    else:
        # One declares typography and the other does not. That is a real
        # structural asymmetry, so it scores below a match — but the colour
        # evidence still counts.
        typography = _UNDECLARED * 0.5

    score = _COLOR_WEIGHT * color + _TYPOGRAPHY_WEIGHT * typography
    return _clamp(score), {
        "color_family": _round(color_parts[0]),
        "palette_relation": _round(color_parts[1]),
        "contrast_role": _round(color_parts[2]),
        "color": _round(color),
        "typography": _round(typography),
    }


def asset_dimension(
    left: VisualSample, right: VisualSample
) -> tuple[float, dict[str, Any]]:
    """Subject class, salience, and placement agreement."""

    subject = 1.0 if left.subject.subject_class == right.subject.subject_class else 0.0
    salience = 1.0 if left.subject.salience == right.subject.salience else 0.0
    if left.placement == "unknown" or right.placement == "unknown":
        placement = _UNDECLARED
    else:
        placement = 1.0 if left.placement == right.placement else 0.0
    subject_score = (subject + salience) / 2.0

    score = _SUBJECT_WEIGHT * subject_score + _PLACEMENT_WEIGHT * placement
    return _clamp(score), {
        "subject_class": _round(subject),
        "salience": _round(salience),
        "placement": _round(placement),
        "subject": _round(subject_score),
    }


_DIMENSION_FUNCTIONS = {
    "geometry": geometry_dimension,
    "structure": structure_dimension,
    "style": style_dimension,
    "asset": asset_dimension,
}


# --------------------------------------------------------------------------
# Difference codes
# --------------------------------------------------------------------------


def _difference_codes(
    left: VisualSample,
    right: VisualSample,
    details: Mapping[str, Mapping[str, Any]],
) -> tuple[DifferenceCode, ...]:
    """Derive machine-readable reasons the two samples are not identical."""

    codes: list[DifferenceCode] = []

    def add(code: str, dimension: str, detail: str) -> None:
        codes.append(DifferenceCode(code=code, dimension=dimension, detail=detail))

    if left.layout_template_class != right.layout_template_class:
        add(
            "layout_template_class_mismatch",
            "structure",
            f"{left.layout_template_class!r} vs {right.layout_template_class!r}",
        )
    if left.alignment != right.alignment:
        add("alignment_mismatch", "structure", f"{left.alignment!r} vs {right.alignment!r}")

    graph = details["structure"].get("graph_jaccard", 1.0)
    if graph < 1.0:
        add("layout_graph_differs", "structure", f"graph_jaccard={graph}")

    if left.color_family != right.color_family:
        add(
            "color_family_mismatch",
            "style",
            f"{left.color_family!r} vs {right.color_family!r}",
        )
    if left.palette_relation != right.palette_relation:
        add(
            "palette_relation_mismatch",
            "style",
            f"{left.palette_relation!r} vs {right.palette_relation!r}",
        )
    if left.contrast_role != right.contrast_role:
        add(
            "contrast_role_mismatch",
            "style",
            f"{left.contrast_role!r} vs {right.contrast_role!r}",
        )
    if (left.text_style is None) != (right.text_style is None):
        add("typography_missing_on_one_side", "style", "one sample declares no text_style")
    elif left.text_style is not None and right.text_style is not None:
        if left.text_style.scale_relation != right.text_style.scale_relation:
            add(
                "type_scale_relation_mismatch",
                "style",
                f"{left.text_style.scale_relation!r} vs "
                f"{right.text_style.scale_relation!r}",
            )

    if left.subject.subject_class != right.subject.subject_class:
        add(
            "subject_class_mismatch",
            "asset",
            f"{left.subject.subject_class!r} vs {right.subject.subject_class!r}",
        )
    if left.subject.salience != right.subject.salience:
        add(
            "subject_salience_mismatch",
            "asset",
            f"{left.subject.salience!r} vs {right.subject.salience!r}",
        )
    if left.placement != right.placement:
        add("placement_mismatch", "asset", f"{left.placement!r} vs {right.placement!r}")

    if left.composition_density != right.composition_density:
        add(
            "composition_density_mismatch",
            "structure",
            f"{left.composition_density!r} vs {right.composition_density!r}",
        )

    left_roles = set(regions_by_role(left))
    right_roles = set(regions_by_role(right))
    if left_roles != right_roles:
        only_left = sorted(left_roles - right_roles)
        only_right = sorted(right_roles - left_roles)
        if only_left:
            add("region_role_absent_on_right", "geometry", ", ".join(only_left))
        if only_right:
            add("region_role_absent_on_left", "geometry", ", ".join(only_right))

    if details["geometry"].get("mean_box_similarity", 1.0) < 1.0:
        add(
            "region_geometry_differs",
            "geometry",
            f"mean_box_similarity={details['geometry'].get('mean_box_similarity')}",
        )
    if details["geometry"].get("mean_layer_agreement", 1.0) < 1.0:
        add(
            "layer_order_differs",
            "geometry",
            f"mean_layer_agreement={details['geometry'].get('mean_layer_agreement')}",
        )

    return tuple(sorted(codes, key=lambda code: (code.dimension, code.code)))


def _agreements_and_differences(
    dimension: str,
    left: VisualSample,
    right: VisualSample,
    detail: Mapping[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Render human-readable agreements and differences for one dimension."""

    agreements: list[str] = []
    differences: list[str] = []

    if dimension == "geometry":
        if detail.get("coverage") == 1.0:
            agreements.append("region roles match exactly")
        else:
            differences.append(f"region role coverage {detail.get('coverage')}")
        if detail.get("mean_box_similarity") == 1.0:
            agreements.append("region boxes match")
        if detail.get("mean_layer_agreement") == 1.0:
            agreements.append("layer ordering matches")
        elif detail.get("mean_layer_agreement") != 1.0:
            differences.append(f"layer agreement {detail.get('mean_layer_agreement')}")
    elif dimension == "structure":
        if detail.get("template_class") == 1.0:
            agreements.append(f"template class {left.layout_template_class}")
        elif detail.get("template_class") == 0.0:
            differences.append(
                f"template class {left.layout_template_class} vs "
                f"{right.layout_template_class}"
            )
        if detail.get("graph_jaccard") == 1.0:
            agreements.append("layout graph identical")
        else:
            differences.append(f"layout graph jaccard {detail.get('graph_jaccard')}")
        if detail.get("alignment") == 1.0:
            agreements.append(f"alignment {left.alignment}")
    elif dimension == "style":
        if detail.get("color_family") == 1.0:
            agreements.append(f"colour family {left.color_family}")
        else:
            differences.append(
                f"colour family {left.color_family} vs {right.color_family}"
            )
        if detail.get("typography") in (0.5, 1.0):
            agreements.append("typography comparable")
        else:
            differences.append("typography differs")
    elif dimension == "asset":
        if detail.get("subject_class") == 1.0:
            agreements.append(f"subject class {left.subject.subject_class}")
        else:
            differences.append(
                f"subject class {left.subject.subject_class} vs "
                f"{right.subject.subject_class}"
            )
        if detail.get("placement") == 0.0:
            differences.append(f"placement {left.placement} vs {right.placement}")

    return tuple(agreements), tuple(differences)


# --------------------------------------------------------------------------
# Public entry points
# --------------------------------------------------------------------------


def pairwise_similarity(
    left: VisualSample,
    right: VisualSample,
    *,
    provenance_mode: str = "provenance_agnostic",
) -> SimilarityResult:
    """Compare two visual samples and explain the result.

    When ``provenance_mode`` is ``cross_provenance`` and both samples come from
    the same creator, the result is returned with ``comparable=False`` and a
    suppressed score rather than a misleading high number.
    """

    if provenance_mode not in PROVENANCE_MODES:
        raise SimilarityContractError(
            f"unknown provenance_mode {provenance_mode!r}; expected one of "
            f"{list(PROVENANCE_MODES)!r}"
        )

    same_creator = left.provenance.creator_id == right.provenance.creator_id
    comparable = True
    suppressed: str | None = None
    if provenance_mode == "provenance_only" and not same_creator:
        comparable = False
        suppressed = "samples come from different creators"
    elif provenance_mode == "cross_provenance" and same_creator:
        comparable = False
        suppressed = "samples come from the same creator; agreement is not independent"

    if not comparable:
        return SimilarityResult(
            left_id=left.sample_id,
            right_id=right.sample_id,
            score=0.0,
            provenance_mode=provenance_mode,
            dimensions=tuple(
                DimensionScore(dimension=name, score=0.0, detail={})
                for name in DIMENSIONS
            ),
            contributions=(),
            difference_codes=(
                DifferenceCode(
                    code="provenance_not_comparable",
                    dimension="provenance",
                    detail=suppressed or "",
                ),
            ),
            comparable=False,
            suppressed_reason=suppressed,
        )

    weights = dimension_weights()
    details: dict[str, Mapping[str, Any]] = {}
    dimensions: list[DimensionScore] = []
    for name in DIMENSIONS:
        raw, detail = _DIMENSION_FUNCTIONS[name](left, right)
        details[name] = detail
        dimensions.append(
            DimensionScore(dimension=name, score=_round(raw), detail=dict(detail))
        )

    contributions: list[Contribution] = []
    total = 0.0
    for item in dimensions:
        weight = weights[item.dimension]
        weighted = _round(item.score * weight)
        total += weighted
        agreements, differences = _agreements_and_differences(
            item.dimension, left, right, item.detail
        )
        contributions.append(
            Contribution(
                dimension=item.dimension,
                raw_score=item.score,
                weight=weight,
                weighted_score=weighted,
                agreements=agreements,
                differences=differences,
            )
        )

    score = _round(_clamp(total))
    codes = _difference_codes(left, right, details)
    return SimilarityResult(
        left_id=left.sample_id,
        right_id=right.sample_id,
        score=score,
        provenance_mode=provenance_mode,
        dimensions=tuple(dimensions),
        contributions=tuple(contributions),
        difference_codes=codes,
        comparable=True,
    )


def similarity_matrix(
    samples: Iterable[VisualSample],
    *,
    provenance_mode: str = "provenance_agnostic",
) -> dict[tuple[str, str], SimilarityResult]:
    """Compute every unordered pair exactly once.

    Keys are ``(left_id, right_id)`` sorted lexicographically, so the matrix is
    independent of the input order.
    """

    ordered = sorted(samples, key=lambda sample: sample.sample_id)
    ids = [sample.sample_id for sample in ordered]
    duplicates = sorted({sid for sid in ids if ids.count(sid) > 1})
    if duplicates:
        raise SimilarityContractError("duplicate sample ids: " + ", ".join(duplicates))

    matrix: dict[tuple[str, str], SimilarityResult] = {}
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            matrix[(left.sample_id, right.sample_id)] = pairwise_similarity(
                left, right, provenance_mode=provenance_mode
            )
    return matrix


__all__ = [
    "DIMENSION_WEIGHTS",
    "DIMENSIONS",
    "PROVENANCE_MODES",
    "SCORE_PRECISION",
    "STRUCTURAL_RECURRENCE_MIN",
    "Contribution",
    "DifferenceCode",
    "DimensionScore",
    "SimilarityContractError",
    "SimilarityResult",
    "asset_dimension",
    "dimension_weights",
    "geometry_dimension",
    "layout_edges",
    "pairwise_similarity",
    "regions_by_role",
    "similarity_matrix",
    "structure_dimension",
    "style_dimension",
]
