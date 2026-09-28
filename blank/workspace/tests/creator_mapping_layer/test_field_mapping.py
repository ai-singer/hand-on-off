"""Field mapping: one module at a time, field by field."""

from __future__ import annotations

import unittest
from pathlib import Path

from creator_mapping import (
    FIELD_RULES,
    MAPPED_MODULES,
    REQUIRED_PATHS,
    BundleAssetResolver,
    map_bundle_to_instance,
)
from creator_skill import (
    CreatorRequest,
    DEFAULT_SKILL_CATALOG,
    SkillComposer,
    SkillRegistry,
)

WORKSPACE = Path(__file__).resolve().parents[2]


def _mapped():
    registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
    from creator_projection import AssetRegistry

    resolver = BundleAssetResolver(AssetRegistry.load(WORKSPACE), registry)
    bundle = SkillComposer(registry).compose(
        CreatorRequest(
            domain="finance",
            platform="xiaohongshu",
            style="education",
            creator_id="finance_xhs",
            declared_capabilities=("visual-style-distillation",),
        )
    ).bundle
    return bundle, map_bundle_to_instance(bundle, resolver=resolver)


class ModulePresenceTests(unittest.TestCase):
    """Every mapped module is present and carries every required field."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle, cls.mapped = _mapped()

    def test_all_seven_modules_present(self) -> None:
        for module in MAPPED_MODULES:
            with self.subTest(module=module):
                self.assertIn(module, self.mapped.instance)

    def test_every_module_carries_its_required_fields(self) -> None:
        for module in MAPPED_MODULES:
            document = self.mapped.instance[module]
            for path in REQUIRED_PATHS[module]:
                with self.subTest(module=module, path=path):
                    self.assertIn(path, document)

    def test_provenance_block_is_present(self) -> None:
        self.assertIn("provenance", self.mapped.instance)

    def test_provenance_names_generated_by(self) -> None:
        generated_by = self.mapped.instance["provenance"]["generated_by"]
        self.assertIn("creator_mapping", generated_by)
        self.assertIn(self.bundle.bundle_id, generated_by)


class IdentityMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bundle, cls.mapped = _mapped()
        cls.identity = cls.mapped.instance["identity"]

    def test_creator_id(self) -> None:
        self.assertEqual(self.identity["creator_id"], "finance_xhs")

    def test_name_is_derived_from_the_creator_id(self) -> None:
        self.assertEqual(self.identity["name"], "Finance Xhs")

    def test_domain_comes_from_the_request(self) -> None:
        self.assertEqual(self.identity["domain"], "finance")

    def test_platform_comes_from_the_request(self) -> None:
        self.assertEqual(self.identity["platform"], "xiaohongshu")

    def test_language_is_chinese_for_a_chinese_platform(self) -> None:
        self.assertEqual(self.identity["language"], "zh")

    def test_persona_has_mental_models(self) -> None:
        models = self.identity["persona"]["mental_models"]
        self.assertEqual(len(models), 5)

    def test_persona_models_come_from_the_domain_sections(self) -> None:
        ids = [m["model_id"] for m in self.identity["persona"]["mental_models"]]
        self.assertIn("business_mechanism", ids)

    def test_persona_models_carry_a_failure_condition(self) -> None:
        for model in self.identity["persona"]["mental_models"]:
            self.assertTrue(model["failure_condition"])

    def test_persona_mode_is_reasoning_model(self) -> None:
        self.assertEqual(self.identity["persona"]["mode"], "reasoning_model")

    def test_heuristics_are_derived(self) -> None:
        self.assertTrue(self.identity["persona"]["decision_heuristics"])

    def test_boundaries_are_declared(self) -> None:
        boundaries = self.identity["persona"]["honest_boundaries"]
        self.assertTrue(any("not from a distilled creator" in b for b in boundaries))

    def test_audience_is_a_declared_absence(self) -> None:
        self.assertTrue(self.identity["audience"].startswith("not_available:"))

    def test_tone_is_mapped_from_the_distillation_skill(self) -> None:
        self.assertIn("mechanism-first", self.identity["tone"])


class SourceMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bundle, cls.mapped = _mapped()
        cls.source = cls.mapped.instance["source"]

    def test_keywords_are_derived_from_the_value_rules(self) -> None:
        self.assertEqual(len(self.source["keywords"]), 43)

    def test_keywords_carry_weights(self) -> None:
        for item in self.source["keywords"]:
            self.assertIn("weight", item)
            self.assertIsInstance(item["weight"], float)

    def test_an_evidence_layer_source_exists(self) -> None:
        layers = {s["layer"] for s in self.source["data_sources"]}
        self.assertIn("evidence", layers)

    def test_a_discovery_layer_source_exists(self) -> None:
        layers = {s["layer"] for s in self.source["data_sources"]}
        self.assertIn("discovery", layers)

    def test_reference_creators_declare_absence(self) -> None:
        entry = self.source["reference_creators"][0]
        self.assertTrue(
            str(entry["verification_method"]).startswith("not_available:")
        )

    def test_collection_rules_declare_absence_via_zero_bounds(self) -> None:
        rules = self.source["collection_rules"]
        self.assertEqual(rules["min_notes"], 0)
        self.assertEqual(rules["rate_limit_seconds"], 0)
        self.assertTrue(str(rules["dedupe_by"]).startswith("not_available:"))


class TextRulesMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bundle, cls.mapped = _mapped()
        cls.text_rules = cls.mapped.instance["text_rules"]

    def test_structure_template_id(self) -> None:
        self.assertEqual(
            self.text_rules["structure"]["template_id"],
            "mechanism-evidence-case-risk",
        )

    def test_structure_sections_are_referenced_by_name(self) -> None:
        sections = self.text_rules["structure"]["sections"]
        self.assertEqual(len(sections), 5)
        self.assertIn("business or economic mechanism", sections)

    def test_title_formulas_are_derived_from_sections(self) -> None:
        self.assertTrue(self.text_rules["title_formula"])
        self.assertIn("?", self.text_rules["title_formula"][0])

    def test_length_bounds_are_platform_aware(self) -> None:
        self.assertEqual(self.text_rules["length"]["min_chars"], 300)
        self.assertEqual(self.text_rules["length"]["max_chars"], 1200)

    def test_knowledge_boundaries_come_from_the_review_rubric(self) -> None:
        self.assertTrue(self.text_rules["knowledge_boundary"])

    def test_tone_avoids_investment_advice(self) -> None:
        self.assertIn("investment advice", self.text_rules["tone"]["avoid"])


class VisualRulesMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bundle, cls.mapped = _mapped()
        cls.visual = cls.mapped.instance["visual_rules"]

    def test_profile_id_is_referenced(self) -> None:
        self.assertTrue(self.visual["profile_id"].startswith("vcp-"))

    def test_profile_version_is_referenced(self) -> None:
        self.assertEqual(self.visual["profile_version"], "m5.0.0")

    def test_visual_language_is_read(self) -> None:
        self.assertEqual(self.visual["visual_language"], "information_first")

    def test_attention_strategy_is_read(self) -> None:
        self.assertIn("first", self.visual["attention_strategy"])

    def test_composition_is_read(self) -> None:
        self.assertTrue(self.visual["composition"]["preferred_layout"])

    def test_hierarchy_is_read(self) -> None:
        self.assertIn("primary", self.visual["hierarchy"])

    def test_constraints_are_read(self) -> None:
        self.assertIn("must_have", self.visual["constraints"])

    def test_provenance_is_carried_through(self) -> None:
        self.assertTrue(self.visual["provenance"])

    def test_no_prompt_key(self) -> None:
        self.assertNotIn("prompt", self.visual)

    def test_no_image_key(self) -> None:
        self.assertNotIn("image", self.visual)

    def test_provenance_cites_the_visual_skill(self) -> None:
        record = self.mapped.field_provenance["visual_rules.profile_id"]
        self.assertEqual(record["skill_id"], "visual-style-distillation")
        self.assertEqual(record["asset_id"], "visual_profile_m5")


class RiskPolicyMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bundle, cls.mapped = _mapped()
        cls.risk = cls.mapped.instance["risk_policy"]

    def test_four_categories_are_mapped(self) -> None:
        self.assertEqual(len(self.risk["risk_categories"]), 4)

    def test_investment_advice_is_blocking(self) -> None:
        blocking = [c for c in self.risk["risk_categories"] if c["severity"] == "block"]
        self.assertEqual(len(blocking), 1)
        self.assertEqual(blocking[0]["category_id"], "investment_advice")

    def test_blocked_patterns_are_mapped(self) -> None:
        self.assertEqual(len(self.risk["blocked_patterns"]), 37)

    def test_every_pattern_references_a_declared_category(self) -> None:
        declared = {c["category_id"] for c in self.risk["risk_categories"]}
        for pattern in self.risk["blocked_patterns"]:
            self.assertIn(pattern["category_id"], declared)

    def test_review_rules_cover_pass_and_block(self) -> None:
        decisions = {r["decision"] for r in self.risk["review_rules"]}
        self.assertIn("pass", decisions)
        self.assertIn("block", decisions)

    def test_review_is_required(self) -> None:
        self.assertIs(self.risk["review_required"], True)

    def test_runtime_is_not_connected(self) -> None:
        self.assertIs(self.risk["runtime_connected"], False)

    def test_source_is_declared(self) -> None:
        self.assertEqual(self.risk["source"], "risk_evaluation")

    def test_risk_policy_is_enabled_because_its_asset_is_available(self) -> None:
        self.assertIs(self.risk["enabled"], True)

    def test_evidence_requirement_requires_source_ids(self) -> None:
        self.assertIs(self.risk["evidence_requirement"]["require_source_ids"], True)


class GenerationMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bundle, cls.mapped = _mapped()
        cls.generation = cls.mapped.instance["generation"]

    def test_generation_is_disabled(self) -> None:
        self.assertIs(self.generation["enabled"], False)

    def test_reason_is_the_absent_capability_code(self) -> None:
        self.assertEqual(
            self.generation["reason"], "generation_capability_not_available"
        )

    def test_adapter_ref_names_an_injected_adapter(self) -> None:
        self.assertEqual(
            self.generation["adapter_ref"], "deployment.generation_adapter"
        )

    def test_input_matches_the_runtime_projection(self) -> None:
        self.assertEqual(
            self.generation["input"],
            ["topic", "structure", "knowledge", "style", "domain_context", "constraints"],
        )

    def test_quality_gate_requires_pass(self) -> None:
        self.assertEqual(
            self.generation["quality_gate"]["required_decision"], "PASS"
        )

    def test_no_model_identifier_appears(self) -> None:
        import json

        raw = json.dumps(self.generation).lower()
        for token in ("gpt", "claude", "openai", "gemini", "diffusion"):
            self.assertNotIn(token, raw)


class PublishingMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bundle, cls.mapped = _mapped()
        cls.publishing = cls.mapped.instance["publishing"]

    def test_publishing_is_disabled(self) -> None:
        self.assertIs(self.publishing["enabled"], False)

    def test_reason_is_the_absent_capability_code(self) -> None:
        self.assertEqual(
            self.publishing["reason"], "publishing_capability_not_available"
        )

    def test_platform_comes_from_the_request(self) -> None:
        self.assertEqual(self.publishing["platform"], "xiaohongshu")

    def test_image_ratio_is_platform_aware(self) -> None:
        self.assertEqual(
            self.publishing["image_requirement"]["aspect_ratio"], "4:5"
        )

    def test_idempotency_key_is_declared(self) -> None:
        self.assertTrue(self.publishing["api"]["idempotency_key"])

    def test_schedule_is_manual(self) -> None:
        self.assertEqual(self.publishing["schedule"]["mode"], "manual")

    def test_human_approval_is_required(self) -> None:
        self.assertIs(self.publishing["requires_human_approval"], True)


class EveryFieldHasARuleTests(unittest.TestCase):
    """No instance field may exist without a rule that declares its origin."""

    @classmethod
    def setUpClass(cls) -> None:
        _bundle, cls.mapped = _mapped()
        cls.declared = {(r.module, r.path) for r in FIELD_RULES}

    def test_every_document_field_has_a_declared_rule(self) -> None:
        for module in MAPPED_MODULES:
            document = self.mapped.instance[module]
            for path in document:
                if path in ("mapped_availability",):
                    continue
                with self.subTest(module=module, path=path):
                    self.assertIn((module, path), self.declared)

    def test_every_field_has_a_provenance_record(self) -> None:
        for module in MAPPED_MODULES:
            document = self.mapped.instance[module]
            for path in document:
                if path in ("mapped_availability",):
                    continue
                with self.subTest(module=module, path=path):
                    self.assertIn(
                        f"{module}.{path}", self.mapped.field_provenance
                    )

    def test_field_count_matches_the_rule_table(self) -> None:
        self.assertEqual(len(self.mapped.field_provenance), len(FIELD_RULES))


if __name__ == "__main__":
    unittest.main()
