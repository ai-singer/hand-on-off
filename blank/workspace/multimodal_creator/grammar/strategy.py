"""Creator strategy pattern distillation v2 (Phase M4, phase 4).

M3's pattern extraction had a structural flaw named in the phase brief: it read
the **cluster label** — the dominant layout class — as its summary. That made the
pattern a restatement of the clustering rather than an independent description of
what the creator does, and it inherited every one of the layout classifier's
errors (M3 micro F1 ≈ 0.33).

v2 derives strategy from the **grammar and invariants**, which carry no label:

* ``attention_strategy`` — how the composition opens and where it goes
* ``information_hierarchy`` — the order the message is delivered in
* ``composition_strategy`` — the arrangement moves that recur

and it emits **strategy, never material**. The brief's examples are explicit:
not ``"red background"`` and not ``"same image"``. A test asserts that no colour
value, pixel reference, asset path, or image identifier can appear in a
serialised pattern.

The dependency direction is now::

    grammars + invariants ──▶ CreatorStrategyPattern

instead of::

    cluster label ──▶ pattern
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .invariants import Invariant, InvariantSet
from .model import ATTENTION_STAGES, VisualGrammar

#: Attention strategies, decided by which stage leads.
ATTENTION_STRATEGIES: tuple[str, ...] = (
    "subject_first",
    "headline_first",
    "data_first",
    "action_first",
    "undetermined",
)

#: Information hierarchy stages, in delivery order.
HIERARCHY_STAGES: tuple[str, ...] = ("hook", "explanation", "evidence", "action")

#: Composition moves the extractor can express.
COMPOSITION_MOVES: tuple[str, ...] = (
    "central_subject",
    "offset_subject",
    "full_bleed_subject",
    "top_entry",
    "bottom_anchor",
    "overlay_headline",
    "split_columns",
    "stacked_information",
    "centred_information",
)

#: Region type that satisfies each hierarchy stage.
_STAGE_SOURCES: Mapping[str, tuple[str, ...]] = {
    "hook": ("headline", "subtitle"),
    "explanation": ("supporting_information",),
    "evidence": ("data_display",),
    "action": ("cta", "branding"),
}

#: Support fraction a feature needs before it becomes part of the strategy.
DEFAULT_STRATEGY_SUPPORT = 0.7


class StrategyError(Exception):
    """Raised when a strategy pattern cannot be distilled."""


@dataclass(frozen=True, slots=True)
class CreatorStrategyPattern:
    """An abstracted description of *how* a creator composes.

    Carries no colour values, no image identifiers, and no asset references —
    only strategy vocabulary. The type cannot hold material even if a caller
    wanted it to, which is what makes the no-copy guarantee structural.
    """

    pattern_id: str
    cluster_id: str
    attention_strategy: str
    information_hierarchy: tuple[str, ...]
    composition_strategy: tuple[str, ...]
    invariants: tuple[Invariant, ...]
    support: int
    creator_ids: tuple[str, ...]
    confidence: float
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.attention_strategy not in ATTENTION_STRATEGIES:
            raise StrategyError(
                f"unknown attention_strategy {self.attention_strategy!r}"
            )
        for stage in self.information_hierarchy:
            if stage not in HIERARCHY_STAGES:
                raise StrategyError(f"unknown hierarchy stage {stage!r}")
        ordered = [s for s in HIERARCHY_STAGES if s in self.information_hierarchy]
        if list(self.information_hierarchy) != ordered:
            raise StrategyError(
                f"information_hierarchy must follow delivery order "
                f"{HIERARCHY_STAGES!r}, got {self.information_hierarchy!r}"
            )
        for move in self.composition_strategy:
            if move not in COMPOSITION_MOVES:
                raise StrategyError(f"unknown composition move {move!r}")
        if not 0.0 <= self.confidence <= 1.0:
            raise StrategyError("confidence must be within 0..1")

    def invariant_features(self) -> tuple[str, ...]:
        return tuple(item.feature for item in self.invariants)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "cluster_id": self.cluster_id,
            "attention_strategy": self.attention_strategy,
            "information_hierarchy": list(self.information_hierarchy),
            "composition_strategy": list(self.composition_strategy),
            "invariants": [item.as_dict() for item in self.invariants],
            "support": self.support,
            "creator_ids": list(self.creator_ids),
            "confidence": self.confidence,
            "evidence": dict(self.evidence),
        }

    def render(self) -> str:
        return (
            f"{self.pattern_id}: attention={self.attention_strategy} "
            f"hierarchy=[{' > '.join(self.information_hierarchy)}] "
            f"composition=[{', '.join(self.composition_strategy)}] "
            f"support={self.support} confidence={self.confidence:.2f}"
        )


def _attention_strategy(grammars: Sequence[VisualGrammar]) -> tuple[str, float]:
    """Which stage leads, by majority — mined, not assigned.

    A leading ``subtitle`` counts as a headline lead: both are the text entry
    point, and M3's observer legitimately types a short top band as either. Not
    folding them together would make the strategy depend on an observer decision
    that carries no strategic difference.
    """

    counts: dict[str, int] = {}
    for grammar in grammars:
        signature = grammar.attention_signature()
        if not signature:
            counts["undetermined"] = counts.get("undetermined", 0) + 1
            continue
        lead = signature[0].split(":", 1)[1]
        strategy = {
            "subject": "subject_first",
            "headline": "headline_first",
            "subtitle": "headline_first",
            "data_display": "data_first",
            "cta": "action_first",
        }.get(lead, "undetermined")
        counts[strategy] = counts.get(strategy, 0) + 1

    if not counts:
        return "undetermined", 0.0
    best = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return best[0], round(best[1] / len(grammars), 6)


def _information_hierarchy(
    grammars: Sequence[VisualGrammar], *, support: float
) -> tuple[str, ...]:
    """Which delivery stages recur, in canonical order.

    ``hook`` requires text near the top of the frame, not merely a headline-typed
    region. A composition whose text sits at the bottom has no entry hook — the
    subject leads and the text explains — and claiming one would be inventing a
    stage the geometry does not support.
    """

    threshold = max(1, int(len(grammars) * support))
    counts: dict[str, int] = {stage: 0 for stage in HIERARCHY_STAGES}

    for grammar in grammars:
        types = {region.region_type for region in grammar.regions}
        lead_types = _STAGE_SOURCES["hook"]
        has_top_text = any(
            region.region_type in lead_types and region.position_band == "top"
            for region in grammar.regions
        )
        if has_top_text:
            counts["hook"] += 1
        if types & set(_STAGE_SOURCES["explanation"]):
            counts["explanation"] += 1
        if types & set(_STAGE_SOURCES["evidence"]):
            counts["evidence"] += 1
        if types & set(_STAGE_SOURCES["action"]):
            counts["action"] += 1

    kept = {stage for stage, count in counts.items() if count >= threshold}
    return tuple(stage for stage in HIERARCHY_STAGES if stage in kept)


def _composition_strategy(
    grammars: Sequence[VisualGrammar], *, support: float
) -> tuple[str, ...]:
    """Arrangement moves that recur across the cluster's grammars."""

    threshold = max(1, int(len(grammars) * support))
    move_counts: dict[str, int] = {}

    for grammar in grammars:
        relations = grammar.relation_types()
        moves: set[str] = set()
        if "subject_center_focus" in relations:
            moves.add("central_subject")
        if "subject_offset_focus" in relations:
            moves.add("offset_subject")
        if "subject_full_bleed" in relations:
            moves.add("full_bleed_subject")
        if "headline_overlay_subject" in relations:
            moves.add("overlay_headline")
        if "cta_bottom_anchor" in relations:
            moves.add("bottom_anchor")

        for region in grammar.regions:
            if region.position_band == "top" and region.region_type in {
                "headline",
                "subtitle",
            }:
                moves.add("top_entry")
            if region.position_band == "center" and region.column_band == "mid":
                if region.region_type in {"supporting_information", "headline"}:
                    moves.add("centred_information")

        columns = {
            region.column_band
            for region in grammar.regions
            if region.region_type
            in {"supporting_information", "subject", "data_display"}
        }
        if len(columns) >= 2:
            moves.add("split_columns")

        supporting = [r for r in grammar.regions if r.region_type == "supporting_information"]
        if len(supporting) >= 2:
            moves.add("stacked_information")

        for move in moves:
            move_counts[move] = move_counts.get(move, 0) + 1

    kept = {move for move, count in move_counts.items() if count >= threshold}
    return tuple(move for move in COMPOSITION_MOVES if move in kept)


def distill_strategy(
    grammars: Sequence[VisualGrammar],
    invariant_set: InvariantSet,
    *,
    creator_ids: Sequence[str] = (),
    support: float = DEFAULT_STRATEGY_SUPPORT,
) -> CreatorStrategyPattern:
    """Distil strategy from grammars and their invariants.

    ``invariant_set`` supplies the frequencies; the grammars supply the
    structure. Neither supplies a layout label, which is the whole point of v2.
    """

    if not grammars:
        raise StrategyError("cannot distil a strategy from no grammars")
    if not 0.0 < support <= 1.0:
        raise StrategyError("support must be within (0, 1]")
    if invariant_set.member_count != len(grammars):
        raise StrategyError(
            f"invariant set covers {invariant_set.member_count} members but "
            f"{len(grammars)} grammars were supplied; they must describe the same cluster"
        )

    attention, attention_support = _attention_strategy(grammars)
    hierarchy = _information_hierarchy(grammars, support=support)
    composition = _composition_strategy(grammars, support=support)

    creators = tuple(sorted(set(creator_ids)))
    # Confidence blends how strongly the attention lead dominates with how much
    # agreement the invariant set achieved, and how much creator diversity backs
    # it. A pattern seen once by one creator is weak however clean it looks.
    invariant_strength = (
        sum(item.frequency for item in invariant_set.invariants)
        / len(invariant_set.invariants)
        if invariant_set.invariants
        else 0.0
    )
    diversity = min(1.0, len(creators) / 3.0) if creators else 0.5
    confidence = round(
        min(1.0, 0.4 * attention_support + 0.4 * invariant_strength + 0.2 * diversity),
        6,
    )

    return CreatorStrategyPattern(
        pattern_id=f"strategy-{invariant_set.cluster_id}",
        cluster_id=invariant_set.cluster_id,
        attention_strategy=attention,
        information_hierarchy=hierarchy,
        composition_strategy=composition,
        invariants=tuple(
            sorted(invariant_set.invariants, key=lambda item: (-item.frequency, item.key))
        ),
        support=len(grammars),
        creator_ids=creators,
        confidence=confidence,
        evidence={
            "attention_support": attention_support,
            "invariant_threshold": invariant_set.threshold,
            "invariant_count": len(invariant_set.invariants),
            "distinct_feature_count": len(invariant_set.all_features),
            "strategy_support": support,
            "derived_from": "grammar+invariants",
            "layout_label_used": False,
        },
    )


def render_strategies(patterns: Sequence[CreatorStrategyPattern]) -> str:
    if not patterns:
        return "no strategy patterns distilled"
    lines = [f"creator strategy patterns: {len(patterns)}"]
    for pattern in patterns:
        lines.append("  " + pattern.render())
    return "\n".join(lines)


__all__ = [
    "ATTENTION_STRATEGIES",
    "COMPOSITION_MOVES",
    "DEFAULT_STRATEGY_SUPPORT",
    "HIERARCHY_STAGES",
    "CreatorStrategyPattern",
    "StrategyError",
    "distill_strategy",
    "render_strategies",
]
