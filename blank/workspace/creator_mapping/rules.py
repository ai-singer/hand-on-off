"""The mapping rules: skill type → instance module, and field → its source.

Two ideas hold this layer together, and both are enforced rather than documented:

1. **A skill never copies a field into the instance.** A skill declares a
   *capability* and names an *asset*; the mapping layer reads that asset and
   derives the instance field from it. A rule therefore records the asset and the
   transform, not the value. Copying ``skill.capabilities`` into the instance
   would be a silent fabrication, because a capability name is not content.

2. **A field with no derivable source is declared unavailable, not defaulted.**
   ``collection_rules``, ``reference_creators``, ``generation`` and ``publishing``
   have no implementing asset anywhere in this repository. Each is emitted with an
   explicit reason. Auto-filling them would break the capability-honesty principle
   that C0.1, C0.2 and C0.3 all enforce, so :mod:`creator_mapping.validation`
   rejects it.

Rule ids are stable and cited in every provenance record, so a reviewer can go
from an instance field back to the rule that produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import MappingRuleError

#: How a target field is derived.
FIELD_MODES: tuple[str, ...] = (
    # derived from a resolved asset's content
    "asset",
    # a structural value the mapping layer must supply (creator id, platform)
    "structural",
    # the field must exist for the contract, but no source backs it. The mapper
    # emits an explicit declaration of absence - `not_available: true` plus a
    # reason - and never a substitute value.
    "not_available",
    # the field has no place in the contract-valid document at all (an open module
    # object). The absence is recorded in the module's availability block and as a
    # provenance record, so nothing is silently dropped.
    "unavailable",
    # an adapter routing declaration: never enabled by mapping
    "capability",
)

#: Which skill type feeds which instance module.
#:
#: ``domain`` feeds ``source`` as well as contributing to ``identity``, because the
#: domain taxonomy is where collection keywords come from - a fact the C0.3
#: taxonomy already encodes by putting ``source`` after ``domain`` in
#: ``requires_prior``.
SKILL_MODULE_RULES: Mapping[str, tuple[str, ...]] = {
    "identity": ("identity",),
    "domain": ("identity", "source"),
    "source": ("source",),
    "distillation": ("text_rules", "visual_rules"),
    "generation": ("generation",),
    "review": ("risk_policy",),
    "publishing": ("publishing",),
}

#: Which asset each module is read from, by skill type.
#:
#: The asset id itself comes from the skill's provenance; this table says which
#: module consumes it. A skill whose asset is unavailable still reaches its module,
#: where the unavailability is declared.
MODULE_SKILL_RULES: Mapping[str, str] = {
    "identity": "identity",
    "source": "domain",
    "text_rules": "distillation",
    "visual_rules": "distillation",
    "risk_policy": "review",
    "generation": "generation",
    "publishing": "publishing",
}


@dataclass(frozen=True, slots=True)
class FieldRule:
    """One target field and where its value comes from."""

    rule_id: str
    module: str
    path: str
    mode: str
    skill_type: str
    description: str
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        for name in ("rule_id", "module", "path", "skill_type", "description"):
            if not str(getattr(self, name)).strip():
                raise MappingRuleError(f"field rule {self.rule_id!r} has an empty {name}")
        if self.mode not in FIELD_MODES:
            raise MappingRuleError(
                f"field rule {self.rule_id!r} has unknown mode {self.mode!r}; "
                f"expected one of: {', '.join(FIELD_MODES)}"
            )
        if self.mode in ("unavailable", "not_available") and not self.unavailable_reason.strip():
            raise MappingRuleError(
                f"unavailable rule {self.rule_id!r} must declare why"
            )

    @property
    def unavailable(self) -> bool:
        return self.mode in ("unavailable", "not_available")

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "rule_id": self.rule_id,
            "module": self.module,
            "path": self.path,
            "mode": self.mode,
            "skill_type": self.skill_type,
            "description": self.description,
        }
        if self.unavailable_reason:
            record["unavailable_reason"] = self.unavailable_reason
        return record


def _rule(
    rule_id: str,
    module: str,
    path: str,
    mode: str,
    skill_type: str,
    description: str,
    unavailable_reason: str = "",
) -> FieldRule:
    return FieldRule(
        rule_id=rule_id,
        module=module,
        path=path,
        mode=mode,
        skill_type=skill_type,
        description=description,
        unavailable_reason=unavailable_reason,
    )


#: Every target field of a mapped instance, with its rule.
FIELD_RULES: tuple[FieldRule, ...] = (
    # ---- identity -------------------------------------------------------
    _rule("RULE_IDENTITY_001", "identity", "creator_id", "structural", "identity",
          "instance identity comes from the bundle id, so the artifact is self-identifying"),
    _rule("RULE_IDENTITY_002", "identity", "name", "structural", "identity",
          "display name defaults to the creator id; the bundle names no other"),
    _rule("RULE_IDENTITY_003", "identity", "domain", "structural", "domain",
          "domain comes from the request and must be a value the contract accepts"),
    _rule("RULE_IDENTITY_004", "identity", "persona", "asset", "domain",
          "persona is derived from the domain skill's value-rule sections"),
    _rule("RULE_IDENTITY_005", "identity", "audience", "not_available", "identity",
          "the contract requires an audience value; no audience model exists in this "
          "repository, so an explicit declaration of absence is emitted instead",
          unavailable_reason="audience_model_not_available"),
    _rule("RULE_IDENTITY_006", "identity", "tone", "asset", "distillation",
          "tone is derived from the distillation skill's declared boundaries"),
    _rule("RULE_IDENTITY_007", "identity", "platform", "structural", "publishing",
          "platform comes from the request, which the contract validates"),
    _rule("RULE_IDENTITY_008", "identity", "language", "structural", "identity",
          "language defaults to the contract's value for a Chinese-platform creator"),
    # ---- source ---------------------------------------------------------
    _rule("RULE_SOURCE_001", "source", "keywords", "asset", "domain",
          "keywords are flattened from the domain skill's value rules"),
    _rule("RULE_SOURCE_002", "source", "data_sources", "asset", "source",
          "data sources are derived from the source skill's declared evidence layer"),
    _rule("RULE_SOURCE_003", "source", "collection_rules", "not_available", "source",
          "collection rules are emitted as an explicit declaration of absence: no "
          "acquisition implementation exists in this repository",
          unavailable_reason="collection_rules_not_available"),
    _rule("RULE_SOURCE_004", "source", "reference_creators", "not_available", "source",
          "reference creators are emitted as an explicit declaration of absence: no "
          "creator-discovery implementation exists and no asset declares a creator",
          unavailable_reason="reference_creator_not_available"),
    # ---- text_rules -----------------------------------------------------
    _rule("RULE_TEXT_001", "text_rules", "title_formula", "asset", "distillation",
          "title formulas are derived from the structure template's section names"),
    _rule("RULE_TEXT_002", "text_rules", "structure", "asset", "distillation",
          "structure is referenced by template id and section names"),
    _rule("RULE_TEXT_003", "text_rules", "tone", "asset", "distillation",
          "text tone is derived from the distillation skill's declared output"),
    _rule("RULE_TEXT_004", "text_rules", "length", "asset", "distillation",
          "length bounds are structural defaults the contract requires"),
    _rule("RULE_TEXT_005", "text_rules", "knowledge_boundary", "asset", "review",
          "knowledge boundaries are derived from the review skill's rubric questions"),
    # ---- visual_rules ---------------------------------------------------
    _rule("RULE_VISUAL_001", "visual_rules", "profile_id", "asset", "distillation",
          "the M5 profile id is referenced, never copied"),
    _rule("RULE_VISUAL_002", "visual_rules", "profile_version", "asset", "distillation",
          "the M5 profile version is referenced, never copied"),
    _rule("RULE_VISUAL_003", "visual_rules", "visual_language", "asset", "distillation",
          "visual language vocabulary is read from the M5 profile"),
    _rule("RULE_VISUAL_004", "visual_rules", "attention_strategy", "asset", "distillation",
          "attention strategy vocabulary is read from the M5 profile"),
    _rule("RULE_VISUAL_005", "visual_rules", "composition", "asset", "distillation",
          "composition rules are read from the M5 profile"),
    _rule("RULE_VISUAL_006", "visual_rules", "hierarchy", "asset", "distillation",
          "hierarchy vocabulary is read from the M5 profile"),
    _rule("RULE_VISUAL_007", "visual_rules", "constraints", "asset", "distillation",
          "visual constraints are read from the M5 profile"),
    _rule("RULE_VISUAL_008", "visual_rules", "provenance", "asset", "distillation",
          "the M5 profile's own provenance is carried through unchanged"),
    # ---- risk_policy ----------------------------------------------------
    _rule("RULE_RISK_001", "risk_policy", "risk_categories", "asset", "review",
          "risk categories are read from the review skill's filter rules"),
    _rule("RULE_RISK_002", "risk_policy", "review_rules", "asset", "review",
          "review decisions are derived from the rubric pass score and the category "
          "severities"),
    _rule("RULE_RISK_003", "risk_policy", "blocked_patterns", "asset", "review",
          "blocked patterns are read from the review skill's filter rules"),
    _rule("RULE_RISK_004", "risk_policy", "evidence_requirement", "asset", "review",
          "evidence requirements are derived from the rubric's finance checks"),
    _rule("RULE_RISK_005", "risk_policy", "review_required", "structural", "review",
          "review is required whenever a risk policy exists"),
    _rule("RULE_RISK_006", "risk_policy", "source", "structural", "review",
          "the declared origin of the policy is recorded"),
    _rule("RULE_RISK_007", "risk_policy", "runtime_connected", "structural", "review",
          "mapping declares policy; it does not connect an evaluator to the runtime"),
    _rule("RULE_RISK_008", "risk_policy", "enabled", "capability", "review",
          "the review capability is available when its asset resolved"),
    # ---- generation -----------------------------------------------------
    _rule("RULE_GEN_001", "generation", "adapter_ref", "capability", "generation",
          "names the adapter a deployment would inject"),
    _rule("RULE_GEN_002", "generation", "input", "capability", "generation",
          "declares the generation input projection the runtime contract defines"),
    _rule("RULE_GEN_003", "generation", "output_format", "capability", "generation",
          "declares the output format"),
    _rule("RULE_GEN_004", "generation", "quality_gate", "capability", "generation",
          "generation may only run after the quality gate returns PASS"),
    _rule("RULE_GEN_005", "generation", "enabled", "capability", "generation",
          "enabled only when the generation skill is available; mapping never "
          "enables an absent capability"),
    _rule("RULE_GEN_006", "generation", "reason", "capability", "generation",
          "records why generation is disabled"),
    # ---- publishing -----------------------------------------------------
    _rule("RULE_PUB_001", "publishing", "platform", "capability", "publishing",
          "the publishing target platform"),
    _rule("RULE_PUB_002", "publishing", "image_requirement", "capability", "publishing",
          "media requirements a publisher would need"),
    _rule("RULE_PUB_003", "publishing", "api", "capability", "publishing",
          "names the publisher adapter and its idempotency key source"),
    _rule("RULE_PUB_004", "publishing", "schedule", "capability", "publishing",
          "the schedule mode, manual by default"),
    _rule("RULE_PUB_005", "publishing", "requires_human_approval", "capability", "publishing",
          "publishing requires human approval"),
    _rule("RULE_PUB_006", "publishing", "enabled", "capability", "publishing",
          "enabled only when the publishing skill is available; mapping never "
          "enables an absent capability"),
    _rule("RULE_PUB_007", "publishing", "reason", "capability", "publishing",
          "records why publishing is disabled"),
)

#: Target paths that must be present in every mapped instance, per module.
REQUIRED_PATHS: Mapping[str, tuple[str, ...]] = {
    module: tuple(
        rule.path for rule in FIELD_RULES if rule.module == module
    )
    for module in ("identity", "source", "text_rules", "visual_rules",
                   "risk_policy", "generation", "publishing")
}

#: Modules a mapped instance must contain, beyond the contract's own requirement.
MAPPED_MODULES: tuple[str, ...] = (
    "identity",
    "source",
    "text_rules",
    "visual_rules",
    "risk_policy",
    "generation",
    "publishing",
)

#: Capability modules, which may not be enabled by mapping.
CAPABILITY_MODULES: tuple[str, ...] = ("generation", "publishing")


def rules_for_module(module: str) -> tuple[FieldRule, ...]:
    """Return every field rule for a module, in declaration order."""

    return tuple(rule for rule in FIELD_RULES if rule.module == module)


def rule_by_id(rule_id: str) -> FieldRule:
    """Return a rule by id, rejecting an unknown id."""

    for rule in FIELD_RULES:
        if rule.rule_id == rule_id:
            return rule
    raise MappingRuleError(f"unknown mapping rule {rule_id!r}")


def rule_for_path(module: str, path: str) -> FieldRule:
    """Return the rule that governs one target path."""

    for rule in FIELD_RULES:
        if rule.module == module and rule.path == path:
            return rule
    raise MappingRuleError(f"no mapping rule for {module}.{path}")


def unavailable_rules() -> tuple[FieldRule, ...]:
    """Every rule whose target has no implementing source."""

    return tuple(rule for rule in FIELD_RULES if rule.unavailable)


def rule_ids() -> tuple[str, ...]:
    return tuple(rule.rule_id for rule in FIELD_RULES)


__all__ = [
    "CAPABILITY_MODULES",
    "FIELD_MODES",
    "FIELD_RULES",
    "FieldRule",
    "MAPPED_MODULES",
    "MODULE_SKILL_RULES",
    "REQUIRED_PATHS",
    "SKILL_MODULE_RULES",
    "rule_by_id",
    "rule_for_path",
    "rule_ids",
    "rules_for_module",
    "unavailable_rules",
]
