"""Schema and contract-boundary tests for the multimodal artifact.

Covers: JSON validity, required fields, the visual/text boundary, layout as an
independent fact, and the universal/plugin authority split.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from multimodal_creator import (
    CROSS_MODAL_TYPES,
    MULTIMODAL_CONTRACT_VERSION,
    PLUGIN_MAY_NOT_REDEFINE,
    REGION_ROLES,
    SIGNAL_BINDING,
    TEXT_SIGNALS,
    VISUAL_PATTERN_TYPES,
    VisualSignal,
    build_multimodal_artifact,
    layout_exists_independently,
    merge_creator_extension,
    text_signals_are_not_visual,
    validate_multimodal_artifact,
)
from multimodal_creator.taxonomy import MultimodalContractError

from .fixtures import (
    BASELINE_SCHEMA,
    WORKSPACE_ROOT_SCHEMA,
    image_structures,
    rich_observation,
    text_core,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = WORKSPACE_ROOT / WORKSPACE_ROOT_SCHEMA
BASELINE_PATH = WORKSPACE_ROOT / BASELINE_SCHEMA


def observed_artifact() -> dict:
    return build_multimodal_artifact(
        text_core(),
        structures=image_structures(),
        observations=[rich_observation()],
        visual_capability="observed",
    )


class SchemaDocumentTests(unittest.TestCase):
    """The schema file itself must be a valid, parsable contract."""

    def test_schema_is_valid_json(self) -> None:
        payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["title"], "MultimodalDistillationArtifact")

    def test_schema_stays_inside_dependency_free_subset(self) -> None:
        """No $ref/allOf/oneOf/if-then: the project validator cannot read them."""

        raw = SCHEMA_PATH.read_text(encoding="utf-8")
        payload = json.loads(raw)
        for unsupported in ("$ref", "allOf", "anyOf", "oneOf", "if", "then", "not"):
            self.assertNotIn(
                f'"{unsupported}"',
                raw,
                f"schema must not use {unsupported!r}; the runtime validator cannot resolve it",
            )
        self.assertFalse(payload.get("additionalProperties", True))

    def test_schema_declares_the_four_added_families(self) -> None:
        payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        properties = payload["properties"]
        for family in (
            "visual_patterns",
            "layout_patterns",
            "asset_patterns",
            "cross_modal_patterns",
        ):
            self.assertIn(family, properties, f"{family} missing from schema")

    def test_schema_preserves_the_text_signals(self) -> None:
        """The extension must not drop or rename the existing text signals."""

        payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        for field in baseline["required"]:
            self.assertIn(field, payload["properties"], f"baseline field {field} lost")
        # ``style_pattern`` is the stored name of the text_style_pattern signal.
        self.assertIn("style_pattern", payload["properties"])
        self.assertIn("text_style_pattern", TEXT_SIGNALS)

    def test_schema_only_adds_optional_families(self) -> None:
        """Required fields are exactly the baseline set, so old artifacts pass."""

        payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(sorted(payload["required"]), sorted(baseline["required"]))

    def test_added_families_match_the_contract_vocabulary(self) -> None:
        payload = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        visual_types = payload["properties"]["visual_patterns"]["items"]["properties"][
            "visual_pattern_type"
        ]["enum"]
        cross_types = payload["properties"]["cross_modal_patterns"]["items"][
            "properties"
        ]["cross_modal_type"]["enum"]
        self.assertEqual(sorted(visual_types), sorted(VISUAL_PATTERN_TYPES))
        self.assertEqual(sorted(cross_types), sorted(CROSS_MODAL_TYPES))


class RequiredFieldTests(unittest.TestCase):
    """Required fields must be enforced, not merely documented."""

    def test_complete_observed_artifact_validates(self) -> None:
        validate_multimodal_artifact(observed_artifact())

    def test_missing_baseline_field_is_rejected(self) -> None:
        artifact = observed_artifact()
        del artifact["knowledge_unit"]
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_missing_envelope_field_is_rejected(self) -> None:
        artifact = observed_artifact()
        del artifact["multimodal_envelope"]["visual_capability"]
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_unknown_top_level_field_is_rejected(self) -> None:
        artifact = observed_artifact()
        artifact["surprise"] = True
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_unknown_region_role_is_rejected(self) -> None:
        artifact = observed_artifact()
        artifact["visual_patterns"][0]["regions"] = [
            {
                "region_id": "weird",
                "role": "canvas",
                "box": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                "layer_order": 0,
            }
        ]
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_region_role_vocabulary_is_closed_and_exposed(self) -> None:
        self.assertIn("background", REGION_ROLES)
        self.assertIn("title", REGION_ROLES)
        self.assertNotIn("canvas", REGION_ROLES)

    def test_out_of_frame_geometry_is_rejected(self) -> None:
        artifact = observed_artifact()
        artifact["visual_patterns"][0]["regions"] = [
            {
                "region_id": "overflow",
                "role": "title",
                "box": {"x": 0.9, "y": 0.0, "w": 0.5, "h": 0.2},
                "layer_order": 0,
            }
        ]
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_multimodal_families_without_envelope_are_rejected(self) -> None:
        artifact = observed_artifact()
        del artifact["multimodal_envelope"]
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_observed_capability_requires_visual_families(self) -> None:
        artifact = observed_artifact()
        artifact["layout_patterns"] = []
        artifact["asset_patterns"] = []
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)


class VisualTextBoundaryTests(unittest.TestCase):
    """Visual distillation must not degrade into OCR."""

    def test_record_grounded_only_in_ocr_is_rejected(self) -> None:
        artifact = observed_artifact()
        for family in ("visual_patterns", "layout_patterns", "asset_patterns"):
            record = copy.deepcopy(artifact[family][0])
            record["evidence_kinds"] = ["ocr_text"]
            mutated = copy.deepcopy(artifact)
            mutated[family] = [record]
            with self.assertRaises(MultimodalContractError):
                validate_multimodal_artifact(mutated)

    def test_ocr_may_accompany_structural_evidence(self) -> None:
        artifact = observed_artifact()
        artifact["visual_patterns"][0]["evidence_kinds"] = [
            "region_layout",
            "ocr_text",
        ]
        validate_multimodal_artifact(artifact)

    def test_text_signal_smuggled_into_visual_family_is_caught(self) -> None:
        artifact = observed_artifact()
        artifact["visual_patterns"][0]["label"] = "3 mistakes investors make"
        self.assertFalse(text_signals_are_not_visual(artifact))
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_visual_record_claiming_a_text_signal_type_is_caught(self) -> None:
        artifact = observed_artifact()
        artifact["asset_patterns"][0]["asset_pattern_type"] = "knowledge_unit"
        self.assertFalse(text_signals_are_not_visual(artifact))

    def test_text_signal_carrying_visual_fields_is_caught(self) -> None:
        artifact = observed_artifact()
        artifact["knowledge_unit"][0]["evidence_kinds"] = ["region_layout"]
        self.assertFalse(text_signals_are_not_visual(artifact))

    def test_clean_artifact_passes_the_boundary_check(self) -> None:
        artifact = observed_artifact()
        self.assertTrue(text_signals_are_not_visual(artifact))


class LayoutIndependenceTests(unittest.TestCase):
    """Layout must be a first-class structural fact, not a text by-product."""

    def test_layout_records_exist_without_any_text_anchor(self) -> None:
        artifact = observed_artifact()
        self.assertTrue(artifact["layout_patterns"])
        self.assertTrue(layout_exists_independently(artifact))

    def test_layout_record_carries_a_region_grid(self) -> None:
        artifact = observed_artifact()
        grid = artifact["layout_patterns"][0]["region_grid"]
        self.assertIn("columns", grid)
        self.assertIn("rows", grid)
        self.assertTrue(grid["regions"])
        for region in grid["regions"]:
            self.assertIn("role", region)
            self.assertIn("box", region)
            self.assertIn("layer_order", region)

    def test_layout_reading_order_must_reference_declared_regions(self) -> None:
        artifact = observed_artifact()
        artifact["layout_patterns"][0]["reading_order"] = ["not-a-region"]
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_layout_template_class_comes_from_the_closed_vocabulary(self) -> None:
        artifact = observed_artifact()
        artifact["layout_patterns"][0]["template_class"] = "vibes"
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_layout_declares_the_layout_template_pattern_type(self) -> None:
        artifact = observed_artifact()
        self.assertEqual(
            artifact["layout_patterns"][0]["visual_pattern_type"], "layout_template"
        )


class UniversalPluginAuthorityTests(unittest.TestCase):
    """Structure is universal; domain meaning is the plugin's job."""

    def test_structural_records_are_universal_layer(self) -> None:
        artifact = observed_artifact()
        for family in (
            "visual_patterns",
            "layout_patterns",
            "asset_patterns",
            "cross_modal_patterns",
        ):
            for record in artifact[family]:
                self.assertEqual(record["layer"], "universal")

    def test_plugin_origin_universal_record_is_rejected(self) -> None:
        artifact = observed_artifact()
        artifact["visual_patterns"][0]["origin"] = "plugin"
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_plugin_may_attach_domain_meaning(self) -> None:
        artifact = observed_artifact()
        pattern_id = artifact["asset_patterns"][0]["pattern_id"]
        extended = merge_creator_extension(
            artifact,
            plugin="xiaolin_finance",
            domain_vocabulary={"attention": ["earnings_surprise", "guidance_cut"]},
            pattern_bindings=[
                {
                    "pattern_id": pattern_id,
                    "family": "asset_patterns",
                    "domain_meaning": "Financial charts carry the load-bearing claim.",
                    "attention_hints": ["read the axis before the headline"],
                }
            ],
        )
        validate_multimodal_artifact(extended)
        self.assertEqual(extended["creator_extension"]["plugin"], "xiaolin_finance")

    def test_plugin_binding_must_name_a_real_family(self) -> None:
        artifact = observed_artifact()
        with self.assertRaises(MultimodalContractError):
            merge_creator_extension(
                artifact,
                plugin="xiaolin_finance",
                pattern_bindings=[
                    {
                        "pattern_id": "p",
                        "family": "plugin_invented_family",
                        "domain_meaning": "nope",
                    }
                ],
            )

    def test_plugin_binding_must_state_domain_meaning(self) -> None:
        artifact = observed_artifact()
        with self.assertRaises(MultimodalContractError):
            merge_creator_extension(
                artifact,
                plugin="xiaolin_finance",
                pattern_bindings=[
                    {"pattern_id": "p", "family": "asset_patterns", "domain_meaning": "  "}
                ],
            )

    def test_plugin_extension_must_acknowledge_universal_vocabulary(self) -> None:
        artifact = observed_artifact()
        extended = merge_creator_extension(artifact, plugin="xiaolin_finance")
        declared = set(extended["creator_extension"]["may_not_redefine"])
        self.assertTrue(set(PLUGIN_MAY_NOT_REDEFINE).issubset(declared))
        self.assertIn("layout_template_class_vocabulary", declared)

    def test_extension_dropping_the_acknowledgement_is_rejected(self) -> None:
        from multimodal_creator import assert_creator_extension_is_interpretive

        artifact = observed_artifact()
        extended = merge_creator_extension(artifact, plugin="xiaolin_finance")
        extended["creator_extension"]["may_not_redefine"] = []
        with self.assertRaises(MultimodalContractError):
            assert_creator_extension_is_interpretive(extended["creator_extension"])

    def test_plugin_cannot_add_a_region_role(self) -> None:
        """A domain vocabulary is free-form, but it cannot extend region roles."""

        artifact = observed_artifact()
        extended = merge_creator_extension(
            artifact,
            plugin="xiaolin_finance",
            domain_vocabulary={"region_role": ["earnings_banner"]},
        )
        # The vocabulary is stored as interpretation...
        self.assertIn("earnings_banner", extended["creator_extension"]["domain_vocabulary"]["region_role"])
        # ...but the universal region vocabulary is untouched, so a record using
        # the invented role is still rejected.
        extended["visual_patterns"][0]["regions"] = [
            {
                "region_id": "banner",
                "role": "earnings_banner",
                "box": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.1},
                "layer_order": 0,
            }
        ]
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(extended)


class SignalBindingTests(unittest.TestCase):
    """Named signals must map onto stored families without ambiguity."""

    def test_every_named_signal_binds_to_a_family(self) -> None:
        for signal in VisualSignal:
            self.assertIn(signal, SIGNAL_BINDING, f"{signal} has no stored binding")

    def test_contract_version_is_declared_in_the_envelope(self) -> None:
        artifact = observed_artifact()
        self.assertEqual(
            artifact["multimodal_envelope"]["contract_version"],
            MULTIMODAL_CONTRACT_VERSION,
        )

    def test_geometry_units_are_normalized(self) -> None:
        artifact = observed_artifact()
        self.assertEqual(
            artifact["multimodal_envelope"]["geometry_units"], "normalized_xywh"
        )

    def test_motif_policy_defaults_to_aggregate_only(self) -> None:
        """No source asset bytes or references are stored by default."""

        artifact = observed_artifact()
        self.assertEqual(
            artifact["multimodal_envelope"]["motif_policy"], "aggregate_only"
        )

    def test_record_filed_under_the_wrong_family_is_rejected(self) -> None:
        artifact = observed_artifact()
        artifact["asset_patterns"][0]["asset_pattern_type"] = "layout_template"
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)


if __name__ == "__main__":
    unittest.main()
