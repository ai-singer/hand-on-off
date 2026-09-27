"""Phase 8.2 adds analysis only. It must not reach production or the network."""

from __future__ import annotations

import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = WORKSPACE_ROOT / "risk_evaluation" / "attribution"

#: Trees that must never import the risk evaluation framework at all. Kept in
#: step with `tests/risk_semantic_evaluator/test_comparison.py`.
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


class ProductionIsolationTests(unittest.TestCase):
    def _production_sources(self):
        for directory in ISOLATED_DIRECTORIES:
            root = WORKSPACE_ROOT / directory
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                yield path

    def test_no_production_module_mentions_the_attribution_layer(self) -> None:
        offenders = [
            str(path.relative_to(WORKSPACE_ROOT))
            for path in self._production_sources()
            if "risk_evaluation" in path.read_text(encoding="utf-8")
        ]

        self.assertEqual(offenders, [])

    def test_the_scan_actually_visits_production_files(self) -> None:
        """A guard that scans nothing always passes."""

        files = list(self._production_sources())

        self.assertGreater(len(files), 20)
        self.assertTrue(any("plugins" in str(path) for path in files))
        self.assertTrue(any("runtime" in str(path) for path in files))

    def test_the_plugin_still_produces_its_own_risk_constraints(self) -> None:
        """Production detection is the plugin's, and is unchanged."""

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


class OfflineOnlyTests(unittest.TestCase):
    """No network, no model, no external API."""

    FORBIDDEN = (
        "import socket",
        "import urllib",
        "import requests",
        "import httpx",
        "http.client",
        "openai",
        "anthropic",
        "transformers",
        "torch",
        "spacy",
        "nltk",
    )

    def test_the_package_imports_nothing_external(self) -> None:
        offenders: list[str] = []
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in self.FORBIDDEN:
                if token in text:
                    offenders.append(f"{path.name}: {token}")

        self.assertEqual(offenders, [])

    def test_the_package_only_imports_from_itself_and_the_taxonomy(self) -> None:
        """A prototype that reaches into the evaluator would be coupled to it."""

        forbidden = (
            "semantic_evaluator_v2",
            "semantic_evaluator",
            "evaluator",
            "benchmark_registry",
            "adversarial",
            "release_freeze",
        )
        offenders: list[str] = []
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if f"import {token}" in text or f"from ..{token}" in text:
                    offenders.append(f"{path.name}: {token}")

        self.assertEqual(offenders, [])

    def test_the_package_writes_only_inside_itself(self) -> None:
        offenders: list[str] = []
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for directory in ISOLATED_DIRECTORIES:
                if f'"{directory}/' in text:
                    offenders.append(f"{path.name}: {directory}")

        self.assertEqual(offenders, [])

    def test_the_annotation_report_is_inside_the_package(self) -> None:
        from risk_evaluation.attribution.evaluation import REPORT_PATH

        self.assertTrue(REPORT_PATH.is_relative_to(PACKAGE))


class EvaluatorUntouchedTests(unittest.TestCase):
    """The phase forbids modifying the evaluator or the taxonomy."""

    def test_the_attribution_package_does_not_patch_the_evaluator(self) -> None:
        forbidden = ("setattr(", "monkeypatch", "SIGNAL_PATTERNS =", "INTENT_PATTERNS =")
        offenders: list[str] = []
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.name}: {token}")

        self.assertEqual(offenders, [])

    def test_the_taxonomy_v2_statement_sources_are_unchanged(self) -> None:
        from risk_evaluation.taxonomy_v2 import STATEMENT_SOURCES

        self.assertEqual(
            STATEMENT_SOURCES, ("author", "third_party", "quoted", "unknown")
        )

    def test_the_attribution_layer_declares_its_own_speakers(self) -> None:
        """Three speakers here, four statement sources there: not the same axis."""

        from risk_evaluation.attribution.model import SPEAKERS, STANCES
        from risk_evaluation.taxonomy_v2 import STATEMENT_SOURCES

        self.assertEqual(SPEAKERS, ("author", "third_party", "unknown"))
        self.assertNotIn("quoted", SPEAKERS)
        self.assertIn("quoted", STANCES)
        self.assertNotEqual(tuple(SPEAKERS), tuple(STATEMENT_SOURCES))


class TestPackageNamingTests(unittest.TestCase):
    def test_the_test_package_does_not_shadow_a_workspace_package(self) -> None:
        top_level = {
            path.name
            for path in WORKSPACE_ROOT.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }

        self.assertNotIn("attribution_layer", top_level)

    def test_the_attribution_package_lives_under_risk_evaluation(self) -> None:
        self.assertTrue(
            PACKAGE.is_relative_to(WORKSPACE_ROOT / "risk_evaluation")
        )


if __name__ == "__main__":
    unittest.main()
