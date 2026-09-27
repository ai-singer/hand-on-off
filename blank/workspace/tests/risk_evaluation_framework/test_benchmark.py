from __future__ import annotations

import json
import unittest

from risk_evaluation.benchmark import (
    ADVERSARIAL,
    BENCHMARK_CASES,
    BENCHMARK_KINDS,
    KEYWORD,
    PARAPHRASE,
    SAFE,
    BenchmarkCase,
    run_benchmark,
)
from risk_evaluation.taxonomy import category_names


#: The keyword evaluator's measured baseline on the expanded 50-case benchmark.
#: Recorded in docs/PHASE_7_2_SEMANTIC_RISK_EVALUATOR_REPORT.md. If the rules
#: change, update that report in the same change.
DOCUMENTED_KEYWORD_RECALL = 1.0
DOCUMENTED_PARAPHRASE_RECALL = 0.05
DOCUMENTED_FALSE_POSITIVE_RATE = 0.0
DOCUMENTED_ADVERSARIAL_ACCURACY = 0.4


class BenchmarkCompositionTests(unittest.TestCase):
    def test_benchmark_has_fifty_cases_in_the_required_mix(self) -> None:
        kinds = [case.kind for case in BENCHMARK_CASES]

        self.assertEqual(len(BENCHMARK_CASES), 50)
        self.assertEqual(kinds.count(KEYWORD), 10)
        self.assertEqual(kinds.count(SAFE), 10)
        self.assertEqual(kinds.count(PARAPHRASE), 20)
        self.assertEqual(kinds.count(ADVERSARIAL), 10)
        self.assertEqual(set(kinds), set(BENCHMARK_KINDS))

    def test_case_ids_are_unique_and_cases_are_well_formed(self) -> None:
        identifiers = [case.case_id for case in BENCHMARK_CASES]

        self.assertEqual(len(identifiers), len(set(identifiers)))
        for case in BENCHMARK_CASES:
            self.assertIsInstance(case, BenchmarkCase)
            self.assertTrue(case.text.strip(), case.case_id)
            self.assertIn(case.kind, BENCHMARK_KINDS, case.case_id)
            for name in case.expected:
                self.assertIn(name, category_names(), case.case_id)

    def test_only_safe_cases_expect_no_risk(self) -> None:
        """Adversarial cases include both directions, safe cases never a risk."""

        for case in BENCHMARK_CASES:
            if case.kind == SAFE:
                self.assertEqual(case.expected, (), case.case_id)
            if case.kind in (KEYWORD, PARAPHRASE):
                self.assertTrue(case.expected, case.case_id)

        risky_adversarial = [case for case in BENCHMARK_CASES if case.kind == ADVERSARIAL and case.expected]
        safe_adversarial = [case for case in BENCHMARK_CASES if case.kind == ADVERSARIAL and not case.expected]
        self.assertEqual(len(risky_adversarial), 5)
        self.assertEqual(len(safe_adversarial), 5)


class BenchmarkMeasurementTests(unittest.TestCase):
    """The keyword evaluator's capability boundary, unchanged by Phase 7.2."""

    def setUp(self) -> None:
        self.report = run_benchmark()

    def test_benchmark_runs_with_the_keyword_evaluator(self) -> None:
        self.assertEqual(self.report.evaluator, "keyword-xiaolin-finance-v1")
        self.assertEqual(len(self.report.outcomes), 50)

    def test_enumerated_wording_is_always_detected(self) -> None:
        self.assertEqual(len(self.report.keyword), 10)
        self.assertEqual(self.report.keyword_recall, DOCUMENTED_KEYWORD_RECALL)

    def test_paraphrase_detection_is_the_capability_boundary(self) -> None:
        self.assertEqual(len(self.report.paraphrase), 20)
        self.assertEqual(self.report.paraphrase_recall, DOCUMENTED_PARAPHRASE_RECALL)
        self.assertEqual(len([o for o in self.report.paraphrase if o.matched]), 1)
        # 19 of 20 paraphrases, plus all 5 risky adversarial cases, are missed.
        self.assertEqual(len(self.report.missed), 24)

    def test_safe_material_is_not_flagged(self) -> None:
        self.assertEqual(len(self.report.safe), 10)
        self.assertEqual(
            self.report.false_positive_rate, DOCUMENTED_FALSE_POSITIVE_RATE
        )
        self.assertEqual([o for o in self.report.safe if o.flagged], [])

    def test_adversarial_accuracy_is_recorded(self) -> None:
        self.assertEqual(len(self.report.adversarial), 10)
        self.assertEqual(
            self.report.adversarial_accuracy, DOCUMENTED_ADVERSARIAL_ACCURACY
        )
        # The keyword evaluator flags a disclaimed guarantee as a guarantee.
        self.assertEqual(len(self.report.adversarial_false_positives), 1)

    def test_flagged_and_matched_are_distinct(self) -> None:
        """A safe case can be flagged without matching any expected category."""

        for outcome in self.report.outcomes:
            if not outcome.case.is_risky:
                self.assertFalse(outcome.matched)
            self.assertEqual(outcome.correct, outcome.matched if outcome.case.is_risky else not outcome.flagged)

    def test_per_category_counts_sum_to_the_expected_totals(self) -> None:
        per_category = self.report.per_category()
        total_expected = sum(expected for _, expected in per_category.values())

        self.assertEqual(total_expected, sum(len(c.expected) for c in BENCHMARK_CASES))
        self.assertEqual(total_expected, 42)
        self.assertEqual(per_category["investment_advice"], (3, 13))
        self.assertEqual(per_category["unverified_information"], (3, 7))
        self.assertEqual(per_category["financial_guarantee"], (2, 7))

    def test_report_serializes(self) -> None:
        payload = json.loads(json.dumps(self.report.as_dict()))

        self.assertEqual(payload["counts"][KEYWORD]["total"], 10)
        self.assertEqual(payload["counts"][PARAPHRASE]["total"], 20)
        self.assertEqual(len(payload["outcomes"]), 50)
        self.assertIn("capability boundary", self.report.render())


if __name__ == "__main__":
    unittest.main()
