from __future__ import annotations

import unittest

from core import RawSource, SourceType, load_plugin
from distillation_core import DistillationEngine
from workflows.content_distillation_pipeline import ContentDistillationPipeline


class RecordingGenerationAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return {"format": request.format_name, "status": "generated"}


class QualityGateControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = load_plugin("plugins.xiaolin_finance")

    def test_pass_continues_to_generation(self) -> None:
        adapter = RecordingGenerationAdapter()
        pipeline = ContentDistillationPipeline(
            DistillationEngine(self.plugin),
            adapter,
        )

        result = pipeline.run(
            [
                RawSource(
                    source_id="safe-1",
                    source_type=SourceType.DATA,
                    content=(
                        "The company business model connects revenue, cash flow, "
                        "margin data, and the latest earnings."
                    ),
                )
            ]
        )

        self.assertEqual(result.quality_report["gate_decision"], "PASS")
        self.assertEqual(result.quality_report["status"], "pass")
        self.assertTrue(result.quality_report["generation_adapter_invoked"])
        self.assertEqual(adapter.calls, 1)
        self.assertIsNotNone(result.generated_output)

    def test_fail_stops_before_generation(self) -> None:
        adapter = RecordingGenerationAdapter()
        pipeline = ContentDistillationPipeline(
            DistillationEngine(self.plugin),
            adapter,
        )

        result = pipeline.run(
            [
                RawSource(
                    source_id="risk-1",
                    source_type=SourceType.DOCUMENT,
                    content="Buy now for a guaranteed return.",
                )
            ]
        )

        self.assertEqual(result.quality_report["gate_decision"], "FAIL")
        self.assertEqual(result.quality_report["status"], "review_required")
        self.assertFalse(result.quality_report["generation_adapter_invoked"])
        self.assertEqual(adapter.calls, 0)
        self.assertIsNone(result.generated_output)


if __name__ == "__main__":
    unittest.main()
