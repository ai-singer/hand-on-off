"""Similarity calibration on real observations (Phase M3, phase 6).

M2 shipped ``threshold = 0.90`` calibrated on synthetic *declared* structure. The
phase brief is explicit that this number must not be carried over: a threshold is
a property of the measurement distribution, and M3 measures a different
distribution — one produced by decoding pixels.

This module re-measures. It partitions every pair into the four provenance
quadrants the brief requires, reports mean / median / min / max for each, and
derives a threshold from the observed separation rather than assuming one.

How the threshold is chosen
---------------------------

The decision uses **Youden's J statistic** (``sensitivity + specificity - 1``)
swept over candidate cut points. That is the standard way to pick a cut point
when the two error types matter differently and the classes are imbalanced, which
is exactly the situation here:

* a false merge invents a template that does not exist, and
* a false split hides one that does.

Youden's J maximises their sum, and the exact midpoint of the widest empty band is
reported alongside it as a transparency check. If the two disagree, the report
says so rather than quietly preferring one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..similarity.similarity_contract import SimilarityResult, pairwise_similarity

#: The four quadrants the calibration must report.
QUADRANTS: tuple[str, ...] = (
    "same_creator_same_template",
    "same_creator_different_template",
    "different_creator_same_template",
    "different_creator_different_template",
)

#: Quadrants whose pairs are positive examples of "same visual template".
POSITIVE_QUADRANTS: frozenset[str] = frozenset(
    {"same_creator_same_template", "different_creator_same_template"}
)

#: Quadrants whose pairs are negatives.
NEGATIVE_QUADRANTS: frozenset[str] = frozenset(
    {"same_creator_different_template", "different_creator_different_template"}
)

#: M2's threshold, reported for comparison and explicitly not reused.
M2_SYNTHETIC_THRESHOLD = 0.90


class CalibrationError(Exception):
    """Raised when calibration cannot be performed."""


@dataclass(frozen=True, slots=True)
class QuadrantStats:
    """Distribution of similarity within one quadrant."""

    quadrant: str
    count: int
    mean: float
    median: float
    minimum: float
    maximum: float
    p10: float
    p90: float
    scores: tuple[float, ...] = ()

    @staticmethod
    def _percentile(ordered: Sequence[float], fraction: float) -> float:
        if not ordered:
            return 0.0
        index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
        return ordered[index]

    @classmethod
    def from_scores(cls, quadrant: str, scores: Sequence[float]) -> "QuadrantStats":
        if not scores:
            return cls(quadrant, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ())
        ordered = sorted(scores)
        count = len(ordered)
        return cls(
            quadrant=quadrant,
            count=count,
            mean=round(sum(ordered) / count, 6),
            median=round(cls._percentile(ordered, 0.5), 6),
            minimum=round(ordered[0], 6),
            maximum=round(ordered[-1], 6),
            p10=round(cls._percentile(ordered, 0.10), 6),
            p90=round(cls._percentile(ordered, 0.90), 6),
            scores=tuple(round(score, 6) for score in ordered),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "quadrant": self.quadrant,
            "count": self.count,
            "mean": self.mean,
            "median": self.median,
            "min": self.minimum,
            "max": self.maximum,
            "p10": self.p10,
            "p90": self.p90,
        }


@dataclass(frozen=True, slots=True)
class ThresholdCandidate:
    """One candidate cut point and its confusion counts."""

    threshold: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int

    @property
    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return round(self.true_positive / denominator, 6) if denominator else 0.0

    @property
    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return round(self.true_positive / denominator, 6) if denominator else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return round(2 * p * r / (p + r), 6) if (p + r) else 0.0

    @property
    def youden_j(self) -> float:
        """Sensitivity + specificity - 1."""

        positives = self.true_positive + self.false_negative
        negatives = self.true_negative + self.false_positive
        sensitivity = self.true_positive / positives if positives else 0.0
        specificity = self.true_negative / negatives if negatives else 0.0
        return round(sensitivity + specificity - 1.0, 6)

    def as_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "false_negative": self.false_negative,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "youden_j": self.youden_j,
        }


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """The full calibration result, serialisable to ``similarity_distribution.json``."""

    quadrants: Mapping[str, QuadrantStats]
    recommended_threshold: float
    selection_method: str
    candidates: tuple[ThresholdCandidate, ...]
    separation_gap: float
    separation_midpoint: float | None
    overlap: bool
    pair_count: int
    dataset_id: str
    backend_id: str
    m2_threshold_for_reference: float = M2_SYNTHETIC_THRESHOLD
    notes: tuple[str, ...] = field(default_factory=tuple)

    def best_candidate(self) -> ThresholdCandidate:
        for candidate in self.candidates:
            if candidate.threshold == self.recommended_threshold:
                return candidate
        raise CalibrationError("recommended threshold is not among the candidates")

    def as_dict(self) -> dict[str, Any]:
        best = self.best_candidate()
        return {
            "schema": "similarity_distribution/v1",
            "dataset_id": self.dataset_id,
            "backend_id": self.backend_id,
            "pair_count": self.pair_count,
            "quadrants": {
                name: stats.as_dict() for name, stats in sorted(self.quadrants.items())
            },
            "recommended_threshold": self.recommended_threshold,
            "selection_method": self.selection_method,
            "recommended_candidate": best.as_dict(),
            "separation": {
                "gap": self.separation_gap,
                "midpoint": self.separation_midpoint,
                "classes_overlap": self.overlap,
            },
            "m2_synthetic_threshold_for_reference": self.m2_threshold_for_reference,
            "notes": list(self.notes),
        }

    def render(self) -> str:
        lines = [
            f"similarity calibration — {self.pair_count} pairs "
            f"({self.dataset_id}, backend={self.backend_id!r})",
            "",
            f"{'quadrant':<38} {'n':>4} {'mean':>6} {'med':>6} {'min':>6} {'max':>6}",
        ]
        for name in QUADRANTS:
            stats = self.quadrants.get(name)
            if stats is None or stats.count == 0:
                lines.append(f"{name:<38} {0:>4}      —      —      —      —")
                continue
            lines.append(
                f"{name:<38} {stats.count:>4} {stats.mean:>6.3f} {stats.median:>6.3f} "
                f"{stats.minimum:>6.3f} {stats.maximum:>6.3f}"
            )
        best = self.best_candidate()
        lines += [
            "",
            f"same-template min : "
            f"{min((self.quadrants[q].minimum for q in POSITIVE_QUADRANTS if self.quadrants.get(q) and self.quadrants[q].count), default=0.0):.3f}",
            f"different-template max : "
            f"{max((self.quadrants[q].maximum for q in NEGATIVE_QUADRANTS if self.quadrants.get(q) and self.quadrants[q].count), default=0.0):.3f}",
            f"separation gap : {self.separation_gap:.3f}"
            + (f" (midpoint {self.separation_midpoint:.3f})" if self.separation_midpoint else ""),
            f"classes overlap: {self.overlap}",
            "",
            f"recommended threshold: {self.recommended_threshold:.3f} "
            f"via {self.selection_method}",
            f"  precision={best.precision:.3f} recall={best.recall:.3f} "
            f"f1={best.f1:.3f} youden_j={best.youden_j:.3f}",
            f"  tp={best.true_positive} fp={best.false_positive} "
            f"tn={best.true_negative} fn={best.false_negative}",
            f"M2 synthetic threshold for reference: {self.m2_threshold_for_reference:.3f}",
        ]
        for note in self.notes:
            lines.append(f"note: {note}")
        return "\n".join(lines)


def quadrant_of(
    left_label: Mapping[str, Any], right_label: Mapping[str, Any]
) -> str:
    """Classify a pair into one of the four quadrants from ground truth."""

    same_creator = left_label.get("creator_id") == right_label.get("creator_id")
    same_template = left_label.get("template_id") == right_label.get("template_id")
    if same_creator and same_template:
        return "same_creator_same_template"
    if same_creator:
        return "same_creator_different_template"
    if same_template:
        return "different_creator_same_template"
    return "different_creator_different_template"


def _candidate_thresholds(scores: Sequence[float]) -> list[float]:
    """Cut points to sweep: just above each observed score, plus the extremes."""

    ordered = sorted(set(round(score, 6) for score in scores))
    candidates = {0.0, 1.0}
    for score in ordered:
        candidates.add(round(min(1.0, score + 1e-6), 6))
    return sorted(candidates)


def calibrate(
    pairs: Iterable[tuple[str, str, SimilarityResult]],
    *,
    labels: Mapping[str, Mapping[str, Any]],
    dataset_id: str,
    backend_id: str,
    m2_threshold: float = M2_SYNTHETIC_THRESHOLD,
) -> CalibrationReport:
    """Measure the similarity distribution and recommend a threshold.

    ``pairs`` yields ``(left_id, right_id, result)``. Labels supply creator and
    template identity — the only place ground truth enters the pipeline, and
    never a family decision.
    """

    by_quadrant: dict[str, list[float]] = {name: [] for name in QUADRANTS}
    positives: list[float] = []
    negatives: list[float] = []
    pair_count = 0

    for left_id, right_id, result in pairs:
        if not result.comparable:
            continue
        left_label = labels.get(left_id)
        right_label = labels.get(right_id)
        if left_label is None or right_label is None:
            raise CalibrationError(
                f"missing ground-truth label for {left_id!r} or {right_id!r}"
            )
        quadrant = quadrant_of(left_label, right_label)
        by_quadrant[quadrant].append(result.score)
        pair_count += 1
        if quadrant in POSITIVE_QUADRANTS:
            positives.append(result.score)
        else:
            negatives.append(result.score)

    if not positives or not negatives:
        raise CalibrationError(
            "calibration needs both same-template and different-template pairs; "
            f"got {len(positives)} positive and {len(negatives)} negative"
        )

    quadrants = {
        name: QuadrantStats.from_scores(name, scores)
        for name, scores in by_quadrant.items()
    }

    positive_min = min(positives)
    negative_max = max(negatives)
    gap = round(positive_min - negative_max, 6)
    overlap = gap <= 0.0
    midpoint = round((positive_min + negative_max) / 2.0, 6) if not overlap else None

    candidates: list[ThresholdCandidate] = []
    for threshold in _candidate_thresholds(positives + negatives):
        tp = sum(1 for score in positives if score >= threshold)
        fn = len(positives) - tp
        fp = sum(1 for score in negatives if score >= threshold)
        tn = len(negatives) - fp
        candidates.append(
            ThresholdCandidate(
                threshold=threshold,
                true_positive=tp,
                false_positive=fp,
                true_negative=tn,
                false_negative=fn,
            )
        )

    # Youden's J, then F1, then the midpoint of the gap, then the higher
    # threshold. Fully ordered so the choice is reproducible.
    best = max(
        candidates,
        key=lambda item: (
            item.youden_j,
            item.f1,
            -(abs(item.threshold - midpoint) if midpoint is not None else 0.0),
            item.threshold,
        ),
    )

    notes: list[str] = []
    if overlap:
        notes.append(
            "the same-template and different-template distributions overlap; no "
            "threshold separates them perfectly on this dataset"
        )
    else:
        notes.append(
            f"the distributions are separated by a gap of {gap:.3f}, so every "
            "threshold inside the gap gives identical decisions"
        )
    if midpoint is not None and abs(best.threshold - midpoint) > 1e-6:
        notes.append(
            f"Youden's J selected {best.threshold:.3f} while the gap midpoint is "
            f"{midpoint:.3f}; both are inside the separating band, so they agree on "
            "every pair in this dataset"
        )
    if abs(best.threshold - m2_threshold) > 1e-6:
        notes.append(
            f"the recommended threshold differs from M2's synthetic "
            f"{m2_threshold:.3f}, which was calibrated on declared structure rather "
            "than on decoded pixels and is not reused"
        )

    return CalibrationReport(
        quadrants=quadrants,
        recommended_threshold=round(best.threshold, 6),
        selection_method="youden_j",
        candidates=tuple(candidates),
        separation_gap=gap,
        separation_midpoint=midpoint,
        overlap=overlap,
        pair_count=pair_count,
        dataset_id=dataset_id,
        backend_id=backend_id,
        m2_threshold_for_reference=m2_threshold,
        notes=tuple(notes),
    )


def calibrate_from_samples(
    samples: Sequence[Any],
    *,
    labels: Mapping[str, Mapping[str, Any]],
    dataset_id: str,
    backend_id: str,
    provenance_mode: str = "provenance_agnostic",
    m2_threshold: float = M2_SYNTHETIC_THRESHOLD,
) -> CalibrationReport:
    """Measure similarity over every pair of samples."""

    ordered = sorted(samples, key=lambda sample: sample.sample_id)
    pairs: list[tuple[str, str, SimilarityResult]] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            pairs.append(
                (
                    left.sample_id,
                    right.sample_id,
                    pairwise_similarity(left, right, provenance_mode=provenance_mode),
                )
            )
    return calibrate(
        pairs,
        labels=labels,
        dataset_id=dataset_id,
        backend_id=backend_id,
        m2_threshold=m2_threshold,
    )


def write_calibration(report: CalibrationReport, path: str | Path) -> Path:
    """Persist a calibration report as ``similarity_distribution.json``."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


__all__ = [
    "M2_SYNTHETIC_THRESHOLD",
    "NEGATIVE_QUADRANTS",
    "POSITIVE_QUADRANTS",
    "QUADRANTS",
    "CalibrationError",
    "CalibrationReport",
    "QuadrantStats",
    "ThresholdCandidate",
    "calibrate",
    "calibrate_from_samples",
    "quadrant_of",
    "write_calibration",
]
