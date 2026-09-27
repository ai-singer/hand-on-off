"""Metrics for the unified pipeline: attribution, intent, decision, trace.

Four families, because the pipeline makes four separable kinds of claim and a
single F1 would hide which one is failing.

    attribution   did it find the right speaker and stance per claim?
    intent        did it find the relation the guide says is present?
    decision      precision, recall, false positives, false negatives
    trace         does every claim carry evidence?

Trace completeness is a metric rather than an assertion because the phase names
it as one: 100% of claims must carry evidence, and that number should be
produced by a run rather than promised by a docstring.

Attribution and intent are scored only on cases whose claim **count** matched,
for the same reason Phase 8.2 did: comparing position by position across
different splits measures nothing. The aligned-claim count is always reported
next to the accuracy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..model import RiskEvaluationResult
from ..pipeline import RiskEvaluationPipeline
from .cases import (
    BENCHMARK_CASES,
    BENCHMARK_NAME,
    BENCHMARK_VERSION,
    GROUP_BASIS,
    GROUP_NAMES,
    BenchmarkCase,
    group_sizes,
    label_source,
    relation_counts,
)


REPORT_PATH = Path(__file__).resolve().parent / "v3_report.json"

TRUE_POSITIVE = "tp"
FALSE_POSITIVE = "fp"
FALSE_NEGATIVE = "fn"
TRUE_NEGATIVE = "tn"
OUTCOMES = (TRUE_POSITIVE, FALSE_POSITIVE, FALSE_NEGATIVE, TRUE_NEGATIVE)


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _outcome(expected_risk: bool, flagged: bool) -> str:
    if expected_risk and flagged:
        return TRUE_POSITIVE
    if expected_risk and not flagged:
        return FALSE_NEGATIVE
    if not expected_risk and flagged:
        return FALSE_POSITIVE
    return TRUE_NEGATIVE


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """One case, scored on all four families."""

    case: BenchmarkCase
    result: RiskEvaluationResult

    @property
    def case_id(self) -> str:
        return self.case.case_id

    @property
    def baseline_categories(self) -> tuple[str, ...]:
        return self.result.baseline

    @property
    def v3_categories(self) -> tuple[str, ...]:
        return self.result.categories

    @property
    def baseline_outcome(self) -> str:
        return _outcome(self.case.expects_risk, self.result.baseline_flagged)

    @property
    def v3_outcome(self) -> str:
        return _outcome(self.case.expects_risk, self.result.flagged)

    @property
    def baseline_correct(self) -> bool:
        return self.baseline_categories == self.case.expected_categories

    @property
    def v3_correct(self) -> bool:
        return self.v3_categories == self.case.expected_categories

    @property
    def split_ok(self) -> bool:
        return len(self.result.claims) == len(self.case.claims)

    @property
    def speaker_ok(self) -> tuple[bool, ...]:
        if not self.split_ok:
            return ()
        return tuple(
            claim.speaker == label.speaker
            for claim, label in zip(self.result.claims, self.case.claims)
        )

    @property
    def stance_ok(self) -> tuple[bool, ...]:
        if not self.split_ok:
            return ()
        return tuple(
            claim.stance == label.stance
            for claim, label in zip(self.result.claims, self.case.claims)
        )

    @property
    def expected_relations(self) -> tuple[str, ...]:
        return self.case.expected_relations

    @property
    def found_relations(self) -> tuple[str, ...]:
        """Relations the intent layer found, **including negated and hedged ones**.

        Detection and assertion are different questions. `Analysts say the fund
        cannot lose money.` contains the RISK_REMOVED relation - the layer found
        it - and the decision policy then declines to report it as the article's.
        Counting only asserted relations would score the intent layer for a
        decision the policy made, and would report a 37.5% relation recall for a
        layer that actually found the relation in nearly every case.
        """

        return tuple(
            dict.fromkeys(
                intent.relation
                for claim in self.result.claims
                for intent in claim.intents
            )
        )

    @property
    def asserted_relations(self) -> tuple[str, ...]:
        """Relations that survived negation and hedging."""

        return tuple(
            dict.fromkeys(
                intent.relation
                for claim in self.result.claims
                for intent in claim.asserted_intents
            )
        )

    @property
    def relation_recall_ok(self) -> bool:
        """Every relation the guide says is present was found."""

        return set(self.expected_relations) <= set(self.found_relations)

    @property
    def claims_with_evidence(self) -> int:
        return sum(1 for claim in self.result.claims if claim.evidence)

    @property
    def trace_complete(self) -> bool:
        return bool(self.result.claims) and all(
            claim.evidence for claim in self.result.claims
        )

    @property
    def transition(self) -> str:
        if self.baseline_correct and self.v3_correct:
            return "unchanged"
        if not self.baseline_correct and self.v3_correct:
            return "fixed"
        if self.baseline_correct and not self.v3_correct:
            return "broken"
        return "different"

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.case.group,
            "text": self.case.text,
            "expected": list(self.case.expected_categories),
            "baseline": list(self.baseline_categories),
            "v3": list(self.v3_categories),
            "actions": dict(sorted(self.result.actions.items())),
            "baseline_outcome": self.baseline_outcome,
            "v3_outcome": self.v3_outcome,
            "transition": self.transition,
            "split_ok": self.split_ok,
            "speaker_ok": list(self.speaker_ok),
            "stance_ok": list(self.stance_ok),
            "expected_relations": list(self.expected_relations),
            "found_relations": list(self.found_relations),
            "asserted_relations": list(self.asserted_relations),
            "relation_recall_ok": self.relation_recall_ok,
            "claims": len(self.result.claims),
            "claims_with_evidence": self.claims_with_evidence,
            "label_source": label_source(self.case),
        }


@dataclass(frozen=True, slots=True)
class AttributionMetrics:
    outcomes: tuple[CaseOutcome, ...]

    @property
    def cases(self) -> int:
        return len(self.outcomes)

    @property
    def split_correct(self) -> int:
        return sum(1 for item in self.outcomes if item.split_ok)

    @property
    def split_accuracy(self) -> float:
        return _ratio(self.split_correct, self.cases)

    @property
    def aligned_claims(self) -> int:
        return sum(len(item.case.claims) for item in self.outcomes if item.split_ok)

    @property
    def speaker_correct(self) -> int:
        return sum(sum(item.speaker_ok) for item in self.outcomes)

    @property
    def stance_correct(self) -> int:
        return sum(sum(item.stance_ok) for item in self.outcomes)

    @property
    def speaker_accuracy(self) -> float:
        return _ratio(self.speaker_correct, self.aligned_claims)

    @property
    def stance_accuracy(self) -> float:
        return _ratio(self.stance_correct, self.aligned_claims)

    def errors(self) -> tuple[CaseOutcome, ...]:
        return tuple(
            item
            for item in self.outcomes
            if not item.split_ok
            or not all(item.speaker_ok)
            or not all(item.stance_ok)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "split_correct": self.split_correct,
            "split_accuracy": self.split_accuracy,
            "aligned_claims": self.aligned_claims,
            "speaker_correct": self.speaker_correct,
            "speaker_accuracy": self.speaker_accuracy,
            "stance_correct": self.stance_correct,
            "stance_accuracy": self.stance_accuracy,
            "error_cases": [item.case_id for item in self.errors()],
        }


@dataclass(frozen=True, slots=True)
class IntentMetrics:
    outcomes: tuple[CaseOutcome, ...]

    @property
    def cases_with_relations(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.expected_relations)

    @property
    def expected_total(self) -> int:
        return sum(len(item.expected_relations) for item in self.cases_with_relations)

    @property
    def found_total(self) -> int:
        return sum(
            len(set(item.expected_relations) & set(item.found_relations))
            for item in self.cases_with_relations
        )

    @property
    def relation_recall(self) -> float:
        return _ratio(self.found_total, self.expected_total)

    @property
    def cases_recalled(self) -> int:
        return sum(1 for item in self.cases_with_relations if item.relation_recall_ok)

    @property
    def case_recall(self) -> float:
        return _ratio(self.cases_recalled, len(self.cases_with_relations))

    def per_relation(self) -> Mapping[str, Mapping[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for item in self.cases_with_relations:
            for relation in item.expected_relations:
                bucket = buckets.setdefault(
                    relation, {"expected": 0, "found": 0, "cases": []}
                )
                bucket["expected"] += 1
                if relation in item.found_relations:
                    bucket["found"] += 1
                else:
                    bucket["cases"].append(item.case_id)
        return {
            name: {
                "expected": bucket["expected"],
                "found": bucket["found"],
                "recall": _ratio(bucket["found"], bucket["expected"]),
                "missed_cases": bucket["cases"],
            }
            for name, bucket in sorted(buckets.items())
        }

    def misses(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.cases_with_relations if not item.relation_recall_ok)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases_with_relations": len(self.cases_with_relations),
            "expected_relations": self.expected_total,
            "found_relations": self.found_total,
            "relation_recall": self.relation_recall,
            "case_recall": self.case_recall,
            "per_relation": {
                k: dict(v) for k, v in self.per_relation().items()
            },
            "miss_cases": [item.case_id for item in self.misses()],
        }


@dataclass(frozen=True, slots=True)
class DecisionMetrics:
    outcomes: tuple[CaseOutcome, ...]
    name: str

    def _categories(self, item: CaseOutcome) -> tuple[str, ...]:
        return item.baseline_categories if self.name == "baseline" else item.v3_categories

    @property
    def counts(self) -> Mapping[str, int]:
        buckets = {key: 0 for key in OUTCOMES}
        for item in self.outcomes:
            buckets[
                item.baseline_outcome if self.name == "baseline" else item.v3_outcome
            ] += 1
        return buckets

    @property
    def correct(self) -> int:
        return sum(
            1
            for item in self.outcomes
            if (item.baseline_correct if self.name == "baseline" else item.v3_correct)
        )

    @property
    def accuracy(self) -> float:
        return _ratio(self.correct, len(self.outcomes))

    @property
    def precision(self) -> float:
        counts = self.counts
        denominator = counts[TRUE_POSITIVE] + counts[FALSE_POSITIVE]
        return _ratio(counts[TRUE_POSITIVE], denominator)

    @property
    def recall(self) -> float:
        counts = self.counts
        denominator = counts[TRUE_POSITIVE] + counts[FALSE_NEGATIVE]
        return _ratio(counts[TRUE_POSITIVE], denominator)

    @property
    def f1(self) -> float:
        precision, recall = self.precision, self.recall
        if not precision or not recall:
            return 0.0
        return round(2 * precision * recall / (precision + recall), 4)

    def per_group(self) -> Mapping[str, Mapping[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for item in self.outcomes:
            bucket = buckets.setdefault(
                GROUP_NAMES[item.case.group],
                {"cases": 0, "correct": 0, "fp": 0, "fn": 0, "tp": 0, "tn": 0},
            )
            outcome = (
                item.baseline_outcome if self.name == "baseline" else item.v3_outcome
            )
            correct = (
                item.baseline_correct if self.name == "baseline" else item.v3_correct
            )
            bucket["cases"] += 1
            bucket["correct"] += int(correct)
            bucket["tp"] += int(outcome == TRUE_POSITIVE)
            bucket["fp"] += int(outcome == FALSE_POSITIVE)
            bucket["fn"] += int(outcome == FALSE_NEGATIVE)
            bucket["tn"] += int(outcome == TRUE_NEGATIVE)
        return dict(sorted(buckets.items()))

    def errors(self) -> tuple[CaseOutcome, ...]:
        return tuple(
            item
            for item in self.outcomes
            if not (item.baseline_correct if self.name == "baseline" else item.v3_correct)
        )

    def as_dict(self) -> dict[str, Any]:
        counts = self.counts
        return {
            "name": self.name,
            "cases": len(self.outcomes),
            "correct": self.correct,
            "accuracy": self.accuracy,
            "true_positives": counts[TRUE_POSITIVE],
            "false_positives": counts[FALSE_POSITIVE],
            "false_negatives": counts[FALSE_NEGATIVE],
            "true_negatives": counts[TRUE_NEGATIVE],
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "per_group": {k: dict(v) for k, v in self.per_group().items()},
            "error_cases": [item.case_id for item in self.errors()],
        }


@dataclass(frozen=True, slots=True)
class TraceMetrics:
    outcomes: tuple[CaseOutcome, ...]

    @property
    def claims(self) -> int:
        return sum(len(item.result.claims) for item in self.outcomes)

    @property
    def claims_with_evidence(self) -> int:
        return sum(item.claims_with_evidence for item in self.outcomes)

    @property
    def completeness(self) -> float:
        return _ratio(self.claims_with_evidence, self.claims)

    @property
    def complete_cases(self) -> int:
        return sum(1 for item in self.outcomes if item.trace_complete)

    @property
    def decisions_without_evidence(self) -> int:
        return sum(
            1
            for item in self.outcomes
            for decision in item.result.final_decision
            if not decision.evidence
        )

    @property
    def traces_missing_spans(self) -> int:
        return sum(
            1
            for item in self.outcomes
            for claim in item.result.claims
            if claim.source_span == (0, 0)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "claims": self.claims,
            "claims_with_evidence": self.claims_with_evidence,
            "completeness": self.completeness,
            "complete_cases": self.complete_cases,
            "cases": len(self.outcomes),
            "decisions_without_evidence": self.decisions_without_evidence,
            "traces_missing_spans": self.traces_missing_spans,
        }


@dataclass(frozen=True, slots=True)
class V3Metrics:
    outcomes: tuple[CaseOutcome, ...]
    attribution: AttributionMetrics
    intent: IntentMetrics
    baseline: DecisionMetrics
    decision: DecisionMetrics
    trace: TraceMetrics

    @property
    def fixed_cases(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.transition == "fixed")

    @property
    def broken_cases(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.transition == "broken")

    def as_dict(self) -> dict[str, Any]:
        return {
            "attribution": self.attribution.as_dict(),
            "intent": self.intent.as_dict(),
            "decision": self.decision.as_dict(),
            "baseline": self.baseline.as_dict(),
            "trace": self.trace.as_dict(),
            "fixed_cases": [item.case_id for item in self.fixed_cases],
            "broken_cases": [item.case_id for item in self.broken_cases],
        }

    def render(self) -> str:
        attribution, intent = self.attribution, self.intent
        trace = self.trace
        lines = [
            f"benchmark      : {BENCHMARK_NAME}/{BENCHMARK_VERSION}",
            f"cases          : {attribution.cases}",
            "",
            "attribution",
            f"  claim split accuracy : {attribution.split_accuracy:.1%} "
            f"({attribution.split_correct}/{attribution.cases})",
            f"  speaker accuracy     : {attribution.speaker_accuracy:.1%} "
            f"({attribution.speaker_correct}/{attribution.aligned_claims} aligned)",
            f"  stance accuracy      : {attribution.stance_accuracy:.1%} "
            f"({attribution.stance_correct}/{attribution.aligned_claims} aligned)",
            "",
            "intent",
            f"  relation recall      : {intent.relation_recall:.1%} "
            f"({intent.found_total}/{intent.expected_total})",
            f"  case recall          : {intent.case_recall:.1%} "
            f"({intent.cases_recalled}/{len(intent.cases_with_relations)})",
            "",
            "decision",
            f"  {'':22}{'baseline':>10}{'v3':>10}",
            f"  {'precision':22}{self.baseline.precision:>10.4f}{self.decision.precision:>10.4f}",
            f"  {'recall':22}{self.baseline.recall:>10.4f}{self.decision.recall:>10.4f}",
            f"  {'f1':22}{self.baseline.f1:>10.4f}{self.decision.f1:>10.4f}",
            f"  {'accuracy':22}{self.baseline.accuracy:>10.4f}{self.decision.accuracy:>10.4f}",
            f"  {'false positives':22}{self.baseline.counts[FALSE_POSITIVE]:>10}"
            f"{self.decision.counts[FALSE_POSITIVE]:>10}",
            f"  {'false negatives':22}{self.baseline.counts[FALSE_NEGATIVE]:>10}"
            f"{self.decision.counts[FALSE_NEGATIVE]:>10}",
            "",
            "trace",
            f"  claims               : {trace.claims}",
            f"  claims with evidence : {trace.claims_with_evidence} "
            f"({trace.completeness:.1%})",
            f"  decisions without evidence : {trace.decisions_without_evidence}",
            "",
            f"fixed  : {[item.case_id for item in self.fixed_cases]}",
            f"broken : {[item.case_id for item in self.broken_cases]}",
        ]
        return "\n".join(lines)


def run_case(case: BenchmarkCase, pipeline: RiskEvaluationPipeline) -> CaseOutcome:
    return CaseOutcome(case=case, result=pipeline.evaluate(case.text))


def evaluate_benchmark(
    cases: Sequence[BenchmarkCase] | None = None,
    *,
    pipeline: RiskEvaluationPipeline | None = None,
) -> V3Metrics:
    active = tuple(cases) if cases is not None else BENCHMARK_CASES
    active_pipeline = pipeline if pipeline is not None else RiskEvaluationPipeline()
    outcomes = tuple(run_case(case, active_pipeline) for case in active)
    return V3Metrics(
        outcomes=outcomes,
        attribution=AttributionMetrics(outcomes),
        intent=IntentMetrics(outcomes),
        baseline=DecisionMetrics(outcomes, "baseline"),
        decision=DecisionMetrics(outcomes, "v3"),
        trace=TraceMetrics(outcomes),
    )


def metrics_payload(
    metrics: V3Metrics | None = None,
    *,
    cases: Sequence[BenchmarkCase] | None = None,
) -> dict[str, Any]:
    active = metrics if metrics is not None else evaluate_benchmark(cases)
    active_cases = tuple(cases) if cases is not None else BENCHMARK_CASES
    return {
        "benchmark": BENCHMARK_NAME,
        "version": BENCHMARK_VERSION,
        "case_count": len(active_cases),
        "groups": dict(group_sizes(active_cases)),
        "group_basis": dict(GROUP_BASIS),
        "relation_counts": dict(relation_counts(active_cases)),
        "metrics": active.as_dict(),
        "cases": [item.as_dict() for item in active.outcomes],
        "note": (
            "Labels come from the annotation guide, never from a pipeline run. "
            "Attribution and intent are scored only on cases whose claim count "
            "matched, and the aligned-claim count is reported alongside."
        ),
    }


def write_report(
    path: str | Path | None = None,
    metrics: V3Metrics | None = None,
) -> Path:
    target = Path(path) if path is not None else REPORT_PATH
    target.write_text(
        json.dumps(metrics_payload(metrics), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    metrics = evaluate_benchmark()
    print(metrics.render())
    print()
    print("per relation:")
    for name, bucket in metrics.intent.per_relation().items():
        print(
            f"  {name:14} {bucket['found']}/{bucket['expected']} "
            f"{bucket['recall']:.1%} missed={bucket['missed_cases']}"
        )
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_report(metrics=metrics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
