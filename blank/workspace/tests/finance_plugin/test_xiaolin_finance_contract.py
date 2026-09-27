from __future__ import annotations

import json
import unittest
from pathlib import Path

from core import RawSource, SourceType, load_plugin
from core.schema_validation import validate_schema_instance
from distillation_core import DistillationEngine
from plugin_interface import PluginContribution, PluginIdentity
from schema_validation import validate_runtime_schemas
from workflows.content_distillation_pipeline import ContentDistillationPipeline


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = WORKSPACE_ROOT / "plugins" / "xiaolin_finance"
PLUGIN_MANIFEST_PATH = PLUGIN_ROOT / "plugin.json"
DOMAIN_SCHEMA_PATH = PLUGIN_ROOT / "schemas" / "domain_extension.schema.json"
SHARED_SCHEMA_PATH = WORKSPACE_ROOT / "schemas" / "unified_distillation_artifact.json"

FINANCE_SOURCE = RawSource(
    source_id="finance-1",
    source_type=SourceType.DATA,
    content=(
        "The company business model links subscription revenue to "
        "cash flow and margin data."
    ),
)
ADVICE_SOURCE = RawSource(
    source_id="advice-1",
    source_type=SourceType.DOCUMENT,
    content="Buy now for a guaranteed return.",
)
PREDICTION_SOURCE = RawSource(
    source_id="prediction-1",
    source_type=SourceType.DOCUMENT,
    content="The share price will definitely rise next quarter.",
)


class DomainFreePlugin:
    """Contributes nothing, so common output can be compared against it."""

    @property
    def identity(self) -> PluginIdentity:
        return PluginIdentity(
            name="domain_free",
            version="1.0.0",
            domain="none",
            creator_target="none",
        )

    def enhance(self, raw_sources, common_signals) -> PluginContribution:
        return PluginContribution(
            domain_extension={},
            evaluation_result={"score": 1.0, "passed": True},
        )


class RecordingGenerationAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return {"status": "generated", "format": request.format_name}


def _manifest() -> dict:
    return json.loads(PLUGIN_MANIFEST_PATH.read_text(encoding="utf-8"))


def _plugin_json(relative: str):
    return json.loads((PLUGIN_ROOT / relative).read_text(encoding="utf-8"))


class FinancePluginSchemaTests(unittest.TestCase):
    """Test 1 - the plugin schema and its declaration are valid and aligned."""

    def setUp(self) -> None:
        self.plugin = load_plugin("plugins.xiaolin_finance")
        self.manifest = _manifest()

    def test_manifest_agrees_with_runtime_identity(self) -> None:
        declared = self.manifest["plugin"]

        self.assertEqual(declared["name"], self.plugin.identity.name)
        self.assertEqual(declared["version"], self.plugin.identity.version)
        self.assertEqual(declared["domain"], self.plugin.identity.domain)
        self.assertEqual(
            declared["creator_target"], self.plugin.identity.creator_target
        )

    def test_manifest_declared_files_exist(self) -> None:
        for key in ("value", "filter", "structure"):
            self.assertTrue(
                (PLUGIN_ROOT / self.manifest["rules"][key]).is_file(),
                key,
            )
        self.assertTrue(
            (PLUGIN_ROOT / self.manifest["domain_schema"]["path"]).is_file()
        )
        self.assertTrue((PLUGIN_ROOT / self.manifest["evaluation"]["path"]).is_file())

    def test_domain_extension_matches_private_schema(self) -> None:
        artifact = DistillationEngine(self.plugin).distill([FINANCE_SOURCE])
        extension = artifact["domain_extension"]

        validate_schema_instance(
            extension, DOMAIN_SCHEMA_PATH, root_name="domain_extension"
        )

        self.assertEqual(
            extension["schema_version"], self.manifest["domain_schema"]["version"]
        )
        for section in self.manifest["distills"]:
            self.assertIn(section, extension)
            self.assertIn("matched", extension[section])

    def test_declared_taxonomy_matches_the_rule_files(self) -> None:
        value_rules = _plugin_json("rules/value_rules.json")
        filter_rules = _plugin_json("rules/filter_rules.json")

        self.assertEqual(
            {rule["section"] for rule in value_rules["rules"]},
            set(self.manifest["distills"]),
        )
        self.assertEqual(
            {rule["category"] for rule in filter_rules["rules"]},
            set(self.manifest["prohibits"]),
        )
        for rule in value_rules["rules"]:
            self.assertIn(rule["section"], value_rules["sections"])


class FinancePluginEnhancementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = load_plugin("plugins.xiaolin_finance")

    # Test 2 - finance input is enhanced
    def test_finance_input_produces_domain_enhancement(self) -> None:
        artifact = DistillationEngine(self.plugin).distill([FINANCE_SOURCE])
        extension = artifact["domain_extension"]

        matched = [name for name in _manifest()["distills"] if extension[name]["matched"]]
        self.assertIn("business_mechanism", matched)
        self.assertIn("data_expression_pattern", matched)
        self.assertTrue(extension["business_mechanism"]["source_ids"])
        self.assertTrue(
            any(
                item["origin"] == "xiaolin_finance"
                for item in artifact["topic_candidate"]
            )
        )
        self.assertTrue(artifact["evaluation_result"]["domain"]["passed"])
        self.assertTrue(
            artifact["domain_extension"]["recommended_structure"]["sections"]
        )

    def test_sources_are_classified_by_the_role_they_played(self) -> None:
        artifact = DistillationEngine(self.plugin).distill([FINANCE_SOURCE])
        classified = artifact["domain_extension"]["source_classification"]

        self.assertEqual(len(classified), 1)
        entry = classified[0]
        self.assertEqual(entry["source_id"], "finance-1")
        self.assertTrue(entry["roles"])
        self.assertTrue(entry["artifact_fields"])
        for role in entry["roles"]:
            self.assertIn(
                role,
                {"topic_source", "knowledge_source", "structure_source", "style_source"},
            )

    def test_evaluation_reports_inherited_and_finance_checks(self) -> None:
        artifact = DistillationEngine(self.plugin).distill([FINANCE_SOURCE])
        domain = artifact["evaluation_result"]["domain"]

        self.assertEqual(
            set(domain["inherited_checks"]),
            {"performance", "structure_quality", "transferability"},
        )
        self.assertEqual(
            set(domain["finance_checks"]),
            {"data_credibility", "explanation_completeness", "risk_boundary"},
        )
        for check in {**domain["inherited_checks"], **domain["finance_checks"]}.values():
            self.assertGreaterEqual(check["score"], 0.0)
            self.assertLessEqual(check["score"], 1.0)

    def test_plugin_is_deterministic(self) -> None:
        first = DistillationEngine(self.plugin).distill([FINANCE_SOURCE])
        second = DistillationEngine(self.plugin).distill([FINANCE_SOURCE])

        self.assertEqual(first["domain_extension"], second["domain_extension"])
        self.assertEqual(first["evaluation_result"], second["evaluation_result"])


class FinancePluginProhibitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = load_plugin("plugins.xiaolin_finance")

    # Test 3 - investment advice is blocked
    def test_investment_advice_is_blocked(self) -> None:
        artifact = DistillationEngine(self.plugin).distill([ADVICE_SOURCE])
        blocking = [
            item for item in artifact["risk_constraints"] if item["severity"] == "block"
        ]

        self.assertTrue(blocking)
        self.assertIn("finance.investment-advice", {item["rule_id"] for item in blocking})
        self.assertFalse(artifact["evaluation_result"]["domain"]["passed"])
        self.assertEqual(
            artifact["evaluation_result"]["domain"]["finance_checks"]["risk_boundary"][
                "score"
            ],
            0.0,
        )

    def test_investment_advice_stops_before_generation(self) -> None:
        adapter = RecordingGenerationAdapter()
        pipeline = ContentDistillationPipeline(
            DistillationEngine(self.plugin), adapter
        )

        result = pipeline.run([ADVICE_SOURCE])

        self.assertEqual(result.quality_report["status"], "review_required")
        self.assertEqual(adapter.calls, 0)

    # Test 4 - unsupported prediction is blocked
    def test_unsupported_prediction_requires_evidence(self) -> None:
        artifact = DistillationEngine(self.plugin).distill([PREDICTION_SOURCE])
        risks = {item["rule_id"]: item for item in artifact["risk_constraints"]}

        self.assertIn("finance.unsupported-prediction", risks)
        self.assertEqual(risks["finance.unsupported-prediction"]["severity"], "warning")
        self.assertEqual(
            risks["finance.unsupported-prediction"]["action"], "require_evidence"
        )

    def test_unsupported_prediction_stops_before_generation(self) -> None:
        adapter = RecordingGenerationAdapter()
        pipeline = ContentDistillationPipeline(
            DistillationEngine(self.plugin), adapter
        )

        result = pipeline.run([PREDICTION_SOURCE])

        self.assertEqual(result.quality_report["status"], "review_required")
        self.assertEqual(adapter.calls, 0)

    def test_every_prohibited_category_has_a_rule(self) -> None:
        filter_rules = _plugin_json("rules/filter_rules.json")
        declared = set(_manifest()["prohibits"])

        self.assertEqual(declared, set(filter_rules["prohibited_categories"]))
        for rule in filter_rules["rules"]:
            self.assertIn(rule["severity"], {"info", "warning", "block"})
            self.assertIn(
                rule["action"],
                {"downrank", "require_evidence", "require_review", "block"},
            )


class FinancePluginArtifactCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plugin = load_plugin("plugins.xiaolin_finance")

    # Test 5 - the shared artifact contract is preserved
    def test_artifact_remains_compatible_with_the_shared_schema(self) -> None:
        artifact = DistillationEngine(self.plugin).distill([FINANCE_SOURCE])

        validate_schema_instance(artifact, SHARED_SCHEMA_PATH, root_name="artifact")
        validation = validate_runtime_schemas(
            artifact,
            plugin=self.plugin,
            shared_schema_path=SHARED_SCHEMA_PATH,
        )

        self.assertEqual(validation.status, "PASS")
        self.assertTrue(validation.domain_schema_applied)
        self.assertEqual(artifact["artifact_version"], "1.0.0")
        for field in (
            "topic_candidate",
            "content_template",
            "knowledge_unit",
            "style_pattern",
            "domain_extension",
            "risk_constraints",
            "evaluation_result",
        ):
            self.assertIn(field, artifact)

    # Test 6 - the plugin cannot modify the common core
    def test_plugin_only_appends_and_never_rewrites_common_output(self) -> None:
        plain = DistillationEngine(DomainFreePlugin()).distill([FINANCE_SOURCE])
        enhanced = DistillationEngine(self.plugin).distill([FINANCE_SOURCE])

        for field in ("knowledge_unit", "content_template", "style_pattern"):
            self.assertEqual(enhanced[field], plain[field], field)

        common_topics = len(plain["topic_candidate"])
        self.assertEqual(
            enhanced["topic_candidate"][:common_topics], plain["topic_candidate"]
        )
        self.assertGreater(len(enhanced["topic_candidate"]), common_topics)
        self.assertEqual(enhanced["artifact_version"], plain["artifact_version"])

    def test_replacing_the_plugin_changes_only_the_domain_layer(self) -> None:
        plain = DistillationEngine(DomainFreePlugin()).distill([FINANCE_SOURCE])
        enhanced = DistillationEngine(self.plugin).distill([FINANCE_SOURCE])

        self.assertEqual(plain["domain_extension"], {})
        self.assertEqual(enhanced["plugin"]["domain"], "finance")
        self.assertEqual(plain["plugin"]["domain"], "none")

        # The common evaluation runs over the merged artifact, so appending topic
        # candidates legitimately raises its populated-family count. What must not
        # change is the underlying source coverage the plugin did not touch.
        plain_common = plain["evaluation_result"]["common"]["checks"]
        enhanced_common = enhanced["evaluation_result"]["common"]["checks"]
        self.assertEqual(
            enhanced_common["source_reference_coverage"],
            plain_common["source_reference_coverage"],
        )
        self.assertGreaterEqual(
            enhanced_common["populated_signal_families"],
            plain_common["populated_signal_families"],
        )


if __name__ == "__main__":
    unittest.main()
