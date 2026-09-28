"""v3 is an experimental composition. Production must be untouched by it."""

from __future__ import annotations

import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = WORKSPACE_ROOT / "risk_evaluation" / "v3"

ISOLATED_DIRECTORIES = (
    "runtime",
    "workflows",
    "evaluation",
    "distillation_core",
    "plugins",
    "production",
    "core",
    "config",
    "schema_validation",
    "security",
    "artifact",
)

PROTECTED = (
    "risk_evaluation/semantic_evaluator_v2.py",
    "risk_evaluation/semantic_evaluator.py",
    "risk_evaluation/taxonomy_v2.py",
    "risk_evaluation/taxonomy.py",
)


class ProductionIsolationTests(unittest.TestCase):
    def _production_sources(self):
        for directory in ISOLATED_DIRECTORIES:
            root = WORKSPACE_ROOT / directory
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                yield path

    def test_no_production_module_mentions_v3(self) -> None:
        offenders = [
            str(path.relative_to(WORKSPACE_ROOT))
            for path in self._production_sources()
            if "risk_evaluation.v3" in path.read_text(encoding="utf-8")
        ]

        self.assertEqual(offenders, [])

    def test_no_production_module_imports_the_risk_framework(self) -> None:
        offenders = [
            str(path.relative_to(WORKSPACE_ROOT))
            for path in self._production_sources()
            if "risk_evaluation" in path.read_text(encoding="utf-8")
        ]

        self.assertEqual(offenders, [])

    def test_the_scan_visits_real_files(self) -> None:
        self.assertGreater(len(list(self._production_sources())), 5)

    def test_the_plugin_still_produces_its_own_risk_constraints(self) -> None:
        from core import RawSource, SourceType, load_plugin
        from distillation_core import DistillationEngine

        plugin = load_plugin("plugins.xiaolin_finance")
        artifact = DistillationEngine(plugin).distill(
            [
                RawSource(
                    source_id="s-1",
                    source_type=SourceType.DOCUMENT,
                    content="Buy now for a guaranteed return.",
                )
            ]
        )

        self.assertTrue(artifact["risk_constraints"])
        self.assertTrue(
            all("evaluator" not in item for item in artifact["risk_constraints"])
        )


class ProtectedModuleTests(unittest.TestCase):
    def test_the_protected_modules_do_not_import_v3(self) -> None:
        offenders = [
            relative
            for relative in PROTECTED
            if "v3" in (WORKSPACE_ROOT / relative).read_text(encoding="utf-8").split()
            or "risk_evaluation.v3" in (WORKSPACE_ROOT / relative).read_text(encoding="utf-8")
        ]

        self.assertEqual(offenders, [])

    def test_v3_does_not_patch_anything(self) -> None:
        forbidden = ("setattr(", "monkeypatch")
        offenders: list[str] = []
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.name}: {token}")

        self.assertEqual(offenders, [])

    def test_v3_reuses_the_earlier_layers_rather_than_copying_them(self) -> None:
        """Six entities, one lexicon: the v3 set extends Phase 8.4's model."""

        from risk_evaluation.intent_patterns.model import EntityLexicon

        from risk_evaluation.v3.patterns import ENTITIES

        self.assertIsInstance(ENTITIES, EntityLexicon)

    def test_v3_is_offline(self) -> None:
        forbidden = (
            "import socket",
            "import urllib",
            "import requests",
            "import httpx",
            "openai",
            "anthropic",
        )
        offenders: list[str] = []
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.name}: {token}")

        self.assertEqual(offenders, [])

    def test_v3_writes_only_inside_itself(self) -> None:
        offenders: list[str] = []
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for directory in ISOLATED_DIRECTORIES:
                if f'"{directory}/' in text:
                    offenders.append(f"{path.name}: {directory}")

        self.assertEqual(offenders, [])

    def test_the_artifacts_live_inside_v3(self) -> None:
        from risk_evaluation.v3.benchmark import REPORT_PATH
        from risk_evaluation.v3.replay import REPLAY_PATH

        self.assertTrue(REPORT_PATH.is_relative_to(PACKAGE))
        self.assertTrue(REPLAY_PATH.is_relative_to(PACKAGE))

    def test_v3_is_not_registered_as_an_evaluator(self) -> None:
        from risk_evaluation.regression import EVALUATORS

        self.assertEqual(set(EVALUATORS), {"keyword", "semantic"})

    def test_no_benchmark_version_was_added(self) -> None:
        from risk_evaluation.benchmark_registry import BenchmarkRegistry

        keys = {
            f"{record.benchmark_id}/{record.version}"
            for record in BenchmarkRegistry().list_benchmarks()
        }

        self.assertEqual(
            keys,
            {
                "semantic/v1",
                "semantic/v2",
                "semantic/v3",
                "semantic/v4",
                "semantic/adversarial/v1",
                # Phase 8.9 added the independent validation benchmark. Registered
                # here rather than filtered out, so a version nobody declared still
                # fails this test.
                "risk/independent/v1",
            },
        )


class UntouchedOutputTests(unittest.TestCase):
    """The pipeline calls the evaluator; it does not change what it returns."""

    PINNED = {
        "This fund cannot lose money.": ("financial_guarantee",),
        "This return is guaranteed.": (),
        "This is a guaranteed return.": ("financial_guarantee",),
        "Do not miss this opportunity.": ("emotional_manipulation",),
        "The company reports its results in March.": (),
    }

    def _categories(self, text: str) -> tuple[str, ...]:
        from risk_evaluation.semantic_evaluator_v2 import SemanticRiskEvaluatorV2

        return tuple(
            sorted({i.category for i in SemanticRiskEvaluatorV2().evaluate_text(text)})
        )

    def test_the_evaluator_output_is_pinned(self) -> None:
        wrong = [
            f"{text!r}: {expected} -> {self._categories(text)}"
            for text, expected in self.PINNED.items()
            if self._categories(text) != expected
        ]

        self.assertEqual(wrong, [])

    def test_running_the_pipeline_does_not_move_the_evaluator(self) -> None:
        before = {text: self._categories(text) for text in self.PINNED}

        from risk_evaluation.v3.benchmark import evaluate_benchmark
        from risk_evaluation.v3.replay import replay as run_replay

        evaluate_benchmark()
        run_replay()

        after = {text: self._categories(text) for text in self.PINNED}
        self.assertEqual(before, after)

    def test_the_taxonomy_is_unchanged(self) -> None:
        from risk_evaluation.taxonomy import RISK_TAXONOMY

        self.assertEqual(
            {entry.name for entry in RISK_TAXONOMY},
            {
                "investment_advice",
                "market_prediction",
                "financial_guarantee",
                "unverified_information",
                "emotional_manipulation",
            },
        )


class TestPackageNamingTests(unittest.TestCase):
    def test_the_test_package_does_not_shadow_a_workspace_package(self) -> None:
        top_level = {
            path.name
            for path in WORKSPACE_ROOT.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }

        self.assertNotIn("risk_evaluation_v3", top_level)

    def test_v3_lives_under_risk_evaluation(self) -> None:
        self.assertTrue(PACKAGE.is_relative_to(WORKSPACE_ROOT / "risk_evaluation"))


if __name__ == "__main__":
    unittest.main()
