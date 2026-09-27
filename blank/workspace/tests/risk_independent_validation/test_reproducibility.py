from __future__ import annotations

import json
import unittest

from risk_evaluation.independent_benchmark import INDEPENDENT_CASES
from risk_evaluation.validation import (
    FALSE_NEGATIVE,
    FALSE_NEGATIVE_CAUSES,
    FALSE_POSITIVE,
    FALSE_POSITIVE_CAUSES,
    classify_error,
    run_validation,
)


DOCUMENTED_METRICS = {
    ("keyword", "macro_f1"): 0.2841,
    ("keyword", "micro_precision"): 0.7333,
    ("keyword", "micro_recall"): 0.1774,
    ("keyword", "micro_f1"): 0.2857,
    ("keyword", "false_positive_rate"): 0.075,
    ("keyword", "false_negative_rate"): 0.8167,
    ("keyword", "paraphrase_recall"): 0.0,
    ("keyword", "keyword_subset_recall"): 0.9167,
    ("semantic", "macro_f1"): 0.8344,
    ("semantic", "micro_precision"): 0.8475,
    ("semantic", "micro_recall"): 0.8065,
    ("semantic", "micro_f1"): 0.8265,
    ("semantic", "false_positive_rate"): 0.15,
    ("semantic", "false_negative_rate"): 0.1667,
    ("semantic", "paraphrase_recall"): 0.7917,
    ("semantic", "keyword_subset_recall"): 1.0,
}


class ReproducibilityTests(unittest.TestCase):
    """Same frozen evaluator, same benchmark, same numbers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.first = run_validation()
        cls.second = run_validation()

    def test_two_runs_produce_identical_metrics(self) -> None:
        self.assertEqual(self.first.as_dict()["metrics"], self.second.as_dict()["metrics"])

    def test_two_runs_produce_identical_case_rows(self) -> None:
        self.assertEqual(self.first.case_table(), self.second.case_table())

    def test_two_runs_produce_identical_findings(self) -> None:
        self.assertEqual(
            [item.as_dict() for item in self.first.errors],
            [item.as_dict() for item in self.second.errors],
        )

    def test_measured_metrics_match_the_documented_report(self) -> None:
        for (evaluator, metric), expected in DOCUMENTED_METRICS.items():
            with self.subTest(evaluator=evaluator, metric=metric):
                self.assertEqual(self.first.metrics[evaluator].as_dict()[metric], expected)

    def test_case_table_covers_every_case(self) -> None:
        rows = self.first.case_table()

        self.assertEqual(len(rows), len(INDEPENDENT_CASES))
        self.assertEqual(
            [row["id"] for row in rows],
            [case.case_id for case in INDEPENDENT_CASES],
        )

    def test_each_row_carries_both_evaluator_results(self) -> None:
        for row in self.first.case_table():
            self.assertEqual(
                set(row),
                {
                    "id",
                    "group",
                    "text",
                    "expected",
                    "risk_level",
                    "keyword_result",
                    "semantic_result",
                    "keyword_correct",
                    "semantic_correct",
                },
                row["id"],
            )


class ContaminationSensitivityTests(unittest.TestCase):
    """How much of the headline result survives removing reused texts.

    These cases are **not** removed from the benchmark. This is a published
    sensitivity check on the 62 texts that do not appear in the development
    benchmark, so a reader can see the contamination-adjusted estimate next to
    the headline one.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from risk_evaluation.benchmark import BENCHMARK_CASES

        development = {case.text for case in BENCHMARK_CASES}
        cls.fresh = tuple(
            case for case in INDEPENDENT_CASES if case.text not in development
        )
        cls.report = run_validation(cls.fresh)

    def test_subset_size(self) -> None:
        self.assertEqual(len(self.fresh), 62)

    def test_contamination_adjusted_semantic_metrics(self) -> None:
        metrics = self.report.metrics["semantic"]

        self.assertEqual(metrics.macro_f1, 0.7424)
        self.assertEqual(metrics.paraphrase_recall, 0.6897)
        self.assertEqual(metrics.false_positive_rate, 0.2222)
        self.assertEqual(metrics.false_negative_rate, 0.2571)

    def test_contamination_adjusted_keyword_metrics(self) -> None:
        metrics = self.report.metrics["keyword"]

        self.assertEqual(metrics.macro_f1, 0.2061)
        self.assertEqual(metrics.paraphrase_recall, 0.0)

    def test_reused_texts_flatter_both_evaluators(self) -> None:
        full = run_validation()

        self.assertGreater(
            full.metrics["semantic"].macro_f1,
            self.report.metrics["semantic"].macro_f1,
        )
        self.assertGreater(
            full.metrics["semantic"].paraphrase_recall,
            self.report.metrics["semantic"].paraphrase_recall,
        )
        self.assertLess(
            full.metrics["semantic"].false_positive_rate,
            self.report.metrics["semantic"].false_positive_rate,
        )

    def test_adjusted_paraphrase_recall_is_still_below_the_in_sample_figure(self) -> None:
        self.assertLess(self.report.metrics["semantic"].paraphrase_recall, 0.95)


class ErrorClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_validation()

    def test_every_incorrect_result_is_classified(self) -> None:
        for evaluator in ("keyword", "semantic"):
            metrics = self.report.metrics[evaluator]
            risky = sum(1 for c in INDEPENDENT_CASES if c.is_risky)
            no_risk = len(INDEPENDENT_CASES) - risky
            expected_errors = round(metrics.false_negative_rate * risky) + round(
                metrics.false_positive_rate * no_risk
            )
            self.assertEqual(len(self.report.errors_for(evaluator)), expected_errors)

    def test_causes_come_from_the_documented_vocabulary(self) -> None:
        for finding in self.report.errors:
            allowed = (
                FALSE_NEGATIVE_CAUSES
                if finding.direction == FALSE_NEGATIVE
                else FALSE_POSITIVE_CAUSES
            )
            self.assertIn(finding.cause, allowed, finding.case_id)

    def test_cause_summary_matches_the_findings(self) -> None:
        for evaluator in ("keyword", "semantic"):
            findings = self.report.errors_for(evaluator)
            summary = self.report.cause_summary(evaluator)

            self.assertEqual(sum(summary.values()), len(findings))
            for cause, count in summary.items():
                self.assertEqual(
                    count, sum(1 for item in findings if item.cause == cause), cause
                )

    def test_missing_intent_signal_dominates_the_keyword_evaluator(self) -> None:
        summary = self.report.cause_summary("keyword")

        self.assertGreater(summary["missing_intent_signal"], 40)

    def test_quotation_errors_appear_for_both_evaluators(self) -> None:
        for evaluator in ("keyword", "semantic"):
            causes = {item.cause for item in self.report.errors_for(evaluator)}
            self.assertIn("quotation_mistaken", causes, evaluator)

    def test_classification_rules_are_deterministic(self) -> None:
        case = next(c for c in INDEPENDENT_CASES if c.case_id == "bd-16")

        first = classify_error(case, ("financial_guarantee",), direction=FALSE_POSITIVE)
        second = classify_error(case, ("financial_guarantee",), direction=FALSE_POSITIVE)

        self.assertEqual(first, second)
        self.assertEqual(first[0], "quotation_mistaken")

    def test_taxonomy_ambiguity_is_used_when_a_wrong_category_was_flagged(self) -> None:
        case = next(c for c in INDEPENDENT_CASES if c.case_id == "mp-06")

        cause, _ = classify_error(case, ("emotional_manipulation",), direction=FALSE_NEGATIVE)

        self.assertEqual(cause, "taxonomy_ambiguity")

    def test_language_gap_is_used_for_unmatched_chinese(self) -> None:
        case = next(c for c in INDEPENDENT_CASES if c.case_id == "mp-15")

        cause, _ = classify_error(case, (), direction=FALSE_NEGATIVE)

        self.assertEqual(cause, "language_gap")


class ReportGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_validation()

    def test_report_serializes(self) -> None:
        payload = json.loads(json.dumps(self.report.as_dict()))

        self.assertEqual(payload["cases"], 100)
        self.assertEqual(set(payload["metrics"]), {"keyword", "semantic"})
        self.assertEqual(len(payload["errors"]), len(self.report.errors))

    def test_report_renders_both_evaluators(self) -> None:
        rendered = self.report.render()

        self.assertIn("keyword", rendered)
        self.assertIn("semantic", rendered)
        self.assertIn("macro F1", rendered)
        self.assertIn("paraphrase recall", rendered)

    def test_semantic_evaluator_beats_the_keyword_baseline_on_macro_f1(self) -> None:
        self.assertGreater(
            self.report.metrics["semantic"].macro_f1,
            self.report.metrics["keyword"].macro_f1,
        )

    def test_semantic_evaluator_pays_a_higher_false_positive_rate(self) -> None:
        self.assertGreater(
            self.report.metrics["semantic"].false_positive_rate,
            self.report.metrics["keyword"].false_positive_rate,
        )

    def test_independent_paraphrase_recall_is_below_the_in_sample_figure(self) -> None:
        """Phase 7.2 measured 95% in-sample; the independent figure is lower."""

        independent = self.report.metrics["semantic"].paraphrase_recall

        self.assertLess(independent, 0.95)
        self.assertGreater(independent, 0.5)

    def test_error_findings_serialize(self) -> None:
        for finding in self.report.errors:
            payload = json.loads(json.dumps(finding.as_dict()))
            self.assertEqual(payload["case_id"], finding.case_id)
            self.assertIn(payload["direction"], (FALSE_NEGATIVE, FALSE_POSITIVE))


if __name__ == "__main__":
    unittest.main()
