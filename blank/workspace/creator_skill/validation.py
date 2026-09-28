"""Validation for Creator Skill artifacts.

Four checks, layered so a caller can tell a *shape* problem from a *policy*
problem:

1. :func:`validate_schema` - the document matches the generated JSON Schema.
2. :func:`validate_semantics` - the declared skill makes sense: known type, semver
   version, enough capabilities, non-empty inputs and outputs.
3. :func:`validate_provenance` - the skill names a real source, and a
   ``distillation_artifact`` or ``projection`` source resolves in the asset
   registry. A skill with no source is rejected.
4. :func:`validate_isolation` - the skill carries no prompt, no model call, and no
   runtime code. A skill is a capability declaration, not executable code.

:func:`validate_skill` runs all four and returns an inspectable report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from creator_contract import ISOLATION_FORBIDDEN_KEYS, PROMPT_FORBIDDEN_KEYS
from creator_contract.validation import FORBIDDEN_CODE_PATTERNS

from .errors import (
    SkillError,
    SkillIsolationError,
    SkillProvenanceError,
    SkillSchemaError,
)
from .model import PROVENANCE_SOURCES, CreatorSkill, SkillProvenance
from .schema import minimum_capabilities, validate_schema_document
from .taxonomy import SKILL_TYPE_ORDER, is_known_skill_type

#: Semantic version ``X.Y.Z`` with optional pre-release/build suffix.
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")

#: Skill identifiers are lowercase, hyphenated or underscored.
_SKILL_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")

#: Keys that mean "this skill is carrying runtime behaviour".
#:
#: Extends the contract's isolation keys with skill-specific ones. A capability
#: declaration has no reason to name these.
SKILL_ISOLATION_KEYS: tuple[str, ...] = tuple(
    sorted(
        set(ISOLATION_FORBIDDEN_KEYS)
        | {
            "model_call",
            "api_call",
            "api_key",
            "credentials",
            "endpoint",
            "webhook",
            "executor",
            "handler",
            "callback",
            "implementation",
            "code",
            "entrypoint",
        }
    )
)

#: Keys prohibited inside a skill, which the contract's prompt denylist covers
#: plus a few skill-specific additions.
SKILL_PROMPT_KEYS: tuple[str, ...] = tuple(
    sorted(set(PROMPT_FORBIDDEN_KEYS) | {"prompt_template", "prompting"})
)

#: Prompt-ish phrases that must not appear as string content.
SKILL_PROMPT_PHRASES: tuple[str, ...] = (
    "create image",
    "generate image",
    "image prompt",
    "system prompt",
    "you are a",
    "act as a",
    "write a viral",
)

#: Modules a skill must never import or reference.
SKILL_FORBIDDEN_MODULES: tuple[str, ...] = (
    "distillation_core",
    "runtime",
    "production",
    "risk_evaluation",
    "workflows",
    "multimodal_creator",
)


@dataclass(frozen=True, slots=True)
class SkillValidationReport:
    """Result of validating one skill."""

    skill_id: str
    skill_type: str
    version: str
    checks: Mapping[str, str]

    @property
    def passed(self) -> bool:
        return all(value == "PASS" for value in self.checks.values())

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "skill_type": self.skill_type,
            "version": self.version,
            "status": self.status,
            "checks": dict(self.checks),
        }


# --------------------------------------------------------------------------
# 1. Schema
# --------------------------------------------------------------------------


def validate_schema(
    skill: CreatorSkill | Mapping[str, Any],
    *,
    schema_path: str | None = None,
) -> None:
    """Validate the skill document against the generated schema."""

    document = skill.as_dict() if isinstance(skill, CreatorSkill) else dict(skill)
    validate_schema_document(document, schema_path=schema_path)


# --------------------------------------------------------------------------
# 2. Semantics
# --------------------------------------------------------------------------


def validate_semantics(skill: CreatorSkill) -> None:
    """Check the declared skill is internally coherent."""

    if not isinstance(skill, CreatorSkill):
        raise SkillError("validate_semantics requires a CreatorSkill")
    if not is_known_skill_type(skill.skill_type):
        raise SkillError(
            f"skill {skill.skill_id!r} declares unknown type {skill.skill_type!r}; "
            f"expected one of: {', '.join(SKILL_TYPE_ORDER)}"
        )
    if not _SKILL_ID.match(skill.skill_id):
        raise SkillError(
            f"skill_id {skill.skill_id!r} must be lowercase and hyphen/underscore "
            "separated"
        )
    if not _SEMVER.match(skill.version):
        raise SkillError(f"skill {skill.skill_id!r} version {skill.version!r} is not X.Y.Z")

    minimum = minimum_capabilities(skill.skill_type)
    if len(skill.capabilities) < minimum:
        raise SkillError(
            f"skill {skill.skill_id!r} declares {len(skill.capabilities)} "
            f"capability(ies); type {skill.skill_type!r} requires at least {minimum}"
        )
    if not skill.inputs:
        raise SkillError(f"skill {skill.skill_id!r} declares no inputs")
    if not skill.outputs:
        raise SkillError(f"skill {skill.skill_id!r} declares no outputs")

    if skill.provenance.skill_version != skill.version:
        raise SkillError(
            f"skill {skill.skill_id!r} version {skill.version!r} does not match its "
            f"provenance skill_version {skill.provenance.skill_version!r}"
        )

    for dependency in skill.dependencies:
        if dependency.target == skill.skill_id:
            raise SkillError(f"skill {skill.skill_id!r} depends on itself")


# --------------------------------------------------------------------------
# 3. Provenance
# --------------------------------------------------------------------------


def validate_provenance(
    skill: CreatorSkill,
    *,
    registered_assets: Sequence[str] | None = None,
) -> None:
    """A skill must name a real source.

    When ``registered_assets`` is supplied, a ``distillation_artifact`` or
    ``projection`` source must resolve in the asset registry, so a skill cannot
    claim to derive from something that does not exist.
    """

    if not isinstance(skill.provenance, SkillProvenance):
        raise SkillProvenanceError(f"skill {skill.skill_id!r} has no provenance")
    provenance = skill.provenance
    if provenance.source_kind not in PROVENANCE_SOURCES:
        raise SkillProvenanceError(
            f"skill {skill.skill_id!r} provenance source_kind "
            f"{provenance.source_kind!r} is not one of: {', '.join(PROVENANCE_SOURCES)}"
        )
    if not provenance.source_ref.strip():
        raise SkillProvenanceError(f"skill {skill.skill_id!r} declares no source_ref")

    if registered_assets is not None and provenance.source_kind in (
        "distillation_artifact",
        "projection",
    ):
        if provenance.source_ref not in set(registered_assets):
            raise SkillProvenanceError(
                f"skill {skill.skill_id!r} claims source {provenance.source_ref!r} "
                "which is not a registered asset"
            )


def assert_provenance_present(skill: CreatorSkill) -> None:
    """Raise when a skill has no usable provenance."""

    if skill.provenance is None:
        raise SkillProvenanceError(f"skill {skill.skill_id!r} has no provenance record")
    if not str(skill.provenance.source_ref).strip():
        raise SkillProvenanceError(f"skill {skill.skill_id!r} has an empty source_ref")


# --------------------------------------------------------------------------
# 4. Isolation
# --------------------------------------------------------------------------


def _walk(document: Any, prefix: str = ""):
    if isinstance(document, Mapping):
        for key, value in document.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield str(key).lower(), path, value
            yield from _walk(value, path)
    elif isinstance(document, Sequence) and not isinstance(document, (str, bytes)):
        for index, item in enumerate(document):
            yield from _walk(item, f"{prefix}[{index}]")


def _iter_strings(document: Any, prefix: str = ""):
    """Yield every string anywhere in the document, with its path.

    Separate from :func:`_walk` because a check that reads *values* must see
    strings nested inside sequences, which the key-walking generator reports only
    as the containing list.
    """

    if isinstance(document, Mapping):
        for key, value in document.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _iter_strings(value, path)
    elif isinstance(document, Sequence) and not isinstance(document, (str, bytes)):
        for index, item in enumerate(document):
            yield from _iter_strings(item, f"{prefix}[{index}]")
    elif isinstance(document, str):
        yield document, prefix


def assert_no_prompt(skill: CreatorSkill | Mapping[str, Any]) -> None:
    """Raise when a skill carries a prompt."""

    document = skill.as_dict() if isinstance(skill, CreatorSkill) else dict(skill)
    offenders: list[str] = []
    for key, path, _value in _walk(document):
        if key in SKILL_PROMPT_KEYS:
            offenders.append(f"{path} (forbidden key {key!r})")
    for text, path in _iter_strings(document):
        lowered = text.lower()
        for phrase in SKILL_PROMPT_PHRASES:
            if phrase in lowered:
                offenders.append(f"{path} (contains prompt phrase {phrase!r})")
                break
    if offenders:
        raise SkillIsolationError(
            "a creator skill is a capability declaration and must not carry a "
            "prompt: " + "; ".join(sorted(set(offenders)))
        )


def assert_no_model_call(skill: CreatorSkill | Mapping[str, Any]) -> None:
    """Raise when a skill declares a model invocation."""

    document = skill.as_dict() if isinstance(skill, CreatorSkill) else dict(skill)
    offenders: list[str] = []
    for key, path, _value in _walk(document):
        if key in ("model", "model_id", "model_call", "model_reference", "api_call"):
            offenders.append(f"{path} (forbidden key {key!r})")
    for text, path in _iter_strings(document):
        lowered = text.lower()
        for token in ("openai", "anthropic", "gemini", "httpx", "requests."):
            if token in lowered:
                offenders.append(f"{path} (contains {token!r})")
                break
    if offenders:
        raise SkillIsolationError(
            "a creator skill must not declare a model call: "
            + "; ".join(sorted(set(offenders)))
        )


def assert_no_runtime_code(skill: CreatorSkill | Mapping[str, Any]) -> None:
    """Raise when a skill carries code or references a runtime module."""

    document = skill.as_dict() if isinstance(skill, CreatorSkill) else dict(skill)
    offenders: list[str] = []
    for key, path, _value in _walk(document):
        if key in SKILL_ISOLATION_KEYS:
            offenders.append(f"{path} (forbidden key {key!r})")
    for text, path in _iter_strings(document):
        offenders.extend(_code_offenders(text, path))
    if offenders:
        raise SkillIsolationError(
            "creator skill must be a declaration only; found runtime content: "
            + "; ".join(sorted(set(offenders)))
        )


def _code_offenders(text: str, path: str) -> list[str]:
    """Return every code-shaped reason one string value is rejected."""

    lowered = text.lower()
    found: list[str] = []
    for pattern in FORBIDDEN_CODE_PATTERNS:
        if pattern in lowered:
            found.append(f"{path} (contains {pattern!r})")
            break
    for module in SKILL_FORBIDDEN_MODULES:
        if f"{module}." in lowered or f"import {module}" in lowered:
            found.append(f"{path} (references runtime module {module!r})")
            break
    if "skills/" in lowered:
        found.append(f"{path} (contains a hard-coded skill path)")
    return found


def validate_isolation(skill: CreatorSkill | Mapping[str, Any]) -> None:
    """Run all isolation checks against a skill."""

    assert_no_prompt(skill)
    assert_no_model_call(skill)
    assert_no_runtime_code(skill)


# --------------------------------------------------------------------------
# Combined
# --------------------------------------------------------------------------


def validate_skill(
    skill: CreatorSkill,
    *,
    registered_assets: Sequence[str] | None = None,
    schema_path: str | None = None,
) -> SkillValidationReport:
    """Validate a skill completely and return an inspectable report."""

    if not isinstance(skill, CreatorSkill):
        raise SkillError("validate_skill requires a CreatorSkill")

    checks: dict[str, str] = {}
    validate_schema(skill, schema_path=schema_path)
    checks["schema"] = "PASS"
    validate_semantics(skill)
    checks["semantics"] = "PASS"
    validate_provenance(skill, registered_assets=registered_assets)
    checks["provenance"] = "PASS"
    validate_isolation(skill)
    checks["isolation"] = "PASS"

    return SkillValidationReport(
        skill_id=skill.skill_id,
        skill_type=skill.skill_type,
        version=skill.version,
        checks=checks,
    )


def validate_document(
    document: Mapping[str, Any],
    *,
    registered_assets: Sequence[str] | None = None,
    schema_path: str | None = None,
) -> SkillValidationReport:
    """Validate a raw skill document by building a skill from it."""

    from .registry import skill_from_document

    return validate_skill(
        skill_from_document(document),
        registered_assets=registered_assets,
        schema_path=schema_path,
    )


__all__ = [
    "SKILL_FORBIDDEN_MODULES",
    "SKILL_ISOLATION_KEYS",
    "SKILL_PROMPT_KEYS",
    "SKILL_PROMPT_PHRASES",
    "SkillValidationReport",
    "assert_no_model_call",
    "assert_no_prompt",
    "assert_no_runtime_code",
    "assert_provenance_present",
    "validate_document",
    "validate_isolation",
    "validate_provenance",
    "validate_schema",
    "validate_semantics",
    "validate_skill",
]
