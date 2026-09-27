"""The experimental evaluator, its result contract, and the claim-level path."""

from __future__ import annotations

import json
import unittest

from risk_evaluation.attribution_experiment.decision import AUTHORIAL, STRICT
from risk_evaluation.attribution_experiment.evaluator import (
    AUTHORIAL_EVALUATOR,
    DEFAULT_EVALUATOR,
    EXPERIMENT_NAME,
    EXPERIMENT_VERSION,
    AttributionAwareEvaluator,
    AttributionAwareResult,
    attribution_aware,
    categories_of,
    compare_policies,
)
from risk_evaluation.model import RiskEvaluationError
from risk_evaluation.semantic_evaluator_v2 import SemanticRiskEvaluatorV2


MIXED = "Economists forecast slower growth in Europe. This fund cannot lose money."
CITATION = "The company said the fund cannot lose money."


class ResultContractTests(unittest.TestCase):
    """`claims`, `claim_results`, `final_decision`, `evidence` - as specified."""

    def setUp(self) -> None:
        self.result = DEFAULT_EVALUATOR.evaluate(MIXED)

    def test_the_result_is_the_declared_type(self) -> None:
        self.assertIsInstance(self.result, AttributionAwareResult)

    def test_claims_are_exposed(self) -> None:
        self.assertEqual(len(self.result.claims), 2)

    def test_claim_results_are_per_claim(self) -> None:
        self.assertEqual(
            set(self.result.claim_results),
            {claim.claim_id for claim in self.result.claims},
        )

    def test_claim_results_are_evaluator_result_objects(self) -> None:
        from risk_evaluation.model import RiskEvaluationResult

        for results in self.result.claim_results.values():
            for item in results:
                self.assertIsInstance(item, RiskEvaluationResult)

    def test_final_decision_is_the_merged_output(self) -> None:
        self.assertEqual(self.result.categories, ("financial_guarantee",))

    def test_evidence_is_recorded(self) -> None:
        for key in (
            "evaluator",
            "version",
            "baseline_evaluator",
            "policy",
            "claims",
            "baseline_categories",
            "dropped_categories",
        ):
            self.assertIn(key, self.result.evidence)

    def test_the_baseline_is_carried_alongside(self) -> None:
        self.assertEqual(self.result.baseline_categories, ())
        self.assertTrue(self.result.changed)

    def test_claim_decisions_explain_every_claim(self) -> None:
        self.assertEqual(len(self.result.claim_decisions), 2)
        for decision in self.result.claim_decisions:
            self.assertTrue(decision.rules or not decision.detected)

    def test_a_decision_can_be_looked_up(self) -> None:
        self.assertEqual(
            self.result.decision_for("claim-002").claim_id, "claim-002"
        )

    def test_looking_up_a_missing_decision_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.result.decision_for("claim-999")

    def test_as_dict_is_json_serializable(self) -> None:
        json.dumps(self.result.as_dict(), sort_keys=True)

    def test_render_shows_both_verdicts(self) -> None:
        rendered = self.result.render()

        self.assertIn("baseline", rendered)
        self.assertIn("experiment", rendered)


class EvaluatorBehaviourTests(unittest.TestCase):
    def test_the_evaluator_names_itself_and_the_baseline(self) -> None:
        evaluator = AttributionAwareEvaluator()

        self.assertEqual(evaluator.name, EXPERIMENT_NAME)
        self.assertEqual(evaluator.version, EXPERIMENT_VERSION)
        self.assertEqual(evaluator.baseline_evaluator, "semantic-intent-v2")

    def test_the_default_policy_is_the_literal_reading(self) -> None:
        self.assertEqual(DEFAULT_EVALUATOR.policy, STRICT)

    def test_evaluate_text_is_an_alias(self) -> None:
        evaluator = AttributionAwareEvaluator()

        self.assertEqual(
            evaluator.evaluate_text(MIXED).categories, evaluator.evaluate(MIXED).categories
        )

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaises(RiskEvaluationError):
            DEFAULT_EVALUATOR.evaluate("   ")

    def test_non_string_text_is_rejected(self) -> None:
        with self.assertRaises(RiskEvaluationError):
            DEFAULT_EVALUATOR.evaluate(7)  # type: ignore[arg-type]

    def test_a_citation_is_suppressed(self) -> None:
        result = DEFAULT_EVALUATOR.evaluate(CITATION)

        self.assertEqual(result.baseline_categories, ("financial_guarantee",))
        self.assertEqual(result.categories, ())
        self.assertTrue(result.changed)

    def test_an_authorial_claim_is_kept(self) -> None:
        result = DEFAULT_EVALUATOR.evaluate("We believe this fund cannot lose money.")

        self.assertEqual(result.categories, ("financial_guarantee",))
        self.assertEqual(
            result.categories, result.baseline_categories
        )

    def test_a_neutral_text_is_flagged_by_neither(self) -> None:
        result = DEFAULT_EVALUATOR.evaluate("The company reports its results in March.")

        self.assertEqual(result.categories, ())
        self.assertEqual(result.baseline_categories, ())
        self.assertFalse(result.changed)

    def test_the_unmodified_evaluator_is_used_per_claim(self) -> None:
        """The claim results are exactly what the baseline returns for that text."""

        result = DEFAULT_EVALUATOR.evaluate(MIXED)
        for claim in result.claims:
            self.assertEqual(
                result.claim_results[claim.claim_id],
                SemanticRiskEvaluatorV2().evaluate_text(claim.text),
            )

    def test_an_injected_baseline_is_used(self) -> None:
        seen: list[str] = []

        class Recorder(SemanticRiskEvaluatorV2):
            def evaluate_text(self, text, *, source_ids=()):  # type: ignore[override]
                seen.append(text)
                return SemanticRiskEvaluatorV2().evaluate_text(text)

        evaluator = AttributionAwareEvaluator(baseline=Recorder())
        evaluator.evaluate(MIXED)

        self.assertIn(MIXED, seen)
        self.assertGreaterEqual(len(seen), 3)

    def test_evaluation_is_deterministic(self) -> None:
        self.assertEqual(
            DEFAULT_EVALUATOR.evaluate(MIXED).as_dict(),
            DEFAULT_EVALUATOR.evaluate(MIXED).as_dict(),
        )

    def test_the_module_level_helper_matches_the_default_instance(self) -> None:
        self.assertEqual(
            attribution_aware(MIXED).categories, DEFAULT_EVALUATOR.evaluate(MIXED).categories
        )


class PolicyTests(unittest.TestCase):
    def test_both_policies_are_available(self) -> None:
        seen = compare_policies(CITATION)

        self.assertEqual(set(seen), {STRICT, AUTHORIAL})

    def test_the_authorial_policy_suppresses_more(self) -> None:
        strict = DEFAULT_EVALUATOR.evaluate("A broker told clients the fund cannot lose money.")
        authorial = AUTHORIAL_EVALUATOR.evaluate(
            "A broker told clients the fund cannot lose money."
        )

        self.assertEqual(strict.categories, ("financial_guarantee",))
        self.assertEqual(authorial.categories, ())

    def test_the_policies_agree_on_a_plain_authorial_claim(self) -> None:
        text = "This fund cannot lose money."

        self.assertEqual(
            DEFAULT_EVALUATOR.evaluate(text).categories,
            AUTHORIAL_EVALUATOR.evaluate(text).categories,
        )

    def test_an_unknown_policy_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AttributionAwareEvaluator(policy="wishful")

    def test_the_policy_is_recorded_on_the_result(self) -> None:
        self.assertEqual(AUTHORIAL_EVALUATOR.evaluate(CITATION).policy, AUTHORIAL)


class CategoryHelperTests(unittest.TestCase):
    def test_categories_of_sorts_and_de_duplicates(self) -> None:
        from risk_evaluation.semantic_evaluator_v2 import SemanticRiskEvaluatorV2

        results = SemanticRiskEvaluatorV2().evaluate_text(
            "The stock will definitely rise, do not miss out."
        )

        self.assertEqual(
            categories_of(results), ("emotional_manipulation", "market_prediction")
        )

    def test_categories_of_an_empty_sequence(self) -> None:
        self.assertEqual(categories_of(()), ())


if __name__ == "__main__":
    unittest.main()
