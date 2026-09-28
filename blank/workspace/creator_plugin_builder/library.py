"""The library's own skill declarations — what the Shared Skill Library ships.

Two halves, and the split is the architecture:

**Universal Creator Skills** — how to do a thing, for any domain.
``source-discovery``, ``text-distillation``, ``risk-review`` and the rest. A universal
skill must contain no domain knowledge: if it named one, every new domain would force
a change to the uploaded library, which is the outcome this design exists to prevent.

**Meta Skills** — how to build and check the other half.
``domain-plugin-builder`` turns a request into a domain plugin;
``domain-plugin-validator`` checks one; ``skill-composer`` assembles a set. These are
library content too, and they are what makes a *user* able to say "I want a finance
creator" and get a plugin without anyone writing finance code.

Generated domain plugins are **not** library content. They are produced at run time by
the builder and live with the creator they configure.

This module declares the library; it does not implement the skills. A declaration is
what the builder binds rules to and what the validator checks for pollution. The
declarations are data, so a future phase can emit them as real skill packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .model import (
    META_SKILLS,
    UNIVERSAL_SKILLS,
    PluginLibraryError,
)

#: The library version these declarations were written for.
LIBRARY_VERSION = "1.0.0"

#: What each universal skill operates on, and what it produces.
#:
#: A description here must contain no domain vocabulary — ``audit_layers`` checks
#: that, and this mapping is what it checks. Writing "the finance value rules" in one
#: of these lines would fail the build, which is the intended behaviour.
UNIVERSAL_SKILL_SUMMARIES: Mapping[str, tuple[str, str]] = {
    "identity-rules": (
        "Turn a declared domain identity into an instance identity block.",
        "identity",
    ),
    "source-discovery": (
        "Find and enumerate the material a creator draws from.",
        "source references",
    ),
    "source-normalization": (
        "Normalize raw material into the shape the pipeline consumes.",
        "normalized source records",
    ),
    "text-distillation": (
        "Distill normalized material into the text rules an instance carries.",
        "text rules",
    ),
    "visual-distillation": (
        "Distill visual references into the visual rules an instance carries.",
        "visual rules",
    ),
    "template-extraction": (
        "Extract reusable structure from finished material.",
        "structure templates",
    ),
    "quality-review": (
        "Evaluate an artifact against the shared quality contract.",
        "a review decision with reasons",
    ),
    "risk-review": (
        "Evaluate an artifact against the declared risk constraints.",
        "a risk decision with reasons",
    ),
    "generation-interface": (
        "Declare the interface a generation adapter must satisfy.",
        "a declared capability",
    ),
    "publishing-interface": (
        "Declare the interface a publishing adapter must satisfy.",
        "a declared capability",
    ),
}

#: What each meta skill does.
META_SKILL_SUMMARIES: Mapping[str, tuple[str, str]] = {
    "domain-plugin-builder": (
        "Turn a domain request into a domain plugin document.",
        "a domain plugin",
    ),
    "domain-plugin-validator": (
        "Check a domain plugin for protocol conformance, isolation and provenance.",
        "a validation report",
    ),
    "skill-composer": (
        "Assemble the set of universal skills a composed creator needs.",
        "a skill selection",
    ),
}

#: Meta skills that accept a domain request or a plugin document as input.
META_SKILL_INPUTS: Mapping[str, str] = {
    "domain-plugin-builder": "domain_request",
    "domain-plugin-validator": "domain_plugin",
    "skill-composer": "creator_request",
}


@dataclass(frozen=True, slots=True)
class SkillDeclaration:
    """One library skill: what it is, which layer it belongs to, what it does."""

    name: str
    skill_type: str
    layer: str
    purpose: str
    produces: str
    accepts: str = ""

    @property
    def universal(self) -> bool:
        return self.layer == "universal"

    @property
    def meta(self) -> bool:
        return self.layer == "meta"

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "name": self.name,
            "skill_type": self.skill_type,
            "layer": self.layer,
            "purpose": self.purpose,
            "produces": self.produces,
        }
        if self.accepts:
            record["accepts"] = self.accepts
        return record


def universal_declarations() -> tuple[SkillDeclaration, ...]:
    """Every universal skill the library declares, sorted by name."""

    missing = sorted(set(UNIVERSAL_SKILLS) - set(UNIVERSAL_SKILL_SUMMARIES))
    if missing:  # pragma: no cover - guarded by a test
        raise PluginLibraryError(
            "universal skills have no declared summary: " + ", ".join(missing)
        )
    return tuple(
        SkillDeclaration(
            name=name,
            skill_type=UNIVERSAL_SKILLS[name],
            layer="universal",
            purpose=UNIVERSAL_SKILL_SUMMARIES[name][0],
            produces=UNIVERSAL_SKILL_SUMMARIES[name][1],
        )
        for name in sorted(UNIVERSAL_SKILLS)
    )


def meta_declarations() -> tuple[SkillDeclaration, ...]:
    """Every meta skill the library declares, sorted by name."""

    return tuple(
        SkillDeclaration(
            name=name,
            skill_type=META_SKILLS[name],
            layer="meta",
            purpose=META_SKILL_SUMMARIES[name][0],
            produces=META_SKILL_SUMMARIES[name][1],
            accepts=META_SKILL_INPUTS.get(name, ""),
        )
        for name in sorted(META_SKILLS)
    )


def all_declarations() -> tuple[SkillDeclaration, ...]:
    """The whole library: universal skills and meta skills."""

    return universal_declarations() + meta_declarations()


def skill_declarations() -> dict[str, dict[str, Any]]:
    """The library as a plain document, keyed by skill name.

    This is the input :func:`creator_plugin_builder.validator.audit_layers` scans for
    domain pollution.
    """

    return {entry.name: entry.as_dict() for entry in all_declarations()}


def declaration(name: str) -> SkillDeclaration:
    """One declaration, rejecting an unknown name."""

    for entry in all_declarations():
        if entry.name == name:
            return entry
    raise PluginLibraryError(
        f"the library declares no skill {name!r}",
        detail="declared skills: " + ", ".join(e.name for e in all_declarations()),
    )


def library_document() -> dict[str, Any]:
    """The library manifest, for inspection and for a future upload step."""

    return {
        "library_version": LIBRARY_VERSION,
        "universal_skill_count": len(UNIVERSAL_SKILLS),
        "meta_skill_count": len(META_SKILLS),
        "generated_at_runtime": False,
        "note": (
            "Generated domain plugins are produced by domain-plugin-builder at run "
            "time and are not part of this library."
        ),
        "universal_skills": [e.as_dict() for e in universal_declarations()],
        "meta_skills": [e.as_dict() for e in meta_declarations()],
    }


def skill_composition(request_skills: Mapping[str, Any]) -> dict[str, Any]:
    """Which library skills a set of requirements resolves to.

    ``skill-composer``'s job, stated as data: given a requirement set, report which
    universal skills satisfy it and which requirements nothing satisfies. The second
    list is the useful one — it is the honest statement of what the library cannot
    yet do.
    """

    satisfied: dict[str, str] = {}
    unsatisfied: list[str] = []
    for requirement in sorted(request_skills):
        if requirement in UNIVERSAL_SKILLS:
            satisfied[requirement] = UNIVERSAL_SKILLS[requirement]
        elif requirement in META_SKILLS:
            satisfied[requirement] = META_SKILLS[requirement]
        else:
            unsatisfied.append(requirement)
    return {
        "requested": len(request_skills),
        "satisfied": satisfied,
        "satisfied_count": len(satisfied),
        "unsatisfied": unsatisfied,
        "complete": not unsatisfied,
    }


__all__ = [
    "LIBRARY_VERSION",
    "META_SKILL_INPUTS",
    "META_SKILL_SUMMARIES",
    "UNIVERSAL_SKILL_SUMMARIES",
    "SkillDeclaration",
    "all_declarations",
    "declaration",
    "library_document",
    "meta_declarations",
    "skill_composition",
    "skill_declarations",
    "universal_declarations",
]
