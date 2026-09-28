"""Grammar evaluation metrics (Phase M4, phase 9).

M3 reported a single accuracy figure for a single label. M4 reports four
different things, because they fail in different ways:

**Grammar** — region accuracy: did the extractor find the regions that are there,
and type them correctly?
**Relation** — precision and recall over extracted relations.
**Pattern** — strategy soundness, measured against human judgement via
:mod:`multimodal_creator.dataset.human_eval` when raters exist.
**Discovery** — stability: does the same input produce the same clusters, and
does a marginally perturbed input still produce them?

Stability is reported separately from accuracy on purpose. A method that is
accurate once but produces different answers on re-run cannot be built on, and a
single accuracy number would hide that entirely.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .model import VisualGrammar
from .strategy import CreatorStrategyPattern


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return round(2 * precision * recall / (precision + recall), 6) if (precision + recall) else 0.0


@dataclass(frozen=True, slots=True)
class RegionAccuracy:
    """How well extracted regions match the expected regions."""

    expected: int
    found: int
    correct_type: int
    correct_placement: int
    precision: float
    recall: float
    f1: float
    type_accuracy: float
    placement_accuracy: float
    per_type: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    missing: tuple[str, ...] = ()
    spurious: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected,
            "found": self.found,
            "correct_type": self.correct_type,
            "correct_placement": self.correct_placement,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "type_accuracy": self.type_accuracy,
            "placement_accuracy": self.placement_accuracy,
            "per_type": {k: dict(v) for k, v in sorted(self.per_type.items())},
            "missing": list(self.missing),
            "spurious": list(self.spurious),
        }

    def render(self) -> str:
        return (
            f"grammar regions: P={self.precision:.3f} R={self.recall:.3f} "
            f"F1={self.f1:.3f} | type_acc={self.type_accuracy:.3f} "
            f"placement_acc={self.placement_accuracy:.3f} "
            f"(expected {self.expected}, found {self.found})"
        )


@dataclass(frozen=True, slots=True)
class RelationMetrics:
    """Precision and recall over extracted relations."""

    expected: int
    found: int
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float
    per_relation: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected,
            "found": self.found,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "per_relation": {
                k: dict(v) for k, v in sorted(self.per_relation.items())
            },
        }

    def render(self) -> str:
        return (
            f"grammar relations: P={self.precision:.3f} R={self.recall:.3f} "
            f"F1={self.f1:.3f} (tp={self.true_positive} fp={self.false_positive} "
            f"fn={self.false_negative})"
        )


@dataclass(frozen=True, slots=True)
class StabilityMetrics:
    """Reproducibility of discovery under repetition and perturbation."""

    runs: int
    identical_runs: int
    repetition_rate: float
    perturbed_runs: int
    stable_under_perturbation: int
    perturbation_rate: float
    baseline_cluster_count: int
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "identical_runs": self.identical_runs,
            "repetition_rate": self.repetition_rate,
            "perturbed_runs": self.perturbed_runs,
            "stable_under_perturbation": self.stable_under_perturbation,
            "perturbation_rate": self.perturbation_rate,
            "baseline_cluster_count": self.baseline_cluster_count,
            "notes": list(self.notes),
        }

    def render(self) -> str:
        return (
            f"discovery stability: repetition={self.repetition_rate:.3f} "
            f"({self.identical_runs}/{self.runs}) "
            f"perturbation={self.perturbation_rate:.3f} "
            f"({self.stable_under_perturbation}/{self.perturbed_runs})"
        )


@dataclass(frozen=True, slots=True)
class StrategyMetrics:
    """Agreement between distilled strategy and reference strategy."""

    patterns: int
    attention_matches: int
    hierarchy_matches: int
    composition_jaccard: float
    attention_accuracy: float
    hierarchy_accuracy: float
    measurement_note: str = (
        "agreement is measured against reference labels; when those labels come "
        "from human raters this is human agreement, and the report must say which"
    )

    def as_dict(self) -> dict[str, Any]:
        return {
            "patterns": self.patterns,
            "attention_matches": self.attention_matches,
            "hierarchy_matches": self.hierarchy_matches,
            "composition_jaccard": self.composition_jaccard,
            "attention_accuracy": self.attention_accuracy,
            "hierarchy_accuracy": self.hierarchy_accuracy,
            "measurement_note": self.measurement_note,
        }

    def render(self) -> str:
        return (
            f"strategy: attention_acc={self.attention_accuracy:.3f} "
            f"hierarchy_acc={self.hierarchy_accuracy:.3f} "
            f"composition_jaccard={self.composition_jaccard:.3f} "
            f"over {self.patterns} patterns"
        )


# --------------------------------------------------------------------------
# Metric computations
# --------------------------------------------------------------------------


def region_accuracy(
    found: VisualGrammar,
    expected: Mapping[str, Any],
) -> RegionAccuracy:
    """Compare an extracted grammar's regions against an expectation.

    ``expected`` is ``{"regions": [{"region_type": ..., "position_band": ...,
    "column_band": ...}, ...]}``. Region identity is not compared: two
    observations may segment the same composition into differently-identified
    regions, and what matters is whether the *types and placements* are right.
    """

    expected_regions = list(expected.get("regions", ()))
    expected_keys = Counter(
        (str(item["region_type"]), str(item.get("position_band", ""))) for item in expected_regions
    )
    found_keys = Counter(
        (region.region_type, region.position_band) for region in found.regions
    )

    true_positive = sum((expected_keys & found_keys).values())
    false_positive = sum(found_keys.values()) - true_positive
    false_negative = sum(expected_keys.values()) - true_positive

    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)

    # Type accuracy and placement accuracy are reported separately, because a
    # right type in the wrong place and a wrong type in the right place are
    # different failures with different fixes.
    type_hits = sum(
        1
        for item in expected_regions
        if any(
            region.region_type == item["region_type"] for region in found.regions
        )
    )
    placement_hits = sum(
        1
        for item in expected_regions
        if any(
            region.region_type == item["region_type"]
            and region.position_band == item.get("position_band")
            for region in found.regions
        )
    )

    per_type: dict[str, dict[str, Any]] = {}
    for region_type in sorted({key[0] for key in expected_keys} | {key[0] for key in found_keys}):
        expected_count = sum(
            count for (name, _band), count in expected_keys.items() if name == region_type
        )
        found_count = sum(
            count for (name, _band), count in found_keys.items() if name == region_type
        )
        matched = sum(
            min(expected_keys.get((region_type, band), 0), found_keys.get((region_type, band), 0))
            for band in {b for (n, b) in expected_keys | found_keys if n == region_type}
        )
        per_type[region_type] = {
            "expected": expected_count,
            "found": found_count,
            "matched": matched,
        }

    missing = tuple(
        sorted(
            f"{name}@{band}"
            for (name, band), count in expected_keys.items()
            if found_keys.get((name, band), 0) < count
        )
    )
    spurious = tuple(
        sorted(
            f"{name}@{band}"
            for (name, band), count in found_keys.items()
            if expected_keys.get((name, band), 0) < count
        )
    )

    return RegionAccuracy(
        expected=sum(expected_keys.values()),
        found=sum(found_keys.values()),
        correct_type=type_hits,
        correct_placement=placement_hits,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
        type_accuracy=_ratio(type_hits, len(expected_regions)),
        placement_accuracy=_ratio(placement_hits, len(expected_regions)),
        per_type=per_type,
        missing=missing,
        spurious=spurious,
    )


def relation_metrics(
    found: VisualGrammar,
    expected_relations: Sequence[str],
) -> RelationMetrics:
    """Precision and recall over relation *types*.

    Types, not endpoints: relation endpoints depend on region identity, which the
    evaluator explicitly does not compare. Scoring endpoints would punish a
    correct extraction for naming its regions differently.
    """

    expected_set = set(str(name) for name in expected_relations)
    found_set = set(found.relation_types())

    true_positive = len(expected_set & found_set)
    false_positive = len(found_set - expected_set)
    false_negative = len(expected_set - found_set)

    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)

    per_relation: dict[str, dict[str, Any]] = {}
    for name in sorted(expected_set | found_set):
        per_relation[name] = {
            "expected": name in expected_set,
            "found": name in found_set,
        }

    return RelationMetrics(
        expected=len(expected_set),
        found=len(found_set),
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
        per_relation=per_relation,
    )


def stability_metrics(
    baseline: Sequence[tuple[str, ...]],
    repeats: Sequence[Sequence[tuple[str, ...]]],
    perturbed: Sequence[Sequence[tuple[str, ...]]] = (),
    *,
    notes: Sequence[str] = (),
) -> StabilityMetrics:
    """Compare cluster structures across repeated and perturbed runs.

    A cluster structure is represented as a sequence of sorted member-id tuples,
    so comparison is independent of cluster naming — the same partition under
    different generated ids still counts as identical.
    """

    def normalise(structure: Sequence[Sequence[str]]) -> tuple[tuple[str, ...], ...]:
        return tuple(sorted(tuple(sorted(cluster)) for cluster in structure))

    baseline_key = normalise(baseline)
    identical = sum(1 for run in repeats if normalise(run) == baseline_key)
    stable = sum(1 for run in perturbed if normalise(run) == baseline_key)

    return StabilityMetrics(
        runs=len(repeats),
        identical_runs=identical,
        repetition_rate=_ratio(identical, len(repeats)),
        perturbed_runs=len(perturbed),
        stable_under_perturbation=stable,
        perturbation_rate=_ratio(stable, len(perturbed)),
        baseline_cluster_count=len(baseline_key),
        notes=tuple(notes),
    )


def strategy_metrics(
    patterns: Sequence[CreatorStrategyPattern],
    reference: Mapping[str, Mapping[str, Any]],
) -> StrategyMetrics:
    """Compare distilled strategies against reference strategies.

    ``reference`` maps ``pattern_id`` to
    ``{"attention_strategy": ..., "information_hierarchy": [...]}``.
    """

    attention_matches = 0
    hierarchy_matches = 0
    jaccards: list[float] = []
    compared = 0

    for pattern in patterns:
        expected = reference.get(pattern.pattern_id)
        if expected is None:
            continue
        compared += 1
        if pattern.attention_strategy == expected.get("attention_strategy"):
            attention_matches += 1
        expected_hierarchy = set(expected.get("information_hierarchy") or ())
        found_hierarchy = set(pattern.information_hierarchy)
        if found_hierarchy == expected_hierarchy:
            hierarchy_matches += 1
        expected_moves = set(expected.get("composition_strategy") or ())
        found_moves = set(pattern.composition_strategy)
        union = expected_moves | found_moves
        jaccards.append(len(expected_moves & found_moves) / len(union) if union else 1.0)

    return StrategyMetrics(
        patterns=compared,
        attention_matches=attention_matches,
        hierarchy_matches=hierarchy_matches,
        composition_jaccard=round(sum(jaccards) / len(jaccards), 6) if jaccards else 0.0,
        attention_accuracy=_ratio(attention_matches, compared),
        hierarchy_accuracy=_ratio(hierarchy_matches, compared),
    )


@dataclass(frozen=True, slots=True)
class EvaluationBundle:
    """All grammar-level metrics for one run."""

    region: RegionAccuracy
    relation: RelationMetrics
    stability: StabilityMetrics
    strategy: StrategyMetrics

    def as_dict(self) -> dict[str, Any]:
        return {
            "grammar_regions": self.region.as_dict(),
            "grammar_relations": self.relation.as_dict(),
            "discovery_stability": self.stability.as_dict(),
            "strategy": self.strategy.as_dict(),
        }

    def render(self) -> str:
        return "\n".join(
            [
                self.region.render(),
                self.relation.render(),
                self.stability.render(),
                self.strategy.render(),
            ]
        )


__all__ = [
    "EvaluationBundle",
    "RegionAccuracy",
    "RelationMetrics",
    "StabilityMetrics",
    "StrategyMetrics",
    "region_accuracy",
    "relation_metrics",
    "stability_metrics",
    "strategy_metrics",
]
