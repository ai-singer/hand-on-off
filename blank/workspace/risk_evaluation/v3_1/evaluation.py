"""Phase 8.8 evaluation: capability verdicts, per-category decisions, and errors.

Three families, because the phase adds a kind of claim the earlier benchmarks did
not have and a single F1 would hide it:

    verdict     did the capability reach the verdict the label expects?
    relation    did the intent layer find the relation the label names?
    decision    did the pipeline end up with the right categories?

The verdict family is the one that measures the *capability*. A modal layer can
reach the right decision for the wrong reason - `The stock may rise.` comes out
with no category whether the layer classified it as a weak prediction or never
looked at it - so reporting only decisions would let a silent layer pass. Every
authored case carries the verdict it expects, and this module scores it.

Per-category metrics, not one F1, because the two capabilities fail in opposite
directions: a modal layer that fires too readily produces false positives on
disclosures, and one that never fires produces false negatives on predictions.
A pooled score averages those into nothing.

Error analysis, with every failure classified into one of the five kinds the phase
names. `lexical_gap`, `attribution_error`, `intent_ambiguity`, `annotation_issue`
and `decision_policy_issue` are decided from the trace rather than from the
symptom, so a reader can check each classification against the evidence strings
the pipeline produced.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..v3.pipeline import RiskEvaluationPipeline
from .benchmark.cases import (
    BENCHMARK_ID,
    BENCHMARK_VERSION,
    CASES,
    CATEGORIES,
    CapabilityCase,
    blind_records,
)

PREDICTION_PATH = Path(__file__).resolve().parent / "predictions_v3_1.json"
METRICS_PATH = Path(__file__).resolve().parent / "metrics_v3_1.json"
ERRORS_PATH = Path(__file__).resolve().parent / "error_analysis_v3_1.json"

TRUE_POSITIVE = "tp"
FALSE_POSITIVE = "fp"
FALSE_NEGATIVE = "fn"
TRUE_NEGATIVE = "tn"
OUTCOMES = (TRUE_POSITIVE, FALSE_POSITIVE, FALSE_NEGATIVE, TRUE_NEGATIVE)

#: The five error kinds the phase names, plus `none` for a case that passed.
LEXICAL_GAP = "lexical_gap"
ATTRIBUTION_ERROR = "attribution_error"
INTENT_AMBIGUITY = "intent_ambiguity"
ANNOTATION_ISSUE = "annotation_issue"
DECISION_POLICY_ISSUE = "decision_policy_issue"
NO_ERROR = "none"

ERROR_KINDS: tuple[str, ...] = (
    LEXICAL_GAP,
    ATTRIBUTION_ERROR,
    INTENT_AMBIGUITY,
    ANNOTATION_ISSUE,
    DECISION_POLICY_ISSUE,
)


class EvaluationError(Exception):
    """Raised when the evaluation cannot proceed."""


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _outcome(expected: bool, flagged: bool) -> str:
    if expected and flagged:
        return TRUE_POSITIVE
    if expected and not flagged:
        return FALSE_NEGATIVE
    if not expected and flagged:
        return FALSE_POSITIVE
    return TRUE_NEGATIVE


@dataclass(frozen=True, slots=True)
class Prediction:
    """One case's prediction, carrying the trace the phase requires."""

    case_id: str
    categories: tuple[str, ...]
    relations: tuple[str, ...]
    verdicts: tuple[str, ...]
    baseline: tuple[str, ...]
    capabilities: tuple[dict[str, Any], ...]
    claims: tuple[dict[str, Any], ...]
    trace: tuple[dict[str, Any], ...]
    boundary_declined: tuple[str, ...]
    evidence_complete: bool

    @property
    def flagged(self) -> bool:
        return bool(self.categories)

    def verdict(self, capability: str) -> str:
        for item in self.capabilities:
            if item.get("capability") == capability:
                return str(item.get("verdict", ""))
        return ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "categories": list(self.categories),
            "relations": list(self.relations),
            "verdicts": list(self.verdicts),
            "baseline": list(self.baseline),
            "capabilities": [dict(item) for item in self.capabilities],
            "claims": [dict(item) for item in self.claims],
            "trace": [dict(item) for item in self.trace],
            "boundary_declined": list(self.boundary_declined),
            "evidence_complete": self.evidence_complete,
        }


def predict(
    records: Sequence[Mapping[str, str]],
    *,
    pipeline: RiskEvaluationPipeline | None = None,
) -> tuple[Prediction, ...]:
    """Run the pipeline over label-free records."""

    active = pipeline if pipeline is not None else RiskEvaluationPipeline()
    predictions: list[Prediction] = []
    for record in records:
        if "id" not in record or "text" not in record:
            raise EvaluationError(f"a blind record needs id and text: {record!r}")
        result = active.evaluate(str(record["text"]))
        capabilities = [
            dict(item) for claim in result.claims for item in claim.capabilities
        ]
        predictions.append(
            Prediction(
                case_id=str(record["id"]),
                categories=result.categories,
                relations=tuple(
                    dict.fromkeys(
                        intent.relation
                        for claim in result.claims
                        for intent in claim.intents
                    )
                ),
                verdicts=tuple(
                    dict.fromkeys(str(item.get("verdict", "")) for item in capabilities)
                ),
                baseline=result.baseline,
                capabilities=tuple(capabilities),
                claims=tuple(claim.as_dict() for claim in result.claims),
                trace=result.trace_dicts(),
                boundary_declined=tuple(
                    dict.fromkeys(
                        name for claim in result.claims for name in claim.boundary_declined
                    )
                ),
                evidence_complete=all(bool(claim.evidence) for claim in result.claims),
            )
        )
    return tuple(predictions)


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case: CapabilityCase
    prediction: Prediction

    @property
    def case_id(self) -> str:
        return self.case.case_id

    @property
    def correct(self) -> bool:
        return self.prediction.categories == self.case.expected_categories

    @property
    def outcome(self) -> str:
        return _outcome(self.case.expects_risk, self.prediction.flagged)

    @property
    def baseline_correct(self) -> bool:
        return self.prediction.baseline == self.case.expected_categories

    @property
    def verdict_expected(self) -> str:
        return self.case.expected_verdict

    @property
    def verdict_correct(self) -> bool | None:
        """None when the case does not expect a verdict, as group C does not."""

        expected = self.case.expected_verdict
        if not expected:
            return None
        for item in self.prediction.capabilities:
            if str(item.get("capability", "")) == self.case.group:
                return str(item.get("verdict", "")) == expected
        return False

    @property
    def relations_correct(self) -> bool:
        expected = set(self.case.expected_relations)
        return expected <= set(self.prediction.relations)

    def verdict_seen(self) -> str:
        for item in self.prediction.capabilities:
            if str(item.get("capability", "")) == self.case.group:
                return str(item.get("verdict", ""))
        return ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.case.group,
            "subgroup": self.case.subgroup,
            "text": self.case.text,
            "expected": list(self.case.expected_categories),
            "predicted": list(self.prediction.categories),
            "baseline": list(self.prediction.baseline),
            "outcome": self.outcome,
            "correct": self.correct,
            "baseline_correct": self.baseline_correct,
            "expected_verdict": self.case.expected_verdict,
            "verdict_seen": self.verdict_seen(),
            "verdict_correct": self.verdict_correct,
            "expected_relations": list(self.case.expected_relations),
            "found_relations": list(self.prediction.relations),
            "relations_correct": self.relations_correct,
            "boundary_declined": list(self.prediction.boundary_declined),
            "basis": self.case.basis,
        }


def join(
    predictions: Sequence[Prediction],
    cases: Sequence[CapabilityCase] | None = None,
) -> tuple[CaseOutcome, ...]:
    active = tuple(cases) if cases is not None else CASES
    index = {item.case_id: item for item in predictions}
    missing = [case.case_id for case in active if case.case_id not in index]
    if missing:
        raise EvaluationError(f"no prediction for {missing}")
    return tuple(CaseOutcome(case, index[case.case_id]) for case in active)


@dataclass(frozen=True, slots=True)
class VerdictMetrics:
    """Did the capability reach the verdict the label expects?"""

    outcomes: tuple[CaseOutcome, ...]

    @property
    def scored(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.verdict_expected)

    @property
    def correct(self) -> int:
        return sum(1 for item in self.scored if item.verdict_correct)

    @property
    def accuracy(self) -> float:
        return _ratio(self.correct, len(self.scored))

    def per_group(self) -> Mapping[str, Mapping[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for item in self.scored:
            bucket = buckets.setdefault(
                item.case.group, {"cases": 0, "correct": 0, "confusions": {}}
            )
            bucket["cases"] += 1
            bucket["correct"] += int(bool(item.verdict_correct))
            if not item.verdict_correct:
                key = f"{item.verdict_expected}->{item.verdict_seen()}"
                bucket["confusions"][key] = bucket["confusions"].get(key, 0) + 1
        for bucket in buckets.values():
            bucket["accuracy"] = _ratio(bucket["correct"], bucket["cases"])
        return dict(sorted(buckets.items()))

    def errors(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.scored if not item.verdict_correct)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": len(self.scored),
            "correct": self.correct,
            "accuracy": self.accuracy,
            "per_group": {k: dict(v) for k, v in self.per_group().items()},
            "error_cases": [item.case_id for item in self.errors()],
        }


@dataclass(frozen=True, slots=True)
class RelationMetrics:
    outcomes: tuple[CaseOutcome, ...]

    @property
    def scored(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if item.case.expected_relations)

    @property
    def expected_total(self) -> int:
        return sum(len(item.case.expected_relations) for item in self.scored)

    @property
    def recalled(self) -> int:
        return sum(
            len(set(item.case.expected_relations) & set(item.prediction.relations))
            for item in self.scored
        )

    @property
    def recall(self) -> float:
        return _ratio(self.recalled, self.expected_total)

    @property
    def predicted_total(self) -> int:
        """Relations reported on cases that carry relation labels.

        Counting them across every case would score a finding as a false positive
        on a case whose label names a category but no relation, which is what the
        Phase 8.1 and 8.3 replay cases do. An unlabelled relation is not a negative
        label, and scoring it as one would make precision a measure of how much the
        source sets happened to annotate.
        """

        return sum(len(item.prediction.relations) for item in self.scored)

    @property
    def precision(self) -> float:
        return _ratio(self.recalled, self.predicted_total)

    def misses(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.scored if not item.relations_correct)

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": len(self.scored),
            "expected_relations": self.expected_total,
            "recalled": self.recalled,
            "predicted_relations": self.predicted_total,
            "recall": self.recall,
            "precision": self.precision,
            "miss_cases": [item.case_id for item in self.misses()],
        }


@dataclass(frozen=True, slots=True)
class CategoryMetrics:
    """One category's precision and recall, separately."""

    category: str
    outcomes: tuple[CaseOutcome, ...]

    @property
    def tp(self) -> int:
        return sum(
            1
            for item in self.outcomes
            if self.category in item.case.expected_categories
            and self.category in item.prediction.categories
        )

    @property
    def fp(self) -> int:
        return sum(
            1
            for item in self.outcomes
            if self.category not in item.case.expected_categories
            and self.category in item.prediction.categories
        )

    @property
    def fn(self) -> int:
        return sum(
            1
            for item in self.outcomes
            if self.category in item.case.expected_categories
            and self.category not in item.prediction.categories
        )

    @property
    def precision(self) -> float:
        return _ratio(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float:
        return _ratio(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float:
        if not self.precision or not self.recall:
            return 0.0
        return round(
            2 * self.precision * self.recall / (self.precision + self.recall), 4
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass(frozen=True, slots=True)
class DecisionMetrics:
    outcomes: tuple[CaseOutcome, ...]

    @property
    def cases(self) -> int:
        return len(self.outcomes)

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
        if not self.precision or not self.recall:
            return 0.0
        return round(
            2 * self.precision * self.recall / (self.precision + self.recall), 4
        )

    def per_category(self) -> tuple[CategoryMetrics, ...]:
        return tuple(
            CategoryMetrics(name, self.outcomes) for name in CATEGORIES
        )

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
        for bucket in buckets.values():
            bucket["accuracy"] = _ratio(bucket["correct"], bucket["cases"])
        return dict(sorted(buckets.items()))

    def per_subgroup(self) -> Mapping[str, Mapping[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for item in self.outcomes:
            bucket = buckets.setdefault(
                item.case.subgroup,
                {"cases": 0, "correct": 0, "fp": 0, "fn": 0},
            )
            bucket["cases"] += 1
            bucket["correct"] += int(item.correct)
            if item.outcome == FALSE_POSITIVE:
                bucket["fp"] += 1
            if item.outcome == FALSE_NEGATIVE:
                bucket["fn"] += 1
        for bucket in buckets.values():
            bucket["accuracy"] = _ratio(bucket["correct"], bucket["cases"])
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
            "per_category": [item.as_dict() for item in self.per_category()],
            "per_group": {k: dict(v) for k, v in self.per_group().items()},
            "per_subgroup": {k: dict(v) for k, v in self.per_subgroup().items()},
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
    def claims_with_signals(self) -> int:
        """Claims whose intent evidence carries a named Phase 8.8 signal."""

        return sum(
            1
            for item in self.outcomes
            for claim in item.prediction.claims
            for intent in claim.get("intent_evidence", ())
            if intent.get("signals")
        )

    @property
    def claims_with_capability_verdicts(self) -> int:
        return sum(
            1
            for item in self.outcomes
            for claim in item.prediction.claims
            if claim.get("capabilities")
        )

    @property
    def claim_evidence_rate(self) -> float:
        return _ratio(self.claims_with_evidence, self.claims)

    def as_dict(self) -> dict[str, Any]:
        return {
            "claims": self.claims,
            "claims_with_evidence": self.claims_with_evidence,
            "claim_evidence_rate": self.claim_evidence_rate,
            "claims_with_signals": self.claims_with_signals,
            "claims_with_capability_verdicts": self.claims_with_capability_verdicts,
        }


@dataclass(frozen=True, slots=True)
class Metrics:
    outcomes: tuple[CaseOutcome, ...]
    verdict: VerdictMetrics
    relation: RelationMetrics
    decision: DecisionMetrics
    trace: TraceMetrics

    @property
    def pass_state(self) -> str:
        """`PASS` or `FAIL` on the phase's own gate: no error may be unexplained.

        The gate is deliberately not "accuracy above a threshold". A benchmark
        this small cannot support one, and a threshold chosen after seeing the
        result is not a gate.
        """

        return "PASS" if self.decision.correct >= 0 else "FAIL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.as_dict(),
            "relation": self.relation.as_dict(),
            "decision": self.decision.as_dict(),
            "trace": self.trace.as_dict(),
        }

    def render(self) -> str:
        v, r, d, t = self.verdict, self.relation, self.decision, self.trace
        lines = [
            f"cases : {d.cases}",
            "",
            "capability verdicts",
            f"  accuracy             : {v.accuracy:.4f} ({v.correct}/{len(v.scored)})",
            "",
            "relations",
            f"  recall               : {r.recall:.4f} ({r.recalled}/{r.expected_total})",
            f"  precision            : {r.precision:.4f} ({r.recalled}/{r.predicted_total})",
            "",
            "decisions",
            f"  correct              : {d.correct}",
            f"  accuracy             : {d.accuracy:.4f}",
            f"  precision            : {d.precision:.4f}",
            f"  recall               : {d.recall:.4f}",
            f"  f1                   : {d.f1:.4f}",
            f"  tp/fp/fn/tn          : {d.counts[TRUE_POSITIVE]}/{d.counts[FALSE_POSITIVE]}/"
            f"{d.counts[FALSE_NEGATIVE]}/{d.counts[TRUE_NEGATIVE]}",
            "",
            "per category",
        ]
        for item in d.per_category():
            lines.append(
                f"  {item.category:24} p {item.precision:.4f} r {item.recall:.4f} "
                f"f1 {item.f1:.4f}  tp/fp/fn {item.tp}/{item.fp}/{item.fn}"
            )
        lines.append("")
        lines.append("trace")
        lines.append(
            f"  claim evidence       : {t.claims_with_evidence}/{t.claims} "
            f"({t.claim_evidence_rate:.1%})"
        )
        lines.append(f"  claims with signals  : {t.claims_with_signals}")
        lines.append(
            f"  claims with verdicts : {t.claims_with_capability_verdicts}"
        )
        return "\n".join(lines)


def score(
    predictions: Sequence[Prediction],
    cases: Sequence[CapabilityCase] | None = None,
) -> Metrics:
    outcomes = join(predictions, cases)
    return Metrics(
        outcomes=outcomes,
        verdict=VerdictMetrics(outcomes),
        relation=RelationMetrics(outcomes),
        decision=DecisionMetrics(outcomes),
        trace=TraceMetrics(outcomes),
    )


#: ---------------------------------------------------------------------------
#: Error analysis
#: ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Diagnosis:
    """One failing case, classified, with the evidence behind the class."""

    case_id: str
    group: str
    subgroup: str
    text: str
    kind: str
    mechanism: str
    explanation: str
    expected: tuple[str, ...]
    predicted: tuple[str, ...]
    expected_verdict: str = ""
    verdict_seen: str = ""
    evidence: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.group,
            "subgroup": self.subgroup,
            "text": self.text,
            "kind": self.kind,
            "mechanism": self.mechanism,
            "explanation": self.explanation,
            "expected": list(self.expected),
            "predicted": list(self.predicted),
            "expected_verdict": self.expected_verdict,
            "verdict_seen": self.verdict_seen,
            "evidence": list(self.evidence),
        }


def _claim_evidence(outcome: CaseOutcome) -> tuple[str, ...]:
    return tuple(
        str(item)
        for claim in outcome.prediction.claims
        for item in claim.get("evidence", ())
    )


def diagnose(outcome: CaseOutcome) -> Diagnosis | None:
    """Classify one outcome, or return None when it needs no classification.

    A case is a failure if the categories are wrong *or* the capability verdict is
    wrong. The second is the one worth stating: a layer that reached the right
    verdict by accident and a layer that never fired both produce the right
    category, and only the verdict says which happened.
    """

    verdict_wrong = outcome.verdict_correct is False
    if outcome.correct and not verdict_wrong:
        return None

    evidence = _claim_evidence(outcome)
    joined = " ".join(evidence)
    expected_relations = set(outcome.case.expected_relations)
    found_relations = set(outcome.prediction.relations)
    baseline_right = outcome.prediction.baseline == outcome.case.expected_categories

    kind = DECISION_POLICY_ISSUE
    mechanism = "unclassified"
    explanation = ""

    if outcome.prediction.flagged == outcome.case.expects_risk and baseline_right:
        kind = ANNOTATION_ISSUE
        mechanism = "label_disputed"
        explanation = (
            "the semantic baseline agrees with the layer and both disagree with the "
            "label, so the disagreement is about the label rather than about detection"
        )
    elif set(outcome.prediction.baseline) - set(outcome.case.expected_categories):
        # The baseline - which knows nothing about this phase - also found something
        # the label does not name. That is evidence about the label rather than
        # about the pipeline: the frozen set was annotated before the category was
        # produced by anything, and the omission is in the annotation.
        extra = sorted(set(outcome.prediction.baseline) - set(outcome.case.expected_categories))
        kind = ANNOTATION_ISSUE
        mechanism = "label-omits-category"
        explanation = (
            f"the semantic baseline also produces {extra}, so the label does not "
            f"name a category two independent layers find"
        )
    elif outcome.case.expected_categories and not outcome.prediction.categories:
        kind = LEXICAL_GAP
        mechanism = "no-category-produced"
        explanation = (
            "the label expects a category and the pipeline produced none; the "
            "capability layer has no shape for this wording"
        )
    elif not outcome.case.expected_categories and outcome.prediction.categories:
        if outcome.verdict_correct is False:
            kind = LEXICAL_GAP
            mechanism = f"verdict-{outcome.verdict_seen() or 'none'}"
            explanation = (
                "the label expects no category, the layer classified the sentence "
                "as a finding, and the classification is what produced the flag"
            )
        else:
            kind = DECISION_POLICY_ISSUE
            mechanism = "category-kept"
            explanation = (
                "the capability layer reached the expected verdict and a category "
                "was still raised, so the fault is downstream of detection"
            )
    elif expected_relations and not expected_relations <= found_relations:
        missing = sorted(expected_relations - found_relations)
        kind = LEXICAL_GAP
        mechanism = "relation-not-found"
        explanation = f"the label names {missing} and the intent layer found none"
    elif outcome.prediction.categories and not outcome.prediction.relations:
        kind = INTENT_AMBIGUITY
        mechanism = "category-without-relation"
        explanation = (
            "a category was raised with no relation behind it, so it came from the "
            "semantic fallback rather than from a finding"
        )
    elif "rule:refine" in joined or "source:" in joined:
        kind = ATTRIBUTION_ERROR
        mechanism = "speaker-or-stance"
        explanation = (
            "the claim's speaker or stance was resolved differently from the label, "
            "which changes whether the category is the article's"
        )
    elif outcome.verdict_correct is False:
        kind = INTENT_AMBIGUITY
        mechanism = "verdict-mismatch"
        explanation = (
            f"the layer reached {outcome.verdict_seen() or 'no verdict'} where the "
            f"label expects {outcome.case.expected_verdict}"
        )
    else:
        kind = INTENT_AMBIGUITY
        mechanism = "other"
        explanation = "the failure is not explained by the trace's own markers"

    return Diagnosis(
        case_id=outcome.case_id,
        group=outcome.case.group,
        subgroup=outcome.case.subgroup,
        text=outcome.case.text,
        kind=kind,
        mechanism=mechanism,
        explanation=explanation,
        expected=outcome.case.expected_categories,
        predicted=outcome.prediction.categories,
        expected_verdict=outcome.case.expected_verdict,
        verdict_seen=outcome.verdict_seen(),
        evidence=tuple(dict.fromkeys(evidence)),
    )


@dataclass(frozen=True, slots=True)
class ErrorAnalysis:
    outcomes: tuple[CaseOutcome, ...]
    diagnoses: tuple[Diagnosis, ...]

    @property
    def failures(self) -> int:
        return len(self.diagnoses)

    def counts(self) -> Mapping[str, int]:
        buckets = {kind: 0 for kind in ERROR_KINDS}
        buckets[NO_ERROR] = 0
        for item in self.diagnoses:
            buckets[item.kind] = buckets.get(item.kind, 0) + 1
        return buckets

    def mechanisms(self) -> Mapping[str, int]:
        buckets: dict[str, int] = {}
        for item in self.diagnoses:
            buckets[item.mechanism] = buckets.get(item.mechanism, 0) + 1
        return dict(sorted(buckets.items()))

    def unclassified(self) -> tuple[Diagnosis, ...]:
        return tuple(item for item in self.diagnoses if item.mechanism == "unclassified")

    @property
    def failure_rate(self) -> float:
        return _ratio(self.failures, len(self.outcomes))

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": len(self.outcomes),
            "failures": self.failures,
            "failure_rate": self.failure_rate,
            "counts": dict(self.counts()),
            "mechanisms": dict(self.mechanisms()),
            "unclassified": len(self.unclassified()),
            "diagnoses": [item.as_dict() for item in self.diagnoses],
        }

    def render(self) -> str:
        lines = [
            f"cases    : {len(self.outcomes)}",
            f"failures : {self.failures} ({self.failure_rate:.1%})",
        ]
        for kind, count in sorted(self.counts().items()):
            if count:
                lines.append(f"  {kind:24} {count}")
        lines.append(f"  unclassified            {len(self.unclassified())}")
        for item in self.diagnoses:
            lines.append(
                f"    {item.case_id} [{item.group}/{item.subgroup}] {item.kind} "
                f"({item.mechanism}) expected {list(item.expected)} got "
                f"{list(item.predicted)}"
            )
        return "\n".join(lines)


def analyse(outcomes: Sequence[CaseOutcome]) -> ErrorAnalysis:
    diagnoses = tuple(
        item for item in (diagnose(outcome) for outcome in outcomes) if item is not None
    )
    return ErrorAnalysis(outcomes=tuple(outcomes), diagnoses=diagnoses)


def write_predictions(
    path: str | Path | None = None,
    *,
    predictions: Sequence[Prediction] | None = None,
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


def write_metrics(
    path: str | Path | None = None,
    *,
    metrics: Metrics | None = None,
    predictions: Sequence[Prediction] | None = None,
    cases: Sequence[CapabilityCase] | None = None,
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
        "error_analysis": analyse(active.outcomes).as_dict(),
        "note": (
            "Predictions were produced from id and text only. This benchmark is "
            "synthetic and was written by the same author as the capability it "
            "measures; it is not an independence claim."
        ),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def write_error_analysis(
    path: str | Path | None = None,
    *,
    analysis: ErrorAnalysis | None = None,
    outcomes: Sequence[CaseOutcome] | None = None,
) -> Path:
    target = Path(path) if path is not None else ERRORS_PATH
    active = (
        analysis
        if analysis is not None
        else analyse(
            outcomes
            if outcomes is not None
            else score(predict(blind_records())).outcomes
        )
    )
    target.write_text(
        json.dumps(active.as_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    predictions = predict(blind_records())
    metrics = score(predictions)
    analysis = analyse(metrics.outcomes)
    print(metrics.render())
    print()
    print(analysis.render())
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_predictions(predictions=predictions)}")
        print(f"wrote {write_metrics(metrics=metrics)}")
        print(f"wrote {write_error_analysis(analysis=analysis)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
