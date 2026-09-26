from __future__ import annotations

import unittest
from pathlib import Path

from core import RawSource, SourceType, discover_skills, load_plugin
from distillation_core import DistillationEngine
from plugin_interface import PluginContribution, PluginIdentity
from workflows.content_distillation_pipeline import ContentDistillationPipeline


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ARTIFACT_FIELDS = {
    "topic_candidate",
    "content_template",
    "knowledge_unit",
    "style_pattern",
    "domain_extension",
    "risk_constraints",
    "evaluation_result",
}


class ReplacementEducationPlugin:
    """Test-only plugin proving that the common engine is domain-independent."""

    @property
    def identity(self) -> PluginIdentity:
        return PluginIdentity(
            name="replacement_education",
            version="1.0.0",
            domain="education",
            creator_target="general-learner",
        )

    def enhance(self, raw_sources, common_signals) -> PluginContribution:
        return PluginContribution(
            domain_extension={
                "schema_version": "1.0.0",
                "teaching_mode": "explain-and-check",
            },
            evaluation_result={"score": 1.0, "passed": True},
        )


class DistillationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.finance_plugin = load_plugin("plugins.xiaolin_finance")

    def test_ordinary_material_produces_unified_artifact(self) -> None:
        sources = [
            RawSource(
                source_id="doc-1",
                source_type=SourceType.DOCUMENT,
                content="Water changes state when temperature and pressure change.",
            )
        ]
        pipeline = ContentDistillationPipeline(
            DistillationEngine(ReplacementEducationPlugin())
        )

        result = pipeline.run(sources)

        self.assertTrue(REQUIRED_ARTIFACT_FIELDS.issubset(result.artifact))
        self.assertEqual(
            result.artifact["knowledge_unit"][0]["evidence_refs"][0]["source_id"],
            "doc-1",
        )
        self.assertEqual(result.artifact["artifact_version"], "1.0.0")
        self.assertIsNone(result.generated_output)
        self.assertEqual(result.quality_report["status"], "pass")

    def test_finance_plugin_applies_domain_enhancement(self) -> None:
        sources = [
            RawSource(
                source_id="finance-1",
                source_type=SourceType.DATA,
                content=(
                    "The company business model links subscription revenue to "
                    "cash flow and margin data."
                ),
            )
        ]

        artifact = DistillationEngine(self.finance_plugin).distill(sources)

        extension = artifact["domain_extension"]
        dimensions = {item["dimension"] for item in extension["value_signals"]}
        self.assertIn("business_mechanism", dimensions)
        self.assertIn("data_interpretation", dimensions)
        self.assertIn("company_case", dimensions)
        self.assertTrue(
            any(item["origin"] == "xiaolin_finance" for item in artifact["topic_candidate"])
        )
        self.assertTrue(artifact["evaluation_result"]["domain"]["passed"])

    def test_replacing_plugin_does_not_change_common_core(self) -> None:
        sources = [
            RawSource(
                source_id="science-1",
                source_type=SourceType.DOCUMENT,
                content="Photosynthesis converts light energy into chemical energy.",
            )
        ]

        finance_artifact = DistillationEngine(self.finance_plugin).distill(sources)
        replacement_artifact = DistillationEngine(ReplacementEducationPlugin()).distill(
            sources
        )

        self.assertEqual(
            finance_artifact["knowledge_unit"], replacement_artifact["knowledge_unit"]
        )
        self.assertEqual(finance_artifact["plugin"]["domain"], "finance")
        self.assertEqual(replacement_artifact["plugin"]["domain"], "education")
        self.assertEqual(
            replacement_artifact["domain_extension"]["teaching_mode"],
            "explain-and-check",
        )

    def test_finance_risk_blocks_automatic_progression(self) -> None:
        sources = [
            RawSource(
                source_id="risk-1",
                source_type=SourceType.DOCUMENT,
                content="Buy now for a guaranteed return.",
            )
        ]
        pipeline = ContentDistillationPipeline(DistillationEngine(self.finance_plugin))

        result = pipeline.run(sources)

        self.assertTrue(
            any(item["severity"] == "block" for item in result.artifact["risk_constraints"])
        )
        self.assertEqual(result.quality_report["status"], "review_required")


class SkillRegistryTests(unittest.TestCase):
    def test_skills_are_independently_discoverable_and_versioned(self) -> None:
        skills = discover_skills(WORKSPACE_ROOT / "skills")

        self.assertEqual(
            set(skills), {"source_ingestion", "unified_distillation", "quality_review"}
        )
        for manifest in skills.values():
            self.assertRegex(manifest.version, r"^\d+\.\d+\.\d+$")
            self.assertTrue((manifest.package_dir / manifest.entrypoint).is_file())
            self.assertTrue(manifest.test_command)


if __name__ == "__main__":
    unittest.main()
