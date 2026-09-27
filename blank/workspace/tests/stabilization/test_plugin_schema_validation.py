from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from core import RawSource, SourceType, load_plugin
from core.errors import ArtifactValidationError
from distillation_core import DistillationEngine
from plugin_interface import PluginContribution, PluginIdentity
from schema_validation import validate_runtime_schemas
from workflows.content_distillation_pipeline import ContentDistillationPipeline


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class RecordingGenerationAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return {"status": "generated", "format": request.format_name}


class NoPrivateSchemaPlugin:
    @property
    def identity(self) -> PluginIdentity:
        return PluginIdentity(
            name="no_private_schema",
            version="1.0.0",
            domain="general",
            creator_target="general-audience",
        )

    def enhance(self, raw_sources, common_signals) -> PluginContribution:
        return PluginContribution(
            domain_extension={},
            evaluation_result={"score": 1.0, "passed": True},
        )


class PluginSchemaRuntimeValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = RawSource(
            source_id="source-1",
            source_type=SourceType.DATA,
            content=(
                "The company business model connects revenue, cash flow, "
                "margin data, and earnings."
            ),
        )

    def test_valid_plugin_domain_extension_passes(self) -> None:
        plugin = load_plugin("plugins.xiaolin_finance")
        artifact = DistillationEngine(plugin).distill([self.source])

        validation = validate_runtime_schemas(
            artifact,
            plugin=plugin,
            shared_schema_path=(
                WORKSPACE_ROOT / "schemas" / "unified_distillation_artifact.json"
            ),
        )

        self.assertEqual(validation.status, "PASS")
        self.assertTrue(validation.domain_schema_applied)
        self.assertIsNotNone(validation.domain_schema_path)

    def test_invalid_plugin_domain_extension_stops_before_generation(self) -> None:
        plugin = load_plugin("plugins.xiaolin_finance")
        adapter = RecordingGenerationAdapter()
        pipeline = ContentDistillationPipeline(DistillationEngine(plugin), adapter)
        invalid_contribution = PluginContribution(
            domain_extension={"unexpected": "invalid"},
            evaluation_result={"score": 1.0, "passed": True},
        )

        with patch.object(
            type(plugin),
            "enhance",
            return_value=invalid_contribution,
        ):
            with self.assertRaises(ArtifactValidationError):
                pipeline.run([self.source])

        self.assertEqual(adapter.calls, 0)

    def test_plugin_without_private_schema_runs_normally(self) -> None:
        adapter = RecordingGenerationAdapter()
        pipeline = ContentDistillationPipeline(
            DistillationEngine(NoPrivateSchemaPlugin()),
            adapter,
        )

        result = pipeline.run([self.source])

        self.assertEqual(result.quality_report["gate_decision"], "PASS")
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(result.artifact["domain_extension"], {})


if __name__ == "__main__":
    unittest.main()
