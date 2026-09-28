"""Negative tests: the projection must reject the five named defect classes.

The phase brief names five mandatory rejections:

1. a ``prompt`` field anywhere in an instance;
2. generation falsely enabled (``enabled: true`` with no capability);
3. visual rules containing generation ability;
4. modification of an original asset;
5. a missing source (untraceable field).

Each is covered explicitly by name, then extended so the boundary is tested
rather than the example.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from creator_contract import CreatorContractError
from creator_contract import validate as validate_contract
from creator_projection import (
    GENERATION_TOKENS,
    ProjectionAssetUnavailableError,
    ProjectionCapabilityError,
    ProjectionProvenanceError,
    SOURCED_MODULES,
    assert_fields_traceable,
    assert_no_generation_capability,
    assert_no_phantom_capability,
    assert_projection_provenance,
    project_instance,
    validate_projection,
    write_instance,
)
from creator_projection.mapper import ProjectionResult
from creator_projection.provenance import REQUIRED_PROVENANCE_KEYS

WORKSPACE = Path(__file__).resolve().parents[2]

#: Keys the contract forbids inside visual_rules.
PROMPT_KEYS = (
    "prompt",
    "prompts",
    "negative_prompt",
    "system_prompt",
    "template_prompt",
    "render",
    "renderer",
    "generator",
    "generate",
    "generation",
    "model",
    "model_id",
    "diffusion",
    "checkpoint",
    "seed",
    "steps",
    "image",
    "images",
    "image_data",
    "pixels",
    "base64",
    "publish",
    "endpoint",
    "api_key",
    "credentials",
    "webhook",
)


def _result() -> ProjectionResult:
    return project_instance(WORKSPACE)


def _with(result: ProjectionResult, instance: dict) -> ProjectionResult:
    return ProjectionResult(
        instance=instance,
        notes=result.notes,
        field_provenance=result.field_provenance,
        creator_id=result.creator_id,
        registry_version=result.registry_version,
        asset_availability=result.asset_availability,
        timestamp=result.timestamp,
    )


class Negative1PromptFieldTests(unittest.TestCase):
    """Req 1: a ``prompt`` field must be rejected, wherever it appears."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = _result()

    def test_valid_instance_has_no_prompt_anywhere(self) -> None:
        raw = json.dumps(self.result.instance).lower()
        self.assertNotIn('"prompt"', raw)

    def test_prompt_in_visual_rules_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["visual_rules"]["prompt"] = "create image"
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)

    def test_prompt_in_generation_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["generation"]["prompt"] = "write the article"
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)

    def test_prompt_in_identity_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["identity"]["prompt"] = "you are a creator"
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)

    def test_prompt_in_text_rules_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["text_rules"]["prompt"] = "write a viral article"
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)

    def test_nested_prompt_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["visual_rules"]["constraints"]["prompt"] = "create image"
        with self.assertRaises((CreatorContractError, ProjectionCapabilityError)):
            validate_projection(_with(self.result, instance))

    def test_every_prompt_key_is_rejected_in_visual_rules(self) -> None:
        for key in PROMPT_KEYS:
            with self.subTest(key=key):
                instance = deepcopy(self.result.instance)
                instance["visual_rules"][key] = "value"
                with self.assertRaises((CreatorContractError, ProjectionCapabilityError)):
                    validate_projection(_with(self.result, instance))

    def test_prompt_phrase_as_content_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["visual_rules"]["visual_language"] = "create image of a factory"
        with self.assertRaises((CreatorContractError, ProjectionCapabilityError)):
            validate_projection(_with(self.result, instance))


class Negative2GenerationFalselyEnabledTests(unittest.TestCase):
    """Req 2: ``generation.enabled = true`` must be rejected."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = _result()

    def test_baseline_is_disabled(self) -> None:
        self.assertIs(self.result.instance["generation"]["enabled"], False)

    def test_enabling_generation_is_rejected_by_the_contract(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["generation"]["enabled"] = True
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)

    def test_enabling_generation_is_rejected_by_projection(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["generation"]["enabled"] = True
        del instance["generation"]["reason"]
        with self.assertRaises(ProjectionCapabilityError):
            validate_projection(_with(self.result, instance))

    def test_enabling_publishing_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["publishing"]["enabled"] = True
        del instance["publishing"]["reason"]
        with self.assertRaises(ProjectionCapabilityError):
            validate_projection(_with(self.result, instance))

    def test_enabling_a_capability_while_keeping_a_reason_is_rejected(self) -> None:
        """Self-contradictory declaration: enabled, yet explained away."""

        instance = deepcopy(self.result.instance)
        instance["generation"]["enabled"] = True
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)

    def test_missing_reason_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        del instance["generation"]["reason"]
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)

    def test_empty_reason_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["generation"]["reason"] = "   "
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)

    def test_arbitrary_reason_is_rejected_by_projection(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["generation"]["reason"] = "will be added later"
        with self.assertRaises(ProjectionCapabilityError):
            validate_projection(_with(self.result, instance))

    def test_publishing_missing_reason_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        del instance["publishing"]["reason"]
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)

    def test_declaring_a_reason_while_disabled_is_required(self) -> None:
        """A disabled capability with no explanation is indistinguishable from an oversight."""

        instance = deepcopy(self.result.instance)
        instance["publishing"]["enabled"] = False
        del instance["publishing"]["reason"]
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)

    def test_claiming_a_connected_risk_runtime_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["risk_policy"]["runtime_connected"] = True
        with self.assertRaises(ProjectionCapabilityError):
            validate_projection(_with(self.result, instance))

    def test_writing_a_falsely_enabled_instance_is_refused(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["generation"]["enabled"] = True
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CreatorContractError):
                write_instance(_with(self.result, instance), tmp)

    def test_generation_input_that_is_not_a_contract_input_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["generation"]["input"] = ["topic", "vibes"]
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)


class Negative3VisualGenerationTests(unittest.TestCase):
    """Req 3: visual rules must contain no generation ability."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = _result()
        cls.visual = cls.result.instance["visual_rules"]

    def test_valid_visual_rules_pass(self) -> None:
        assert_no_generation_capability(self.visual)

    def test_every_generation_token_is_rejected(self) -> None:
        for token in GENERATION_TOKENS:
            with self.subTest(token=token):
                visual = deepcopy(self.visual)
                visual["visual_language"] = f"uses {token}"
                with self.assertRaises(ProjectionCapabilityError):
                    assert_no_generation_capability(visual)

    def test_serialised_visual_rules_have_no_generation_tokens(self) -> None:
        raw = json.dumps(self.visual).lower()
        for token in GENERATION_TOKENS:
            self.assertNotIn(token, raw)

    def test_serialised_visual_rules_have_no_image_bytes(self) -> None:
        raw = json.dumps(self.visual).lower()
        for token in ("base64", "png", "jpg", "pixel"):
            self.assertNotIn(token, raw)

    def test_adding_a_renderer_is_rejected(self) -> None:
        visual = deepcopy(self.visual)
        visual["renderer"] = "some-renderer"
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_generation_capability(visual)

    def test_adding_diffusion_settings_is_rejected(self) -> None:
        visual = deepcopy(self.visual)
        visual["constraints"]["diffusion"] = "v1"
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_generation_capability(visual)

    def test_adding_an_image_field_is_rejected(self) -> None:
        visual = deepcopy(self.visual)
        visual["image"] = "AAAA"
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_generation_capability(visual)

    def test_visual_rules_reference_a_profile_rather_than_copying_one(self) -> None:
        self.assertIn("profile_id", self.visual)
        self.assertIn("profile_version", self.visual)

    def test_visual_rules_do_not_embed_the_full_m5_document(self) -> None:
        """A reference is not a copy: the envelope fields are absent."""

        self.assertNotIn("visual_profile", self.visual)
        self.assertNotIn("source_pattern_ids", self.visual)


class Negative4OriginalAssetModificationTests(unittest.TestCase):
    """Req 4: the projection must not modify any original asset."""

    def _digest(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_workspace_is_byte_identical_after_projection(self) -> None:
        before = {
            path.relative_to(WORKSPACE).as_posix(): self._digest(path)
            for path in sorted(WORKSPACE.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts
        }
        project_instance(WORKSPACE)
        after = {
            path.relative_to(WORKSPACE).as_posix(): self._digest(path)
            for path in sorted(WORKSPACE.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts
        }
        self.assertEqual(before, after)

    def test_workspace_is_unchanged_after_writing_the_example_projection(self) -> None:
        targets = [
            WORKSPACE / "creator_projection" / "assets.yaml",
            WORKSPACE / "docs" / "m5" / "profiles" / "visual_profile.yaml",
            WORKSPACE / "plugins" / "xiaolin_finance" / "rules" / "filter_rules.json",
            WORKSPACE / "plugins" / "xiaolin_finance" / "rules" / "value_rules.json",
            WORKSPACE / "plugins" / "xiaolin_finance" / "rules" / "structure_templates.json",
            WORKSPACE / "plugins" / "xiaolin_finance" / "evaluation" / "rubric.json",
        ]
        before = {path: self._digest(path) for path in targets}
        result = project_instance(WORKSPACE)
        with tempfile.TemporaryDirectory() as tmp:
            write_instance(result, tmp)
        for path in targets:
            with self.subTest(path=path.name):
                self.assertEqual(before[path], self._digest(path))

    def test_rule_content_is_not_rewritten(self) -> None:
        path = WORKSPACE / "plugins" / "xiaolin_finance" / "rules" / "filter_rules.json"
        before = json.loads(path.read_text(encoding="utf-8"))
        project_instance(WORKSPACE)
        self.assertEqual(before, json.loads(path.read_text(encoding="utf-8")))

    def test_m5_profile_is_not_rewritten(self) -> None:
        path = WORKSPACE / "docs" / "m5" / "profiles" / "visual_profile.yaml"
        before = path.read_text(encoding="utf-8")
        project_instance(WORKSPACE)
        self.assertEqual(before, path.read_text(encoding="utf-8"))

    def test_registry_itself_is_not_rewritten(self) -> None:
        path = WORKSPACE / "creator_projection" / "assets.yaml"
        before = path.read_text(encoding="utf-8")
        project_instance(WORKSPACE)
        self.assertEqual(before, path.read_text(encoding="utf-8"))

    def test_no_instance_directory_is_created_by_projection_alone(self) -> None:
        stray = WORKSPACE / "creator_instance"
        if stray.exists():
            self.skipTest("example projection directory already present")
        project_instance(WORKSPACE)
        self.assertFalse(stray.exists())


class Negative5MissingSourceTests(unittest.TestCase):
    """Req 5: a field with no traceable source must fail validation."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = _result()

    def test_baseline_is_fully_traceable(self) -> None:
        assert_projection_provenance(self.result)

    def test_removing_a_module_provenance_entry_fails(self) -> None:
        for module in SOURCED_MODULES:
            with self.subTest(module=module):
                instance = deepcopy(self.result.instance)
                del instance["provenance"][module]
                with self.assertRaises(CreatorContractError):
                    validate_contract(instance)

    def test_emptying_a_module_provenance_source_fails(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["provenance"]["identity"]["source"] = ""
        with self.assertRaises(CreatorContractError):
            validate_contract(instance)

    def test_removing_a_field_provenance_record_fails(self) -> None:
        provenance = deepcopy(self.result.field_provenance)
        del provenance["identity"]["name"]
        with self.assertRaises(ProjectionProvenanceError):
            assert_fields_traceable(provenance, "identity", ("name",))

    def test_removing_a_required_provenance_key_fails(self) -> None:
        for key in REQUIRED_PROVENANCE_KEYS:
            with self.subTest(key=key):
                provenance = deepcopy(self.result.field_provenance)
                del provenance["identity"]["name"][key]
                with self.assertRaises(ProjectionProvenanceError):
                    assert_fields_traceable(provenance, "identity", ("name",))

    def test_blanking_a_source_path_fails(self) -> None:
        provenance = deepcopy(self.result.field_provenance)
        provenance["identity"]["name"]["source_path"] = ""
        with self.assertRaises(ProjectionProvenanceError):
            assert_fields_traceable(provenance, "identity", ("name",))

    def test_unknown_projection_method_fails(self) -> None:
        provenance = deepcopy(self.result.field_provenance)
        provenance["identity"]["name"]["projection_method"] = "guesswork"
        with self.assertRaises(ProjectionProvenanceError):
            assert_fields_traceable(provenance, "identity", ("name",))

    def test_a_field_added_without_provenance_fails(self) -> None:
        """Adding a field to a module without recording it must break validation."""

        instance = deepcopy(self.result.instance)
        instance["identity"]["smuggled_field"] = "no source"
        result = _with(self.result, instance)
        with self.assertRaises((ProjectionProvenanceError, CreatorContractError)):
            validate_projection(result)

    def test_untraceable_provenance_is_rejected_by_validation(self) -> None:
        provenance = deepcopy(self.result.field_provenance)
        provenance["identity"] = {}
        broken = ProjectionResult(
            instance=self.result.instance,
            notes=self.result.notes,
            field_provenance=provenance,
            creator_id=self.result.creator_id,
            registry_version=self.result.registry_version,
            asset_availability=self.result.asset_availability,
            timestamp=self.result.timestamp,
        )
        with self.assertRaises(ProjectionProvenanceError):
            assert_projection_provenance(broken)


class NegativeCrossCuttingTests(unittest.TestCase):
    """Defects that combine classes must still be rejected."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = _result()

    def test_prompt_and_false_generation_together_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        instance["visual_rules"]["prompt"] = "create image"
        instance["generation"]["enabled"] = True
        with self.assertRaises((CreatorContractError, ProjectionCapabilityError)):
            validate_projection(_with(self.result, instance))

    def test_missing_source_and_false_publishing_together_is_rejected(self) -> None:
        instance = deepcopy(self.result.instance)
        del instance["provenance"]["publishing"]
        instance["publishing"]["enabled"] = True
        with self.assertRaises(CreatorContractError):
            validate_projection(_with(self.result, instance))

    def test_an_empty_instance_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            validate_contract({})

    def test_a_valid_instance_is_not_rejected(self) -> None:
        """The negative suite must not be passing for the wrong reason."""

        self.assertTrue(validate_projection(self.result).passed)

    def test_registry_with_no_available_assets_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "assets.yaml"
            registry_path.write_text(
                "version: '1.0.0'\n"
                "assets:\n"
                "  - id: only\n"
                "    type: text_rules\n"
                "    location: missing.json\n"
                "    format: json\n"
                "    status: unavailable\n"
                "    reason: everything_is_missing\n",
                encoding="utf-8",
            )
            from creator_projection import AssetRegistry

            registry = AssetRegistry.load(root, registry_path)
            with self.assertRaises(ProjectionAssetUnavailableError):
                registry.read_json("only")


if __name__ == "__main__":
    unittest.main()
