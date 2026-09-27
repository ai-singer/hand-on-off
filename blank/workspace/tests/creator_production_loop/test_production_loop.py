from __future__ import annotations

import unittest

from core import load_plugin
from distillation_core import DistillationEngine
from production.generation_input import (
    GENERATION_INPUT_FIELDS,
    GenerationInputError,
    resolve_generation_input,
)
from workflows.content_distillation_pipeline import ContentDistillationPipeline
from workflows.content_distillation_pipeline.generation_interface import (
    GenerationRequest,
)
from workflows.lobster.runtime_adapter import build_generation_handoff

from ._fixtures import (
    COMMON_FAMILIES,
    DISTILLATION_SECTIONS,
    DomainFreePlugin,
    PLUGIN_MODULE_PATH,
    QUALITY_SOURCE,
    RISK_SOURCE,
    ROLE_SOURCES,
    RecordingGenerationAdapter,
)


class PluginEnhancementTests(unittest.TestCase):
    """Step 4 - the Creator plugin adds domain judgement without rewriting."""

    def setUp(self) -> None:
        self.plugin = load_plugin(PLUGIN_MODULE_PATH)

    def test_finance_material_gains_the_domain_extension(self) -> None:
        artifact = DistillationEngine(self.plugin).distill(list(ROLE_SOURCES))
        extension = artifact["domain_extension"]

        self.assertTrue(extension)
        for section in DISTILLATION_SECTIONS:
            self.assertIn(section, extension)
        self.assertTrue(
            any(extension[name]["matched"] for name in DISTILLATION_SECTIONS)
        )
        self.assertEqual(extension["plugin_identity"]["name"], "xiaolin_finance")
        self.assertTrue(extension["source_classification"])

    def test_common_families_are_never_rewritten(self) -> None:
        plain = DistillationEngine(DomainFreePlugin()).distill(list(ROLE_SOURCES))
        enhanced = DistillationEngine(self.plugin).distill(list(ROLE_SOURCES))

        for family in ("content_template", "knowledge_unit", "style_pattern"):
            self.assertEqual(enhanced[family], plain[family], family)

        common_topics = len(plain["topic_candidate"])
        self.assertEqual(
            enhanced["topic_candidate"][:common_topics], plain["topic_candidate"]
        )
        self.assertGreaterEqual(len(enhanced["topic_candidate"]), common_topics)
        self.assertTrue(COMMON_FAMILIES)


class EvaluationLoopTests(unittest.TestCase):
    """Step 5 - evaluation is a production gate, not a display layer."""

    def setUp(self) -> None:
        self.plugin = load_plugin(PLUGIN_MODULE_PATH)

    def _run(self, source):
        adapter = RecordingGenerationAdapter()
        pipeline = ContentDistillationPipeline(
            DistillationEngine(self.plugin), adapter
        )
        return pipeline.run([source]), adapter

    # Case 1 - high quality finance explanation
    def test_high_quality_explanation_passes_and_reaches_the_handoff(self) -> None:
        result, adapter = self._run(QUALITY_SOURCE)

        self.assertEqual(result.quality_report["status"], "pass")
        self.assertTrue(result.artifact["evaluation_result"]["domain"]["passed"])
        self.assertEqual(result.artifact["risk_constraints"], [])
        self.assertEqual(adapter.calls, 1)

        handoff = build_generation_handoff(
            {
                "artifact": result.artifact,
                "can_continue": True,
                "decision": "PASS",
            }
        )
        self.assertEqual(handoff["status"], "ready_for_generation")

    # Case 2 - risky content
    def test_risky_content_is_gated_and_never_reaches_generation(self) -> None:
        result, adapter = self._run(RISK_SOURCE)

        blocking = [
            item
            for item in result.artifact["risk_constraints"]
            if item["severity"] == "block"
        ]
        self.assertTrue(blocking)
        self.assertIn("investment_advice", {item["category"] for item in blocking})
        self.assertEqual(result.quality_report["status"], "review_required")
        self.assertEqual(adapter.calls, 0)

        with self.assertRaises(ValueError):
            build_generation_handoff(
                {
                    "artifact": result.artifact,
                    "can_continue": False,
                    "decision": "REVIEW_REQUIRED",
                }
            )


class GenerationContractTests(unittest.TestCase):
    """Step 6 - a validated artifact is consumable by a generation module."""

    def setUp(self) -> None:
        self.plugin = load_plugin(PLUGIN_MODULE_PATH)
        self.artifact = DistillationEngine(self.plugin).distill(list(ROLE_SOURCES))

    def test_every_addressed_input_resolves_from_the_artifact(self) -> None:
        resolved = resolve_generation_input(self.artifact)

        self.assertEqual(set(resolved.values), set(GENERATION_INPUT_FIELDS))
        self.assertEqual(resolved.missing, ())
        self.assertTrue(resolved.complete, resolved.render())

    def test_projection_is_derived_and_creates_no_new_artifact_format(self) -> None:
        resolved = resolve_generation_input(self.artifact)

        # Every projected value is the artifact section itself, not a copy of a
        # new shape, so the projection cannot drift from the artifact.
        self.assertIs(resolved.values["topic"], self.artifact["topic_candidate"])
        self.assertIs(resolved.values["structure"], self.artifact["content_template"])
        self.assertIs(resolved.values["knowledge"], self.artifact["knowledge_unit"])
        self.assertIs(resolved.values["style"], self.artifact["style_pattern"])
        self.assertIs(resolved.values["domain_context"], self.artifact["domain_extension"])
        self.assertIs(resolved.values["constraints"], self.artifact["risk_constraints"])

        with self.assertRaises(GenerationInputError):
            resolve_generation_input("not an artifact")

    def test_generation_request_carries_the_artifact_unchanged(self) -> None:
        adapter = RecordingGenerationAdapter()
        request = GenerationRequest(
            artifact=self.artifact,
            format_name="content_plan",
            constraints={"max_sections": 5},
        )

        adapter.generate(request)

        self.assertEqual(adapter.calls, 1)
        self.assertIs(adapter.requests[0].artifact, self.artifact)
        self.assertEqual(adapter.requests[0].format_name, "content_plan")
        self.assertEqual(adapter.requests[0].constraints, {"max_sections": 5})
        # Consuming the artifact must not mutate it.
        self.assertEqual(
            set(self.artifact),
            {
                "artifact_version",
                "plugin",
                *COMMON_FAMILIES,
                "domain_extension",
                "risk_constraints",
                "evaluation_result",
            },
        )


if __name__ == "__main__":
    unittest.main()
