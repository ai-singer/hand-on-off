from __future__ import annotations

import copy
import json
import unittest

from core import RawSource, SourceType, load_plugin
from distillation_core import DistillationEngine
from risk_evaluation.evaluator import KeywordRiskEvaluator, RiskIntentEvaluator
from risk_evaluation.model import RiskEvaluationError, RiskEvaluationResult
from risk_evaluation.taxonomy import category_names


ADVICE_TEXT = "This is a guaranteed buy at the current price."
BENIGN_TEXT = "The income statement shows how revenue converts into margin."


class _StubSemanticEvaluator:
    """Test double proving the interface accepts a different implementation.

    It performs no analysis: the point is that the protocol, not the keyword
    implementation, is the contract.
    """

    name = "stub-semantic-v0"

    def evaluate_text(self, text, *, source_ids=()):
        if "buy" not in text.lower():
            return ()
        return (
            RiskEvaluationResult(
                category="investment_advice",
                intent="stub",
                confidence=0.9,
                evidence_required=("disclaimer",),
                severity="block",
                action="block",
                evaluator=self.name,
                source_ids=tuple(source_ids),
            ),
        )

    def evaluate_artifact(self, artifact):
        return ()


class IntentLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = KeywordRiskEvaluator()

    def test_keyword_evaluator_satisfies_the_protocol(self) -> None:
        self.assertIsInstance(self.evaluator, RiskIntentEvaluator)

    def test_a_different_evaluator_can_replace_it(self) -> None:
        replacement = _StubSemanticEvaluator()

        self.assertIsInstance(replacement, RiskIntentEvaluator)
        self.assertNotEqual(replacement.name, self.evaluator.name)
        self.assertEqual(len(replacement.evaluate_text(ADVICE_TEXT)), 1)

    def test_evaluate_text_detects_an_enumerated_risk(self) -> None:
        results = self.evaluator.evaluate_text(ADVICE_TEXT, source_ids=("s-1",))

        self.assertTrue(results)
        result = results[0]
        self.assertIn("investment_advice", result.candidates)
        self.assertEqual(result.severity, "block")
        self.assertEqual(result.action, "block")
        self.assertEqual(result.source_ids, ("s-1",))
        self.assertEqual(result.evaluator, self.evaluator.name)
        self.assertTrue(result.evidence_required)

    def test_ambiguity_is_reported_rather_than_resolved_silently(self) -> None:
        results = self.evaluator.evaluate_text(ADVICE_TEXT)
        result = results[0]

        self.assertTrue(result.ambiguous)
        self.assertIn("cannot separate", result.detail)
        self.assertEqual(result.confidence, 0.5)

    def test_benign_text_produces_no_result(self) -> None:
        self.assertEqual(self.evaluator.evaluate_text(BENIGN_TEXT), ())

    def test_empty_text_is_rejected(self) -> None:
        with self.assertRaises(RiskEvaluationError):
            self.evaluator.evaluate_text("   ")

    def test_evaluate_artifact_reads_existing_constraints(self) -> None:
        plugin = load_plugin("plugins.xiaolin_finance")
        artifact = DistillationEngine(plugin).distill(
            [RawSource(source_id="a-1", source_type=SourceType.DOCUMENT, content=ADVICE_TEXT)]
        )

        results = self.evaluator.evaluate_artifact(artifact)

        self.assertEqual(len(results), len(artifact["risk_constraints"]))
        self.assertEqual(self.evaluator.evaluate_artifact({"risk_constraints": []}), ())

    def test_artifacts_without_the_category_field_still_resolve(self) -> None:
        """Phase 6.2 added risk_constraints[].category; older artifacts lack it."""

        plugin = load_plugin("plugins.xiaolin_finance")
        artifact = DistillationEngine(plugin).distill(
            [RawSource(source_id="a-2", source_type=SourceType.DOCUMENT, content=ADVICE_TEXT)]
        )
        legacy = copy.deepcopy(artifact)
        for item in legacy["risk_constraints"]:
            item.pop("category", None)

        results = self.evaluator.evaluate_artifact(legacy)

        self.assertTrue(results)
        self.assertIn("investment_advice", results[0].candidates)

    def test_unknown_rule_id_is_rejected(self) -> None:
        with self.assertRaises(RiskEvaluationError):
            self.evaluator.evaluate_artifact(
                {"risk_constraints": [{"rule_id": "finance.unknown", "severity": "block"}]}
            )

    def test_results_serialize_as_a_collection(self) -> None:
        results = self.evaluator.evaluate_text(ADVICE_TEXT)

        payload = json.dumps([item.as_dict() for item in results])
        restored = [
            RiskEvaluationResult.from_dict(item) for item in json.loads(payload)
        ]

        self.assertEqual(restored, list(results))

    def test_every_produced_category_is_a_taxonomy_category(self) -> None:
        for text in (ADVICE_TEXT, "A rumor says the company will be acquired."):
            for result in self.evaluator.evaluate_text(text):
                self.assertIn(result.category, category_names())
                for candidate in result.candidates:
                    self.assertIn(candidate, category_names())


if __name__ == "__main__":
    unittest.main()
