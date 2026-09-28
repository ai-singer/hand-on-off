"""Building domain plugins: finance, sports, technology, and unknown domains."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from creator_plugin_builder import (
    DEFAULT_REQUIREMENTS,
    PLUGIN_CORE_SKILLS,
    PLUGIN_SLOTS,
    PROTOCOL_STAGES,
    BuildResult,
    DomainNotFoundError,
    DomainPlugin,
    DomainRegistry,
    DomainRequest,
    DomainRequestError,
    PluginRuleError,
    PluginBuilderError,
    PluginRegistryError,
    RuleStatus,
    build_domain_plugin,
    build_domain_plugins,
    catalog_domains,
    catalog_document,
    default_registry,
    describe_domain,
    domain_request_from_document,
    load_domain_request,
    plugin_path,
    write_domain_plugin,
)

from . import fixtures


class FinancePluginTests(unittest.TestCase):
    """The finance plugin: what the phase is judged on."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = fixtures.build("finance")
        cls.plugin = cls.result.plugin

    def test_the_build_returns_a_result(self) -> None:
        self.assertIsInstance(self.result, BuildResult)

    def test_the_plugin_is_a_domain_plugin(self) -> None:
        self.assertIsInstance(self.plugin, DomainPlugin)

    def test_the_plugin_name_follows_the_convention(self) -> None:
        self.assertEqual(self.plugin.plugin_name, "domain_finance_plugin")

    def test_the_domain_is_finance(self) -> None:
        self.assertEqual(self.plugin.domain, "finance")

    def test_the_display_name_is_finance(self) -> None:
        self.assertEqual(self.plugin.display_name, "Finance")

    def test_the_version_is_recorded(self) -> None:
        self.assertEqual(self.plugin.version, "1.0.0")

    def test_the_format_version_is_recorded(self) -> None:
        self.assertEqual(self.plugin.format_version, "1.0.0")

    def test_every_rule_slot_is_populated(self) -> None:
        for slot in PLUGIN_SLOTS:
            self.assertTrue(self.plugin.rules(slot), slot)

    def test_every_check_passed(self) -> None:
        for name, status in self.result.checks.items():
            self.assertEqual(status, "PASS", name)

    def test_the_six_checks_ran(self) -> None:
        self.assertEqual(len(self.result.checks), 6)

    def test_the_plugin_is_usable(self) -> None:
        self.assertTrue(self.plugin.usable)

    def test_the_plugin_is_not_yet_fully_available(self) -> None:
        self.assertFalse(self.plugin.fully_available)

    def test_the_identity_rule_is_declared_rather_than_available(self) -> None:
        self.assertIn("identity_rules.domain_persona", self.plugin.declared_rules)

    def test_the_persona_is_reported_unavailable(self) -> None:
        self.assertFalse(self.plugin.persona_available)

    def test_the_persona_states_why_it_is_unavailable(self) -> None:
        self.assertTrue(self.plugin.identity.persona_reason)

    def test_the_identity_records_the_reference_sources(self) -> None:
        self.assertEqual(
            self.plugin.identity.reference_sources, ("creator_a", "creator_b")
        )

    def test_the_topic_taxonomy_is_recorded(self) -> None:
        self.assertEqual(
            self.plugin.values("topic_rules"),
            ("company_event", "market_move", "policy_impact"),
        )

    def test_the_protocol_is_fully_implemented(self) -> None:
        self.assertEqual(len(self.plugin.protocol_stages), len(PROTOCOL_STAGES))

    def test_the_finance_observation_term_is_event(self) -> None:
        first = self.plugin.protocol_stages[0]
        self.assertEqual(first.stage, "observation")
        self.assertEqual(first.domain_term, "event")

    def test_the_required_core_skills_are_the_library_defaults(self) -> None:
        self.assertEqual(
            tuple(self.plugin.required_core_skills), tuple(DEFAULT_REQUIREMENTS)
        )

    def test_the_plugin_consumes_the_general_text_asset(self) -> None:
        self.assertIn("text_distillation_rules", self.plugin.source_assets)

    def test_the_plugin_consumes_the_visual_profile(self) -> None:
        self.assertIn("visual_profile_m5", self.plugin.source_assets)

    def test_the_plugin_consumes_the_risk_reference(self) -> None:
        self.assertIn("risk_policy_reference", self.plugin.source_assets)

    def test_the_missing_source_strategy_is_listed_as_unavailable(self) -> None:
        self.assertIn(
            "source_collection_strategy", self.plugin.unavailable_assets
        )

    def test_the_plugin_serialises(self) -> None:
        json.dumps(self.plugin.as_dict())

    def test_the_plugin_summarises(self) -> None:
        json.dumps(self.plugin.summary())

    def test_the_build_report_serialises(self) -> None:
        json.dumps(self.result.report())

    def test_the_build_is_deterministic(self) -> None:
        again = build_domain_plugin(fixtures.request_for("finance"))
        self.assertEqual(again.plugin.as_dict(), self.plugin.as_dict())

    def test_two_builds_share_a_request_digest(self) -> None:
        again = build_domain_plugin(fixtures.request_for("finance"))
        self.assertEqual(
            again.plugin.provenance.request_digest,
            self.plugin.provenance.request_digest,
        )


class SportsPluginTests(unittest.TestCase):
    """Sports builds from the same library, and is structurally its own plugin."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = fixtures.build("sports")
        cls.plugin = cls.result.plugin

    def test_the_plugin_name_follows_the_convention(self) -> None:
        self.assertEqual(self.plugin.plugin_name, "domain_sports_plugin")

    def test_the_domain_is_sports(self) -> None:
        self.assertEqual(self.plugin.domain, "sports")

    def test_every_check_passed(self) -> None:
        for name, status in self.result.checks.items():
            self.assertEqual(status, "PASS", name)

    def test_every_rule_slot_is_populated(self) -> None:
        for slot in PLUGIN_SLOTS:
            self.assertTrue(self.plugin.rules(slot), slot)

    def test_the_topic_taxonomy_is_sports_specific(self) -> None:
        self.assertEqual(
            self.plugin.values("topic_rules"),
            ("match_outcome", "player_performance", "transfer"),
        )

    def test_the_sports_observation_term_is_fixture(self) -> None:
        self.assertEqual(self.plugin.protocol_stages[0].domain_term, "fixture")

    def test_the_sports_protocol_differs_from_finance(self) -> None:
        finance = fixtures.plugin("finance")
        self.assertNotEqual(
            tuple(s.domain_term for s in self.plugin.protocol_stages),
            tuple(s.domain_term for s in finance.protocol_stages),
        )

    def test_the_protocol_stage_names_are_identical_to_finance(self) -> None:
        """The protocol is universal; only the vocabulary is local."""

        finance = fixtures.plugin("finance")
        self.assertEqual(
            tuple(s.stage for s in self.plugin.protocol_stages),
            tuple(s.stage for s in finance.protocol_stages),
        )

    def test_sports_binds_the_same_core_skills_as_finance(self) -> None:
        finance = fixtures.plugin("finance")
        self.assertEqual(
            self.plugin.required_core_skills, finance.required_core_skills
        )

    def test_sports_reads_the_same_assets_as_finance(self) -> None:
        finance = fixtures.plugin("finance")
        self.assertEqual(self.plugin.source_assets, finance.source_assets)

    def test_the_plugin_is_usable(self) -> None:
        self.assertTrue(self.plugin.usable)

    def test_the_plugin_is_not_fully_available(self) -> None:
        self.assertFalse(self.plugin.fully_available)


class TechnologyPluginTests(unittest.TestCase):
    """Technology is the third domain, and proves the pattern repeats."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plugin = fixtures.plugin("technology")

    def test_the_plugin_name_follows_the_convention(self) -> None:
        self.assertEqual(self.plugin.plugin_name, "domain_technology_plugin")

    def test_the_domain_is_technology(self) -> None:
        self.assertEqual(self.plugin.domain, "technology")

    def test_every_rule_slot_is_populated(self) -> None:
        for slot in PLUGIN_SLOTS:
            self.assertTrue(self.plugin.rules(slot), slot)

    def test_the_topic_taxonomy_is_technology_specific(self) -> None:
        self.assertEqual(
            self.plugin.values("topic_rules"),
            ("product_launch", "architecture_choice", "adoption_signal"),
        )

    def test_the_technology_observation_term_is_release(self) -> None:
        self.assertEqual(self.plugin.protocol_stages[0].domain_term, "release")

    def test_the_protocol_is_implemented(self) -> None:
        self.assertEqual(
            tuple(s.stage for s in self.plugin.protocol_stages), PROTOCOL_STAGES
        )

    def test_all_three_taxonomies_are_distinct(self) -> None:
        taxonomies = {
            plugin.domain: plugin.values("topic_rules")
            for plugin in fixtures.all_plugins()
        }
        self.assertEqual(len(set(taxonomies.values())), 3)


class AllDomainsTests(unittest.TestCase):
    """Every catalog domain builds, and no two plugins are the same."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plugins = fixtures.all_plugins()

    def test_three_domains_build(self) -> None:
        self.assertEqual(len(self.plugins), 3)

    def test_the_domains_are_finance_sports_technology(self) -> None:
        self.assertEqual(
            tuple(p.domain for p in self.plugins),
            ("finance", "sports", "technology"),
        )

    def test_every_plugin_name_is_unique(self) -> None:
        names = [p.plugin_name for p in self.plugins]
        self.assertEqual(len(set(names)), len(names))

    def test_every_plugin_serialisation_is_unique(self) -> None:
        blobs = {json.dumps(p.as_dict(), sort_keys=True) for p in self.plugins}
        self.assertEqual(len(blobs), len(self.plugins))

    def test_every_plugin_passes_every_check(self) -> None:
        for plugin in self.plugins:
            result = fixtures.build(plugin.domain)
            for name, status in result.checks.items():
                self.assertEqual(status, "PASS", f"{plugin.domain}.{name}")

    def test_every_plugin_is_usable(self) -> None:
        for plugin in self.plugins:
            self.assertTrue(plugin.usable, plugin.domain)

    def test_building_several_at_once_matches_building_one(self) -> None:
        results = build_domain_plugins(
            [fixtures.request_for(d) for d in ("finance", "sports", "technology")]
        )
        self.assertEqual(
            [r.plugin.domain for r in results], ["finance", "sports", "technology"]
        )

    def test_the_plugins_differ_only_in_their_domain_data(self) -> None:
        """The shared structure is what makes one library serve three domains."""

        finance, sports, technology = self.plugins
        for plugin in (sports, technology):
            self.assertEqual(
                plugin.required_core_skills, finance.required_core_skills
            )
            self.assertEqual(plugin.source_assets, finance.source_assets)
            self.assertEqual(
                tuple(s.stage for s in plugin.protocol_stages),
                tuple(s.stage for s in finance.protocol_stages),
            )
            self.assertEqual(
                tuple(r.core_skill for r in plugin.identity_rules),
                tuple(r.core_skill for r in finance.identity_rules),
            )


class UnknownDomainTests(unittest.TestCase):
    """An unknown domain is refused, not approximated."""

    def test_an_unknown_domain_is_refused(self) -> None:
        with self.assertRaises(DomainNotFoundError):
            build_domain_plugin(DomainRequest(domain="astrology"))

    def test_the_refusal_carries_its_code(self) -> None:
        try:
            build_domain_plugin(DomainRequest(domain="astrology"))
        except DomainNotFoundError as exc:
            self.assertEqual(exc.code, "DOMAIN_NOT_FOUND")
        else:  # pragma: no cover
            self.fail("expected DomainNotFoundError")

    def test_the_refusal_lists_the_registered_domains(self) -> None:
        try:
            build_domain_plugin(DomainRequest(domain="astrology"))
        except DomainNotFoundError as exc:
            for domain in catalog_domains():
                self.assertIn(domain, exc.detail)
        else:  # pragma: no cover
            self.fail("expected DomainNotFoundError")

    def test_the_refusal_says_a_domain_is_a_catalog_entry(self) -> None:
        try:
            build_domain_plugin(DomainRequest(domain="astrology"))
        except DomainNotFoundError as exc:
            self.assertIn("catalog entry", exc.detail)
        else:  # pragma: no cover
            self.fail("expected DomainNotFoundError")

    def test_an_empty_domain_is_refused(self) -> None:
        with self.assertRaises(DomainRequestError):
            DomainRequest(domain="")

    def test_a_whitespace_domain_is_refused(self) -> None:
        with self.assertRaises(DomainRequestError):
            DomainRequest(domain="  ")

    def test_a_domain_with_surrounding_whitespace_is_refused(self) -> None:
        with self.assertRaises(DomainRequestError):
            DomainRequest(domain=" finance")

    def test_a_non_request_is_refused(self) -> None:
        with self.assertRaises(PluginBuilderError):
            build_domain_plugin({"domain": "finance"})  # type: ignore[arg-type]

    def test_an_empty_reference_source_is_refused(self) -> None:
        with self.assertRaises(DomainRequestError):
            DomainRequest(domain="finance", reference_sources=("",))

    def test_a_domain_is_case_sensitive(self) -> None:
        with self.assertRaises(DomainNotFoundError):
            build_domain_plugin(DomainRequest(domain="Finance"))


class RegistryTests(unittest.TestCase):
    """The registry: lookup, membership, and duplicate rejection."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = default_registry()

    def test_the_default_registry_has_three_domains(self) -> None:
        self.assertEqual(len(self.registry), 3)

    def test_the_domains_are_sorted(self) -> None:
        self.assertEqual(
            self.registry.domains(), ("finance", "sports", "technology")
        )

    def test_the_registry_declares_finance(self) -> None:
        self.assertTrue(self.registry.has("finance"))

    def test_the_registry_declares_sports(self) -> None:
        self.assertTrue(self.registry.has("sports"))

    def test_the_registry_declares_technology(self) -> None:
        self.assertTrue(self.registry.has("technology"))

    def test_the_registry_does_not_declare_astrology(self) -> None:
        self.assertFalse(self.registry.has("astrology"))

    def test_membership_uses_in(self) -> None:
        self.assertIn("finance", self.registry)

    def test_iteration_yields_domains(self) -> None:
        self.assertEqual(tuple(self.registry), self.registry.domains())

    def test_get_returns_an_entry(self) -> None:
        self.assertEqual(self.registry.get("finance").domain, "finance")

    def test_get_rejects_an_unknown_domain(self) -> None:
        with self.assertRaises(PluginRegistryError):
            self.registry.get("astrology")

    def test_ids_match_domains(self) -> None:
        self.assertEqual(self.registry.ids(), self.registry.domains())

    def test_registering_a_duplicate_is_refused(self) -> None:
        registry = default_registry()
        entry = registry.get("finance")
        with self.assertRaises(PluginRegistryError):
            registry.register(entry)

    def test_unregister_removes_an_entry(self) -> None:
        registry = default_registry()
        registry.unregister("sports")
        self.assertFalse(registry.has("sports"))

    def test_unregistering_an_unknown_domain_is_refused(self) -> None:
        with self.assertRaises(PluginRegistryError):
            default_registry().unregister("astrology")

    def test_registering_a_non_entry_is_refused(self) -> None:
        with self.assertRaises(PluginRegistryError):
            DomainRegistry([{"domain": "x"}])  # type: ignore[list-item]

    def test_a_custom_registry_can_hold_one_domain(self) -> None:
        registry = DomainRegistry([default_registry().get("finance")])
        self.assertEqual(registry.domains(), ("finance",))

    def test_an_empty_registry_refuses_every_domain(self) -> None:
        registry = DomainRegistry([])
        self.assertEqual(len(registry), 0)
        with self.assertRaises(DomainNotFoundError):
            build_domain_plugin(DomainRequest(domain="finance"), registry=registry)

    def test_the_registry_serialises(self) -> None:
        json.dumps(self.registry.as_dict())

    def test_the_catalog_document_lists_every_domain(self) -> None:
        self.assertEqual(catalog_document()["domain_count"], 3)

    def test_the_catalog_document_serialises(self) -> None:
        json.dumps(catalog_document())


class RequestLoadingTests(unittest.TestCase):
    """``domain_request.yaml`` in, a request out."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.examples = fixtures.WORKSPACE / "examples" / "domain_requests"

    def test_the_finance_example_loads(self) -> None:
        request = load_domain_request(self.examples / "finance.yaml")
        self.assertEqual(request.domain, "finance")

    def test_the_example_records_the_platform(self) -> None:
        request = load_domain_request(self.examples / "finance.yaml")
        self.assertEqual(request.platform, "xiaohongshu")

    def test_the_example_records_the_reference_sources(self) -> None:
        request = load_domain_request(self.examples / "finance.yaml")
        self.assertEqual(request.reference_sources, ("creator_a", "creator_b"))

    def test_every_example_loads_and_builds(self) -> None:
        for path in sorted(self.examples.glob("*.yaml")):
            request = load_domain_request(path)
            result = build_domain_plugin(request)
            self.assertTrue(result.passed, path.name)

    def test_the_sports_example_loads(self) -> None:
        self.assertEqual(
            load_domain_request(self.examples / "sports.yaml").domain, "sports"
        )

    def test_the_technology_example_loads(self) -> None:
        self.assertEqual(
            load_domain_request(self.examples / "technology.yaml").domain,
            "technology",
        )

    def test_a_json_request_loads(self) -> None:
        target = fixtures.scratch_dir("req_json") / "r.json"
        target.write_text(
            json.dumps({"domain": "finance", "reference_sources": ["a"]}),
            encoding="utf-8",
        )
        request = load_domain_request(target)
        self.assertEqual(request.domain, "finance")
        self.assertEqual(request.reference_sources, ("a",))

    def test_a_missing_request_file_is_reported(self) -> None:
        with self.assertRaises(DomainRequestError):
            load_domain_request(self.examples / "nope.yaml")

    def test_a_malformed_yaml_request_is_reported(self) -> None:
        target = fixtures.scratch_dir("req_bad") / "r.yaml"
        target.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with self.assertRaises(DomainRequestError):
            load_domain_request(target)

    def test_a_malformed_json_request_is_reported(self) -> None:
        target = fixtures.scratch_dir("req_bad_json") / "r.json"
        target.write_text("{not json", encoding="utf-8")
        with self.assertRaises(DomainRequestError):
            load_domain_request(target)

    def test_a_request_missing_the_domain_is_refused(self) -> None:
        with self.assertRaises(DomainRequestError):
            domain_request_from_document({"platform": "xiaohongshu"})

    def test_an_unknown_request_key_is_refused(self) -> None:
        with self.assertRaises(DomainRequestError):
            domain_request_from_document({"domain": "finance", "nope": 1})

    def test_a_single_reference_creator_is_accepted(self) -> None:
        """The earlier single-reference shape still works, folded into the list."""

        request = domain_request_from_document(
            {"domain": "finance", "reference_creator": "creator_a"}
        )
        self.assertEqual(request.reference_sources, ("creator_a",))

    def test_a_scalar_reference_sources_value_is_accepted(self) -> None:
        request = domain_request_from_document(
            {"domain": "finance", "reference_sources": "creator_a"}
        )
        self.assertEqual(request.reference_sources, ("creator_a",))

    def test_a_non_list_reference_sources_value_is_refused(self) -> None:
        with self.assertRaises(DomainRequestError):
            domain_request_from_document(
                {"domain": "finance", "reference_sources": {"a": 1}}
            )

    def test_the_request_serialises(self) -> None:
        json.dumps(fixtures.request_for("finance").as_dict())

    def test_a_request_with_no_sources_is_allowed(self) -> None:
        request = DomainRequest(domain="finance")
        self.assertEqual(request.reference_source_count, 0)

    def test_a_domain_builds_with_no_reference_sources(self) -> None:
        result = build_domain_plugin(DomainRequest(domain="finance"))
        self.assertTrue(result.passed)


class WriteTests(unittest.TestCase):
    """Writing a plugin to disk, and refusing to write an invalid one."""

    def test_writing_produces_two_files(self) -> None:
        root = fixtures.scratch_dir("write_ok")
        written = write_domain_plugin(fixtures.plugin("finance"), root)
        self.assertEqual(len(written), 2)

    def test_the_plugin_document_is_written(self) -> None:
        root = fixtures.scratch_dir("write_doc")
        write_domain_plugin(fixtures.plugin("finance"), root)
        self.assertTrue((root / "domain_finance_plugin.plugin.json").is_file())

    def test_the_provenance_document_is_written(self) -> None:
        root = fixtures.scratch_dir("write_prov")
        write_domain_plugin(fixtures.plugin("finance"), root)
        self.assertTrue(
            (root / "domain_finance_plugin.provenance.json").is_file()
        )

    def test_the_written_document_round_trips(self) -> None:
        root = fixtures.scratch_dir("write_round")
        write_domain_plugin(fixtures.plugin("finance"), root)
        payload = json.loads(
            (root / "domain_finance_plugin.plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload, fixtures.plugin("finance").as_dict())

    def test_writing_is_deterministic(self) -> None:
        first = fixtures.scratch_dir("write_det1")
        second = fixtures.scratch_dir("write_det2")
        write_domain_plugin(fixtures.plugin("finance"), first)
        write_domain_plugin(fixtures.plugin("finance"), second)
        self.assertEqual(
            (first / "domain_finance_plugin.plugin.json").read_text(encoding="utf-8"),
            (second / "domain_finance_plugin.plugin.json").read_text(encoding="utf-8"),
        )

    def test_the_plugin_path_follows_the_convention(self) -> None:
        path = plugin_path(fixtures.plugin("sports"), "out")
        self.assertEqual(path.name, "domain_sports_plugin.plugin.json")

    def test_writing_creates_the_directory(self) -> None:
        root = fixtures.scratch_dir("write_mkdir") / "deep" / "nested"
        write_domain_plugin(fixtures.plugin("finance"), root)
        self.assertTrue(root.is_dir())

    def test_all_three_plugins_write(self) -> None:
        root = fixtures.scratch_dir("write_all")
        for plugin in fixtures.all_plugins():
            write_domain_plugin(plugin, root)
        self.assertEqual(len(list(root.glob("*.plugin.json"))), 3)


class DescribeTests(unittest.TestCase):
    """The report is a document, not an object dump."""

    def test_describe_returns_a_document(self) -> None:
        report = describe_domain(fixtures.request_for("finance"))
        self.assertIsInstance(report, dict)

    def test_the_report_says_PASS(self) -> None:
        self.assertEqual(
            describe_domain(fixtures.request_for("finance"))["status"], "PASS"
        )

    def test_the_report_names_the_plugin(self) -> None:
        self.assertEqual(
            describe_domain(fixtures.request_for("finance"))["plugin_name"],
            "domain_finance_plugin",
        )

    def test_the_report_carries_the_summary(self) -> None:
        report = describe_domain(fixtures.request_for("finance"))
        self.assertIn("usable", report["summary"])

    def test_the_report_serialises(self) -> None:
        json.dumps(describe_domain(fixtures.request_for("sports")))


class CoreSkillTests(unittest.TestCase):
    """Every plugin binds to declared library skills, and to nothing else."""

    def test_the_library_declares_ten_core_skills(self) -> None:
        self.assertEqual(len(PLUGIN_CORE_SKILLS), 10)

    def test_every_rule_binds_to_a_declared_core_skill(self) -> None:
        for plugin in fixtures.all_plugins():
            for slot in PLUGIN_SLOTS:
                for rule in plugin.rules(slot):
                    self.assertIn(rule.core_skill, PLUGIN_CORE_SKILLS)

    def test_every_protocol_stage_binds_to_a_declared_core_skill(self) -> None:
        for plugin in fixtures.all_plugins():
            for stage in plugin.protocol_stages:
                self.assertIn(stage.core_skill, PLUGIN_CORE_SKILLS)

    def test_every_requirement_is_a_declared_core_skill(self) -> None:
        for plugin in fixtures.all_plugins():
            for skill in plugin.required_core_skills:
                self.assertIn(skill, PLUGIN_CORE_SKILLS)

    def test_no_plugin_requires_a_meta_skill(self) -> None:
        """A plugin is built *by* the meta skills, not run by them."""

        from creator_plugin_builder import META_SKILLS

        for plugin in fixtures.all_plugins():
            for skill in plugin.required_core_skills:
                self.assertNotIn(skill, META_SKILLS)

    def test_every_rule_status_is_a_declared_status(self) -> None:
        declared = tuple(status.value for status in RuleStatus)
        for plugin in fixtures.all_plugins():
            for slot in PLUGIN_SLOTS:
                for rule in plugin.rules(slot):
                    self.assertIn(rule.status, declared)

    def test_available_rules_are_marked_available(self) -> None:
        for plugin in fixtures.all_plugins():
            for slot in PLUGIN_SLOTS:
                for rule in plugin.rules(slot):
                    self.assertEqual(rule.available,
                                     rule.status == RuleStatus.AVAILABLE.value)


if __name__ == "__main__":
    unittest.main()
