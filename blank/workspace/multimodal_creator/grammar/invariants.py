"""Invariant discovery (Phase M4, phase 5).

Given a cluster of grammars, find the features they **agree on**. The contract's
example is the target behaviour:

    20 images in, and the result is
      90%: headline top
      85%: subject center
      80%: CTA bottom

Two hard rules, both enforced in code rather than promised in prose:

**Nothing is specified by hand.** Every invariant is *mined* from the observed
feature frequencies. There is no allow-list of interesting patterns, no seeded
candidate set, and no per-cluster special case. A test asserts the extractor's
source contains no literal relation or region-type name.

**Frequency is reported, not thresholded away.** The extractor returns every
feature with its support. Choosing which of them count as invariants is a
separate, explicit decision made by the caller, so the evidence survives even
when the cut does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .model import ATTENTION_STAGES, REGION_TYPES, VisualGrammar

#: Default support level at which a feature is called an invariant.
DEFAULT_INVARIANT_THRESHOLD = 0.8

#: Feature families. Kept separate because they mean different things: a region
#: *presence* invariant is a claim about what is always there, a *relation*
#: invariant is a claim about arrangement.
FEATURE_FAMILIES: tuple[str, ...] = (
    "region_presence",
    "region_placement",
    "region_density",
    "region_dominance",
    "relation_presence",
    "attention_flow",
)


class InvariantError(Exception):
    """Raised when invariants cannot be mined."""


@dataclass(frozen=True, slots=True)
class Invariant:
    """One feature and how often the cluster exhibits it."""

    feature_family: str
    feature: str
    frequency: float
    support: int
    total: int
    detail: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.feature_family not in FEATURE_FAMILIES:
            raise InvariantError(f"unknown feature family {self.feature_family!r}")
        if not 0.0 <= self.frequency <= 1.0:
            raise InvariantError(f"frequency must be within 0..1, got {self.frequency!r}")
        if self.total <= 0:
            raise InvariantError("total must be positive")
        if not 0 <= self.support <= self.total:
            raise InvariantError(
                f"support {self.support} is outside 0..{self.total}"
            )

    @property
    def key(self) -> str:
        return f"{self.feature_family}:{self.feature}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_family": self.feature_family,
            "feature": self.feature,
            "frequency": self.frequency,
            "support": self.support,
            "total": self.total,
            "detail": dict(self.detail),
        }

    def render(self) -> str:
        return f"{self.frequency:5.0%}: {self.feature}"


@dataclass(frozen=True, slots=True)
class InvariantSet:
    """All mined features for one cluster, plus the ones above threshold."""

    cluster_id: str
    member_count: int
    threshold: float
    invariants: tuple[Invariant, ...]
    all_features: tuple[Invariant, ...] = ()

    def __post_init__(self) -> None:
        if self.member_count <= 0:
            raise InvariantError("a cluster must have at least one member")
        if not 0.0 < self.threshold <= 1.0:
            raise InvariantError("threshold must be within (0, 1]")

    def by_family(self, family: str) -> tuple[Invariant, ...]:
        return tuple(item for item in self.invariants if item.feature_family == family)

    def features(self) -> tuple[str, ...]:
        return tuple(item.feature for item in self.invariants)

    def frequency_of(self, feature: str) -> float:
        """Frequency of a feature, accepting either key form.

        Callers may pass the bare feature name (``background_present``) or the
        family-qualified key (``region_presence:background_present``). Both are
        accepted because both are natural to write, and silently returning 0.0 for
        the qualified form — as an earlier version did — turns a naming mismatch
        into what looks like a measurement of zero.
        """

        for item in self.all_features:
            if item.feature == feature or item.key == feature:
                return item.frequency
        return 0.0

    def support_of(self, feature: str) -> int:
        for item in self.all_features:
            if item.feature == feature or item.key == feature:
                return item.support
        return 0

    def strongest(self, count: int = 3) -> tuple[Invariant, ...]:
        return tuple(
            sorted(
                self.invariants,
                key=lambda item: (-item.frequency, item.key),
            )[:count]
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "member_count": self.member_count,
            "threshold": self.threshold,
            "invariants": [item.as_dict() for item in self.invariants],
            "all_feature_count": len(self.all_features),
            "all_features": [item.as_dict() for item in self.all_features],
        }

    def render(self) -> str:
        lines = [
            f"invariants for {self.cluster_id}: {len(self.invariants)} above "
            f"{self.threshold:.0%} over {self.member_count} members"
        ]
        for family in FEATURE_FAMILIES:
            items = self.by_family(family)
            if not items:
                continue
            lines.append(f"  {family}:")
            for item in items:
                lines.append(f"    {item.render()}")
        return "\n".join(lines)


def _features_of(grammar: VisualGrammar) -> list[tuple[str, str, Mapping[str, Any]]]:
    """Every feature one grammar exhibits, as ``(family, feature, detail)``.

    Features are deliberately *discrete and readable* rather than embedded. An
    invariant a human cannot read is an invariant a human cannot check, which is
    the failure mode M4 exists to avoid.
    """

    features: list[tuple[str, str, Mapping[str, Any]]] = []

    for region in grammar.regions:
        features.append(
            (
                "region_presence",
                f"{region.region_type}_present",
                {"region_id": region.region_id},
            )
        )
        features.append(
            (
                "region_placement",
                f"{region.region_type}_{region.position_band}_{region.column_band}",
                {"region_id": region.region_id},
            )
        )
        features.append(
            (
                "region_density",
                f"{region.region_type}_{region.density}",
                {"region_id": region.region_id},
            )
        )
        features.append(
            (
                "region_dominance",
                f"{region.region_type}_{region.dominance}",
                {"region_id": region.region_id},
            )
        )

    for relation in grammar.relationships:
        features.append(
            (
                "relation_presence",
                relation.relation_type,
                {
                    "source": relation.source_region_id,
                    "target": relation.target_region_id,
                    "strength": relation.strength,
                },
            )
        )

    signature = "->".join(grammar.attention_signature())
    if signature:
        features.append(("attention_flow", signature, {}))

    return features


class InvariantExtractor:
    """Mine the features a set of grammars agree on.

    Pure and deterministic: features are counted with a stable ordering
    throughout, so a cluster always yields the same invariants in the same order.
    """

    def __init__(self, *, threshold: float = DEFAULT_INVARIANT_THRESHOLD) -> None:
        if not 0.0 < threshold <= 1.0:
            raise InvariantError("threshold must be within (0, 1]")
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    def extract(
        self,
        grammars: Sequence[VisualGrammar],
        *,
        cluster_id: str,
        threshold: float | None = None,
    ) -> InvariantSet:
        if not grammars:
            raise InvariantError("cannot mine invariants from no grammars")
        cut = self._threshold if threshold is None else threshold
        if not 0.0 < cut <= 1.0:
            raise InvariantError("threshold must be within (0, 1]")

        total = len(grammars)
        counts: dict[tuple[str, str], int] = {}
        details: dict[tuple[str, str], Mapping[str, Any]] = {}

        for grammar in grammars:
            # Count each (family, feature) once per grammar: an invariant is about
            # how many *members* exhibit a feature, not how many times it occurs.
            seen: dict[tuple[str, str], Mapping[str, Any]] = {}
            for family, feature, detail in _features_of(grammar):
                seen.setdefault((family, feature), detail)
            for key, detail in seen.items():
                counts[key] = counts.get(key, 0) + 1
                details.setdefault(key, detail)

        all_features = [
            Invariant(
                feature_family=family,
                feature=feature,
                frequency=round(count / total, 6),
                support=count,
                total=total,
                detail=dict(details.get((family, feature), {})),
            )
            for (family, feature), count in counts.items()
        ]
        # Deterministic: strongest first, then family, then feature name.
        all_features.sort(key=lambda item: (-item.frequency, item.feature_family, item.feature))

        invariants = tuple(item for item in all_features if item.frequency >= cut)
        return InvariantSet(
            cluster_id=cluster_id,
            member_count=total,
            threshold=cut,
            invariants=invariants,
            all_features=tuple(all_features),
        )


def invariant_features(invariant_set: InvariantSet) -> tuple[str, ...]:
    """Feature names above threshold, for use as a structural signature."""

    return invariant_set.features()


def summarise_invariants(sets: Iterable[InvariantSet]) -> str:
    """Render several invariant sets as one report block."""

    rendered = [item.render() for item in sets]
    return "\n\n".join(rendered) if rendered else "no invariant sets"


__all__ = [
    "DEFAULT_INVARIANT_THRESHOLD",
    "FEATURE_FAMILIES",
    "Invariant",
    "InvariantError",
    "InvariantExtractor",
    "InvariantSet",
    "invariant_features",
    "summarise_invariants",
]
