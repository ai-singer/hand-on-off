"""Provenance, the Skill Library, and cross-domain core-skill sharing."""

from __future__ import annotations

import json
import unittest

from creator_plugin_builder import (
    CHAIN_SOURCES,
    LIBRARY_VERSION,
    META_SKILLS,
    PLUGIN_CORE_SKILLS,
    PLUGIN_SLOTS,
    PROVENANCE_CHAIN,
    UNIVERSAL_SKILLS,
    UNIVERSAL_SKILL_SUMMARIES,
    DomainRequest,
    SkillDeclaration,
    all_declarations,
    asset_usage,
    build_domain_plugin,
    declaration,
    library_document,
    meta_declarations,
    plugin_path,
    provenance_document,
    request_digest,
    rule_chains,
    skill_composition,
    skill_declarations,
    skill_usage,
    universal_declarations,
    untraced_rules,
)

from . import fixtures


class ChainTests(unittest.TestCase):
    """``domain_request → domain_catalog → asset → rule``, per rule."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plugin = fixtures.plugin("finance")
        cls.chains = rule_chains(cls.plugin)

    def test_the_chain_has_four_links(self) -> None:
        self.assertEqual(len(PROVENANCE_CHAIN), 4)

    def test_the_chain_names_the_request_first(self) -> None:
        self.assertEqual(PROVENANCE_CHAIN[0], "domain_request")

    def test_the_chain_ends_at_the_rule(self) -> None:
        self.assertEqual(PROVENANCE_CHAIN[-1], "rule")

    def test_every_link_names_where_its_value_lives(self) -> None:
        for link in PROVENANCE_CHAIN:
            self.assertIn(link, CHAIN_SOURCES)

    def test_one_chain_per_rule_and_per_stage(self) -> None:
        expected = sum(len(self.plugin.rules(slot)) for slot in PLUGIN_SLOTS)
        expected += len(self.plugin.protocol_stages)
        self.assertEqual(len(self.chains), expected)

    def test_every_chain_is_recorded(self) -> None:
        for chain in self.chains:
            self.assertTrue(chain["recorded"])

    def test_every_chain_names_a_slot(self) -> None:
        for chain in self.chains:
            self.assertTrue(chain["slot"])

    def test_every_chain_names_a_rule(self) -> None:
        for chain in self.chains:
            self.assertTrue(chain["rule"])

    def test_every_chain_names_a_core_skill(self) -> None:
        for chain in self.chains:
            self.assertIn(chain["core_skill"], PLUGIN_CORE_SKILLS)

    def test_every_chain_names_an_asset(self) -> None:
        for chain in self.chains:
            self.assertTrue(chain["asset"]["asset_id"])

    def test_every_chain_carries_the_request_digest(self) -> None:
        for chain in self.chains:
            self.assertEqual(
                chain["request_digest"], self.plugin.provenance.request_digest
            )

    def test_every_chain_carries_the_catalog_version(self) -> None:
        for chain in self.chains:
            self.assertEqual(
                chain["catalog_version"], self.plugin.provenance.catalog_version
            )

    def test_declared_chains_carry_a_reason(self) -> None:
        for chain in self.chains:
            if not chain["asset"]["available"]:
                self.assertTrue(chain["reason"], chain["rule"])

    def test_every_domain_has_full_chains(self) -> None:
        for plugin in fixtures.all_plugins():
            for chain in rule_chains(plugin):
                self.assertTrue(chain["asset"]["asset_id"], plugin.domain)

    def test_no_rule_is_untraced(self) -> None:
        for plugin in fixtures.all_plugins():
            self.assertEqual(untraced_rules(plugin), (), plugin.domain)

    def test_a_rule_with_no_core_skill_is_untraced(self) -> None:
        from dataclasses import replace

        from creator_plugin_builder import DistillationStage

        stage = self.plugin.protocol_stages[0]
        blank = DistillationStage.__new__(DistillationStage)
        for name, value in (
            ("stage", stage.stage),
            ("domain_term", stage.domain_term),
            ("core_skill", ""),
            ("status", stage.status),
            ("order", stage.order),
            ("source_asset", stage.source_asset),
            ("reason", stage.reason),
            ("questions", stage.questions),
        ):
            object.__setattr__(blank, name, value)
        plugin = replace(
            self.plugin,
            protocol_stages=(blank,) + self.plugin.protocol_stages[1:],
        )
        self.assertIn("protocol_stages.observation", untraced_rules(plugin))


class ProvenanceDocumentTests(unittest.TestCase):
    """The provenance document is what a reviewer reads."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plugin = fixtures.plugin("finance")
        cls.document = provenance_document(cls.plugin)

    def test_it_names_the_plugin(self) -> None:
        self.assertEqual(self.document["plugin_name"], "domain_finance_plugin")

    def test_it_names_the_chain(self) -> None:
        self.assertEqual(self.document["chain"], list(PROVENANCE_CHAIN))

    def test_it_records_where_each_link_lives(self) -> None:
        self.assertEqual(self.document["chain_sources"], dict(CHAIN_SOURCES))

    def test_it_records_the_generator(self) -> None:
        self.assertTrue(self.document["generated_by"])

    def test_it_records_the_timestamp(self) -> None:
        self.assertTrue(self.document["generated_at"])

    def test_it_records_the_catalog_version(self) -> None:
        self.assertTrue(self.document["catalog_version"])

    def test_it_records_the_library_version(self) -> None:
        self.assertEqual(self.document["library_version"], LIBRARY_VERSION)

    def test_it_records_the_request_digest(self) -> None:
        self.assertTrue(self.document["request_digest"])

    def test_it_lists_the_source_assets(self) -> None:
        self.assertTrue(self.document["source_assets"])

    def test_it_lists_the_unavailable_assets(self) -> None:
        self.assertTrue(self.document["unavailable_assets"])

    def test_it_summarises_the_rule_counts(self) -> None:
        summary = self.document["summary"]
        self.assertEqual(
            summary["rule_count"],
            summary["available_rule_count"] + summary["declared_rule_count"],
        )

    def test_it_counts_the_catalog_value_rules(self) -> None:
        """The one taxonomy rule plus the six protocol stages."""

        self.assertEqual(self.document["summary"]["catalog_value_rule_count"], 7)

    def test_the_summary_key_is_present_and_matches_the_rules(self) -> None:
        self.assertEqual(
            self.document["summary"]["catalog_value_rule_count"],
            sum(1 for c in self.document["rules"] if c["values_source"] == "catalog"),
        )

    def test_it_lists_every_rule(self) -> None:
        self.assertEqual(len(self.document["rules"]), len(rule_chains(self.plugin)))

    def test_it_serialises(self) -> None:
        json.dumps(self.document)

    def test_every_domain_produces_a_provenance_document(self) -> None:
        for plugin in fixtures.all_plugins():
            document = provenance_document(plugin)
            self.assertTrue(document["request_digest"], plugin.domain)


class RequestDigestTests(unittest.TestCase):
    """The digest identifies what was asked for."""

    def test_the_digest_is_a_hex_string(self) -> None:
        digest = request_digest(
            DomainRequest(domain="finance"), catalog_version="1.0.0"
        )
        self.assertEqual(len(digest), 64)

    def test_the_digest_is_deterministic(self) -> None:
        request = DomainRequest(domain="finance", platform="xiaohongshu")
        self.assertEqual(
            request_digest(request, catalog_version="1.0.0"),
            request_digest(request, catalog_version="1.0.0"),
        )

    def test_the_digest_changes_with_the_domain(self) -> None:
        self.assertNotEqual(
            request_digest(DomainRequest(domain="finance"), catalog_version="1.0.0"),
            request_digest(DomainRequest(domain="sports"), catalog_version="1.0.0"),
        )

    def test_the_digest_changes_with_the_platform(self) -> None:
        self.assertNotEqual(
            request_digest(
                DomainRequest(domain="finance", platform="a"), catalog_version="1.0.0"
            ),
            request_digest(
                DomainRequest(domain="finance", platform="b"), catalog_version="1.0.0"
            ),
        )

    def test_the_digest_changes_with_the_reference_sources(self) -> None:
        self.assertNotEqual(
            request_digest(
                DomainRequest(domain="finance", reference_sources=("a",)),
                catalog_version="1.0.0",
            ),
            request_digest(
                DomainRequest(domain="finance", reference_sources=("b",)),
                catalog_version="1.0.0",
            ),
        )

    def test_the_digest_changes_with_the_catalog_version(self) -> None:
        request = DomainRequest(domain="finance")
        self.assertNotEqual(
            request_digest(request, catalog_version="1.0.0"),
            request_digest(request, catalog_version="2.0.0"),
        )

    def test_the_digest_rejects_a_non_request(self) -> None:
        from creator_plugin_builder import PluginProvenanceError

        with self.assertRaises(PluginProvenanceError):
            request_digest({"domain": "finance"}, catalog_version="1.0.0")  # type: ignore[arg-type]

    def test_two_builds_of_the_same_request_agree(self) -> None:
        first = build_domain_plugin(fixtures.request_for("finance"))
        second = build_domain_plugin(fixtures.request_for("finance"))
        self.assertEqual(
            first.plugin.provenance.request_digest,
            second.plugin.provenance.request_digest,
        )

    def test_different_platforms_give_different_plugins(self) -> None:
        first = build_domain_plugin(
            DomainRequest(domain="finance", platform="a")
        )
        second = build_domain_plugin(
            DomainRequest(domain="finance", platform="b")
        )
        self.assertNotEqual(
            first.plugin.provenance.request_digest,
            second.plugin.provenance.request_digest,
        )

    def test_the_digest_reaches_the_provenance_document(self) -> None:
        plugin = fixtures.plugin("finance")
        self.assertEqual(
            provenance_document(plugin)["request_digest"],
            plugin.provenance.request_digest,
        )


class UsageTests(unittest.TestCase):
    """Which rule reads which asset, and which skill each rule binds to."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plugin = fixtures.plugin("finance")
        cls.assets = asset_usage(cls.plugin)
        cls.skills = skill_usage(cls.plugin)

    def test_asset_usage_covers_every_asset_the_plugin_names(self) -> None:
        self.assertEqual(
            set(self.assets), set(self.plugin.provenance.source_assets)
        )

    def test_asset_usage_lists_rule_names(self) -> None:
        for names in self.assets.values():
            for name in names:
                self.assertIn(".", name)

    def test_asset_usage_is_sorted(self) -> None:
        self.assertEqual(list(self.assets), sorted(self.assets))

    def test_skill_usage_lists_the_core_skills(self) -> None:
        for skill in self.skills:
            self.assertIn(skill, PLUGIN_CORE_SKILLS)

    def test_skill_usage_covers_every_rule(self) -> None:
        total = sum(len(names) for names in self.skills.values())
        expected = sum(len(self.plugin.rules(slot)) for slot in PLUGIN_SLOTS)
        expected += len(self.plugin.protocol_stages)
        self.assertEqual(total, expected)

    def test_skill_usage_serialises(self) -> None:
        json.dumps({"assets": {k: list(v) for k, v in self.assets.items()}})

    def test_asset_usage_serialises(self) -> None:
        json.dumps({k: list(v) for k, v in self.skills.items()})


class LibraryTests(unittest.TestCase):
    """The library: ten universal skills and three meta skills."""

    def test_the_library_has_ten_universal_skills(self) -> None:
        self.assertEqual(len(UNIVERSAL_SKILLS), 10)

    def test_the_library_has_three_meta_skills(self) -> None:
        self.assertEqual(len(META_SKILLS), 3)

    def test_every_universal_skill_has_a_summary(self) -> None:
        self.assertEqual(set(UNIVERSAL_SKILL_SUMMARIES), set(UNIVERSAL_SKILLS))

    def test_the_declaration_count_matches(self) -> None:
        self.assertEqual(
            len(all_declarations()),
            len(UNIVERSAL_SKILLS) + len(META_SKILLS),
        )

    def test_universal_declarations_are_sorted(self) -> None:
        names = [d.name for d in universal_declarations()]
        self.assertEqual(names, sorted(names))

    def test_meta_declarations_are_sorted(self) -> None:
        names = [d.name for d in meta_declarations()]
        self.assertEqual(names, sorted(names))

    def test_every_declaration_declares_a_layer(self) -> None:
        for entry in all_declarations():
            self.assertIn(entry.layer, ("universal", "meta"))

    def test_universal_declarations_are_universal(self) -> None:
        for entry in universal_declarations():
            self.assertTrue(entry.universal)
            self.assertFalse(entry.meta)

    def test_meta_declarations_are_meta(self) -> None:
        for entry in meta_declarations():
            self.assertTrue(entry.meta)
            self.assertFalse(entry.universal)

    def test_the_builder_skill_is_declared(self) -> None:
        self.assertIn("domain-plugin-builder", META_SKILLS)

    def test_the_validator_skill_is_declared(self) -> None:
        self.assertIn("domain-plugin-validator", META_SKILLS)

    def test_the_composer_skill_is_declared(self) -> None:
        self.assertIn("skill-composer", META_SKILLS)

    def test_every_meta_skill_declares_what_it_accepts(self) -> None:
        for entry in meta_declarations():
            self.assertTrue(entry.accepts, entry.name)

    def test_every_declaration_declares_a_purpose(self) -> None:
        for entry in all_declarations():
            self.assertTrue(entry.purpose, entry.name)

    def test_every_declaration_declares_what_it_produces(self) -> None:
        for entry in all_declarations():
            self.assertTrue(entry.produces, entry.name)

    def test_declaration_lookup_works(self) -> None:
        self.assertEqual(declaration("text-distillation").layer, "universal")

    def test_declaration_lookup_rejects_an_unknown_name(self) -> None:
        from creator_plugin_builder import PluginLibraryError

        with self.assertRaises(PluginLibraryError):
            declaration("not-a-skill")

    def test_skill_declarations_is_keyed_by_name(self) -> None:
        self.assertEqual(
            set(skill_declarations()), set(UNIVERSAL_SKILLS) | set(META_SKILLS)
        )

    def test_a_declaration_serialises(self) -> None:
        json.dumps(declaration("text-distillation").as_dict())

    def test_a_declaration_can_be_built_directly(self) -> None:
        entry = SkillDeclaration(
            name="x", skill_type="t", layer="universal", purpose="p", produces="q"
        )
        self.assertNotIn("accepts", entry.as_dict())

    def test_the_library_document_serialises(self) -> None:
        json.dumps(library_document())

    def test_the_library_document_counts_the_skills(self) -> None:
        document = library_document()
        self.assertEqual(document["universal_skill_count"], 10)
        self.assertEqual(document["meta_skill_count"], 3)

    def test_the_library_document_says_plugins_are_not_shipped(self) -> None:
        self.assertIs(library_document()["generated_at_runtime"], False)

    def test_the_core_skills_a_plugin_may_bind_to_exclude_the_meta_skills(self) -> None:
        for name in META_SKILLS:
            self.assertNotIn(name, PLUGIN_CORE_SKILLS)

    def test_the_core_skills_include_every_universal_skill(self) -> None:
        self.assertEqual(set(PLUGIN_CORE_SKILLS), set(UNIVERSAL_SKILLS))


class CompositionTests(unittest.TestCase):
    """``skill-composer``'s job, stated as data."""

    def test_a_known_requirement_is_satisfied(self) -> None:
        result = skill_composition({"text-distillation": 1})
        self.assertTrue(result["complete"])

    def test_an_unknown_requirement_is_unsatisfied(self) -> None:
        result = skill_composition({"not-a-skill": 1})
        self.assertFalse(result["complete"])

    def test_the_unsatisfied_list_names_the_gap(self) -> None:
        result = skill_composition({"text-distillation": 1, "nope": 1})
        self.assertEqual(result["unsatisfied"], ["nope"])

    def test_a_meta_skill_requirement_resolves(self) -> None:
        result = skill_composition({"domain-plugin-builder": 1})
        self.assertIn("domain-plugin-builder", result["satisfied"])

    def test_the_counts_add_up(self) -> None:
        result = skill_composition({"text-distillation": 1, "nope": 1})
        self.assertEqual(result["requested"], 2)
        self.assertEqual(result["satisfied_count"], 1)

    def test_an_empty_request_is_complete(self) -> None:
        self.assertTrue(skill_composition({})["complete"])

    def test_the_result_serialises(self) -> None:
        json.dumps(skill_composition({"text-distillation": 1}))


class SharedCoreSkillTests(unittest.TestCase):
    """Requirement 9: one core skill serves every domain."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plugins = fixtures.all_plugins()
        cls.finance, cls.sports, cls.technology = cls.plugins

    def test_every_domain_binds_the_same_core_skills(self) -> None:
        for plugin in self.plugins:
            self.assertEqual(
                plugin.required_core_skills,
                self.finance.required_core_skills,
                plugin.domain,
            )

    def test_text_distillation_serves_every_domain(self) -> None:
        for plugin in self.plugins:
            usage = skill_usage(plugin)
            self.assertIn("text-distillation", usage, plugin.domain)

    def test_risk_review_serves_every_domain(self) -> None:
        for plugin in self.plugins:
            self.assertIn("risk-review", skill_usage(plugin), plugin.domain)

    def test_source_normalization_serves_every_domain(self) -> None:
        for plugin in self.plugins:
            self.assertIn("source-normalization", skill_usage(plugin), plugin.domain)

    def test_visual_distillation_serves_every_domain(self) -> None:
        for plugin in self.plugins:
            self.assertIn("visual-distillation", skill_usage(plugin), plugin.domain)

    def test_every_domain_protocol_stage_uses_text_distillation(self) -> None:
        for plugin in self.plugins:
            for stage in plugin.protocol_stages:
                self.assertEqual(stage.core_skill, "text-distillation")

    def test_the_union_of_core_skills_is_one_set(self) -> None:
        union: set[str] = set()
        for plugin in self.plugins:
            union |= set(plugin.required_core_skills)
        self.assertEqual(len(union), len(self.finance.required_core_skills))

    def test_three_domains_produce_three_plugins_from_one_library(self) -> None:
        """The whole architectural claim, measured."""

        library_skills = set(UNIVERSAL_SKILLS)
        for plugin in self.plugins:
            self.assertTrue(set(plugin.required_core_skills) <= library_skills)

    def test_adding_a_domain_would_not_change_the_library(self) -> None:
        """A domain is a catalog entry; the library is untouched by it."""

        before = dict(UNIVERSAL_SKILLS)
        build_domain_plugin(DomainRequest(domain="sports"))
        self.assertEqual(dict(UNIVERSAL_SKILLS), before)

    def test_every_domain_shares_the_same_asset_bindings(self) -> None:
        for plugin in self.plugins:
            self.assertEqual(plugin.source_assets, self.finance.source_assets,
                             plugin.domain)

    def test_every_domain_shares_the_same_rule_slots(self) -> None:
        for plugin in self.plugins:
            for slot in PLUGIN_SLOTS:
                self.assertTrue(plugin.rules(slot), f"{plugin.domain}.{slot}")

    def test_every_domain_differs_in_its_taxonomy(self) -> None:
        taxonomies = [p.values("topic_rules") for p in self.plugins]
        self.assertEqual(len(set(taxonomies)), len(taxonomies))

    def test_every_domain_differs_in_its_protocol_vocabulary(self) -> None:
        vocabularies = [
            tuple(s.domain_term for s in p.protocol_stages) for p in self.plugins
        ]
        self.assertEqual(len(set(vocabularies)), len(vocabularies))

    def test_every_domain_agrees_on_the_protocol_stage_names(self) -> None:
        expected = tuple(s.stage for s in self.finance.protocol_stages)
        for plugin in self.plugins:
            self.assertEqual(
                tuple(s.stage for s in plugin.protocol_stages), expected, plugin.domain
            )


class VersionTests(unittest.TestCase):
    """Requirement 10: a plugin is versionable."""

    def test_every_plugin_declares_a_version(self) -> None:
        for plugin in fixtures.all_plugins():
            self.assertTrue(plugin.version, plugin.domain)

    def test_the_version_is_recorded_in_the_provenance(self) -> None:
        for plugin in fixtures.all_plugins():
            self.assertTrue(plugin.provenance.library_version, plugin.domain)

    def test_the_format_version_is_recorded(self) -> None:
        for plugin in fixtures.all_plugins():
            self.assertEqual(plugin.format_version, "1.0.0", plugin.domain)

    def test_the_catalog_version_is_recorded(self) -> None:
        for plugin in fixtures.all_plugins():
            self.assertTrue(plugin.provenance.catalog_version, plugin.domain)

    def test_a_plugin_version_can_be_overridden(self) -> None:
        result = build_domain_plugin(
            fixtures.request_for("finance"), version="2.3.4"
        )
        self.assertEqual(result.plugin.version, "2.3.4")

    def test_an_overridden_version_reaches_the_document(self) -> None:
        result = build_domain_plugin(
            fixtures.request_for("finance"), version="2.3.4"
        )
        self.assertEqual(result.plugin.as_dict()["version"], "2.3.4")

    def test_an_empty_version_falls_back_to_the_catalog(self) -> None:
        result = build_domain_plugin(
            fixtures.request_for("finance"), version=""
        )
        self.assertEqual(result.plugin.version, "1.0.0")

    def test_the_written_filename_does_not_carry_the_version(self) -> None:
        """The filename identifies the plugin; the version lives inside it."""

        path = plugin_path(fixtures.plugin("finance"), "out")
        self.assertEqual(path.name, "domain_finance_plugin.plugin.json")

    def test_the_library_declares_a_version(self) -> None:
        self.assertTrue(LIBRARY_VERSION)

    def test_the_library_version_reaches_the_provenance(self) -> None:
        self.assertEqual(
            fixtures.plugin("sports").provenance.library_version, LIBRARY_VERSION
        )


if __name__ == "__main__":
    unittest.main()
