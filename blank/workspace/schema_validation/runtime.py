"""Compose shared Artifact validation with optional plugin-private validation."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Mapping

from core.errors import ArtifactValidationError
from core.schema_validation import validate_schema_instance
from plugin_interface.base import CreatorDistillationPlugin


_DOMAIN_SCHEMA = Path("schemas") / "domain_extension.schema.json"


@dataclass(frozen=True, slots=True)
class RuntimeSchemaValidationResult:
    """Inspectable result returned after all applicable schemas pass."""

    status: str
    shared_schema_path: Path
    domain_schema_path: Path | None
    domain_schema_applied: bool


def validate_runtime_schemas(
    artifact: Mapping[str, Any],
    *,
    plugin: CreatorDistillationPlugin,
    shared_schema_path: str | Path,
) -> RuntimeSchemaValidationResult:
    """Validate the shared Artifact and an optional plugin domain extension.

    A plugin-private Schema is an enhancement, not a core dependency. Plugins
    without a schemas/domain_extension.schema.json file continue through shared
    validation. When the private Schema exists, failure is explicit and stops
    the pipeline before the quality gate or generation adapter.
    """

    shared_path = Path(shared_schema_path)
    validate_schema_instance(dict(artifact), shared_path, root_name="artifact")

    domain_schema_path = _discover_domain_schema(plugin)
    if domain_schema_path is None:
        return RuntimeSchemaValidationResult(
            status="PASS",
            shared_schema_path=shared_path,
            domain_schema_path=None,
            domain_schema_applied=False,
        )

    try:
        validate_schema_instance(
            artifact.get("domain_extension"),
            domain_schema_path,
            root_name=f"domain_extension[{plugin.identity.name}]",
        )
    except ArtifactValidationError as exc:
        raise ArtifactValidationError(
            f"plugin {plugin.identity.name!r} domain_extension failed Schema "
            f"validation: {exc}"
        ) from exc

    return RuntimeSchemaValidationResult(
        status="PASS",
        shared_schema_path=shared_path,
        domain_schema_path=domain_schema_path,
        domain_schema_applied=True,
    )


def _discover_domain_schema(
    plugin: CreatorDistillationPlugin,
) -> Path | None:
    """Find the conventional private Schema next to the plugin implementation."""

    module = import_module(type(plugin).__module__)
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return None
    candidate = Path(module_file).resolve().parent / _DOMAIN_SCHEMA
    return candidate if candidate.is_file() else None
