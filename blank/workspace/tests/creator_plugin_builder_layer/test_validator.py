"""The validator: isolation, provenance, usability, and the batch report."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from creator_plugin_builder import (
    PLUGIN_SLOTS,
    DomainPlugin,
    PluginIsolationError,
    PluginLibraryError,
    PluginProvenanceError,
    PluginRuleError,
    PluginValidationReport,
    RuleBinding,
    RuleStatus,
    contains_domain_marker,
    describe_validation,
    validate_isolation,
    validate_plugin,
    validate_plugins,
    validate_provenance,
    validate_usability,
)

from . import fixtures


class ValidationReportTests(unittest.TestCase):
    """Every plugin passes all six checks."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plugin = fixtures.plugin("finance")
        cls.report = validate_plugin(cls.plugin)

    def test_the_report_is_a_report(self) -> None:
        self.assertIsInstance(self.report, PluginValidationReport)

    def test_the_report_passed(self) -> None:
        self.assertTrue(self.report.passed)

    def test_the_report_says_PASS(self) -> None:
        self.assertEqual(self.report.status, "PASS")

    def test_all_six_checks_ran(self) -> None:
        self.assertEqual(len(self.report.checks), 6)

    def test_the_check_names_are_the_six_the_brief_names(self) -> None:
        self.assertEqual(
            sorted(self.report.checks),
            ["isolation", "layers", "protocol", "provenance", "schema", "usability"],
        )

    def test_every_check_passed(self) -> None:
        for name, status in self.report.checks.items():
            self.assertEqual(status, "PASS", name)

    def test_the_report_names_the_plugin(self) -> None:
        self.assertEqual(self.report.plugin_name, "domain_finance_plugin")

    def test_the_report_names_the_domain(self) -> None:
        self.assertEqual(self.report.domain, "finance")

    def test_the_report_records_the_version(self) -> None:
        self.assertEqual(self.report.version, "1.0.0")

    def test_the_report_serialises(self) -> None:
        json.dumps(self.report.as_dict())

    def test_a_report_with_findings_serialises_them(self) -> None:
        report = PluginValidationReport(
            plugin_name="x",
            domain="y",
            version="1.0.0",
            checks={"schema": "PASS"},
            findings=("one",),
        )
        self.assertEqual(report.as_dict()["findings"], ["one"])

    def test_every_domain_passes(self) -> None:
        for plugin in fixtures.all_plugins():
            self.assertTrue(validate_plugin(plugin).passed, plugin.domain)

    def test_validate_plugin_rejects_a_non_plugin(self) -> None:
        with self.assertRaises(PluginRuleError):
            validate_plugin({"not": "a plugin"})  # type: ignore[arg-type]


class IsolationTests(unittest.TestCase):
    """Check 4: no runtime, no prompt, no forbidden reference."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plugin = fixtures.plugin("finance")

    def test_a_real_plugin_is_isolated(self) -> None:
        validate_isolation(self.plugin)

    def test_every_domain_is_isolated(self) -> None:
        for plugin in fixtures.all_plugins():
            validate_isolation(plugin)

    def test_a_runtime_key_is_refused(self) -> None:
        rule = RuleBinding(
            slot="runtime",
            core_skill="text-distillation",
            source_asset="text_distillation_rules",
            asset_type="text_rules",
            status=RuleStatus.AVAILABLE.value,
        )
        plugin = replace(self.plugin, source_rules=(rule,))
        with self.assertRaises(PluginIsolationError):
            validate_isolation(plugin)

    def test_a_prompt_key_is_refused(self) -> None:
        rule = RuleBinding(
            slot="prompt",
            core_skill="text-distillation",
            source_asset="text_distillation_rules",
            asset_type="text_rules",
            status=RuleStatus.AVAILABLE.value,
        )
        plugin = replace(self.plugin, source_rules=(rule,))
        with self.assertRaises(PluginIsolationError):
            validate_isolation(plugin)

    def test_a_prompt_phrase_in_a_value_is_refused(self) -> None:
        rule = RuleBinding(
            slot="structure",
            core_skill="text-distillation",
            source_asset="text_structure_templates",
            asset_type="text_rules",
            status=RuleStatus.AVAILABLE.value,
            deliverable="you are a finance expert",
        )
        plugin = replace(self.plugin, text_distillation_rules=(rule,))
        with self.assertRaises(PluginIsolationError):
            validate_isolation(plugin)

    def test_an_agent_loop_key_is_refused(self) -> None:
        rule = RuleBinding(
            slot="agent_loop",
            core_skill="text-distillation",
            source_asset="text_distillation_rules",
            asset_type="text_rules",
            status=RuleStatus.AVAILABLE.value,
        )
        plugin = replace(self.plugin, source_rules=(rule,))
        with self.assertRaises(PluginIsolationError):
            validate_isolation(plugin)

    def test_a_forbidden_module_reference_is_refused(self) -> None:
        rule = RuleBinding(
            slot="structure",
            core_skill="text-distillation",
            source_asset="text_structure_templates",
            asset_type="text_rules",
            status=RuleStatus.AVAILABLE.value,
            deliverable="reads from workflows/",
        )
        plugin = replace(self.plugin, text_distillation_rules=(rule,))
        with self.assertRaises(PluginIsolationError):
            validate_isolation(plugin)

    def test_a_runtime_suffix_is_refused(self) -> None:
        rule = RuleBinding(
            slot="structure",
            core_skill="text-distillation",
            source_asset="text_structure_templates",
            asset_type="text_rules",
            status=RuleStatus.AVAILABLE.value,
            deliverable="run scripts/tennis.py",
        )
        plugin = replace(self.plugin, text_distillation_rules=(rule,))
        with self.assertRaises(PluginIsolationError):
            validate_isolation(plugin)

    def test_the_refusal_names_the_violation(self) -> None:
        rule = RuleBinding(
            slot="prompt",
            core_skill="text-distillation",
            source_asset="text_distillation_rules",
            asset_type="text_rules",
            status=RuleStatus.AVAILABLE.value,
        )
        plugin = replace(self.plugin, source_rules=(rule,))
        try:
            validate_isolation(plugin)
        except PluginIsolationError as exc:
            self.assertTrue(exc.detail)
        else:  # pragma: no cover
            self.fail("expected PluginIsolationError")

    def test_a_clean_deliverable_is_accepted(self) -> None:
        rule = RuleBinding(
            slot="structure",
            core_skill="text-distillation",
            source_asset="text_structure_templates",
            asset_type="text_rules",
            status=RuleStatus.AVAILABLE.value,
            deliverable="the text shape for this domain",
        )
        plugin = replace(self.plugin, text_distillation_rules=(rule,))
        validate_isolation(plugin)

    def test_the_word_runtime_inside_a_longer_word_is_not_a_violation(self) -> None:
        """The check matches whole words, so a longer word is not a false positive."""

        rule = RuleBinding(
            slot="structure",
            core_skill="text-distillation",
            source_asset="text_structure_templates",
            asset_type="text_rules",
            status=RuleStatus.AVAILABLE.value,
            deliverable="runtimeless declaration",
        )
        plugin = replace(self.plugin, text_distillation_rules=(rule,))
        validate_isolation(plugin)

    def test_no_plugin_carries_a_forbidden_module(self) -> None:
        from creator_plugin_builder import FORBIDDEN_MODULES, RUNTIME_SUFFIXES

        for plugin in fixtures.all_plugins():
            text = json.dumps(plugin.as_dict()).lower()
            for module in FORBIDDEN_MODULES:
                self.assertNotIn(f'"{module}"', text, f"{plugin.domain}: {module}")
            for suffix in RUNTIME_SUFFIXES:
                self.assertNotIn(suffix, text, f"{plugin.domain}: {suffix}")

    def test_no_plugin_declares_a_runtime_key(self) -> None:
        from creator_plugin_builder import PROMPT_KEYS, RUNTIME_KEYS

        for plugin in fixtures.all_plugins():
            document = plugin.as_dict()

            def keys(node):
                if isinstance(node, dict):
                    for key, value in node.items():
                        yield str(key)
                        yield from keys(value)
                elif isinstance(node, list):
                    for item in node:
                        yield from keys(item)

            found = set(keys(document))
            for key in RUNTIME_KEYS:
                self.assertNotIn(key, found, f"{plugin.domain}: {key}")
            for key in PROMPT_KEYS:
                self.assertNotIn(key, found, f"{plugin.domain}: {key}")


class ProvenanceValidationTests(unittest.TestCase):
    """Check 5: every rule can name its origin."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plugin = fixtures.plugin("finance")

    def test_a_real_plugin_has_complete_provenance(self) -> None:
        validate_provenance(self.plugin)

    def test_every_domain_has_complete_provenance(self) -> None:
        for plugin in fixtures.all_plugins():
            validate_provenance(plugin)

    def test_a_missing_request_digest_is_refused(self) -> None:
        plugin = replace(
            self.plugin,
            provenance=replace(self.plugin.provenance, request_digest="x"),
        )
        # An empty digest cannot be constructed, so the check is exercised by giving
        # the plugin a provenance whose digest is blank via direct assignment on a
        # copy that bypasses __post_init__.
        from creator_plugin_builder import PluginProvenance

        blank = PluginProvenance.__new__(PluginProvenance)
        for field_name, value in (
            ("generated_by", self.plugin.provenance.generated_by),
            ("generated_at", self.plugin.provenance.generated_at),
            ("domain", self.plugin.provenance.domain),
            ("request_digest", ""),
            ("catalog_version", self.plugin.provenance.catalog_version),
            ("library_version", self.plugin.provenance.library_version),
            ("source_assets", self.plugin.provenance.source_assets),
            ("core_skills", self.plugin.provenance.core_skills),
            ("unavailable_assets", self.plugin.provenance.unavailable_assets),
            ("notes", self.plugin.provenance.notes),
        ):
            object.__setattr__(blank, field_name, value)
        with self.assertRaises(PluginProvenanceError):
            validate_provenance(replace(plugin, provenance=blank))

    def test_a_mismatched_domain_is_refused(self) -> None:
        plugin = replace(
            self.plugin,
            provenance=replace(self.plugin.provenance, domain="sports"),
        )
        with self.assertRaises(PluginProvenanceError):
            validate_provenance(plugin)

    def test_a_provenance_omitting_a_read_asset_is_refused(self) -> None:
        plugin = replace(
            self.plugin,
            provenance=replace(
                self.plugin.provenance, source_assets=("text_distillation_rules",)
            ),
        )
        with self.assertRaises(PluginProvenanceError):
            validate_provenance(plugin)

    def test_a_provenance_with_wrong_core_skills_is_refused(self) -> None:
        plugin = replace(
            self.plugin,
            provenance=replace(
                self.plugin.provenance, core_skills=("text-distillation",)
            ),
        )
        with self.assertRaises(PluginProvenanceError):
            validate_provenance(plugin)

    def test_provenance_with_no_assets_is_refused_at_construction(self) -> None:
        with self.assertRaises(PluginProvenanceError):
            replace(self.plugin.provenance, source_assets=())

    def test_provenance_with_no_catalog_version_is_refused(self) -> None:
        with self.assertRaises(PluginProvenanceError):
            replace(self.plugin.provenance, catalog_version="")

    def test_provenance_with_no_library_version_is_refused(self) -> None:
        with self.assertRaises(PluginProvenanceError):
            replace(self.plugin.provenance, library_version="")

    def test_provenance_with_no_generator_is_refused(self) -> None:
        with self.assertRaises(PluginProvenanceError):
            replace(self.plugin.provenance, generated_by="")

    def test_provenance_with_no_timestamp_is_refused(self) -> None:
        with self.assertRaises(PluginProvenanceError):
            replace(self.plugin.provenance, generated_at="")

    def test_the_provenance_serialises(self) -> None:
        json.dumps(self.plugin.provenance.as_dict())

    def test_no_plugin_has_an_untraced_rule(self) -> None:
        from creator_plugin_builder import untraced_rules

        for plugin in fixtures.all_plugins():
            self.assertEqual(untraced_rules(plugin), (), plugin.domain)

    def test_a_rule_with_no_asset_is_reported_as_untraced(self) -> None:
        from creator_plugin_builder import untraced_rules

        rule = RuleBinding(
            slot="structure",
            core_skill="text-distillation",
            source_asset="",
            asset_type="",
            status=RuleStatus.AVAILABLE.value,
        )
        plugin = replace(self.plugin, text_distillation_rules=(rule,))
        self.assertIn(
            "text_distillation_rules.structure", untraced_rules(plugin)
        )


class UsabilityTests(unittest.TestCase):
    """Check 6: a universal skill could act on every rule."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plugin = fixtures.plugin("finance")

    def test_a_real_plugin_is_usable(self) -> None:
        validate_usability(self.plugin)

    def test_every_domain_is_usable(self) -> None:
        for plugin in fixtures.all_plugins():
            validate_usability(plugin)

    def test_an_unknown_asset_is_refused(self) -> None:
        with self.assertRaises(PluginRuleError):
            validate_usability(self.plugin, registered_assets=("text_rules",))

    def test_the_real_registry_assets_are_accepted(self) -> None:
        from creator_projection import AssetRegistry

        registry = AssetRegistry.load(fixtures.WORKSPACE)
        validate_usability(self.plugin, registered_assets=tuple(registry.ids()))

    def test_a_non_plugin_is_refused(self) -> None:
        with self.assertRaises(PluginRuleError):
            validate_usability("not a plugin")  # type: ignore[arg-type]

    def test_an_empty_rule_slot_is_refused(self) -> None:
        plugin = replace(self.plugin, source_rules=())
        with self.assertRaises(PluginRuleError):
            validate_usability(plugin)

    def test_a_rule_binding_to_a_meta_skill_is_refused(self) -> None:
        """A plugin is built by the meta skills; it is not run by them."""

        rule = RuleBinding.__new__(RuleBinding)
        object.__setattr__(rule, "slot", "x")
        object.__setattr__(rule, "core_skill", "domain-plugin-builder")
        object.__setattr__(rule, "source_asset", "text_distillation_rules")
        object.__setattr__(rule, "asset_type", "text_rules")
        object.__setattr__(rule, "status", RuleStatus.AVAILABLE.value)
        object.__setattr__(rule, "reason", "")
        object.__setattr__(rule, "values", ())
        object.__setattr__(rule, "values_source", "asset")
        object.__setattr__(rule, "deliverable", "")
        plugin = replace(self.plugin, source_rules=(rule,))
        with self.assertRaises(PluginLibraryError):
            validate_usability(plugin)

    def test_a_plugin_with_no_requirements_is_refused_at_construction(self) -> None:
        with self.assertRaises(PluginRuleError):
            replace(self.plugin, required_core_skills=())

    def test_a_requirement_outside_the_library_is_refused_at_construction(self) -> None:
        with self.assertRaises(PluginLibraryError):
            replace(self.plugin, required_core_skills=("not-a-skill",))

    def test_an_empty_asset_name_is_refused(self) -> None:
        rule = RuleBinding(
            slot="x",
            core_skill="text-distillation",
            source_asset="",
            asset_type="",
            status=RuleStatus.AVAILABLE.value,
        )
        plugin = replace(self.plugin, source_rules=(rule,))
        with self.assertRaises(PluginRuleError):
            validate_usability(plugin)


class BatchValidationTests(unittest.TestCase):
    """Validating a set, and reporting on it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plugins = fixtures.all_plugins()

    def test_validate_plugins_returns_one_report_each(self) -> None:
        reports = validate_plugins(self.plugins)
        self.assertEqual(len(reports), len(self.plugins))

    def test_validate_plugins_preserves_order(self) -> None:
        reports = validate_plugins(self.plugins)
        self.assertEqual(
            [r.domain for r in reports], [p.domain for p in self.plugins]
        )

    def test_every_report_passed(self) -> None:
        for report in validate_plugins(self.plugins):
            self.assertTrue(report.passed, report.domain)

    def test_describe_validation_counts_them(self) -> None:
        document = describe_validation(self.plugins)
        self.assertEqual(document["plugin_count"], 3)

    def test_describe_validation_reports_three_passed(self) -> None:
        self.assertEqual(describe_validation(self.plugins)["passed"], 3)

    def test_describe_validation_reports_no_failures(self) -> None:
        self.assertEqual(describe_validation(self.plugins)["failed"], 0)

    def test_describe_validation_says_PASS(self) -> None:
        self.assertEqual(describe_validation(self.plugins)["status"], "PASS")

    def test_describe_validation_lists_the_checks(self) -> None:
        self.assertEqual(
            describe_validation(self.plugins)["checks"],
            ["isolation", "layers", "protocol", "provenance", "schema", "usability"],
        )

    def test_describe_validation_serialises(self) -> None:
        json.dumps(describe_validation(self.plugins))

    def test_an_empty_batch_validates(self) -> None:
        document = describe_validation(())
        self.assertEqual(document["plugin_count"], 0)
        self.assertEqual(document["status"], "PASS")


class DomainMarkerTests(unittest.TestCase):
    """The marker detector is what makes the layer audit possible."""

    def test_a_finance_word_is_detected(self) -> None:
        self.assertIn("finance", contains_domain_marker("finance keywords"))

    def test_a_sports_word_is_detected(self) -> None:
        self.assertIn("sports", contains_domain_marker("sports fixtures"))

    def test_a_technology_word_is_detected(self) -> None:
        self.assertIn("technology", contains_domain_marker("technology news"))

    def test_a_clean_text_has_no_markers(self) -> None:
        self.assertEqual(contains_domain_marker("distill normalized material"), ())

    def test_markers_are_case_insensitive(self) -> None:
        self.assertIn("finance", contains_domain_marker("FINANCE"))

    def test_markers_are_sorted_and_unique(self) -> None:
        found = contains_domain_marker("finance and sports and finance")
        self.assertEqual(found, tuple(sorted(set(found))))


class IsolationSourceTests(unittest.TestCase):
    """The package's own source obeys the rules it enforces."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.package = fixtures.WORKSPACE / "creator_plugin_builder"
        cls.files = sorted(cls.package.glob("*.py"))
        cls.text = "\n".join(p.read_text(encoding="utf-8") for p in cls.files)

    def test_no_package_module_writes_a_file_it_should_not(self) -> None:
        """Only the schema writer and the plugin writer, and both are explicit."""

        writers = []
        for path in self.files:
            source = path.read_text(encoding="utf-8")
            if "write_text(" in source:
                writers.append(path.name)
        self.assertEqual(sorted(writers), ["builder.py", "schema.py"])

    def test_no_package_module_calls_a_model(self) -> None:
        for marker in ("openai", "anthropic", "chat.completions"):
            self.assertNotIn(marker, self.text)

    def test_no_package_module_opens_a_network_connection(self) -> None:
        for marker in ("urllib", "requests.", "socket.", "http.client"):
            self.assertNotIn(marker, self.text)

    def test_no_package_module_calls_lobster(self) -> None:
        """Nothing in the package may *call* the Lobster API.

        The package's docstrings say a user later uploads to Lobster; what must not
        exist is code that reaches it. So the check is on executable shape: no import,
        no client, no endpoint.
        """

        for marker in (
            "import lobster",
            "from lobster",
            "lobster.",
            "Lobster(",
            "lobster_api",
            "LobsterClient",
            "api.lobster",
        ):
            self.assertNotIn(marker, self.text, marker)

    def test_no_package_module_names_a_network_endpoint(self) -> None:
        """The only URLs allowed are JSON Schema identifiers, which are not fetched."""

        offenders: list[str] = []
        for path in self.files:
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if "http://" not in line and "https://" not in line:
                    continue
                stripped = line.strip()
                if stripped.startswith('"$schema"') or stripped.startswith('"$id"'):
                    continue
                offenders.append(f"{path.name}:{number}: {stripped}")
        self.assertEqual(offenders, [])

    def test_every_package_module_has_a_docstring(self) -> None:
        import ast

        for path in self.files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            self.assertIsNotNone(ast.get_docstring(tree), path.name)

    def test_every_package_module_uses_future_annotations(self) -> None:
        for path in self.files:
            source = path.read_text(encoding="utf-8")
            self.assertIn("from __future__ import annotations", source, path.name)

    def test_every_package_module_declares_its_exports(self) -> None:
        for path in self.files:
            source = path.read_text(encoding="utf-8")
            self.assertIn("__all__", source, path.name)


if __name__ == "__main__":
    unittest.main()
