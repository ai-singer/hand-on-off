"""Negative tests: forbidden content, false capabilities, untraceable skills."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy

from creator_skill import (
    DEFAULT_SKILL_CATALOG,
    SKILL_ISOLATION_KEYS,
    SKILL_PROMPT_KEYS,
    SkillCompositionError,
    SkillDependency,
    SkillIsolationError,
    SkillProvenanceError,
    SkillRegistry,
    SkillSchemaError,
    assert_no_model_call,
    assert_no_prompt,
    assert_no_runtime_code,
    validate_isolation,
    validate_schema,
    validate_semantics,
    validate_skill,
)
from creator_skill.catalog import catalog_asset_references
from creator_skill.model import CreatorSkill, SkillCompatibility, SkillProvenance
from creator_skill.registry import skill_from_document


def _valid_skill(**overrides) -> CreatorSkill:
    base = {
        "skill_id": "clean-skill",
        "skill_type": "review",
        "version": "1.0.0",
        "description": "a clean review skill",
        "capabilities": ("review.one", "review.two"),
        "inputs": ("in",),
        "outputs": ("out",),
        "dependencies": (),
        "compatibility": SkillCompatibility(),
        "provenance": SkillProvenance(
            source_kind="manual",
            source_ref="test",
            skill_version="1.0.0",
            generated_at="1970-01-01T00:00:00Z",
        ),
    }
    base.update(overrides)
    return CreatorSkill(**base)


class PromptRejectionTests(unittest.TestCase):
    """A skill carrying a prompt must be rejected."""

    def test_clean_skill_passes(self) -> None:
        assert_no_prompt(_valid_skill())

    def test_every_prompt_key_is_rejected(self) -> None:
        for key in SKILL_PROMPT_KEYS:
            with self.subTest(key=key):
                document = _valid_skill().as_dict()
                document[key] = "value"
                with self.assertRaises(SkillIsolationError):
                    assert_no_prompt(document)

    def test_prompt_phrase_in_a_capability_is_rejected(self) -> None:
        document = _valid_skill().as_dict()
        document["capabilities"] = ["create image", "review.two"]
        with self.assertRaises(SkillIsolationError):
            assert_no_prompt(document)

    def test_system_prompt_phrase_is_rejected(self) -> None:
        document = _valid_skill().as_dict()
        document["description"] = "carries a system prompt"
        with self.assertRaises(SkillIsolationError):
            assert_no_prompt(document)

    def test_prompt_key_is_rejected_by_the_schema_first(self) -> None:
        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        document["prompt"] = "create image"
        with self.assertRaises(SkillSchemaError):
            validate_schema(document)

    def test_nested_prompt_is_rejected(self) -> None:
        document = _valid_skill().as_dict()
        document["compatibility"]["prompt"] = "x"
        with self.assertRaises(SkillIsolationError):
            assert_no_prompt(document)


class ModelCallRejectionTests(unittest.TestCase):
    """A skill declaring a model call must be rejected."""

    def test_clean_skill_passes(self) -> None:
        assert_no_model_call(_valid_skill())

    def test_model_keys_are_rejected(self) -> None:
        for key in ("model", "model_id", "model_call", "model_reference", "api_call"):
            with self.subTest(key=key):
                document = _valid_skill().as_dict()
                document[key] = "gpt"
                with self.assertRaises(SkillIsolationError):
                    assert_no_model_call(document)

    def test_provider_name_in_a_string_is_rejected(self) -> None:
        for provider in ("openai", "anthropic", "gemini"):
            with self.subTest(provider=provider):
                document = _valid_skill().as_dict()
                document["description"] = f"calls {provider} directly"
                with self.assertRaises(SkillIsolationError):
                    assert_no_model_call(document)

    def test_model_key_is_rejected_by_the_schema(self) -> None:
        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        document["model"] = "gpt-4"
        with self.assertRaises(SkillSchemaError):
            validate_schema(document)


class RuntimeCodeRejectionTests(unittest.TestCase):
    """A skill carrying code must be rejected."""

    def test_clean_skill_passes(self) -> None:
        assert_no_runtime_code(_valid_skill())

    def test_every_isolation_key_is_rejected(self) -> None:
        for key in SKILL_ISOLATION_KEYS:
            with self.subTest(key=key):
                document = _valid_skill().as_dict()
                document[key] = "value"
                with self.assertRaises(SkillIsolationError):
                    assert_no_runtime_code(document)

    def test_python_function_in_a_string_is_rejected(self) -> None:
        document = _valid_skill().as_dict()
        document["description"] = "def run(): return 1"
        with self.assertRaises(SkillIsolationError):
            assert_no_runtime_code(document)

    def test_import_in_a_string_is_rejected(self) -> None:
        document = _valid_skill().as_dict()
        document["description"] = "import subprocess"
        with self.assertRaises(SkillIsolationError):
            assert_no_runtime_code(document)

    def test_runtime_module_reference_is_rejected(self) -> None:
        for module in ("distillation_core", "runtime", "multimodal_creator", "risk_evaluation"):
            with self.subTest(module=module):
                document = _valid_skill().as_dict()
                document["outputs"] = [f"{module}.engine"]
                with self.assertRaises(SkillIsolationError):
                    assert_no_runtime_code(document)

    def test_a_bare_module_name_as_a_capability_is_not_flagged(self) -> None:
        """A capability may legitimately be named after a subsystem.

        The check targets a module *reference* (``runtime.engine``), not the word
        alone, because flagging the bare word would forbid useful capability names.
        """

        document = _valid_skill().as_dict()
        document["capabilities"] = ["review.runtime_connected", "review.two"]
        assert_no_runtime_code(document)

    def test_hard_coded_skill_path_is_rejected(self) -> None:
        document = _valid_skill().as_dict()
        document["description"] = "loaded from skills/finance-persona.json"
        with self.assertRaises(SkillIsolationError):
            assert_no_runtime_code(document)

    def test_http_client_in_a_string_is_rejected(self) -> None:
        document = _valid_skill().as_dict()
        document["description"] = "performs requests.get(url)"
        with self.assertRaises(SkillIsolationError):
            assert_no_runtime_code(document)

    def test_ordinary_prose_is_not_flagged(self) -> None:
        """False positives would make the check useless in practice."""

        document = _valid_skill().as_dict()
        document["description"] = (
            "derived from the template and adapted for the domain"
        )
        assert_no_runtime_code(document)

    def test_validate_isolation_runs_all_three(self) -> None:
        validate_isolation(_valid_skill())

    def test_validate_isolation_rejects_a_prompt(self) -> None:
        document = _valid_skill().as_dict()
        document["prompt"] = "x"
        with self.assertRaises(SkillIsolationError):
            validate_isolation(document)


class SkillSemanticsRejectionTests(unittest.TestCase):
    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            validate_semantics(_valid_skill(skill_type="telepathy"))

    def test_bad_skill_id_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            validate_semantics(_valid_skill(skill_id="Bad Skill"))

    def test_bad_version_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            validate_semantics(_valid_skill(version="1.0"))

    def test_too_few_capabilities_are_rejected(self) -> None:
        with self.assertRaises(Exception):
            validate_semantics(_valid_skill(capabilities=("only.one",)))

    def test_no_inputs_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            validate_semantics(_valid_skill(inputs=()))

    def test_no_outputs_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            validate_semantics(_valid_skill(outputs=()))

    def test_version_mismatch_with_provenance_is_rejected(self) -> None:
        skill = _valid_skill(
            provenance=SkillProvenance(
                source_kind="manual",
                source_ref="test",
                skill_version="2.0.0",
                generated_at="1970-01-01T00:00:00Z",
            )
        )
        with self.assertRaises(Exception):
            validate_semantics(skill)

    def test_valid_skill_passes_semantics(self) -> None:
        validate_semantics(_valid_skill())


class UntraceableSkillTests(unittest.TestCase):
    """A skill with no usable source must be rejected."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.assets = list(catalog_asset_references())

    def test_skill_without_provenance_block_fails(self) -> None:
        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        del document["provenance"]
        with self.assertRaises(Exception):
            skill_from_document(document)

    def test_skill_with_empty_source_ref_fails(self) -> None:
        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        document["provenance"]["source_ref"] = ""
        with self.assertRaises(Exception):
            skill_from_document(document)

    def test_skill_claiming_an_unregistered_artifact_fails(self) -> None:
        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        document["provenance"]["source_kind"] = "projection"
        document["provenance"]["source_ref"] = "ghost_asset"
        with self.assertRaises(SkillProvenanceError):
            validate_skill(skill_from_document(document), registered_assets=self.assets)

    def test_registry_refuses_a_skill_with_a_bad_source(self) -> None:
        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        document["provenance"]["source_kind"] = "projection"
        document["provenance"]["source_ref"] = "ghost_asset"
        registry = SkillRegistry(registered_assets=self.assets)
        with self.assertRaises(SkillProvenanceError):
            registry.register(skill_from_document(document))

    def test_full_validation_rejects_an_untraceable_skill(self) -> None:
        document = deepcopy(DEFAULT_SKILL_CATALOG[0])
        document["provenance"]["source_kind"] = "distillation_artifact"
        document["provenance"]["source_ref"] = "not_registered"
        with self.assertRaises(SkillProvenanceError):
            validate_skill(skill_from_document(document), registered_assets=self.assets)


class FalseCapabilityTests(unittest.TestCase):
    """Available must not be claimed without an implementation."""

    def test_declared_skill_cannot_omit_a_reason(self) -> None:
        with self.assertRaises(Exception):
            _valid_skill(status="declared")

    def test_declared_skill_with_a_reason_is_accepted(self) -> None:
        skill = _valid_skill(status="declared", reason="not implemented")
        self.assertFalse(skill.available)

    def test_declared_skills_are_marked_in_the_registry(self) -> None:
        registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
        declared = [s.skill_id for s in registry if not s.available]
        self.assertIn("xiaohongshu-publishing", declared)
        self.assertIn("xiaohongshu-article-generation", declared)

    def test_declared_skills_do_not_appear_in_list_available(self) -> None:
        registry = SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
        available = {s.skill_id for s in registry.list_available()}
        self.assertNotIn("xiaohongshu-publishing", available)

    def test_generation_and_publishing_carry_zero_confidence(self) -> None:
        by_id = {entry["skill_id"]: entry for entry in DEFAULT_SKILL_CATALOG}
        self.assertEqual(
            by_id["xiaohongshu-article-generation"]["provenance"]["confidence"], 0.0
        )
        self.assertEqual(
            by_id["xiaohongshu-publishing"]["provenance"]["confidence"], 0.0
        )

    def test_strict_request_refuses_to_claim_a_declared_skill(self) -> None:
        from creator_skill import CreatorRequest, SkillComposer

        composer = SkillComposer(
            SkillRegistry.from_documents(DEFAULT_SKILL_CATALOG, validate=False)
        )
        with self.assertRaises(SkillCompositionError):
            composer.compose(
                CreatorRequest(
                    domain="finance", platform="xiaohongshu", allow_unavailable=False
                )
            )


class CrossCuttingNegativeTests(unittest.TestCase):
    def test_prompt_and_model_call_together_are_rejected(self) -> None:
        document = _valid_skill().as_dict()
        document["prompt"] = "x"
        document["model"] = "gpt"
        with self.assertRaises(SkillIsolationError):
            validate_isolation(document)

    def test_a_valid_skill_is_not_rejected(self) -> None:
        """The negative suite must not be passing for the wrong reason."""

        self.assertTrue(
            validate_skill(
                skill_from_document(DEFAULT_SKILL_CATALOG[0]),
                registered_assets=list(catalog_asset_references()),
            ).passed
        )

    def test_no_catalog_skill_serialises_a_prompt(self) -> None:
        raw = json.dumps(DEFAULT_SKILL_CATALOG).lower()
        for token in ("\"prompt\"", "system_prompt", "negative_prompt"):
            self.assertNotIn(token, raw)

    def test_no_catalog_skill_serialises_a_model_call(self) -> None:
        raw = json.dumps(DEFAULT_SKILL_CATALOG).lower()
        for token in ("model_call", "openai", "anthropic", "api_key"):
            self.assertNotIn(token, raw)


if __name__ == "__main__":
    unittest.main()
