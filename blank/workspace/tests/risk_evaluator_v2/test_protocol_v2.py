from __future__ import annotations

import json
import unittest

from risk_evaluation.evaluator import KeywordRiskEvaluator, RiskIntentEvaluator
from risk_evaluation.model import RiskEvaluationResult
from risk_evaluation.semantic_evaluator import SemanticRiskEvaluator
from risk_evaluation.semantic_evaluator_v2 import (
    EVALUATOR_NAME,
    SemanticRiskEvaluatorV2,
)


class ProtocolCompatibilityTests(unittest.TestCase):
    """v2 must be drop-in usable wherever a RiskIntentEvaluator is expected."""

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluatorV2()

    def test_name_is_the_v2_identifier(self) -> None:
        self.assertEqual(EVALUATOR_NAME, "semantic-intent-v2")
        self.assertEqual(self.evaluator.name, "semantic-intent-v2")

    def test_name_differs_from_both_earlier_evaluators(self) -> None:
        names = {
            self.evaluator.name,
            SemanticRiskEvaluator.name,
            KeywordRiskEvaluator.name,
        }

        self.assertEqual(len(names), 3)

    def test_satisfies_the_runtime_checkable_protocol(self) -> None:
        self.assertIsInstance(self.evaluator, RiskIntentEvaluator)

    def test_evaluate_text_returns_result_objects(self) -> None:
        results = self.evaluator.evaluate_text("The share price will definitely double.")

        self.assertTrue(results)
        for item in results:
            self.assertIsInstance(item, RiskEvaluationResult)

    def test_evaluate_text_returns_a_tuple(self) -> None:
        self.assertIsInstance(self.evaluator.evaluate_text("The stock will rise."), tuple)

    def test_source_ids_are_propagated_to_every_result(self) -> None:
        results = self.evaluator.evaluate_text(
            "The share price will definitely double.", source_ids=("src-1", "src-2")
        )

        self.assertTrue(results)
        for item in results:
            self.assertEqual(item.source_ids, ("src-1", "src-2"))

    def test_omitting_source_ids_leaves_them_empty(self) -> None:
        results = self.evaluator.evaluate_text("The share price will definitely double.")

        for item in results:
            self.assertEqual(item.source_ids, ())

    def test_source_ids_do_not_change_the_categories(self) -> None:
        text = "The share price will definitely double."

        self.assertEqual(
            [r.category for r in self.evaluator.evaluate_text(text)],
            [r.category for r in self.evaluator.evaluate_text(text, source_ids=("s",))],
        )

    def test_results_are_json_serializable(self) -> None:
        results = self.evaluator.evaluate_text("The share price will definitely double.")

        json.dumps([item.as_dict() for item in results], sort_keys=True)

    def test_results_name_the_evaluator_that_produced_them(self) -> None:
        results = self.evaluator.evaluate_text("The share price will definitely double.")

        for item in results:
            self.assertEqual(item.evaluator, "semantic-intent-v2")

    def test_empty_text_is_rejected(self) -> None:
        from risk_evaluation.model import RiskEvaluationError

        with self.assertRaises(RiskEvaluationError):
            self.evaluator.evaluate_text("")

    def test_whitespace_only_text_is_rejected(self) -> None:
        from risk_evaluation.model import RiskEvaluationError

        with self.assertRaises(RiskEvaluationError):
            self.evaluator.evaluate_text("   \n  ")

    def test_non_string_text_is_rejected(self) -> None:
        from risk_evaluation.model import RiskEvaluationError

        with self.assertRaises(RiskEvaluationError):
            self.evaluator.evaluate_text(42)

    def test_a_safe_sentence_yields_no_results(self) -> None:
        self.assertEqual(self.evaluator.evaluate_text("The quarter ended in March."), ())


class ArtifactTests(unittest.TestCase):
    """`evaluate_artifact` reads the same unified artifact shape as v1."""

    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluatorV2()

    def test_artifact_with_a_risky_statement_is_flagged(self) -> None:
        artifact = {
            "knowledge_unit": [
                {"statement": "The share price will definitely double next year."}
            ]
        }
        results = self.evaluator.evaluate_artifact(artifact)

        self.assertIn("market_prediction", {r.category for r in results})

    def test_artifact_with_no_units_yields_no_results(self) -> None:
        self.assertEqual(self.evaluator.evaluate_artifact({}), ())

    def test_topic_candidate_labels_are_also_read(self) -> None:
        artifact = {"topic_candidate": [{"label": "Do not miss this opportunity."}]}
        results = self.evaluator.evaluate_artifact(artifact)

        self.assertIn("emotional_manipulation", {r.category for r in results})

    def test_non_mapping_artifact_is_rejected(self) -> None:
        from risk_evaluation.model import RiskEvaluationError

        with self.assertRaises(RiskEvaluationError):
            self.evaluator.evaluate_artifact(["not", "a", "mapping"])

    def test_a_safe_artifact_yields_no_results(self) -> None:
        artifact = {"knowledge_unit": [{"statement": "The quarter ended in March."}]}

        self.assertEqual(self.evaluator.evaluate_artifact(artifact), ())

    def test_artifact_and_text_paths_agree(self) -> None:
        statement = "The share price will definitely double next year."
        artifact = {"knowledge_unit": [{"statement": statement}]}

        self.assertEqual(
            [r.category for r in self.evaluator.evaluate_artifact(artifact)],
            [r.category for r in self.evaluator.evaluate_text(statement)],
        )


class AnalysisContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analysis = SemanticRiskEvaluatorV2().analyze(
            "Sources say the market will certainly crash."
        )

    def test_analysis_reports_both_dimensions(self) -> None:
        self.assertEqual(self.analysis.statement_source, "unknown")
        self.assertEqual(self.analysis.certainty_level, "certain")

    def test_analysis_reports_the_market_claim_case(self) -> None:
        self.assertEqual(self.analysis.market_claim_case, "attribution_expectation")

    def test_analysis_is_json_serializable(self) -> None:
        json.dumps(self.analysis.as_dict(), sort_keys=True)

    def test_analysis_detail_explains_the_decision(self) -> None:
        self.assertIn("statement_source=unknown", self.analysis.detail)
        self.assertIn("market_claim_case=attribution_expectation", self.analysis.detail)

    def test_categories_agree_with_the_result_objects(self) -> None:
        self.assertEqual(
            list(self.analysis.categories),
            [item.category for item in self.analysis.results],
        )

    def test_every_result_category_is_either_kept_or_suppressed(self) -> None:
        """Nothing may be matched and then silently dropped."""

        for item in self.analysis.results:
            self.assertIn(item.category, self.analysis.categories)
        for name in self.analysis.suppressed:
            self.assertNotIn(name, self.analysis.categories)


if __name__ == "__main__":
    unittest.main()
