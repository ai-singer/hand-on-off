"""The Creator Skill taxonomy.

A Creator Skill answers exactly one question. Seven types cover the whole
lifecycle of a Creator Agent, from *who speaks* to *where it is published*:

===============  =========================================
Skill type       Question it answers
===============  =========================================
identity         who is speaking
domain           what it knows
source           where it finds material
distillation     how it learns from material
generation       how it produces content
review           what it must refuse
publishing       where output goes
===============  =========================================

The split exists so that skills can be **reused across creators**: a
``xiaohongshu`` publishing skill is shared by a finance creator and a sports
creator, while only ``identity`` and ``domain`` differ. Nothing in this taxonomy
is creator-specific except by compatibility declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import SkillError

#: The seven skill types, in composition order.
SKILL_TYPE_ORDER: tuple[str, ...] = (
    "identity",
    "domain",
    "source",
    "distillation",
    "generation",
    "review",
    "publishing",
)

#: The seven skill type names, qualified as the brief names them.
SKILL_TYPE_NAMES: Mapping[str, str] = {
    "identity": "identity_skill",
    "domain": "domain_skill",
    "source": "source_skill",
    "distillation": "distillation_skill",
    "generation": "generation_skill",
    "review": "review_skill",
    "publishing": "publishing_skill",
}


@dataclass(frozen=True, slots=True)
class SkillType:
    """One taxonomy entry."""

    skill_type: str
    name: str
    responsibility: str
    question: str
    required: bool
    requires_prior: tuple[str, ...]
    description: str
    examples: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "skill_type": self.skill_type,
            "name": self.name,
            "responsibility": self.responsibility,
            "question": self.question,
            "required": self.required,
            "requires_prior": list(self.requires_prior),
            "description": self.description,
            "examples": list(self.examples),
        }


#: The taxonomy. ``requires_prior`` is the composition skeleton: it is the order
#: a bundle must select skills in, and the shape dependency validation checks.
SKILL_TYPES: Mapping[str, SkillType] = {
    "identity": SkillType(
        skill_type="identity",
        name="identity_skill",
        responsibility="是谁",
        question="who is speaking",
        required=True,
        requires_prior=(),
        description=(
            "The persona and voice a creator instance speaks with: identity card, "
            "mental models, decision heuristics, expression guidance, boundaries."
        ),
        examples=("finance_expert_persona", "tim_mediastorm_perspective"),
    ),
    "domain": SkillType(
        skill_type="domain",
        name="domain_skill",
        responsibility="懂什么",
        question="what it knows",
        required=True,
        requires_prior=("identity",),
        description=(
            "The subject-matter taxonomy a creator distils and explains: which "
            "dimensions matter, and how material is valued within them."
        ),
        examples=("stock_analysis", "football_analysis", "ai_news"),
    ),
    "source": SkillType(
        skill_type="source",
        name="source_skill",
        responsibility="去哪里找信息",
        question="where it finds material",
        required=True,
        requires_prior=("domain",),
        description=(
            "Where raw material comes from, and the rules for collecting it: "
            "dual-layer discovery versus evidence sourcing, rate limits, tiering, "
            "identity verification."
        ),
        examples=("xiaohongshu_source", "news_source"),
    ),
    "distillation": SkillType(
        skill_type="distillation",
        name="distillation_skill",
        responsibility="如何学习素材",
        question="how it learns from material",
        required=True,
        requires_prior=("source",),
        description=(
            "How collected material is turned into reusable structure: text "
            "distillation and visual (multimodal) distillation."
        ),
        examples=("text_distillation", "visual_distillation"),
    ),
    "generation": SkillType(
        skill_type="generation",
        name="generation_skill",
        responsibility="如何生成内容",
        question="how it produces content",
        required=True,
        requires_prior=("distillation",),
        description=(
            "How content is produced from a validated artifact. Declared as a "
            "routing capability; the adapter itself is injected by a deployment."
        ),
        examples=("xhs_article_generator",),
    ),
    "review": SkillType(
        skill_type="review",
        name="review_skill",
        responsibility="审核",
        question="what it must refuse",
        required=True,
        requires_prior=("distillation",),
        description=(
            "What must not be produced, and the review decision policy: risk "
            "categories, blocked patterns, evidence requirements, gate outcomes."
        ),
        examples=("finance_risk_review",),
    ),
    "publishing": SkillType(
        skill_type="publishing",
        name="publishing_skill",
        responsibility="发布",
        question="where output goes",
        required=True,
        requires_prior=("review",),
        description=(
            "Where output is published, with what media requirements and "
            "idempotency key. Declared as a target; the publisher is injected."
        ),
        examples=("xhs_publisher",),
    ),
}

#: Types whose skills target a platform and therefore must declare it rather than
#: defaulting to every platform. A Xiaohongshu source skill is not a news source
#: skill, and treating an unstated platform as a match would bundle the wrong one.
PLATFORM_SPECIFIC_TYPES: tuple[str, ...] = ("source", "publishing")

#: Skill types every complete bundle must select.
REQUIRED_SKILL_TYPES: tuple[str, ...] = tuple(
    skill_type
    for skill_type in SKILL_TYPE_ORDER
    if SKILL_TYPES[skill_type].required
)

#: Skill types a bundle may omit.
OPTIONAL_SKILL_TYPES: tuple[str, ...] = tuple(
    skill_type
    for skill_type in SKILL_TYPE_ORDER
    if not SKILL_TYPES[skill_type].required
)

#: Minimum capability count a skill of each type must declare. Applying an
#: empty capability list would be a declaration with nothing in it.
MINIMUM_CAPABILITIES: Mapping[str, int] = {
    "identity": 3,
    "domain": 2,
    "source": 2,
    "distillation": 2,
    "generation": 1,
    "review": 2,
    "publishing": 2,
}


def skill_type(skill_type_id: str) -> SkillType:
    """Return a taxonomy entry, rejecting an unknown type."""

    try:
        return SKILL_TYPES[skill_type_id]
    except KeyError as exc:
        raise SkillError(
            f"unknown skill type {skill_type_id!r}; expected one of: "
            f"{', '.join(SKILL_TYPE_ORDER)}"
        ) from exc


def is_known_skill_type(skill_type_id: str) -> bool:
    return skill_type_id in SKILL_TYPES


def prior_types(skill_type_id: str) -> tuple[str, ...]:
    """Return the skill types that must be chosen before this one."""

    return skill_type(skill_type_id).requires_prior


def composition_order() -> tuple[str, ...]:
    """Return the order skills must be composed in (the taxonomy order)."""

    return SKILL_TYPE_ORDER


def taxonomy_document() -> dict[str, Any]:
    """Return the whole taxonomy as a plain document."""

    return {
        "skill_types": {
            skill_type_id: SKILL_TYPES[skill_type_id].as_dict()
            for skill_type_id in SKILL_TYPE_ORDER
        },
        "required": list(REQUIRED_SKILL_TYPES),
        "optional": list(OPTIONAL_SKILL_TYPES),
        "composition_order": list(SKILL_TYPE_ORDER),
    }


__all__ = [
    "MINIMUM_CAPABILITIES",
    "OPTIONAL_SKILL_TYPES",
    "PLATFORM_SPECIFIC_TYPES",
    "REQUIRED_SKILL_TYPES",
    "SKILL_TYPES",
    "SKILL_TYPE_NAMES",
    "SKILL_TYPE_ORDER",
    "SkillType",
    "composition_order",
    "is_known_skill_type",
    "prior_types",
    "skill_type",
    "taxonomy_document",
]
