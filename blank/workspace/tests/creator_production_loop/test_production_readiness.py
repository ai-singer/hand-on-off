from __future__ import annotations

import unittest

from core import load_plugin
from distillation_core import DistillationEngine
from production.generation_input import GENERATION_INPUT_FIELDS, resolve_generation_input
from production.risk_recall import PROHIBITED_PROBES, measure_risk_recall
from workflows.content_distillation_pipeline import ContentDistillationPipeline

from ._fixtures import (
    ARTIFACT_SECTIONS,
    PLUGIN_MODULE_PATH,
    ROLE_SOURCES,
    RecordingGenerationAdapter,
)


#: Recorded in docs/CREATOR_PRODUCTION_READINESS_REPORT.md. If these fail
#: because the rules improved, update that report in the same change: the
#: report claims a specific baseline and must not drift from reality.
DOCUMENTED_OVERALL_RECALL = 0.55
DOCUMENTED_PARAPHRASE_RECALL = 0.0
DOCUMENTED_FALSE_POSITIVE_RATE = 0.2


class FullProductionLoopTests(unittest.TestCase):
    """Source -> distill -> evaluate -> artifact -> generate contract."""

    def test_four_source_kinds_traverse_the_whole_loop(self) -> None:
        adapter = RecordingGenerationAdapter()
        pipeline = ContentDistillationPipeline(
            DistillationEngine(load_plugin(PLUGIN_MODULE_PATH)), adapter
        )

        result = pipeline.run(list(ROLE_SOURCES))

        # Artifact: one validated artifact carrying every section.
        self.assertEqual(set(result.artifact), set(ARTIFACT_SECTIONS))
        self.assertEqual(result.artifact["artifact_version"], "1.0.0")
        self.assertEqual(result.artifact["plugin"]["name"], "xiaolin_finance")

        # Evaluation: a production decision, not a display layer.
        self.assertEqual(result.quality_report["status"], "pass")
        self.assertEqual(result.artifact["risk_constraints"], [])

        # Generation contract: every addressed input resolves.
        resolved = resolve_generation_input(result.artifact)
        self.assertTrue(resolved.complete, resolved.render())
        self.assertEqual(set(resolved.values), set(GENERATION_INPUT_FIELDS))

        # Generation: consumed exactly once, after the gate allowed it.
        self.assertEqual(adapter.calls, 1)
        self.assertIs(adapter.requests[0].artifact, result.artifact)


class RiskRecallBaselineTests(unittest.TestCase):
    """Pins the measured risk-boundary baseline to the documented numbers."""

    def setUp(self) -> None:
        self.report = measure_risk_recall()

    def test_probe_set_is_intact(self) -> None:
        self.assertEqual(self.report.total_prohibited, len(PROHIBITED_PROBES))
        self.assertEqual(self.report.total_prohibited, 20)
        self.assertEqual(self.report.clean_probes, 5)

    def test_enumerated_wording_is_always_caught(self) -> None:
        self.assertEqual(self.report.keyword_probes, 11)
        self.assertEqual(self.report.keyword_recall, 1.0)

    def test_measured_baseline_matches_the_readiness_report(self) -> None:
        self.assertEqual(self.report.recall, DOCUMENTED_OVERALL_RECALL)
        self.assertEqual(
            self.report.paraphrase_recall, DOCUMENTED_PARAPHRASE_RECALL
        )
        self.assertEqual(
            round(self.report.false_positive_rate, 4),
            DOCUMENTED_FALSE_POSITIVE_RATE,
        )


if __name__ == "__main__":
    unittest.main()
