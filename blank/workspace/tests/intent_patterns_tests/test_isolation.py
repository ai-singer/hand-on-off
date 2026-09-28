"""Phase 8.4 is an offline prototype. It must not reach production."""

from __future__ import annotations

import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = WORKSPACE_ROOT / "risk_evaluation" / "intent_patterns"

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
    "risk_evaluation/taxonomy_v2.py",
    "risk_evaluation/semantic_evaluator.py",
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

    def test_no_production_module_mentions_the_pattern_layer(self) -> None:
        offenders = [
            str(path.relative_to(WORKSPACE_ROOT))
            for path in self._production_sources()
            if "intent_patterns" in path.read_text(encoding="utf-8")
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
        files = list(self._production_sources())

        self.assertGreater(len(files), 5)

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


class ProtectedFilesTests(unittest.TestCase):
    def test_the_protected_modules_do_not_import_the_pattern_layer(self) -> None:
        offenders = [
            relative
            for relative in PROTECTED
            if "intent_patterns" in (WORKSPACE_ROOT / relative).read_text(encoding="utf-8")
        ]

        self.assertEqual(offenders, [])

    def test_the_pattern_layer_does_not_patch_anything(self) -> None:
        forbidden = ("setattr(", "monkeypatch", "SIGNAL_PATTERNS =", "INTENT_PATTERNS =")
        offenders: list[str] = []
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.name}: {token}")

        self.assertEqual(offenders, [])

    def test_the_pattern_layer_is_offline(self) -> None:
        forbidden = (
            "import socket",
            "import urllib",
            "import requests",
            "import httpx",
            "http.client",
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

    def test_the_pattern_layer_writes_only_inside_itself(self) -> None:
        offenders: list[str] = []
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for directory in ISOLATED_DIRECTORIES:
                if f'"{directory}/' in text:
                    offenders.append(f"{path.name}: {directory}")

        self.assertEqual(offenders, [])

    def test_the_artifacts_live_inside_the_package(self) -> None:
        from risk_evaluation.intent_patterns.evaluation import (
            BENCHMARK_PATH,
            COMPARISON_PATH,
        )

        self.assertTrue(BENCHMARK_PATH.is_relative_to(PACKAGE))
        self.assertTrue(COMPARISON_PATH.is_relative_to(PACKAGE))

    def test_the_layer_is_not_registered_as_an_evaluator(self) -> None:
        from risk_evaluation.regression import EVALUATORS

        self.assertEqual(set(EVALUATORS), {"keyword", "semantic"})

    def test_no_benchmark_version_was_added(self) -> None:
        from risk_evaluation.benchmark_registry import BenchmarkRegistry

        keys = {
            f"{record.benchmark_id}/{record.version}"
            for record in BenchmarkRegistry().list_benchmarks()
        }

        self.assertFalse(any("intent_pattern" in key for key in keys))

    def test_the_registry_is_unchanged(self) -> None:
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


class TestPackageNamingTests(unittest.TestCase):
    def test_the_test_package_does_not_shadow_a_workspace_package(self) -> None:
        top_level = {
            path.name
            for path in WORKSPACE_ROOT.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }

        self.assertNotIn("intent_patterns_tests", top_level)

    def test_the_package_lives_under_risk_evaluation(self) -> None:
        self.assertTrue(PACKAGE.is_relative_to(WORKSPACE_ROOT / "risk_evaluation"))


if __name__ == "__main__":
    unittest.main()
