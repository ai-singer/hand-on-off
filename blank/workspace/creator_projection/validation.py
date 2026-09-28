"""Validation for projected instances.

Adds projection-specific checks on top of the contract checks, covering the
things C0.2 is responsible for:

* every projected field is traceable to a declared asset;
* **no capability is claimed that does not exist** (this is the check behind
  "禁止补全不存在能力");
* the visual layer carries no generation ability;
* the projection is a pure function of its inputs (determinism).
"""

from __future__ import annotations

from typing import Any, Mapping

from creator_contract import (
    ISOLATION_FORBIDDEN_KEYS,
    PROMPT_FORBIDDEN_KEYS,
    validate as validate_contract,
)
from creator_contract.validation import (
    FORBIDDEN_CODE_PATTERNS,
    IsolationReport,
)

from .asset_registry import AssetRegistry
from .errors import (
    ProjectionCapabilityError,
    ProjectionError,
    ProjectionProvenanceError,
)
from .mapper import (
    GENERATION_ABSENT_REASON,
    PUBLISHING_ABSENT_REASON,
    SOURCED_MODULES,
    ProjectionResult,
)
from .provenance import REQUIRED_PROVENANCE_KEYS, assert_fields_traceable

#: Text tokens that indicate a generation capability anywhere in an instance.
GENERATION_TOKENS: tuple[str, ...] = (
    "image_generation",
    "generate_image",
    "text_to_image",
    "text-to-image",
    "diffusion",
    "renderer",
    "render",
    "midjourney",
    "stable diffusion",
    "dall-e",
    "text_to_video",
    "img2img",
    "txt2img",
)


def validate_projection(
    result: ProjectionResult,
    *,
    registry: AssetRegistry | None = None,
    workspace_root: Any = None,
) -> IsolationReport:
    """Validate a projection end to end and return the contract report.

    Raises:
        ProjectionProvenanceError: when a field cannot be traced.
        ProjectionCapabilityError: when an absent capability is claimed present.
    """

    report = validate_contract(result.instance, workspace_root=workspace_root)

    assert_projection_provenance(result)
    assert_no_phantom_capability(result.instance)
    assert_no_generation_capability(result.instance["visual_rules"])

    if registry is not None:
        assert_registry_consistency(result, registry)

    return report


def assert_projection_provenance(result: ProjectionResult) -> None:
    """Every field of every module must carry a complete provenance record."""

    for module in SOURCED_MODULES:
        document = result.instance.get(module)
        if not isinstance(document, Mapping):
            raise ProjectionProvenanceError(f"instance has no {module!r} module")
        assert_fields_traceable(result.field_provenance, module, tuple(document))

    modules_block = result.instance.get("provenance")
    if not isinstance(modules_block, Mapping):
        raise ProjectionProvenanceError("instance has no contract provenance block")
    for module in SOURCED_MODULES:
        if module not in modules_block:
            raise ProjectionProvenanceError(
                f"contract provenance is missing an entry for {module!r}"
            )


def assert_no_phantom_capability(instance: Mapping[str, Any]) -> None:
    """An absent capability must be disabled and must state why.

    This is the guard against the failure mode the brief names explicitly:
    ``generation.enabled=true`` when no generation capability exists.
    """

    generation = instance.get("generation")
    if not isinstance(generation, Mapping):
        raise ProjectionCapabilityError("instance has no generation block")
    if generation.get("enabled") is not False:
        raise ProjectionCapabilityError(
            "generation.enabled must be false: no generation adapter exists in "
            "this repository, so enabling generation would be a false claim"
        )
    if str(generation.get("reason", "")).strip() != GENERATION_ABSENT_REASON:
        raise ProjectionCapabilityError(
            f"generation must declare reason={GENERATION_ABSENT_REASON!r}"
        )

    publishing = instance.get("publishing")
    if not isinstance(publishing, Mapping):
        raise ProjectionCapabilityError("instance has no publishing block")
    if publishing.get("enabled") is not False:
        raise ProjectionCapabilityError(
            "publishing.enabled must be false: no publisher, CMS, or idempotency "
            "implementation exists, so enabling publishing would be a false claim"
        )
    if str(publishing.get("reason", "")).strip() != PUBLISHING_ABSENT_REASON:
        raise ProjectionCapabilityError(
            f"publishing must declare reason={PUBLISHING_ABSENT_REASON!r}"
        )

    risk_policy = instance.get("risk_policy")
    if isinstance(risk_policy, Mapping):
        if risk_policy.get("runtime_connected") is True:
            raise ProjectionCapabilityError(
                "risk_policy.runtime_connected must be false: this projection "
                "declares policy, it does not connect an evaluator to the runtime"
            )


def assert_no_generation_capability(visual_rules: Mapping[str, Any]) -> None:
    """The visual layer must carry no generation ability of any kind."""

    if not isinstance(visual_rules, Mapping):
        raise ProjectionCapabilityError("visual_rules must be an object")

    offenders: list[str] = []
    for key, path, value in _walk(visual_rules):
        if key in PROMPT_FORBIDDEN_KEYS:
            offenders.append(f"{path} (forbidden key {key!r})")
        if isinstance(value, str):
            lowered = value.lower()
            for token in GENERATION_TOKENS:
                if token in lowered:
                    offenders.append(f"{path} (contains {token!r})")
                    break
    if offenders:
        raise ProjectionCapabilityError(
            "visual_rules must reference a distilled profile and carry no "
            "generation capability: " + "; ".join(sorted(set(offenders)))
        )


def assert_no_runtime_code(instance: Mapping[str, Any]) -> None:
    """A projected instance must not contain code or a live client."""

    offenders: list[str] = []
    for key, path, value in _walk(instance):
        if key in ISOLATION_FORBIDDEN_KEYS:
            offenders.append(f"{path} (forbidden key {key!r})")
        if isinstance(value, str):
            lowered = value.lower()
            for pattern in FORBIDDEN_CODE_PATTERNS:
                if pattern in lowered:
                    offenders.append(f"{path} (contains {pattern!r})")
                    break
    if offenders:
        raise ProjectionError(
            "projected instance contains runtime content: "
            + "; ".join(sorted(set(offenders)))
        )


def assert_registry_consistency(
    result: ProjectionResult, registry: AssetRegistry
) -> None:
    """The projection's reported availability must match the registry."""

    if result.registry_version != registry.version:
        raise ProjectionError(
            f"projection used registry version {result.registry_version!r} but the "
            f"registry reports {registry.version!r}"
        )
    if result.asset_availability != registry.availability():
        raise ProjectionError("projection asset availability does not match the registry")

    modules_block = result.instance.get("provenance", {})
    if isinstance(modules_block, Mapping):
        for module in SOURCED_MODULES:
            entry = modules_block.get(module)
            if not isinstance(entry, Mapping):
                continue
            asset_id = entry.get("source")
            if asset_id is None:
                continue
            if asset_id not in registry.ids():
                raise ProjectionError(
                    f"provenance for {module!r} cites unregistered asset {asset_id!r}"
                )


def assert_provenance_keys_complete(result: ProjectionResult) -> None:
    """Every field record carries exactly the required provenance keys."""

    for module, fields in result.field_provenance.items():
        for field_name, record in fields.items():
            missing = [key for key in REQUIRED_PROVENANCE_KEYS if key not in record]
            if missing:
                raise ProjectionProvenanceError(
                    f"provenance for {module}.{field_name} is missing: "
                    + ", ".join(missing)
                )


def _walk(document: Any, prefix: str = ""):
    if isinstance(document, Mapping):
        for key, value in document.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield str(key).lower(), path, value
            yield from _walk(value, path)
    elif isinstance(document, (list, tuple)):
        for index, item in enumerate(document):
            yield from _walk(item, f"{prefix}[{index}]")


__all__ = [
    "GENERATION_TOKENS",
    "assert_no_generation_capability",
    "assert_no_phantom_capability",
    "assert_no_runtime_code",
    "assert_projection_provenance",
    "assert_provenance_keys_complete",
    "assert_registry_consistency",
    "validate_projection",
]
