"""Validation for a Creator Instance document.

Three independent checks, each separately reportable so a caller can tell a shape
problem from a policy problem:

1. :func:`validate_schema` — shape and types, via the project's existing
   dependency-free schema validator and ``schemas/creator_instance.schema.json``.
2. :func:`validate_dependencies` — cross-module references resolve
   (creator ids agree, the M5 profile reference is coherent, referenced
   categories exist).
3. :func:`validate_isolation` — an instance is **configuration, not runtime**:
   it may not contain code, model calls, crawling, or publishing.

:func:`validate` runs all three and returns an inspectable
:class:`IsolationReport`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.errors import ArtifactValidationError
from core.schema_validation import validate_schema_instance

from .artifacts import contract_schema_path
from .errors import (
    CreatorContractDependencyError,
    CreatorContractError,
    CreatorContractIsolationError,
    CreatorContractSchemaError,
)

#: Semantic version of the instance contract this module implements.
CONTRACT_VERSION = "1.0.0"

# --------------------------------------------------------------------------
# Isolation policies
# --------------------------------------------------------------------------

#: Key names that mean "this instance is carrying runtime code".
#:
#: Checked at every nesting depth. Deliberately conservative: only names that
#: cannot be legitimate configuration are listed.
ISOLATION_FORBIDDEN_KEYS: tuple[str, ...] = (
    "python",
    "code",
    "source_code",
    "script",
    "exec",
    "eval",
    "subprocess",
    "shell",
    "command",
    "model_call",
    "api_call",
    "crawler",
    "crawl",
    "scraper",
    "scrape",
    "spider",
    "publisher_code",
    "upload_code",
)

#: Substrings that indicate executable code or a live network client inside a
#: string value. Kept specific so legitimate prose ("projected from the
#: template") and legitimate locators (``https://www.stats.gov.cn/``) are not
#: flagged, while real code is.
#:
#: Note: ``import `` covers ``from x import y`` too, so no bare ``from `` entry is
#: needed - and a bare ``from `` would match ordinary English prose.
FORBIDDEN_CODE_PATTERNS: tuple[str, ...] = (
    "def ",
    "import ",
    "subprocess.",
    "subprocess(",
    "os.system",
    "eval(",
    "exec(",
    "requests.",
    "urllib",
    "aiohttp",
    "httpx",
    "socket.",
    "playwright",
    "boto3",
    "openai.",
    "anthropic.",
    "importlib",
)

#: Key names prohibited inside ``visual_rules``. The visual layer stores a
#: distilled *vocabulary and constraints*, never a generation program. Mirrors
#: ``multimodal_creator.profile.schema.FORBIDDEN_KEYS`` so the two layers cannot
#: drift apart.
PROMPT_FORBIDDEN_KEYS: tuple[str, ...] = (
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

#: Prompt-ish phrases that must not appear as string content inside
#: ``visual_rules`` even under an innocent key name.
PROMPT_CONTENT_PATTERNS: tuple[str, ...] = (
    "create image",
    "generate image",
    "image prompt",
    "midjourney",
    "stable diffusion",
    "dall-e",
    "dall·e",
    "text-to-image",
    "text to image",
)

#: Modules that must never be referenced by way of an import path in an instance.
ISOLATION_FORBIDDEN_MODULES: tuple[str, ...] = (
    "distillation_core",
    "runtime",
    "production",
    "risk_evaluation",
    "workflows",
    "multimodal_creator",
)


@dataclass(frozen=True, slots=True)
class IsolationReport:
    """Result of a full contract validation, returned rather than only raised."""

    status: str
    contract_version: str
    modules_present: tuple[str, ...]
    provenance_modules: tuple[str, ...]
    checks: Mapping[str, str]

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "contract_version": self.contract_version,
            "modules_present": list(self.modules_present),
            "provenance_modules": list(self.provenance_modules),
            "checks": dict(self.checks),
        }


# --------------------------------------------------------------------------
# 1. Schema
# --------------------------------------------------------------------------


def load_contract_schema(workspace_root: str | Path | None = None) -> dict[str, Any]:
    """Read the contract schema, failing with a typed error."""

    path = contract_schema_path(workspace_root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CreatorContractSchemaError(f"contract schema not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CreatorContractSchemaError(
            f"cannot read contract schema {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise CreatorContractSchemaError(f"contract schema root must be an object: {path}")
    return payload


def validate_schema(
    instance: Mapping[str, Any],
    *,
    workspace_root: str | Path | None = None,
) -> None:
    """Validate an instance against the contract schema.

    Raises:
        CreatorContractError: when the document does not match the contract.
    """

    if not isinstance(instance, Mapping):
        raise CreatorContractError("creator instance must be an object")
    try:
        validate_schema_instance(
            dict(instance),
            contract_schema_path(workspace_root),
            root_name="creator_instance",
        )
    except ArtifactValidationError as exc:
        raise CreatorContractError(str(exc)) from exc


# --------------------------------------------------------------------------
# 2. Dependencies
# --------------------------------------------------------------------------


def validate_dependencies(instance: Mapping[str, Any]) -> None:
    """Check that cross-module references inside an instance resolve.

    Assumes the shape has already been checked; raises
    :class:`CreatorContractDependencyError` on a broken reference.
    """

    identity = _mapping(instance, "identity")
    source = _mapping(instance, "source")
    text_rules = _mapping(instance, "text_rules")
    visual_rules = _mapping(instance, "visual_rules")
    risk_policy = _mapping(instance, "risk_policy")
    generation = _mapping(instance, "generation")
    publishing = _mapping(instance, "publishing")
    provenance = _mapping(instance, "provenance")

    # -- identity <-> module agreement ------------------------------------
    creator_id = identity.get("creator_id")
    if not isinstance(creator_id, str) or not creator_id.strip():
        raise CreatorContractDependencyError("identity.creator_id must be non-empty")

    persona = _mapping(identity, "persona")
    models = persona.get("mental_models")
    if not isinstance(models, Sequence) or isinstance(models, (str, bytes)) or not models:
        raise CreatorContractDependencyError(
            "identity.persona.mental_models must be a non-empty array"
        )
    model_ids = [
        str(model.get("model_id"))
        for model in models
        if isinstance(model, Mapping) and model.get("model_id")
    ]
    if len(model_ids) != len(models):
        raise CreatorContractDependencyError(
            "every mental model must declare a model_id"
        )
    if len(set(model_ids)) != len(model_ids):
        raise CreatorContractDependencyError("mental model ids must be unique")

    # -- source <-> identity ---------------------------------------------
    creators = source.get("reference_creators")
    if not isinstance(creators, Sequence) or not creators:
        raise CreatorContractDependencyError(
            "source.reference_creators must declare at least one creator"
        )
    for creator in creators:
        if not isinstance(creator, Mapping):
            raise CreatorContractDependencyError("reference creator must be an object")
        if creator.get("identity_verified") is not True:
            raise CreatorContractDependencyError(
                "reference creator "
                f"{creator.get('name')!r} is not identity-verified; "
                "an unverified user_id must not be collected against"
            )

    data_sources = source.get("data_sources")
    if not isinstance(data_sources, Sequence) or not data_sources:
        raise CreatorContractDependencyError("source.data_sources must not be empty")
    layers = {
        str(item.get("layer"))
        for item in data_sources
        if isinstance(item, Mapping)
    }
    if "evidence" not in layers:
        raise CreatorContractDependencyError(
            "source.data_sources must declare at least one 'evidence' layer source; "
            "discovery-layer social material may not be the factual basis"
        )

    # -- risk_policy internal consistency --------------------------------
    categories = risk_policy.get("risk_categories")
    if not isinstance(categories, Sequence) or not categories:
        raise CreatorContractDependencyError("risk_policy.risk_categories must not be empty")
    category_ids = {
        str(item.get("category_id"))
        for item in categories
        if isinstance(item, Mapping) and item.get("category_id")
    }
    if len(category_ids) != len(categories):
        raise CreatorContractDependencyError(
            "every risk category must declare a unique category_id"
        )

    blocked = risk_policy.get("blocked_patterns")
    if not isinstance(blocked, Sequence) or not blocked:
        raise CreatorContractDependencyError("risk_policy.blocked_patterns must not be empty")
    for item in blocked:
        if not isinstance(item, Mapping):
            raise CreatorContractDependencyError("blocked pattern must be an object")
        referenced = str(item.get("category_id"))
        if referenced not in category_ids:
            raise CreatorContractDependencyError(
                f"blocked pattern references undeclared risk category {referenced!r}"
            )

    for rule in _sequence(risk_policy, "review_rules"):
        if not isinstance(rule, Mapping):
            raise CreatorContractDependencyError("review rule must be an object")
        if not str(rule.get("when", "")).strip():
            raise CreatorContractDependencyError("review rule must declare 'when'")

    # -- text_rules <-> risk_policy --------------------------------------
    if not text_rules.get("knowledge_boundary"):
        raise CreatorContractDependencyError(
            "text_rules.knowledge_boundary must not be empty"
        )

    # -- visual_rules reference ------------------------------------------
    profile_id = visual_rules.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise CreatorContractDependencyError("visual_rules.profile_id must be non-empty")
    if not str(visual_rules.get("profile_version", "")).strip():
        raise CreatorContractDependencyError(
            "visual_rules.profile_version must be non-empty"
        )
    composition = _mapping(visual_rules, "composition")
    if not composition.get("preferred_layout"):
        raise CreatorContractDependencyError(
            "visual_rules.composition.preferred_layout must not be empty"
        )
    if not _mapping(visual_rules, "provenance"):
        raise CreatorContractDependencyError(
            "visual_rules.provenance must record the M5 artifact it came from"
        )

    # -- generation <-> evaluation ---------------------------------------
    if generation.get("quality_gate", {}).get("required_decision") != "PASS":
        raise CreatorContractDependencyError(
            "generation.quality_gate.required_decision must be 'PASS'; "
            "generation may only run after the gate passes"
        )
    if not str(generation.get("adapter_ref", "")).strip():
        raise CreatorContractDependencyError(
            "generation.adapter_ref must name the injected adapter"
        )

    # -- publishing -------------------------------------------------------
    api = _mapping(publishing, "api")
    if not str(api.get("idempotency_key", "")).strip():
        raise CreatorContractDependencyError(
            "publishing.api.idempotency_key must declare a key source; "
            "publishing without idempotency is not permitted"
        )
    requirement = _mapping(publishing, "image_requirement")
    ratio = requirement.get("aspect_ratio")
    if ratio not in {"16:9", "4:5", "9:16", "1:1"}:
        raise CreatorContractDependencyError(
            f"publishing.image_requirement.aspect_ratio {ratio!r} is not supported"
        )

    # -- provenance completeness -----------------------------------------
    assert_provenance_complete(instance)

    for module in ("identity", "source", "text_rules", "visual_rules",
                   "risk_policy", "generation", "publishing"):
        record = provenance.get(module)
        if not isinstance(record, Mapping):
            raise CreatorContractDependencyError(
                f"provenance.{module} must be an object"
            )
        if not str(record.get("source", "")).strip():
            raise CreatorContractDependencyError(
                f"provenance.{module}.source must name where the module came from"
            )


def assert_provenance_complete(instance: Mapping[str, Any]) -> None:
    """Raise unless every module has a provenance record with a source."""

    provenance = instance.get("provenance")
    if not isinstance(provenance, Mapping):
        raise CreatorContractDependencyError("instance has no provenance block")
    missing = [
        module
        for module in ("identity", "source", "text_rules", "visual_rules",
                       "risk_policy", "generation", "publishing")
        if module not in provenance
    ]
    if missing:
        raise CreatorContractDependencyError(
            "provenance is missing entries for: " + ", ".join(missing)
        )


def assert_risk_policy_not_empty(instance: Mapping[str, Any]) -> None:
    """Raise unless the risk policy actually constrains something."""

    risk_policy = instance.get("risk_policy")
    if not isinstance(risk_policy, Mapping):
        raise CreatorContractDependencyError("instance has no risk_policy block")
    for field in ("risk_categories", "review_rules", "blocked_patterns"):
        values = risk_policy.get(field)
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
            raise CreatorContractDependencyError(
                f"risk_policy.{field} must not be empty; "
                "an instance without risk rules is not a valid creator"
            )


def assert_no_phantom_capability(instance: Mapping[str, Any]) -> None:
    """Reject an instance that claims a capability it cannot have.

    ``generation`` and ``publishing`` are *routing and target declarations*. A
    declaration may name an adapter to inject; it may not assert that the
    capability is present. An instance that sets ``enabled: true`` must therefore
    carry no absence reason, and an instance that sets ``enabled: false`` must
    state why - otherwise the disabled state is indistinguishable from an
    oversight.

    This rule lives in the contract rather than in the projection because it is a
    property of a valid instance, not of how the instance was produced.
    """

    for module in ("generation", "publishing"):
        block = instance.get(module)
        if not isinstance(block, Mapping):
            raise CreatorContractDependencyError(f"instance has no {module} block")
        enabled = block.get("enabled")
        reason = str(block.get("reason", "")).strip()
        if enabled is True and reason:
            raise CreatorContractDependencyError(
                f"{module}.enabled is true but a reason is declared ({reason!r}); "
                "a declaration must not both enable the capability and explain "
                "its absence"
            )
        if enabled is False and not reason:
            raise CreatorContractDependencyError(
                f"{module}.enabled is false but no reason is declared; a disabled "
                "capability must state why it is disabled"
            )


# --------------------------------------------------------------------------
# 3. Isolation
# --------------------------------------------------------------------------


def _iter_key_paths(document: Any, prefix: str = ""):
    if isinstance(document, Mapping):
        for key, value in document.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield str(key).lower(), path, value
            yield from _iter_key_paths(value, path)
    elif isinstance(document, Sequence) and not isinstance(document, (str, bytes)):
        for index, item in enumerate(document):
            yield from _iter_key_paths(item, f"{prefix}[{index}]")


def _iter_string_paths(document: Any, prefix: str = ""):
    if isinstance(document, Mapping):
        for key, value in document.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _iter_string_paths(value, path)
    elif isinstance(document, Sequence) and not isinstance(document, (str, bytes)):
        for index, item in enumerate(document):
            yield from _iter_string_paths(item, f"{prefix}[{index}]")
    elif isinstance(document, str):
        yield document, prefix


def assert_no_runtime_code(instance: Mapping[str, Any]) -> None:
    """Raise if an instance carries code, a live client, or a module import."""

    offenders: list[str] = []
    for key, path, _value in _iter_key_paths(instance):
        if key in ISOLATION_FORBIDDEN_KEYS:
            offenders.append(f"{path} (forbidden key {key!r})")
    for text, path in _iter_string_paths(instance):
        lowered = text.lower()
        for pattern in FORBIDDEN_CODE_PATTERNS:
            if pattern in lowered:
                offenders.append(f"{path} (contains {pattern!r})")
                break
        for module in ISOLATION_FORBIDDEN_MODULES:
            if f"import {module}" in lowered or f"{module}." in lowered:
                offenders.append(f"{path} (references runtime module {module!r})")
                break
    if offenders:
        raise CreatorContractIsolationError(
            "creator instance must be configuration only; found runtime content: "
            + "; ".join(sorted(set(offenders)))
        )


def assert_no_generation_prompt(visual_rules: Mapping[str, Any]) -> None:
    """Raise if ``visual_rules`` contains a prompt, model reference, or image data.

    Enforced both by key name and by string content, so an image prompt cannot
    be smuggled in under an innocent key.
    """

    if not isinstance(visual_rules, Mapping):
        raise CreatorContractIsolationError("visual_rules must be an object")
    offenders: list[str] = []
    for key, path, _value in _iter_key_paths(visual_rules):
        if key in PROMPT_FORBIDDEN_KEYS:
            offenders.append(f"{path} (forbidden key {key!r})")
    for text, path in _iter_string_paths(visual_rules):
        lowered = text.lower()
        for pattern in PROMPT_CONTENT_PATTERNS:
            if pattern in lowered:
                offenders.append(f"{path} (contains prompt phrase {pattern!r})")
                break
    if offenders:
        raise CreatorContractIsolationError(
            "visual_rules must reference a distilled M5 profile, never a "
            "generation prompt: " + "; ".join(sorted(set(offenders)))
        )


def assert_visual_rules_reference_only(
    visual_rules: Mapping[str, Any],
    profile: Mapping[str, Any] | None = None,
) -> None:
    """Check ``visual_rules`` is a faithful reference to an M5 profile.

    When ``profile`` (the M5 ``factory_config`` projection) is supplied, its
    identifiers and vocabulary must agree with the instance.
    """

    assert_no_generation_prompt(visual_rules)

    if profile is None:
        return

    envelope = profile.get("visual_profile")
    if not isinstance(envelope, Mapping):
        raise CreatorContractDependencyError(
            "M5 profile projection has no visual_profile envelope"
        )

    expected_id = envelope.get("profile_id")
    if expected_id != visual_rules.get("profile_id"):
        raise CreatorContractDependencyError(
            "visual_rules.profile_id "
            f"{visual_rules.get('profile_id')!r} does not match the M5 profile "
            f"{expected_id!r}"
        )
    expected_version = envelope.get("profile_version")
    if expected_version != visual_rules.get("profile_version"):
        raise CreatorContractDependencyError(
            "visual_rules.profile_version "
            f"{visual_rules.get('profile_version')!r} does not match the M5 "
            f"profile {expected_version!r}"
        )

    profile_identity = profile.get("identity")
    if isinstance(profile_identity, Mapping):
        declared_language = visual_rules.get("visual_language")
        actual_language = profile_identity.get("visual_language")
        if declared_language != actual_language:
            raise CreatorContractDependencyError(
                "visual_rules.visual_language "
                f"{declared_language!r} does not match the M5 profile "
                f"{actual_language!r}"
            )

    profile_composition = profile.get("composition")
    if isinstance(profile_composition, Mapping):
        instance_composition = visual_rules.get("composition", {})
        for field in ("preferred_layout", "forbidden_layout"):
            declared = list(instance_composition.get(field, ()))
            actual = list(profile_composition.get(field, ()))
            if sorted(map(str, declared)) != sorted(map(str, actual)):
                raise CreatorContractDependencyError(
                    f"visual_rules.composition.{field} does not match the M5 profile"
                )


def validate_isolation(
    instance: Mapping[str, Any],
    *,
    visual_profile: Mapping[str, Any] | None = None,
) -> None:
    """Run all isolation checks against an instance."""

    assert_no_runtime_code(instance)
    visual_rules = instance.get("visual_rules")
    if not isinstance(visual_rules, Mapping):
        raise CreatorContractIsolationError("instance has no visual_rules block")
    assert_visual_rules_reference_only(visual_rules, visual_profile)
    assert_risk_policy_not_empty(instance)


# --------------------------------------------------------------------------
# Combined entry point
# --------------------------------------------------------------------------


def validate(
    instance: Mapping[str, Any],
    *,
    workspace_root: str | Path | None = None,
    visual_profile: Mapping[str, Any] | None = None,
) -> IsolationReport:
    """Validate an instance completely and return an inspectable report.

    Raises:
        CreatorContractError: if any check fails.
    """

    checks: dict[str, str] = {}

    validate_schema(instance, workspace_root=workspace_root)
    checks["schema"] = "PASS"

    validate_dependencies(instance)
    checks["dependencies"] = "PASS"

    assert_no_phantom_capability(instance)
    checks["capability_declaration"] = "PASS"

    validate_isolation(instance, visual_profile=visual_profile)
    checks["isolation"] = "PASS"

    provenance = instance.get("provenance", {})
    return IsolationReport(
        status="PASS",
        contract_version=str(instance.get("contract_version", "")),
        modules_present=tuple(sorted(instance)),
        provenance_modules=tuple(sorted(provenance)) if isinstance(provenance, Mapping) else (),
        checks=checks,
    )


def _mapping(instance: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = instance.get(key)
    if not isinstance(value, Mapping):
        raise CreatorContractDependencyError(f"{key} must be an object")
    return value


def _sequence(instance: Mapping[str, Any], key: str) -> Sequence[Any]:
    value = instance.get(key)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    raise CreatorContractDependencyError(f"{key} must be an array")


__all__ = [
    "CONTRACT_VERSION",
    "FORBIDDEN_CODE_PATTERNS",
    "ISOLATION_FORBIDDEN_KEYS",
    "ISOLATION_FORBIDDEN_MODULES",
    "IsolationReport",
    "PROMPT_CONTENT_PATTERNS",
    "PROMPT_FORBIDDEN_KEYS",
    "assert_no_generation_prompt",
    "assert_no_phantom_capability",
    "assert_no_runtime_code",
    "assert_provenance_complete",
    "assert_risk_policy_not_empty",
    "assert_visual_rules_reference_only",
    "load_contract_schema",
    "validate",
    "validate_dependencies",
    "validate_isolation",
    "validate_schema",
]
