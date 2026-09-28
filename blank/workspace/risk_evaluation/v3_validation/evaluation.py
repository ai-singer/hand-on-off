"""Blind evaluation: run the frozen pipeline, then score it, in that order.

The two stages are separate functions and the first one cannot see a label.

    predict(blind_records)    id and text only -> a prediction artifact
    score(predictions, cases) predictions joined with labels -> metrics

`predict` takes `Sequence[Mapping[str, str]]` carrying `id` and `text` and
nothing else, and it never touches `CASES`. There is therefore no code path from
the evaluation stage to an annotation, which is what "blind" has to mean if it is
to mean anything: a claim of blindness that rests on not looking is weaker than
one the call signature enforces.

Metrics in four families, because the pipeline makes four separable kinds of
claim and one F1 would hide which is failing: attribution, intent (precision and
recall, and per relation), decision, and trace.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..v3.pipeline import PipelineConfig, RiskEvaluationPipeline
from .cases import (
    BENCHMARK_ID,
    BENCHMARK_VERSION,
    CASES,
    ValidationCase,
    blind_records,
)

PREDICTION_PATH = Path(__file__).resolve().parent / "predictions_independent_v1.json"
METRICS_PATH = Path(__file__).resolve().parent / "metrics_independent_v1.json"

TRUE_POSITIVE = "tp"
FALSE_POSITIVE = "fp"
FALSE_NEGATIVE = "fn"
TRUE_NEGATIVE = "tn"
OUTCOMES = (TRUE_POSITIVE, FALSE_POSITIVE, FALSE_NEGATIVE, TRUE_NEGATIVE)

RELATIONS = ("GUARANTEE", "RISK_REMOVED", "PREDICTION", "ADVICE")


class EvaluationError(Exception):
    """Raised when the evaluation cannot proceed."""


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
class Prediction:
    """One prediction, carrying the trace the phase requires."""

    case_id: str
    categories: tuple[str, ...]
    actions: Mapping[str, str]
    claims: tuple[dict[str, Any], ...]
    trace: tuple[dict[str, Any], ...]
    baseline: tuple[str, ...]
    evidence_complete: bool
    decisions_with_evidence: int
    decisions_total: int
    spans_present: int
    spans_total: int

    @property
    def flagged(self) -> bool:
        return bool(self.categories)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "categories": list(self.categories),
            "actions": dict(sorted(self.actions.items())),
            "flagged": self.flagged,
            "baseline": list(self.baseline),
            "claims": [dict(item) for item in self.claims],
            "trace": [dict(item) for item in self.trace],
            "evidence_complete": self.evidence_complete,
            "decisions_with_evidence": self.decisions_with_evidence,
            "decisions_total": self.decisions_total,
            "spans_present": self.spans_present,
            "spans_total": self.spans_total,
        }


def predict(
    records: Sequence[Mapping[str, str]],
    *,
    pipeline: RiskEvaluationPipeline | None = None,
    config: PipelineConfig | None = None,
) -> tuple[Prediction, ...]:
    """Run the pipeline over label-free records.

    `records` must carry `id` and `text`. Anything else is ignored, and the
    benchmark's labels are not reachable from here.
    """

    active_pipeline = (
        pipeline
        if pipeline is not None
        else RiskEvaluationPipeline(config=config or PipelineConfig())
    )
    predictions: list[Prediction] = []
    for record in records:
        if "id" not in record or "text" not in record:
            raise EvaluationError(f"a blind record needs id and text: {record!r}")
        result = active_pipeline.evaluate(str(record["text"]))
        decisions = list(result.final_decision)
        claims = result.claims
        predictions.append(
            Prediction(
                case_id=str(record["id"]),
                categories=result.categories,
                actions=result.actions,
                claims=tuple(claim.as_dict() for claim in claims),
                trace=result.trace_dicts(),
                baseline=result.baseline,
                evidence_complete=all(bool(claim.evidence) for claim in claims),
                decisions_with_evidence=sum(1 for d in decisions if d.evidence),
                decisions_total=len(decisions),
                spans_present=sum(1 for c in claims if c.source_span != (0, 0)),
                spans_total=len(claims),
            )
        )
    return tuple(predictions)


def write_predictions(
    path: str | Path | None = None,
    predictions: Sequence[Prediction] | None = None,
    *,
    records: Sequence[Mapping[str, str]] | None = None,
) -> Path:
    target = Path(path) if path is not None else PREDICTION_PATH
    active = (
        tuple(predictions)
        if predictions is not None
        else predict(records if records is not None else blind_records())
    )
    payload = {
        "benchmark": f"{BENCHMARK_ID}/{BENCHMARK_VERSION}",
        "mode": "blind",
        "note": (
            "Produced from id and text only. Labels are not reachable from the "
            "prediction stage."
        ),
        "predictions": [item.as_dict() for item in active],
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case: ValidationCase
    prediction: Prediction

    @property
    def case_id(self) -> str:
        return self.case.case_id

    @property
    def outcome(self) -> str:
        return _outcome(self.case.expects_risk, self.prediction.flagged)

    @property
    def correct(self) -> bool:
        return self.prediction.categories == self.case.categories

    @property
    def baseline_correct(self) -> bool:
        return self.prediction.baseline == self.case.categories

    @property
    def split_ok(self) -> bool:
        return len(self.prediction.claims) == len(self.case.claims)

    @property
    def speaker_ok(self) -> tuple[bool, ...]:
        if not self.split_ok:
            return ()
        return tuple(
            claim["speaker"] == label.speaker
            for claim, label in zip(self.prediction.claims, self.case.claims)
        )

    @property
    def stance_ok(self) -> tuple[bool, ...]:
        if not self.split_ok:
            return ()
        return tuple(
            claim["stance"] == label.stance
            for claim, label in zip(self.prediction.claims, self.case.claims)
        )

    @property
    def found_relations(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                intent["relation"]
                for claim in self.prediction.claims
                for intent in claim.get("intent_evidence", ())
            )
        )

    @property
    def asserted_relations(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                intent["relation"]
                for claim in self.prediction.claims
                for intent in claim.get("intent_evidence", ())
                if intent.get("asserted")
            )
        )

    @property
    def expected_relations(self) -> tuple[str, ...]:
        return self.case.expected_relations

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.case.group,
            "text": self.case.text,
            "expected": list(self.case.categories),
            "predicted": list(self.prediction.categories),
            "baseline": list(self.prediction.baseline),
            "outcome": self.outcome,
            "correct": self.correct,
            "baseline_correct": self.baseline_correct,
            "split_ok": self.split_ok,
            "speaker_ok": list(self.speaker_ok),
            "stance_ok": list(self.stance_ok),
            "expected_relations": list(self.expected_relations),
            "found_relations": list(self.found_relations),
            "asserted_relations": list(self.asserted_relations),
            "annotation_reason": self.case.annotation_reason,
        }


def join(
    predictions: Sequence[Prediction],
    cases: Sequence[ValidationCase] | None = None,
) -> tuple[CaseOutcome, ...]:
    """Join the blind predictions with the labels, by id."""

    active = tuple(cases) if cases is not None else CASES
    index = {item.case_id: item for item in predictions}
    missing = [case.case_id for case in active if case.case_id not in index]
    if missing:
        raise EvaluationError(f"no prediction for {missing}")
    return tuple(CaseOutcome(case, index[case.case_id]) for case in active)


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
            if not item.split_ok or not all(item.speaker_ok) or not all(item.stance_ok)
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
    def recalled(self) -> int:
        return sum(
            len(set(item.expected_relations) & set(item.found_relations))
            for item in self.cases_with_relations
        )

    @property
    def recall(self) -> float:
        return _ratio(self.recalled, self.expected_total)

    @property
    def predicted_total(self) -> int:
        """Relations the layer reported anywhere in the benchmark."""

        return sum(
            len(item.found_relations) for item in self.outcomes
        )

    @property
    def precision(self) -> float:
        """Of the relations reported, how many the guide says are present.

        A relation is a true positive when the case expects it. A relation
        reported on a case that does not expect it is a false positive, which is
        what catches an over-eager frame.
        """

        return _ratio(self.recalled, self.predicted_total)

    def per_relation(self) -> Mapping[str, Mapping[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for relation in RELATIONS:
            expected = [i for i in self.cases_with_relations if relation in i.expected_relations]
            found = sum(1 for i in expected if relation in i.found_relations)
            buckets[relation] = {
                "expected": len(expected),
                "found": found,
                "recall": _ratio(found, len(expected)),
                "missed_cases": [
                    i.case_id for i in expected if relation not in i.found_relations
                ],
            }
        return buckets

    def false_positive_cases(self) -> tuple[CaseOutcome, ...]:
        return tuple(
            item
            for item in self.outcomes
            if set(item.found_relations) - set(item.expected_relations)
        )

    def misses(self) -> tuple[CaseOutcome, ...]:
        return tuple(
            item
            for item in self.cases_with_relations
            if set(item.expected_relations) - set(item.found_relations)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases_with_relations": len(self.cases_with_relations),
            "expected_relations": self.expected_total,
            "recalled": self.recalled,
            "predicted_relations": self.predicted_total,
            "recall": self.recall,
            "precision": self.precision,
            "per_relation": {k: dict(v) for k, v in self.per_relation().items()},
            "miss_cases": [item.case_id for item in self.misses()],
            "false_positive_cases": [
                item.case_id for item in self.false_positive_cases()
            ],
        }


@dataclass(frozen=True, slots=True)
class DecisionMetrics:
    outcomes: tuple[CaseOutcome, ...]

    @property
    def counts(self) -> Mapping[str, int]:
        buckets = {key: 0 for key in OUTCOMES}
        for item in self.outcomes:
            buckets[item.outcome] += 1
        return buckets

    @property
    def correct(self) -> int:
        return sum(1 for item in self.outcomes if item.correct)

    @property
    def accuracy(self) -> float:
        return _ratio(self.correct, len(self.outcomes))

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
        precision, recall = self.precision, self.recall
        if not precision or not recall:
            return 0.0
        return round(2 * precision * recall / (precision + recall), 4)

    @property
    def false_positive_rate(self) -> float:
        counts = self.counts
        return _ratio(counts[FALSE_POSITIVE], counts[FALSE_POSITIVE] + counts[TRUE_NEGATIVE])

    @property
    def false_negative_rate(self) -> float:
        counts = self.counts
        return _ratio(counts[FALSE_NEGATIVE], counts[FALSE_NEGATIVE] + counts[TRUE_POSITIVE])

    def per_group(self) -> Mapping[str, Mapping[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for item in self.outcomes:
            bucket = buckets.setdefault(
                item.case.group,
                {"cases": 0, "correct": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0},
            )
            bucket["cases"] += 1
            bucket["correct"] += int(item.correct)
            bucket[item.outcome] += 1
        return dict(sorted(buckets.items()))

    def errors(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if not item.correct)

    def as_dict(self) -> dict[str, Any]:
        counts = self.counts
        return {
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
            "false_positive_rate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
            "per_group": {k: dict(v) for k, v in self.per_group().items()},
            "error_cases": [item.case_id for item in self.errors()],
        }


@dataclass(frozen=True, slots=True)
class TraceMetrics:
    outcomes: tuple[CaseOutcome, ...]

    @property
    def claims(self) -> int:
        return sum(len(item.prediction.claims) for item in self.outcomes)

    @property
    def claims_with_evidence(self) -> int:
        return sum(
            1
            for item in self.outcomes
            for claim in item.prediction.claims
            if claim.get("evidence")
        )

    @property
    def decisions(self) -> int:
        return sum(item.prediction.decisions_total for item in self.outcomes)

    @property
    def decisions_with_evidence(self) -> int:
        return sum(item.prediction.decisions_with_evidence for item in self.outcomes)

    @property
    def spans_present(self) -> int:
        return sum(item.prediction.spans_present for item in self.outcomes)

    @property
    def spans_total(self) -> int:
        return sum(item.prediction.spans_total for item in self.outcomes)

    @property
    def claim_evidence_rate(self) -> float:
        return _ratio(self.claims_with_evidence, self.claims)

    @property
    def decision_evidence_rate(self) -> float:
        return _ratio(self.decisions_with_evidence, self.decisions)

    @property
    def span_completeness(self) -> float:
        return _ratio(self.spans_present, self.spans_total)

    def as_dict(self) -> dict[str, Any]:
        return {
            "claims": self.claims,
            "claims_with_evidence": self.claims_with_evidence,
            "claim_evidence_rate": self.claim_evidence_rate,
            "decisions": self.decisions,
            "decisions_with_evidence": self.decisions_with_evidence,
            "decision_evidence_rate": self.decision_evidence_rate,
            "spans_present": self.spans_present,
            "spans_total": self.spans_total,
            "span_completeness": self.span_completeness,
        }


@dataclass(frozen=True, slots=True)
class ValidationMetrics:
    outcomes: tuple[CaseOutcome, ...]
    attribution: AttributionMetrics
    intent: IntentMetrics
    decision: DecisionMetrics
    trace: TraceMetrics

    def as_dict(self) -> dict[str, Any]:
        return {
            "attribution": self.attribution.as_dict(),
            "intent": self.intent.as_dict(),
            "decision": self.decision.as_dict(),
            "trace": self.trace.as_dict(),
        }

    def render(self) -> str:
        a, i, d, t = self.attribution, self.intent, self.decision, self.trace
        return "\n".join(
            [
                f"cases : {a.cases}",
                "",
                "attribution",
                f"  claim split accuracy : {a.split_accuracy:.1%} ({a.split_correct}/{a.cases})",
                f"  speaker accuracy     : {a.speaker_accuracy:.1%} ({a.speaker_correct}/{a.aligned_claims})",
                f"  stance accuracy      : {a.stance_accuracy:.1%} ({a.stance_correct}/{a.aligned_claims})",
                "",
                "intent",
                f"  relation recall      : {i.recall:.1%} ({i.recalled}/{i.expected_total})",
                f"  relation precision   : {i.precision:.1%} ({i.recalled}/{i.predicted_total})",
                "",
                "decision",
                f"  precision            : {d.precision:.4f}",
                f"  recall               : {d.recall:.4f}",
                f"  f1                   : {d.f1:.4f}",
                f"  accuracy             : {d.accuracy:.4f}",
                f"  false positive rate  : {d.false_positive_rate:.4f}",
                f"  false negative rate  : {d.false_negative_rate:.4f}",
                f"  tp/fp/fn/tn          : {d.counts[TRUE_POSITIVE]}/{d.counts[FALSE_POSITIVE]}/"
                f"{d.counts[FALSE_NEGATIVE]}/{d.counts[TRUE_NEGATIVE]}",
                "",
                "trace",
                f"  claim evidence       : {t.claims_with_evidence}/{t.claims} ({t.claim_evidence_rate:.1%})",
                f"  decision evidence    : {t.decisions_with_evidence}/{t.decisions} ({t.decision_evidence_rate:.1%})",
                f"  span completeness    : {t.spans_present}/{t.spans_total} ({t.span_completeness:.1%})",
            ]
        )


def score(
    predictions: Sequence[Prediction],
    cases: Sequence[ValidationCase] | None = None,
) -> ValidationMetrics:
    outcomes = join(predictions, cases)
    return ValidationMetrics(
        outcomes=outcomes,
        attribution=AttributionMetrics(outcomes),
        intent=IntentMetrics(outcomes),
        decision=DecisionMetrics(outcomes),
        trace=TraceMetrics(outcomes),
    )


def write_metrics(
    path: str | Path | None = None,
    metrics: ValidationMetrics | None = None,
    *,
    predictions: Sequence[Prediction] | None = None,
    cases: Sequence[ValidationCase] | None = None,
) -> Path:
    target = Path(path) if path is not None else METRICS_PATH
    active = (
        metrics
        if metrics is not None
        else score(
            predictions if predictions is not None else predict(blind_records()),
            cases,
        )
    )
    payload = {
        "benchmark": f"{BENCHMARK_ID}/{BENCHMARK_VERSION}",
        "metrics": active.as_dict(),
        "cases": [item.as_dict() for item in active.outcomes],
        "note": (
            "Predictions were produced from id and text only. Errors are counted "
            "on exact category match; fp/fn come from the flag."
        ),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    from .cases import decontaminated_cases

    predictions = predict(blind_records())
    metrics = score(predictions)
    print("=== independent_v1 (100 cases) ===")
    print(metrics.render())
    print()
    print("=== independent_v2 (clean subset) ===")
    print(score(predictions, decontaminated_cases()).render())
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_predictions(predictions=predictions)}")
        print(f"wrote {write_metrics(metrics=metrics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
