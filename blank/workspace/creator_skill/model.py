"""A Creator Skill is a declared capability, never executable code.

A skill states what a Creator Agent *can do* and what it *needs*. It does not
carry a prompt, a model call, or runtime code. This module defines the immutable
value objects; :mod:`creator_skill.validation` enforces the isolation rules.

Design notes
------------

* Everything is a frozen dataclass, so a registered skill cannot be mutated in
  place. Registry operations return copies or new objects.
* ``capabilities`` are ordered and deduplicated on construction.
* ``dependencies`` are ``require`` / ``enhance`` / ``conflict`` edges, which is
  what makes a bundle checkable as a graph rather than a list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .errors import SkillError

#: Relationship kinds a dependency edge may declare.
DEPENDENCY_KINDS: tuple[str, ...] = ("require", "enhance", "conflict")

#: Where a skill came from. ``source_ref`` must name an asset for every kind
#: except ``manual``.
PROVENANCE_SOURCES: tuple[str, ...] = (
    "template",
    "distillation_artifact",
    "projection",
    "manual",
)

#: Maturity of a declared skill.
SKILL_STATUSES: tuple[str, ...] = ("available", "unavailable", "declared")


def _require_non_empty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillError(f"{field_name} must be a non-empty string")
    return value.strip()


def _require_sequence(value: Any, field_name: str) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise SkillError(f"{field_name} must be a sequence")
    return tuple(value)


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for item in values:
        seen.setdefault(item, None)
    return tuple(seen)


@dataclass(frozen=True, slots=True)
class SkillDependency:
    """One edge from a skill to another skill or capability."""

    target: str
    kind: str = "require"
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", _require_non_empty(self.target, "dependency target"))
        if self.kind not in DEPENDENCY_KINDS:
            raise SkillError(
                f"dependency kind {self.kind!r} is not one of: {', '.join(DEPENDENCY_KINDS)}"
            )

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {"target": self.target, "kind": self.kind}
        if self.reason:
            record["reason"] = self.reason
        return record


@dataclass(frozen=True, slots=True)
class SkillProvenance:
    """Where a skill came from. A skill with no source is invalid."""

    source_kind: str
    source_ref: str
    skill_version: str
    generated_at: str
    confidence: float = 1.0
    note: str = ""

    def __post_init__(self) -> None:
        if self.source_kind not in PROVENANCE_SOURCES:
            raise SkillError(
                f"provenance source_kind {self.source_kind!r} is not one of: "
                f"{', '.join(PROVENANCE_SOURCES)}"
            )
        object.__setattr__(
            self, "source_ref", _require_non_empty(self.source_ref, "provenance source_ref")
        )
        object.__setattr__(
            self, "skill_version", _require_non_empty(self.skill_version, "skill_version")
        )
        object.__setattr__(
            self, "generated_at", _require_non_empty(self.generated_at, "generated_at")
        )
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise SkillError("provenance confidence must be numeric")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise SkillError("provenance confidence must be within 0..1")

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "skill_version": self.skill_version,
            "generated_at": self.generated_at,
            "confidence": float(self.confidence),
        }
        if self.note:
            record["note"] = self.note
        return record


@dataclass(frozen=True, slots=True)
class SkillCompatibility:
    """What an instance must satisfy for this skill to be usable."""

    domains: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    requires_contract_version: str = "1.0.0"

    def __post_init__(self) -> None:
        for name in ("domains", "platforms", "styles"):
            object.__setattr__(
                self, name, _dedupe(_require_sequence(getattr(self, name), name))
            )
        object.__setattr__(
            self,
            "requires_contract_version",
            _require_non_empty(self.requires_contract_version, "requires_contract_version"),
        )

    def matches_domain(self, domain: str | None) -> bool:
        """An empty declaration is a wildcard; otherwise it must contain the value."""

        if not self.domains:
            return True
        return domain in self.domains

    def matches_platform(self, platform: str | None) -> bool:
        if not self.platforms:
            return True
        return platform in self.platforms

    def matches_style(self, style: str | None) -> bool:
        if not self.styles:
            return True
        return style in self.styles

    def as_dict(self) -> dict[str, Any]:
        return {
            "domains": list(self.domains),
            "platforms": list(self.platforms),
            "styles": list(self.styles),
            "requires_contract_version": self.requires_contract_version,
        }


@dataclass(frozen=True, slots=True)
class CreatorSkill:
    """A declared creator capability."""

    skill_id: str
    skill_type: str
    version: str
    description: str
    capabilities: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    dependencies: tuple[SkillDependency, ...]
    compatibility: SkillCompatibility
    provenance: SkillProvenance
    status: str = "available"
    reason: str = ""
    reusable: bool = True
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "skill_id", _require_non_empty(self.skill_id, "skill_id"))
        object.__setattr__(self, "skill_type", _require_non_empty(self.skill_type, "skill_type"))
        object.__setattr__(self, "version", _require_non_empty(self.version, "version"))
        object.__setattr__(
            self, "description", _require_non_empty(self.description, "description")
        )
        if not isinstance(self.compatibility, SkillCompatibility):
            raise SkillError("compatibility must be a SkillCompatibility")
        if not isinstance(self.provenance, SkillProvenance):
            raise SkillError("provenance must be a SkillProvenance")
        if self.status not in SKILL_STATUSES:
            raise SkillError(
                f"status {self.status!r} is not one of: {', '.join(SKILL_STATUSES)}"
            )
        if self.status != "available" and not self.reason.strip():
            raise SkillError(
                f"skill {self.skill_id!r} is {self.status} but declares no reason"
            )

        object.__setattr__(
            self, "capabilities", _dedupe(_require_sequence(self.capabilities, "capabilities"))
        )
        object.__setattr__(self, "inputs", _dedupe(_require_sequence(self.inputs, "inputs")))
        object.__setattr__(self, "outputs", _dedupe(_require_sequence(self.outputs, "outputs")))
        object.__setattr__(self, "tags", _dedupe(_require_sequence(self.tags, "tags")))

        dependencies = _require_sequence(self.dependencies, "dependencies")
        for dependency in dependencies:
            if not isinstance(dependency, SkillDependency):
                raise SkillError("every dependency must be a SkillDependency")
        object.__setattr__(self, "dependencies", dependencies)

        if not self.capabilities:
            raise SkillError(f"skill {self.skill_id!r} declares no capabilities")

    @property
    def available(self) -> bool:
        return self.status == "available"

    def requires(self) -> tuple[str, ...]:
        return tuple(d.target for d in self.dependencies if d.kind == "require")

    def enhances(self) -> tuple[str, ...]:
        return tuple(d.target for d in self.dependencies if d.kind == "enhance")

    def conflicts_with(self) -> tuple[str, ...]:
        return tuple(d.target for d in self.dependencies if d.kind == "conflict")

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "skill_id": self.skill_id,
            "skill_type": self.skill_type,
            "version": self.version,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "dependencies": [d.as_dict() for d in self.dependencies],
            "compatibility": self.compatibility.as_dict(),
            "provenance": self.provenance.as_dict(),
            "status": self.status,
            "reusable": self.reusable,
        }
        if self.reason:
            record["reason"] = self.reason
        if self.tags:
            record["tags"] = list(self.tags)
        return record


@dataclass(frozen=True, slots=True)
class CreatorRequest:
    """What a caller asks the factory for.

    ``allow_unavailable`` defaults to ``True``, which means a declared-but-not-yet
    implemented skill may be **selected and marked** rather than omitted. That is
    the honest default: the bundle names the capability, records its status, and
    lets a caller see exactly what is missing. Set it to ``False`` to demand a
    bundle in which every capability is actually available - today that raises,
    because source acquisition, generation and publishing are unimplemented.
    """

    domain: str
    platform: str
    style: str = "education"
    creator_id: str = ""
    required_skill_types: tuple[str, ...] = ()
    declared_capabilities: tuple[str, ...] = ()
    allow_unavailable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "domain", _require_non_empty(self.domain, "domain"))
        object.__setattr__(self, "platform", _require_non_empty(self.platform, "platform"))
        object.__setattr__(self, "style", _require_non_empty(self.style, "style"))
        object.__setattr__(
            self,
            "required_skill_types",
            _dedupe(_require_sequence(self.required_skill_types, "required_skill_types")),
        )
        object.__setattr__(
            self,
            "declared_capabilities",
            _dedupe(_require_sequence(self.declared_capabilities, "declared_capabilities")),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "platform": self.platform,
            "style": self.style,
            "creator_id": self.creator_id,
            "required_skill_types": list(self.required_skill_types),
            "declared_capabilities": list(self.declared_capabilities),
            "allow_unavailable": self.allow_unavailable,
        }


@dataclass(frozen=True, slots=True)
class SkillSelection:
    """One selected skill, with the reason it was chosen."""

    skill_type: str
    skill_id: str
    version: str
    reason: str
    score: float = 1.0
    status: str = "available"

    def as_dict(self) -> dict[str, Any]:
        return {
            "skill_type": self.skill_type,
            "skill_id": self.skill_id,
            "version": self.version,
            "reason": self.reason,
            "score": float(self.score),
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class SkillBundle:
    """A verified set of skills.

    ``selections`` holds exactly one skill per selected skill *type* - the
    creator's spine. ``extras`` holds additional skills of an already-satisfied
    type, such as a visual-style distillation alongside text distillation. Keeping
    the two apart is what lets a bundle have, say, two distillation skills without
    breaking the one-per-type rule.
    """

    bundle_id: str
    request: CreatorRequest
    selections: tuple[SkillSelection, ...]
    provenance: SkillProvenance
    extras: tuple[SkillSelection, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)
    alternatives: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_id", _require_non_empty(self.bundle_id, "bundle_id"))
        object.__setattr__(
            self, "selections", _require_sequence(self.selections, "selections")
        )
        object.__setattr__(self, "extras", _require_sequence(self.extras, "extras"))
        object.__setattr__(self, "notes", _require_sequence(self.notes, "notes"))
        seen: set[str] = set()
        for selection in self.selections:
            if not isinstance(selection, SkillSelection):
                raise SkillError("every selection must be a SkillSelection")
            if selection.skill_type in seen:
                raise SkillError(
                    f"bundle selects skill type {selection.skill_type!r} more than once"
                )
            seen.add(selection.skill_type)
        for extra in self.extras:
            if not isinstance(extra, SkillSelection):
                raise SkillError("every extra must be a SkillSelection")
        core_ids = {s.skill_id for s in self.selections}
        for extra in self.extras:
            if extra.skill_id in core_ids:
                raise SkillError(
                    f"skill {extra.skill_id!r} appears both as a selection and an extra"
                )

    def skill_ids(self) -> tuple[str, ...]:
        """Every skill id the bundle references, core and extra."""

        return tuple(s.skill_id for s in (*self.selections, *self.extras))

    def all_selections(self) -> tuple[SkillSelection, ...]:
        return (*self.selections, *self.extras)

    def by_type(self, skill_type: str) -> SkillSelection | None:
        for selection in self.selections:
            if selection.skill_type == skill_type:
                return selection
        return None

    def selected_types(self) -> tuple[str, ...]:
        return tuple(s.skill_type for s in self.selections)

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "request": self.request.as_dict(),
            "selections": [s.as_dict() for s in self.selections],
            "extras": [s.as_dict() for s in self.extras],
            "provenance": self.provenance.as_dict(),
            "notes": list(self.notes),
            "alternatives": {
                key: list(value) for key, value in sorted(self.alternatives.items())
            },
        }


@dataclass(frozen=True, slots=True)
class CompositionResult:
    """A bundle plus the full explanation of how it was composed."""

    bundle: SkillBundle
    reasons: Mapping[str, str]
    rejected: Mapping[str, tuple[str, ...]]
    unsatisfied: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.unsatisfied

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle": self.bundle.as_dict(),
            "reasons": dict(sorted(self.reasons.items())),
            "rejected": {k: list(v) for k, v in sorted(self.rejected.items())},
            "unsatisfied": list(self.unsatisfied),
            "complete": self.complete,
        }


__all__ = [
    "CompositionResult",
    "CreatorRequest",
    "CreatorSkill",
    "DEPENDENCY_KINDS",
    "PROVENANCE_SOURCES",
    "SKILL_STATUSES",
    "SkillBundle",
    "SkillCompatibility",
    "SkillDependency",
    "SkillProvenance",
    "SkillSelection",
]
