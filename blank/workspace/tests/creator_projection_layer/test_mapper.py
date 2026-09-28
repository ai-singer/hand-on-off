"""Asset -> contract module mappers, including the Markdown projection path."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from creator_projection import (
    ProjectionAssetUnavailableError,
    ProjectionError,
    project_generation,
    project_identity,
    project_instance,
    project_publishing,
    project_risk_policy,
    project_source,
    project_text_rules,
    project_visual_rules,
)
from creator_projection.asset_registry import AssetRegistry
from creator_projection.provenance import ProvenanceBuilder

WORKSPACE = Path(__file__).resolve().parents[2]

PERSONA_SKILL = """---
name: sample-perspective
description: A sample persona skill.
---

# Sample Person

## Identity card

A sample creator who explains mechanisms.

## Mental models

### Model 1: Mechanism first

- Mechanism: explain how value, cost and incentive connect.
- Evidence: appears across several explained cases.
- Apply when: a topic has a conclusion but no cause.
- Failure condition: no evidence supports the mechanism.

### Model 2: Boundary keeping

- Mechanism: state the conditions under which a conclusion holds.
- Evidence: conclusions carry explicit uncertainty.
- Apply when: a forecast or return is involved.
- Failure condition: excessive hedging removes informational value.

## Decision heuristics

- When a topic is only "meaningful", find a checkable number first.
- When a conclusion involves a forecast, write the conditions first.

## Honest boundaries

- Based on public material only.
- Does not represent the referenced creator.
- Research cutoff applies.
"""

REGISTRY_WITH_PERSONA = """version: "1.0.0"
assets:
  - id: nuwa_persona_skill
    type: identity_source
    location: persona/SKILL.md
    format: markdown
    status: available
    description: a persona skill
  - id: persona_perspective_skill
    type: identity_source
    location: persona/SKILL.md
    format: markdown
    status: unavailable
    reason: not_used
    description: unused fallback
  - id: plugin_manifest
    type: identity_source
    location: plugins/xiaolin_finance/plugin.json
    format: json
    status: available
  - id: plugin_release_manifest
    type: identity_source
    location: plugins/xiaolin_finance/release.json
    format: json
    status: available
  - id: runtime_config
    type: identity_source
    location: config/runtime/default.json
    format: json
    status: available
  - id: visual_profile_m5
    type: visual_rules
    location: docs/m5/profiles/visual_profile.yaml
    format: yaml
    status: available
  - id: visual_profile_m5_json
    type: visual_rules
    location: docs/m5/profiles/vcp-4fea7437238d4bca.json
    format: json
    status: available
  - id: text_distillation_rules
    type: text_rules
    location: plugins/xiaolin_finance/rules/value_rules.json
    format: json
    status: available
  - id: text_structure_templates
    type: text_rules
    location: plugins/xiaolin_finance/rules/structure_templates.json
    format: json
    status: available
  - id: risk_policy_reference
    type: risk_reference
    location: plugins/xiaolin_finance/rules/filter_rules.json
    format: json
    status: available
  - id: evaluation_rubric
    type: evaluation_policy
    location: plugins/xiaolin_finance/evaluation/rubric.json
    format: json
    status: available
  - id: source_collection_strategy
    type: source_rules
    location: absent/strategy.md
    format: markdown
    status: unavailable
    reason: test_fixture_absent
    description: absent on purpose
  - id: generation_capability
    type: generation_capability
    location: workflows/content_distillation_pipeline/generation_interface.py
    format: python
    status: unavailable
    reason: generation_capability_not_available
    description: absent
  - id: publishing_capability
    type: publishing_capability
    location: config/runtime/default.json
    format: json
    status: unavailable
    reason: publishing_capability_not_available
    description: absent
"""


class MapperBasicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = AssetRegistry.load(WORKSPACE)
        cls.builder = ProvenanceBuilder()

    def test_identity_mapper_returns_the_identity_module(self) -> None:
        module = project_identity(self.registry, ProvenanceBuilder())
        self.assertEqual(module.name, "identity")

    def test_source_mapper_returns_the_source_module(self) -> None:
        self.assertEqual(project_source(self.registry, ProvenanceBuilder()).name, "source")

    def test_text_rules_mapper_returns_the_module(self) -> None:
        self.assertEqual(
            project_text_rules(self.registry, ProvenanceBuilder()).name, "text_rules"
        )

    def test_visual_rules_mapper_returns_the_module(self) -> None:
        self.assertEqual(
            project_visual_rules(self.registry, ProvenanceBuilder()).name, "visual_rules"
        )

    def test_risk_policy_mapper_returns_the_module(self) -> None:
        self.assertEqual(
            project_risk_policy(self.registry, ProvenanceBuilder()).name, "risk_policy"
        )

    def test_every_mapper_declares_its_fields(self) -> None:
        for mapper in (
            project_identity,
            project_source,
            project_text_rules,
            project_visual_rules,
            project_risk_policy,
        ):
            with self.subTest(mapper=mapper.__name__):
                module = mapper(self.registry, ProvenanceBuilder())
                self.assertEqual(sorted(module.fields), sorted(module.document))

    def test_every_mapper_records_provenance(self) -> None:
        for mapper in (
            project_identity,
            project_source,
            project_text_rules,
            project_visual_rules,
            project_risk_policy,
        ):
            with self.subTest(mapper=mapper.__name__):
                builder = ProvenanceBuilder()
                module = mapper(self.registry, builder)
                self.assertEqual(len(builder.module_fields(module.name)), len(module.fields))


class IdentityMapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = AssetRegistry.load(WORKSPACE)
        cls.identity = project_identity(cls.registry, ProvenanceBuilder()).document

    def test_creator_id_comes_from_runtime_config(self) -> None:
        self.assertEqual(self.identity["creator_id"], "creator-agent-template")

    def test_domain_is_contract_valid(self) -> None:
        self.assertEqual(self.identity["domain"], "finance")

    def test_persona_mode_is_recorded(self) -> None:
        self.assertEqual(self.identity["persona"]["mode"], "reasoning_model")

    def test_mental_models_have_the_required_fields(self) -> None:
        for model in self.identity["persona"]["mental_models"]:
            for key in ("model_id", "mechanism", "evidence", "apply_when", "failure_condition"):
                self.assertIn(key, model)

    def test_mental_models_are_unique(self) -> None:
        ids = [m["model_id"] for m in self.identity["persona"]["mental_models"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_honest_boundaries_are_present(self) -> None:
        self.assertTrue(self.identity["persona"]["honest_boundaries"])

    def test_audience_absence_is_declared(self) -> None:
        self.assertIn("no audience model", self.identity["audience"])

    def test_language_is_contract_valid(self) -> None:
        self.assertIn(self.identity["language"], ("zh", "en", "bilingual"))

    def test_platform_is_contract_valid(self) -> None:
        self.assertIn(self.identity["platform"], ("xiaohongshu", "bilibili", "youtube", "douyin", "wechat", "web"))


class TextRulesMapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text_rules = project_text_rules(AssetRegistry.load(WORKSPACE), ProvenanceBuilder()).document

    def test_structure_template_id_is_projected(self) -> None:
        self.assertEqual(
            self.text_rules["structure"]["template_id"], "mechanism-evidence-case-risk"
        )

    def test_structure_sections_are_referenced_by_name(self) -> None:
        self.assertEqual(len(self.text_rules["structure"]["sections"]), 5)

    def test_knowledge_boundary_is_populated(self) -> None:
        self.assertTrue(self.text_rules["knowledge_boundary"])

    def test_length_bounds_are_numeric(self) -> None:
        self.assertIsInstance(self.text_rules["length"]["min_chars"], int)
        self.assertIsInstance(self.text_rules["length"]["max_chars"], int)

    def test_title_formula_contains_no_article_prose(self) -> None:
        import json

        raw = json.dumps(self.text_rules["title_formula"]).lower()
        for token in ("write a", "viral", "clickbait"):
            self.assertNotIn(token, raw)

    def test_no_prompt_field_anywhere(self) -> None:
        import json

        self.assertNotIn("prompt", json.dumps(self.text_rules).lower())


class VisualRulesMapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = AssetRegistry.load(WORKSPACE)
        cls.visual = project_visual_rules(cls.registry, ProvenanceBuilder()).document

    def test_profile_id_is_referenced(self) -> None:
        self.assertTrue(self.visual["profile_id"].startswith("vcp-"))

    def test_profile_version_is_referenced(self) -> None:
        self.assertEqual(self.visual["profile_version"], "m5.0.0")

    def test_matches_the_m5_file_exactly(self) -> None:
        profile = self.registry.read_yaml("visual_profile_m5")
        self.assertEqual(
            self.visual["profile_id"], profile["visual_profile"]["profile_id"]
        )

    def test_attention_strategy_is_carried(self) -> None:
        self.assertIn("first", self.visual["attention_strategy"])

    def test_composition_is_carried(self) -> None:
        self.assertTrue(self.visual["composition"]["preferred_layout"])
        self.assertTrue(self.visual["composition"]["forbidden_layout"])

    def test_hierarchy_is_carried(self) -> None:
        self.assertIn("primary", self.visual["hierarchy"])

    def test_constraints_are_carried(self) -> None:
        self.assertIn("must_have", self.visual["constraints"])
        self.assertIn("avoid", self.visual["constraints"])

    def test_provenance_is_carried(self) -> None:
        self.assertTrue(self.visual["provenance"])

    def test_no_prompt_key(self) -> None:
        self.assertNotIn("prompt", self.visual)

    def test_no_image_key(self) -> None:
        self.assertNotIn("image", self.visual)

    def test_no_model_key(self) -> None:
        self.assertNotIn("model", self.visual)

    def test_serialised_form_is_free_of_generation_tokens(self) -> None:
        import json

        raw = json.dumps(self.visual).lower()
        for token in ("prompt", "diffusion", "renderer", "image_generation"):
            self.assertNotIn(token, raw)


class RiskPolicyMapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.risk = project_risk_policy(AssetRegistry.load(WORKSPACE), ProvenanceBuilder()).document

    def test_four_categories_are_projected(self) -> None:
        self.assertEqual(len(self.risk["risk_categories"]), 4)

    def test_investment_advice_is_blocking(self) -> None:
        blocking = [c for c in self.risk["risk_categories"] if c["severity"] == "block"]
        self.assertEqual(len(blocking), 1)
        self.assertEqual(blocking[0]["category_id"], "investment_advice")

    def test_every_category_has_a_valid_action(self) -> None:
        for category in self.risk["risk_categories"]:
            self.assertIn(
                category["action"],
                ("downrank", "require_evidence", "require_review", "block"),
            )

    def test_blocked_patterns_are_projected(self) -> None:
        self.assertTrue(self.risk["blocked_patterns"])

    def test_every_pattern_references_a_declared_category(self) -> None:
        declared = {c["category_id"] for c in self.risk["risk_categories"]}
        for pattern in self.risk["blocked_patterns"]:
            self.assertIn(pattern["category_id"], declared)

    def test_review_is_declared_required(self) -> None:
        self.assertIs(self.risk["review_required"], True)

    def test_runtime_is_declared_not_connected(self) -> None:
        self.assertIs(self.risk["runtime_connected"], False)

    def test_source_is_declared(self) -> None:
        self.assertEqual(self.risk["source"], "risk_evaluation")

    def test_review_rules_cover_pass_and_block(self) -> None:
        decisions = {rule["decision"] for rule in self.risk["review_rules"]}
        self.assertIn("block", decisions)
        self.assertIn("pass", decisions)


class MarkdownProjectionPathTests(unittest.TestCase):
    """The persona path, exercised with a fixture workspace."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)

        (cls.root / "persona").mkdir(parents=True)
        (cls.root / "persona" / "SKILL.md").write_text(PERSONA_SKILL, encoding="utf-8")

        for relative in (
            "plugins/xiaolin_finance/plugin.json",
            "plugins/xiaolin_finance/release.json",
            "plugins/xiaolin_finance/rules/value_rules.json",
            "plugins/xiaolin_finance/rules/filter_rules.json",
            "plugins/xiaolin_finance/rules/structure_templates.json",
            "plugins/xiaolin_finance/evaluation/rubric.json",
            "config/runtime/default.json",
            "docs/m5/profiles/visual_profile.yaml",
            "docs/m5/profiles/vcp-4fea7437238d4bca.json",
            "workflows/content_distillation_pipeline/generation_interface.py",
        ):
            target = cls.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(WORKSPACE / relative, target)

        cls.registry_path = cls.root / "assets.yaml"
        cls.registry_path.write_text(REGISTRY_WITH_PERSONA, encoding="utf-8")
        cls.registry = AssetRegistry.load(cls.root, cls.registry_path)
        cls.module = project_identity(cls.registry, ProvenanceBuilder())

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_persona_asset_is_used_when_available(self) -> None:
        self.assertNotIn("asset_substitution", {
            note.kind for note in self.module.notes
        })

    def test_no_substitution_note_is_emitted(self) -> None:
        self.assertEqual(self.module.notes, ())

    def test_models_are_extracted_from_markdown_headings(self) -> None:
        models = self.module.document["persona"]["mental_models"]
        self.assertEqual(len(models), 2)

    def test_model_ids_are_slugs_of_the_headings(self) -> None:
        ids = [m["model_id"] for m in self.module.document["persona"]["mental_models"]]
        self.assertEqual(ids, ["mechanism-first", "boundary-keeping"])

    def test_model_mechanism_is_taken_verbatim(self) -> None:
        model = self.module.document["persona"]["mental_models"][0]
        self.assertEqual(model["mechanism"], "explain how value, cost and incentive connect.")

    def test_heuristics_are_taken_verbatim(self) -> None:
        heuristics = self.module.document["persona"]["decision_heuristics"]
        self.assertIn(
            'When a topic is only "meaningful", find a checkable number first.', heuristics
        )

    def test_boundaries_are_taken_verbatim(self) -> None:
        boundaries = self.module.document["persona"]["honest_boundaries"]
        self.assertIn("Does not represent the referenced creator.", boundaries)

    def test_name_comes_from_the_level_one_heading(self) -> None:
        self.assertEqual(self.module.document["name"], "Sample Person")

    def test_projection_method_is_markdown_projection(self) -> None:
        builder = ProvenanceBuilder()
        module = project_identity(self.registry, builder)
        record = builder.module_fields(module.name)["persona"]
        self.assertEqual(record["projection_method"], "markdown_projection")

    def test_markdown_projection_has_full_confidence(self) -> None:
        builder = ProvenanceBuilder()
        module = project_identity(self.registry, builder)
        record = builder.module_fields(module.name)["persona"]
        self.assertEqual(record["confidence"], 1.0)

    def test_full_projection_from_the_fixture_validates(self) -> None:
        result = project_instance(self.root, registry_path=self.registry_path)
        from creator_projection import validate_projection

        self.assertTrue(validate_projection(result).passed)

    def test_persona_asset_path_is_recorded(self) -> None:
        builder = ProvenanceBuilder()
        project_identity(self.registry, builder)
        record = builder.module_fields("identity")["persona"]
        self.assertEqual(record["source_path"], "persona/SKILL.md")


class EmptyPersonaAssetTests(unittest.TestCase):
    """A persona asset with no models must fail loudly, not silently degrade."""

    def test_persona_asset_without_models_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "persona").mkdir(parents=True)
            (root / "persona" / "SKILL.md").write_text(
                "# Nobody\n\n## Identity card\n\nnothing here\n", encoding="utf-8"
            )
            for relative in (
                "plugins/xiaolin_finance/plugin.json",
                "config/runtime/default.json",
                "plugins/xiaolin_finance/rules/value_rules.json",
                "plugins/xiaolin_finance/rules/filter_rules.json",
                "plugins/xiaolin_finance/rules/structure_templates.json",
                "plugins/xiaolin_finance/evaluation/rubric.json",
                "docs/m5/profiles/visual_profile.yaml",
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(WORKSPACE / relative, target)
            registry_path = root / "assets.yaml"
            registry_path.write_text(REGISTRY_WITH_PERSONA, encoding="utf-8")
            registry = AssetRegistry.load(root, registry_path)
            with self.assertRaises(ProjectionError):
                project_identity(registry, ProvenanceBuilder())


class SourceMapperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = project_source(AssetRegistry.load(WORKSPACE), ProvenanceBuilder()).document

    def test_keywords_are_projected(self) -> None:
        self.assertEqual(len(self.source["keywords"]), 43)

    def test_an_evidence_layer_source_exists(self) -> None:
        layers = {s["layer"] for s in self.source["data_sources"]}
        self.assertIn("evidence", layers)

    def test_reference_creator_is_marked_verified(self) -> None:
        self.assertIs(self.source["reference_creators"][0]["identity_verified"], True)

    def test_verification_method_declares_it_is_not_applicable(self) -> None:
        method = self.source["reference_creators"][0]["verification_method"]
        self.assertIn("not-applicable", method)

    def test_collection_rules_are_present(self) -> None:
        for key in ("min_notes", "material_tiers", "rate_limit_seconds", "dedupe_by"):
            self.assertIn(key, self.source["collection_rules"])

    def test_keywords_carry_weights(self) -> None:
        self.assertTrue(all("weight" in item for item in self.source["keywords"]))
        self.assertTrue(all(isinstance(item["weight"], float) for item in self.source["keywords"]))


class ReadOnlyTests(unittest.TestCase):
    """Projection must not modify any original asset."""

    def _digest(self, root: Path) -> dict[str, str]:
        digests: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                digests[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        return digests

    def test_projection_leaves_the_workspace_byte_identical(self) -> None:
        before = self._digest(WORKSPACE)
        project_instance(WORKSPACE)
        after = self._digest(WORKSPACE)
        self.assertEqual(before, after)

    def test_registry_file_is_unchanged_by_projection(self) -> None:
        path = WORKSPACE / "creator_projection" / "assets.yaml"
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        project_instance(WORKSPACE)
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_m5_profile_is_unchanged_by_projection(self) -> None:
        path = WORKSPACE / "docs" / "m5" / "profiles" / "visual_profile.yaml"
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        project_instance(WORKSPACE)
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_rule_files_are_unchanged_by_projection(self) -> None:
        paths = [
            WORKSPACE / "plugins" / "xiaolin_finance" / "rules" / name
            for name in ("value_rules.json", "filter_rules.json", "structure_templates.json")
        ]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        project_instance(WORKSPACE)
        for path in paths:
            self.assertEqual(before[path], hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
