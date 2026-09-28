"""Evaluation metrics for the M3 validation (Phase 9).

Reports the metrics the brief requires, and deliberately not "accuracy" alone —
a single number hides which of the two failure modes is happening, and for
template discovery the two are not symmetric.

Reported
--------

**Detection** — precision, recall, F1 for layout-family detection, micro-averaged
over families, plus a confusion summary. A false positive here means a sample
whose template was never used is claimed to use it.

**Clustering** — pairwise precision, recall, F1 over same-family pairs. Pairwise
counting is the right lens for clustering because it is independent of cluster
labelling: it does not care what the clusters are called, only whether pairs that
belong together ended up together.

**Pattern** — agreement between the distilled pattern and the ground-truth
template group. This is *not* human agreement in the strong sense: no human
rater scored these outputs. It is an automated agreement measure, and the report
says so rather than claiming human validation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


def _safe_ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return round(2 * precision * recall / (precision + recall), 6) if (precision + recall) else 0.0


@dataclass(frozen=True, slots=True)
class DetectionMetrics:
    """Per-family and micro-averaged layout detection."""

    per_family: Mapping[str, Mapping[str, Any]]
    micro_precision: float
    micro_recall: float
    micro_f1: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    correct: int
    total: int
    confusion: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    undetected: tuple[str, ...] = ()

    @property
    def labelled_accuracy(self) -> float:
        return _safe_ratio(self.correct, self.total)

    def as_dict(self) -> dict[str, Any]:
        return {
            "per_family": {name: dict(values) for name, values in sorted(self.per_family.items())},
            "micro": {
                "precision": self.micro_precision,
                "recall": self.micro_recall,
                "f1": self.micro_f1,
            },
            "macro": {
                "precision": self.macro_precision,
                "recall": self.macro_recall,
                "f1": self.macro_f1,
            },
            "correct": self.correct,
            "total": self.total,
            "labelled_accuracy": self.labelled_accuracy,
            "confusion": {
                actual: dict(counts) for actual, counts in sorted(self.confusion.items())
            },
            "undetected_samples": list(self.undetected),
        }

    def render(self) -> str:
        lines = [
            f"detection: {self.correct}/{self.total} labelled "
            f"(accuracy {self.labelled_accuracy:.3f})",
            f"  micro  P={self.micro_precision:.3f} R={self.micro_recall:.3f} "
            f"F1={self.micro_f1:.3f}",
            f"  macro  P={self.macro_precision:.3f} R={self.macro_recall:.3f} "
            f"F1={self.macro_f1:.3f}",
        ]
        for name, values in sorted(self.per_family.items()):
            lines.append(
                f"    {name:<22} P={values['precision']:.3f} "
                f"R={values['recall']:.3f} F1={values['f1']:.3f} "
                f"(tp={values['true_positive']} fp={values['false_positive']} "
                f"fn={values['false_negative']})"
            )
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ClusteringMetrics:
    """Pairwise clustering agreement against ground-truth template identity."""

    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    f1: float
    cluster_count: int
    recurring_count: int
    sample_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "pairwise": {
                "true_positive": self.true_positive,
                "false_positive": self.false_positive,
                "true_negative": self.true_negative,
                "false_negative": self.false_negative,
                "precision": self.precision,
                "recall": self.recall,
                "f1": self.f1,
            },
            "cluster_count": self.cluster_count,
            "recurring_count": self.recurring_count,
            "sample_count": self.sample_count,
        }

    def render(self) -> str:
        return (
            f"clustering: pairwise P={self.precision:.3f} R={self.recall:.3f} "
            f"F1={self.f1:.3f}\n"
            f"  tp={self.true_positive} fp={self.false_positive} "
            f"tn={self.true_negative} fn={self.false_negative}\n"
            f"  clusters={self.cluster_count} (recurring {self.recurring_count}) "
            f"over {self.sample_count} samples"
        )


@dataclass(frozen=True, slots=True)
class PatternMetrics:
    """Agreement between distilled patterns and ground-truth template groups."""

    pattern_count: int
    matched_groups: int
    total_groups: int
    agreement: float
    purity: float
    coverage: float
    per_pattern: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern_count": self.pattern_count,
            "matched_groups": self.matched_groups,
            "total_groups": self.total_groups,
            "group_agreement": self.agreement,
            "purity": self.purity,
            "coverage": self.coverage,
            "per_pattern": {
                name: dict(values) for name, values in sorted(self.per_pattern.items())
            },
            "measurement_note": (
                "automated agreement against ground-truth template groups; no human "
                "rater scored these outputs, so this is not human agreement"
            ),
        }

    def render(self) -> str:
        return (
            f"pattern: {self.pattern_count} distilled, "
            f"groups recovered {self.matched_groups}/{self.total_groups} "
            f"(agreement {self.agreement:.3f})\n"
            f"  purity={self.purity:.3f} coverage={self.coverage:.3f}"
        )


def detection_metrics(
    predictions: Mapping[str, str | None],
    ground_truth: Mapping[str, str],
) -> DetectionMetrics:
    """Micro- and macro-averaged detection metrics over layout families.

    Detection here means: for each sample, was its layout class correctly
    asserted. A ``None`` prediction counts as a miss rather than being dropped,
    so an observer that refuses to classify cannot score well by abstaining.

    Predicted classes are included in the family universe even when no
    ground-truth sample carries them. The observer may legitimately report a
    broader layout class that the corpus labels subdivide — several distinct
    templates can share one arrangement — and a prediction outside the label set
    is a genuine false positive that must be counted, not crash the metric.
    """

    families = sorted(set(ground_truth.values()) | {p for p in predictions.values() if p})
    counts: dict[str, Counter] = {family: Counter() for family in families}
    confusion: dict[str, Counter] = {}
    correct = 0
    undetected: list[str] = []

    for sample_id, actual in ground_truth.items():
        predicted = predictions.get(sample_id)
        confusion.setdefault(actual, Counter())
        if predicted is None:
            undetected.append(sample_id)
            confusion[actual]["<undetected>"] += 1
            for family in families:
                if family == actual:
                    counts[family]["false_negative"] += 1
                else:
                    counts[family]["true_negative"] += 1
            continue

        confusion[actual][predicted] += 1
        if predicted == actual:
            correct += 1
            counts[actual]["true_positive"] += 1
            for family in families:
                if family != actual:
                    counts[family]["true_negative"] += 1
        else:
            counts[predicted]["false_positive"] += 1
            counts[actual]["false_negative"] += 1
            for family in families:
                if family not in {predicted, actual}:
                    counts[family]["true_negative"] += 1

    per_family: dict[str, dict[str, Any]] = {}
    precisions: list[float] = []
    recalls: list[float] = []
    total_tp = total_fp = total_fn = 0

    for family in families:
        counter = counts[family]
        tp = counter["true_positive"]
        fp = counter["false_positive"]
        fn = counter["false_negative"]
        total_tp += tp
        total_fp += fp
        total_fn += fn
        precision = _safe_ratio(tp, tp + fp)
        recall = _safe_ratio(tp, tp + fn)
        per_family[family] = {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_negative": counter["true_negative"],
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
            "support": sum(1 for value in ground_truth.values() if value == family),
        }
        precisions.append(precision)
        recalls.append(recall)

    micro_precision = _safe_ratio(total_tp, total_tp + total_fp)
    micro_recall = _safe_ratio(total_tp, total_tp + total_fn)
    macro_precision = round(sum(precisions) / len(precisions), 6) if precisions else 0.0
    macro_recall = round(sum(recalls) / len(recalls), 6) if recalls else 0.0

    return DetectionMetrics(
        per_family=per_family,
        micro_precision=micro_precision,
        micro_recall=micro_recall,
        micro_f1=_f1(micro_precision, micro_recall),
        macro_precision=macro_precision,
        macro_recall=macro_recall,
        macro_f1=_f1(macro_precision, macro_recall),
        correct=correct,
        total=len(ground_truth),
        confusion={actual: dict(counts) for actual, counts in confusion.items()},
        undetected=tuple(sorted(undetected)),
    )


def clustering_metrics(
    membership: Mapping[str, str],
    ground_truth: Mapping[str, str],
    *,
    recurring_cluster_ids: Sequence[str] = (),
) -> ClusteringMetrics:
    """Pairwise precision/recall/F1 of discovered clusters vs true families.

    Pairs involving a sample with no cluster are counted as negatives rather than
    excluded, so leaving samples unclustered is penalised as a miss rather than
    improving precision by omission.
    """

    sample_ids = sorted(set(ground_truth) & set(membership))
    true_positive = false_positive = true_negative = false_negative = 0

    for index, left in enumerate(sample_ids):
        for right in sample_ids[index + 1 :]:
            same_true = ground_truth[left] == ground_truth[right]
            left_cluster = membership.get(left)
            right_cluster = membership.get(right)
            same_predicted = (
                left_cluster is not None
                and right_cluster is not None
                and left_cluster == right_cluster
            )
            if same_true and same_predicted:
                true_positive += 1
            elif not same_true and same_predicted:
                false_positive += 1
            elif not same_true and not same_predicted:
                true_negative += 1
            else:
                false_negative += 1

    precision = _safe_ratio(true_positive, true_positive + false_positive)
    recall = _safe_ratio(true_positive, true_positive + false_negative)
    clusters = {value for value in membership.values() if value is not None}
    return ClusteringMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        true_negative=true_negative,
        false_negative=false_negative,
        precision=precision,
        recall=recall,
        f1=_f1(precision, recall),
        cluster_count=len(clusters),
        recurring_count=len(set(recurring_cluster_ids)),
        sample_count=len(sample_ids),
    )


def pattern_metrics(
    patterns: Sequence[Any],
    ground_truth: Mapping[str, str],
) -> PatternMetrics:
    """Agreement between distilled patterns and ground-truth template groups.

    ``purity`` is the mean fraction of a pattern's members sharing one true
    template; ``coverage`` is the fraction of ground-truth groups that some
    pattern accounts for. Both are needed: a pattern can be pure but tiny, or
    broad but mixed.
    """

    per_pattern: dict[str, dict[str, Any]] = {}
    recovered: set[str] = set()

    for pattern in patterns:
        members = [member for member in pattern.member_ids if member in ground_truth]
        if not members:
            continue
        counts = Counter(ground_truth[member] for member in members)
        dominant, dominant_count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
        purity = _safe_ratio(dominant_count, len(members))
        recovered.add(dominant)
        per_pattern[pattern.pattern_id] = {
            "support": len(members),
            "dominant_template": dominant,
            "purity": purity,
            "template_counts": dict(sorted(counts.items())),
            "layout_strategy": list(pattern.layout_strategy),
            "hierarchy": list(pattern.hierarchy),
        }

    total_groups = len(set(ground_truth.values()))
    matched = len(recovered)
    purities = [entry["purity"] for entry in per_pattern.values()]
    covered_samples = sum(
        1
        for sample_id in ground_truth
        if any(sample_id in pattern.member_ids for pattern in patterns)
    )

    return PatternMetrics(
        pattern_count=len(per_pattern),
        matched_groups=matched,
        total_groups=total_groups,
        agreement=_safe_ratio(matched, total_groups),
        purity=round(sum(purities) / len(purities), 6) if purities else 0.0,
        coverage=_safe_ratio(covered_samples, len(ground_truth)),
        per_pattern=per_pattern,
    )


@dataclass(frozen=True, slots=True)
class EvaluationBundle:
    """All three metric families for one run."""

    detection: DetectionMetrics
    clustering: ClusteringMetrics
    pattern: PatternMetrics

    def as_dict(self) -> dict[str, Any]:
        return {
            "detection": self.detection.as_dict(),
            "clustering": self.clustering.as_dict(),
            "pattern": self.pattern.as_dict(),
        }

    def render(self) -> str:
        return "\n\n".join(
            [
                self.detection.render(),
                self.clustering.render(),
                self.pattern.render(),
            ]
        )


__all__ = [
    "ClusteringMetrics",
    "DetectionMetrics",
    "EvaluationBundle",
    "PatternMetrics",
    "clustering_metrics",
    "detection_metrics",
    "pattern_metrics",
]
