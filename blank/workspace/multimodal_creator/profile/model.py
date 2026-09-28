"""Visual Creator Profile model (Phase M5).

This is the engineering bridge from M4's distillation output to a **config asset**
a Creator Instance Factory can consume. It adds no visual understanding: every
field is derived from an M4 artifact, and every field records the artifact it
came from.

The four parts of the brief's target structure
----------------------------------------------

``visual_identity``
    What the creator's visual language *is*, described in design terms M4
    already measured — density, contrast, framing, typographic scale. Not a
    domain name.
``composition_rules``
    What the creator reliably does, and what they never do. Both come from M4's
    composition strategy and the grammar's observed moves; the "never" set is
    derived from moves that were *absent* across the whole cluster, which is a
    measurement rather than an opinion.
``attention_strategy`` / ``hierarchy_pattern``
    The ordered attention and delivery sequences, from M4's attention flow and
    information hierarchy.
``constraints``
    ``must_have`` and ``avoid``, from M4's :class:`VisualConstraint` layer, each
    retaining the invariant that produced it.

Provenance is not optional
--------------------------

Every value in this model sits beside a :class:`FieldProvenance` entry naming the
M4 artifact it came from, how it was derived, and the confidence behind it. The
model will not construct without provenance for each declared field, and
:mod:`multimodal_creator.profile.validation` enforces the same rule on a
round-tripped document. A field with no source is a hard error, because an
unsourced config value is indistinguishable from a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# --------------------------------------------------------------------------
# Vocabularies
# --------------------------------------------------------------------------

#: Version of the profile contract.
PROFILE_VERSION = "m5.0.0"

#: Validated visual languages, derived from M4's attention strategy.
VISUAL_LANGUAGES: tuple[str, ...] = (
    "information_first",
    "subject_first",
    "data_first",
    "action_first",
    "undetermined",
)

#: Composition complexity levels, derived from measured structure.
COMPLEXITY_LEVELS: tuple[str, ...] = ("low", "medium", "high", "undetermined")

#: Ordinal attention slots. A profile fills the ones its strategy supports.
ATTENTION_SLOTS: tuple[str, ...] = ("first", "second", "third", "fourth")

#: Hierarchy tiers, matching the brief's primary/secondary/tertiary naming.
HIERARCHY_TIERS: tuple[str, ...] = ("primary", "secondary", "tertiary", "quaternary")

#: Phases an M4 artifact can come from. Only M4 is accepted as a source, because
#: M5 is defined as the bridge from M4 and nothing else.
SOURCE_PHASES: tuple[str, ...] = ("M4",)

#: How a value was obtained from its source. Recorded so a reviewer can tell a
#: direct copy from an aggregate from a threshold decision.
DERIVATIONS: tuple[str, ...] = (
    "direct",
    "aggregated",
    "thresholded",
    "inverted",
    "enumerated_absent",
)

#: Families within the profile that carry provenance. Used to check completeness.
PROVENANCE_FAMILIES: tuple[str, ...] = (
    "visual_identity",
    "composition_rules",
    "attention_strategy",
    "hierarchy_pattern",
    "constraints",
)


class ProfileError(Exception):
    """Raised when a profile cannot be built or is malformed."""


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    """Where one profile field came from.

    ``confidence`` is the *weakest* signal supporting the field, not an
    optimistic average: a value backed by one strong measurement and one weak
    one is only as trustworthy as the weak one.
    """

    source_phase: str
    artifact_id: str
    artifact_kind: str
    derivation: str
    confidence: float
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.source_phase not in SOURCE_PHASES:
            raise ProfileError(
                f"source_phase must be one of {list(SOURCE_PHASES)!r}, got "
                f"{self.source_phase!r}; M5 derives only from M4 artifacts"
            )
        if not self.artifact_id.strip():
            raise ProfileError("artifact_id must be non-empty")
        if not self.artifact_kind.strip():
            raise ProfileError("artifact_kind must be non-empty")
        if self.derivation not in DERIVATIONS:
            raise ProfileError(
                f"derivation must be one of {list(DERIVATIONS)!r}, got {self.derivation!r}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ProfileError(
                f"confidence must be within 0..1, got {self.confidence!r}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": {
                "phase": self.source_phase,
                "artifact": self.artifact_id,
                "artifact_kind": self.artifact_kind,
            },
            "derivation": self.derivation,
            "confidence": self.confidence,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class VisualIdentity:
    """What the creator's visual language is, in measured design terms.

    ``style_family`` is a **composite of M4's own style traits**, not a domain
    label. The brief forbids hardcoding a name such as ``educational_finance``,
    so none is invented: the value is built from the measured traits, which makes
    it auditable and traceable in a way a hand-written category would not be.
    """

    style_family: str
    visual_language: str
    complexity: str
    density: str
    contrast: str
    framing: str
    typography: str

    def __post_init__(self) -> None:
        if self.visual_language not in VISUAL_LANGUAGES:
            raise ProfileError(
                f"visual_language must be one of {list(VISUAL_LANGUAGES)!r}, got "
                f"{self.visual_language!r}"
            )
        if self.complexity not in COMPLEXITY_LEVELS:
            raise ProfileError(
                f"complexity must be one of {list(COMPLEXITY_LEVELS)!r}, got "
                f"{self.complexity!r}"
            )
        if not self.style_family.strip():
            raise ProfileError(
                "style_family must be non-empty; use 'undetermined' when M4 evidence "
                "does not support a composite"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "style_family": self.style_family,
            "visual_language": self.visual_language,
            "complexity": self.complexity,
            "density": self.density,
            "contrast": self.contrast,
            "framing": self.framing,
            "typography": self.typography,
        }


@dataclass(frozen=True, slots=True)
class CompositionRules:
    """What the creator reliably does, and what they never do.

    Both sets are measurements. ``preferred`` comes from moves present at or
    above the support threshold; ``forbidden`` comes from moves that were
    **absent across the entire cluster**. The two are disjoint by construction,
    and the model refuses a profile where they are not.
    """

    preferred: tuple[str, ...]
    forbidden: tuple[str, ...]

    def __post_init__(self) -> None:
        overlap = sorted(set(self.preferred) & set(self.forbidden))
        if overlap:
            raise ProfileError(
                "a composition move cannot be both preferred and forbidden: "
                + ", ".join(overlap)
            )

    def as_dict(self) -> dict[str, Any]:
        return {"preferred": list(self.preferred), "forbidden": list(self.forbidden)}


@dataclass(frozen=True, slots=True)
class AttentionStrategy:
    """The ordered attention sequence, keyed by ordinal slot."""

    order: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.order:
            raise ProfileError("attention strategy must name at least one slot")
        positions = 0
        for slot, region_type in self.order.items():
            if slot not in ATTENTION_SLOTS:
                raise ProfileError(
                    f"unknown attention slot {slot!r}; expected one of "
                    f"{list(ATTENTION_SLOTS)!r}"
                )
            if not str(region_type).strip():
                raise ProfileError(f"attention slot {slot!r} has an empty target")
            positions += 1
        # Slots must be filled from the front, with no gaps.
        expected = list(ATTENTION_SLOTS[:positions])
        if list(self.order) != expected:
            raise ProfileError(
                f"attention slots must be contiguous from 'first', got "
                f"{list(self.order)!r}"
            )

    def as_dict(self) -> dict[str, Any]:
        return dict(self.order)


@dataclass(frozen=True, slots=True)
class HierarchyPattern:
    """The delivery sequence, keyed by tier.

    Tiers are filled from ``primary`` with no gaps, so a reader can always tell
    what comes first without interpreting an empty middle tier.
    """

    tiers: Mapping[str, str]

    def __post_init__(self) -> None:
        if not self.tiers:
            raise ProfileError("hierarchy pattern must name at least one tier")
        positions = 0
        for tier, stage in self.tiers.items():
            if tier not in HIERARCHY_TIERS:
                raise ProfileError(
                    f"unknown hierarchy tier {tier!r}; expected one of "
                    f"{list(HIERARCHY_TIERS)!r}"
                )
            if not str(stage).strip():
                raise ProfileError(f"hierarchy tier {tier!r} has an empty stage")
            positions += 1
        expected = list(HIERARCHY_TIERS[:positions])
        if list(self.tiers) != expected:
            raise ProfileError(
                f"hierarchy tiers must be contiguous from 'primary', got "
                f"{list(self.tiers)!r}"
            )

    def as_dict(self) -> dict[str, Any]:
        return dict(self.tiers)


@dataclass(frozen=True, slots=True)
class ConstraintLayer:
    """``must_have`` and ``avoid``, each retaining its originating invariant."""

    must_have: tuple[str, ...]
    avoid: tuple[str, ...]

    def __post_init__(self) -> None:
        overlap = sorted(set(self.must_have) & set(self.avoid))
        if overlap:
            raise ProfileError(
                "a constraint cannot be both required and avoided: "
                + ", ".join(overlap)
            )

    def as_dict(self) -> dict[str, Any]:
        return {"must_have": list(self.must_have), "avoid": list(self.avoid)}


@dataclass(frozen=True, slots=True)
class VisualCreatorProfile:
    """A stable, traceable config asset derived from M4 artifacts.

    Deliberately contains **no generation logic**: no prompt, no model
    reference, no renderer settings, and no image bytes. Those are unrepresentable
    here, and :mod:`multimodal_creator.profile.validation` rejects them if they
    arrive through a raw document.
    """

    profile_id: str
    creator_id: str
    version: str
    visual_identity: VisualIdentity
    composition_rules: CompositionRules
    attention_strategy: AttentionStrategy
    hierarchy_pattern: HierarchyPattern
    constraints: ConstraintLayer
    provenance: Mapping[str, FieldProvenance]
    source_pattern_ids: tuple[str, ...]
    support: int
    confidence: float
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ProfileError("profile_id must be non-empty")
        if not self.creator_id.strip():
            raise ProfileError("creator_id must be non-empty")
        if not self.version.strip():
            raise ProfileError("version must be non-empty")
        if self.support < 0:
            raise ProfileError("support must not be negative")
        if not 0.0 <= self.confidence <= 1.0:
            raise ProfileError("confidence must be within 0..1")
        if not self.source_pattern_ids:
            raise ProfileError(
                "a profile must name at least one M4 source pattern; a profile with "
                "no source is a hand-written config"
            )
        missing = [
            family for family in PROVENANCE_FAMILIES if family not in self.provenance
        ]
        if missing:
            raise ProfileError(
                "every profile family needs provenance; missing: " + ", ".join(missing)
            )
        for family, record in self.provenance.items():
            if family not in PROVENANCE_FAMILIES:
                raise ProfileError(f"provenance names unknown family {family!r}")
            if record.source_phase != "M4":
                raise ProfileError(
                    f"provenance for {family!r} must come from M4, got "
                    f"{record.source_phase!r}"
                )

    # -- views -------------------------------------------------------------

    def provenance_for(self, family: str) -> FieldProvenance:
        if family not in self.provenance:
            raise ProfileError(f"no provenance for family {family!r}")
        return self.provenance[family]

    def weakest_confidence(self) -> float:
        """The lowest confidence across all families — the profile's real floor."""

        return round(
            min(record.confidence for record in self.provenance.values()), 6
        )

    def all_rules(self) -> tuple[str, ...]:
        """Every rule-like string in the profile, for audit and for YAML export."""

        return (
            tuple(f"preferred_layout:{move}" for move in self.composition_rules.preferred)
            + tuple(f"forbidden_layout:{move}" for move in self.composition_rules.forbidden)
            + tuple(
                f"attention_{slot}:{target}"
                for slot, target in self.attention_strategy.order.items()
            )
            + tuple(
                f"hierarchy_{tier}:{stage}"
                for tier, stage in self.hierarchy_pattern.tiers.items()
            )
            + tuple(f"must_have:{rule}" for rule in self.constraints.must_have)
            + tuple(f"avoid:{rule}" for rule in self.constraints.avoid)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_version": self.version,
            "profile_id": self.profile_id,
            "creator_id": self.creator_id,
            "source_pattern_ids": list(self.source_pattern_ids),
            "support": self.support,
            "confidence": self.confidence,
            "visual_identity": self.visual_identity.as_dict(),
            "composition_rules": self.composition_rules.as_dict(),
            "attention_strategy": self.attention_strategy.as_dict(),
            "hierarchy_pattern": self.hierarchy_pattern.as_dict(),
            "constraints": self.constraints.as_dict(),
            "provenance": {
                family: record.as_dict()
                for family, record in sorted(self.provenance.items())
            },
            "notes": list(self.notes),
        }

    def render(self) -> str:
        identity = self.visual_identity
        lines = [
            f"visual creator profile {self.profile_id} (creator={self.creator_id})",
            f"  version={self.version} support={self.support} "
            f"confidence={self.confidence:.2f} floor={self.weakest_confidence():.2f}",
            "  identity:",
            f"    style_family      {identity.style_family}",
            f"    visual_language   {identity.visual_language}",
            f"    complexity        {identity.complexity}",
            f"    density/contrast  {identity.density} / {identity.contrast}",
            f"    framing/type      {identity.framing} / {identity.typography}",
            "  composition:",
            f"    preferred {list(self.composition_rules.preferred)}",
            f"    forbidden {list(self.composition_rules.forbidden)}",
            "  attention: " + " -> ".join(
                f"{slot}:{target}" for slot, target in self.attention_strategy.order.items()
            ),
            "  hierarchy: " + " -> ".join(
                f"{tier}:{stage}" for tier, stage in self.hierarchy_pattern.tiers.items()
            ),
            f"  constraints: must_have={list(self.constraints.must_have)} "
            f"avoid={list(self.constraints.avoid)}",
            f"  sources: {list(self.source_pattern_ids)}",
        ]
        for family in PROVENANCE_FAMILIES:
            record = self.provenance[family]
            lines.append(
                f"    {family:<20} <- {record.artifact_id} "
                f"({record.derivation}, {record.confidence:.2f})"
            )
        return "\n".join(lines)


__all__ = [
    "ATTENTION_SLOTS",
    "COMPLEXITY_LEVELS",
    "DERIVATIONS",
    "HIERARCHY_TIERS",
    "PROFILE_VERSION",
    "PROVENANCE_FAMILIES",
    "SOURCE_PHASES",
    "VISUAL_LANGUAGES",
    "AttentionStrategy",
    "CompositionRules",
    "ConstraintLayer",
    "FieldProvenance",
    "HierarchyPattern",
    "ProfileError",
    "VisualCreatorProfile",
    "VisualIdentity",
]
