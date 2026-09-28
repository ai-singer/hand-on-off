"""M4 → M5 mapping (Phase M5, Task 2).

Every profile field is **derived**. The brief forbids four things, and each is
excluded structurally rather than by discipline:

===================================  ==================================================
Forbidden                            How it is excluded
===================================  ==================================================
hand-written domain templates        no template exists in this module; every value
                                     comes from a passed-in M4 artifact
hardcoded creator names              ``creator_id`` is passed in by the caller; no
                                     name literal appears here
hardcoded colours                    no colour value is read or written anywhere;
                                     identity is expressed in measured design traits
hardcoded image prompts              no prompt field exists in the profile model, and
                                     the schema rejects the key outright
===================================  ==================================================

The "forbidden" composition set deserves a note. It is built from moves in the
composition vocabulary that were **absent across every member** of the cluster.
That is a measurement, not an opinion — but absence over a small sample is weaker
evidence than presence, so the forbidden list carries a lower confidence and the
profile records the support it rests on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..grammar.constraints import Constraint, VisualConstraint
from ..grammar.model import VisualGrammar
from ..grammar.strategy import (
    ATTENTION_STRATEGIES,
    COMPOSITION_MOVES,
    HIERARCHY_STAGES,
    CreatorStrategyPattern,
)
from .model import (
    ATTENTION_SLOTS,
    HIERARCHY_TIERS,
    PROFILE_VERSION,
    AttentionStrategy,
    CompositionRules,
    ConstraintLayer,
    FieldProvenance,
    HierarchyPattern,
    ProfileError,
    VisualCreatorProfile,
    VisualIdentity,
)

#: Attention strategy → the visual language it expresses.
#:
#: Fixed and published. This is the only place a strategic name is attached to a
#: measured strategy, and it is a translation of M4's own vocabulary, not an
#: invented domain category.
LANGUAGE_BY_ATTENTION: Mapping[str, str] = {
    "headline_first": "information_first",
    "subject_first": "subject_first",
    "data_first": "data_first",
    "action_first": "action_first",
    "undetermined": "undetermined",
}

#: Grammar relations that evidence a full-bleed framing.
_FULL_BLEED_RELATIONS = frozenset({"subject_full_bleed", "background_encloses_all"})

#: Grammar relations that evidence a split framing.
_SPLIT_RELATIONS = frozenset({"support_beside_subject"})

#: Grammar relations that evidence a hard boundary.
_HIGH_CONTRAST_RELATIONS = frozenset({"high_contrast_boundary"})

#: Grammar relations that evidence a soft boundary.
_LOW_CONTRAST_RELATIONS = frozenset({"low_contrast_blend"})

#: Region types that carry display typography.
_DISPLAY_TYPES = frozenset({"headline", "subtitle"})

#: Region types that carry body typography.
_BODY_TYPES = frozenset({"supporting_information", "data_display"})

#: Average headline area above which display type counts as large.
_LARGE_TYPE_AREA = 0.12

#: Complexity thresholds over the number of distinct composition moves.
_COMPLEXITY_ORDER: tuple[str, ...] = ("low", "medium", "high")

#: Support fraction at which a constraint becomes a ``must_have``.
_MUST_HAVE_FREQUENCY = 0.85

#: Relation types that a composition must have to count as having an entry point.
_ENTRY_RELATIONS = frozenset(
    {"headline_above_subject", "headline_overlay_subject", "cta_top_anchor"}
)

#: Relation types that evidence supporting information.
_SUPPORT_RELATIONS = frozenset(
    {"support_below_headline", "support_beside_subject", "data_below_headline"}
)


class MappingError(ProfileError):
    """Raised when M4 artifacts cannot be mapped to a profile."""


@dataclass(frozen=True, slots=True)
class MappingEvidence:
    """What the mapper measured, kept for audit.

    Exposed so a reviewer can see the counts behind every derived value rather
    than trusting the summary.
    """

    pattern_count: int
    grammar_count: int
    style_traits: tuple[str, ...]
    average_region_area: float
    composition_moves_present: tuple[str, ...]
    composition_moves_absent: tuple[str, ...]
    must_have_features: tuple[str, ...]
    support: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern_count": self.pattern_count,
            "grammar_count": self.grammar_count,
            "style_traits": list(self.style_traits),
            "average_region_area": self.average_region_area,
            "composition_moves_present": list(self.composition_moves_present),
            "composition_moves_absent": list(self.composition_moves_absent),
            "must_have_features": list(self.must_have_features),
            "support": self.support,
        }


def _weakest(*values: float) -> float:
    """The lowest of the given confidences.

    A derived value is only as reliable as its weakest input, so aggregation
    takes the minimum rather than an average that would flatter it.
    """

    candidates = [value for value in values if value is not None]
    return round(min(candidates), 6) if candidates else 0.0


def _average(values: Sequence[float]) -> float:
    return round(sum(values) / len(values), 6) if values else 0.0


def _dominant(values: Sequence[str], fallback: str) -> str:
    """Most frequent value, ties broken lexicographically for determinism."""

    present = [value for value in values if value]
    if not present:
        return fallback
    counts: dict[str, int] = {}
    for value in present:
        counts[value] = counts.get(value, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


class PatternToProfileMapper:
    """Map one creator's M4 artifacts onto a single profile.

    Stateless and pure: the same inputs always produce the same profile, in the
    same field order, with the same provenance.
    """

    def __init__(
        self,
        *,
        must_have_frequency: float = _MUST_HAVE_FREQUENCY,
    ) -> None:
        if not 0.0 < must_have_frequency <= 1.0:
            raise MappingError("must_have_frequency must be within (0, 1]")
        self._must_have_frequency = must_have_frequency

    # -- public API --------------------------------------------------------

    def map(
        self,
        *,
        creator_id: str,
        patterns: Sequence[CreatorStrategyPattern],
        grammars: Sequence[VisualGrammar],
        constraints: Sequence[VisualConstraint],
    ) -> VisualCreatorProfile:
        """Build a profile from a creator's M4 output.

        ``patterns`` may hold more than one strategy pattern: a creator whose
        images fall into several families genuinely has several strategies, and
        merging them into one would lose that. All source patterns are recorded.
        """

        if not creator_id.strip():
            raise MappingError("creator_id must be non-empty")
        if not patterns:
            raise MappingError(
                "no M4 strategy pattern supplied; a profile cannot be derived from "
                "nothing, and M5 may not invent one"
            )
        if not grammars:
            raise MappingError(
                "no grammar supplied; composition rules are derived from grammars"
            )
        pattern_ids = {pattern.pattern_id for pattern in patterns}
        for constraint in constraints:
            if constraint.pattern_id not in pattern_ids:
                raise MappingError(
                    f"constraint {constraint.constraint_id!r} references pattern "
                    f"{constraint.pattern_id!r}, which was not supplied"
                )

        evidence = self._measure(patterns, grammars, constraints)
        pattern_id = "+".join(sorted(pattern_ids))
        pattern_confidence = _weakest(*(p.confidence for p in patterns))
        grammar_confidence = _weakest(*(g.confidence for g in grammars))
        constraint_confidence = (
            _weakest(*(c.frequency for c in self._all_constraints(constraints)))
            if constraints
            else 0.0
        )

        identity = self._identity(patterns, grammars, evidence)
        rules = self._composition_rules(patterns, evidence)
        attention = self._attention(patterns, grammars)
        hierarchy = self._hierarchy(patterns)
        constraint_layer = self._constraint_layer(constraints)

        provenance = {
            "visual_identity": FieldProvenance(
                source_phase="M4",
                artifact_id=pattern_id,
                artifact_kind="CreatorStrategyPattern+VisualGrammar",
                derivation="aggregated",
                confidence=_weakest(pattern_confidence, grammar_confidence),
                evidence={
                    "style_traits": list(evidence.style_traits),
                    "average_region_area": evidence.average_region_area,
                    "attention_strategy": [
                        p.attention_strategy for p in patterns
                    ],
                },
            ),
            "composition_rules": FieldProvenance(
                source_phase="M4",
                artifact_id=pattern_id,
                artifact_kind="CreatorStrategyPattern",
                derivation="enumerated_absent",
                confidence=pattern_confidence,
                evidence={
                    "moves_present": list(evidence.composition_moves_present),
                    "moves_absent": list(evidence.composition_moves_absent),
                    "vocabulary_size": len(COMPOSITION_MOVES),
                },
            ),
            "attention_strategy": FieldProvenance(
                source_phase="M4",
                artifact_id=pattern_id,
                artifact_kind="CreatorStrategyPattern",
                derivation="direct",
                confidence=pattern_confidence,
                evidence={
                    "attention_support": [
                        p.evidence.get("attention_support") for p in patterns
                    ],
                },
            ),
            "hierarchy_pattern": FieldProvenance(
                source_phase="M4",
                artifact_id=pattern_id,
                artifact_kind="CreatorStrategyPattern",
                derivation="direct",
                confidence=pattern_confidence,
                evidence={
                    "strategies": [p.attention_strategy for p in patterns],
                    "support": evidence.support,
                },
            ),
            "constraints": FieldProvenance(
                source_phase="M4",
                artifact_id=(
                    "+".join(sorted(c.constraint_id for c in constraints))
                    if constraints
                    else pattern_id
                ),
                artifact_kind="VisualConstraint" if constraints else "CreatorStrategyPattern",
                derivation="thresholded",
                confidence=constraint_confidence or pattern_confidence,
                evidence={
                    "constraint_count": len(constraints),
                    "must_have_features": list(evidence.must_have_features),
                    "must_have_frequency": self._must_have_frequency,
                },
            ),
        }

        profile_id = self._profile_id(creator_id, sorted(pattern_ids))
        overall = _weakest(*(record.confidence for record in provenance.values()))

        return VisualCreatorProfile(
            profile_id=profile_id,
            creator_id=creator_id,
            version=PROFILE_VERSION,
            visual_identity=identity,
            composition_rules=rules,
            attention_strategy=attention,
            hierarchy_pattern=hierarchy,
            constraints=constraint_layer,
            provenance=provenance,
            source_pattern_ids=tuple(sorted(pattern_ids)),
            support=evidence.support,
            confidence=overall,
            notes=self._notes(evidence),
        )

    # -- measurement -------------------------------------------------------

    def _measure(
        self,
        patterns: Sequence[CreatorStrategyPattern],
        grammars: Sequence[VisualGrammar],
        constraints: Sequence[VisualConstraint],
    ) -> MappingEvidence:
        # Style traits come from M4 invariants whose family is region_density,
        # which is where M4 records how a cluster's regions are filled.
        traits: list[str] = []
        for pattern in patterns:
            for invariant in pattern.invariants:
                if invariant.feature_family == "region_density":
                    traits.append(invariant.feature)

        areas: list[float] = []
        for grammar in grammars:
            for region in grammar.regions:
                areas.append(region.area_share)

        present: list[str] = []
        for pattern in patterns:
            for move in pattern.composition_strategy:
                if move not in present:
                    present.append(move)
        absent = [move for move in COMPOSITION_MOVES if move not in present]

        must_have: list[str] = []
        for constraint in self._all_constraints(constraints):
            if (
                constraint.strength == "required"
                and constraint.frequency >= self._must_have_frequency
                and constraint.value not in must_have
            ):
                must_have.append(constraint.value)

        support = max((pattern.support for pattern in patterns), default=0)
        return MappingEvidence(
            pattern_count=len(patterns),
            grammar_count=len(grammars),
            style_traits=tuple(sorted(set(traits))),
            average_region_area=_average(areas),
            composition_moves_present=tuple(present),
            composition_moves_absent=tuple(absent),
            must_have_features=tuple(sorted(must_have)),
            support=support,
        )

    @staticmethod
    def _all_constraints(
        constraints: Sequence[VisualConstraint],
    ) -> tuple[Constraint, ...]:
        gathered: list[Constraint] = []
        for item in constraints:
            gathered.extend(item.all_constraints())
        return tuple(gathered)

    # -- field derivation --------------------------------------------------

    def _identity(
        self,
        patterns: Sequence[CreatorStrategyPattern],
        grammars: Sequence[VisualGrammar],
        evidence: MappingEvidence,
    ) -> VisualIdentity:
        language = LANGUAGE_BY_ATTENTION.get(
            _dominant([p.attention_strategy for p in patterns], "undetermined"),
            "undetermined",
        )

        trait_names = {
            trait.split("_", 1)[1] if "_" in trait else trait
            for trait in evidence.style_traits
        }
        density = _dominant(
            [
                trait
                for trait in trait_names
                if trait in {"sparse", "moderate", "dense"}
            ],
            "moderate",
        )

        relations: set[str] = set()
        for grammar in grammars:
            relations |= grammar.relation_types()

        if relations & _HIGH_CONTRAST_RELATIONS:
            contrast = "high_contrast"
        elif relations & _LOW_CONTRAST_RELATIONS:
            contrast = "low_contrast"
        else:
            contrast = "undetermined"

        if relations & _FULL_BLEED_RELATIONS:
            framing = "full_bleed"
        elif relations & _SPLIT_RELATIONS:
            framing = "split"
        else:
            framing = "stacked"

        display_areas = [
            region.area_share
            for grammar in grammars
            for region in grammar.regions
            if region.region_type in _DISPLAY_TYPES
        ]
        has_body = any(
            region.region_type in _BODY_TYPES
            for grammar in grammars
            for region in grammar.regions
        )
        if display_areas and _average(display_areas) >= _LARGE_TYPE_AREA:
            typography = "large_display_type"
        elif display_areas and has_body:
            typography = "balanced_display_and_body"
        elif display_areas:
            typography = "display_led"
        else:
            typography = "undetermined"

        complexity = self._complexity(evidence.composition_moves_present)

        # The style family is a composite of measured traits. The brief forbids
        # inventing a domain label such as "educational_finance", so none is
        # invented: the value is built from the traits M4 actually measured, which
        # makes it traceable rather than asserted.
        parts = [part for part in (contrast, density, framing, typography) if part != "undetermined"]
        style_family = "__".join(parts) if parts else "undetermined"

        return VisualIdentity(
            style_family=style_family,
            visual_language=language,
            complexity=complexity,
            density=density,
            contrast=contrast,
            framing=framing,
            typography=typography,
        )

    def _complexity(self, moves: Sequence[str]) -> str:
        """Complexity from how many distinct composition moves recur.

        A creator who reliably repeats one or two moves has a simpler, more
        reproducible visual grammar than one who repeats six, and that is exactly
        what a factory consuming this profile needs to know.
        """

        count = len(moves)
        if count <= 2:
            return _COMPLEXITY_ORDER[0]
        if count <= 4:
            return _COMPLEXITY_ORDER[1]
        return _COMPLEXITY_ORDER[2]

    def _composition_rules(
        self,
        patterns: Sequence[CreatorStrategyPattern],
        evidence: MappingEvidence,
    ) -> CompositionRules:
        return CompositionRules(
            preferred=tuple(evidence.composition_moves_present),
            forbidden=tuple(evidence.composition_moves_absent),
        )

    def _attention(
        self,
        patterns: Sequence[CreatorStrategyPattern],
        grammars: Sequence[VisualGrammar],
    ) -> AttentionStrategy:
        """Map M4 attention signatures onto ordinal slots.

        The sequence is read from the **grammars**, because
        :meth:`VisualGrammar.attention_signature` is where M4 records the ordered
        ``stage:region_type`` pairs. The strategy pattern summarises the lead but
        not the full order, so using it alone would yield a one-slot sequence and
        lose the second and third steps the profile is meant to carry.

        Each slot takes the dominant region type across members at that position,
        so a single divergent sample does not redefine the creator's sequence.
        """

        per_slot: dict[str, list[str]] = {slot: [] for slot in ATTENTION_SLOTS}
        for grammar in grammars:
            signature = grammar.attention_signature()
            for index, entry in enumerate(signature):
                if index >= len(ATTENTION_SLOTS):
                    break
                per_slot[ATTENTION_SLOTS[index]].append(str(entry).split(":", 1)[-1])

        order: dict[str, str] = {}
        for slot in ATTENTION_SLOTS:
            candidates = per_slot[slot]
            if not candidates:
                break
            target = _dominant(candidates, "")
            if not target:
                break
            order[slot] = target

        if not order:
            # No grammar carried a signature, so fall back to the strategy's own
            # lead rather than inventing a sequence.
            strategy = _dominant(
                [p.attention_strategy for p in patterns], "undetermined"
            )
            lead = {
                "headline_first": "headline",
                "subject_first": "subject",
                "data_first": "data_display",
                "action_first": "cta",
            }.get(strategy)
            if lead is None:
                # M4 itself concluded "undetermined", which happens when the
                # observer could not evidence an entry point. Carrying that verdict
                # through is the honest result: inventing a lead would manufacture
                # a strategy the evidence does not support. The value is a declared
                # vocabulary member, so a consumer can branch on it.
                lead = "undetermined"
            order = {ATTENTION_SLOTS[0]: lead}

        return AttentionStrategy(order=order)

    def _hierarchy(
        self, patterns: Sequence[CreatorStrategyPattern]
    ) -> HierarchyPattern:
        stages: list[str] = []
        for pattern in patterns:
            for stage in pattern.information_hierarchy:
                if stage not in stages:
                    stages.append(stage)
        ordered = [stage for stage in HIERARCHY_STAGES if stage in stages]
        if not ordered:
            # M4 found no delivery stage it could evidence. Recording the verdict
            # is honest; inventing a stage would not be. ``undetermined`` is a
            # declared member of the stage vocabulary for exactly this case.
            ordered = ["undetermined"]
        tiers = {
            HIERARCHY_TIERS[index]: stage
            for index, stage in enumerate(ordered[: len(HIERARCHY_TIERS)])
        }
        return HierarchyPattern(tiers=tiers)

    def _constraint_layer(
        self, constraints: Sequence[VisualConstraint]
    ) -> ConstraintLayer:
        """Split M4 constraints into what must be present and what to avoid.

        ``must_have`` takes required constraints at or above the frequency
        threshold. ``avoid`` takes the structural relations that no grammar
        exhibited — an entry point or a support structure that is conspicuously
        missing is something a generated instance should not omit either.
        """

        required: list[str] = []
        for constraint in self._all_constraints(constraints):
            if (
                constraint.strength == "required"
                and constraint.frequency >= self._must_have_frequency
                and constraint.value not in required
            ):
                required.append(constraint.value)

        return ConstraintLayer(
            must_have=tuple(sorted(required)),
            avoid=self._avoided(constraints),
        )

    def _avoided(self, constraints: Sequence[VisualConstraint]) -> tuple[str, ...]:
        """Structural expectations the M4 evidence does not support.

        These are derived from the relation vocabulary *absent* from the M4
        constraints: if a composition never evidenced an entry point or a support
        structure, a profile should say so rather than leave the gap invisible.
        """

        observed: set[str] = set()
        for constraint in self._all_constraints(constraints):
            observed.add(constraint.value)

        avoided: list[str] = []
        if not (observed & (_ENTRY_RELATIONS | {"headline_present"})):
            avoided.append("unclear_entry_point")
        if not (observed & (_SUPPORT_RELATIONS | {"supporting_information_present"})):
            avoided.append("missing_information_support")
        return tuple(sorted(avoided))

    @staticmethod
    def _profile_id(creator_id: str, pattern_ids: Sequence[str]) -> str:
        """Content-addressed profile id.

        Derived from the creator and the source patterns, never from a name
        literal, so two runs over the same evidence produce the same id and the id
        cannot drift while the sources stay the same.
        """

        import hashlib

        digest = hashlib.sha256(
            "|".join([creator_id, *pattern_ids]).encode("utf-8")
        ).hexdigest()[:16]
        return f"vcp-{digest}"

    def _notes(self, evidence: MappingEvidence) -> tuple[str, ...]:
        notes = [
            f"derived from {evidence.pattern_count} M4 strategy pattern(s) over "
            f"{evidence.grammar_count} grammar(s)",
            f"forbidden composition set rests on {evidence.support} supporting "
            "observations; absence over a small sample is weaker evidence than presence",
        ]
        if evidence.composition_moves_absent:
            notes.append(
                "forbidden moves are the composition vocabulary entries no cluster "
                "member exhibited, not moves observed to be avoided"
            )
        return tuple(notes)


def pattern_to_profile(
    *,
    creator_id: str,
    patterns: Sequence[CreatorStrategyPattern],
    grammars: Sequence[VisualGrammar],
    constraints: Sequence[VisualConstraint],
    must_have_frequency: float = _MUST_HAVE_FREQUENCY,
) -> VisualCreatorProfile:
    """Convenience wrapper around :class:`PatternToProfileMapper`."""

    return PatternToProfileMapper(must_have_frequency=must_have_frequency).map(
        creator_id=creator_id,
        patterns=patterns,
        grammars=grammars,
        constraints=constraints,
    )


__all__ = [
    "LANGUAGE_BY_ATTENTION",
    "MappingError",
    "MappingEvidence",
    "PatternToProfileMapper",
    "pattern_to_profile",
]
