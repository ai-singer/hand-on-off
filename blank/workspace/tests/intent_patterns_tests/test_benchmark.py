"""Requirement: the benchmark, the old/new comparison, and the combination."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.intent_patterns.evaluation import (
    BENCHMARK_CASES,
    BENCHMARK_PATH,
    BOUNDARY,
    CATEGORY,
    COMPARISON_PATH,
    NEGATIVE,
    POSITIVE,
    REQUIRED_GROUP_SIZES,
    PatternBenchmarkCase,
    attribution_combination,
    benchmark_payload,
    case_index,
    combination_summary,
    compare_with_old,
    evaluate_patterns,
    group_cases,
    group_sizes,
    run_benchmark,
    write_benchmark,
    write_comparison,
)
from risk_evaluation.intent_patterns.financial_guarantee import PATTERNS
from risk_evaluation.semantic_evaluator import SemanticRiskEvaluator
from risk_evaluation.semantic_evaluator_v2 import SemanticRiskEvaluatorV2


class BenchmarkShapeTests(unittest.TestCase):
    def test_at_least_forty_cases(self) -> None:
        self.assertGreaterEqual(len(BENCHMARK_CASES), 40)

    def test_every_group_meets_its_required_size(self) -> None:
        sizes = group_sizes()

        for group, required in REQUIRED_GROUP_SIZES.items():
            self.assertGreaterEqual(sizes[group], required, group)

    def test_case_ids_are_unique(self) -> None:
        ids = [case.case_id for case in BENCHMARK_CASES]

        self.assertEqual(len(ids), len(set(ids)))

    def test_every_case_records_a_note(self) -> None:
        for case in BENCHMARK_CASES:
            self.assertTrue(case.note.strip(), case.case_id)

    def test_the_positive_group_covers_active_passive_and_nominal(self) -> None:
        """The phase requires these three among the positives."""

        forms = {
            form for case in group_cases(POSITIVE) for form in case.forms
        }

        self.assertTrue({"active", "passive", "nominal"} <= forms)

    def test_the_negative_group_covers_education_discussion_and_negation(
        self,
    ) -> None:
        forms = {
            form for case in group_cases(NEGATIVE) for form in case.forms
        }

        self.assertTrue({"education", "discussion", "negation"} <= forms)

    def test_the_boundary_group_covers_uncertain_quoted_and_hypothetical(
        self,
    ) -> None:
        forms = {
            form for case in group_cases(BOUNDARY) for form in case.forms
        }

        self.assertTrue({"uncertain", "quoted", "hypothetical"} <= forms)

    def test_an_unknown_group_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PatternBenchmarkCase("X-1", "mixed", "text")

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PatternBenchmarkCase("X-1", POSITIVE, "  ")

    def test_group_expectations_are_derived_from_the_group(self) -> None:
        for case in BENCHMARK_CASES:
            self.assertEqual(case.expects_relation, case.group in (POSITIVE, BOUNDARY))
            self.assertEqual(case.expects_category, case.group == POSITIVE)


class BenchmarkArtifactTests(unittest.TestCase):
    def test_the_benchmark_file_exists(self) -> None:
        self.assertTrue(BENCHMARK_PATH.is_file())

    def test_the_file_matches_the_payload(self) -> None:
        on_disk = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))

        self.assertEqual(on_disk["case_count"], len(BENCHMARK_CASES))
        self.assertEqual(len(on_disk["cases"]), len(BENCHMARK_CASES))
        self.assertEqual(on_disk["version"], "v1")
        self.assertEqual(on_disk["category"], CATEGORY)

    def test_the_payload_is_json_serializable(self) -> None:
        json.dumps(benchmark_payload(), sort_keys=True)

    def test_writing_is_reproducible(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "benchmark.json"
            write_benchmark(target)
            first = target.read_text(encoding="utf-8")
            write_benchmark(target)

            self.assertEqual(first, target.read_text(encoding="utf-8"))

    def test_case_index_maps_every_id(self) -> None:
        self.assertEqual(len(case_index()), len(BENCHMARK_CASES))


class PinnedResultTests(unittest.TestCase):
    """The measured result, pinned so it cannot drift unnoticed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.relation, cls.category = run_benchmark()

    def test_the_old_evaluator_recall_is_pinned(self) -> None:
        self.assertEqual(self.relation.old_recall, 0.2353)
        self.assertEqual(self.relation.old_true_positives, 4)

    def test_the_pattern_recall_is_pinned(self) -> None:
        self.assertEqual(self.relation.recall, 0.9412)
        self.assertEqual(self.relation.true_positives, 16)

    def test_the_false_negative_count_falls_from_thirteen_to_one(self) -> None:
        self.assertEqual(self.relation.old_false_negatives, 13)
        self.assertEqual(self.relation.false_negatives, 1)

    def test_the_miss_reduction_is_twelve(self) -> None:
        self.assertEqual(self.relation.miss_reduction, 12)
        self.assertEqual(self.relation.miss_reduction_rate, 0.9231)

    def test_thirteen_cases_were_fixed(self) -> None:
        self.assertEqual(len(self.relation.fixed_cases()), 13)

    def test_no_case_was_broken(self) -> None:
        self.assertEqual(self.relation.broken_cases(), ())

    def test_one_positive_remains_undetected(self) -> None:
        self.assertEqual(
            [item.case_id for item in self.relation.remaining_errors()], ["PG-15"]
        )

    def test_the_old_evaluator_has_one_false_positive_and_the_pattern_none(
        self,
    ) -> None:
        self.assertEqual(self.relation.old_false_positives, 1)
        self.assertEqual(self.relation.false_positives, 0)

    def test_both_scoring_views_agree_on_recall(self) -> None:
        self.assertEqual(self.relation.recall, self.category.recall)
        self.assertEqual(self.relation.old_recall, self.category.old_recall)

    def test_the_boundary_group_adds_no_false_positives(self) -> None:
        """Hedging is built into the matcher, not bolted on."""

        self.assertEqual(self.category.false_positives, self.relation.false_positives)

    def test_rerunning_reproduces_the_result(self) -> None:
        again = evaluate_patterns()

        self.assertEqual(again.as_dict(), self.relation.as_dict())

    def test_the_comparison_is_json_serializable(self) -> None:
        json.dumps(compare_with_old(), sort_keys=True)

    def test_render_states_the_three_measures(self) -> None:
        rendered = self.relation.render()

        for token in ("recall", "false positives", "miss reduction"):
            self.assertIn(token, rendered)


class FormBreakdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.relation, _ = run_benchmark()

    def test_the_miss_by_form_is_reported(self) -> None:
        by_form = self.relation.by_form()

        self.assertIn("copular", by_form)
        self.assertIn("active", by_form)
        self.assertIn("passive", by_form)
        self.assertIn("nominal", by_form)

    def test_the_old_rule_only_handled_the_attributive_form(self) -> None:
        by_form = self.relation.by_form()

        self.assertEqual(by_form["attributive"]["old"], by_form["attributive"]["cases"])
        self.assertEqual(by_form["copular"]["old"], 0)
        self.assertEqual(by_form["active"]["old"], 0)
        self.assertEqual(by_form["passive"]["old"], 0)

    def test_the_pattern_handles_every_form_but_one(self) -> None:
        by_form = self.relation.by_form()

        self.assertEqual(by_form["copular"]["pattern"], by_form["copular"]["cases"])
        self.assertEqual(by_form["active"]["pattern"], by_form["active"]["cases"])
        self.assertEqual(by_form["passive"]["pattern"], by_form["passive"]["cases"])
        self.assertEqual(by_form["nominal"]["pattern"], by_form["nominal"]["cases"] - 1)


class OldEvaluatorTests(unittest.TestCase):
    """Which evaluator is "old", and why they agree."""

    def test_both_existing_evaluators_miss_the_same_forms(self) -> None:
        """They share a signal layer, so the blind spot is not v2-specific."""

        for text in (
            "This return is guaranteed.",
            "Returns are guaranteed.",
            "We guarantee this return.",
        ):
            for evaluator in (SemanticRiskEvaluator(), SemanticRiskEvaluatorV2()):
                fired = any(
                    item.category == CATEGORY for item in evaluator.evaluate_text(text)
                )
                self.assertFalse(fired, f"{text!r} / {type(evaluator).__name__}")

    def test_both_existing_evaluators_catch_the_prenominal_form(self) -> None:
        for evaluator in (SemanticRiskEvaluator(), SemanticRiskEvaluatorV2()):
            fired = any(
                item.category == CATEGORY
                for item in evaluator.evaluate_text("This is a guaranteed return.")
            )
            self.assertTrue(fired, type(evaluator).__name__)

    def test_the_two_evaluators_agree_across_the_benchmark(self) -> None:
        relation, _ = run_benchmark()

        for item in relation.outcomes:
            old_v2 = CATEGORY in item.old_categories
            old_v1 = CATEGORY in item.old_v1_categories
            self.assertEqual(old_v2, old_v1, item.case_id)


class CombinationTests(unittest.TestCase):
    """Requirement 6: pattern layer plus attribution layer."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.outcomes = attribution_combination()
        cls.summary = combination_summary(cls.outcomes)

    def test_the_combination_scores_the_phase_8_3_cases(self) -> None:
        self.assertEqual(self.summary["cases"], 60)

    def test_the_baseline_misses_nine(self) -> None:
        self.assertEqual(self.summary["baseline_misses"], 9)

    def test_attribution_alone_reduces_the_misses_to_two(self) -> None:
        self.assertEqual(self.summary["attribution_misses"], 2)

    def test_adding_the_pattern_layer_removes_the_last_two_misses(self) -> None:
        self.assertEqual(self.summary["combination_misses"], 0)
        self.assertEqual(self.summary["combination_correct"], 55)

    def test_the_pattern_layer_changes_exactly_the_blind_spot_cases(self) -> None:
        self.assertEqual(
            sorted(self.summary["changed_by_pattern"]), ["A-02", "D-06"]
        )

    def test_both_changed_cases_are_the_predicative_guarantee(self) -> None:
        for item in self.outcomes:
            if item.case_id in ("A-02", "D-06"):
                self.assertIn("is guaranteed", item.text, item.case_id)
                self.assertEqual(
                    item.attribution_plus_pattern, ("financial_guarantee",), item.case_id
                )

    def test_the_combination_breaks_nothing(self) -> None:
        broken = [
            item.case_id
            for item in self.outcomes
            if item.attribution_correct and not item.combination_correct
        ]

        self.assertEqual(broken, [])

    def test_the_combination_never_removes_an_attribution_finding(self) -> None:
        """The pattern layer is additive; it must not suppress anything."""

        for item in self.outcomes:
            self.assertTrue(
                set(item.attribution_only) <= set(item.attribution_plus_pattern),
                item.case_id,
            )

    def test_a_rejection_is_still_not_the_articles_risk(self) -> None:
        """The case that broke when the policy was bypassed."""

        by_id = {item.case_id: item for item in self.outcomes}

        for case_id in ("C-01", "C-03"):
            self.assertEqual(by_id[case_id].attribution_plus_pattern, (), case_id)
            self.assertEqual(by_id[case_id].baseline, ("financial_guarantee",), case_id)

    def test_the_summary_is_json_serializable(self) -> None:
        json.dumps(self.summary, sort_keys=True)

    def test_outcomes_are_json_serializable(self) -> None:
        json.dumps([item.as_dict() for item in self.outcomes], sort_keys=True)


class ComparisonArtifactTests(unittest.TestCase):
    def test_the_comparison_file_exists(self) -> None:
        self.assertTrue(COMPARISON_PATH.is_file())

    def test_the_file_records_both_views(self) -> None:
        payload = json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))

        self.assertIn("relation_view", payload)
        self.assertIn("category_view", payload)
        self.assertIn("combination", payload)

    def test_the_file_matches_a_fresh_run(self) -> None:
        payload = json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))
        fresh = compare_with_old()

        self.assertEqual(payload["relation_view"]["recall"], fresh["relation_view"]["recall"])
        self.assertEqual(
            payload["relation_view"]["miss_reduction"],
            fresh["relation_view"]["miss_reduction"],
        )

    def test_the_file_says_how_boundary_is_scored(self) -> None:
        payload = json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))

        self.assertIn("Boundary cases contain the relation", payload["note"])

    def test_writing_the_comparison_is_reproducible(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "comparison.json"
            write_comparison(target)
            first = target.read_text(encoding="utf-8")
            write_comparison(target)

            self.assertEqual(first, target.read_text(encoding="utf-8"))


class RegressionProtectionTests(unittest.TestCase):
    """Requirement: nothing existing is affected."""

    def test_the_pattern_layer_does_not_modify_the_evaluators(self) -> None:
        pinned = {
            "This is a guaranteed return.": True,
            "This return is guaranteed.": False,
            "Returns are guaranteed.": False,
            "We guarantee this return.": False,
        }
        for text, expected in pinned.items():
            fired = any(
                item.category == CATEGORY
                for item in SemanticRiskEvaluatorV2().evaluate_text(text)
            )
            self.assertEqual(fired, expected, text)

    def test_running_the_benchmark_does_not_move_the_evaluators(self) -> None:
        text = "This return is guaranteed."
        before = tuple(
            sorted({i.category for i in SemanticRiskEvaluatorV2().evaluate_text(text)})
        )
        run_benchmark()
        attribution_combination()
        after = tuple(
            sorted({i.category for i in SemanticRiskEvaluatorV2().evaluate_text(text)})
        )

        self.assertEqual(before, after)

    def test_the_pattern_set_categories_the_registry_knows(self) -> None:
        from risk_evaluation.taxonomy import category as taxonomy_category

        for name in PATTERNS.categories:
            self.assertEqual(taxonomy_category(name).name, name)


if __name__ == "__main__":
    unittest.main()
