"""Visual Grammar model (Phase M4, phase 2).

M3 established that a **layout class label cannot express complex visual
structure**: its classifier reached micro F1 ≈ 0.33, because a single label must
throw away everything that makes a composition what it is. M4 stops trying to
improve the label and replaces the representation instead.

A :class:`VisualGrammar` is a structured description of how one image is built:

* **regions** — what the composition is made of, each with position, size,
  density and dominance rank,
* **relationships** — how those regions stand to each other
  (``headline_above_subject``, ``subject_center_focus``, ``cta_bottom_anchor``),
* **attention_flow** — the order in which a viewer is led through them.

The three layers are deliberately separate. A label collapses them; a grammar
keeps them, which is what lets later phases distinguish *template* similarity
from *creator style* similarity instead of blending both into one number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

#: Grammar region types. Coarser than the M1 region-role vocabulary and chosen
#: for *function* rather than appearance: what a region does in the composition.
REGION_TYPES: tuple[str, ...] = (
    "headline",
    "subtitle",
    "subject",
    "supporting_information",
    "data_display",
    "cta",
    "branding",
    "background",
)

#: Vertical thirds a region can occupy.
POSITION_BANDS: tuple[str, ...] = ("top", "center", "bottom")

#: Horizontal thirds. Named ``mid`` rather than ``center`` so that a column band
#: and a position band can never be confused for one another in a grammar dump.
COLUMN_BANDS: tuple[str, ...] = ("left", "mid", "right")

#: How much of its own bounding box a region fills.
DENSITY_LEVELS: tuple[str, ...] = ("sparse", "moderate", "dense")

#: Ordinal dominance rank, first being most dominant.
DOMINANCE_RANKS: tuple[str, ...] = ("primary", "secondary", "tertiary", "background")

#: Relationship vocabulary. Every name is directional and machine-readable.
RELATION_TYPES: tuple[str, ...] = (
    "headline_above_subject",
    "headline_below_subject",
    "headline_overlay_subject",
    "subject_center_focus",
    "subject_offset_focus",
    "subject_full_bleed",
    "cta_bottom_anchor",
    "cta_top_anchor",
    "branding_corner",
    "support_below_headline",
    "support_beside_subject",
    "data_above_caption",
    "data_below_headline",
    "background_encloses_all",
    "high_contrast_boundary",
    "low_contrast_blend",
)

#: Attention-flow stages.
ATTENTION_STAGES: tuple[str, ...] = (
    "entrance_point",
    "primary_focus",
    "secondary_information",
    "action_area",
)

#: Grammar contract version, recorded on every grammar.
GRAMMAR_VERSION = "m4.0.0"


class GrammarError(Exception):
    """Raised when a grammar cannot be built or is internally inconsistent."""


@dataclass(frozen=True, slots=True)
class GrammarRegion:
    """One functional region of a composition.

    ``dominance`` is an ordinal rank, not a score: the contract records *how
    regions order*, which is comparable and arguable, rather than inventing a
    salience number that cannot be checked.
    """

    region_id: str
    region_type: str
    position_band: str
    column_band: str
    width_share: float
    height_share: float
    area_share: float
    density: str
    dominance: str
    layer_order: int
    position_center: tuple[float, float]

    def __post_init__(self) -> None:
        if self.region_type not in REGION_TYPES:
            raise GrammarError(f"unknown region_type {self.region_type!r}")
        if self.position_band not in POSITION_BANDS:
            raise GrammarError(f"unknown position_band {self.position_band!r}")
        if self.column_band not in COLUMN_BANDS:
            raise GrammarError(f"unknown column_band {self.column_band!r}")
        if self.density not in DENSITY_LEVELS:
            raise GrammarError(f"unknown density {self.density!r}")
        if self.dominance not in DOMINANCE_RANKS:
            raise GrammarError(f"unknown dominance {self.dominance!r}")
        for name in ("width_share", "height_share", "area_share"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise GrammarError(f"{name} must be within 0..1, got {value!r}")
        cx, cy = self.position_center
        if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0):
            raise GrammarError(f"position_center must be normalized, got {self.position_center!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "region_type": self.region_type,
            "position_band": self.position_band,
            "column_band": self.column_band,
            "width_share": self.width_share,
            "height_share": self.height_share,
            "area_share": self.area_share,
            "density": self.density,
            "dominance": self.dominance,
            "layer_order": self.layer_order,
            "position_center": list(self.position_center),
        }


@dataclass(frozen=True, slots=True)
class GrammarRelation:
    """A directional structural relation between two grammar regions."""

    relation_id: str
    relation_type: str
    source_region_id: str
    target_region_id: str
    strength: float
    rationale: str

    def __post_init__(self) -> None:
        if self.relation_type not in RELATION_TYPES:
            raise GrammarError(f"unknown relation_type {self.relation_type!r}")
        if not 0.0 <= self.strength <= 1.0:
            raise GrammarError(f"relation strength must be within 0..1, got {self.strength!r}")
        if not self.source_region_id or not self.target_region_id:
            raise GrammarError("a relation needs both endpoints")

    def as_dict(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "relation_type": self.relation_type,
            "source_region_id": self.source_region_id,
            "target_region_id": self.target_region_id,
            "strength": self.strength,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class AttentionFlow:
    """The order a viewer is led through the composition.

    ``stages`` is a subsequence of :data:`ATTENTION_STAGES`, and each entry maps
    a stage to the region that occupies it. A composition with no action area
    simply has no ``action_area`` entry rather than an empty one.
    """

    stages: tuple[str, ...]
    assignments: Mapping[str, str]

    def __post_init__(self) -> None:
        for stage in self.stages:
            if stage not in ATTENTION_STAGES:
                raise GrammarError(f"unknown attention stage {stage!r}")
        for stage in self.assignments:
            if stage not in ATTENTION_STAGES:
                raise GrammarError(f"unknown attention stage {stage!r}")
        ordered = [stage for stage in ATTENTION_STAGES if stage in self.stages]
        if list(self.stages) != ordered:
            raise GrammarError(
                f"attention stages must follow the canonical order {ATTENTION_STAGES!r}, "
                f"got {self.stages!r}"
            )

    def region_for(self, stage: str) -> str | None:
        return self.assignments.get(stage)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stages": list(self.stages),
            "assignments": dict(self.assignments),
        }


@dataclass(frozen=True, slots=True)
class VisualGrammar:
    """Structured description of how one composition is built."""

    grammar_id: str
    source_id: str
    regions: tuple[GrammarRegion, ...]
    relationships: tuple[GrammarRelation, ...]
    attention_flow: AttentionFlow
    evidence_source: str
    confidence: float
    version: str = GRAMMAR_VERSION
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.grammar_id.strip():
            raise GrammarError("grammar_id must be non-empty")
        if not self.source_id.strip():
            raise GrammarError("source_id must be non-empty")
        if not self.regions:
            raise GrammarError("a grammar must contain at least one region")
        if not 0.0 <= self.confidence <= 1.0:
            raise GrammarError("confidence must be within 0..1")

        ids = [region.region_id for region in self.regions]
        duplicates = sorted({rid for rid in ids if ids.count(rid) > 1})
        if duplicates:
            raise GrammarError("duplicate region ids: " + ", ".join(duplicates))
        known = set(ids)

        for relation in self.relationships:
            for endpoint in (relation.source_region_id, relation.target_region_id):
                if endpoint not in known:
                    raise GrammarError(
                        f"relation {relation.relation_id!r} references unknown region "
                        f"{endpoint!r}"
                    )
        for stage, region_id in self.attention_flow.assignments.items():
            if region_id not in known:
                raise GrammarError(
                    f"attention stage {stage!r} references unknown region {region_id!r}"
                )

    # -- views -------------------------------------------------------------

    def region(self, region_id: str) -> GrammarRegion:
        for item in self.regions:
            if item.region_id == region_id:
                return item
        raise GrammarError(f"no region {region_id!r} in grammar {self.grammar_id!r}")

    def by_type(self, region_type: str) -> tuple[GrammarRegion, ...]:
        return tuple(r for r in self.regions if r.region_type == region_type)

    def relation_types(self) -> frozenset[str]:
        return frozenset(r.relation_type for r in self.relationships)

    def dominant_region(self) -> GrammarRegion:
        for rank in DOMINANCE_RANKS:
            for item in self.regions:
                if item.dominance == rank:
                    return item
        return self.regions[0]

    def attention_signature(self) -> tuple[str, ...]:
        """Attention stages paired with the region type occupying each."""

        signature: list[str] = []
        for stage in self.attention_flow.stages:
            region_id = self.attention_flow.region_for(stage)
            if region_id is None:
                continue
            signature.append(f"{stage}:{self.region(region_id).region_type}")
        return tuple(signature)

    def structural_signature(self) -> tuple[str, ...]:
        """Region types with their coarse placement, sorted for comparison.

        Sorted deliberately: this signature expresses *what the composition
        contains and roughly where*, independent of declaration order, so two
        grammars describing the same structure compare equal.
        """

        return tuple(
            sorted(
                f"{item.region_type}@{item.position_band}/{item.column_band}"
                for item in self.regions
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "grammar_id": self.grammar_id,
            "source_id": self.source_id,
            "version": self.version,
            "evidence_source": self.evidence_source,
            "confidence": self.confidence,
            "regions": [region.as_dict() for region in self.regions],
            "relationships": [relation.as_dict() for relation in self.relationships],
            "attention_flow": self.attention_flow.as_dict(),
            "attention_signature": list(self.attention_signature()),
            "structural_signature": list(self.structural_signature()),
            "notes": list(self.notes),
        }

    def render(self) -> str:
        lines = [
            f"grammar {self.grammar_id} ({self.source_id}) "
            f"evidence={self.evidence_source} confidence={self.confidence:.2f}",
            "  regions:",
        ]
        for region in self.regions:
            lines.append(
                f"    {region.region_type:<22} {region.position_band}/{region.column_band} "
                f"area={region.area_share:.2f} density={region.density:<9} "
                f"dominance={region.dominance}"
            )
        lines.append("  relationships:")
        for relation in self.relationships:
            lines.append(
                f"    {relation.relation_type:<28} "
                f"{relation.source_region_id} -> {relation.target_region_id} "
                f"({relation.strength:.2f})"
            )
        lines.append("  attention flow: " + " -> ".join(self.attention_signature()))
        return "\n".join(lines)


def band_of(value: float) -> str:
    """Map a normalized coordinate onto a generic third: low / center / high.

    Deliberately *not* used for column bands. Position and column vocabularies are
    distinct on purpose — a column band reads ``left``/``mid``/``right``, a
    position band reads ``top``/``center``/``bottom`` — so this helper is only for
    callers that want a neutral third name.
    """

    if value < 1.0 / 3.0:
        return "low"
    if value < 2.0 / 3.0:
        return "center"
    return "high"


def position_band_of(value: float) -> str:
    """Map a normalized vertical coordinate onto :data:`POSITION_BANDS`."""

    if value < 1.0 / 3.0:
        return "top"
    if value < 2.0 / 3.0:
        return "center"
    return "bottom"


def column_band_of(value: float) -> str:
    """Map a normalized horizontal coordinate onto :data:`COLUMN_BANDS`."""

    if value < 1.0 / 3.0:
        return "left"
    if value < 2.0 / 3.0:
        return "mid"
    return "right"


__all__ = [
    "ATTENTION_STAGES",
    "COLUMN_BANDS",
    "DENSITY_LEVELS",
    "DOMINANCE_RANKS",
    "GRAMMAR_VERSION",
    "POSITION_BANDS",
    "REGION_TYPES",
    "RELATION_TYPES",
    "AttentionFlow",
    "GrammarError",
    "GrammarRegion",
    "GrammarRelation",
    "VisualGrammar",
    "band_of",
    "column_band_of",
    "position_band_of",
]
