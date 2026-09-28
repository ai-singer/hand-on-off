"""Capability declarations: absent capabilities are marked, never faked."""

from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from creator_projection import (
    GENERATION_ABSENT_REASON,
    GENERATION_INPUTS,
    GENERATION_TOKENS,
    PUBLISHING_ABSENT_REASON,
    ProjectionCapabilityError,
    assert_no_generation_capability,
    assert_no_phantom_capability,
    project_generation,
    project_instance,
    project_publishing,
    validate_projection,
)
from creator_projection.provenance import ProvenanceBuilder

WORKSPACE = Path(__file__).resolve().parents[2]


class GenerationDeclarationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from creator_projection import AssetRegistry

        cls.registry = AssetRegistry.load(WORKSPACE)
        cls.module = project_generation(cls.registry, ProvenanceBuilder())

    def test_generation_block_exists(self) -> None:
        self.assertIn("generation", project_instance(WORKSPACE).instance)

    def test_generation_is_disabled(self) -> None:
        self.assertIs(self.module.document["enabled"], False)

    def test_generation_declares_the_absent_reason(self) -> None:
        self.assertEqual(self.module.document["reason"], GENERATION_ABSENT_REASON)

    def test_reason_is_a_machine_readable_code(self) -> None:
        self.assertTrue(self.module.document["reason"].islower())
        self.assertNotIn(" ", self.module.document["reason"])

    def test_generation_declares_an_adapter_reference(self) -> None:
        self.assertTrue(self.module.document["adapter_ref"])

    def test_generation_inputs_match_the_runtime_contract(self) -> None:
        self.assertEqual(self.module.document["input"], list(GENERATION_INPUTS))

    def test_generation_requires_a_passing_gate(self) -> None:
        self.assertEqual(
            self.module.document["quality_gate"]["required_decision"], "PASS"
        )

    def test_generation_carries_no_model_identifier(self) -> None:
        import json

        raw = json.dumps(self.module.document).lower()
        for token in ("gpt", "claude", "openai", "gemini", "diffusion"):
            self.assertNotIn(token, raw)

    def test_generation_emits_a_capability_absent_note(self) -> None:
        kinds = {note.kind for note in self.module.notes}
        self.assertIn("capability_absent", kinds)

    def test_generation_note_names_the_missing_asset(self) -> None:
        note = self.module.notes[0]
        self.assertEqual(note.asset_id, "generation_capability")


class PublishingDeclarationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from creator_projection import AssetRegistry

        cls.registry = AssetRegistry.load(WORKSPACE)
        cls.module = project_publishing(cls.registry, ProvenanceBuilder())

    def test_publishing_is_disabled(self) -> None:
        self.assertIs(self.module.document["enabled"], False)

    def test_publishing_declares_the_absent_reason(self) -> None:
        self.assertEqual(self.module.document["reason"], PUBLISHING_ABSENT_REASON)

    def test_publishing_declares_an_idempotency_key(self) -> None:
        self.assertTrue(self.module.document["api"]["idempotency_key"])

    def test_publishing_requires_human_approval(self) -> None:
        self.assertIs(self.module.document["requires_human_approval"], True)

    def test_publishing_schedule_defaults_to_manual(self) -> None:
        self.assertEqual(self.module.document["schedule"]["mode"], "manual")

    def test_publishing_carries_no_credentials(self) -> None:
        import json

        raw = json.dumps(self.module.document).lower()
        for token in ("api_key", "token", "secret", "password"):
            self.assertNotIn(token, raw)

    def test_publishing_emits_a_capability_absent_note(self) -> None:
        kinds = {note.kind for note in self.module.notes}
        self.assertIn("capability_absent", kinds)


class PhantomCapabilityTests(unittest.TestCase):
    """The guard against claiming a capability that does not exist."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.instance = project_instance(WORKSPACE).instance

    def test_valid_instance_passes(self) -> None:
        assert_no_phantom_capability(self.instance)

    def test_enabling_generation_is_rejected(self) -> None:
        instance = deepcopy(self.instance)
        instance["generation"]["enabled"] = True
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_phantom_capability(instance)

    def test_generation_without_a_reason_is_rejected(self) -> None:
        instance = deepcopy(self.instance)
        del instance["generation"]["reason"]
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_phantom_capability(instance)

    def test_generation_with_a_wrong_reason_is_rejected(self) -> None:
        instance = deepcopy(self.instance)
        instance["generation"]["reason"] = "coming_soon"
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_phantom_capability(instance)

    def test_enabling_publishing_is_rejected(self) -> None:
        instance = deepcopy(self.instance)
        instance["publishing"]["enabled"] = True
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_phantom_capability(instance)

    def test_publishing_without_a_reason_is_rejected(self) -> None:
        instance = deepcopy(self.instance)
        del instance["publishing"]["reason"]
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_phantom_capability(instance)

    def test_claiming_a_connected_risk_runtime_is_rejected(self) -> None:
        instance = deepcopy(self.instance)
        instance["risk_policy"]["runtime_connected"] = True
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_phantom_capability(instance)

    def test_missing_generation_block_is_rejected(self) -> None:
        instance = deepcopy(self.instance)
        del instance["generation"]
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_phantom_capability(instance)

    def test_missing_publishing_block_is_rejected(self) -> None:
        instance = deepcopy(self.instance)
        del instance["publishing"]
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_phantom_capability(instance)

    def test_projection_module_refuses_to_enable_a_capability(self) -> None:
        """If the registry ever claims the asset is available, projection stops."""

        from creator_projection import AssetRegistry
        from creator_projection.asset_registry import Asset

        registry = AssetRegistry.load(WORKSPACE)
        forced = AssetRegistry(
            registry.workspace_root,
            {
                **{a.asset_id: a for a in registry},
                "generation_capability": Asset(
                    asset_id="generation_capability",
                    asset_type="generation_capability",
                    location=registry.get("generation_capability").location,
                    asset_format="python",
                    status="available",
                    reason=None,
                    description="forced available",
                ),
            },
            registry.version,
        )
        with self.assertRaises(ProjectionCapabilityError):
            project_generation(forced, ProvenanceBuilder())


class VisualGenerationTests(unittest.TestCase):
    """The visual layer must carry no generation ability."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.visual = project_instance(WORKSPACE).instance["visual_rules"]

    def test_valid_visual_rules_pass(self) -> None:
        assert_no_generation_capability(self.visual)

    def test_every_generation_token_is_rejected(self) -> None:
        for token in GENERATION_TOKENS:
            with self.subTest(token=token):
                visual = deepcopy(self.visual)
                visual["visual_language"] = f"uses {token} internally"
                with self.assertRaises(ProjectionCapabilityError):
                    assert_no_generation_capability(visual)

    def test_prompt_key_is_rejected(self) -> None:
        visual = deepcopy(self.visual)
        visual["prompt"] = "create image"
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_generation_capability(visual)

    def test_nested_prompt_key_is_rejected(self) -> None:
        visual = deepcopy(self.visual)
        visual["constraints"]["prompt"] = "create image"
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_generation_capability(visual)

    def test_model_key_is_rejected(self) -> None:
        visual = deepcopy(self.visual)
        visual["model"] = "some-model"
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_generation_capability(visual)

    def test_non_mapping_visual_rules_are_rejected(self) -> None:
        with self.assertRaises(ProjectionCapabilityError):
            assert_no_generation_capability(["not", "a", "mapping"])  # type: ignore[arg-type]


class EndToEndCapabilityTests(unittest.TestCase):
    def test_full_projection_validates(self) -> None:
        result = project_instance(WORKSPACE)
        self.assertTrue(validate_projection(result).passed)

    def test_notes_report_every_absent_capability(self) -> None:
        result = project_instance(WORKSPACE)
        absent = {note.module for note in result.notes if note.kind == "capability_absent"}
        self.assertIn("generation", absent)
        self.assertIn("publishing", absent)

    def test_notes_report_every_substitution(self) -> None:
        result = project_instance(WORKSPACE)
        substitutions = [note for note in result.notes if note.kind == "substitution"]
        modules = {note.module for note in substitutions}
        self.assertIn("identity", modules)
        self.assertIn("source", modules)

    def test_writing_an_invalid_instance_is_refused(self) -> None:
        from creator_projection import write_instance
        from creator_projection.mapper import ProjectionResult

        result = project_instance(WORKSPACE)
        broken = deepcopy(result.instance)
        broken["generation"]["enabled"] = True
        bad = ProjectionResult(
            instance=broken,
            notes=result.notes,
            field_provenance=result.field_provenance,
            creator_id=result.creator_id,
            registry_version=result.registry_version,
            asset_availability=result.asset_availability,
            timestamp=result.timestamp,
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                write_instance(bad, tmp)


if __name__ == "__main__":
    unittest.main()
