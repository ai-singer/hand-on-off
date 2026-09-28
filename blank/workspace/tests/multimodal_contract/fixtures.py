"""Shared builders for Phase M1 multimodal contract tests.

Fixtures are constructed in memory and describe *structure only*. No image, no
video, no external asset, and no model output is involved anywhere in these
tests, which is the point: Phase M1 builds a protocol, not a capability.
"""

from __future__ import annotations

from typing import Any

from multimodal_creator import StructuralObservation, structure_from_metadata

WORKSPACE_ROOT_SCHEMA = "schemas/multimodal_artifact.schema.json"
BASELINE_SCHEMA = "schemas/unified_distillation_artifact.json"


def text_core() -> dict[str, Any]:
    """A minimal but complete text-only artifact, matching the baseline shape."""

    return {
        "artifact_version": "1.0.0",
        "plugin": {
            "name": "fixture_creator",
            "version": "1.0.0",
            "domain": "general",
            "creator_target": "short_form_cards",
        },
        "topic_candidate": [
            {
                "label": "3 mistakes investors make",
                "rationale": "Repeated framing across the source set.",
                "source_ids": ["img-1"],
                "confidence": 0.7,
                "origin": "common",
            }
        ],
        "content_template": [
            {
                "name": "three-card-listicle",
                "sections": ["hook", "mistake-one", "mistake-two", "mistake-three"],
                "source_ids": ["img-1"],
                "origin": "common",
            }
        ],
        "knowledge_unit": [
            {
                "statement": "Fees compound against long-horizon returns.",
                "evidence_refs": [{"source_id": "img-1", "source_type": "image"}],
                "confidence": 0.65,
                "origin": "common",
            }
        ],
        "style_pattern": [
            {
                "name": "direct-address",
                "attributes": ["second-person", "short-sentences"],
                "source_ids": ["img-1"],
                "origin": "common",
            }
        ],
        "domain_extension": {},
        "risk_constraints": [],
        "evaluation_result": {
            "common": {"score": 0.8, "checks": {"shape": True}, "passed": True},
            "domain": {},
        },
    }


def image_structures() -> list:
    """One earnings screenshot carrying four roles at once."""

    return [
        structure_from_metadata(
            "img-1",
            "image",
            {
                "modalities": ["visual", "textual"],
                "multimodal_roles": [
                    "knowledge_source",
                    "visual_style_source",
                    "layout_source",
                    "typography_source",
                ],
                "text_is_transcribed": True,
            },
        )
    ]


def rich_observation(**overrides: Any) -> StructuralObservation:
    """An observation carrying every structural field the taxonomy can use."""

    fields: dict[str, Any] = {
        "observation_id": "obs-1",
        "medium": "image",
        "source_id": "img-1",
        "roles": ["visual_style_source", "layout_source"],
        "evidence_kinds": [
            "region_layout",
            "region_geometry",
            "color_distribution",
            "dominance_order",
        ],
        "regions": (
            {
                "region_id": "r-bg",
                "role": "background",
                "box": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                "layer_order": 0,
            },
            {
                "region_id": "r-title",
                "role": "title",
                "box": {"x": 0.06, "y": 0.08, "w": 0.88, "h": 0.18},
                "layer_order": 1,
            },
            {
                "region_id": "r-chart",
                "role": "chart",
                "box": {"x": 0.08, "y": 0.34, "w": 0.5, "h": 0.4},
                "layer_order": 1,
            },
        ),
        "layout_template_class": "image_left_text_right",
        "alignment": "left",
        "density": "balanced",
        "palette_relation": "high_contrast_accent",
        "type_scale_relation": "two_level",
        "subject_class": "document_scan",
        "chart_class": "bar",
        "cover_role": "article_cover",
        "placement": "side_panel",
        "recurrence": 100,
        "confidence": 0.72,
    }
    fields.update(overrides)
    return StructuralObservation(**fields)


def video_observation(**overrides: Any) -> StructuralObservation:
    """A video observation, which may report temporal rhythm."""

    fields: dict[str, Any] = {
        "observation_id": "obs-video-1",
        "medium": "video",
        "source_id": "vid-1",
        "roles": ["visual_style_source", "sequence_source", "chart_source"],
        "evidence_kinds": [
            "region_layout",
            "temporal_rhythm",
            "chart_encoding",
            "subject_salience",
        ],
        "regions": (
            {
                "region_id": "v-bg",
                "role": "background",
                "box": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},
                "layer_order": 0,
            },
            {
                "region_id": "v-chart",
                "role": "chart",
                "box": {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.5},
                "layer_order": 1,
            },
        ),
        "layout_template_class": "full_bleed_overlay",
        "alignment": "center",
        "density": "dense",
        "chart_class": "line",
        "subject_class": "data_chart",
        "recurrence": 24,
        "confidence": 0.68,
    }
    fields.update(overrides)
    return StructuralObservation(**fields)


def video_structures() -> list:
    return [
        structure_from_metadata(
            "vid-1",
            "video",
            {
                "modalities": ["visual", "temporal", "textual"],
                "multimodal_roles": [
                    "visual_style_source",
                    "sequence_source",
                    "chart_source",
                    "hook_source",
                ],
                "text_is_transcribed": True,
            },
        )
    ]
