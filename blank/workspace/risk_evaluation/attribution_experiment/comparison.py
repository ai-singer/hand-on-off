"""Comparison and metrics: baseline versus attribution-aware.

The phase says not to look only at F1, so the four required measures come first
and F1 is reported last as context:

1. **false positive change** - benign text newly flagged, or no longer flagged
2. **false negative change** - risk newly missed, or no longer missed
3. **attribution-related error reduction** - errors on groups B, C and D, which
   are the groups where attribution is the question
4. **decision difference cases** - which cases changed, classified as fixed,
   broken, or merely different

Two scoring bases are reported because a binary flag hides the interesting
failures. A case expecting `unverified_information` that is flagged
`financial_guarantee` counts as *flagged* but is still wrong about what the risk
is. `flagged_outcome` answers "did it notice anything"; `exact` answers "did it
get the categories right". Errors are counted on `exact`; the FP/FN deltas the
phase asks for are counted on the flag, which is what a gate would act on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .cases import (
    ATTRIBUTION_GROUPS,
    DATASET_VERSION,
    EXPERIMENT_CASES,
    GROUP_NAMES,
    REPLAY_CASES,
    ExperimentCase,
)
from .decision import POLICIES, STRICT, ClaimDecision
from .evaluator import AttributionAwareEvaluator


TRUE_POSITIVE = "tp"
FALSE_POSITIVE = "fp"
FALSE_NEGATIVE = "fn"
TRUE_NEGATIVE = "tn"
OUTCOMES = (TRUE_POSITIVE, FALSE_POSITIVE, FALSE_NEGATIVE, TRUE_NEGATIVE)

UNCHANGED = "unchanged"
FIXED = "fixed"
BROKEN = "broken"
DIFFERENT = "different"


def _outcome(expected_risk: bool, flagged: bool) -> str:
    if expected_risk and flagged:
        return TRUE_POSITIVE
    if expected_risk and not flagged:
        return FALSE_NEGATIVE
    if not expected_risk and flagged:
        return FALSE_POSITIVE
    return TRUE_NEGATIVE


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


@dataclass(frozen=True, slots=True)
class CaseComparison:
    """One case, scored both ways."""

    case: ExperimentCase
    baseline_categories: tuple[str, ...]
    experiment_categories: tuple[str, ...]
    baseline_outcome: str
    experiment_outcome: str
    decisions: tuple[ClaimDecision, ...] = ()
    policy: str = STRICT

    @property
    def case_id(self) -> str:
        return self.case.case_id

    @property
    def expected(self) -> tuple[str, ...]:
        return self.case.expected_categories

    @property
    def baseline_correct(self) -> bool:
        return self.baseline_categories == self.expected

    @property
    def experiment_correct(self) -> bool:
        return self.experiment_categories == self.expected

    @property
    def changed(self) -> bool:
        return self.baseline_categories != self.experiment_categories

    @property
    def transition(self) -> str:
        if not self.changed:
            return UNCHANGED
        if not self.baseline_correct and self.experiment_correct:
            return FIXED
        if self.baseline_correct and not self.experiment_correct:
            return BROKEN
        return DIFFERENT

    @property
    def is_attribution_case(self) -> bool:
        return self.case.is_attribution_case

    @property
    def dropped_categories(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.baseline_categories) - set(self.experiment_categories)))

    @property
    def added_categories(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.experiment_categories) - set(self.baseline_categories)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.case.group,
            "group_name": self.case.group_name,
            "text": self.case.text,
            "expected": list(self.expected),
            "baseline_categories": list(self.baseline_categories),
            "experiment_categories": list(self.experiment_categories),
            "baseline_outcome": self.baseline_outcome,
            "experiment_outcome": self.experiment_outcome,
            "baseline_correct": self.baseline_correct,
            "experiment_correct": self.experiment_correct,
            "changed": self.changed,
            "transition": self.transition,
            "attribution_case": self.is_attribution_case,
            "dropped_categories": list(self.dropped_categories),
            "added_categories": list(self.added_categories),
            "claims": [item.as_dict() for item in self.decisions],
        }

    def render(self) -> str:
        lines = [
            f"{self.case_id} [{self.case.group_name}] {self.transition}",
            f"    {self.case.text}",
            f"    expected   : {list(self.expected)}",
            f"    baseline   : {list(self.baseline_categories)} ({self.baseline_outcome})",
            f"    experiment : {list(self.experiment_categories)} ({self.experiment_outcome})",
        ]
        for item in self.decisions:
            lines.append(f"      {item.render()}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class EvaluatorMetrics:
    name: str
    outcomes: Mapping[str, int]
    correct: int
    cases: int
    attribution_errors: int
    attribution_cases: int

    @property
    def true_positive(self) -> int:
        return self.outcomes[TRUE_POSITIVE]

    @property
    def false_positive(self) -> int:
        return self.outcomes[FALSE_POSITIVE]

    @property
    def false_negative(self) -> int:
        return self.outcomes[FALSE_NEGATIVE]

    @property
    def true_negative(self) -> int:
        return self.outcomes[TRUE_NEGATIVE]

    @property
    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return _ratio(self.true_positive, denominator)

    @property
    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return _ratio(self.true_positive, denominator)

    @property
    def f1(self) -> float:
        precision, recall = self.precision, self.recall
        if not precision or not recall:
            return 0.0
        return round(2 * precision * recall / (precision + recall), 4)

    @property
    def accuracy(self) -> float:
        return _ratio(self.correct, self.cases)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cases": self.cases,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "outcomes": dict(self.outcomes),
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "attribution_cases": self.attribution_cases,
            "attribution_errors": self.attribution_errors,
        }


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    cases: tuple[CaseComparison, ...]
    baseline: EvaluatorMetrics
    experiment: EvaluatorMetrics
    policy: str = STRICT
    dataset_version: str = DATASET_VERSION

    # -- the four required measures ---------------------------------------

    @property
    def false_positive_change(self) -> int:
        return self.experiment.false_positive - self.baseline.false_positive

    @property
    def false_negative_change(self) -> int:
        return self.experiment.false_negative - self.baseline.false_negative

    @property
    def attribution_error_reduction(self) -> int:
        return self.baseline.attribution_errors - self.experiment.attribution_errors

    @property
    def attribution_error_reduction_rate(self) -> float:
        base = self.baseline.attribution_errors
        return round(self.attribution_error_reduction / base, 4) if base else 0.0

    @property
    def decision_difference_cases(self) -> tuple[CaseComparison, ...]:
        return tuple(item for item in self.cases if item.changed)

    # -- classification of the differences --------------------------------

    def by_transition(self, transition: str) -> tuple[CaseComparison, ...]:
        return tuple(item for item in self.cases if item.transition == transition)

    @property
    def fixed_cases(self) -> tuple[CaseComparison, ...]:
        return self.by_transition(FIXED)

    @property
    def broken_cases(self) -> tuple[CaseComparison, ...]:
        return self.by_transition(BROKEN)

    @property
    def different_cases(self) -> tuple[CaseComparison, ...]:
        return self.by_transition(DIFFERENT)

    def group_metrics(self, evaluator: str) -> Mapping[str, Mapping[str, Any]]:
        if evaluator not in ("baseline", "experiment"):
            raise ValueError("evaluator must be 'baseline' or 'experiment'")
        buckets: dict[str, dict[str, Any]] = {}
        for item in self.cases:
            bucket = buckets.setdefault(
                item.case.group_name,
                {"cases": 0, "correct": 0, "false_positives": 0, "false_negatives": 0},
            )
            bucket["cases"] += 1
            correct = item.baseline_correct if evaluator == "baseline" else item.experiment_correct
            outcome = (
                item.baseline_outcome if evaluator == "baseline" else item.experiment_outcome
            )
            bucket["correct"] += int(correct)
            bucket["false_positives"] += int(outcome == FALSE_POSITIVE)
            bucket["false_negatives"] += int(outcome == FALSE_NEGATIVE)
        return dict(sorted(buckets.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "policy": self.policy,
            "cases": len(self.cases),
            "baseline": self.baseline.as_dict(),
            "experiment": self.experiment.as_dict(),
            "false_positive_change": self.false_positive_change,
            "false_negative_change": self.false_negative_change,
            "attribution_error_reduction": self.attribution_error_reduction,
            "attribution_error_reduction_rate": self.attribution_error_reduction_rate,
            "decision_difference_count": len(self.decision_difference_cases),
            "decision_difference_cases": [
                item.case_id for item in self.decision_difference_cases
            ],
            "fixed_cases": [item.case_id for item in self.fixed_cases],
            "broken_cases": [item.case_id for item in self.broken_cases],
            "different_cases": [item.case_id for item in self.different_cases],
            "per_group": {
                "baseline": {k: dict(v) for k, v in self.group_metrics("baseline").items()},
                "experiment": {k: dict(v) for k, v in self.group_metrics("experiment").items()},
            },
        }

    def render(self) -> str:
        lines = [
            f"dataset      : attribution_experiment/{self.dataset_version}",
            f"policy       : {self.policy}",
            f"cases        : {len(self.cases)}",
            "",
            f"{'':22}{'baseline':>12}{'experiment':>12}{'change':>10}",
            self._row("false positives", self.baseline.false_positive, self.experiment.false_positive),
            self._row("false negatives", self.baseline.false_negative, self.experiment.false_negative),
            self._row("true positives", self.baseline.true_positive, self.experiment.true_positive),
            self._row("true negatives", self.baseline.true_negative, self.experiment.true_negative),
            self._row("categories exact", self.baseline.correct, self.experiment.correct),
            self._row(
                "attribution errors",
                self.baseline.attribution_errors,
                self.experiment.attribution_errors,
            ),
            self._row("macro F1", None, None, self.baseline.f1, self.experiment.f1),
            "",
            f"attribution error reduction : {self.attribution_error_reduction} "
            f"({self.attribution_error_reduction_rate:.1%})",
            f"decision difference cases   : {len(self.decision_difference_cases)}",
            f"  fixed      : {[item.case_id for item in self.fixed_cases]}",
            f"  broken     : {[item.case_id for item in self.broken_cases]}",
            f"  different  : {[item.case_id for item in self.different_cases]}",
        ]
        return "\n".join(lines)

    def _row(
        self,
        label: str,
        baseline: int | None,
        experiment: int | None,
        baseline_float: float | None = None,
        experiment_float: float | None = None,
    ) -> str:
        if baseline is not None and experiment is not None:
            return f"{label:22}{baseline:>12}{experiment:>12}{experiment - baseline:>+10}"
        left = f"{baseline_float:.4f}" if baseline_float is not None else "-"
        right = f"{experiment_float:.4f}" if experiment_float is not None else "-"
        return f"{label:22}{left:>12}{right:>12}"


def compare_case(
    case: ExperimentCase,
    evaluator: AttributionAwareEvaluator,
) -> CaseComparison:
    result = evaluator.evaluate(case.text)
    return CaseComparison(
        case=case,
        baseline_categories=result.baseline_categories,
        experiment_categories=result.categories,
        baseline_outcome=_outcome(case.expects_risk, result.baseline_flagged),
        experiment_outcome=_outcome(case.expects_risk, result.flagged),
        decisions=result.claim_decisions,
        policy=evaluator.policy,
    )


def _metrics(
    name: str, cases: Sequence[CaseComparison], *, experiment: bool
) -> EvaluatorMetrics:
    outcomes = {key: 0 for key in OUTCOMES}
    correct = 0
    attribution_errors = 0
    attribution_cases = 0
    for item in cases:
        outcome = item.experiment_outcome if experiment else item.baseline_outcome
        outcomes[outcome] += 1
        is_correct = item.experiment_correct if experiment else item.baseline_correct
        correct += int(is_correct)
        if item.is_attribution_case:
            attribution_cases += 1
            attribution_errors += int(not is_correct)
    return EvaluatorMetrics(
        name=name,
        outcomes=outcomes,
        correct=correct,
        cases=len(cases),
        attribution_errors=attribution_errors,
        attribution_cases=attribution_cases,
    )


def run_comparison(
    cases: Sequence[ExperimentCase] | None = None,
    *,
    policy: str = STRICT,
    evaluator: AttributionAwareEvaluator | None = None,
) -> ComparisonReport:
    """Score baseline and experiment on the same cases."""

    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}, got {policy!r}")
    active_cases = tuple(cases) if cases is not None else EXPERIMENT_CASES
    active_evaluator = (
        evaluator if evaluator is not None else AttributionAwareEvaluator(policy=policy)
    )
    comparisons = tuple(compare_case(case, active_evaluator) for case in active_cases)
    return ComparisonReport(
        cases=comparisons,
        baseline=_metrics("baseline", comparisons, experiment=False),
        experiment=_metrics("experiment", comparisons, experiment=True),
        policy=active_evaluator.policy,
    )


def replay_report(
    *,
    policy: str = STRICT,
    cases: Sequence[ExperimentCase] | None = None,
) -> ComparisonReport:
    """The Phase 8.1 replay, scored the same way."""

    active = tuple(cases) if cases is not None else REPLAY_CASES
    return run_comparison(active, policy=policy)


def policy_sensitivity(
    cases: Sequence[ExperimentCase] | None = None,
) -> Mapping[str, ComparisonReport]:
    """Both readings of R1, on the same data."""

    return {policy: run_comparison(cases, policy=policy) for policy in POLICIES}


def write_report(path: str | Any, report: ComparisonReport | None = None) -> Any:
    from pathlib import Path

    target = Path(path)
    active = report if report is not None else run_comparison()
    payload = {
        **active.as_dict(),
        "group_names": dict(GROUP_NAMES),
        "attribution_groups": list(ATTRIBUTION_GROUPS),
        "note": (
            "Errors are counted on exact category match; the false positive and "
            "false negative deltas are counted on whether anything was flagged, "
            "which is what a gate would act on."
        ),
        "cases_detail": [item.as_dict() for item in active.cases],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    report = run_comparison()
    print("=== strict rules (default) ===")
    print(report.render())
    print()
    print("=== authorial filter (sensitivity variant) ===")
    print(run_comparison(policy="authorial-filter").render())
    print()
    print("=== changed cases ===")
    for item in report.decision_difference_cases:
        print(item.render())
        print()
    print("=== Phase 8.1 replay ===")
    print(replay_report().render())
    if "--write" in sys.argv:
        from pathlib import Path

        base = Path(__file__).resolve().parent
        print()
        print(f"wrote {write_report(base / 'comparison_report.json', report)}")
        print(
            f"wrote {write_report(base / 'replay_report.json', replay_report())}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
