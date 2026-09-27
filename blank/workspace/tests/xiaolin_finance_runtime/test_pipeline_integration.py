from __future__ import annotations

import unittest

from core import RawSource, load_plugin
from core.schema_validation import validate_schema_instance
from distillation_core import DistillationEngine
from schema_validation import validate_runtime_schemas
from workflows.lobster.runtime_adapter import (
    build_generation_handoff,
    distill_payload,
    evaluate_gate,
    normalize_source_input,
    verify_plugin_checkpoint,
)

from ._fixtures import (
    DEFAULT_CONFIG,
    DomainFreePlugin,
    PLUGIN_MODULE_PATH,
    PLUGIN_NAME,
    PLUGIN_ROOT,
    REPORT_SOURCE,
    SHARED_SCHEMA_PATH,
    plugin_json,
)


class PipelineIntegrationTests(unittest.TestCase):
    """Step 2 - RawSource -> Engine -> Plugin -> Unified Artifact."""

    def setUp(self) -> None:
        self.plugin = load_plugin(PLUGIN_MODULE_PATH)

    def _distill(self, source: RawSource) -> dict:
        return DistillationEngine(self.plugin).distill([source])

    # 1 - the engine runs the plugin and returns one artifact
    def test_distillation_pipeline_produces_a_domain_artifact(self) -> None:
        artifact = self._distill(REPORT_SOURCE)

        self.assertEqual(artifact["plugin"]["name"], PLUGIN_NAME)
        self.assertEqual(artifact["artifact_version"], "1.0.0")
        self.assertEqual(
            artifact["domain_extension"]["plugin_identity"]["name"], PLUGIN_NAME
        )
        self.assertEqual(
            artifact["evaluation_result"]["domain"]["rubric_version"],
            plugin_json("evaluation/rubric.json")["version"],
        )

        # The plugin records the common signal counts it received. Only
        # topic_candidate is enhanced, so only that count may differ from the
        # final artifact.
        counts = artifact["domain_extension"]["common_signal_counts"]
        self.assertEqual(
            set(counts),
            {"topic_candidate", "content_template", "knowledge_unit", "style_pattern"},
        )
        for field in ("content_template", "knowledge_unit", "style_pattern"):
            self.assertEqual(counts[field], len(artifact[field]), field)
        self.assertLessEqual(counts["topic_candidate"], len(artifact["topic_candidate"]))

    # 2 - the common families are not rewritten by the plugin
    def test_common_fields_are_preserved_and_only_appended(self) -> None:
        plain = DistillationEngine(DomainFreePlugin()).distill([REPORT_SOURCE])
        enhanced = self._distill(REPORT_SOURCE)

        for field in ("knowledge_unit", "content_template", "style_pattern"):
            self.assertEqual(enhanced[field], plain[field], field)

        common_topics = len(plain["topic_candidate"])
        self.assertEqual(
            enhanced["topic_candidate"][:common_topics], plain["topic_candidate"]
        )
        self.assertGreater(len(enhanced["topic_candidate"]), common_topics)
        self.assertTrue(
            all(
                item["origin"] == PLUGIN_NAME
                for item in enhanced["topic_candidate"][common_topics:]
            )
        )

    # 3 - the domain extension exists and satisfies both schema layers
    def test_domain_extension_is_present_and_schema_valid(self) -> None:
        artifact = self._distill(REPORT_SOURCE)
        extension = artifact["domain_extension"]

        self.assertTrue(extension)
        validate_schema_instance(
            extension,
            PLUGIN_ROOT / "schemas" / "domain_extension.schema.json",
            root_name="domain_extension",
        )
        validation = validate_runtime_schemas(
            artifact,
            plugin=self.plugin,
            shared_schema_path=SHARED_SCHEMA_PATH,
        )
        self.assertEqual(validation.status, "PASS")
        self.assertTrue(validation.domain_schema_applied)
        self.assertEqual(
            extension["schema_version"],
            plugin_json("plugin.json")["domain_schema"]["version"],
        )

    # 4 - the whole runtime adapter chain accepts the domain artifact
    def test_runtime_adapter_chain_reaches_the_generation_handoff(self) -> None:
        envelope = normalize_source_input(
            [
                {
                    "source_id": REPORT_SOURCE.source_id,
                    "source_type": "document",
                    "content": REPORT_SOURCE.as_text(),
                    "metadata": {"source": "financial_report"},
                }
            ]
        )
        distilled = distill_payload(envelope, DEFAULT_CONFIG)
        checked = verify_plugin_checkpoint(distilled, DEFAULT_CONFIG)
        gate = evaluate_gate(checked)
        handoff = build_generation_handoff(gate)

        self.assertEqual(distilled["artifact"]["plugin"]["name"], PLUGIN_NAME)
        self.assertEqual(gate["decision"], "PASS")
        self.assertTrue(gate["can_continue"])
        self.assertEqual(handoff["status"], "ready_for_generation")


if __name__ == "__main__":
    unittest.main()
