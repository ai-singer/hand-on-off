from __future__ import annotations

import unittest

from core import load_plugin
from distillation_core import DistillationEngine
from workflows.content_distillation_pipeline import ContentDistillationPipeline

from ._fixtures import (
    PLUGIN_MODULE_PATH,
    PROHIBITED_CATEGORIES,
    RecordingGenerationAdapter,
    plugin_json,
    source,
)

ADVICE_TEXT = "This stock is a guaranteed buy."
PREDICTION_TEXT = "Company price will definitely rise."
UNVERIFIED_TEXT = "据说不具名的消息人士透露，该公司收入翻倍。"


class RiskBoundaryTests(unittest.TestCase):
    """Step 4 - the plugin's prohibited categories act on real input."""

    def setUp(self) -> None:
        self.plugin = load_plugin(PLUGIN_MODULE_PATH)

    def _artifact(self, text: str) -> dict:
        return DistillationEngine(self.plugin).distill([source(text)])

    def _run(self, text: str):
        adapter = RecordingGenerationAdapter()
        pipeline = ContentDistillationPipeline(
            DistillationEngine(self.plugin), adapter
        )
        return pipeline.run([source(text)]), adapter

    # Test 1 - investment advice
    def test_investment_advice_is_blocked(self) -> None:
        artifact = self._artifact(ADVICE_TEXT)
        constraints = {item["category"]: item for item in artifact["risk_constraints"]}

        self.assertIn("investment_advice", constraints)
        self.assertEqual(constraints["investment_advice"]["severity"], "block")
        self.assertEqual(constraints["investment_advice"]["action"], "block")
        self.assertEqual(
            artifact["evaluation_result"]["domain"]["finance_checks"]["risk_boundary"][
                "score"
            ],
            0.0,
        )

    def test_investment_advice_never_reaches_generation(self) -> None:
        result, adapter = self._run(ADVICE_TEXT)

        self.assertEqual(result.quality_report["status"], "review_required")
        self.assertEqual(adapter.calls, 0)

    # Test 2 - market prediction
    def test_market_prediction_requires_evidence(self) -> None:
        artifact = self._artifact(PREDICTION_TEXT)
        constraints = {item["category"]: item for item in artifact["risk_constraints"]}

        self.assertIn("market_prediction", constraints)
        self.assertEqual(constraints["market_prediction"]["severity"], "warning")
        self.assertEqual(
            constraints["market_prediction"]["action"], "require_evidence"
        )

    def test_market_prediction_enters_review(self) -> None:
        result, adapter = self._run(PREDICTION_TEXT)

        self.assertEqual(result.quality_report["status"], "review_required")
        self.assertEqual(adapter.calls, 0)

    # Test 3 - unverified fact
    def test_unverified_fact_raises_a_risk_constraint(self) -> None:
        artifact = self._artifact(UNVERIFIED_TEXT)
        constraints = {item["category"]: item for item in artifact["risk_constraints"]}

        self.assertIn("unverified_fact", constraints)
        self.assertEqual(constraints["unverified_fact"]["action"], "require_evidence")
        self.assertLess(
            artifact["evaluation_result"]["domain"]["finance_checks"][
                "data_credibility"
            ]["score"],
            1.0,
        )

    def test_every_prohibited_category_is_reachable(self) -> None:
        declared = set(plugin_json("rules/filter_rules.json")["prohibited_categories"])

        self.assertEqual(declared, set(PROHIBITED_CATEGORIES))
        self.assertEqual(
            declared, set(plugin_json("plugin.json")["prohibits"])
        )


if __name__ == "__main__":
    unittest.main()
