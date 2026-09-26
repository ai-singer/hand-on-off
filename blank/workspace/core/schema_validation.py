"""Small dependency-free validator for the unified artifact schema subset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .errors import ArtifactValidationError


_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def _validate_node(value: Any, schema: Mapping[str, Any], path: str) -> None:
    declared_type = schema.get("type")
    if declared_type:
        expected = _TYPE_MAP.get(declared_type)
        if expected is None:
            raise ArtifactValidationError(
                f"schema uses unsupported type {declared_type!r} at {path}"
            )
        if declared_type in {"number", "integer"} and isinstance(value, bool):
            valid = False
        else:
            valid = isinstance(value, expected)
        if not valid:
            raise ArtifactValidationError(
                f"{path} must be {declared_type}, got {type(value).__name__}"
            )

    if "enum" in schema and value not in schema["enum"]:
        raise ArtifactValidationError(f"{path} must be one of {schema['enum']!r}")

    if isinstance(value, dict):
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            raise ArtifactValidationError(
                f"{path} is missing required fields: {', '.join(missing)}"
            )
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unexpected = sorted(set(value) - set(properties))
            if unexpected:
                raise ArtifactValidationError(
                    f"{path} has unexpected fields: {', '.join(unexpected)}"
                )
        for key, child in value.items():
            child_schema = properties.get(key)
            if child_schema:
                _validate_node(child, child_schema, f"{path}.{key}")

    if isinstance(value, list):
        minimum = schema.get("minItems")
        if minimum is not None and len(value) < minimum:
            raise ArtifactValidationError(
                f"{path} must contain at least {minimum} item(s)"
            )
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_node(item, item_schema, f"{path}[{index}]")


def validate_unified_artifact(
    artifact: Mapping[str, Any], schema_path: str | Path
) -> None:
    path = Path(schema_path)
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"cannot read artifact schema {path}: {exc}") from exc
    _validate_node(dict(artifact), schema, "artifact")
