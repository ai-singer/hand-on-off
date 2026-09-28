"""Template projection and artifacts tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from creator_contract import (
    MODULE_FILES,
    MODULE_NAMES,
    CreatorContractError,
    canonical_json,
    emit_document,
    instance_dir,
    minimal_instance,
    module_filename,
    module_path,
    parse_document,
    project_blank_template,
    read_instance,
    resolve_repository_template_root,
    resolve_template_root,
    validate,
    write_instance,
    write_projected_instance,
)
from creator_contract.artifacts import read_document


class ProjectionBasicsTests(unittest.TestCase):
    """The blank template projects onto the contract."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.instance, cls.report = project_blank_template()

    def test_projection_is_schema_valid(self) -> None:
        self.assertTrue(validate(self.instance).passed)

    def test_projection_declares_all_eight_modules(self) -> None:
        for module in MODULE_NAMES:
            self.assertIn(module, self.instance)

    def test_projection_contract_version(self) -> None:
        self.assertEqual(self.instance["contract_version"], "1.0.0")

    def test_projection_creator_id_comes_from_runtime_config(self) -> None:
        self.assertEqual(self.report.creator_id, "creator-agent-template")

    def test_projection_reads_exactly_six_config_sources(self) -> None:
        self.assertEqual(len(self.report.sources_read), 6)

    def test_projection_reads_the_runtime_config(self) -> None:
        self.assertIn("config/runtime/default.json", self.report.sources_read)

    def test_projection_reads_the_plugin_manifest(self) -> None:
        self.assertIn("plugins/xiaolin_finance/plugin.json", self.report.sources_read)

    def test_projection_reads_value_filter_and_structure_rules(self) -> None:
        joined = " ".join(self.report.sources_read)
        for name in ("value_rules.json", "filter_rules.json", "structure_templates.json"):
            self.assertIn(name, joined)

    def test_projection_reads_the_rubric(self) -> None:
        self.assertIn("plugins/xiaolin_finance/evaluation/rubric.json", self.report.sources_read)

    def test_projection_root_is_a_directory(self) -> None:
        self.assertTrue(self.report.template_root.is_dir())

    def test_projection_records_notes_for_every_gap(self) -> None:
        """Gaps must be declared, not silently defaulted."""

        joined = " ".join(self.report.notes)
        self.assertIn("no persona", joined)
        self.assertIn("no reference creator", joined)
        self.assertIn("no generation adapter", joined)
        self.assertIn("no publisher", joined)

    def test_projection_report_is_json_serialisable(self) -> None:
        json.dumps(self.report.as_dict())


class ProjectionContentTests(unittest.TestCase):
    """Projected content is faithful to the template's own configuration."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.instance, cls.report = project_blank_template()

    def test_domain_is_read_from_the_plugin_manifest(self) -> None:
        self.assertEqual(self.instance["identity"]["domain"], "finance")

    def test_mental_models_come_from_the_five_value_rule_sections(self) -> None:
        models = self.instance["identity"]["persona"]["mental_models"]
        self.assertEqual(len(models), 5)
        self.assertEqual(
            [model["model_id"] for model in models],
            [
                "business_mechanism",
                "financial_structure",
                "data_expression_pattern",
                "case_selection_logic",
                "misconception_analysis",
            ],
        )

    def test_every_mental_model_declares_a_failure_condition(self) -> None:
        for model in self.instance["identity"]["persona"]["mental_models"]:
            self.assertTrue(model["failure_condition"])

    def test_keywords_are_flattened_from_value_rules(self) -> None:
        keywords = self.instance["source"]["keywords"]
        self.assertEqual(len(keywords), 43)
        self.assertTrue(all("keyword" in item and "weight" in item for item in keywords))

    def test_keywords_include_both_languages(self) -> None:
        joined = " ".join(item["keyword"] for item in self.instance["source"]["keywords"])
        self.assertIn("revenue", joined)
        self.assertIn("商业模式", joined)

    def test_risk_categories_come_from_filter_rules(self) -> None:
        categories = self.instance["risk_policy"]["risk_categories"]
        self.assertEqual(len(categories), 4)
        self.assertEqual(
            sorted(item["category_id"] for item in categories),
            [
                "emotional_language",
                "investment_advice",
                "market_prediction",
                "unverified_fact",
            ],
        )

    def test_investment_advice_is_a_blocking_category(self) -> None:
        blocking = [
            item
            for item in self.instance["risk_policy"]["risk_categories"]
            if item["severity"] == "block"
        ]
        self.assertEqual(len(blocking), 1)
        self.assertEqual(blocking[0]["category_id"], "investment_advice")

    def test_blocked_patterns_are_flattened_from_filter_rules(self) -> None:
        self.assertEqual(len(self.instance["risk_policy"]["blocked_patterns"]), 37)

    def test_every_blocked_pattern_references_a_declared_category(self) -> None:
        declared = {
            item["category_id"]
            for item in self.instance["risk_policy"]["risk_categories"]
        }
        for pattern in self.instance["risk_policy"]["blocked_patterns"]:
            self.assertIn(pattern["category_id"], declared)

    def test_structure_template_is_projected(self) -> None:
        structure = self.instance["text_rules"]["structure"]
        self.assertEqual(structure["template_id"], "mechanism-evidence-case-risk")
        self.assertEqual(len(structure["sections"]), 5)

    def test_knowledge_boundary_includes_rubric_questions(self) -> None:
        boundaries = self.instance["text_rules"]["knowledge_boundary"]
        self.assertTrue(any("revenue" in item or "mechanism" in item for item in boundaries))

    def test_visual_rules_reference_an_m5_profile(self) -> None:
        visual = self.instance["visual_rules"]
        self.assertTrue(visual["profile_id"].startswith("vcp-"))
        self.assertEqual(visual["profile_version"], "m5.0.0")

    def test_visual_rules_carry_no_prompt(self) -> None:
        """The projected visual layer must remain prompt-free."""

        raw = canonical_json(self.instance["visual_rules"]).lower()
        for token in ("prompt", "midjourney", "diffusion", "base64"):
            self.assertNotIn(token, raw)

    def test_provenance_records_the_template_contract(self) -> None:
        provenance = self.instance["provenance"]
        self.assertIn("template_contract", provenance)
        self.assertEqual(
            provenance["template_contract"]["specification"],
            "creator-distillation-plugin",
        )

    def test_every_provenance_entry_names_an_artifact(self) -> None:
        for module, record in self.instance["provenance"].items():
            if not isinstance(record, dict) or "source" not in record:
                continue
            self.assertTrue(record["source"], f"{module} has an empty source")

    def test_generation_is_declared_but_disabled(self) -> None:
        self.assertFalse(self.instance["generation"]["enabled"])

    def test_generation_requires_a_passing_gate(self) -> None:
        self.assertEqual(
            self.instance["generation"]["quality_gate"]["required_decision"], "PASS"
        )

    def test_publishing_declares_an_idempotency_key(self) -> None:
        self.assertTrue(
            self.instance["publishing"]["api"]["idempotency_key"].strip()
        )

    def test_publishing_requires_human_approval(self) -> None:
        self.assertTrue(self.instance["publishing"]["requires_human_approval"])

    def test_projection_does_not_embed_python_modules(self) -> None:
        raw = canonical_json(self.instance).lower()
        for module in ("distillation_core", "risk_evaluation", "multimodal_creator"):
            self.assertNotIn(f"{module}.", raw)


class ProjectionOverrideTests(unittest.TestCase):
    """Projection inputs are respected and bad inputs fail loudly."""

    def test_explicit_template_root_is_honoured(self) -> None:
        root = resolve_template_root()
        instance, report = project_blank_template(template_root=root)
        self.assertEqual(report.template_root, root)
        self.assertTrue(validate(instance).passed)

    def test_repository_relative_resolver_finds_the_checkout_layout(self) -> None:
        root = resolve_repository_template_root()
        self.assertTrue((root / "config" / "runtime" / "default.json").is_file())

    def test_missing_template_root_is_rejected(self) -> None:
        with self.assertRaises(CreatorContractError):
            project_blank_template(template_root="no/such/workspace")

    def test_missing_plugin_directory_is_rejected(self) -> None:
        with self.assertRaises(CreatorContractError):
            project_blank_template(plugin_relative="plugins/does_not_exist")

    def test_a_different_visual_profile_is_honoured(self) -> None:
        profile = {
            "visual_profile": {"profile_id": "vcp-custom", "profile_version": "m5.1.0"},
            "identity": {"visual_language": "cinematic"},
            "composition": {"preferred_layout": ["centred_information"], "forbidden_layout": []},
            "attention": {"first": "subject"},
            "hierarchy": {"primary": "proof"},
            "constraints": {"must_have": ["subject_present"], "avoid": []},
            "provenance": {"visual_identity": {"source": {"phase": "M4"}}},
        }
        instance, _report = project_blank_template(visual_profile=profile)
        self.assertEqual(instance["visual_rules"]["profile_id"], "vcp-custom")
        self.assertEqual(instance["visual_rules"]["visual_language"], "cinematic")
        self.assertTrue(validate(instance).passed)

    def test_projection_does_not_write_into_the_template(self) -> None:
        """Projection must be read-only with respect to the template workspace."""

        root = resolve_template_root()
        before = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
        project_blank_template()
        after = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
        self.assertEqual(before, after)


class ArtifactLayoutTests(unittest.TestCase):
    """The eight-module layout, path helpers, and serialisation."""

    def test_eight_module_names_are_declared(self) -> None:
        self.assertEqual(len(MODULE_NAMES), 8)

    def test_module_files_map_covers_every_module(self) -> None:
        self.assertEqual(sorted(MODULE_FILES), sorted(MODULE_NAMES))

    def test_module_filename_is_json(self) -> None:
        self.assertEqual(module_filename("identity"), "identity.json")

    def test_unknown_module_filename_is_rejected(self) -> None:
        with self.assertRaises(CreatorContractError):
            module_filename("runtime")

    def test_module_path_joins_root_and_creator(self) -> None:
        path = module_path("creator_instance", "finance-xia", "identity")
        self.assertEqual(path.parts[-2:], ("finance-xia", "identity.json"))

    def test_creator_id_with_a_separator_is_rejected(self) -> None:
        for bad in ("a/b", "a\\b", "..", "a:b"):
            with self.subTest(creator_id=bad):
                with self.assertRaises(CreatorContractError):
                    instance_dir("creator_instance", bad)

    def test_blank_creator_id_is_rejected(self) -> None:
        with self.assertRaises(CreatorContractError):
            instance_dir("creator_instance", "  ")

    def test_canonical_json_is_deterministic(self) -> None:
        document = {"b": 1, "a": {"d": 2, "c": 3}}
        self.assertEqual(canonical_json(document), canonical_json(document))

    def test_canonical_json_sorts_keys(self) -> None:
        self.assertLess(canonical_json({"b": 1, "a": 1}).find('"a"'),
                        canonical_json({"b": 1, "a": 1}).find('"b"'))

    def test_canonical_json_preserves_non_ascii(self) -> None:
        self.assertIn("商业模式", canonical_json({"k": "商业模式"}))

    def test_emitted_document_round_trips(self) -> None:
        document = {
            "a": "text",
            "b": 3,
            "c": True,
            "d": ["x", "y"],
            "e": {"f": "g"},
        }
        self.assertEqual(parse_document(emit_document(document)), document)

    def test_emitted_document_skips_comments(self) -> None:
        payload = "# a comment\nkey: \"value\"\n"
        self.assertEqual(parse_document(payload), {"key": "value"})

    def test_parser_rejects_a_line_without_a_colon(self) -> None:
        with self.assertRaises(CreatorContractError):
            parse_document("just a bare line\n")


class WriteAndReadInstanceTests(unittest.TestCase):
    """Writing an instance produces the declared layout and reads back."""

    def test_write_instance_creates_nine_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            written = write_instance(minimal_instance(), root=tmp)
            self.assertEqual(len(written), 9)
            for path in written:
                self.assertTrue(path.is_file(), path)

    def test_write_instance_uses_the_declared_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_instance(minimal_instance(), root=tmp)
            target = Path(tmp) / "finance-xia"
            for module in MODULE_NAMES:
                self.assertTrue((target / f"{module}.json").is_file(), module)

    def test_written_instance_reads_back_equal(self) -> None:
        instance = minimal_instance()
        with tempfile.TemporaryDirectory() as tmp:
            write_instance(instance, root=tmp)
            loaded = read_instance(tmp, "finance-xia")
            self.assertEqual(loaded, instance)

    def test_written_instance_validates_after_a_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_instance(minimal_instance(), root=tmp)
            loaded = read_instance(tmp, "finance-xia")
            self.assertTrue(validate(loaded).passed)

    def test_write_instance_rejects_a_missing_module(self) -> None:
        instance = minimal_instance()
        del instance["source"]
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CreatorContractError):
                write_instance(instance, root=tmp)

    def test_read_instance_on_an_empty_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CreatorContractError):
                read_instance(tmp, "nobody")

    def test_read_instance_reassembles_from_module_files(self) -> None:
        instance = minimal_instance()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "finance-xia"
            target.mkdir(parents=True)
            for module in MODULE_NAMES:
                (target / f"{module}.json").write_text(
                    canonical_json(instance[module]), encoding="utf-8"
                )
            loaded = read_instance(tmp, "finance-xia")
            self.assertEqual(sorted(loaded), sorted(MODULE_NAMES))

    def test_read_document_reports_a_missing_file(self) -> None:
        with self.assertRaises(CreatorContractError):
            read_document("definitely/not/here.json")

    def test_write_projected_instance_writes_nine_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            written, report = write_projected_instance(out_root=tmp)
            self.assertEqual(len(written), 9)
            self.assertEqual(report.creator_id, "creator-agent-template")

    def test_write_projected_instance_output_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_projected_instance(out_root=tmp)
            loaded = read_instance(tmp, "creator-agent-template")
            self.assertTrue(validate(loaded).passed)

    def test_write_projected_instance_does_not_touch_the_template(self) -> None:
        root = resolve_template_root()
        before = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
        with tempfile.TemporaryDirectory() as tmp:
            write_projected_instance(out_root=tmp)
        after = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
