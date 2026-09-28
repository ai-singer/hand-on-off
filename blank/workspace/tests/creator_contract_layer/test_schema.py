"""Schema conformance tests: 20+ cases over the eight instance modules."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy

from creator_contract import (
    CONTRACT_VERSION,
    CreatorContractError,
    load_contract_schema,
    minimal_instance,
    validate_schema,
)


class ContractSchemaDocumentTests(unittest.TestCase):
    """The schema file itself is well-formed and declares the full contract."""

    def test_schema_loads_as_an_object(self) -> None:
        schema = load_contract_schema()
        self.assertIsInstance(schema, dict)

    def test_schema_declares_the_eight_modules_plus_version(self) -> None:
        schema = load_contract_schema()
        self.assertEqual(
            sorted(schema["properties"]),
            sorted(
                [
                    "contract_version",
                    "identity",
                    "source",
                    "text_rules",
                    "visual_rules",
                    "risk_policy",
                    "generation",
                    "publishing",
                    "provenance",
                ]
            ),
        )

    def test_schema_requires_every_module(self) -> None:
        schema = load_contract_schema()
        self.assertEqual(len(schema["required"]), 9)

    def test_schema_is_sealed_at_the_root(self) -> None:
        schema = load_contract_schema()
        self.assertIs(schema["additionalProperties"], False)

    def test_schema_uses_only_the_dependency_free_subset(self) -> None:
        """No $ref/allOf/oneOf/if - the project validator cannot express them."""

        raw = json.dumps(load_contract_schema())
        for unsupported in ("\"$ref\"", "\"allOf\"", "\"oneOf\"", "\"if\""):
            self.assertNotIn(unsupported, raw)

    def test_contract_version_is_pinned_to_one_value(self) -> None:
        schema = load_contract_schema()
        self.assertEqual(
            schema["properties"]["contract_version"]["enum"], [CONTRACT_VERSION]
        )


class SchemaAcceptsValidInstancesTests(unittest.TestCase):
    """A conforming document passes."""

    def test_minimal_instance_passes(self) -> None:
        validate_schema(minimal_instance())

    def test_all_eight_module_files_are_present(self) -> None:
        instance = minimal_instance()
        for module in (
            "identity",
            "source",
            "text_rules",
            "visual_rules",
            "risk_policy",
            "generation",
            "publishing",
            "provenance",
        ):
            self.assertIn(module, instance)

    def test_a_sports_instance_passes(self) -> None:
        validate_schema(minimal_instance(domain="sports", creator_id="sports-xia"))

    def test_a_tech_instance_passes(self) -> None:
        validate_schema(minimal_instance(domain="tech", creator_id="tech-xia"))

    def test_a_general_instance_passes(self) -> None:
        validate_schema(minimal_instance(domain="general", creator_id="general-xia"))

    def test_an_instance_with_extra_hierarchy_tiers_passes(self) -> None:
        instance = minimal_instance()
        instance["visual_rules"]["hierarchy"] = {
            "primary": "hook",
            "secondary": "proof",
        }
        validate_schema(instance)

    def test_an_instance_with_zero_forbidden_layouts_passes(self) -> None:
        instance = minimal_instance()
        instance["visual_rules"]["composition"]["forbidden_layout"] = []
        validate_schema(instance)

    def test_an_instance_with_empty_avoid_list_passes(self) -> None:
        instance = minimal_instance()
        instance["visual_rules"]["constraints"]["avoid"] = []
        validate_schema(instance)


class SchemaRejectsStructuralDefectsTests(unittest.TestCase):
    """Every required module, and the version, is enforced."""

    def test_missing_module_is_rejected(self) -> None:
        instance = minimal_instance()
        del instance["identity"]
        with self.assertRaises(CreatorContractError) as ctx:
            validate_schema(instance)
        self.assertIn("identity", str(ctx.exception))

    def test_missing_risk_policy_is_rejected(self) -> None:
        instance = minimal_instance()
        del instance["risk_policy"]
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_missing_visual_rules_is_rejected(self) -> None:
        instance = minimal_instance()
        del instance["visual_rules"]
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_missing_publishing_is_rejected(self) -> None:
        instance = minimal_instance()
        del instance["publishing"]
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_wrong_contract_version_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["contract_version"] = "2.0.0"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unknown_root_module_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["runtime"] = {"anything": True}
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unknown_identity_field_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["identity"]["secret_sauce"] = "x"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unknown_domain_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["identity"]["domain"] = "astrology"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unknown_platform_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["identity"]["platform"] = "myspace"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unknown_language_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["identity"]["language"] = "fr"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_identity_creator_id_must_be_a_string(self) -> None:
        instance = minimal_instance()
        instance["identity"]["creator_id"] = 123
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_mental_models_must_be_a_non_empty_array(self) -> None:
        instance = minimal_instance()
        instance["identity"]["persona"]["mental_models"] = []
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_mental_models_must_be_objects(self) -> None:
        instance = minimal_instance()
        instance["identity"]["persona"]["mental_models"] = ["a string"]
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_uncertainty_in_severity_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"]["risk_categories"][0]["severity"] = "critical"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unknown_risk_action_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"]["risk_categories"][0]["action"] = "ignore"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unknown_generation_input_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["generation"]["input"] = ["topic", "vibes"]
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_quality_gate_must_require_pass(self) -> None:
        instance = minimal_instance()
        instance["generation"]["quality_gate"]["required_decision"] = "FAIL"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unsupported_aspect_ratio_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["publishing"]["image_requirement"]["aspect_ratio"] = "3:2"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unsupported_publishing_platform_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["publishing"]["platform"] = "carrier_pigeon"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unsupported_retry_policy_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["publishing"]["api"]["retry_policy"] = "forever"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unsupported_schedule_mode_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["publishing"]["schedule"]["mode"] = "whenever"
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_unknown_text_length_key_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["text_rules"]["length"]["target"] = 500
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_empty_title_formula_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["text_rules"]["title_formula"] = []
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_empty_keywords_are_rejected(self) -> None:
        instance = minimal_instance()
        instance["source"]["keywords"] = []
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_empty_reference_creators_are_rejected(self) -> None:
        instance = minimal_instance()
        instance["source"]["reference_creators"] = []
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_empty_data_sources_are_rejected(self) -> None:
        instance = minimal_instance()
        instance["source"]["data_sources"] = []
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_provenance_must_be_present(self) -> None:
        instance = minimal_instance()
        del instance["provenance"]
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_provenance_must_cover_every_module(self) -> None:
        instance = minimal_instance()
        del instance["provenance"]["risk_policy"]
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)

    def test_non_mapping_instance_is_rejected(self) -> None:
        with self.assertRaises(CreatorContractError):
            validate_schema(["not", "an", "object"])  # type: ignore[arg-type]

    def test_rejection_does_not_mutate_the_input(self) -> None:
        instance = minimal_instance()
        original = deepcopy(instance)
        del instance["identity"]
        with self.assertRaises(CreatorContractError):
            validate_schema(instance)
        self.assertNotIn("identity", instance)
        self.assertEqual(len(original), 9)


if __name__ == "__main__":
    unittest.main()
