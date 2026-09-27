"""Independent validation metrics and error analysis.

Scores both evaluators over `independent_benchmark.INDEPENDENT_CASES` and
classifies every incorrect result. Two design choices matter for honesty:

1. **The "paraphrase" subset is objective.** A risky case counts as a paraphrase
   when its text contains none of the literal keywords in the plugin's filter
   rules. That split is computed mechanically from the rule file, not chosen by
   hand, so it cannot be adjusted to flatter a result.
2. **Error causes are assigned by documented deterministic rules**, not case by
   case. Cause attribution is still a judgement, but applying one fixed rule set
   to every error keeps it reproducible and inspectable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluator import KeywordRiskEvaluator, RiskIntentEvaluator
from .independent_benchmark import INDEPENDENT_CASES, AnnotationCase
from .semantic_evaluator import NEGATION_CUES, SemanticRiskEvaluator
from .taxonomy import category_names


_PLUGIN_RULES = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "xiaolin_finance"
    / "rules"
    / "filter_rules.json"
)

FALSE_NEGATIVE = "false_negative"
FALSE_POSITIVE = "false_positive"

#: Documented cause vocabulary, mirroring the phase's categories.
FALSE_NEGATIVE_CAUSES = (
    "missing_intent_signal",
    "taxonomy_ambiguity",
    "language_gap",
    "context_dependency",
)
FALSE_POSITIVE_CAUSES = (
    "insufficient_negation_handling",
    "educational_context_mistaken",
    "quotation_mistaken",
)

_QUOTATION_FRAMING = (
    '"',
    "'",
    "quote",
    "quoted",
    "wrote",
    "claim",
    "claimed",
    "headline",
    "commenter",
    "saying",
)
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


@lru_cache(maxsize=1)
def plugin_keywords() -> tuple[str, ...]:
    """Literal keywords the keyword evaluator matches, read from its rule file."""

    payload = json.loads(_PLUGIN_RULES.read_text(encoding="utf-8"))
    return tuple(
        str(keyword) for rule in payload["rules"] for keyword in rule["keywords"]
    )


def contains_literal_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in plugin_keywords())


@lru_cache(maxsize=1)
def _negation_patterns() -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern) for pattern in NEGATION_CUES)


def has_negation_cue(text: str) -> bool:
    lowered = text.lower()
    return any(pattern.search(lowered) for pattern in _negation_patterns())


def has_quotation_framing(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _QUOTATION_FRAMING)


def has_cjk(text: str) -> bool:
    return bool(_CJK.search(text))


@dataclass(frozen=True, slots=True)
class CategoryMetrics:
    category: str
    true_positive: int
    false_positive: int
    false_negative: int
    precision: float
    recall: float
    f1: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass(frozen=True, slots=True)
class CaseResult:
    case: AnnotationCase
    keyword_categories: tuple[str, ...]
    semantic_categories: tuple[str, ...]

    def predicted(self, evaluator: str) -> tuple[str, ...]:
        return (
            self.keyword_categories if evaluator == "keyword" else self.semantic_categories
        )

    def detected(self, evaluator: str) -> bool:
        return bool(set(self.predicted(evaluator)) & set(self.case.expected_categories))

    def flagged(self, evaluator: str) -> bool:
        return bool(self.predicted(evaluator))

    def is_paraphrase(self) -> bool:
        return self.case.is_risky and not contains_literal_keyword(self.case.text)

    def row(self) -> dict[str, Any]:
        return {
            "id": self.case.case_id,
            "group": self.case.group,
            "text": self.case.text,
            "expected": list(self.case.expected_categories),
            "risk_level": self.case.risk_level,
            "keyword_result": list(self.keyword_categories),
            "semantic_result": list(self.semantic_categories),
            "keyword_correct": self._correct("keyword"),
            "semantic_correct": self._correct("semantic"),
        }

    def _correct(self, evaluator: str) -> bool:
        if self.case.is_risky:
            return self.detected(evaluator)
        return not self.flagged(evaluator)


@dataclass(frozen=True, slots=True)
class ErrorFinding:
    case_id: str
    evaluator: str
    direction: str
    cause: str
    detail: str
    text: str
    expected: tuple[str, ...]
    predicted: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "evaluator": self.evaluator,
            "direction": self.direction,
            "cause": self.cause,
            "detail": self.detail,
            "text": self.text,
            "expected": list(self.expected),
            "predicted": list(self.predicted),
        }


def classify_error(
    case: AnnotationCase, predicted: Sequence[str], *, direction: str
) -> tuple[str, str]:
    """Assign a documented cause to one incorrect result.

    False positives are checked for quotation framing first, because a quoted
    claim the article refutes is a different failure from a genuine
    misjudgement of the article's own voice. False negatives fall through from
    "the expected category was missed although something was flagged"
    (taxonomy ambiguity) to language, then context, then a missing signal.
    """

    text = case.text
    if direction == FALSE_POSITIVE:
        if has_quotation_framing(text):
            return "quotation_mistaken", "text frames the claim as someone else's words"
        if has_negation_cue(text):
            return (
                "insufficient_negation_handling",
                "text negates the claim but a signal still fired",
            )
        return "educational_context_mistaken", "no risky intent; flagged anyway"

    if predicted:
        return (
            "taxonomy_ambiguity",
            f"flagged {sorted(predicted)} instead of {sorted(case.expected_categories)}",
        )
    if has_cjk(text):
        return "language_gap", "non-English phrasing carries no matching signal"
    if has_quotation_framing(text) or text.count(",") >= 2:
        return "context_dependency", "intent depends on surrounding context"
    return "missing_intent_signal", "no signal class fired"


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    """Metrics for one evaluator over the independent benchmark."""

    evaluator: str
    cases: int
    per_category: Mapping[str, CategoryMetrics]
    macro_f1: float
    micro_precision: float
    micro_recall: float
    micro_f1: float
    false_positive_rate: float
    false_negative_rate: float
    paraphrase_total: int
    paraphrase_detected: int
    keyword_subset_total: int
    keyword_subset_detected: int

    @property
    def paraphrase_recall(self) -> float:
        return _ratio(self.paraphrase_detected, self.paraphrase_total)

    @property
    def keyword_subset_recall(self) -> float:
        return _ratio(self.keyword_subset_detected, self.keyword_subset_total)

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluator": self.evaluator,
            "cases": self.cases,
            "per_category": {
                name: metrics.as_dict() for name, metrics in self.per_category.items()
            },
            "macro_f1": self.macro_f1,
            "micro_precision": self.micro_precision,
            "micro_recall": self.micro_recall,
            "micro_f1": self.micro_f1,
            "false_positive_rate": self.false_positive_rate,
            "false_negative_rate": self.false_negative_rate,
            "paraphrase_total": self.paraphrase_total,
            "paraphrase_detected": self.paraphrase_detected,
            "paraphrase_recall": self.paraphrase_recall,
            "keyword_subset_total": self.keyword_subset_total,
            "keyword_subset_detected": self.keyword_subset_detected,
            "keyword_subset_recall": self.keyword_subset_recall,
        }

    def render(self) -> str:
        lines = [
            f"evaluator            : {self.evaluator}",
            f"macro F1             : {self.macro_f1:.3f}",
            f"micro P/R/F1         : {self.micro_precision:.3f} / "
            f"{self.micro_recall:.3f} / {self.micro_f1:.3f}",
            f"false positive rate  : {self.false_positive_rate:.1%}",
            f"false negative rate  : {self.false_negative_rate:.1%}",
            f"paraphrase recall    : {self.paraphrase_recall:.1%}"
            f"  ({self.paraphrase_detected}/{self.paraphrase_total})",
            f"enumerated recall    : {self.keyword_subset_recall:.1%}"
            f"  ({self.keyword_subset_detected}/{self.keyword_subset_total})",
            "per category (P / R / F1):",
        ]
        for name, metrics in sorted(self.per_category.items()):
            lines.append(
                f"  {name:24} {metrics.precision:.3f} / "
                f"{metrics.recall:.3f} / {metrics.f1:.3f}"
                f"   (tp={metrics.true_positive} fp={metrics.false_positive} "
                f"fn={metrics.false_negative})"
            )
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    results: tuple[CaseResult, ...]
    metrics: Mapping[str, EvaluationMetrics]
    errors: tuple[ErrorFinding, ...]

    def case_table(self) -> tuple[dict[str, Any], ...]:
        return tuple(result.row() for result in self.results)

    def errors_for(self, evaluator: str) -> tuple[ErrorFinding, ...]:
        return tuple(item for item in self.errors if item.evaluator == evaluator)

    def cause_summary(self, evaluator: str) -> Mapping[str, int]:
        counts: dict[str, int] = {}
        for item in self.errors_for(evaluator):
            counts[item.cause] = counts.get(item.cause, 0) + 1
        return dict(sorted(counts.items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": len(self.results),
            "metrics": {name: item.as_dict() for name, item in self.metrics.items()},
            "errors": [item.as_dict() for item in self.errors],
            "cause_summary": {
                name: dict(self.cause_summary(name)) for name in self.metrics
            },
        }

    def render(self) -> str:
        blocks = [self.metrics[name].render() for name in sorted(self.metrics)]
        return "\n\n".join(blocks)


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _category_metrics(
    results: Sequence[CaseResult], evaluator: str
) -> Mapping[str, CategoryMetrics]:
    metrics: dict[str, CategoryMetrics] = {}
    for name in category_names():
        tp = fp = fn = 0
        for result in results:
            expected = name in result.case.expected_categories
            predicted = name in result.predicted(evaluator)
            if expected and predicted:
                tp += 1
            elif predicted:
                fp += 1
            elif expected:
                fn += 1
        precision = _ratio(tp, tp + fp)
        recall = _ratio(tp, tp + fn)
        metrics[name] = CategoryMetrics(
            category=name,
            true_positive=tp,
            false_positive=fp,
            false_negative=fn,
            precision=precision,
            recall=recall,
            f1=_f1(precision, recall),
        )
    return metrics


def _evaluation_metrics(
    results: Sequence[CaseResult], evaluator: str
) -> EvaluationMetrics:
    per_category = _category_metrics(results, evaluator)
    risky = [item for item in results if item.case.is_risky]
    no_risk = [item for item in results if not item.case.is_risky]
    paraphrase = [item for item in risky if item.is_paraphrase()]
    enumerated = [item for item in risky if not item.is_paraphrase()]

    tp = sum(item.true_positive for item in per_category.values())
    fp = sum(item.false_positive for item in per_category.values())
    fn = sum(item.false_negative for item in per_category.values())
    micro_precision = _ratio(tp, tp + fp)
    micro_recall = _ratio(tp, tp + fn)

    return EvaluationMetrics(
        evaluator=evaluator,
        cases=len(results),
        per_category=per_category,
        macro_f1=round(
            sum(item.f1 for item in per_category.values()) / len(per_category), 4
        ),
        micro_precision=micro_precision,
        micro_recall=micro_recall,
        micro_f1=_f1(micro_precision, micro_recall),
        false_positive_rate=_ratio(
            sum(1 for item in no_risk if item.flagged(evaluator)), len(no_risk)
        ),
        false_negative_rate=_ratio(
            sum(1 for item in risky if not item.detected(evaluator)), len(risky)
        ),
        paraphrase_total=len(paraphrase),
        paraphrase_detected=sum(1 for item in paraphrase if item.detected(evaluator)),
        keyword_subset_total=len(enumerated),
        keyword_subset_detected=sum(1 for item in enumerated if item.detected(evaluator)),
    )


def _errors_for(
    results: Sequence[CaseResult], evaluator: str
) -> tuple[ErrorFinding, ...]:
    findings: list[ErrorFinding] = []
    for result in results:
        predicted = result.predicted(evaluator)
        if result.case.is_risky:
            if result.detected(evaluator):
                continue
            cause, detail = classify_error(
                result.case, predicted, direction=FALSE_NEGATIVE
            )
            findings.append(
                ErrorFinding(
                    case_id=result.case.case_id,
                    evaluator=evaluator,
                    direction=FALSE_NEGATIVE,
                    cause=cause,
                    detail=detail,
                    text=result.case.text,
                    expected=result.case.expected_categories,
                    predicted=predicted,
                )
            )
        else:
            if not result.flagged(evaluator):
                continue
            cause, detail = classify_error(
                result.case, predicted, direction=FALSE_POSITIVE
            )
            findings.append(
                ErrorFinding(
                    case_id=result.case.case_id,
                    evaluator=evaluator,
                    direction=FALSE_POSITIVE,
                    cause=cause,
                    detail=detail,
                    text=result.case.text,
                    expected=(),
                    predicted=predicted,
                )
            )
    return tuple(findings)


def run_validation(
    cases: Sequence[AnnotationCase] | None = None,
    *,
    keyword: RiskIntentEvaluator | None = None,
    semantic: RiskIntentEvaluator | None = None,
) -> ValidationReport:
    """Run the blind evaluation over the independent benchmark."""

    keyword_evaluator = keyword if keyword is not None else KeywordRiskEvaluator()
    semantic_evaluator = semantic if semantic is not None else SemanticRiskEvaluator()
    active_cases = cases if cases is not None else INDEPENDENT_CASES

    results: list[CaseResult] = []
    for case in active_cases:
        results.append(
            CaseResult(
                case=case,
                keyword_categories=tuple(
                    sorted({r.category for r in keyword_evaluator.evaluate_text(case.text)})
                ),
                semantic_categories=tuple(
                    sorted({r.category for r in semantic_evaluator.evaluate_text(case.text)})
                ),
            )
        )

    errors = (
        *_errors_for(results, "keyword"),
        *_errors_for(results, "semantic"),
    )
    return ValidationReport(
        results=tuple(results),
        metrics={
            "keyword": _evaluation_metrics(results, "keyword"),
            "semantic": _evaluation_metrics(results, "semantic"),
        },
        errors=errors,
    )


def main() -> int:
    report = run_validation()
    print(report.render())
    print()
    for name in ("keyword", "semantic"):
        print(f"{name} error causes:")
        for cause, count in report.cause_summary(name).items():
            print(f"  {cause:34} {count}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
