from __future__ import annotations

import json
import unittest

from risk_evaluation.independent_benchmark import AnnotationCase, RISK, SAFE
from risk_evaluation.model import RiskEvaluationResult
from risk_evaluation.validation import (
    contains_literal_keyword,
    run_validation,
)


class _FixedEvaluator:
    """Returns pre-set categories per text, so metrics can be hand-checked."""

    name = "fixed"

    def __init__(self, mapping: dict[str, tuple[str, ...]]) -> None:
        self._mapping = mapping

    def evaluate_text(self, text, *, source_ids=()):
        return tuple(
            RiskEvaluationResult(
                category=name,
                intent="stub",
                confidence=0.5,
                evidence_required=(),
                severity="warning",
                action="downrank",
                evaluator=self.name,
            )
            for name in self._mapping.get(text, ())
        )

    def evaluate_artifact(self, artifact):
        return ()


def _risk(case_id: str, text: str, expected: tuple[str, ...]) -> AnnotationCase:
    return AnnotationCase(case_id, RISK, text, expected, "synthetic")


def _safe(case_id: str, text: str) -> AnnotationCase:
    return AnnotationCase(case_id, SAFE, text, (), "synthetic")


#: Two risky cases and two safe ones, small enough to compute by hand.
CASES = (
    _risk("r-1", "alpha", ("investment_advice",)),
    _risk("r-2", "beta", ("market_prediction",)),
    _safe("s-1", "gamma"),
    _safe("s-2", "delta"),
)


class MetricArithmeticTests(unittest.TestCase):
    def _metrics(self, keyword_map, semantic_map=None):
        report = run_validation(
            CASES,
            keyword=_FixedEvaluator(keyword_map),
            semantic=_FixedEvaluator(semantic_map if semantic_map is not None else {}),
        )
        return report.metrics

    def test_perfect_detection_yields_unit_scores(self) -> None:
        metrics = self._metrics(
            {"alpha": ("investment_advice",), "beta": ("market_prediction",)}
        )["keyword"]

        self.assertEqual(metrics.false_negative_rate, 0.0)
        self.assertEqual(metrics.false_positive_rate, 0.0)
        self.assertEqual(metrics.micro_precision, 1.0)
        self.assertEqual(metrics.micro_recall, 1.0)
        self.assertEqual(metrics.micro_f1, 1.0)

    def test_detecting_nothing_yields_zero_recall(self) -> None:
        metrics = self._metrics({})["keyword"]

        self.assertEqual(metrics.micro_recall, 0.0)
        self.assertEqual(metrics.false_negative_rate, 1.0)
        self.assertEqual(metrics.false_positive_rate, 0.0)

    def test_flagging_everything_yields_unit_false_positive_rate(self) -> None:
        metrics = self._metrics(
            {
                "alpha": ("investment_advice",),
                "beta": ("market_prediction",),
                "gamma": ("investment_advice",),
                "delta": ("investment_advice",),
            }
        )["keyword"]

        self.assertEqual(metrics.false_positive_rate, 1.0)
        self.assertEqual(metrics.false_negative_rate, 0.0)
        self.assertLess(metrics.micro_precision, 1.0)

    def test_per_category_counts_are_exact(self) -> None:
        metrics = self._metrics(
            {"alpha": ("investment_advice",), "gamma": ("investment_advice",)}
        )["keyword"]
        advice = metrics.per_category["investment_advice"]

        # alpha is a true positive; gamma is a false positive; nothing else.
        self.assertEqual(advice.true_positive, 1)
        self.assertEqual(advice.false_positive, 1)
        self.assertEqual(advice.false_negative, 0)
        self.assertEqual(advice.precision, 0.5)
        self.assertEqual(advice.recall, 1.0)

    def test_a_missed_category_is_a_false_negative(self) -> None:
        metrics = self._metrics(
            {"alpha": ("investment_advice",)}
        )["keyword"]
        prediction = metrics.per_category["market_prediction"]

        self.assertEqual(prediction.false_negative, 1)
        self.assertEqual(prediction.recall, 0.0)
        self.assertEqual(prediction.f1, 0.0)

    def test_macro_f1_is_the_mean_of_per_category_f1(self) -> None:
        metrics = self._metrics(
            {"alpha": ("investment_advice",), "beta": ("market_prediction",)}
        )["keyword"]
        expected = round(
            sum(item.f1 for item in metrics.per_category.values())
            / len(metrics.per_category),
            4,
        )

        self.assertEqual(metrics.macro_f1, expected)
        self.assertEqual(metrics.macro_f1, 0.4)

    def test_f1_handles_zero_precision_and_recall(self) -> None:
        metrics = self._metrics({})["keyword"]

        for item in metrics.per_category.values():
            self.assertEqual(item.f1, 0.0)

    def test_metrics_serialize(self) -> None:
        metrics = self._metrics({"alpha": ("investment_advice",)})["keyword"]
        payload = json.loads(json.dumps(metrics.as_dict()))

        self.assertEqual(payload["cases"], 4)
        self.assertIn("per_category", payload)
        self.assertIn("macro_f1", payload)

    def test_render_lists_every_category(self) -> None:
        rendered = self._metrics({})["keyword"].render()

        for name in ("investment_advice", "market_prediction", "financial_guarantee"):
            self.assertIn(name, rendered)


class ParaphraseSubsetTests(unittest.TestCase):
    """The paraphrase split must be mechanical, not chosen by hand."""

    def test_enumerated_text_is_detected_as_enumerated(self) -> None:
        self.assertTrue(contains_literal_keyword("Buy now for a guaranteed return."))

    def test_paraphrased_text_is_not_enumerated(self) -> None:
        self.assertFalse(contains_literal_keyword("You should buy this stock today."))

    def test_chinese_enumeration_is_recognised(self) -> None:
        self.assertTrue(contains_literal_keyword("立即买入这只股票。"))

    def test_the_subset_is_computed_from_the_plugin_rule_file(self) -> None:
        from risk_evaluation.validation import plugin_keywords

        keywords = plugin_keywords()

        self.assertTrue(keywords)
        self.assertIn("guaranteed return", keywords)
        self.assertIn("立即买入", keywords)

    def test_subset_recall_is_reported_separately(self) -> None:
        report = run_validation(
            CASES,
            keyword=_FixedEvaluator({"alpha": ("investment_advice",)}),
            semantic=_FixedEvaluator({}),
        )
        metrics = report.metrics["keyword"]

        # Neither synthetic case contains an enumerated keyword, so the whole
        # risky set counts as paraphrase and the enumerated subset is empty.
        self.assertEqual(metrics.paraphrase_total, 2)
        self.assertEqual(metrics.keyword_subset_total, 0)
        self.assertEqual(metrics.paraphrase_recall, 0.5)

    def test_zero_division_returns_zero(self) -> None:
        report = run_validation(
            (_safe("s-1", "gamma"),),
            keyword=_FixedEvaluator({}),
            semantic=_FixedEvaluator({}),
        )
        metrics = report.metrics["keyword"]

        self.assertEqual(metrics.paraphrase_total, 0)
        self.assertEqual(metrics.paraphrase_recall, 0.0)
        self.assertEqual(metrics.false_negative_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
