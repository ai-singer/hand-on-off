from __future__ import annotations

import json
import unittest

from risk_evaluation.model import (
    ACTIONS,
    SEVERITIES,
    RiskEvaluationError,
    RiskEvaluationResult,
    severity_effect,
)
from risk_evaluation.taxonomy import (
    RISK_TAXONOMY,
    RiskCategory,
    categories_for_evaluator_category,
    category,
    category_names,
)


REQUIRED_CATEGORY_NAMES = (
    "investment_advice",
    "market_prediction",
    "financial_guarantee",
    "unverified_information",
)


def _sample(**overrides) -> RiskEvaluationResult:
    payload = {
        "category": "investment_advice",
        "intent": "Induce the reader to act on the market.",
        "confidence": 0.5,
        "evidence_required": ("disclaimer", "evidence", "uncertainty"),
        "severity": "block",
        "action": "block",
        "evaluator": "test",
        "detail": "sample",
        "source_ids": ("source-1",),
        "candidates": ("investment_advice", "financial_guarantee"),
    }
    payload.update(overrides)
    return RiskEvaluationResult(**payload)


class RiskEvaluationResultTests(unittest.TestCase):
    def test_result_round_trips_through_json(self) -> None:
        original = _sample()

        restored = RiskEvaluationResult.from_dict(
            json.loads(json.dumps(original.as_dict()))
        )

        self.assertEqual(restored, original)
        self.assertTrue(restored.ambiguous)

    def test_candidates_default_to_the_primary_category(self) -> None:
        result = _sample(candidates=())

        self.assertEqual(result.candidates, ("investment_advice",))
        self.assertFalse(result.ambiguous)

    def test_invalid_fields_are_rejected(self) -> None:
        with self.assertRaises(RiskEvaluationError):
            _sample(confidence=1.5)
        with self.assertRaises(RiskEvaluationError):
            _sample(severity="critical")
        with self.assertRaises(RiskEvaluationError):
            _sample(action="ignore")
        with self.assertRaises(RiskEvaluationError):
            _sample(category="")

    def test_malformed_payload_is_rejected(self) -> None:
        with self.assertRaises(RiskEvaluationError):
            RiskEvaluationResult.from_dict({"category": "investment_advice"})

    def test_risk_constraint_projection_matches_the_artifact_contract(self) -> None:
        constraint = _sample().to_risk_constraint()

        self.assertEqual(
            set(constraint),
            {"rule_id", "category", "severity", "action", "message", "source_ids"},
        )
        self.assertIn(constraint["severity"], SEVERITIES)
        self.assertIn(constraint["action"], ACTIONS)
        self.assertTrue(constraint["rule_id"])
        self.assertEqual(constraint["source_ids"], ["source-1"])

    def test_severity_effects_are_documented_for_every_severity(self) -> None:
        for severity in SEVERITIES:
            self.assertNotEqual(severity_effect(severity), "unknown severity", severity)
        self.assertIn("review_required", severity_effect("block"))


class RiskTaxonomyTests(unittest.TestCase):
    def test_taxonomy_covers_the_required_categories(self) -> None:
        names = set(category_names())

        self.assertGreaterEqual(len(RISK_TAXONOMY), 4)
        for required in REQUIRED_CATEGORY_NAMES:
            self.assertIn(required, names)

    def test_every_category_declares_the_full_contract(self) -> None:
        for entry in RISK_TAXONOMY:
            self.assertIsInstance(entry, RiskCategory)
            self.assertTrue(entry.definition, entry.name)
            self.assertTrue(entry.intent, entry.name)
            self.assertTrue(entry.evidence_required, entry.name)
            self.assertIn(entry.severity, SEVERITIES, entry.name)
            self.assertIn(entry.action, ACTIONS, entry.name)
            self.assertTrue(entry.evaluator_categories, entry.name)
            self.assertTrue(entry.examples, entry.name)

    def test_unknown_category_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            category("not_a_category")

    def test_severity_and_action_follow_the_designed_policy(self) -> None:
        blocking = {
            name
            for name, entry in ((item.name, item) for item in RISK_TAXONOMY)
            if entry.severity == "block"
        }

        self.assertEqual(blocking, {"investment_advice", "financial_guarantee"})
        for name in blocking:
            self.assertEqual(category(name).action, "block")

    def test_evaluator_categories_are_recorded_per_category(self) -> None:
        # The current keyword evaluator folds guarantee wording into
        # investment_advice, so that evaluator category is ambiguous by design.
        self.assertEqual(
            categories_for_evaluator_category("investment_advice"),
            ("investment_advice", "financial_guarantee"),
        )
        for evaluator_category in (
            "market_prediction",
            "unverified_fact",
            "emotional_language",
        ):
            self.assertEqual(
                len(categories_for_evaluator_category(evaluator_category)),
                1,
                evaluator_category,
            )


if __name__ == "__main__":
    unittest.main()
