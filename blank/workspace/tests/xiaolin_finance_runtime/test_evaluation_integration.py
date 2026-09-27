from __future__ import annotations

import copy
import unittest
from unittest import mock

from core import load_plugin
from distillation_core import DistillationEngine
from plugins.xiaolin_finance import plugin as finance_plugin_module

from ._fixtures import PLUGIN_MODULE_PATH, REPORT_SOURCE, plugin_json


def _rubric_overrides(*, base=None, pass_score=None):
    """Reload the rule files, substituting rubric values on the fly."""

    real_loader = finance_plugin_module._load_json

    def loader(relative_path: str):
        payload = real_loader(relative_path)
        if relative_path == "evaluation/rubric.json":
            payload = copy.deepcopy(payload)
            if base is not None:
                payload["scoring"]["base"] = base
            if pass_score is not None:
                payload["pass_score"] = pass_score
        return payload

    return loader


class EvaluationIntegrationTests(unittest.TestCase):
    """Step 5 - the domain evaluation reaches the quality assessment."""

    def setUp(self) -> None:
        self.plugin = load_plugin(PLUGIN_MODULE_PATH)

    def _domain(self, rubric_loader=None) -> dict:
        if rubric_loader is None:
            artifact = DistillationEngine(self.plugin).distill([REPORT_SOURCE])
        else:
            with mock.patch.object(
                finance_plugin_module, "_load_json", side_effect=rubric_loader
            ):
                artifact = DistillationEngine(self.plugin).distill([REPORT_SOURCE])
        return artifact["evaluation_result"]["domain"]

    # 1 - both evaluation layers are reported
    def test_inherited_and_finance_dimensions_are_reported(self) -> None:
        rubric = plugin_json("evaluation/rubric.json")
        domain = self._domain()

        self.assertEqual(
            set(domain["inherited_checks"]), set(rubric["inherited_checks"])
        )
        self.assertEqual(set(domain["finance_checks"]), set(rubric["finance_checks"]))
        self.assertEqual(domain["rubric_version"], rubric["version"])

        for name, check in {**domain["inherited_checks"], **domain["finance_checks"]}.items():
            self.assertGreaterEqual(check["score"], 0.0, name)
            self.assertLessEqual(check["score"], 1.0, name)
            self.assertTrue(check["note"], name)

        self.assertEqual(
            domain["passed"], domain["score"] >= rubric["pass_score"]
        )

    # 2 - the scoring policy is read from the rubric, not hardcoded
    def test_scoring_policy_is_driven_by_the_rubric(self) -> None:
        baseline = self._domain()

        raised = self._domain(_rubric_overrides(base=0.95))
        self.assertGreater(raised["score"], baseline["score"])
        self.assertEqual(
            {**raised["inherited_checks"], **raised["finance_checks"]},
            {**baseline["inherited_checks"], **baseline["finance_checks"]},
        )

        strict = self._domain(_rubric_overrides(pass_score=0.99))
        self.assertEqual(strict["score"], baseline["score"])
        self.assertFalse(strict["passed"])
        self.assertTrue(baseline["passed"])


if __name__ == "__main__":
    unittest.main()
