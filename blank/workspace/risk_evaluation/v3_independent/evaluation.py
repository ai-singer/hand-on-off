"""Phase 8.9 evaluation: the frozen evaluator against independently labelled data.

The phase asks for overall precision, recall and F1, the same per category, false
positives and false negatives, and a confusion matrix. This module produces all of
them, plus the pieces that make them interpretable.

**Two confusion matrices, because the labels are sets.** A case can carry more than
one category, so there is no single square matrix that describes the result. Both of
these are reported and each says what it is:

    per category    a 2x2 for each of the five, over present/absent
    primary         a 6x6 over the highest-precedence category, with `none` as a class

**Unresolved cases are excluded from the primary metrics and counted.** Three cases
had a field the adjudicator declined to settle. Scoring them would mean choosing a
label the study did not reach, so they are reported separately with their numbers so
a reader can see what excluding them cost.

**Nothing here is a real-world accuracy.** The text is synthetic and the labels are
machine-assigned. The module's job is to say how the frozen evaluator behaves on this
benchmark, and the report's limitations section says what that is worth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..taxonomy_v2 import CATEGORY_PRECEDENCE
from ..v3.pipeline import RiskEvaluationPipeline
from .build import CATEGORIES as CATEGORIES_ORDER
from .dataset import load_records

EVALUATION_PATH = Path(__file__).resolve().parent / "evaluation_v3_2.json"

#: The taxonomy's precedence, so the primary-category matrix is deterministic.
PRECEDENCE: tuple[str, ...] = tuple(CATEGORY_PRECEDENCE)

NONE = "none"

TRUE_POSITIVE = "tp"
FALSE_POSITIVE = "fp"
FALSE_NEGATIVE = "fn"
TRUE_NEGATIVE = "tn"
OUTCOMES = (TRUE_POSITIVE, FALSE_POSITIVE, FALSE_NEGATIVE, TRUE_NEGATIVE)


class EvaluationError(Exception):
    """Raised when the evaluation cannot proceed."""


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _f1(precision: float, recall: float) -> float:
    if not precision or not recall:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def primary_category(categories: Sequence[str]) -> str:
    """The highest-precedence category, or `none`. Ordering exists for ties."""

    for name in PRECEDENCE:
        if name in categories:
            return name
    return NONE


@dataclass(frozen=True, slots=True)
class CaseResult:
    """One case: what was labelled, what the frozen evaluator said, and the trace."""

    case_id: str
    text: str
    group: str
    language: str
    form: str
    source_type: str
    topic: str
    boundary_kind: str
    intended_intent: str
    expected: tuple[str, ...]
    predicted: tuple[str, ...]
    expected_relations: tuple[str, ...]
    found_relations: tuple[str, ...]
    speakers: tuple[str, ...]
    stances: tuple[str, ...]
    evidence: tuple[str, ...]
    decisions: tuple[dict[str, Any], ...]
    suppressed: tuple[dict[str, Any], ...]
    resolved: bool

    @property
    def correct(self) -> bool:
        return set(self.predicted) == set(self.expected)

    @property
    def expected_risky(self) -> bool:
        return bool(self.expected)

    @property
    def flagged(self) -> bool:
        return bool(self.predicted)

    @property
    def outcome(self) -> str:
        if self.expected_risky and self.flagged:
            return TRUE_POSITIVE
        if self.expected_risky and not self.flagged:
            return FALSE_NEGATIVE
        if not self.expected_risky and self.flagged:
            return FALSE_POSITIVE
        return TRUE_NEGATIVE

    @property
    def extra(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.predicted) - set(self.expected)))

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.expected) - set(self.predicted)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.group,
            "language": self.language,
            "form": self.form,
            "source_type": self.source_type,
            "topic": self.topic,
            "boundary_kind": self.boundary_kind,
            "intended_intent": self.intended_intent,
            "expected": list(self.expected),
            "predicted": list(self.predicted),
            "expected_relations": list(self.expected_relations),
            "found_relations": list(self.found_relations),
            "speakers": list(self.speakers),
            "stances": list(self.stances),
            "outcome": self.outcome,
            "correct": self.correct,
            "resolved": self.resolved,
            "extra": list(self.extra),
            "missing": list(self.missing),
            "primary_expected": primary_category(self.expected),
            "primary_predicted": primary_category(self.predicted),
            "decisions": [dict(item) for item in self.decisions],
            "suppressed": [dict(item) for item in self.suppressed],
            "evidence": list(self.evidence),
        }


def predict(
    records: Sequence[Mapping[str, Any]] | None = None,
    *,
    pipeline: RiskEvaluationPipeline | None = None,
) -> tuple[CaseResult, ...]:
    """Run the frozen pipeline over every record."""

    active = tuple(records) if records is not None else load_records()
    engine = pipeline if pipeline is not None else RiskEvaluationPipeline()
    results: list[CaseResult] = []
    for record in active:
        text = str(record["text"])
        result = engine.evaluate(text)
        frame = record.get("frame", {})
        relations = tuple(
            dict.fromkeys(
                intent.relation
                for claim in result.claims
                for intent in claim.intents
            )
        )
        expected_relations = tuple(
            part
            for part in str(record.get("intent", "")).split(",")
            if part and part != "NONE"
        )
        results.append(
            CaseResult(
                case_id=str(record["id"]),
                text=text,
                group=str(record.get("group", "")),
                language=str(frame.get("language", "")),
                form=str(frame.get("form", "")),
                source_type=str(frame.get("source_type", record.get("source_type", ""))),
                topic=str(frame.get("topic", "")),
                boundary_kind=str(frame.get("boundary_kind", "")),
                intended_intent=str(frame.get("intended_intent", "")),
                expected=tuple(record["expected_categories"]),
                predicted=result.categories,
                expected_relations=expected_relations,
                found_relations=relations,
                speakers=tuple(
                    dict.fromkeys(claim.speaker for claim in result.claims)
                ),
                stances=tuple(
                    dict.fromkeys(claim.stance for claim in result.claims)
                ),
                evidence=tuple(
                    item
                    for claim in result.claims
                    for item in claim.evidence
                ),
                decisions=tuple(
                    decision.as_dict() for decision in result.final_decision
                ),
                suppressed=tuple(
                    decision.as_dict()
                    for trace in result.traces
                    for decision in trace.suppressed
                ),
                resolved=bool(record.get("resolved", True)),
            )
        )
    return tuple(results)


@dataclass(frozen=True, slots=True)
class CategoryMetrics:
    category: str
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float:
        return _ratio(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float:
        return _ratio(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float:
        return _f1(self.precision, self.recall)

    @property
    def support(self) -> int:
        return self.tp + self.fn

    @property
    def confusion(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """Rows labelled, columns predicted: [[tn, fp], [fn, tp]]."""

        return ((self.tn, self.fp), (self.fn, self.tp))

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "tn": self.tn,
            "support": self.support,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "confusion": [list(row) for row in self.confusion],
        }


@dataclass(frozen=True, slots=True)
class Metrics:
    scope: str
    results: tuple[CaseResult, ...]

    @property
    def cases(self) -> int:
        return len(self.results)

    @property
    def correct(self) -> int:
        return sum(1 for item in self.results if item.correct)

    @property
    def accuracy(self) -> float:
        return _ratio(self.correct, self.cases)

    @property
    def counts(self) -> Mapping[str, int]:
        buckets = {key: 0 for key in OUTCOMES}
        for item in self.results:
            buckets[item.outcome] += 1
        return buckets

    @property
    def precision(self) -> float:
        counts = self.counts
        return _ratio(counts[TRUE_POSITIVE], counts[TRUE_POSITIVE] + counts[FALSE_POSITIVE])

    @property
    def recall(self) -> float:
        counts = self.counts
        return _ratio(counts[TRUE_POSITIVE], counts[TRUE_POSITIVE] + counts[FALSE_NEGATIVE])

    @property
    def f1(self) -> float:
        return _f1(self.precision, self.recall)

    @property
    def false_positive_rate(self) -> float:
        counts = self.counts
        return _ratio(counts[FALSE_POSITIVE], counts[FALSE_POSITIVE] + counts[TRUE_NEGATIVE])

    @property
    def false_negative_rate(self) -> float:
        counts = self.counts
        return _ratio(counts[FALSE_NEGATIVE], counts[FALSE_NEGATIVE] + counts[TRUE_POSITIVE])

    def per_category(self) -> tuple[CategoryMetrics, ...]:
        rows: list[CategoryMetrics] = []
        for name in CATEGORIES_ORDER:
            tp = sum(1 for i in self.results if name in i.expected and name in i.predicted)
            fp = sum(1 for i in self.results if name not in i.expected and name in i.predicted)
            fn = sum(1 for i in self.results if name in i.expected and name not in i.predicted)
            tn = sum(
                1 for i in self.results if name not in i.expected and name not in i.predicted
            )
            rows.append(CategoryMetrics(name, tp, fp, fn, tn))
        return tuple(rows)

    def primary_matrix(self) -> tuple[tuple[str, ...], tuple[tuple[int, ...], ...]]:
        """A square matrix over the highest-precedence category, `none` included."""

        labels = (*PRECEDENCE, NONE)
        index = {name: position for position, name in enumerate(labels)}
        grid = [[0] * len(labels) for _ in labels]
        for item in self.results:
            row = index[primary_category(item.expected)]
            column = index[primary_category(item.predicted)]
            grid[row][column] += 1
        return labels, tuple(tuple(row) for row in grid)

    def relation_metrics(self) -> CategoryMetrics:
        tp = sum(1 for i in self.results if set(i.expected_relations) & set(i.found_relations))
        fp = sum(
            1
            for i in self.results
            if set(i.found_relations) - set(i.expected_relations)
        )
        fn = sum(
            1
            for i in self.results
            if set(i.expected_relations) - set(i.found_relations)
        )
        tn = sum(
            1
            for i in self.results
            if not i.expected_relations and not i.found_relations
        )
        return CategoryMetrics("relation", tp, fp, fn, tn)

    def per_group(self) -> Mapping[str, Mapping[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for item in self.results:
            bucket = buckets.setdefault(
                item.group, {"cases": 0, "correct": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0}
            )
            bucket["cases"] += 1
            bucket["correct"] += int(item.correct)
            bucket[item.outcome] += 1
        for bucket in buckets.values():
            bucket["accuracy"] = _ratio(bucket["correct"], bucket["cases"])
        return dict(sorted(buckets.items()))

    def errors(self) -> tuple[CaseResult, ...]:
        return tuple(item for item in self.results if not item.correct)

    def as_dict(self) -> dict[str, Any]:
        counts = self.counts
        labels, grid = self.primary_matrix()
        return {
            "scope": self.scope,
            "cases": self.cases,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "true_positives": counts[TRUE_POSITIVE],
            "false_positives": counts[FALSE_POSITIVE],
            "false_negatives": counts[FALSE_NEGATIVE],
            "true_negatives": counts[TRUE_NEGATIVE],
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "false_positive_rate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
            "per_category": [item.as_dict() for item in self.per_category()],
            "per_group": {key: dict(value) for key, value in self.per_group().items()},
            "relation": self.relation_metrics().as_dict(),
            "confusion_primary": {
                "labels": list(labels),
                "matrix": [list(row) for row in grid],
                "note": (
                    "rows are the labelled highest-precedence category, columns are "
                    "the predicted one; `none` is a class"
                ),
            },
            "error_cases": [item.case_id for item in self.errors()],
        }

    def render(self) -> str:
        counts = self.counts
        lines = [
            f"scope : {self.scope}",
            f"cases : {self.cases}",
            "",
            "overall (a case is correct when its category set matches exactly)",
            f"  correct              : {self.correct} ({self.accuracy:.4f})",
            f"  precision            : {self.precision:.4f}",
            f"  recall               : {self.recall:.4f}",
            f"  f1                   : {self.f1:.4f}",
            f"  tp/fp/fn/tn          : {counts[TRUE_POSITIVE]}/{counts[FALSE_POSITIVE]}/"
            f"{counts[FALSE_NEGATIVE]}/{counts[TRUE_NEGATIVE]}",
            f"  false positive rate  : {self.false_positive_rate:.4f}",
            f"  false negative rate  : {self.false_negative_rate:.4f}",
            "",
            "per category",
        ]
        for row in self.per_category():
            lines.append(
                f"  {row.category:24} p {row.precision:.4f} r {row.recall:.4f} "
                f"f1 {row.f1:.4f}  tp/fp/fn/tn {row.tp}/{row.fp}/{row.fn}/{row.tn}"
            )
        lines.append("")
        lines.append("per group")
        for group, bucket in self.per_group().items():
            lines.append(
                f"  {group:16} {bucket['correct']}/{bucket['cases']} "
                f"({bucket['accuracy']:.4f})  fp {bucket['fp']} fn {bucket['fn']}"
            )
        labels, grid = self.primary_matrix()
        lines.append("")
        lines.append("confusion matrix, highest-precedence category")
        lines.append("  labelled \\ predicted  " + "  ".join(f"{n[:9]:>9}" for n in labels))
        for name, row in zip(labels, grid):
            lines.append(
                f"  {name:22}" + "  ".join(f"{value:>9}" for value in row)
            )
        return "\n".join(lines)


def score(
    results: Sequence[CaseResult] | None = None, *, scope: str = "all"
) -> Metrics:
    active = tuple(results) if results is not None else predict()
    return Metrics(scope=scope, results=active)


def evaluate(records: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Every scope the phase asks for, in one call."""

    results = predict(records)
    resolved = tuple(item for item in results if item.resolved)
    unresolved = tuple(item for item in results if not item.resolved)
    primary = score(resolved, scope="resolved")
    everything = score(results, scope="all")
    return {
        "primary": primary.as_dict(),
        "all_cases": everything.as_dict(),
        "unresolved": {
            "cases": len(unresolved),
            "case_ids": [item.case_id for item in unresolved],
            "correct_if_scored": sum(1 for item in unresolved if item.correct),
            "note": (
                "excluded from the primary metrics: the adjudicator declined to settle "
                "a field, so scoring them would mean choosing a label the study did "
                "not reach"
            ),
        },
        "relation": primary.relation_metrics().as_dict(),
        "cases": [item.as_dict() for item in results],
    }


def write_evaluation(
    path: str | Path | None = None, *, payload: Mapping[str, Any] | None = None
) -> Path:
    target = Path(path) if path is not None else EVALUATION_PATH
    active = dict(payload) if payload is not None else evaluate()
    target.write_text(
        json.dumps(active, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    payload = evaluate()
    resolved = Metrics(scope="resolved", results=tuple(
        item for item in predict() if item.resolved
    ))
    print(resolved.render())
    print()
    print(
        "unresolved cases: {n} {ids}".format(
            n=payload["unresolved"]["cases"], ids=payload["unresolved"]["case_ids"]
        )
    )
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_evaluation(payload=payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
