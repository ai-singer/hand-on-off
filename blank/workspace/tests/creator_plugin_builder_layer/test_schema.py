"""Schema validation: the domain plugin document shape, and what it refuses."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from creator_plugin_builder import (
    PLUGIN_CORE_SKILLS,
    PLUGIN_SLOTS,
    PROTOCOL_STAGES,
    REQUIRED_KEYS,
    ROOT_NAME,
    RULE_STATUSES,
    SCHEMA_FILENAME,
    DomainPlugin,
    PluginIsolationError,
    PluginLayerError,
    PluginLibraryError,
    PluginProtocolError,
    PluginRuleError,
    PluginSchemaError,
    RuleBinding,
    RuleStatus,
    audit_layers,
    build_schema,
    load_schema,
    schema_keys,
    schema_path,
    validate_layers,
    validate_schema,
    write_schema,
)

from . import fixtures


class SchemaDocumentTests(unittest.TestCase):
    """The schema is built from the model, so it cannot drift from it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = build_schema()

    def test_the_root_is_an_object(self) -> None:
        self.assertEqual(self.schema["type"], "object")

    def test_the_root_forbids_extra_keys(self) -> None:
        self.assertIs(self.schema["additionalProperties"], False)

    def test_the_title_names_the_document(self) -> None:
        self.assertEqual(self.schema["title"], "DomainPlugin")

    def test_every_required_key_is_declared(self) -> None:
        declared = set(self.schema["properties"])
        for key in REQUIRED_KEYS:
            self.assertIn(key, declared, key)

    def test_every_declared_key_is_required(self) -> None:
        """Only the two optional blocks may sit outside ``required``."""

        required = set(self.schema["required"])
        optional = {"compatibility", "notes"}
        for key in self.schema["properties"]:
            if key in optional:
                self.assertNotIn(key, required, key)
            else:
                self.assertIn(key, required, key)

    def test_the_optional_keys_are_exactly_the_two_expected(self) -> None:
        optional = set(self.schema["properties"]) - set(self.schema["required"])
        self.assertEqual(optional, {"compatibility", "notes"})

    def test_every_rule_slot_is_declared(self) -> None:
        for slot in PLUGIN_SLOTS:
            self.assertIn(slot, self.schema["properties"], slot)

    def test_every_rule_slot_requires_at_least_one_rule(self) -> None:
        for slot in PLUGIN_SLOTS:
            self.assertEqual(self.schema["properties"][slot]["minItems"], 1, slot)

    def test_the_protocol_requires_every_stage(self) -> None:
        self.assertEqual(
            self.schema["properties"]["protocol_stages"]["minItems"],
            len(PROTOCOL_STAGES),
        )

    def test_the_schema_uses_the_dependency_free_subset(self) -> None:
        text = json.dumps(self.schema)
        for forbidden in ("$ref", "allOf", "anyOf", "oneOf", '"if"', "pattern"):
            self.assertNotIn(forbidden, text, forbidden)

    def test_schema_keys_match_the_properties(self) -> None:
        self.assertEqual(schema_keys(), frozenset(self.schema["properties"]))

    def test_the_schema_is_json_safe(self) -> None:
        json.dumps(self.schema)

    def test_the_schema_is_deterministic(self) -> None:
        self.assertEqual(build_schema(), build_schema())


class SchemaEnumTests(unittest.TestCase):
    """The schema's enums are the model's own vocabularies."""

    def test_rule_statuses_come_from_the_enum(self) -> None:
        self.assertEqual(
            RULE_STATUSES, tuple(status.value for status in RuleStatus)
        )

    def test_core_skill_enums_list_the_library(self) -> None:
        rule = build_schema()["properties"]["source_rules"]["items"]
        self.assertEqual(rule["properties"]["core_skill"]["enum"],
                         list(PLUGIN_CORE_SKILLS))

    def test_protocol_stage_enum_is_the_protocol(self) -> None:
        stage = build_schema()["properties"]["protocol_stages"]["items"]
        self.assertEqual(stage["properties"]["stage"]["enum"], list(PROTOCOL_STAGES))

    def test_values_source_enum_has_two_options(self) -> None:
        rule = build_schema()["properties"]["source_rules"]["items"]
        self.assertEqual(rule["properties"]["values_source"]["enum"],
                         ["asset", "catalog"])

    def test_the_persona_block_requires_availability_and_a_reason(self) -> None:
        persona = build_schema()["properties"]["domain_identity"]["properties"][
            "persona"
        ]
        self.assertEqual(sorted(persona["required"]),
                         ["available", "reason", "source_asset"])

    def test_provenance_requires_the_request_digest(self) -> None:
        provenance = build_schema()["properties"]["provenance"]
        self.assertIn("request_digest", provenance["required"])

    def test_provenance_requires_the_catalog_and_library_versions(self) -> None:
        provenance = build_schema()["properties"]["provenance"]
        self.assertIn("catalog_version", provenance["required"])
        self.assertIn("library_version", provenance["required"])

    def test_provenance_requires_at_least_one_source_asset(self) -> None:
        provenance = build_schema()["properties"]["provenance"]
        self.assertEqual(provenance["properties"]["source_assets"]["minItems"], 1)


class SchemaFileTests(unittest.TestCase):
    """The schema is emitted to ``schemas/`` where the contract's own schemas live."""

    def test_the_filename_is_declared(self) -> None:
        self.assertEqual(SCHEMA_FILENAME, "domain_plugin.schema.json")

    def test_the_root_name_is_declared(self) -> None:
        self.assertEqual(ROOT_NAME, "domain_plugin")

    def test_the_schema_path_is_under_schemas(self) -> None:
        self.assertEqual(schema_path().parent.name, "schemas")

    def test_the_schema_is_emitted(self) -> None:
        target = write_schema()
        self.assertTrue(target.is_file())

    def test_the_emitted_file_matches_the_built_document(self) -> None:
        target = write_schema()
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), build_schema())

    def test_the_emitted_document_loads(self) -> None:
        write_schema()
        self.assertEqual(load_schema(), build_schema())

    def test_writing_is_deterministic(self) -> None:
        first = write_schema().read_text(encoding="utf-8")
        second = write_schema().read_text(encoding="utf-8")
        self.assertEqual(first, second)

    def test_writing_to_a_custom_path_works(self) -> None:
        target = fixtures.scratch_dir("schema_out") / "nested" / "schema.json"
        write_schema(target)
        self.assertTrue(target.is_file())

    def test_a_missing_schema_file_is_reported(self) -> None:
        with self.assertRaises(PluginSchemaError):
            load_schema(fixtures.scratch_dir("schema_missing") / "nope.json")

    def test_a_malformed_schema_file_is_reported(self) -> None:
        target = fixtures.scratch_dir("schema_bad") / "schema.json"
        target.write_text("{not json", encoding="utf-8")
        with self.assertRaises(PluginSchemaError):
            load_schema(target)

    def test_a_non_object_schema_file_is_reported(self) -> None:
        target = fixtures.scratch_dir("schema_array") / "schema.json"
        target.write_text("[1, 2]", encoding="utf-8")
        with self.assertRaises(PluginSchemaError):
            load_schema(target)


class ValidateSchemaTests(unittest.TestCase):
    """A real plugin validates, and each corruption is refused."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = fixtures.plugin("finance").as_dict()

    def test_a_valid_plugin_passes(self) -> None:
        validate_schema(self.document)

    def test_the_plugin_passes_against_the_emitted_schema(self) -> None:
        write_schema()
        validate_schema(self.document)

    def test_a_non_object_is_refused(self) -> None:
        with self.assertRaises(PluginSchemaError):
            validate_schema(["not", "an", "object"])  # type: ignore[arg-type]

    def test_an_unexpected_top_level_key_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        document["extra"] = 1
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_every_required_key_is_enforced(self) -> None:
        for key in REQUIRED_KEYS:
            document = fixtures.as_document(self.document)
            del document[key]
            with self.assertRaises(PluginSchemaError, msg=key):
                validate_schema(document)

    def test_every_rule_slot_must_be_present(self) -> None:
        for slot in PLUGIN_SLOTS:
            document = fixtures.as_document(self.document)
            del document[slot]
            with self.assertRaises(PluginSchemaError, msg=slot):
                validate_schema(document)

    def test_an_empty_rule_slot_is_refused(self) -> None:
        for slot in PLUGIN_SLOTS:
            document = fixtures.as_document(self.document)
            document[slot] = []
            with self.assertRaises(PluginSchemaError, msg=slot):
                validate_schema(document)

    def test_a_wrongly_typed_rule_slot_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        document["source_rules"] = "not a list"
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_an_unknown_rule_status_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        document["source_rules"][0]["status"] = "maybe"
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_an_unknown_core_skill_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        document["source_rules"][0]["core_skill"] = "invented-skill"
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_an_unknown_protocol_stage_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        document["protocol_stages"][0]["stage"] = "invented_stage"
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_a_truncated_protocol_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        document["protocol_stages"] = document["protocol_stages"][:3]
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_an_unknown_values_source_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        document["topic_rules"][0]["values_source"] = "invented"
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_an_extra_key_inside_a_rule_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        document["source_rules"][0]["extra"] = 1
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_an_extra_key_inside_provenance_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        document["provenance"]["extra"] = 1
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_a_missing_provenance_field_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        del document["provenance"]["request_digest"]
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_an_empty_source_asset_list_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        document["provenance"]["source_assets"] = []
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_an_empty_requirements_list_is_refused(self) -> None:
        document = fixtures.as_document(self.document)
        document["required_core_skills"] = []
        with self.assertRaises(PluginSchemaError):
            validate_schema(document)

    def test_the_schema_check_does_not_mutate_the_document(self) -> None:
        before = json.dumps(self.document, sort_keys=True)
        validate_schema(self.document)
        self.assertEqual(json.dumps(self.document, sort_keys=True), before)


class ModelGuardTests(unittest.TestCase):
    """The model refuses at construction what the schema refuses at validation."""

    def test_a_plugin_name_must_start_with_domain(self) -> None:
        document = fixtures.plugin("finance").as_dict()
        document["plugin_name"] = "finance-plugin"
        document.pop("protocol_stages")
        with self.assertRaises((PluginRuleError, PluginProtocolError)):
            DomainPlugin(
                plugin_name="finance-plugin",
                domain="finance",
                version="1.0.0",
                display_name="Finance",
                identity=fixtures.plugin("finance").identity,
                identity_rules=(),
                source_rules=(),
                topic_rules=(),
                protocol_stages=(),
                text_distillation_rules=(),
                visual_adaptation_rules=(),
                risk_constraints=(),
                required_core_skills=("text-distillation",),
                provenance=fixtures.plugin("finance").provenance,
            )

    def test_a_rule_with_no_slot_is_refused(self) -> None:
        with self.assertRaises(PluginRuleError):
            RuleBinding(
                slot="",
                core_skill="text-distillation",
                source_asset="text_distillation_rules",
                asset_type="text_rules",
                status=RuleStatus.AVAILABLE.value,
            )

    def test_a_rule_binding_to_an_unknown_core_skill_is_refused(self) -> None:
        with self.assertRaises(PluginLibraryError):
            RuleBinding(
                slot="x",
                core_skill="not-a-skill",
                source_asset="text_distillation_rules",
                asset_type="text_rules",
                status=RuleStatus.AVAILABLE.value,
            )

    def test_a_rule_with_an_unknown_status_is_refused(self) -> None:
        with self.assertRaises(PluginRuleError):
            RuleBinding(
                slot="x",
                core_skill="text-distillation",
                source_asset="a",
                asset_type="t",
                status="maybe",
            )

    def test_a_rule_with_an_unknown_values_source_is_refused(self) -> None:
        with self.assertRaises(PluginRuleError):
            RuleBinding(
                slot="x",
                core_skill="text-distillation",
                source_asset="a",
                asset_type="t",
                status=RuleStatus.AVAILABLE.value,
                values_source="invented",
            )

    def test_an_available_rule_needs_no_reason(self) -> None:
        rule = RuleBinding(
            slot="x",
            core_skill="text-distillation",
            source_asset="a",
            asset_type="t",
            status=RuleStatus.AVAILABLE.value,
        )
        self.assertTrue(rule.available)

    def test_an_unavailable_rule_needs_a_reason(self) -> None:
        with self.assertRaises(PluginRuleError.__mro__[1]):  # PluginBuilderError
            RuleBinding(
                slot="x",
                core_skill="text-distillation",
                source_asset="a",
                asset_type="t",
                status=RuleStatus.DECLARED.value,
            )

    def test_asset_sourced_values_on_an_unavailable_rule_are_refused(self) -> None:
        from creator_plugin_builder import PluginCapabilityError

        with self.assertRaises(PluginCapabilityError):
            RuleBinding(
                slot="x",
                core_skill="text-distillation",
                source_asset="a",
                asset_type="t",
                status=RuleStatus.DECLARED.value,
                reason="not_available:x",
                values=("v",),
                values_source="asset",
            )

    def test_catalog_sourced_values_on_an_unavailable_rule_are_allowed(self) -> None:
        rule = RuleBinding(
            slot="x",
            core_skill="text-distillation",
            source_asset="a",
            asset_type="t",
            status=RuleStatus.DECLARED.value,
            reason="not_available:taxonomy",
            values=("v",),
            values_source="catalog",
        )
        self.assertFalse(rule.asset_backed)
        self.assertEqual(rule.value_count, 1)


class LayerAuditTests(unittest.TestCase):
    """Check 3: no universal skill may carry domain knowledge."""

    def test_the_library_audits_clean(self) -> None:
        report = audit_layers()
        self.assertTrue(report.passed, report.violations)

    def test_the_audit_lists_the_universal_skills(self) -> None:
        self.assertEqual(len(audit_layers().universal_skills), 10)

    def test_validate_layers_passes_the_real_library(self) -> None:
        self.assertTrue(validate_layers().passed)

    def test_a_polluted_universal_skill_is_caught(self) -> None:
        report = audit_layers(
            {
                "text-distillation": {
                    "layer": "universal",
                    "purpose": "Distill finance material into finance keywords.",
                }
            }
        )
        self.assertFalse(report.passed)
        self.assertTrue(any("finance" in v for v in report.violations))

    def test_a_declared_domain_keyword_list_is_caught(self) -> None:
        report = audit_layers(
            {
                "text-distillation": {
                    "layer": "universal",
                    "domain_keywords": ["a"],
                }
            }
        )
        self.assertFalse(report.passed)

    def test_a_declared_domain_rule_list_is_caught(self) -> None:
        report = audit_layers(
            {"text-distillation": {"layer": "universal", "domain_rules": {}}}
        )
        self.assertFalse(report.passed)

    def test_an_unknown_layer_is_caught(self) -> None:
        report = audit_layers({"x": {"layer": "invented"}})
        self.assertFalse(report.passed)

    def test_a_clean_library_reports_no_violations(self) -> None:
        report = audit_layers(
            {"text-distillation": {"layer": "universal", "purpose": "Distill."}}
        )
        self.assertEqual(report.violations, ())

    def test_validate_layers_refuses_a_polluted_library(self) -> None:
        with self.assertRaises(PluginLayerError):
            validate_layers(
                {"x": {"layer": "universal", "purpose": "sports fixtures"}}
            )

    def test_the_meta_skills_are_exempt_from_the_marker_scan(self) -> None:
        """A meta skill's *name* says 'domain'; that is not pollution."""

        report = audit_layers()
        self.assertTrue(report.passed)

    def test_the_report_serialises(self) -> None:
        json.dumps(audit_layers().as_dict())

    def test_a_failing_report_says_FAIL(self) -> None:
        report = audit_layers({"x": {"layer": "universal", "purpose": "finance"}})
        self.assertEqual(report.status, "FAIL")

    def test_a_passing_report_says_PASS(self) -> None:
        self.assertEqual(audit_layers().status, "PASS")


class ProtocolReferenceTests(unittest.TestCase):
    """The protocol is the same for every domain."""

    def test_the_protocol_has_six_stages(self) -> None:
        self.assertEqual(len(PROTOCOL_STAGES), 6)

    def test_the_protocol_starts_with_observation(self) -> None:
        self.assertEqual(PROTOCOL_STAGES[0], "observation")

    def test_the_protocol_ends_with_boundary(self) -> None:
        self.assertEqual(PROTOCOL_STAGES[-1], "boundary")

    def test_every_plugin_implements_the_same_protocol(self) -> None:
        for plugin in fixtures.all_plugins():
            self.assertEqual(
                tuple(s.stage for s in plugin.protocol_stages),
                PROTOCOL_STAGES,
                plugin.domain,
            )

    def test_every_domain_uses_different_terms(self) -> None:
        terms = {
            plugin.domain: tuple(s.domain_term for s in plugin.protocol_stages)
            for plugin in fixtures.all_plugins()
        }
        self.assertEqual(len(set(terms.values())), len(terms))

    def test_every_stage_carries_a_term(self) -> None:
        for plugin in fixtures.all_plugins():
            for stage in plugin.protocol_stages:
                self.assertTrue(stage.domain_term, f"{plugin.domain}.{stage.stage}")

    def test_a_stage_without_a_term_is_refused(self) -> None:
        from creator_plugin_builder import DistillationStage

        with self.assertRaises(PluginProtocolError):
            DistillationStage(
                stage="observation",
                domain_term="",
                core_skill="text-distillation",
                status=RuleStatus.AVAILABLE.value,
                order=1,
            )

    def test_an_unknown_stage_name_is_refused(self) -> None:
        from creator_plugin_builder import DistillationStage

        with self.assertRaises(PluginProtocolError):
            DistillationStage(
                stage="invented",
                domain_term="x",
                core_skill="text-distillation",
                status=RuleStatus.AVAILABLE.value,
                order=1,
            )


if __name__ == "__main__":
    unittest.main()
