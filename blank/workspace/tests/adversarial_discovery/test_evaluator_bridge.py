from __future__ import annotations

import json
import unittest

from risk_evaluation.adversarial.case import AdversarialCase
from risk_evaluation.adversarial.evaluator_bridge import (
    DEFAULT_EVALUATOR,
    DetectionResult,
    evaluate_case,
    evaluate_cases,
    false_positives,
    misses,
    summarise,
)
from risk_evaluation.adversarial.strategies import AttackStrategy
from risk_evaluation.evaluator import KeywordRiskEvaluator
from risk_evaluation.model import RiskEvaluationResult
from risk_evaluation.semantic_evaluator import SemanticRiskEvaluator
from risk_evaluation.semantic_evaluator_v2 import SemanticRiskEvaluatorV2


def _case(
    text: str,
    target: str,
    *,
    expected: bool = True,
    case_id: str = "ADV-DIR-01",
    strategy: AttackStrategy = AttackStrategy.DIRECT_STATEMENT,
) -> AdversarialCase:
    return AdversarialCase(
        case_id=case_id,
        text=text,
        target_category=target,
        attack_strategy=strategy,
        expected_detection=expected,
        metadata={"rationale": "synthetic", "expectation_basis": "test"},
    )


class BridgeCallTests(unittest.TestCase):
    """Requirement 4: the bridge calls the existing evaluator correctly."""

    def test_the_default_evaluator_is_semantic_intent_v2(self) -> None:
        self.assertEqual(DEFAULT_EVALUATOR, "semantic-intent-v2")
        self.assertEqual(evaluate_case(_case("X", "market_prediction")).evaluator, DEFAULT_EVALUATOR)

    def test_a_detected_target_is_reported_as_the_detected_category(self) -> None:
        result = evaluate_case(
            _case("This fund cannot lose money.", "financial_guarantee")
        )

        self.assertEqual(result.detected_category, "financial_guarantee")
        self.assertTrue(result.detected)
        self.assertTrue(result.hit)

    def test_an_undetected_target_reports_no_detected_category(self) -> None:
        result = evaluate_case(_case("This return is guaranteed.", "financial_guarantee"))

        self.assertIsNone(result.detected_category)
        self.assertFalse(result.detected)

    def test_other_detected_categories_do_not_count_as_the_target(self) -> None:
        """Detecting *something* is not detecting the expected category."""

        result = evaluate_case(
            _case("Sources say the market will certainly crash.", "market_prediction")
        )

        self.assertIn("unverified_information", result.detected_categories)
        self.assertIsNone(result.detected_category)
        self.assertTrue(result.miss)

    def test_every_detected_category_is_reported(self) -> None:
        result = evaluate_case(
            _case("The stock will definitely rise, do not miss out.", "emotional_manipulation")
        )

        self.assertEqual(
            set(result.detected_categories),
            {"market_prediction", "emotional_manipulation"},
        )
        self.assertEqual(result.detected_category, "emotional_manipulation")

    def test_evidence_carries_the_v2_dimensions(self) -> None:
        result = evaluate_case(
            _case("Sources say the market will certainly crash.", "unverified_information")
        )

        self.assertEqual(result.evidence["statement_source"], "unknown")
        self.assertEqual(result.evidence["certainty_level"], "certain")
        self.assertEqual(
            result.evidence["market_claim_case"], "attribution_expectation"
        )

    def test_evidence_carries_the_case_for_traceability(self) -> None:
        case = _case("This return is guaranteed.", "financial_guarantee")
        result = evaluate_case(case)

        self.assertEqual(result.evidence["text"], case.text)
        self.assertEqual(result.evidence["attack_strategy"], "direct_statement")
        self.assertIn("severity", result.evidence)

    def test_results_are_returned_in_case_order(self) -> None:
        cases = [
            _case("Buy this stock.", "investment_advice", case_id="ADV-DIR-01"),
            _case("This return is guaranteed.", "financial_guarantee", case_id="ADV-DIR-02"),
        ]
        results = evaluate_cases(cases)

        self.assertEqual(
            [item.case_id for item in results], ["ADV-DIR-01", "ADV-DIR-02"]
        )

    def test_the_evaluator_is_not_mutated_between_cases(self) -> None:
        evaluator = SemanticRiskEvaluatorV2()
        evaluate_cases([_case("Buy this stock.", "investment_advice")], evaluator)
        after = evaluator.analyze("Buy this stock.")

        self.assertIn("investment_advice", after.categories)

    def test_an_evaluator_without_analyze_still_works(self) -> None:
        """v1 and the keyword evaluator expose `evaluate_text` only."""

        result = evaluate_case(
            _case("Buy this stock now.", "investment_advice"),
            SemanticRiskEvaluator(),
        )

        self.assertEqual(result.evaluator, "semantic-intent-v0")
        self.assertIsInstance(result.detected_categories, tuple)

    def test_the_keyword_evaluator_can_be_used_as_the_target(self) -> None:
        result = evaluate_case(
            _case("Buy this stock now.", "investment_advice"), KeywordRiskEvaluator()
        )

        self.assertTrue(result.evaluator.startswith("keyword"))

    def test_bridge_results_are_json_serializable(self) -> None:
        json.dumps(evaluate_case(_case("Buy this stock.", "investment_advice")).as_dict())

    def test_render_states_the_outcome(self) -> None:
        rendered = evaluate_case(_case("Buy this stock.", "investment_advice")).render()

        self.assertIn("ADV-DIR-01", rendered)
        self.assertIn("investment_advice", rendered)


class DetectionResultSemanticsTests(unittest.TestCase):
    def test_hit_means_agreement_in_either_direction(self) -> None:
        flagged = evaluate_case(_case("Buy this stock.", "investment_advice"))
        quiet = evaluate_case(
            _case("The quarter ended in March.", "market_prediction", expected=False)
        )

        self.assertTrue(flagged.hit)
        self.assertTrue(quiet.hit)

    def test_miss_is_an_expected_risk_that_was_not_reported(self) -> None:
        result = evaluate_case(_case("This return is guaranteed.", "financial_guarantee"))

        self.assertTrue(result.miss)
        self.assertFalse(result.false_positive)
        self.assertEqual(result.status, "miss")

    def test_false_positive_is_a_control_that_was_reported(self) -> None:
        result = evaluate_case(
            _case("Buy this stock.", "investment_advice", expected=False)
        )

        self.assertTrue(result.false_positive)
        self.assertFalse(result.miss)
        self.assertEqual(result.status, "false_positive")

    def test_a_miss_requires_the_expectation_to_be_positive(self) -> None:
        result = evaluate_case(
            _case("The quarter ended in March.", "market_prediction", expected=False)
        )

        self.assertFalse(result.miss)

    def test_status_is_one_of_three_values(self) -> None:
        for expected in (True, False):
            result = evaluate_case(
                _case("Buy this stock.", "investment_advice", expected=expected)
            )
            self.assertIn(result.status, ("hit", "miss", "false_positive"))

    def test_helpers_partition_the_results(self) -> None:
        results = (
            evaluate_case(_case("This return is guaranteed.", "financial_guarantee")),
            evaluate_case(_case("Buy this stock.", "investment_advice")),
            evaluate_case(
                _case("Buy this stock.", "investment_advice", expected=False, case_id="ADV-CTL-01")
            ),
        )

        self.assertEqual(len(misses(results)), 1)
        self.assertEqual(len(false_positives(results)), 1)

    def test_summarise_counts_each_status(self) -> None:
        results = evaluate_cases(
            [
                _case("This return is guaranteed.", "financial_guarantee"),
                _case("Buy this stock.", "investment_advice", case_id="ADV-DIR-02"),
            ]
        )
        summary = summarise(results)

        self.assertEqual(summary["cases"], 2)
        self.assertEqual(summary["misses"], 1)
        self.assertEqual(summary["hits"], 1)
        self.assertEqual(summary["attacks"], 2)

    def test_summarise_breaks_down_by_strategy(self) -> None:
        summary = summarise(
            evaluate_cases([_case("Buy this stock.", "investment_advice")])
        )

        self.assertIn("direct_statement", summary["by_strategy"])

    def test_summarise_counts_debatable_misses(self) -> None:
        case = AdversarialCase(
            case_id="ADV-IMP-01",
            text="This return is guaranteed.",
            target_category="financial_guarantee",
            attack_strategy=AttackStrategy.IMPLICIT_RECOMMENDATION,
            expected_detection=True,
            metadata={"expectation_strength": "debatable", "rationale": "t"},
        )
        summary = summarise(evaluate_cases([case]))

        self.assertEqual(summary["misses_debatable_expectation"], 1)

    def test_summarise_is_json_serializable(self) -> None:
        json.dumps(summarise(evaluate_cases([_case("Buy this stock.", "investment_advice")])))

    def test_results_expose_result_objects_to_the_caller(self) -> None:
        """The bridge returns its own type; the evaluator's contract is unchanged."""

        raw = SemanticRiskEvaluatorV2().evaluate_text("Buy this stock.")
        self.assertTrue(all(isinstance(item, RiskEvaluationResult) for item in raw))


if __name__ == "__main__":
    unittest.main()
