"""JSON Schema for the Creator Skill artifact.

The schema is **generated from the model's own vocabularies** rather than
hand-written, following the pattern already used by
``multimodal_creator.profile.schema``: a literal JSON blob would drift from the
model silently, whereas deriving it means a vocabulary change cannot leave the
two disagreeing.

The schema is strict at every level (``additionalProperties: false``). That is
what makes the isolation guarantee structural: there is nowhere to put a prompt, a
model call, or runtime code, so such a document is rejected by *shape* before any
semantic check runs.

It is expressed only in the subset the project's dependency-free validator
supports - ``type`` / ``enum`` / ``required`` / ``properties`` /
``additionalProperties`` / ``items`` / ``minItems`` - with no ``$ref``,
``allOf``, ``oneOf``, or ``if``/``then``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .errors import SkillSchemaError
from .model import DEPENDENCY_KINDS, PROVENANCE_SOURCES, SKILL_STATUSES
from .taxonomy import MINIMUM_CAPABILITIES, SKILL_TYPE_ORDER

#: Where the generated schema is written, joining the project's ``schemas/``.
SCHEMA_FILENAME = "creator_skill.schema.json"

#: Skill artifact schema version.
SKILL_SCHEMA_VERSION = "1.0.0"


def build_schema() -> dict[str, Any]:
    """Build the skill JSON Schema from the model's vocabularies."""

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://creator-agent.local/schemas/creator_skill.schema.json",
        "title": "CreatorSkill",
        "description": (
            "A declared creator capability. A skill states what a Creator Agent "
            "can do and what it needs; it carries no prompt, no model call, and "
            "no runtime code."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": [
            "skill_id",
            "skill_type",
            "version",
            "description",
            "capabilities",
            "inputs",
            "outputs",
            "dependencies",
            "compatibility",
            "provenance",
            "status",
        ],
        "properties": {
            "skill_id": {"type": "string"},
            "skill_type": {"type": "string", "enum": list(SKILL_TYPE_ORDER)},
            "version": {"type": "string"},
            "description": {"type": "string"},
            "capabilities": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
            "inputs": {"type": "array", "items": {"type": "string"}},
            "outputs": {"type": "array", "items": {"type": "string"}},
            "dependencies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["target", "kind"],
                    "properties": {
                        "target": {"type": "string"},
                        "kind": {"type": "string", "enum": list(DEPENDENCY_KINDS)},
                        "reason": {"type": "string"},
                    },
                },
            },
            "compatibility": {
                "type": "object",
                "additionalProperties": False,
                "required": ["domains", "platforms", "styles", "requires_contract_version"],
                "properties": {
                    "domains": {"type": "array", "items": {"type": "string"}},
                    "platforms": {"type": "array", "items": {"type": "string"}},
                    "styles": {"type": "array", "items": {"type": "string"}},
                    "requires_contract_version": {"type": "string"},
                },
            },
            "provenance": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "source_kind",
                    "source_ref",
                    "skill_version",
                    "generated_at",
                    "confidence",
                ],
                "properties": {
                    "source_kind": {"type": "string", "enum": list(PROVENANCE_SOURCES)},
                    "source_ref": {"type": "string"},
                    "skill_version": {"type": "string"},
                    "generated_at": {"type": "string"},
                    "confidence": {"type": "number"},
                    "note": {"type": "string"},
                },
            },
            "status": {"type": "string", "enum": list(SKILL_STATUSES)},
            "reason": {"type": "string"},
            "reusable": {"type": "boolean"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
    }


def schema_keys() -> frozenset[str]:
    """Top-level keys the schema declares."""

    return frozenset(build_schema()["properties"])


def minimum_capabilities(skill_type_id: str) -> int:
    """Minimum capability count for a skill type."""

    return MINIMUM_CAPABILITIES.get(skill_type_id, 1)


def write_schema(path: str | Path) -> Path:
    """Write the generated schema to disk."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(build_schema(), indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return target


def load_document(path: str | Path) -> Mapping[str, Any]:
    """Read a skill document from disk."""

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SkillSchemaError(f"skill document not found: {source}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillSchemaError(f"cannot read skill document {source}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SkillSchemaError(f"skill document must be an object: {source}")
    return payload


def validate_schema_document(
    document: Mapping[str, Any],
    *,
    schema_path: str | Path | None = None,
) -> None:
    """Validate a skill document against the generated schema.

    Uses the project's existing dependency-free validator, so this layer adds no
    validation machinery to the project.
    """

    from core.errors import ArtifactValidationError
    from core.schema_validation import validate_schema_instance

    payload = json.dumps(build_schema(), sort_keys=True).encode("utf-8")
    if schema_path is not None:
        target = Path(schema_path)
        if not target.is_file():
            write_schema(target)
    else:
        import hashlib
        import tempfile

        digest = hashlib.sha256(payload).hexdigest()[:16]
        target = Path(tempfile.gettempdir()) / f"creator_skill_schema_{digest}.json"
        if not target.is_file():
            target.write_bytes(payload)

    try:
        validate_schema_instance(dict(document), target, root_name="creator_skill")
    except ArtifactValidationError as exc:
        raise SkillSchemaError(str(exc)) from exc


__all__ = [
    "SCHEMA_FILENAME",
    "SKILL_SCHEMA_VERSION",
    "build_schema",
    "load_document",
    "minimum_capabilities",
    "schema_keys",
    "validate_schema_document",
    "write_schema",
]
