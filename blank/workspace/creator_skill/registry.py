"""The Creator Skill registry.

One place where skills live. Nothing else in the layer hard-codes a skill path or
a skill id: skills arrive as declarative documents (see
:mod:`creator_skill.catalog`) and are validated before registration.

Operations, as the brief requires:

* :meth:`SkillRegistry.register` - add a skill, rejecting duplicates.
* :meth:`SkillRegistry.resolve` - look a skill up by id, optionally by exact
  version (``skill_id@1.2.0``).
* :meth:`SkillRegistry.validate_dependency` - check one skill's edges, and the
  whole registry's graph, including cycles and conflicts.
* :meth:`SkillRegistry.list_available` - enumerate what can be composed.

A skill that fails validation is never registered, so a broken skill cannot
reach a bundle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .errors import (
    SkillDependencyError,
    SkillRegistryError,
    SkillSchemaError,
)
from .model import (
    CreatorSkill,
    SkillCompatibility,
    SkillDependency,
    SkillProvenance,
)
from .taxonomy import SKILL_TYPE_ORDER, is_known_skill_type

#: Separator between a skill id and an exact version in a resolver string.
VERSION_SEPARATOR = "@"


def skill_from_document(document: Mapping[str, Any]) -> CreatorSkill:
    """Build a :class:`CreatorSkill` from a declarative document.

    Unknown keys are rejected rather than ignored, so a typo cannot silently drop
    a declaration.
    """

    if not isinstance(document, Mapping):
        raise SkillSchemaError("skill document must be a mapping")

    known = {
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
        "reason",
        "reusable",
        "tags",
    }
    unknown = sorted(set(document) - known)
    if unknown:
        raise SkillSchemaError(
            "skill document has unexpected fields: " + ", ".join(unknown)
        )

    compatibility = document.get("compatibility")
    if not isinstance(compatibility, Mapping):
        raise SkillSchemaError("skill document has no compatibility block")
    provenance = document.get("provenance")
    if not isinstance(provenance, Mapping):
        raise SkillSchemaError("skill document has no provenance block")

    dependencies: list[SkillDependency] = []
    raw_dependencies = document.get("dependencies", ())
    if isinstance(raw_dependencies, (str, bytes)) or not isinstance(
        raw_dependencies, Sequence
    ):
        raise SkillSchemaError("skill dependencies must be a sequence")
    for entry in raw_dependencies:
        if isinstance(entry, SkillDependency):
            dependencies.append(entry)
            continue
        if not isinstance(entry, Mapping):
            raise SkillSchemaError("every dependency must be a mapping")
        dependencies.append(
            SkillDependency(
                target=str(entry.get("target", "")),
                kind=str(entry.get("kind", "require")),
                reason=str(entry.get("reason", "")),
            )
        )

    return CreatorSkill(
        skill_id=str(document.get("skill_id", "")),
        skill_type=str(document.get("skill_type", "")),
        version=str(document.get("version", "")),
        description=str(document.get("description", "")),
        capabilities=tuple(document.get("capabilities", ())),
        inputs=tuple(document.get("inputs", ())),
        outputs=tuple(document.get("outputs", ())),
        dependencies=tuple(dependencies),
        compatibility=SkillCompatibility(
            domains=tuple(compatibility.get("domains", ())),
            platforms=tuple(compatibility.get("platforms", ())),
            styles=tuple(compatibility.get("styles", ())),
            requires_contract_version=str(
                compatibility.get("requires_contract_version", "1.0.0")
            ),
        ),
        provenance=SkillProvenance(
            source_kind=str(provenance.get("source_kind", "")),
            source_ref=str(provenance.get("source_ref", "")),
            skill_version=str(provenance.get("skill_version", "")),
            generated_at=str(provenance.get("generated_at", "")),
            confidence=float(provenance.get("confidence", 1.0)),
            note=str(provenance.get("note", "")),
        ),
        status=str(document.get("status", "available")),
        reason=str(document.get("reason", "")),
        reusable=bool(document.get("reusable", True)),
        tags=tuple(document.get("tags", ())),
    )


@dataclass(frozen=True, slots=True)
class DependencyReport:
    """The outcome of validating a skill's dependency edges."""

    skill_id: str
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]
    conflicts: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing and not self.conflicts

    def as_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "satisfied": list(self.satisfied),
            "missing": list(self.missing),
            "conflicts": list(self.conflicts),
            "passed": self.passed,
        }


class SkillRegistry:
    """A validated, versioned store of Creator Skills."""

    def __init__(self, *, registered_assets: Sequence[str] | None = None) -> None:
        self._skills: dict[str, CreatorSkill] = {}
        self._registered_assets: tuple[str, ...] = tuple(registered_assets or ())

    # -- construction -----------------------------------------------------

    @classmethod
    def from_documents(
        cls,
        documents: Iterable[Mapping[str, Any]],
        *,
        registered_assets: Sequence[str] | None = None,
        validate: bool = True,
    ) -> "SkillRegistry":
        """Build a registry from declarative documents, validating each skill."""

        registry = cls(registered_assets=registered_assets)
        for document in documents:
            registry.register(skill_from_document(document), validate=validate)
        return registry

    @classmethod
    def default(cls, *, validate: bool = True) -> "SkillRegistry":
        """Build the registry from the shipped catalog.

        The catalog is imported lazily so this module has no import-time
        dependency on it.
        """

        from .catalog import DEFAULT_SKILL_CATALOG

        return cls.from_documents(DEFAULT_SKILL_CATALOG, validate=validate)

    # -- access -----------------------------------------------------------

    @property
    def registered_assets(self) -> tuple[str, ...]:
        return self._registered_assets

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, skill_id: object) -> bool:
        return isinstance(skill_id, str) and self._split(skill_id)[0] in self._skills

    def __iter__(self):
        return iter(self._skills.values())

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._skills))

    # -- operations -------------------------------------------------------

    def register(self, skill: CreatorSkill, *, validate: bool = True) -> CreatorSkill:
        """Register a skill. Rejects duplicates and invalid skills."""

        if not isinstance(skill, CreatorSkill):
            raise SkillRegistryError("register requires a CreatorSkill")
        if validate:
            from .validation import validate_skill

            validate_skill(skill, registered_assets=self._registered_assets or None)
        if skill.skill_id in self._skills:
            existing = self._skills[skill.skill_id]
            raise SkillRegistryError(
                f"skill {skill.skill_id!r} is already registered at version "
                f"{existing.version}; skills are immutable once registered"
            )
        self._skills[skill.skill_id] = skill
        return skill

    def unregister(self, skill_id: str) -> CreatorSkill:
        """Remove a skill, refusing if another registered skill requires it."""

        resolved_id, _version = self._split(skill_id)
        skill = self.resolve(resolved_id)
        dependents = sorted(
            other.skill_id
            for other in self._skills.values()
            if resolved_id in other.requires()
        )
        if dependents:
            raise SkillRegistryError(
                f"cannot unregister {resolved_id!r}; required by: "
                + ", ".join(dependents)
            )
        del self._skills[resolved_id]
        return skill

    def resolve(self, skill_id: str, *, version: str | None = None) -> CreatorSkill:
        """Look up a skill by id, or by ``skill_id@version``."""

        resolved_id, inline_version = self._split(skill_id)
        wanted = version or inline_version
        try:
            skill = self._skills[resolved_id]
        except KeyError as exc:
            raise SkillRegistryError(
                f"skill {resolved_id!r} is not registered; registered skills: "
                + ", ".join(self.ids())
            ) from exc
        if wanted is not None and skill.version != wanted:
            raise SkillRegistryError(
                f"skill {resolved_id!r} is registered at version {skill.version!r}, "
                f"not {wanted!r}"
            )
        return skill

    def has(self, skill_id: str) -> bool:
        """Return whether a skill id (optionally versioned) is resolvable."""

        try:
            self.resolve(skill_id)
        except SkillRegistryError:
            return False
        return True

    def list_available(
        self,
        *,
        skill_type: str | None = None,
        require_reusable: bool = False,
    ) -> tuple[CreatorSkill, ...]:
        """List skills that can be composed, in taxonomy then id order."""

        if skill_type is not None and not is_known_skill_type(skill_type):
            raise SkillRegistryError(f"unknown skill type {skill_type!r}")
        selected = [
            skill
            for skill in self._skills.values()
            if skill.available
            and (skill_type is None or skill.skill_type == skill_type)
            and (skill.reusable or not require_reusable)
        ]
        order = {name: index for index, name in enumerate(SKILL_TYPE_ORDER)}
        return tuple(sorted(selected, key=lambda s: (order.get(s.skill_type, 99), s.skill_id)))

    def list_all(self, *, skill_type: str | None = None) -> tuple[CreatorSkill, ...]:
        """List every registered skill, including declared-but-unavailable ones."""

        order = {name: index for index, name in enumerate(SKILL_TYPE_ORDER)}
        selected = [
            skill
            for skill in self._skills.values()
            if skill_type is None or skill.skill_type == skill_type
        ]
        return tuple(sorted(selected, key=lambda s: (order.get(s.skill_type, 99), s.skill_id)))

    def by_type(self, skill_type: str) -> tuple[CreatorSkill, ...]:
        """Return every registered skill of one type."""

        if not is_known_skill_type(skill_type):
            raise SkillRegistryError(f"unknown skill type {skill_type!r}")
        return tuple(
            sorted(
                (s for s in self._skills.values() if s.skill_type == skill_type),
                key=lambda s: s.skill_id,
            )
        )

    def available_assets(self) -> tuple[str, ...]:
        return self._registered_assets

    # -- dependency validation -------------------------------------------

    def validate_dependency(self, skill_id: str) -> DependencyReport:
        """Check one skill's edges against the registry."""

        skill = self.resolve(skill_id)
        satisfied: list[str] = []
        missing: list[str] = []
        conflicts: list[str] = []

        for dependency in skill.dependencies:
            present = self.has(dependency.target)
            if dependency.kind == "conflict":
                if present:
                    conflicts.append(dependency.target)
                continue
            if dependency.kind == "enhance":
                # An enhancement is optional by definition: it sharpens a skill
                # when present and is simply skipped when absent. Only a
                # ``require`` edge can be missing.
                if present:
                    satisfied.append(dependency.target)
                continue
            if present:
                satisfied.append(dependency.target)
            else:
                missing.append(dependency.target)

        return DependencyReport(
            skill_id=skill.skill_id,
            satisfied=tuple(sorted(set(satisfied))),
            missing=tuple(sorted(set(missing))),
            conflicts=tuple(sorted(set(conflicts))),
        )

    def assert_dependencies_resolvable(self, skill_id: str) -> DependencyReport:
        """Raise unless every ``require`` edge resolves and no conflict is present."""

        report = self.validate_dependency(skill_id)
        if report.missing:
            raise SkillDependencyError(
                f"skill {skill_id!r} requires unregistered skills: "
                + ", ".join(report.missing)
            )
        if report.conflicts:
            raise SkillDependencyError(
                f"skill {skill_id!r} conflicts with registered skills: "
                + ", ".join(report.conflicts)
            )
        return report

    def validate_all_dependencies(self) -> Mapping[str, DependencyReport]:
        """Check every registered skill's edges."""

        return {
            skill_id: self.validate_dependency(skill_id) for skill_id in self.ids()
        }

    def assert_no_missing_dependencies(self) -> None:
        """Raise if any registered skill has an unresolvable edge."""

        broken = {
            skill_id: report
            for skill_id, report in self.validate_all_dependencies().items()
            if not report.passed
        }
        if broken:
            details = "; ".join(
                f"{skill_id}: missing={list(report.missing)} "
                f"conflicts={list(report.conflicts)}"
                for skill_id, report in sorted(broken.items())
            )
            raise SkillDependencyError(
                f"{len(broken)} skill(s) have unresolvable dependencies: {details}"
            )

    def topological_order(self) -> tuple[str, ...]:
        """Return skill ids in dependency order, rejecting cycles."""

        remaining = {skill_id: set(self._skills[skill_id].requires()) for skill_id in self._skills}
        ordered: list[str] = []

        while remaining:
            ready = sorted(
                skill_id
                for skill_id, deps in remaining.items()
                if not (deps & set(remaining))
            )
            if not ready:
                cycle = ", ".join(sorted(remaining))
                raise SkillDependencyError(
                    f"dependency cycle among registered skills: {cycle}"
                )
            for skill_id in ready:
                ordered.append(skill_id)
                del remaining[skill_id]

        return tuple(ordered)

    def detect_cycles(self) -> tuple[str, ...]:
        """Return the ids in a cycle, or an empty tuple when the graph is a DAG."""

        try:
            self.topological_order()
        except SkillDependencyError:
            return tuple(sorted(self._skills))
        return ()

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _split(reference: str) -> tuple[str, str | None]:
        if not isinstance(reference, str) or not reference.strip():
            raise SkillRegistryError("skill reference must be a non-empty string")
        reference = reference.strip()
        if VERSION_SEPARATOR in reference:
            skill_id, _, version = reference.partition(VERSION_SEPARATOR)
            if not skill_id.strip() or not version.strip():
                raise SkillRegistryError(
                    f"skill reference {reference!r} is not of the form skill_id@version"
                )
            return skill_id.strip(), version.strip()
        return reference, None

    def as_dict(self) -> dict[str, Any]:
        """Return the registry as a plain document."""

        return {
            "skills": {skill_id: self._skills[skill_id].as_dict() for skill_id in self.ids()},
            "registered_assets": list(self._registered_assets),
            "count": len(self._skills),
        }


__all__ = [
    "DependencyReport",
    "SkillRegistry",
    "VERSION_SEPARATOR",
    "skill_from_document",
]
