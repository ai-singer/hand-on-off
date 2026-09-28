"""The Domain Plugin schema, generated from the model's own vocabularies.

The schema is **built**, not hand-written, so it cannot drift from the model: the
enums come from :mod:`creator_plugin_builder.model`, the rule slots from
:data:`~creator_plugin_builder.model.PLUGIN_SLOTS`, the protocol stages from
:data:`~creator_plugin_builder.model.PROTOCOL_STAGES`, and the required keys from the
same architecture lists the model enforces. :func:`write_schema` emits it to
``schemas/domain_plugin.schema.json``.

It uses the project's dependency-free schema subset — ``type``, ``enum``,
``required``, ``properties``, ``additionalProperties``, ``items``, ``minItems`` — with
no ``$ref``, ``allOf``, ``oneOf`` or ``if``, exactly as the four schemas before it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .model import (
    PLUGIN_CORE_SKILLS,
    PLUGIN_FORMAT_VERSION,
    PLUGIN_SLOTS,
    PROTOCOL_STAGES,
    PluginSchemaError,
    RuleStatus,
)

#: The schema filename, inside ``schemas/``.
SCHEMA_FILENAME = "domain_plugin.schema.json"

#: The document root name, used in schema error messages.
ROOT_NAME = "domain_plugin"

#: Top-level keys a plugin document must carry.
REQUIRED_KEYS: tuple[str, ...] = (
    "plugin_name",
    "domain",
    "version",
    "format_version",
    "display_name",
    "domain_identity",
    "protocol_stages",
    "required_core_skills",
    "provenance",
) + PLUGIN_SLOTS

#: The rule statuses, from the model's enum rather than a repeated literal.
RULE_STATUSES: tuple[str, ...] = tuple(status.value for status in RuleStatus)


def _rule_schema() -> dict[str, Any]:
    """The schema for one :class:`~creator_plugin_builder.model.RuleBinding`."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "slot",
            "core_skill",
            "source_asset",
            "status",
            "values_source",
            "values",
        ],
        "properties": {
            "slot": {"type": "string"},
            "core_skill": {"type": "string", "enum": list(PLUGIN_CORE_SKILLS)},
            "source_asset": {"type": "string"},
            "asset_type": {"type": "string"},
            "status": {"type": "string", "enum": list(RULE_STATUSES)},
            "available": {"type": "boolean"},
            "values_source": {"type": "string", "enum": ["asset", "catalog"]},
            "deliverable": {"type": "string"},
            "reason": {"type": "string"},
            "values": {"type": "array", "items": {"type": "string"}},
        },
    }


def _stage_schema() -> dict[str, Any]:
    """The schema for one :class:`~creator_plugin_builder.model.DistillationStage`."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "stage",
            "domain_term",
            "core_skill",
            "status",
            "order",
        ],
        "properties": {
            "stage": {"type": "string", "enum": list(PROTOCOL_STAGES)},
            "domain_term": {"type": "string"},
            "core_skill": {"type": "string", "enum": list(PLUGIN_CORE_SKILLS)},
            "source_asset": {"type": "string"},
            "status": {"type": "string", "enum": list(RULE_STATUSES)},
            "available": {"type": "boolean"},
            "order": {"type": "integer"},
            "reason": {"type": "string"},
            "questions": {"type": "array", "items": {"type": "string"}},
        },
    }


def build_schema() -> dict[str, Any]:
    """Build the Domain Plugin schema document."""

    properties: dict[str, Any] = {
        "plugin_name": {"type": "string"},
        "domain": {"type": "string"},
        "version": {"type": "string"},
        "format_version": {"type": "string"},
        "display_name": {"type": "string"},
        "domain_identity": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "domain",
                "display_name",
                "reference_sources",
                "keywords",
                "persona",
            ],
            "properties": {
                "domain": {"type": "string"},
                "display_name": {"type": "string"},
                "reference_sources": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "keywords": {"type": "array", "items": {"type": "string"}},
                "persona": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["available", "source_asset", "reason"],
                    "properties": {
                        "available": {"type": "boolean"},
                        "source_asset": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                },
            },
        },
        "protocol_stages": {
            "type": "array",
            "minItems": len(PROTOCOL_STAGES),
            "items": _stage_schema(),
        },
        "required_core_skills": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "enum": list(PLUGIN_CORE_SKILLS)},
        },
        "compatibility": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "platforms": {"type": "array", "items": {"type": "string"}},
                "styles": {"type": "array", "items": {"type": "string"}},
                "requires_contract_version": {"type": "string"},
                "requires_format_version": {"type": "string"},
            },
        },
        "provenance": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "generated_by",
                "generated_at",
                "domain",
                "catalog_version",
                "library_version",
                "request_digest",
                "source_assets",
            ],
            "properties": {
                "generated_by": {"type": "string"},
                "generated_at": {"type": "string"},
                "domain": {"type": "string"},
                "catalog_version": {"type": "string"},
                "library_version": {"type": "string"},
                "request_digest": {"type": "string"},
                "source_assets": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string"},
                },
                "unavailable_assets": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "core_skills": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(PLUGIN_CORE_SKILLS)},
                },
                "notes": {"type": "array", "items": {"type": "string"}},
            },
        },
        "notes": {"type": "array", "items": {"type": "string"}},
    }

    for slot in PLUGIN_SLOTS:
        properties[slot] = {
            "type": "array",
            "minItems": 1,
            "items": _rule_schema(),
        }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://creator-agent.local/schemas/domain_plugin.schema.json",
        "title": "DomainPlugin",
        "description": (
            "A versioned, declarative domain plugin. A plugin carries what a domain "
            "is about - its identity, sources, topics, distillation vocabulary "
            "and adaptations - so that the Universal Creator Skills stay "
            "domain-free. It carries no runtime code, no prompt and no credential."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": list(REQUIRED_KEYS),
        "properties": properties,
    }


def schema_keys() -> frozenset[str]:
    """Every top-level key the schema declares, for a test that pins the surface."""

    return frozenset(build_schema()["properties"])


def schema_path(workspace_root: str | Path | None = None) -> Path:
    """The path of the emitted schema document."""

    root = (
        Path(workspace_root)
        if workspace_root is not None
        else Path(__file__).resolve().parents[1]
    )
    return root / "schemas" / SCHEMA_FILENAME


def write_schema(path: str | Path | None = None) -> Path:
    """Write the schema document, creating its directory if needed."""

    target = Path(path) if path is not None else schema_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(build_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def load_schema(path: str | Path | None = None) -> dict[str, Any]:
    """Read the emitted schema document, failing with a typed error."""

    target = Path(path) if path is not None else schema_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PluginSchemaError(f"domain plugin schema not found: {target}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise PluginSchemaError(
            f"cannot read domain plugin schema {target}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise PluginSchemaError(f"domain plugin schema must be an object: {target}")
    return payload


class _SchemaMismatch(Exception):
    """Internal: a document does not match the schema subset."""


#: The dependency-free subset's type map, matching ``core.schema_validation``.
_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "integer": int,
    "null": type(None),
}


def _validate_node(value: Any, schema: Mapping[str, Any], path: str) -> None:
    """Validate one node against the dependency-free schema subset.

    Deliberately the *same subset* ``core.schema_validation`` implements, so a schema
    this project writes validates the same way whichever validator reads it: ``type``,
    ``enum``, ``required``, ``properties``, ``additionalProperties``, ``items`` and
    ``minItems``, and nothing else. The subset is reimplemented here rather than
    reusing ``core``'s because that validator reads a schema from a **path**, and an
    in-memory schema must be checkable without writing a temporary file.
    """

    if not isinstance(schema, Mapping):
        raise _SchemaMismatch(f"{path}: schema node is not an object")

    declared = schema.get("type")
    if declared:
        expected = _TYPE_MAP.get(declared)
        if expected is None:
            raise _SchemaMismatch(f"{path}: schema uses unsupported type {declared!r}")
        if declared in {"number", "integer"} and isinstance(value, bool):
            valid = False
        else:
            valid = isinstance(value, expected)
        if not valid:
            raise _SchemaMismatch(
                f"{path} must be {declared}, got {type(value).__name__}"
            )

    if "enum" in schema and value not in schema["enum"]:
        raise _SchemaMismatch(
            f"{path} is not one of {', '.join(map(str, schema['enum']))}"
        )

    if isinstance(value, dict):
        required = schema.get("required", ())
        missing = [key for key in required if key not in value]
        if missing:
            raise _SchemaMismatch(
                f"{path} is missing required fields: {', '.join(missing)}"
            )
        properties = schema.get("properties", {})
        for key, child in value.items():
            if key in properties:
                _validate_node(child, properties[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise _SchemaMismatch(f"{path} has unexpected fields: {key}")
            elif isinstance(schema.get("additionalProperties"), Mapping):
                _validate_node(
                    child, schema["additionalProperties"], f"{path}.{key}"
                )

    if isinstance(value, list):
        minimum = schema.get("minItems")
        if minimum is not None and len(value) < minimum:
            raise _SchemaMismatch(
                f"{path} must have at least {minimum} item(s), has {len(value)}"
            )
        if isinstance(schema.get("items"), Mapping):
            for index, item in enumerate(value):
                _validate_node(item, schema["items"], f"{path}[{index}]")


def validate_schema_document(
    document: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
    path: str | Path | None = None,
) -> None:
    """Validate a document against the schema.

    Uses the in-memory schema when one is supplied, and the emitted document
    otherwise. The emitted document is *also* checked with the project's own
    validator when it can be read, so the two implementations cannot disagree
    silently.
    """

    resolved = schema if schema is not None else load_schema(path)

    try:
        _validate_node(dict(document), resolved, ROOT_NAME)
    except _SchemaMismatch as exc:
        raise PluginSchemaError(
            f"{ROOT_NAME} does not match the domain plugin schema", detail=str(exc)
        ) from exc

    if schema is None:
        # Cross-check against core's validator, so a divergence between the two
        # implementations surfaces here rather than in a downstream consumer.
        from core.schema_validation import validate_schema_instance

        target = Path(path) if path is not None else schema_path()
        try:
            validate_schema_instance(dict(document), target, root_name=ROOT_NAME)
        except Exception as exc:
            raise PluginSchemaError(
                f"{ROOT_NAME} does not match the domain plugin schema",
                detail=str(exc),
            ) from exc


__all__ = [
    "REQUIRED_KEYS",
    "ROOT_NAME",
    "RULE_STATUSES",
    "SCHEMA_FILENAME",
    "build_schema",
    "load_schema",
    "schema_keys",
    "schema_path",
    "validate_schema_document",
    "write_schema",
]
