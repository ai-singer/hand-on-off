"""Old versus new on the same cases: does v2 actually improve anything?

The numbers asserted here are the Phase 7.5 measurements. They are pinned so
that a later change to the evaluator, the taxonomy, the benchmark or the metric
code cannot silently move a published result. Changing one of these constants is
a deliberate act that requires re-measuring and re-freezing.
"""

from __future__ import annotations

import json
import unittest

from risk_evaluation.benchmark_v2 import V3_CASES, decontaminated_v3_cases
from risk_evaluation.validation_v2 import (
    EVALUATOR_KEYS,
    SEMANTIC_V1,
    SEMANTIC_V2,
    V2ComparisonReport,
    run_comparison,
)

#: semantic/v3 as published -- 120 cases, 32 of them reused development texts.
V3_MACRO_F1 = {SEMANTIC_V1: 0.7721, SEMANTIC_V2: 0.8174}
V3_FALSE_POSITIVE_RATE = {SEMANTIC_V1: 0.18, SEMANTIC_V2: 0.08}

#: semantic/v4 -- the decontaminated subset. The improvement must survive here
#: too, or it is an artefact of the reused cases rather than a real gain.
V4_MACRO_F1 = {SEMANTIC_V1: 0.6636, SEMANTIC_V2: 0.7236}
V4_FALSE_POSITIVE_RATE = {SEMANTIC_V1: 0.1951, SEMANTIC_V2: 0.0976}


class SharedReportTests(unittest.TestCase):
    """One report instance for the whole class: the comparison is deterministic."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_comparison()

    def test_all_three_evaluators_are_scored(self) -> None:
        self.assertEqual(set(self.report.metrics), set(EVALUATOR_KEYS))

    def test_every_case_is_scored_once_per_evaluator(self) -> None:
        self.assertEqual(len(self.report.results), len(V3_CASES))
        for item in self.report.results:
            for key in EVALUATOR_KEYS:
                self.assertIsInstance(item.predicted(key), tuple)

    def test_report_is_json_serializable(self) -> None:
        json.dumps(self.report.as_dict(), sort_keys=True)

    def test_case_table_has_a_row_per_case(self) -> None:
        rows = self.report.case_table()

        self.assertEqual(len(rows), len(V3_CASES))
        self.assertEqual({row["id"] for row in rows}, {c.case_id for c in V3_CASES})

    def test_case_table_records_what_each_evaluator_predicted(self) -> None:
        for row in self.report.case_table():
            for key in EVALUATOR_KEYS:
                self.assertIn(key, row)

    def test_rerunning_produces_identical_metrics(self) -> None:
        again = run_comparison()

        self.assertEqual(again.as_dict(), self.report.as_dict())

    def test_subset_scoring_uses_only_the_given_cases(self) -> None:
        subset = run_comparison(V3_CASES[:20])

        self.assertEqual(len(subset.results), 20)


class ImprovementTests(unittest.TestCase):
    """The claims Phase 7.5 makes, checked against the published numbers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_comparison()

    def test_macro_f1_improves_on_the_full_benchmark(self) -> None:
        self.assertAlmostEqual(
            self.report.metrics[SEMANTIC_V1].macro_f1, V3_MACRO_F1[SEMANTIC_V1], places=4
        )
        self.assertAlmostEqual(
            self.report.metrics[SEMANTIC_V2].macro_f1, V3_MACRO_F1[SEMANTIC_V2], places=4
        )

    def test_false_positive_rate_falls_on_the_full_benchmark(self) -> None:
        self.assertAlmostEqual(
            self.report.metrics[SEMANTIC_V1].false_positive_rate,
            V3_FALSE_POSITIVE_RATE[SEMANTIC_V1],
            places=4,
        )
        self.assertAlmostEqual(
            self.report.metrics[SEMANTIC_V2].false_positive_rate,
            V3_FALSE_POSITIVE_RATE[SEMANTIC_V2],
            places=4,
        )

    def test_the_gain_is_precision_not_recall(self) -> None:
        self.assertGreater(self.report.deltas("micro_precision"), 0.0)
        self.assertAlmostEqual(self.report.deltas("micro_recall"), 0.0, places=4)

    def test_recall_does_not_regress(self) -> None:
        self.assertGreaterEqual(self.report.deltas("micro_recall"), 0.0)

    def test_false_negative_rate_does_not_regress(self) -> None:
        self.assertLessEqual(self.report.deltas("false_negative_rate"), 0.0)

    def test_v2_beats_both_baselines_on_macro_f1(self) -> None:
        scores = {name: self.report.metrics[name].macro_f1 for name in EVALUATOR_KEYS}

        self.assertEqual(max(scores, key=scores.get), SEMANTIC_V2)

    def test_v2_has_the_lowest_false_positive_rate_of_the_two_semantic_models(
        self,
    ) -> None:
        self.assertLess(
            self.report.metrics[SEMANTIC_V2].false_positive_rate,
            self.report.metrics[SEMANTIC_V1].false_positive_rate,
        )

    def test_per_category_scores_are_reported_for_every_evaluator(self) -> None:
        for name in EVALUATOR_KEYS:
            self.assertTrue(self.report.metrics[name].per_category, name)


class DecontaminationSensitivityTests(unittest.TestCase):
    """The improvement must not be an artefact of the 32 reused texts.

    semantic/v3 reuses 32 sentences from the evaluator development benchmark and
    fails its contamination audit. Re-scoring the 88 clean cases is the check
    that the reported gain is real; it also shows what does *not* survive.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_comparison(decontaminated_v3_cases())

    def test_the_clean_subset_is_scored(self) -> None:
        self.assertEqual(len(self.report.results), len(decontaminated_v3_cases()))

    def test_macro_f1_gain_survives_decontamination(self) -> None:
        self.assertAlmostEqual(
            self.report.metrics[SEMANTIC_V1].macro_f1, V4_MACRO_F1[SEMANTIC_V1], places=4
        )
        self.assertAlmostEqual(
            self.report.metrics[SEMANTIC_V2].macro_f1, V4_MACRO_F1[SEMANTIC_V2], places=4
        )

    def test_false_positive_rate_gain_survives_decontamination(self) -> None:
        self.assertAlmostEqual(
            self.report.metrics[SEMANTIC_V1].false_positive_rate,
            V4_FALSE_POSITIVE_RATE[SEMANTIC_V1],
            places=4,
        )
        self.assertAlmostEqual(
            self.report.metrics[SEMANTIC_V2].false_positive_rate,
            V4_FALSE_POSITIVE_RATE[SEMANTIC_V2],
            places=4,
        )

    def test_the_gain_is_larger_on_clean_data_than_on_all_data(self) -> None:
        full = run_comparison()
        clean_gain = self.report.deltas("macro_f1")
        full_gain = full.deltas("macro_f1")

        self.assertGreater(clean_gain, full_gain)
        self.assertAlmostEqual(clean_gain, 0.06, places=4)

    def test_the_false_positive_gain_is_roughly_unchanged(self) -> None:
        full = run_comparison()

        self.assertAlmostEqual(
            self.report.deltas("false_positive_rate"),
            full.deltas("false_positive_rate"),
            places=2,
        )

    def test_the_market_prediction_advantage_does_not_survive(self) -> None:
        """An honest negative: v2's lead over v1 here was contamination-driven.

        On all 120 cases v2 scores 81.8% against v1's 77.3%. On the 88 clean
        cases both score 75.0%, so the apparent advantage came entirely from the
        reused development sentences -- exactly the cases an evaluator designed
        on that material is expected to win.
        """

        full = run_comparison()

        self.assertAlmostEqual(full.market_prediction_accuracy(SEMANTIC_V1), 0.7727, places=4)
        self.assertAlmostEqual(full.market_prediction_accuracy(SEMANTIC_V2), 0.8182, places=4)
        self.assertAlmostEqual(
            self.report.market_prediction_accuracy(SEMANTIC_V1), 0.75, places=4
        )
        self.assertAlmostEqual(
            self.report.market_prediction_accuracy(SEMANTIC_V2), 0.75, places=4
        )

    def test_attribution_accuracy_is_reported_on_both_subsets(self) -> None:
        full = run_comparison()

        self.assertAlmostEqual(full.attribution_accuracy(), 0.9167, places=4)
        self.assertAlmostEqual(self.report.attribution_accuracy(), 0.8864, places=4)


class AttributionErrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_comparison()

    def test_errors_are_listed_with_the_case(self) -> None:
        for item in self.report.attribution_errors():
            self.assertTrue(item.case.case_id)
            self.assertTrue(item.case.text)

    def test_every_error_is_a_label_disagreement(self) -> None:
        for item in self.report.attribution_errors():
            self.assertNotEqual(
                item.v2_analysis.statement_source, item.case.statement_source
            )

    def test_the_error_count_is_stable(self) -> None:
        self.assertEqual(len(self.report.attribution_errors()), 10)

    def test_most_errors_are_author_voice_false_negatives(self) -> None:
        """Eight of ten misread an attributed claim as the author's own.

        All eight are missing source vocabulary, not failing logic. A ninth
        (`An unnamed banker says …`) is the same lexicon problem in the other
        direction, and one (`The broker note says …, which the article does not
        endorse.`) is the rejection rule outranking a named source.
        """

        errors = self.report.attribution_errors()
        missed = [
            item
            for item in errors
            if item.v2_analysis.statement_source == "author"
            and item.case.statement_source != "author"
        ]

        self.assertEqual(len(errors), 10)
        self.assertEqual(len(missed), 8)

    def test_the_non_lexicon_error_is_the_rejection_rule(self) -> None:
        errors = {
            item.case.case_id: item for item in self.report.attribution_errors()
        }

        self.assertEqual(
            errors["bd-03"].v2_analysis.statement_source, "quoted"
        )
        self.assertEqual(errors["bd-03"].case.statement_source, "third_party")
        self.assertEqual(
            errors["ui-18"].v2_analysis.statement_source, "third_party"
        )


if __name__ == "__main__":
    unittest.main()
