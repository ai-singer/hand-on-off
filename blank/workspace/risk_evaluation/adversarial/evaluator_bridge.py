"""Evaluator bridge: run an existing evaluator over a generated case.

The bridge only *calls* the evaluator. It reads no rule file, changes no
pattern, and writes nothing back. `semantic_evaluator_v2` is the default target
because it is the current best offline evaluator, but any object with
`evaluate_text` works, which is how the same generated cases can be scored
against v1 or the keyword evaluator for comparison.

`DetectionResult.detected` means "the target category was reported for this
text". `hit` means "the evaluator agreed with the case": detected matches
`expected_detection`. A miss is a risky text that was not flagged; a false
positive is a benign text that was. Both are findings; only misses become
failures, per the Phase 8.1 rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..model import RiskEvaluationResult
from ..semantic_evaluator_v2 import EVALUATOR_NAME, SemanticRiskEvaluatorV2
from .case import AdversarialCase


DEFAULT_EVALUATOR = EVALUATOR_NAME


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """What the evaluator said about one generated case."""

    case_id: str
    target_category: str
    expected_detection: bool
    detected_category: str | None
    detected_categories: tuple[str, ...]
    evaluator: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", dict(self.evidence))

    @property
    def detected(self) -> bool:
        """Was the target category reported?"""

        return self.detected_category is not None

    @property
    def hit(self) -> bool:
        """Did the evaluator agree with the case's expectation?"""

        return self.detected == self.expected_detection

    @property
    def miss(self) -> bool:
        """A risk that guide v2 expects reported, and was not."""

        return self.expected_detection and not self.detected

    @property
    def false_positive(self) -> bool:
        """A control the evaluator flagged anyway."""

        return (not self.expected_detection) and self.detected

    @property
    def status(self) -> str:
        if self.miss:
            return "miss"
        if self.false_positive:
            return "false_positive"
        return "hit"

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "target_category": self.target_category,
            "expected_detection": self.expected_detection,
            "detected_category": self.detected_category,
            "detected_categories": list(self.detected_categories),
            "detected": self.detected,
            "hit": self.hit,
            "miss": self.miss,
            "false_positive": self.false_positive,
            "status": self.status,
            "evaluator": self.evaluator,
            "evidence": dict(sorted(self.evidence.items())),
        }

    def render(self) -> str:
        return (
            f"{self.case_id} [{self.status}] target={self.target_category} "
            f"detected={self.detected_category or 'none'} "
            f"evaluator={self.evaluator}"
        )


def _results_from(
    evaluator: Any, text: str
) -> tuple[tuple[RiskEvaluationResult, ...], Mapping[str, Any]]:
    """Get results plus rich evidence, using `analyze` when it exists."""

    analyze = getattr(evaluator, "analyze", None)
    if callable(analyze):
        analysis = analyze(text)
        return tuple(analysis.results), {
            "statement_source": analysis.statement_source,
            "certainty_level": analysis.certainty_level,
            "market_claim_case": analysis.market_claim_case,
            "suppressed": list(analysis.suppressed),
            "detail": analysis.detail,
        }
    results = tuple(evaluator.evaluate_text(text))
    return results, {}


def evaluate_case(
    case: AdversarialCase,
    evaluator: Any | None = None,
) -> DetectionResult:
    """Score one generated case with one evaluator."""

    active = evaluator if evaluator is not None else SemanticRiskEvaluatorV2()
    results, evidence = _results_from(active, case.text)
    detected = tuple(sorted({result.category for result in results}))
    name = str(getattr(active, "name", type(active).__name__))

    return DetectionResult(
        case_id=case.case_id,
        target_category=case.target_category,
        expected_detection=case.expected_detection,
        detected_category=(
            case.target_category if case.target_category in detected else None
        ),
        detected_categories=detected,
        evaluator=name,
        evidence={
            **evidence,
            "attack_strategy": case.attack_strategy.value,
            "expectation_basis": case.expectation_basis,
            "expectation_strength": str(
                case.metadata.get("expectation_strength", "clear")
            ),
            "text": case.text,
            "severity": case.severity,
            "confidences": {
                result.category: result.confidence for result in results
            },
        },
    )


def evaluate_cases(
    cases: Sequence[AdversarialCase],
    evaluator: Any | None = None,
) -> tuple[DetectionResult, ...]:
    """Score every case with the same evaluator instance."""

    active = evaluator if evaluator is not None else SemanticRiskEvaluatorV2()
    return tuple(evaluate_case(case, active) for case in cases)


def misses(results: Sequence[DetectionResult]) -> tuple[DetectionResult, ...]:
    """The only results that enter the failure repository."""

    return tuple(item for item in results if item.miss)


def false_positives(
    results: Sequence[DetectionResult],
) -> tuple[DetectionResult, ...]:
    return tuple(item for item in results if item.false_positive)


def summarise(results: Sequence[DetectionResult]) -> dict[str, Any]:
    """Counts per evaluator-facing status, plus the per-strategy breakdown."""

    by_strategy: dict[str, dict[str, int]] = {}
    for item in results:
        strategy = str(item.evidence.get("attack_strategy", "unknown"))
        bucket = by_strategy.setdefault(
            strategy, {"cases": 0, "hits": 0, "misses": 0, "false_positives": 0}
        )
        bucket["cases"] += 1
        bucket["hits"] += int(item.hit)
        bucket["misses"] += int(item.miss)
        bucket["false_positives"] += int(item.false_positive)

    miss_items = [item for item in results if item.miss]
    return {
        "cases": len(results),
        "hits": sum(1 for item in results if item.hit),
        "misses": len(miss_items),
        "false_positives": sum(1 for item in results if item.false_positive),
        "attacks": sum(1 for item in results if item.expected_detection),
        "controls": sum(1 for item in results if not item.expected_detection),
        "misses_debatable_expectation": sum(
            1
            for item in miss_items
            if str(item.evidence.get("expectation_strength", "clear")) == "debatable"
        ),
        "by_strategy": dict(sorted(by_strategy.items())),
    }
