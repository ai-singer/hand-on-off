"""The mapping contract: skill→module routing and one rule per target field."""

from __future__ import annotations

import unittest

from creator_mapping import (
    CAPABILITY_MODULES,
    FIELD_MODES,
    FIELD_RULES,
    MAPPED_MODULES,
    MODULE_SKILL_RULES,
    REQUIRED_PATHS,
    SKILL_MODULE_RULES,
    FieldRule,
    MappingRuleError,
    describe_rules,
    rule_by_id,
    rule_for_path,
    rule_ids,
    rules_for_module,
    unavailable_rules,
)
from creator_skill import SKILL_TYPE_ORDER


class RuleTableTests(unittest.TestCase):
    def test_skill_module_routing_covers_every_skill_type(self) -> None:
        for skill_type in SKILL_TYPE_ORDER:
            self.assertIn(skill_type, SKILL_MODULE_RULES, skill_type)

    def test_every_skill_type_routes_to_at_least_one_module(self) -> None:
        for skill_type, modules in SKILL_MODULE_RULES.items():
            with self.subTest(skill_type=skill_type):
                self.assertTrue(modules)

    def test_routing_targets_are_real_modules(self) -> None:
        mapped = set(MAPPED_MODULES)
        for skill_type, modules in SKILL_MODULE_RULES.items():
            for module in modules:
                with self.subTest(skill_type=skill_type, module=module):
                    self.assertIn(module, mapped)

    def test_domain_feeds_both_identity_and_source(self) -> None:
        self.assertEqual(set(SKILL_MODULE_RULES["domain"]), {"identity", "source"})

    def test_distillation_feeds_text_and_visual(self) -> None:
        self.assertEqual(
            set(SKILL_MODULE_RULES["distillation"]), {"text_rules", "visual_rules"}
        )

    def test_module_skill_rules_cover_every_mapped_module(self) -> None:
        for module in MAPPED_MODULES:
            self.assertIn(module, MODULE_SKILL_RULES, module)

    def test_module_skill_rules_point_at_known_types(self) -> None:
        for module, skill_type in MODULE_SKILL_RULES.items():
            with self.subTest(module=module):
                self.assertIn(skill_type, SKILL_TYPE_ORDER)

    def test_capability_modules_are_generation_and_publishing(self) -> None:
        self.assertEqual(set(CAPABILITY_MODULES), {"generation", "publishing"})


class FieldRuleTests(unittest.TestCase):
    def test_rule_ids_are_unique(self) -> None:
        ids = rule_ids()
        self.assertEqual(len(ids), len(set(ids)))

    def test_rule_ids_are_prefixed(self) -> None:
        for rule_id in rule_ids():
            self.assertTrue(rule_id.startswith("RULE_"), rule_id)

    def test_every_module_has_rules(self) -> None:
        for module in MAPPED_MODULES:
            with self.subTest(module=module):
                self.assertTrue(rules_for_module(module))

    def test_every_module_has_required_paths(self) -> None:
        for module in MAPPED_MODULES:
            with self.subTest(module=module):
                self.assertTrue(REQUIRED_PATHS[module])

    def test_required_paths_match_the_rules(self) -> None:
        for module in MAPPED_MODULES:
            declared = tuple(r.path for r in rules_for_module(module))
            self.assertEqual(REQUIRED_PATHS[module], declared)

    def test_every_rule_declares_a_known_mode(self) -> None:
        for rule in FIELD_RULES:
            self.assertIn(rule.mode, FIELD_MODES, rule.rule_id)

    def test_every_rule_names_a_known_skill_type(self) -> None:
        for rule in FIELD_RULES:
            self.assertIn(rule.skill_type, SKILL_TYPE_ORDER, rule.rule_id)

    def test_every_rule_has_a_description(self) -> None:
        for rule in FIELD_RULES:
            self.assertTrue(rule.description.strip(), rule.rule_id)

    def test_unavailable_rules_declare_a_reason(self) -> None:
        for rule in unavailable_rules():
            with self.subTest(rule=rule.rule_id):
                self.assertTrue(rule.unavailable_reason.strip())

    def test_rule_by_id_returns_the_rule(self) -> None:
        first = FIELD_RULES[0]
        self.assertIs(rule_by_id(first.rule_id), first)

    def test_unknown_rule_id_is_rejected(self) -> None:
        with self.assertRaises(MappingRuleError):
            rule_by_id("RULE_NOPE_001")

    def test_rule_for_path_returns_the_rule(self) -> None:
        rule = rule_for_path("identity", "creator_id")
        self.assertEqual(rule.module, "identity")

    def test_unknown_path_is_rejected(self) -> None:
        with self.assertRaises(MappingRuleError):
            rule_for_path("identity", "not_a_field")

    def test_empty_rule_id_is_rejected(self) -> None:
        with self.assertRaises(MappingRuleError):
            FieldRule(
                rule_id="",
                module="identity",
                path="creator_id",
                mode="structural",
                skill_type="identity",
                description="d",
            )

    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaises(MappingRuleError):
            FieldRule(
                rule_id="RULE_X_001",
                module="identity",
                path="creator_id",
                mode="guesswork",
                skill_type="identity",
                description="d",
            )

    def test_unavailable_rule_without_a_reason_is_rejected(self) -> None:
        with self.assertRaises(MappingRuleError):
            FieldRule(
                rule_id="RULE_X_002",
                module="identity",
                path="audience",
                mode="unavailable",
                skill_type="identity",
                description="d",
            )

    def test_unavailable_property_covers_both_absence_modes(self) -> None:
        for rule in FIELD_RULES:
            if rule.mode in ("unavailable", "not_available"):
                self.assertTrue(rule.unavailable)
            else:
                self.assertFalse(rule.unavailable)

    def test_as_dict_carries_the_rule_identity(self) -> None:
        record = FIELD_RULES[0].as_dict()
        for key in ("rule_id", "module", "path", "mode", "skill_type"):
            self.assertIn(key, record)

    def test_describe_rules_is_serialisable(self) -> None:
        import json

        json.dumps(describe_rules())

    def test_describe_rules_counts_every_field_rule(self) -> None:
        self.assertEqual(describe_rules()["rule_count"], len(FIELD_RULES))


class SpecificRuleTests(unittest.TestCase):
    """The mapping rules the brief names explicitly."""

    def test_identity_skill_feeds_identity(self) -> None:
        rule = rule_for_path("identity", "persona")
        self.assertEqual(rule.mode, "asset")

    def test_domain_skill_feeds_source_keywords(self) -> None:
        rule = rule_for_path("source", "keywords")
        self.assertIn(rule.skill_type, ("domain", "source"))

    def test_visual_rule_is_a_reference(self) -> None:
        rule = rule_for_path("visual_rules", "profile_id")
        self.assertEqual(rule.rule_id, "RULE_VISUAL_001")
        self.assertEqual(rule.mode, "asset")

    def test_visual_rules_carry_all_five_m5_sections(self) -> None:
        paths = {r.path for r in rules_for_module("visual_rules")}
        for expected in (
            "profile_id",
            "attention_strategy",
            "composition",
            "hierarchy",
            "constraints",
        ):
            self.assertIn(expected, paths)

    def test_review_skill_feeds_risk_policy(self) -> None:
        rule = rule_for_path("risk_policy", "risk_categories")
        self.assertEqual(rule.skill_type, "review")

    def test_generation_rule_is_a_capability_declaration(self) -> None:
        for rule in rules_for_module("generation"):
            self.assertEqual(rule.mode, "capability", rule.rule_id)

    def test_publishing_rule_is_a_capability_declaration(self) -> None:
        for rule in rules_for_module("publishing"):
            self.assertEqual(rule.mode, "capability", rule.rule_id)

    def test_generation_enabled_rule_exists(self) -> None:
        self.assertEqual(
            rule_for_path("generation", "enabled").rule_id, "RULE_GEN_005"
        )

    def test_publishing_enabled_rule_exists(self) -> None:
        self.assertEqual(
            rule_for_path("publishing", "enabled").rule_id, "RULE_PUB_006"
        )

    def test_risk_policy_declares_not_connected_to_runtime(self) -> None:
        self.assertEqual(
            rule_for_path("risk_policy", "runtime_connected").rule_id, "RULE_RISK_007"
        )


if __name__ == "__main__":
    unittest.main()
