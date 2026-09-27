"""Acceptance criterion 5 and the phase's regression protection.

The experiment is only meaningful if the thing it is compared against cannot
move. These tests pin the baseline's output on a set of texts and show that
running the experiment does not change it.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from risk_evaluation.attribution_experiment.cases import EXPERIMENT_CASES
from risk_evaluation.attribution_experiment.evaluator import (
    AttributionAwareEvaluator,
    attribution_aware,
)
from risk_evaluation.semantic_evaluator_v2 import SemanticRiskEvaluatorV2


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

#: Baseline output, recorded before the experiment was written and unchanged by
#: it. If a later change alters any of these, the comparison in Phase 8.3 is
#: invalidated and the report has to be re-measured.
PINNED_BASELINE = {
    "This fund cannot lose money.": ("financial_guarantee",),
    "This return is guaranteed.": (),
    "Buy this stock today.": ("investment_advice",),
    "The share price will certainly double.": ("market_prediction",),
    "Do not miss this opportunity.": ("emotional_manipulation",),
    "Sources say the company will be acquired.": ("unverified_information",),
    "The company reports its results in March.": (),
    "Analysts say this fund cannot lose money.": ("unverified_information",),
    "The company said the fund cannot lose money.": ("financial_guarantee",),
    "Economists forecast growth. This fund cannot lose money.": (),
}


def _categories(text: str) -> tuple[str, ...]:
    return tuple(
        sorted({item.category for item in SemanticRiskEvaluatorV2().evaluate_text(text)})
    )


class BaselineUnchangedTests(unittest.TestCase):
    def test_the_recorded_baseline_still_reproduces(self) -> None:
        wrong: list[str] = []
        for text, expected in PINNED_BASELINE.items():
            actual = _categories(text)
            if actual != expected:
                wrong.append(f"{text!r}: {expected} -> {actual}")

        self.assertEqual(wrong, [])

    def test_running_the_experiment_does_not_move_the_baseline(self) -> None:
        before = {text: _categories(text) for text in PINNED_BASELINE}
        evaluator = AttributionAwareEvaluator()
        for case in EXPERIMENT_CASES:
            evaluator.evaluate(case.text)
        after = {text: _categories(text) for text in PINNED_BASELINE}

        self.assertEqual(before, after)

    def test_the_experiment_result_carries_the_baseline(self) -> None:
        """"Both results are saved", as the phase requires."""

        result = attribution_aware("Economists forecast growth. This fund cannot lose money.")

        self.assertEqual(result.baseline, ())
        self.assertEqual(result.baseline_categories, ())
        self.assertEqual(result.baseline_flagged, False)

    def test_the_baseline_result_is_the_evaluators_own_output(self) -> None:
        text = "This fund cannot lose money."

        self.assertEqual(
            AttributionAwareEvaluator().baseline_for(text),
            SemanticRiskEvaluatorV2().evaluate_text(text),
        )

    def test_the_experiment_does_not_replace_the_baseline_name(self) -> None:
        evaluator = AttributionAwareEvaluator()

        self.assertEqual(evaluator.baseline_evaluator, "semantic-intent-v2")
        self.assertNotEqual(evaluator.name, evaluator.baseline_evaluator)


class EvaluatorSourceUntouchedTests(unittest.TestCase):
    """Mechanical checks that the protected files were not edited."""

    PROTECTED = (
        "risk_evaluation/semantic_evaluator_v2.py",
        "risk_evaluation/taxonomy_v2.py",
    )

    def test_the_protected_modules_do_not_import_the_experiment(self) -> None:
        """`attribution` alone is not the check.

        `semantic_evaluator_v2` legitimately contains `analyze_attribution` and
        `taxonomy_v2` declares `ATTRIBUTION_AGNOSTIC_CATEGORIES`. What must not
        appear is a dependency on this experiment.
        """

        offenders: list[str] = []
        for relative in self.PROTECTED:
            text = (WORKSPACE_ROOT / relative).read_text(encoding="utf-8")
            if "attribution_experiment" in text:
                offenders.append(relative)

        self.assertEqual(offenders, [])

    def test_the_experiment_does_not_patch_the_evaluator(self) -> None:
        package = WORKSPACE_ROOT / "risk_evaluation" / "attribution_experiment"
        forbidden = ("setattr(", "monkeypatch", "SIGNAL_PATTERNS =", "INTENT_PATTERNS =")

        offenders: list[str] = []
        for path in package.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.name}: {token}")

        self.assertEqual(offenders, [])

    def test_the_experiment_is_not_in_the_production_import_graph(self) -> None:
        isolated = (
            "runtime",
            "workflows",
            "production",
            "plugins",
            "core",
            "artifact",
            "security",
            "distillation_core",
        )
        offenders: list[str] = []
        for directory in isolated:
            root = WORKSPACE_ROOT / directory
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                if "attribution" in path.read_text(encoding="utf-8"):
                    offenders.append(str(path.relative_to(WORKSPACE_ROOT)))

        self.assertEqual(offenders, [])

    def test_the_scan_visits_real_files(self) -> None:
        files = [
            path
            for directory in ("runtime", "plugins", "workflows", "production")
            for path in (WORKSPACE_ROOT / directory).rglob("*.py")
        ]

        self.assertGreater(len(files), 5)

    def test_the_experiment_is_not_registered_as_an_evaluator(self) -> None:
        """`regression.EVALUATORS` is the frozen pair; the experiment is not in it."""

        from risk_evaluation.regression import EVALUATORS

        self.assertEqual(set(EVALUATORS), {"keyword", "semantic"})

    def test_the_benchmark_registry_has_no_experiment_version(self) -> None:
        from risk_evaluation.benchmark_registry import BenchmarkRegistry

        keys = {
            f"{record.benchmark_id}/{record.version}"
            for record in BenchmarkRegistry().list_benchmarks()
        }

        self.assertFalse(any("attribution_experiment" in key for key in keys))


class TestPackageNamingTests(unittest.TestCase):
    def test_the_test_package_does_not_shadow_a_workspace_package(self) -> None:
        top_level = {
            path.name
            for path in WORKSPACE_ROOT.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }

        self.assertNotIn("attribution_experiment_tests", top_level)


if __name__ == "__main__":
    unittest.main()
