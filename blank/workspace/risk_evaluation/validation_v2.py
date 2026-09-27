"""Old versus new evaluator comparison on benchmark `semantic/v3`.

Reuses the metric functions in `validation.py` so the numbers are computed
identically to every earlier phase — the comparison changes what is measured
against, not how it is measured.

Two metrics are added for v2, because the capabilities it introduces are not
visible in precision and recall:

- **attribution accuracy** — did the evaluator classify `statement_source` the
  way the guide's rules say it should?
- **market prediction accuracy** — on the `market_boundary` cases, did the
  evaluator agree with the guide about whether the text is a prediction at all?
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from . import validation as base
from .benchmark_v2 import (
    MARKET_BOUNDARY,
    V3_CASES,
    AnnotationCaseV2,
)
from .evaluator import KeywordRiskEvaluator
from .semantic_evaluator import SemanticRiskEvaluator
from .semantic_evaluator_v2 import RiskAnalysisV2, SemanticRiskEvaluatorV2


KEYWORD = "keyword"
SEMANTIC_V1 = "semantic_v1"
SEMANTIC_V2 = "semantic_v2"
EVALUATOR_KEYS = (KEYWORD, SEMANTIC_V1, SEMANTIC_V2)

MARKET_PREDICTION = "market_prediction"
ATTRIBUTION = "attribution"


@dataclass(frozen=True, slots=True)
class V2CaseResult:
    """Duck-types `validation.CaseResult` so the metric functions are reusable."""

    case: AnnotationCaseV2
    keyword_categories: tuple[str, ...]
    semantic_v1_categories: tuple[str, ...]
    semantic_v2_categories: tuple[str, ...]
    v2_analysis: RiskAnalysisV2 | None

    def predicted(self, evaluator: str) -> tuple[str, ...]:
        return {
            KEYWORD: self.keyword_categories,
            SEMANTIC_V1: self.semantic_v1_categories,
            SEMANTIC_V2: self.semantic_v2_categories,
        }[evaluator]

    def detected(self, evaluator: str) -> bool:
        return bool(set(self.predicted(evaluator)) & set(self.case.expected_categories))

    def flagged(self, evaluator: str) -> bool:
        return bool(self.predicted(evaluator))

    def is_paraphrase(self) -> bool:
        return self.case.is_risky and not base.contains_literal_keyword(self.case.text)

    @property
    def attribution_correct(self) -> bool:
        return (
            self.v2_analysis is not None
            and self.v2_analysis.statement_source == self.case.statement_source
        )

    @property
    def is_market_boundary(self) -> bool:
        return self.case.focus == MARKET_BOUNDARY

    def market_prediction_correct(self, evaluator: str) -> bool:
        expected = MARKET_PREDICTION in self.case.expected_categories
        return (MARKET_PREDICTION in self.predicted(evaluator)) == expected


@dataclass(frozen=True, slots=True)
class V2ComparisonReport:
    results: tuple[V2CaseResult, ...]
    metrics: Mapping[str, base.EvaluationMetrics]

    def attribution_accuracy(self) -> float:
        if not self.results:
            return 0.0
        return round(
            sum(1 for item in self.results if item.attribution_correct) / len(self.results),
            4,
        )

    def market_prediction_accuracy(self, evaluator: str) -> float:
        boundary = [item for item in self.results if item.is_market_boundary]
        if not boundary:
            return 0.0
        return round(
            sum(1 for item in boundary if item.market_prediction_correct(evaluator))
            / len(boundary),
            4,
        )

    def attribution_errors(self) -> tuple[V2CaseResult, ...]:
        return tuple(item for item in self.results if not item.attribution_correct)

    def case_table(self) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        for item in self.results:
            rows.append(
                {
                    "id": item.case.case_id,
                    "group": item.case.group,
                    "focus": item.case.focus,
                    "text": item.case.text,
                    "expected": list(item.case.expected_categories),
                    "statement_source": item.case.statement_source,
                    "certainty_level": item.case.certainty_level,
                    "keyword": list(item.keyword_categories),
                    "semantic_v1": list(item.semantic_v1_categories),
                    "semantic_v2": list(item.semantic_v2_categories),
                    "detected_source": (
                        item.v2_analysis.statement_source if item.v2_analysis else None
                    ),
                    "market_claim_case": (
                        item.v2_analysis.market_claim_case if item.v2_analysis else None
                    ),
                    "suppressed": (
                        list(item.v2_analysis.suppressed) if item.v2_analysis else []
                    ),
                    "v1_correct": item.detected(SEMANTIC_V1)
                    if item.case.is_risky
                    else not item.flagged(SEMANTIC_V1),
                    "v2_correct": item.detected(SEMANTIC_V2)
                    if item.case.is_risky
                    else not item.flagged(SEMANTIC_V2),
                }
            )
        return tuple(rows)

    def deltas(self, metric: str, *, baseline: str = SEMANTIC_V1, candidate: str = SEMANTIC_V2) -> float:
        return round(
            self.metrics[candidate].as_dict()[metric]
            - self.metrics[baseline].as_dict()[metric],
            4,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cases": len(self.results),
            "metrics": {name: item.as_dict() for name, item in self.metrics.items()},
            "attribution_accuracy": self.attribution_accuracy(),
            "market_prediction_accuracy": {
                name: self.market_prediction_accuracy(name) for name in EVALUATOR_KEYS
            },
        }

    def render(self) -> str:
        lines = []
        for name in EVALUATOR_KEYS:
            lines.append(f"=== {name} ===")
            lines.append(self.metrics[name].render())
            lines.append("")
        lines.append(f"attribution accuracy (v2 only): {self.attribution_accuracy():.1%}")
        for name in EVALUATOR_KEYS:
            lines.append(
                f"market prediction accuracy [{name}]: "
                f"{self.market_prediction_accuracy(name):.1%}"
            )
        lines.append("")
        for metric in ("macro_f1", "micro_precision", "micro_recall", "false_positive_rate", "false_negative_rate"):
            lines.append(
                f"  {metric:22} {self.metrics[SEMANTIC_V1].as_dict()[metric]:.4f} -> "
                f"{self.metrics[SEMANTIC_V2].as_dict()[metric]:.4f} "
                f"({self.deltas(metric):+.4f})"
            )
        return "\n".join(lines)


def run_comparison(
    cases: Sequence[AnnotationCaseV2] | None = None,
    *,
    keyword: KeywordRiskEvaluator | None = None,
    semantic_v1: SemanticRiskEvaluator | None = None,
    semantic_v2: SemanticRiskEvaluatorV2 | None = None,
) -> V2ComparisonReport:
    """Score all three evaluators on the same v3 cases."""

    active_keyword = keyword if keyword is not None else KeywordRiskEvaluator()
    active_v1 = semantic_v1 if semantic_v1 is not None else SemanticRiskEvaluator()
    active_v2 = semantic_v2 if semantic_v2 is not None else SemanticRiskEvaluatorV2()
    active_cases = cases if cases is not None else V3_CASES

    results: list[V2CaseResult] = []
    for case in active_cases:
        analysis = active_v2.analyze(case.text)
        results.append(
            V2CaseResult(
                case=case,
                keyword_categories=tuple(
                    sorted({r.category for r in active_keyword.evaluate_text(case.text)})
                ),
                semantic_v1_categories=tuple(
                    sorted({r.category for r in active_v1.evaluate_text(case.text)})
                ),
                semantic_v2_categories=analysis.categories,
                v2_analysis=analysis,
            )
        )

    return V2ComparisonReport(
        results=tuple(results),
        metrics={
            name: base._evaluation_metrics(results, name) for name in EVALUATOR_KEYS
        },
    )


def main() -> int:
    report = run_comparison()
    print(report.render())
    print()
    print("attribution errors:")
    for item in report.attribution_errors():
        assert item.v2_analysis is not None
        print(
            f"  {item.case.case_id}: expected {item.case.statement_source}, "
            f"detected {item.v2_analysis.statement_source} <- {item.case.text}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
