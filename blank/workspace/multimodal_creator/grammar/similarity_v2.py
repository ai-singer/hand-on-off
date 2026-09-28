"""Similarity v2 — a vector, never a single score (Phase M4, phase 3).

M3's central measurement problem was that **one number cannot serve two
questions**. Template discovery asks "is this the same arrangement?" Creator
style analysis asks "is this the same visual voice?" Those are different
questions, and a weighted sum of them answers neither: two posts by one creator
in different layouts score moderately on the blend while being *identical* in
style and *unrelated* in structure.

M4 therefore reports a :class:`SimilarityVector` and **refuses to collapse it**.
There is no ``total``, no ``score``, and no weighting that produces one — the
type has no field for it, so synthesis is not merely discouraged but
unrepresentable.

How the two questions are then answered
---------------------------------------

:data:`TEMPLATE_PROFILE` reads ``structural`` and ``composition``.
:data:`CREATOR_STYLE_PROFILE` reads ``style`` and ``composition``.
:data:`BALANCED_PROFILE` weighs all four.

A profile is an explicit, named, inspectable choice. The vector itself is
task-free, so the same measurement can be re-read differently without
re-running the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..taxonomy import StructuralObservation
from .model import ATTENTION_STAGES, VisualGrammar

#: The four similarity dimensions. Order is canonical.
SIMILARITY_DIMENSIONS: tuple[str, ...] = (
    "structural",
    "style",
    "composition",
    "asset",
)

#: Value used when a dimension cannot be computed for a pair. Neutral, and
#: always accompanied by a recorded reason — an unavailable dimension must never
#: look like a measured zero.
UNAVAILABLE = 0.0

#: Region-overlap weight inside the structural dimension.
_PRESENCE_WEIGHT = 0.6
_PLACEMENT_WEIGHT = 0.4

#: Relation-overlap weight inside the composition dimension.
_RELATION_WEIGHT = 0.6
_ATTENTION_WEIGHT = 0.4

#: Style component weights.
_COLOUR_WEIGHT = 0.4
_DENSITY_WEIGHT = 0.3
_PALETTE_WEIGHT = 0.3

#: Asset component weights.
_SUBJECT_WEIGHT = 0.5
_PLACEMENT_WEIGHT_ASSET = 0.3
_CHART_WEIGHT = 0.2

SCORE_PRECISION = 6


class SimilarityError(Exception):
    """Raised when a similarity comparison is undefined."""


def _round(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), SCORE_PRECISION)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 1.0


@dataclass(frozen=True, slots=True)
class DimensionReading:
    """One dimension's value plus what produced it."""

    dimension: str
    value: float
    available: bool = True
    detail: Mapping[str, Any] = field(default_factory=dict)
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.dimension not in SIMILARITY_DIMENSIONS:
            raise SimilarityError(f"unknown dimension {self.dimension!r}")
        if not 0.0 <= self.value <= 1.0:
            raise SimilarityError(f"value must be within 0..1, got {self.value!r}")
        if not self.available and not self.unavailable_reason:
            raise SimilarityError(
                f"dimension {self.dimension!r} is unavailable without a reason; an "
                "unexplained gap is indistinguishable from a measured zero"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "available": self.available,
            "detail": dict(self.detail),
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True, slots=True)
class SimilarityVector:
    """Four independent readings. Deliberately has no combined score.

    If you want one number, you must pick a :class:`SimilarityProfile` and say
    so. That forces the choice into the open instead of hiding it inside a
    weighting that nobody can see or contest.
    """

    left_id: str
    right_id: str
    readings: Mapping[str, DimensionReading]

    def __post_init__(self) -> None:
        missing = [d for d in SIMILARITY_DIMENSIONS if d not in self.readings]
        if missing:
            raise SimilarityError("vector is missing dimensions: " + ", ".join(missing))
        extra = [d for d in self.readings if d not in SIMILARITY_DIMENSIONS]
        if extra:
            raise SimilarityError("vector has unknown dimensions: " + ", ".join(extra))

    def __getitem__(self, dimension: str) -> float:
        return self.readings[dimension].value

    def reading(self, dimension: str) -> DimensionReading:
        if dimension not in self.readings:
            raise SimilarityError(f"unknown dimension {dimension!r}")
        return self.readings[dimension]

    def values(self) -> dict[str, float]:
        return {name: self.readings[name].value for name in SIMILARITY_DIMENSIONS}

    def available_dimensions(self) -> tuple[str, ...]:
        return tuple(
            name for name in SIMILARITY_DIMENSIONS if self.readings[name].available
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "vector": self.values(),
            "readings": {
                name: self.readings[name].as_dict() for name in SIMILARITY_DIMENSIONS
            },
            "note": (
                "a similarity vector is not collapsed into a single score; select a "
                "profile for the task at hand"
            ),
        }

    def render(self) -> str:
        parts = []
        for name in SIMILARITY_DIMENSIONS:
            item = self.readings[name]
            parts.append(f"{name}={item.value:.3f}" + ("" if item.available else " (n/a)"))
        return f"{self.left_id} vs {self.right_id}: " + " ".join(parts)


@dataclass(frozen=True, slots=True)
class SimilarityProfile:
    """A named task-specific reading of the vector.

    Weights must sum to 1.0 so a profile value is comparable across profiles,
    and every profile documents which question it answers.
    """

    name: str
    weights: Mapping[str, float]
    question: str
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SimilarityError("profile name must be non-empty")
        for dimension in self.weights:
            if dimension not in SIMILARITY_DIMENSIONS:
                raise SimilarityError(f"profile names unknown dimension {dimension!r}")
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-9:
            raise SimilarityError(
                f"profile {self.name!r} weights must sum to 1.0, got {total!r}"
            )
        if not self.question.strip():
            raise SimilarityError("profile must state the question it answers")

    def project(self, vector: SimilarityVector) -> float:
        """Collapse the vector *for this profile only*.

        Unavailable dimensions are excluded and the remaining weights are
        renormalised, so a missing measurement dilutes the result rather than
        silently dragging it toward zero.
        """

        usable = {
            dimension: weight
            for dimension, weight in self.weights.items()
            if weight > 0.0 and vector.reading(dimension).available
        }
        if not usable:
            raise SimilarityError(
                f"profile {self.name!r} cannot be applied: no weighted dimension is "
                "available for this pair"
            )
        total = sum(usable.values())
        projected = sum(
            vector.reading(dimension).value * weight for dimension, weight in usable.items()
        )
        return _round(projected / total)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "weights": {k: v for k, v in sorted(self.weights.items())},
            "question": self.question,
            "notes": self.notes,
        }


#: For grouping images that share an *arrangement*.
TEMPLATE_PROFILE = SimilarityProfile(
    name="template",
    weights={"structural": 0.6, "composition": 0.4, "style": 0.0, "asset": 0.0},
    question="is this the same arrangement?",
    notes="style and asset are zero-weighted: the same layout with different colours is still the same template",
)

#: For grouping images that share a *visual voice*.
CREATOR_STYLE_PROFILE = SimilarityProfile(
    name="creator_style",
    weights={"style": 0.55, "composition": 0.35, "structural": 0.1, "asset": 0.0},
    question="is this the same visual voice?",
    notes="structural is near-zero-weighted: a creator varies layout more freely than palette and hierarchy",
)

#: For a general reading with no task preference.
BALANCED_PROFILE = SimilarityProfile(
    name="balanced",
    weights={"structural": 0.3, "composition": 0.3, "style": 0.25, "asset": 0.15},
    question="how alike are these overall?",
    notes="provided for reporting; prefer a task-specific profile when one applies",
)

#: All shipped profiles, by name.
PROFILES: Mapping[str, SimilarityProfile] = {
    TEMPLATE_PROFILE.name: TEMPLATE_PROFILE,
    CREATOR_STYLE_PROFILE.name: CREATOR_STYLE_PROFILE,
    BALANCED_PROFILE.name: BALANCED_PROFILE,
}


# --------------------------------------------------------------------------
# Dimension computations
# --------------------------------------------------------------------------


def _structural_dimension(
    left: VisualGrammar, right: VisualGrammar
) -> DimensionReading:
    """Region presence and coarse placement agreement."""

    left_types = frozenset(region.region_type for region in left.regions)
    right_types = frozenset(region.region_type for region in right.regions)
    presence = _jaccard(left_types, right_types)

    left_sig = frozenset(left.structural_signature())
    right_sig = frozenset(right.structural_signature())
    placement = _jaccard(left_sig, right_sig)

    value = _PRESENCE_WEIGHT * presence + _PLACEMENT_WEIGHT * placement
    return DimensionReading(
        dimension="structural",
        value=_round(value),
        detail={
            "region_type_presence": _round(presence),
            "placement_agreement": _round(placement),
            "shared_region_types": sorted(left_types & right_types),
            "only_left": sorted(left_types - right_types),
            "only_right": sorted(right_types - left_types),
        },
    )


def _style_dimension(
    left: StructuralObservation, right: StructuralObservation
) -> DimensionReading:
    """Typography, density, and palette agreement from the observation.

    Every component falls back to a neutral 0.5 when a side did not declare it,
    matching M2's treatment of "not declared" as weaker evidence than "agrees"
    rather than as disagreement.
    """

    if left.palette_relation and right.palette_relation:
        palette = 1.0 if left.palette_relation == right.palette_relation else 0.0
    elif left.palette_relation is None and right.palette_relation is None:
        palette = 0.5
    else:
        palette = 0.5

    if left.density and right.density:
        density = 1.0 if left.density == right.density else 0.0
    else:
        density = 0.5

    if left.type_scale_relation and right.type_scale_relation:
        typography = (
            1.0 if left.type_scale_relation == right.type_scale_relation else 0.0
        )
    else:
        typography = 0.5

    value = (
        _COLOUR_WEIGHT * typography
        + _DENSITY_WEIGHT * density
        + _PALETTE_WEIGHT * palette
    )
    return DimensionReading(
        dimension="style",
        value=_round(value),
        detail={
            "typography_agreement": _round(typography),
            "density_agreement": _round(density),
            "palette_agreement": _round(palette),
        },
    )


def _composition_dimension(
    left: VisualGrammar, right: VisualGrammar
) -> DimensionReading:
    """Relation and attention-flow agreement — the grammar layer."""

    relation_overlap = _jaccard(left.relation_types(), right.relation_types())

    left_attention = left.attention_signature()
    right_attention = right.attention_signature()
    if not left_attention and not right_attention:
        attention = 1.0
    elif not left_attention or not right_attention:
        attention = 0.0
    else:
        # Position-wise agreement, so a reordered flow is penalised even when the
        # same stages are present.
        matches = sum(
            1
            for index, stage in enumerate(left_attention)
            if index < len(right_attention) and right_attention[index] == stage
        )
        attention = matches / max(len(left_attention), len(right_attention))

    value = _RELATION_WEIGHT * relation_overlap + _ATTENTION_WEIGHT * attention
    return DimensionReading(
        dimension="composition",
        value=_round(value),
        detail={
            "relation_overlap": _round(relation_overlap),
            "attention_agreement": _round(attention),
            "left_relations": sorted(left.relation_types()),
            "right_relations": sorted(right.relation_types()),
            "left_attention": list(left_attention),
            "right_attention": list(right_attention),
        },
    )


def _asset_dimension(
    left: StructuralObservation, right: StructuralObservation
) -> DimensionReading:
    """Subject class, placement, and chart type agreement."""

    if left.subject_class and right.subject_class:
        subject = 1.0 if left.subject_class == right.subject_class else 0.0
    else:
        subject = 0.5

    if left.placement and right.placement:
        placement = 1.0 if left.placement == right.placement else 0.0
    else:
        placement = 0.5

    if left.chart_class and right.chart_class:
        chart = 1.0 if left.chart_class == right.chart_class else 0.0
    elif left.chart_class is None and right.chart_class is None:
        chart = 0.5
    else:
        chart = 0.5

    value = (
        _SUBJECT_WEIGHT * subject
        + _PLACEMENT_WEIGHT_ASSET * placement
        + _CHART_WEIGHT * chart
    )
    return DimensionReading(
        dimension="asset",
        value=_round(value),
        detail={
            "subject_class_agreement": _round(subject),
            "placement_agreement": _round(placement),
            "chart_agreement": _round(chart),
        },
    )


def vector_similarity(
    left_grammar: VisualGrammar,
    right_grammar: VisualGrammar,
    *,
    left_observation: StructuralObservation,
    right_observation: StructuralObservation,
) -> SimilarityVector:
    """Compare two grammars and their source observations across four dimensions.

    Observations are required alongside grammars because style and asset facts
    are properties of the *image*, not of its arrangement, and the grammar
    deliberately does not carry them.
    """

    if left_grammar.source_id != left_observation.source_id:
        raise SimilarityError(
            f"grammar {left_grammar.grammar_id!r} does not belong to observation "
            f"{left_observation.source_id!r}"
        )
    if right_grammar.source_id != right_observation.source_id:
        raise SimilarityError(
            f"grammar {right_grammar.grammar_id!r} does not belong to observation "
            f"{right_observation.source_id!r}"
        )

    readings = {
        "structural": _structural_dimension(left_grammar, right_grammar),
        "style": _style_dimension(left_observation, right_observation),
        "composition": _composition_dimension(left_grammar, right_grammar),
        "asset": _asset_dimension(left_observation, right_observation),
    }
    return SimilarityVector(
        left_id=left_grammar.source_id,
        right_id=right_grammar.source_id,
        readings=readings,
    )


def vector_matrix(
    grammars: Sequence[VisualGrammar],
    observations: Mapping[str, StructuralObservation],
) -> dict[tuple[str, str], SimilarityVector]:
    """Every unordered pair, keyed in sorted id order so the matrix is stable."""

    ordered = sorted(grammars, key=lambda grammar: grammar.source_id)
    ids = [grammar.source_id for grammar in ordered]
    duplicates = sorted({sid for sid in ids if ids.count(sid) > 1})
    if duplicates:
        raise SimilarityError("duplicate grammar source ids: " + ", ".join(duplicates))

    matrix: dict[tuple[str, str], SimilarityVector] = {}
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if left.source_id not in observations or right.source_id not in observations:
                raise SimilarityError(
                    "every grammar needs its source observation to compute style and "
                    "asset dimensions"
                )
            matrix[(left.source_id, right.source_id)] = vector_similarity(
                left,
                right,
                left_observation=observations[left.source_id],
                right_observation=observations[right.source_id],
            )
    return matrix


def profile_scores(
    matrix: Mapping[tuple[str, str], SimilarityVector],
    profile: SimilarityProfile,
) -> dict[tuple[str, str], float]:
    """Project a whole matrix through one profile."""

    return {
        key: profile.project(vector) for key, vector in sorted(matrix.items())
    }


__all__ = [
    "BALANCED_PROFILE",
    "CREATOR_STYLE_PROFILE",
    "PROFILES",
    "SCORE_PRECISION",
    "SIMILARITY_DIMENSIONS",
    "TEMPLATE_PROFILE",
    "UNAVAILABLE",
    "DimensionReading",
    "SimilarityError",
    "SimilarityProfile",
    "SimilarityVector",
    "profile_scores",
    "vector_matrix",
    "vector_similarity",
]
