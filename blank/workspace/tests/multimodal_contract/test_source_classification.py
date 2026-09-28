"""Multi-role source classification and multi-signal tests."""

from __future__ import annotations

import copy
import unittest

from multimodal_creator import (
    DEFAULT_SIGNALS,
    MULTIMODAL_FAMILIES,
    SIGNAL_REQUIREMENTS,
    SOURCE_ROLES,
    MultimodalContractError,
    StructuralObservation,
    VisualSignal,
    build_multimodal_artifact,
    roles_of,
    signal_is_supported,
    sources_holding_role,
    structure_from_metadata,
    validate_multimodal_artifact,
)

from .fixtures import (
    image_structures,
    rich_observation,
    text_core,
    video_observation,
    video_structures,
)


class ImageMultiRoleTests(unittest.TestCase):
    """One source, several roles — never a single label."""

    def test_image_carries_multiple_roles(self) -> None:
        structure = image_structures()[0]
        self.assertGreaterEqual(len(structure.roles), 3)
        self.assertIn("knowledge_source", structure.roles)
        self.assertIn("visual_style_source", structure.roles)
        self.assertIn("layout_source", structure.roles)

    def test_one_image_answers_a_knowledge_and_a_layout_question(self) -> None:
        """The earnings-screenshot case from the contract."""

        structures = image_structures()
        self.assertEqual(sources_holding_role(structures, "knowledge_source"), ("img-1",))
        self.assertEqual(sources_holding_role(structures, "layout_source"), ("img-1",))

    def test_roles_are_returned_as_a_set_like_collection(self) -> None:
        structures = image_structures()
        self.assertEqual(set(roles_of(structures, "img-1")), set(structures[0].roles))

    def test_envelope_records_every_role_declared(self) -> None:
        artifact = build_multimodal_artifact(
            text_core(), structures=image_structures(), visual_capability="contract_only"
        )
        entry = artifact["multimodal_envelope"]["source_roles"][0]
        self.assertEqual(entry["source_id"], "img-1")
        self.assertEqual(set(entry["roles"]), set(image_structures()[0].roles))
        self.assertIn("visual", entry["modalities"])

    def test_all_declared_roles_come_from_the_contract_vocabulary(self) -> None:
        for structure in image_structures() + video_structures():
            for role in structure.roles:
                self.assertIn(role, SOURCE_ROLES)

    def test_image_defaults_to_a_visual_source(self) -> None:
        structure = structure_from_metadata("plain", "image")
        self.assertEqual(structure.modalities, ("visual",))
        self.assertIn("visual_style_source", structure.roles)

    def test_document_defaults_to_text(self) -> None:
        structure = structure_from_metadata("doc", "document")
        self.assertEqual(structure.modalities, ("textual",))
        self.assertEqual(structure.roles, ("knowledge_source",))

    def test_visual_role_without_visual_modality_is_rejected(self) -> None:
        with self.assertRaises(MultimodalContractError):
            structure_from_metadata(
                "doc",
                "document",
                {"modalities": ["textual"], "multimodal_roles": ["layout_source"]},
            )

    def test_visual_modality_without_a_visual_role_is_rejected(self) -> None:
        with self.assertRaises(MultimodalContractError):
            structure_from_metadata(
                "img",
                "image",
                {"modalities": ["visual"], "multimodal_roles": ["knowledge_source"]},
            )

    def test_image_text_must_be_marked_as_transcription(self) -> None:
        with self.assertRaises(MultimodalContractError):
            structure_from_metadata(
                "img",
                "image",
                {
                    "modalities": ["visual", "textual"],
                    "multimodal_roles": ["visual_style_source", "knowledge_source"],
                    "text_is_transcribed": False,
                },
            )

    def test_image_text_transcription_defaults_to_true(self) -> None:
        structure = structure_from_metadata(
            "img",
            "image",
            {
                "modalities": ["visual", "textual"],
                "multimodal_roles": ["visual_style_source", "knowledge_source"],
            },
        )
        self.assertTrue(structure.text_is_transcribed)

    def test_unknown_modality_is_rejected(self) -> None:
        with self.assertRaises(MultimodalContractError):
            structure_from_metadata(
                "img", "image", {"modalities": ["holographic"], "multimodal_roles": ["layout_source"]}
            )


class VideoMultiSignalTests(unittest.TestCase):
    """A video must be able to yield several signal families at once."""

    def test_video_observation_may_report_temporal_rhythm(self) -> None:
        observation = video_observation()
        self.assertIn("temporal_rhythm", observation.evidence_kinds)

    def test_image_observation_cannot_report_temporal_rhythm(self) -> None:
        with self.assertRaises(MultimodalContractError):
            StructuralObservation(
                observation_id="bad",
                medium="image",
                source_id="img-1",
                roles=["visual_style_source"],
                evidence_kinds=["temporal_rhythm"],
            )

    def test_video_produces_multiple_signal_families(self) -> None:
        artifact = build_multimodal_artifact(
            text_core(),
            structures=video_structures(),
            observations=[video_observation()],
            visual_capability="observed",
        )
        validate_multimodal_artifact(artifact)
        populated = [family for family in MULTIMODAL_FAMILIES if artifact[family]]
        self.assertGreaterEqual(len(populated), 3, populated)

    def test_video_layout_and_chart_are_both_present(self) -> None:
        artifact = build_multimodal_artifact(
            text_core(),
            structures=video_structures(),
            observations=[video_observation()],
            visual_capability="observed",
        )
        self.assertTrue(artifact["layout_patterns"])
        chart_types = [
            record["asset_pattern_type"] for record in artifact["asset_patterns"]
        ]
        self.assertIn("chart_pattern", chart_types)

    def test_video_geometry_uses_the_same_normalized_frame_as_images(self) -> None:
        artifact = build_multimodal_artifact(
            text_core(),
            structures=video_structures(),
            observations=[video_observation()],
            visual_capability="observed",
        )
        boxes = [
            region["box"]
            for region in artifact["visual_patterns"][0]["regions"]
        ]
        for box in boxes:
            for value in box.values():
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)


class EvidenceGatingTests(unittest.TestCase):
    """The builder must not invent structure an observation never reported."""

    def test_signal_requirements_are_declared_for_every_emitted_signal(self) -> None:
        for signal in DEFAULT_SIGNALS:
            self.assertIn(signal, SIGNAL_REQUIREMENTS, f"{signal} has no requirement entry")

    def test_missing_subject_class_skips_the_subject_pattern(self) -> None:
        observation = rich_observation(subject_class=None)
        self.assertFalse(
            signal_is_supported(observation, VisualSignal.SUBJECT_PATTERN)
        )

    def test_minimal_observation_yields_no_asset_claims(self) -> None:
        observation = StructuralObservation(
            observation_id="minimal",
            medium="image",
            source_id="img-1",
            roles=["visual_style_source"],
            evidence_kinds=["region_geometry"],
            regions=(
                {
                    "region_id": "r1",
                    "role": "background",
                    "box": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                    "layer_order": 0,
                },
            ),
        )
        artifact = build_multimodal_artifact(
            text_core(),
            structures=image_structures(),
            observations=[observation],
            visual_capability="observed",
        )
        # A bare background cannot justify a subject, chart or cover claim.
        self.assertEqual(artifact["asset_patterns"], [])
        self.assertEqual(artifact["layout_patterns"], [])
        for family in MULTIMODAL_FAMILIES:
            self.assertLessEqual(len(artifact[family]), 2, family)

    def test_chart_pattern_always_reports_a_chart_class(self) -> None:
        artifact = build_multimodal_artifact(
            text_core(),
            structures=image_structures(),
            observations=[rich_observation()],
            visual_capability="observed",
        )
        for record in artifact["asset_patterns"]:
            if record["asset_pattern_type"] == "chart_pattern":
                self.assertIn("chart_class", record)
                self.assertNotEqual(record["chart_class"], None)

    def test_observation_requires_at_least_one_role(self) -> None:
        with self.assertRaises(MultimodalContractError):
            StructuralObservation(
                observation_id="no-role",
                medium="image",
                source_id="img-1",
                roles=(),
                evidence_kinds=["region_geometry"],
            )

    def test_observation_requires_at_least_one_evidence_kind(self) -> None:
        with self.assertRaises(MultimodalContractError):
            StructuralObservation(
                observation_id="no-evidence",
                medium="image",
                source_id="img-1",
                roles=["visual_style_source"],
                evidence_kinds=(),
            )

    def test_unknown_medium_is_rejected(self) -> None:
        with self.assertRaises(MultimodalContractError):
            StructuralObservation(
                observation_id="audio",
                medium="audio",
                source_id="a-1",
                roles=["visual_style_source"],
                evidence_kinds=["region_geometry"],
            )

    def test_builder_does_not_mutate_the_base_artifact(self) -> None:
        base = text_core()
        before = copy.deepcopy(base)
        build_multimodal_artifact(
            base,
            structures=image_structures(),
            observations=[rich_observation()],
            visual_capability="observed",
        )
        self.assertEqual(base, before)


if __name__ == "__main__":
    unittest.main()
