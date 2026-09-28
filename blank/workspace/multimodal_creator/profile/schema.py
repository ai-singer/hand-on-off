"""JSON Schema for the Visual Creator Profile (Phase M5, Task 1).

The schema is defined **in Python and generated from the model's own
vocabularies**, then written out. Defining it as a literal JSON blob would let it
drift from the model silently; deriving it means a vocabulary change cannot leave
the two disagreeing.

Like the M1 artifact schema, this is deliberately confined to the dependency-free
validator subset already in the project (``type``, ``enum``, ``required``,
``properties``, ``additionalProperties``, ``items``, ``minItems``) — no ``$ref``,
``allOf``, ``oneOf``, or ``if``/``then``. Semantic rules that subset cannot
express (provenance completeness, the anti-generation and anti-override
prohibitions) are enforced in :mod:`multimodal_creator.profile.validation`.

The schema is strict at every level — ``additionalProperties: false`` throughout.
That is what makes the anti-generation guarantee structural: there is no place to
put a prompt, a model reference, or an image, so such a document is rejected by
shape before any semantic check runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .model import (
    ATTENTION_SLOTS,
    COMPLEXITY_LEVELS,
    DERIVATIONS,
    HIERARCHY_TIERS,
    PROFILE_VERSION,
    PROVENANCE_FAMILIES,
    SOURCE_PHASES,
    VISUAL_LANGUAGES,
)

#: Where the generated schema is written, following the project's ``schemas/``
#: convention without modifying any existing schema file there.
SCHEMA_FILENAME = "visual_creator_profile.schema.json"

#: Names that must never appear as a key anywhere in a profile document.
#:
#: Kept here rather than in the validator so the schema, the validator, and the
#: tests all read one list. Every entry is something M5 must not carry: generation
#: instructions, model wiring, or publish/deploy configuration.
FORBIDDEN_KEYS: tuple[str, ...] = (
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
    "generation_model",
    "model",
    "model_id",
    "model_reference",
    "diffusion",
    "checkpoint",
    "lora",
    "seed",
    "steps",
    "cfg_scale",
    "sampler",
    "image",
    "images",
    "image_data",
    "image_bytes",
    "pixels",
    "bitmap",
    "base64",
    "asset_path",
    "asset_reference",
    "publish",
    "publish_target",
    "deploy",
    "deployment",
    "endpoint",
    "api_key",
    "credentials",
    "webhook",
)


def _string_array(values: tuple[str, ...]) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string", "enum": list(values)}}


def _provenance_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "source",
            "derivation",
            "confidence",
            "evidence",
        ],
        "properties": {
            "source": {
                "type": "object",
                "additionalProperties": False,
                "required": ["phase", "artifact", "artifact_kind"],
                "properties": {
                    "phase": {"type": "string", "enum": list(SOURCE_PHASES)},
                    "artifact": {"type": "string"},
                    "artifact_kind": {"type": "string"},
                },
            },
            "derivation": {"type": "string", "enum": list(DERIVATIONS)},
            "confidence": {"type": "number"},
            "evidence": {"type": "object"},
        },
    }


def build_schema() -> dict[str, Any]:
    """Build the profile JSON Schema from the model's vocabularies."""

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://creator-agent.local/schemas/visual_creator_profile.schema.json",
        "title": "VisualCreatorProfile",
        "description": (
            "A stable configuration asset derived from Phase M4 visual distillation "
            "output, for consumption by a Creator Instance Factory. Contains no "
            "generation logic: prompts, model references, image data, and publish "
            "targets are rejected by shape."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": [
            "profile_version",
            "profile_id",
            "creator_id",
            "source_pattern_ids",
            "support",
            "confidence",
            "visual_identity",
            "composition_rules",
            "attention_strategy",
            "hierarchy_pattern",
            "constraints",
            "provenance",
            "notes",
        ],
        "properties": {
            "profile_version": {"type": "string"},
            "profile_id": {"type": "string"},
            "creator_id": {"type": "string"},
            "source_pattern_ids": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
            "support": {"type": "integer"},
            "confidence": {"type": "number"},
            "visual_identity": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "style_family",
                    "visual_language",
                    "complexity",
                    "density",
                    "contrast",
                    "framing",
                    "typography",
                ],
                "properties": {
                    "style_family": {"type": "string"},
                    "visual_language": {
                        "type": "string",
                        "enum": list(VISUAL_LANGUAGES),
                    },
                    "complexity": {"type": "string", "enum": list(COMPLEXITY_LEVELS)},
                    "density": {"type": "string"},
                    "contrast": {"type": "string"},
                    "framing": {"type": "string"},
                    "typography": {"type": "string"},
                },
            },
            "composition_rules": {
                "type": "object",
                "additionalProperties": False,
                "required": ["preferred", "forbidden"],
                "properties": {
                    "preferred": {"type": "array", "items": {"type": "string"}},
                    "forbidden": {"type": "array", "items": {"type": "string"}},
                },
            },
            # Only the first slot/tier is required by shape. How many are filled
            # depends on how many attention stages and delivery stages M4 actually
            # evidenced, and the model enforces that they are contiguous from the
            # start — a rule the validator subset cannot express, so it lives in
            # ``profile.validation``.
            "attention_strategy": {
                "type": "object",
                "additionalProperties": False,
                "required": list(ATTENTION_SLOTS[:1]),
                "properties": {
                    slot: {"type": "string"} for slot in ATTENTION_SLOTS
                },
            },
            "hierarchy_pattern": {
                "type": "object",
                "additionalProperties": False,
                "required": list(HIERARCHY_TIERS[:1]),
                "properties": {
                    tier: {"type": "string"} for tier in HIERARCHY_TIERS
                },
            },
            "constraints": {
                "type": "object",
                "additionalProperties": False,
                "required": ["must_have", "avoid"],
                "properties": {
                    "must_have": {"type": "array", "items": {"type": "string"}},
                    "avoid": {"type": "array", "items": {"type": "string"}},
                },
            },
            "provenance": {
                "type": "object",
                "additionalProperties": False,
                "required": list(PROVENANCE_FAMILIES),
                "properties": {
                    family: _provenance_schema() for family in PROVENANCE_FAMILIES
                },
            },
            "notes": {"type": "array", "items": {"type": "string"}},
        },
    }


def schema_keys() -> frozenset[str]:
    """Top-level keys the schema declares."""

    return frozenset(build_schema()["properties"])


def write_schema(path: str | Path) -> Path:
    """Write the generated schema to disk."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(build_schema(), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return target


def validate_schema_document(document: Mapping[str, Any]) -> None:
    """Check a profile document against the schema.

    Uses the project's existing dependency-free validator, the same one the M1
    artifact contract uses, so M5 adds no new validation machinery to the project.
    """

    from core.schema_validation import validate_schema_instance
    from core.errors import ArtifactValidationError

    from .model import ProfileError

    try:
        validate_schema_instance(
            dict(document), _schema_path(), root_name="visual_creator_profile"
        )
    except ArtifactValidationError as exc:
        raise ProfileError(f"schema validation failed: {exc}") from exc


def _schema_path() -> Path:
    """Materialise the schema to a temporary file for the shared validator.

    The project validator reads a path, so the generated schema is written once to
    a cache location and reused. Writing to a temp file keeps ``schemas/`` free of
    a file M5 would otherwise be modifying a shared directory to hold.
    """

    import hashlib
    import tempfile

    payload = json.dumps(build_schema(), sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    target = Path(tempfile.gettempdir()) / f"m5_profile_schema_{digest}.json"
    if not target.is_file():
        target.write_bytes(payload)
    return target


__all__ = [
    "FORBIDDEN_KEYS",
    "PROFILE_VERSION",
    "SCHEMA_FILENAME",
    "build_schema",
    "schema_keys",
    "validate_schema_document",
    "write_schema",
]
