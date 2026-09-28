"""Validation tests: dependency, isolation, and the combined entry point."""

from __future__ import annotations

import copy
import unittest

from creator_contract import (
    ISOLATION_FORBIDDEN_KEYS,
    ISOLATION_FORBIDDEN_MODULES,
    PROMPT_FORBIDDEN_KEYS,
    CreatorContractDependencyError,
    CreatorContractError,
    CreatorContractIsolationError,
    IsolationReport,
    assert_no_generation_prompt,
    assert_no_runtime_code,
    assert_provenance_complete,
    assert_risk_policy_not_empty,
    assert_visual_rules_reference_only,
    minimal_instance,
    validate,
    validate_dependencies,
    validate_isolation,
)


class DependencyValidationTests(unittest.TestCase):
    """Cross-module references must resolve."""

    def test_minimal_instance_resolves(self) -> None:
        validate_dependencies(minimal_instance())

    def test_blank_creator_id_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["identity"]["creator_id"] = "   "
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_duplicate_mental_model_ids_are_rejected(self) -> None:
        instance = minimal_instance()
        models = instance["identity"]["persona"]["mental_models"]
        models[1]["model_id"] = models[0]["model_id"]
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_mental_model_without_id_is_rejected(self) -> None:
        instance = minimal_instance()
        del instance["identity"]["persona"]["mental_models"][0]["model_id"]
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_unverified_reference_creator_is_rejected(self) -> None:
        """The collection precondition: an unverified user_id must not be used."""

        instance = minimal_instance()
        instance["source"]["reference_creators"][0]["identity_verified"] = False
        with self.assertRaises(CreatorContractDependencyError) as ctx:
            validate_dependencies(instance)
        self.assertIn("identity-verified", str(ctx.exception))

    def test_missing_evidence_layer_is_rejected(self) -> None:
        """Discovery-layer social material may not be the factual basis."""

        instance = minimal_instance()
        for source in instance["source"]["data_sources"]:
            source["layer"] = "discovery"
        with self.assertRaises(CreatorContractDependencyError) as ctx:
            validate_dependencies(instance)
        self.assertIn("evidence", str(ctx.exception))

    def test_blocked_pattern_referencing_unknown_category_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"]["blocked_patterns"][0]["category_id"] = "ghost_category"
        with self.assertRaises(CreatorContractDependencyError) as ctx:
            validate_dependencies(instance)
        self.assertIn("ghost_category", str(ctx.exception))

    def test_duplicate_risk_category_ids_are_rejected(self) -> None:
        instance = minimal_instance()
        categories = instance["risk_policy"]["risk_categories"]
        categories[1]["category_id"] = categories[0]["category_id"]
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_review_rule_without_when_is_rejected(self) -> None:
        instance = minimal_instance()
        del instance["risk_policy"]["review_rules"][0]["when"]
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_missing_knowledge_boundary_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["text_rules"]["knowledge_boundary"] = []
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_blank_visual_profile_id_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["visual_rules"]["profile_id"] = ""
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_blank_visual_profile_version_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["visual_rules"]["profile_version"] = ""
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_empty_preferred_layout_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["visual_rules"]["composition"]["preferred_layout"] = []
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_missing_visual_provenance_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["visual_rules"]["provenance"] = {}
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_gate_that_does_not_require_pass_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["generation"]["quality_gate"]["required_decision"] = "FAIL"
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_missing_adapter_ref_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["generation"]["adapter_ref"] = ""
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_publishing_without_idempotency_key_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["publishing"]["api"]["idempotency_key"] = ""
        with self.assertRaises(CreatorContractDependencyError) as ctx:
            validate_dependencies(instance)
        self.assertIn("idempotency", str(ctx.exception))

    def test_unsupported_aspect_ratio_is_rejected_by_dependencies(self) -> None:
        instance = minimal_instance()
        instance["publishing"]["image_requirement"]["aspect_ratio"] = "3:2"
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_provenance_entry_without_source_is_rejected(self) -> None:
        instance = minimal_instance()
        instance["provenance"]["identity"]["source"] = ""
        with self.assertRaises(CreatorContractDependencyError):
            validate_dependencies(instance)

    def test_provenance_completeness_helper_accepts_a_valid_instance(self) -> None:
        assert_provenance_complete(minimal_instance())

    def test_provenance_completeness_helper_names_the_missing_module(self) -> None:
        instance = minimal_instance()
        del instance["provenance"]["generation"]
        with self.assertRaises(CreatorContractDependencyError) as ctx:
            assert_provenance_complete(instance)
        self.assertIn("generation", str(ctx.exception))


class IsolationTests(unittest.TestCase):
    """An instance is configuration, never runtime."""

    def test_minimal_instance_is_isolation_clean(self) -> None:
        assert_no_runtime_code(minimal_instance())

    def test_visual_rules_are_reference_only(self) -> None:
        assert_no_generation_prompt(minimal_instance()["visual_rules"])

    def test_risk_policy_is_not_empty(self) -> None:
        assert_risk_policy_not_empty(minimal_instance())

    def test_empty_risk_categories_are_rejected(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"]["risk_categories"] = []
        with self.assertRaises(CreatorContractDependencyError):
            assert_risk_policy_not_empty(instance)

    def test_empty_review_rules_are_rejected(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"]["review_rules"] = []
        with self.assertRaises(CreatorContractDependencyError):
            assert_risk_policy_not_empty(instance)

    def test_empty_blocked_patterns_are_rejected(self) -> None:
        instance = minimal_instance()
        instance["risk_policy"]["blocked_patterns"] = []
        with self.assertRaises(CreatorContractDependencyError):
            assert_risk_policy_not_empty(instance)

    def test_every_isolation_forbidden_key_is_actually_rejected(self) -> None:
        """The policy tuple is not decorative: each entry must bite."""

        for key in ISOLATION_FORBIDDEN_KEYS:
            with self.subTest(key=key):
                instance = minimal_instance()
                instance["text_rules"]["tone"][key] = "anything"
                with self.assertRaises(CreatorContractIsolationError):
                    assert_no_runtime_code(instance)

    def test_a_forbidden_key_nested_deeply_is_still_caught(self) -> None:
        instance = minimal_instance()
        instance["identity"]["persona"]["mental_models"][0]["script"] = "print(1)"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_runtime_code(instance)

    def test_python_source_in_a_string_is_caught(self) -> None:
        instance = minimal_instance()
        instance["text_rules"]["tone"]["voice"] = "def build():\n    return 1"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_runtime_code(instance)

    def test_import_statement_in_a_string_is_caught(self) -> None:
        instance = minimal_instance()
        instance["text_rules"]["tone"]["voice"] = "import subprocess"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_runtime_code(instance)

    def test_http_client_in_a_string_is_caught(self) -> None:
        instance = minimal_instance()
        instance["source"]["data_sources"][1]["locator"] = "requests.get(url)"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_runtime_code(instance)

    def test_playwright_in_a_string_is_caught(self):
        instance = minimal_instance()
        instance["source"]["collection_rules"]["dedupe_by"] = "playwright session"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_runtime_code(instance)

    def test_runtime_module_reference_is_caught(self) -> None:
        for module in ISOLATION_FORBIDDEN_MODULES:
            with self.subTest(module=module):
                instance = minimal_instance()
                instance["generation"]["adapter_ref"] = f"{module}.engine"
                with self.assertRaises(CreatorContractIsolationError):
                    assert_no_runtime_code(instance)

    def test_a_legitimate_https_locator_is_not_flagged(self) -> None:
        """False positives would make the check useless in practice."""

        instance = minimal_instance()
        instance["source"]["data_sources"][1]["locator"] = "https://www.stats.gov.cn/"
        assert_no_runtime_code(instance)

    def test_ordinary_prose_containing_from_is_not_flagged(self) -> None:
        instance = minimal_instance()
        instance["identity"]["persona"]["honest_boundaries"][0] = (
            "projected from the blank template"
        )
        assert_no_runtime_code(instance)

    def test_visual_rules_may_not_carry_any_prompt_key(self) -> None:
        for key in PROMPT_FORBIDDEN_KEYS:
            with self.subTest(key=key):
                visual_rules = copy.deepcopy(minimal_instance()["visual_rules"])
                visual_rules[key] = "value"
                with self.assertRaises(CreatorContractIsolationError):
                    assert_no_generation_prompt(visual_rules)

    def test_visual_rules_may_not_carry_an_image_prompt_as_content(self) -> None:
        visual_rules = copy.deepcopy(minimal_instance()["visual_rules"])
        visual_rules["visual_language"] = "create image of a rocket launch"
        with self.assertRaises(CreatorContractIsolationError) as ctx:
            assert_no_generation_prompt(visual_rules)
        self.assertIn("prompt", str(ctx.exception).lower())

    def test_text_to_image_phrase_is_caught(self) -> None:
        visual_rules = copy.deepcopy(minimal_instance()["visual_rules"])
        visual_rules["visual_language"] = "text-to-image friendly"
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_generation_prompt(visual_rules)

    def test_non_mapping_visual_rules_are_rejected(self) -> None:
        with self.assertRaises(CreatorContractIsolationError):
            assert_no_generation_prompt(["not", "a", "mapping"])  # type: ignore[arg-type]


class VisualReferenceConsistencyTests(unittest.TestCase):
    """visual_rules must agree with the M5 profile it references."""

    def setUp(self) -> None:
        from creator_contract.authoring import REFERENCE_VISUAL_PROFILE

        self.profile = copy.deepcopy(REFERENCE_VISUAL_PROFILE)

    def test_matching_reference_passes(self) -> None:
        assert_visual_rules_reference_only(
            minimal_instance()["visual_rules"], self.profile
        )

    def test_profile_id_mismatch_is_rejected(self) -> None:
        visual_rules = copy.deepcopy(minimal_instance()["visual_rules"])
        visual_rules["profile_id"] = "vcp-different"
        with self.assertRaises(CreatorContractDependencyError):
            assert_visual_rules_reference_only(visual_rules, self.profile)

    def test_profile_version_mismatch_is_rejected(self) -> None:
        visual_rules = copy.deepcopy(minimal_instance()["visual_rules"])
        visual_rules["profile_version"] = "m4.0.0"
        with self.assertRaises(CreatorContractDependencyError):
            assert_visual_rules_reference_only(visual_rules, self.profile)

    def test_visual_language_mismatch_is_rejected(self) -> None:
        visual_rules = copy.deepcopy(minimal_instance()["visual_rules"])
        visual_rules["visual_language"] = "cinematic"
        with self.assertRaises(CreatorContractDependencyError):
            assert_visual_rules_reference_only(visual_rules, self.profile)

    def test_composition_mismatch_is_rejected(self) -> None:
        visual_rules = copy.deepcopy(minimal_instance()["visual_rules"])
        visual_rules["composition"]["preferred_layout"] = ["not_top_entry"]
        with self.assertRaises(CreatorContractDependencyError):
            assert_visual_rules_reference_only(visual_rules, self.profile)

    def test_profile_without_envelope_is_rejected(self) -> None:
        with self.assertRaises(CreatorContractDependencyError):
            assert_visual_rules_reference_only(
                minimal_instance()["visual_rules"], {"nothing": True}
            )


class CombinedValidationTests(unittest.TestCase):
    """The entry point reports all three checks."""

    def test_validate_returns_a_passing_report(self) -> None:
        report = validate(minimal_instance())
        self.assertIsInstance(report, IsolationReport)
        self.assertTrue(report.passed)
        self.assertEqual(report.status, "PASS")

    def test_report_records_all_four_checks(self) -> None:
        report = validate(minimal_instance())
        self.assertEqual(
            sorted(report.checks),
            ["capability_declaration", "dependencies", "isolation", "schema"],
        )
        self.assertTrue(all(value == "PASS" for value in report.checks.values()))

    def test_report_records_the_contract_version(self) -> None:
        report = validate(minimal_instance())
        self.assertEqual(report.contract_version, "1.0.0")

    def test_report_lists_the_provenance_modules(self) -> None:
        report = validate(minimal_instance())
        self.assertEqual(len(report.provenance_modules), 8)

    def test_report_is_json_serialisable(self) -> None:
        import json

        report = validate(minimal_instance())
        json.dumps(report.as_dict())

    def test_schema_failure_is_reported_before_isolation(self) -> None:
        instance = minimal_instance()
        instance["contract_version"] = "9.9.9"
        with self.assertRaises(CreatorContractError):
            validate(instance)

    def test_isolation_failure_is_raised_by_validate(self) -> None:
        instance = minimal_instance()
        instance["generation"]["adapter_ref"] = "import requests"
        with self.assertRaises(CreatorContractIsolationError):
            validate(instance)

    def test_dependency_failure_is_raised_by_validate(self) -> None:
        instance = minimal_instance()
        instance["publishing"]["api"]["idempotency_key"] = ""
        with self.assertRaises(CreatorContractDependencyError):
            validate(instance)

    def test_validate_accepts_a_visual_profile_for_reference_checking(self) -> None:
        from creator_contract.authoring import REFERENCE_VISUAL_PROFILE

        report = validate(minimal_instance(), visual_profile=REFERENCE_VISUAL_PROFILE)
        self.assertTrue(report.passed)

    def test_validate_rejects_a_divergent_visual_profile(self) -> None:
        divergent = {
            "visual_profile": {
                "profile_id": "vcp-other",
                "profile_version": "m5.0.0",
            }
        }
        with self.assertRaises(CreatorContractDependencyError):
            validate(minimal_instance(), visual_profile=divergent)

    def test_isolation_helper_accepts_a_valid_instance(self) -> None:
        validate_isolation(minimal_instance())


if __name__ == "__main__":
    unittest.main()
