"""Generation constraint prototype (Phase M4, phase 10).

**Interface only.** This module defines what a distilled strategy would *say* to
a generation stage. It generates nothing, renders nothing, and calls nothing.

The point of writing it now is to prove the distillation output is actionable
before M5 exists. A strategy description that cannot be turned into constraints
is a description nobody can use, and finding that out after building a generator
would be expensive.

A :class:`VisualConstraint` is derived mechanically from a
:class:`CreatorStrategyPattern` — every constraint traces back to a measured
invariant. No constraint is authored by hand, and none can appear without an
invariant behind it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .strategy import CreatorStrategyPattern, StrategyError

#: Constraint families a generator would eventually consume.
CONSTRAINT_FAMILIES: tuple[str, ...] = (
    "layout_constraints",
    "attention_constraints",
    "style_constraints",
)

#: How binding a constraint is. ``required`` means the strategy was observed
#: strongly; ``preferred`` means it recurred but not overwhelmingly.
STRENGTHS: tuple[str, ...] = ("required", "preferred")

#: Invariant frequency at or above which a constraint becomes required.
REQUIRED_FREQUENCY = 0.85


class ConstraintError(Exception):
    """Raised when a constraint cannot be derived or is malformed."""


@dataclass(frozen=True, slots=True)
class Constraint:
    """One generation constraint, with the evidence that justified it."""

    family: str
    value: str
    strength: str
    frequency: float
    source_feature: str

    def __post_init__(self) -> None:
        if self.family not in CONSTRAINT_FAMILIES:
            raise ConstraintError(f"unknown constraint family {self.family!r}")
        if self.strength not in STRENGTHS:
            raise ConstraintError(f"unknown constraint strength {self.strength!r}")
        if not 0.0 <= self.frequency <= 1.0:
            raise ConstraintError("frequency must be within 0..1")
        if not self.value.strip():
            raise ConstraintError("constraint value must be non-empty")
        if not self.source_feature.strip():
            raise ConstraintError(
                "every constraint must name the invariant it came from; an "
                "unsourced constraint is an opinion, not a measurement"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "value": self.value,
            "strength": self.strength,
            "frequency": self.frequency,
            "source_feature": self.source_feature,
        }


@dataclass(frozen=True, slots=True)
class VisualConstraint:
    """What a distilled strategy asks of a future generation stage.

    Deliberately a description, not a program: there is no renderer, no prompt,
    and no image bytes anywhere in this type.
    """

    constraint_id: str
    pattern_id: str
    layout_constraints: tuple[Constraint, ...]
    attention_constraints: tuple[Constraint, ...]
    style_constraints: tuple[Constraint, ...]
    generative: bool = False

    def __post_init__(self) -> None:
        if self.generative:
            raise ConstraintError(
                "VisualConstraint is a design surface only and must never be "
                "generative; M4 does not generate content"
            )

    def all_constraints(self) -> tuple[Constraint, ...]:
        return (
            self.layout_constraints + self.attention_constraints + self.style_constraints
        )

    def by_family(self, family: str) -> tuple[Constraint, ...]:
        if family == "layout_constraints":
            return self.layout_constraints
        if family == "attention_constraints":
            return self.attention_constraints
        if family == "style_constraints":
            return self.style_constraints
        raise ConstraintError(f"unknown constraint family {family!r}")

    def required(self) -> tuple[Constraint, ...]:
        return tuple(c for c in self.all_constraints() if c.strength == "required")

    def as_dict(self) -> dict[str, Any]:
        return {
            "constraint_id": self.constraint_id,
            "pattern_id": self.pattern_id,
            "generative": self.generative,
            "layout_constraints": [c.as_dict() for c in self.layout_constraints],
            "attention_constraints": [c.as_dict() for c in self.attention_constraints],
            "style_constraints": [c.as_dict() for c in self.style_constraints],
            "note": (
                "interface prototype only; M4 generates no content and this object "
                "carries no pixels"
            ),
        }

    def render(self) -> str:
        lines = [f"visual constraints for {self.pattern_id} (generative={self.generative})"]
        for family in CONSTRAINT_FAMILIES:
            items = self.by_family(family)
            if not items:
                continue
            lines.append(f"  {family}:")
            for item in items:
                lines.append(
                    f"    [{item.strength:<9}] {item.value} "
                    f"({item.frequency:.0%} of members, from {item.source_feature})"
                )
        return "\n".join(lines)


#: Invariant feature prefix -> constraint family.
_FEATURE_FAMILY_MAP: Mapping[str, str] = {
    "region_presence": "layout_constraints",
    "region_placement": "layout_constraints",
    "region_dominance": "layout_constraints",
    "region_density": "style_constraints",
    "relation_presence": "layout_constraints",
    "attention_flow": "attention_constraints",
}


def constraints_from_strategy(
    pattern: CreatorStrategyPattern,
    *,
    required_frequency: float = REQUIRED_FREQUENCY,
) -> VisualConstraint:
    """Derive generation constraints from a strategy pattern.

    Every constraint carries the invariant that produced it. A constraint whose
    frequency falls below ``required_frequency`` is still emitted, marked
    ``preferred`` — dropping it would discard a real but weaker regularity.
    """

    if not 0.0 < required_frequency <= 1.0:
        raise ConstraintError("required_frequency must be within (0, 1]")

    layout: list[Constraint] = []
    attention: list[Constraint] = []
    style: list[Constraint] = []

    def strength_for(frequency: float) -> str:
        return "required" if frequency >= required_frequency else "preferred"

    for invariant in pattern.invariants:
        family = _FEATURE_FAMILY_MAP.get(invariant.feature_family)
        if family is None:
            continue
        constraint = Constraint(
            family=family,
            value=invariant.feature,
            strength=strength_for(invariant.frequency),
            frequency=invariant.frequency,
            source_feature=invariant.key,
        )
        if family == "layout_constraints":
            layout.append(constraint)
        elif family == "attention_constraints":
            attention.append(constraint)
        else:
            style.append(constraint)

    # The strategy fields are themselves measurements, so they become
    # constraints too — sourced from the pattern rather than from a single
    # invariant, which is why they carry the attention support as frequency.
    attention_support = float(pattern.evidence.get("attention_support", 0.0))
    if pattern.attention_strategy != "undetermined":
        attention.insert(
            0,
            Constraint(
                family="attention_constraints",
                value=pattern.attention_strategy,
                strength=strength_for(attention_support),
                frequency=round(min(1.0, attention_support), 6),
                source_feature="strategy:attention_strategy",
            ),
        )
    for move in pattern.composition_strategy:
        layout.insert(
            0,
            Constraint(
                family="layout_constraints",
                value=move,
                strength="preferred",
                frequency=round(
                    min(1.0, float(pattern.evidence.get("strategy_support", 0.7))), 6
                ),
                source_feature="strategy:composition_strategy",
            ),
        )
    for stage in pattern.information_hierarchy:
        attention.append(
            Constraint(
                family="attention_constraints",
                value=f"hierarchy:{stage}",
                strength="preferred",
                frequency=round(
                    min(1.0, float(pattern.evidence.get("strategy_support", 0.7))), 6
                ),
                source_feature="strategy:information_hierarchy",
            )
        )

    def dedupe(items: Sequence[Constraint]) -> tuple[Constraint, ...]:
        seen: dict[tuple[str, str], Constraint] = {}
        for item in items:
            seen.setdefault((item.family, item.value), item)
        return tuple(
            sorted(seen.values(), key=lambda c: (-c.frequency, c.value))
        )

    return VisualConstraint(
        constraint_id=f"constraint-{pattern.pattern_id}",
        pattern_id=pattern.pattern_id,
        layout_constraints=dedupe(layout),
        attention_constraints=dedupe(attention),
        style_constraints=dedupe(style),
    )


def render_constraints(constraints: Sequence[VisualConstraint]) -> str:
    if not constraints:
        return "no visual constraints derived"
    return "\n\n".join(item.render() for item in constraints)


__all__ = [
    "CONSTRAINT_FAMILIES",
    "REQUIRED_FREQUENCY",
    "STRENGTHS",
    "Constraint",
    "ConstraintError",
    "VisualConstraint",
    "constraints_from_strategy",
    "render_constraints",
]
