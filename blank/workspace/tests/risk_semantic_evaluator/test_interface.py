from __future__ import annotations

import unittest
from pathlib import Path

from core import RawSource, SourceType, load_plugin
from distillation_core import DistillationEngine
from risk_evaluation.evaluator import KeywordRiskEvaluator, RiskIntentEvaluator
from risk_evaluation.model import RiskEvaluationError
from risk_evaluation.semantic_evaluator import SemanticRiskEvaluator


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class _AlternativeEvaluator:
    """Third implementation, proving the protocol is the contract."""

    name = "alternative-v0"

    def evaluate_text(self, text, *, source_ids=()):
        return ()

    def evaluate_artifact(self, artifact):
        return ()


class ProtocolCompatibilityTests(unittest.TestCase):
    def test_semantic_evaluator_satisfies_the_protocol(self) -> None:
        self.assertIsInstance(SemanticRiskEvaluator(), RiskIntentEvaluator)

    def test_both_evaluators_are_interchangeable(self) -> None:
        evaluators = (
            KeywordRiskEvaluator(),
            SemanticRiskEvaluator(),
            _AlternativeEvaluator(),
        )

        for evaluator in evaluators:
            self.assertIsInstance(evaluator, RiskIntentEvaluator)
            self.assertTrue(evaluator.name)
        self.assertEqual(len({item.name for item in evaluators}), 3)

    def test_evaluator_does_not_read_the_plugin_rule_files(self) -> None:
        """The comparison must be between methods, not between configurations."""

        source = (
            WORKSPACE_ROOT / "risk_evaluation" / "semantic_evaluator.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("filter_rules", source)
        self.assertNotIn("plugins.xiaolin_finance", source)
        self.assertNotIn("load_plugin", source)


class EvaluationInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = SemanticRiskEvaluator()

    def test_evaluate_text_requires_text(self) -> None:
        with self.assertRaises(RiskEvaluationError):
            self.evaluator.evaluate_text("   ")
        with self.assertRaises(RiskEvaluationError):
            self.evaluator.evaluate_text(None)  # type: ignore[arg-type]

    def test_evaluate_artifact_requires_a_mapping(self) -> None:
        with self.assertRaises(RiskEvaluationError):
            self.evaluator.evaluate_artifact("not an artifact")  # type: ignore[arg-type]

    def test_evaluate_artifact_uses_the_text_the_artifact_carries(self) -> None:
        plugin = load_plugin("plugins.xiaolin_finance")
        artifact = DistillationEngine(plugin).distill(
            [
                RawSource(
                    source_id="s-1",
                    source_type=SourceType.DOCUMENT,
                    content="You should buy this stock today.",
                )
            ]
        )

        results = self.evaluator.evaluate_artifact(artifact)

        self.assertTrue(results)
        self.assertIn("investment_advice", {item.category for item in results})

    def test_evaluate_artifact_ignores_existing_risk_constraints(self) -> None:
        """Reading them back would make the comparison circular."""

        artifact = {
            "knowledge_unit": [{"statement": "The income statement shows margin."}],
            "risk_constraints": [
                {
                    "rule_id": "finance.investment-advice",
                    "category": "investment_advice",
                    "severity": "block",
                    "action": "block",
                    "message": "enumerated match",
                    "source_ids": ["s-1"],
                }
            ],
        }

        self.assertEqual(self.evaluator.evaluate_artifact(artifact), ())

    def test_artifact_without_text_produces_no_result(self) -> None:
        self.assertEqual(self.evaluator.evaluate_artifact({}), ())


if __name__ == "__main__":
    unittest.main()
