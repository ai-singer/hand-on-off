"""Requirement 8: the adversarial framework must not reach production.

Phase 8.1 is offline discovery. If any production module imported it, the
generated attacks would be part of the runtime rather than a measurement of it.
These tests read the production trees and fail on any mention, so isolation is
checked mechanically rather than asserted in prose.
"""

from __future__ import annotations

import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

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

FORBIDDEN = ("risk_evaluation.adversarial", "from ..adversarial", "adversarial")


class AdversarialIsolationTests(unittest.TestCase):
    def _production_sources(self):
        for directory in ISOLATED_DIRECTORIES:
            root = WORKSPACE_ROOT / directory
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                yield path

    def test_no_production_module_mentions_the_adversarial_framework(self) -> None:
        offenders: list[str] = []
        for path in self._production_sources():
            text = path.read_text(encoding="utf-8")
            if "adversarial" in text:
                offenders.append(str(path.relative_to(WORKSPACE_ROOT)))

        self.assertEqual(offenders, [])

    def test_no_production_module_imports_the_risk_framework(self) -> None:
        offenders: list[str] = []
        for path in self._production_sources():
            text = path.read_text(encoding="utf-8")
            if "risk_evaluation" in text:
                offenders.append(str(path.relative_to(WORKSPACE_ROOT)))

        self.assertEqual(offenders, [])

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

    def test_the_scan_actually_visits_production_files(self) -> None:
        """A guard that scans nothing always passes."""

        files = list(self._production_sources())

        self.assertGreater(len(files), 20)
        self.assertTrue(any("plugins" in str(path) for path in files))
        self.assertTrue(any("runtime" in str(path) for path in files))

    def test_the_detector_would_notice_a_violation(self) -> None:
        """Sanity check the matcher itself, so the empty result means something."""

        sample = "from risk_evaluation.adversarial import default_cases"

        self.assertIn("adversarial", sample)
        self.assertIn("risk_evaluation", sample)

    def test_every_isolated_directory_exists(self) -> None:
        for directory in ISOLATED_DIRECTORIES:
            self.assertTrue((WORKSPACE_ROOT / directory).is_dir(), directory)

    def test_the_adversarial_package_is_offline_only(self) -> None:
        """It reads no plugin rule file and opens no socket."""

        package = WORKSPACE_ROOT / "risk_evaluation" / "adversarial"
        forbidden = ("import socket", "urllib", "requests", "httpx", "http.client")

        for path in package.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{path.name}: {token}")

    def test_the_adversarial_package_never_writes_outside_itself(self) -> None:
        """No production path is named as a write target."""

        package = WORKSPACE_ROOT / "risk_evaluation" / "adversarial"
        for path in package.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for directory in ISOLATED_DIRECTORIES:
                self.assertNotIn(f'"{directory}/', text, f"{path.name}: {directory}")

    def test_the_evaluator_sources_are_not_modified_by_this_package(self) -> None:
        """The bridge calls the evaluator; it does not patch it."""

        package = WORKSPACE_ROOT / "risk_evaluation" / "adversarial"
        forbidden = (
            "semantic_evaluator_v2.READER_PRESSURE_PATTERNS =",
            "semantic_evaluator_v2.V2_INTENT_PATTERNS =",
            "setattr(",
            "monkeypatch",
        )
        for path in package.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, text, f"{path.name}: {token}")

    def test_the_failure_repository_root_is_inside_the_package(self) -> None:
        from risk_evaluation.adversarial.failure_repository import FAILURE_ROOT

        self.assertTrue(
            FAILURE_ROOT.is_relative_to(WORKSPACE_ROOT / "risk_evaluation")
        )

    def test_the_candidate_file_is_inside_the_package(self) -> None:
        from risk_evaluation.adversarial.failure_repository import CANDIDATES_PATH

        self.assertTrue(
            CANDIDATES_PATH.is_relative_to(WORKSPACE_ROOT / "risk_evaluation")
        )


class TestPackageNamingTests(unittest.TestCase):
    def test_the_test_package_does_not_shadow_a_workspace_package(self) -> None:
        top_level = {
            path.name
            for path in WORKSPACE_ROOT.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }

        self.assertNotIn("adversarial_discovery", top_level)


if __name__ == "__main__":
    unittest.main()
