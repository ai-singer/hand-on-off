"""The pattern model: entities, relations, frames and patterns.

The old mechanism is a list of regular expressions over surface word order. That
works until the same meaning appears in a different syntactic shape, and then it
fails silently:

    "This is a guaranteed return."   matched by `guaranteed\\s+(?:return|...)`
    "This return is guaranteed."     not matched: the adjective follows the noun
    "Returns are guaranteed."        not matched
    "We guarantee this return."      not matched: the verb form is not listed

Three of those four sentences say the same thing. A pattern language that cannot
express "the same relation, different word order" will keep missing them.

This model separates three things the old one conflated:

    EntityType   the kind of thing involved      RETURN, CAPITAL, PROFIT, ...
    Relation     what is asserted about it       GUARANTEE
    Frame        how the relation is realised    active, passive, copular,
                                                 attributive, nominal

A `Relation` is a set of `Frame`s. A `Frame` is one syntactic realisation, with
named roles for the participants. Matching is therefore relational: the matcher
looks for a relation between an entity and a predicate, not for a substring.

Negation and hedging are properties of a match, not separate patterns, so a
negated guarantee is a *matched frame that is negated* rather than a sentence
that quietly escapes the rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


class PatternError(Exception):
    """Raised when a pattern or frame is malformed."""


#: How a relation is realised in surface syntax.
ACTIVE = "active"
PASSIVE = "passive"
COPULAR = "copular"
ATTRIBUTIVE = "attributive"
NOMINAL = "nominal"
FRAME_KINDS = (ACTIVE, PASSIVE, COPULAR, ATTRIBUTIVE, NOMINAL)


@dataclass(frozen=True, slots=True)
class EntityType:
    """A kind of thing a relation can be about."""

    name: str
    alternatives: tuple[str, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise PatternError("an entity type must be named")
        if not self.alternatives:
            raise PatternError(f"{self.name}: at least one alternative is required")
        for item in self.alternatives:
            re.compile(item)  # fail loudly on a bad alternative

    @property
    def pattern(self) -> str:
        """A non-capturing alternation over the alternatives."""

        return "(?:" + "|".join(self.alternatives) + ")"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "alternatives": list(self.alternatives),
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class EntityLexicon:
    """The entity types a pattern set knows about."""

    types: Mapping[str, EntityType]

    def __post_init__(self) -> None:
        object.__setattr__(self, "types", dict(self.types))
        if not self.types:
            raise PatternError("an entity lexicon needs at least one type")

    def __contains__(self, name: object) -> bool:
        return name in self.types

    def get(self, name: str) -> EntityType:
        try:
            return self.types[name]
        except KeyError as exc:
            raise PatternError(f"unknown entity type {name!r}") from exc

    def group(self, *names: str) -> str:
        """A non-capturing alternation over several entity types."""

        parts = [self.get(name).pattern for name in names]
        return "(?:" + "|".join(parts) + ")"

    def names(self) -> tuple[str, ...]:
        return tuple(self.types)


@dataclass(frozen=True, slots=True)
class Frame:
    """One syntactic realisation of a relation.

    `self_negating` marks a frame whose *predicate is itself negative* --
    `cannot lose`, `never falls`, `no risk`. For those, negation must be
    measured from the start of the match rather than from the predicate, or the
    frame negates itself: the `cannot` in `cannot lose` is the claim, not a
    modifier of it. The old evaluator's comment describes the same trap.
    """

    kind: str
    template: str
    roles: tuple[str, ...]
    description: str = ""
    self_negating: bool = False

    def __post_init__(self) -> None:
        if self.kind not in FRAME_KINDS:
            raise PatternError(f"frame kind must be one of {FRAME_KINDS}, got {self.kind!r}")
        if not self.roles:
            raise PatternError("a frame must name at least one role")
        re.compile(self.template)

    @property
    def pattern(self) -> re.Pattern[str]:
        return re.compile(self.template, re.IGNORECASE)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "template": self.template,
            "roles": list(self.roles),
            "description": self.description,
            "self_negating": self.self_negating,
        }


@dataclass(frozen=True, slots=True)
class Relation:
    """A predicate and the frames that realise it."""

    name: str
    object_entities: tuple[str, ...]
    frames: tuple[Frame, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise PatternError("a relation must be named")
        if not self.frames:
            raise PatternError(f"{self.name}: at least one frame is required")

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(frame.kind for frame in self.frames))

    def frames_of(self, kind: str) -> tuple[Frame, ...]:
        return tuple(frame for frame in self.frames if frame.kind == kind)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "object_entities": list(self.object_entities),
            "frames": [frame.as_dict() for frame in self.frames],
        }


@dataclass(frozen=True, slots=True)
class IntentPattern:
    """A category's detection rule, expressed as entities and relations.

    The six documented fields, in the documented order.
    """

    pattern_id: str
    category: str
    required_entities: tuple[str, ...]
    relations: tuple[Relation, ...]
    confidence: float
    evidence: str

    def __post_init__(self) -> None:
        if not self.pattern_id.strip():
            raise PatternError("a pattern must have an id")
        if not self.category.strip():
            raise PatternError(f"{self.pattern_id}: a category is required")
        if not self.relations:
            raise PatternError(f"{self.pattern_id}: at least one relation is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise PatternError(
                f"{self.pattern_id}: confidence must be within 0..1, "
                f"got {self.confidence}"
            )
        if not self.evidence.strip():
            raise PatternError(f"{self.pattern_id}: evidence is required")

    @property
    def id(self) -> str:
        return self.pattern_id

    @property
    def relation_names(self) -> tuple[str, ...]:
        return tuple(relation.name for relation in self.relations)

    def relation(self, name: str) -> Relation:
        for relation in self.relations:
            if relation.name == name:
                return relation
        raise PatternError(f"{self.pattern_id}: no relation {name!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.pattern_id,
            "category": self.category,
            "required_entities": list(self.required_entities),
            "relations": [relation.as_dict() for relation in self.relations],
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class EntityMatch:
    """One entity occurrence found in the text."""

    entity_type: str
    value: str
    span: tuple[int, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "value": self.value,
            "span": list(self.span),
        }


@dataclass(frozen=True, slots=True)
class FrameMatch:
    """One frame that fired, with its roles bound."""

    kind: str
    relation: str
    span: tuple[int, int]
    predicate: str
    roles: Mapping[str, str]
    negated: bool = False
    hedge: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "roles", dict(self.roles))

    @property
    def object_value(self) -> str:
        return str(self.roles.get("object", ""))

    @property
    def subject_value(self) -> str:
        return str(self.roles.get("subject", ""))

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "relation": self.relation,
            "span": list(self.span),
            "predicate": self.predicate,
            "roles": dict(self.roles),
            "negated": self.negated,
            "hedge": self.hedge,
        }

    def render(self) -> str:
        state = "negated" if self.negated else ("hedged" if self.hedge else "asserted")
        return (
            f"{self.relation}[{self.kind}] {self.subject_value or '-'} -> "
            f"{self.object_value or '-'} ({self.predicate}) {state}"
        )


@dataclass(frozen=True, slots=True)
class PatternMatch:
    """The result of applying one pattern to one text."""

    pattern_id: str
    category: str
    confidence: float
    frames: tuple[FrameMatch, ...] = ()
    entities: tuple[EntityMatch, ...] = ()
    evidence: str = ""

    @property
    def fired(self) -> bool:
        """True when an asserted, unhedged frame was found."""

        return any(not item.negated and not item.hedge for item in self.frames)

    @property
    def negated_frames(self) -> tuple[FrameMatch, ...]:
        return tuple(item for item in self.frames if item.negated)

    @property
    def hedged_frames(self) -> tuple[FrameMatch, ...]:
        return tuple(item for item in self.frames if item.hedge)

    @property
    def asserted_frames(self) -> tuple[FrameMatch, ...]:
        return tuple(item for item in self.frames if not item.negated and not item.hedge)

    @property
    def frame_kinds(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.kind for item in self.asserted_frames))

    @property
    def scanned(self) -> bool:
        """True when the pattern saw the predicate at all, in any form.

        Distinguishes "no guarantee vocabulary here" from "guarantee vocabulary
        present but negated or hedged". Those are different findings and a
        report that merges them cannot tell a rule that works from one that
        silently never runs.
        """

        return bool(self.frames)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "category": self.category,
            "confidence": self.confidence,
            "fired": self.fired,
            "scanned": self.scanned,
            "frame_kinds": list(self.frame_kinds),
            "frames": [item.as_dict() for item in self.frames],
            "entities": [item.as_dict() for item in self.entities],
            "evidence": self.evidence,
        }

    def render(self) -> str:
        state = "fired" if self.fired else ("scanned" if self.scanned else "silent")
        lines = [f"{self.pattern_id} [{self.category}] {state}"]
        for frame in self.frames:
            lines.append(f"    {frame.render()}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class PatternSet:
    """A named collection of patterns and the lexicon they use."""

    name: str
    lexicon: EntityLexicon
    patterns: tuple[IntentPattern, ...]
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.patterns:
            raise PatternError(f"{self.name}: at least one pattern is required")
        for pattern in self.patterns:
            for name in pattern.required_entities:
                if name not in self.lexicon:
                    raise PatternError(
                        f"{pattern.pattern_id}: unknown entity type {name!r}"
                    )

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(p.category for p in self.patterns))

    def for_category(self, category: str) -> tuple[IntentPattern, ...]:
        return tuple(p for p in self.patterns if p.category == category)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "categories": list(self.categories),
            "entities": {name: self.lexicon.get(name).as_dict() for name in self.lexicon.names()},
            "patterns": [pattern.as_dict() for pattern in self.patterns],
        }


def frame_kinds_covered(pattern: IntentPattern) -> tuple[str, ...]:
    """Every frame kind the pattern can match, across its relations."""

    seen: dict[str, None] = {}
    for relation in pattern.relations:
        for kind in relation.kinds:
            seen.setdefault(kind, None)
    return tuple(seen)
