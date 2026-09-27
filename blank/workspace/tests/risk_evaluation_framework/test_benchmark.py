from __future__ import annotations

import json
import unittest

from risk_evaluation.benchmark import (
    BENCHMARK_CASES,
    PARAPHRASE,
    POSITIVE,
    SAFE,
    BenchmarkCase,
    run_benchmark,
)
from risk_evaluation.taxonomy import category_names


#: Recorded in docs/PHASE_7_1_RISK_EVALUATION_FRAMEWORK_REPORT.md. If the rules
#: or the evaluator change, update that report in the same change: the report
#: claims specific measured rates and must not drift from reality.
DOCUMENTED_POSITIVE_RATE = 1.0
DOCUMENTED_PARAPHRASE_RATE = 0.0
DOCUMENTED_FALSE_POSITIVE_RATE = 0.0


class BenchmarkCompositionTests(unittest.TestCase):
    def test_benchmark_has_twenty_cases_in_the_required_mix(self) -> None:
        kinds = [case.kind for case in BENCHMARK_CASES]

        self.assertEqual(len(BENCHMARK_CASES), 20)
        self.assertEqual(kinds.count(POSITIVE), 10)
        self.assertEqual(kinds.count(SAFE), 5)
        self.assertEqual(kinds.count(PARAPHRASE), 5)

    def test_case_ids_are_unique_and_cases_are_well_formed(self) -> None:
        identifiers = [case.case_id for case in BENCHMARK_CASES]

        self.assertEqual(len(identifiers), len(set(identifiers)))
        for case in BENCHMARK_CASES:
            self.assertIsInstance(case, BenchmarkCase)
            self.assertTrue(case.text.strip(), case.case_id)
            if case.kind == SAFE:
                self.assertEqual(case.expected, (), case.case_id)
            else:
                self.assertTrue(case.expected, case.case_id)
                for name in case.expected:
                    self.assertIn(name, category_names(), case.case_id)


class BenchmarkMeasurementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = run_benchmark()

    def test_benchmark_runs_with_the_keyword_evaluator(self) -> None:
        self.assertEqual(self.report.evaluator, "keyword-xiaolin-finance-v1")
        self.assertEqual(len(self.report.outcomes), 20)

    def test_enumerated_wording_is_always_detected(self) -> None:
        self.assertEqual(len(self.report.positive), 10)
        self.assertEqual(self.report.positive_rate, DOCUMENTED_POSITIVE_RATE)

    def test_paraphrase_detection_is_the_capability_boundary(self) -> None:
        self.assertEqual(len(self.report.paraphrase), 5)
        self.assertEqual(self.report.paraphrase_rate, DOCUMENTED_PARAPHRASE_RATE)
        self.assertEqual(len(self.report.missed), 5)
        for outcome in self.report.missed:
            self.assertEqual(outcome.case.kind, PARAPHRASE)
            self.assertEqual(outcome.categories, ())

    def test_safe_material_is_not_flagged(self) -> None:
        self.assertEqual(len(self.report.safe), 5)
        self.assertEqual(
            self.report.false_positive_rate, DOCUMENTED_FALSE_POSITIVE_RATE
        )
        self.assertEqual(self.report.false_positives, ())

    def test_per_category_counts_sum_to_the_expected_totals(self) -> None:
        per_category = self.report.per_category()
        total_expected = sum(expected for _, expected in per_category.values())

        # 12 expectations across the 10 positive cases plus 6 across the 5
        # paraphrase cases; safe cases expect nothing.
        self.assertEqual(total_expected, 18)
        self.assertEqual(
            per_category["investment_advice"], (3, 5)
        )
        self.assertEqual(per_category["unverified_information"], (3, 3))
        self.assertEqual(per_category["emotional_manipulation"], (2, 3))
        self.assertEqual(per_category["financial_guarantee"], (2, 3))
        self.assertEqual(per_category["market_prediction"], (2, 4))

    def test_report_serializes(self) -> None:
        payload = json.loads(json.dumps(self.report.as_dict()))

        self.assertEqual(payload["positive"]["total"], 10)
        self.assertEqual(payload["paraphrase"]["detected"], 0)
        self.assertEqual(len(payload["outcomes"]), 20)
        self.assertIn("capability boundary", self.report.render())


if __name__ == "__main__":
    unittest.main()
