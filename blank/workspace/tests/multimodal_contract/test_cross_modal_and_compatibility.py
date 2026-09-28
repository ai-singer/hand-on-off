"""Cross-modal relation tests: text and visual expressed together."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from multimodal_creator import (
    ALIGNMENT_RELATIONS,
    MULTIMODAL_FAMILIES,
    TEXT_SIGNALS,
    MultimodalContractError,
    build_cross_modal_records,
    build_multimodal_artifact,
    merge_multimodal_artifact,
    project_text_core,
    validate_multimodal_artifact,
)
from multimodal_creator.builder import BASELINE_SCHEMA_NAME, SCHEMA_DIR

from .fixtures import (
    BASELINE_SCHEMA,
    WORKSPACE_ROOT_SCHEMA,
    image_structures,
    rich_observation,
    text_core,
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = WORKSPACE_ROOT / BASELINE_SCHEMA


def cross_modal_artifact() -> dict:
    """The contract's worked example: red warning ground, three cards, left/right.

    Built in two steps on purpose. The first pass produces the visual facts, so
    the cross-modal records can reference real ``pattern_id`` values instead of
    placeholders — a cross-modal claim must point at structure that exists.
    """

    observation = rich_observation()
    visual_only = build_multimodal_artifact(
        text_core(),
        structures=image_structures(),
        observations=[observation],
        visual_capability="observed",
    )
    layout_id = visual_only["layout_patterns"][0]["pattern_id"]
    visual_id = visual_only["visual_patterns"][0]["pattern_id"]
    examples = [
        {
            "text_signal": "topic_candidate",
            "text_role": "title",
            "relation": "reinforces",
            "visual_family": "layout_patterns",
            "visual_pattern_id": layout_id,
            "visual_evidence": ["region_layout", "dominance_order"],
            "source_ids": ["img-1"],
            "excerpt": "3 mistakes investors make",
        },
        {
            "text_signal": "topic_candidate",
            "text_role": "hook",
            "relation": "reinforces",
            "visual_family": "layout_patterns",
            "visual_pattern_id": layout_id,
            "visual_evidence": ["region_layout"],
            "source_ids": ["img-1"],
            "builder": "hook_visual_alignment",
        },
        {
            "text_signal": "content_template",
            "text_role": "body",
            "relation": "sequences",
            "visual_family": "visual_patterns",
            "visual_pattern_id": visual_id,
            "visual_evidence": ["region_layout", "reading_order"],
            "source_ids": ["img-1"],
            "builder": "page_sequence_pattern",
            "page_sequence": [
                {
                    "page_index": 0,
                    "sequence_role": "opener",
                    "layout_template": "image_left_text_right",
                    "reading_anchor": "r-title",
                    "display_density": "sparse",
                },
                {
                    "page_index": 1,
                    "sequence_role": "proof",
                    "layout_template": "three_card",
                    "reading_anchor": "r-chart",
                    "display_density": "balanced",
                },
                {
                    "page_index": 2,
                    "sequence_role": "cta",
                    "layout_template": "single_column",
                    "reading_anchor": "r-title",
                    "display_density": "sparse",
                },
            ],
        },
    ]
    return build_multimodal_artifact(
        text_core(),
        structures=image_structures(),
        observations=[observation],
        cross_modal=examples,
        visual_capability="observed",
    )


class CrossModalRelationTests(unittest.TestCase):
    """A cross-modal record must bind text and visual together."""

    def test_text_image_relation_is_expressible(self) -> None:
        artifact = cross_modal_artifact()
        validate_multimodal_artifact(artifact)
        alignments = [
            record
            for record in artifact["cross_modal_patterns"]
            if record["cross_modal_type"] == "text_visual_alignment"
        ]
        self.assertTrue(alignments)

    def test_alignment_carries_both_anchors(self) -> None:
        artifact = cross_modal_artifact()
        for record in artifact["cross_modal_patterns"]:
            self.assertIn(record["text_anchor"]["text_signal"], TEXT_SIGNALS)
            self.assertTrue(record["visual_anchor"]["evidence_kinds"])
            self.assertIn(
                record["visual_anchor"]["family"],
                {"visual_patterns", "layout_patterns", "asset_patterns"},
            )

    def test_hook_alignment_anchors_the_hook_text_role(self) -> None:
        artifact = cross_modal_artifact()
        hooks = [
            record
            for record in artifact["cross_modal_patterns"]
            if record["cross_modal_type"] == "hook_visual_alignment"
        ]
        self.assertTrue(hooks)
        for record in hooks:
            self.assertEqual(record["text_anchor"]["text_role"], "hook")

    def test_hook_alignment_without_hook_role_is_rejected(self) -> None:
        artifact = cross_modal_artifact()
        for record in artifact["cross_modal_patterns"]:
            if record["cross_modal_type"] == "hook_visual_alignment":
                record["text_anchor"]["text_role"] = "body"
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_text_only_cross_modal_record_is_rejected(self) -> None:
        artifact = cross_modal_artifact()
        artifact["cross_modal_patterns"][0]["visual_anchor"]["evidence_kinds"] = []
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_visual_only_cross_modal_record_is_rejected(self) -> None:
        artifact = cross_modal_artifact()
        del artifact["cross_modal_patterns"][0]["text_anchor"]
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_cross_modal_record_grounded_only_in_ocr_is_rejected(self) -> None:
        artifact = cross_modal_artifact()
        artifact["cross_modal_patterns"][0]["visual_anchor"]["evidence_kinds"] = [
            "ocr_text"
        ]
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_unknown_relation_is_rejected(self) -> None:
        artifact = cross_modal_artifact()
        artifact["cross_modal_patterns"][0]["relation"] = "vibes"
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_relation_vocabulary_is_exposed_and_closed(self) -> None:
        self.assertIn("reinforces", ALIGNMENT_RELATIONS)
        self.assertIn("contrasts", ALIGNMENT_RELATIONS)
        self.assertNotIn("vibes", ALIGNMENT_RELATIONS)

    def test_builder_rejects_a_text_only_signal(self) -> None:
        with self.assertRaises(MultimodalContractError):
            build_cross_modal_records(
                text_signal="topic_candidate",
                text_role="title",
                relation="reinforces",
                visual_family="layout_patterns",
                visual_pattern_id="p",
                visual_evidence=[],
                source_ids=["img-1"],
            )

    def test_builder_rejects_an_unknown_text_signal(self) -> None:
        with self.assertRaises(MultimodalContractError):
            build_cross_modal_records(
                text_signal="not_a_signal",
                text_role="title",
                relation="reinforces",
                visual_family="layout_patterns",
                visual_pattern_id="p",
                visual_evidence=["region_layout"],
                source_ids=["img-1"],
            )

    def test_builder_rejects_a_non_visual_anchor_family(self) -> None:
        with self.assertRaises(MultimodalContractError):
            build_cross_modal_records(
                text_signal="topic_candidate",
                text_role="title",
                relation="reinforces",
                visual_family="cross_modal_patterns",
                visual_pattern_id="p",
                visual_evidence=["region_layout"],
                source_ids=["img-1"],
            )

    def test_text_style_pattern_alias_resolves_to_the_canonical_signal(self) -> None:
        records = build_cross_modal_records(
            text_signal="style_pattern",
            text_role="body",
            relation="illustrates",
            visual_family="visual_patterns",
            visual_pattern_id="p",
            visual_evidence=["type_scale_relation"],
            source_ids=["img-1"],
        )
        _family, record = records[0]
        self.assertEqual(record["text_anchor"]["text_signal"], "text_style_pattern")


class PageSequenceTests(unittest.TestCase):
    """Multi-page visual rhythm must be representable and ordered."""

    def test_page_sequence_pattern_is_present(self) -> None:
        artifact = cross_modal_artifact()
        sequences = [
            record
            for record in artifact["cross_modal_patterns"]
            if record["cross_modal_type"] == "page_sequence_pattern"
        ]
        self.assertTrue(sequences)

    def test_page_sequence_records_roles_per_page(self) -> None:
        artifact = cross_modal_artifact()
        record = next(
            item
            for item in artifact["cross_modal_patterns"]
            if item["cross_modal_type"] == "page_sequence_pattern"
        )
        roles = [page["sequence_role"] for page in record["page_sequence"]]
        self.assertEqual(roles, ["opener", "proof", "cta"])
        indexes = [page["page_index"] for page in record["page_sequence"]]
        self.assertEqual(indexes, sorted(indexes))

    def test_page_sequence_requires_pages(self) -> None:
        artifact = cross_modal_artifact()
        for record in artifact["cross_modal_patterns"]:
            if record["cross_modal_type"] == "page_sequence_pattern":
                record["page_sequence"] = []
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_unknown_sequence_role_is_rejected(self) -> None:
        artifact = cross_modal_artifact()
        record = next(
            item
            for item in artifact["cross_modal_patterns"]
            if item["cross_modal_type"] == "page_sequence_pattern"
        )
        record["page_sequence"][0]["sequence_role"] = "filler"
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)

    def test_page_display_density_uses_the_closed_vocabulary(self) -> None:
        artifact = cross_modal_artifact()
        record = next(
            item
            for item in artifact["cross_modal_patterns"]
            if item["cross_modal_type"] == "page_sequence_pattern"
        )
        record["page_sequence"][0]["display_density"] = "extremely dense"
        with self.assertRaises(MultimodalContractError):
            validate_multimodal_artifact(artifact)


class CompatibilityTests(unittest.TestCase):
    """The extension must not break the existing text-only artifact."""

    def test_text_only_artifact_still_validates_against_the_new_schema(self) -> None:
        from core.schema_validation import validate_schema_instance

        # A text-only artifact has none of the added families, and the added
        # families are optional, so it validates unchanged.
        artifact = text_core()
        validate_schema_instance(
            artifact,
            WORKSPACE_ROOT / WORKSPACE_ROOT_SCHEMA,
            root_name="artifact",
        )

    def test_merged_artifact_keeps_the_text_signals_byte_identical(self) -> None:
        base = text_core()
        artifact = cross_modal_artifact()
        merged = merge_multimodal_artifact(base, artifact)
        for field in (
            "topic_candidate",
            "content_template",
            "knowledge_unit",
            "style_pattern",
            "risk_constraints",
            "evaluation_result",
            "plugin",
        ):
            self.assertEqual(merged[field], base[field], f"{field} was altered")

    def test_merged_artifact_text_core_validates_against_the_unmodified_baseline(
        self,
    ) -> None:
        from core.schema_validation import validate_schema_instance

        merged = merge_multimodal_artifact(text_core(), cross_modal_artifact())
        core = project_text_core(merged)
        validate_schema_instance(core, BASELINE_PATH, root_name="artifact")

    def test_projection_drops_only_the_added_surface(self) -> None:
        merged = merge_multimodal_artifact(text_core(), cross_modal_artifact())
        core = project_text_core(merged)
        added = set(MULTIMODAL_FAMILIES) | {
            "multimodal_envelope",
            "creator_extension",
        }
        self.assertFalse(added & set(core))
        self.assertEqual(set(core), set(text_core()))

    def test_baseline_schema_is_unmodified(self) -> None:
        """The multimodal track must not have edited the existing artifact schema."""

        payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        self.assertFalse(payload.get("additionalProperties", True))
        for family in MULTIMODAL_FAMILIES:
            self.assertNotIn(
                family,
                payload["properties"],
                "the baseline text-only schema must not gain multimodal fields",
            )
        self.assertNotIn("multimodal_envelope", payload["properties"])
        self.assertNotIn("creator_extension", payload["properties"])

    def test_baseline_schema_discovered_by_the_builder_is_the_shipped_one(self) -> None:
        self.assertEqual(SCHEMA_DIR / BASELINE_SCHEMA_NAME, BASELINE_PATH)

    def test_merge_rejects_a_broken_text_core(self) -> None:
        """A multimodal extension cannot rescue a text core missing a baseline field."""

        broken = copy.deepcopy(cross_modal_artifact())
        del broken["knowledge_unit"]
        with self.assertRaises(MultimodalContractError):
            merge_multimodal_artifact(text_core(), broken)

    def test_merge_reports_a_missing_baseline_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.json"
            with self.assertRaises(MultimodalContractError):
                merge_multimodal_artifact(
                    text_core(),
                    cross_modal_artifact(),
                    baseline_schema_path=missing,
                )

    def test_merge_rejects_an_invalid_multimodal_extension(self) -> None:
        artifact = cross_modal_artifact()
        artifact["visual_patterns"][0]["evidence_kinds"] = ["ocr_text"]
        with self.assertRaises(MultimodalContractError):
            merge_multimodal_artifact(text_core(), artifact)

    def test_contract_only_artifact_keeps_families_empty_but_present(self) -> None:
        artifact = build_multimodal_artifact(
            text_core(), structures=image_structures(), visual_capability="contract_only"
        )
        validate_multimodal_artifact(artifact)
        for family in MULTIMODAL_FAMILIES:
            self.assertEqual(artifact[family], [])


if __name__ == "__main__":
    unittest.main()
