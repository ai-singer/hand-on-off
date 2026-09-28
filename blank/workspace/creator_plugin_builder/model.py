"""The domain plugin model, and the two library boundaries it must respect.

# What this module is for

The deliverable of this phase is not a Creator Instance. It is a **Skill Library**:
a set of skills that can be uploaded once and then serve every creator anyone ever
asks for.

```text
                Lobster Shared Skill Library
                            |
        ┌───────────────────┴───────────────────┐
        |                                       |
  Universal Creator Skills                Meta Skills
  (how to do it, domain-free)        (how to build domain plugins)
        |                                       |
        |                            domain-plugin-builder
        |                            domain-plugin-validator
        |                            skill-composer
        |                                       |
        └───────────────────┬───────────────────┘
                            |
                            v
                  Generated Domain Plugins
              (produced at run time by the builder;
               NOT part of the base library)
```

A domain plugin is *generated*, not shipped. It carries what one domain is about so
that the universal skills never have to know.

# The two boundaries

**1. A universal skill contains no domain knowledge.** ``text-distillation`` is the
same skill for finance, sports and technology. If it named a domain keyword, every
new domain would force a change to the library — which is the outcome this
architecture exists to prevent.

**2. A domain plugin contains no runtime.** It is a configuration asset: rules,
bindings and provenance. No model call, no agent loop, no workflow execution, no
prompt. Both boundaries are enforced by :mod:`creator_plugin_builder.validator`, not
merely documented.

# Honesty

Nothing here invents a capability. Every rule a plugin declares is either bound to a
real registered asset, or declared with a machine-readable reason. Where a value is
the domain's own taxonomy rather than something read from an asset, it says so —
see :attr:`RuleBinding.values_source`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from creator_contract import CreatorContractError

#: The domain plugin format version.
PLUGIN_FORMAT_VERSION = "1.0.0"

#: Deterministic timestamps, so one request built twice is byte-identical.
DEFAULT_TIMESTAMP = "1970-01-01T00:00:00Z"

#: Marker for a value an artifact does not record.
NOT_RECORDED = "(not recorded)"

#: Prefix for the reason on every rule that has no implementing asset.
ABSENCE_MARKER = "not_available:"


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class PluginBuilderError(CreatorContractError):
    """Base class for domain-plugin failures. ``code`` is machine-readable."""

    code = "PLUGIN_BUILDER_ERROR"

    #: All codes this class may carry. Subclasses usually declare exactly one.
    codes: tuple[str, ...] = ()

    def __init__(self, message: str, *, detail: str = "", code: str = "") -> None:
        self.detail = detail
        if code:
            self.code = code
        text = f"[{self.code}] {message}"
        if detail:
            text = f"{text}: {detail}"
        super().__init__(text)


class DomainNotFoundError(PluginBuilderError):
    """The requested domain has no catalog entry."""

    code = "DOMAIN_NOT_FOUND"


class DomainRequestError(PluginBuilderError):
    """A domain request is malformed, or names something that does not exist."""

    code = "DOMAIN_REQUEST_INVALID"


class PluginSchemaError(PluginBuilderError):
    """A plugin document does not match the domain plugin schema."""

    code = "PLUGIN_SCHEMA_INVALID"


class PluginRuleError(PluginBuilderError):
    """A rule is malformed, or names an asset or core skill that does not exist."""

    code = "PLUGIN_RULE_INVALID"


class PluginCapabilityError(PluginBuilderError):
    """A rule claims a capability its asset cannot support."""

    code = "PLUGIN_CAPABILITY_INVENTED"


class PluginProvenanceError(PluginBuilderError):
    """The plugin's provenance is incomplete."""

    code = "PLUGIN_PROVENANCE_INVALID"


class PluginIsolationError(PluginBuilderError):
    """The plugin carries runtime code, a prompt, or a forbidden reference."""

    code = "PLUGIN_ISOLATION_VIOLATION"


class PluginLayerError(PluginBuilderError):
    """The universal/domain boundary has been crossed."""

    code = "PLUGIN_LAYER_VIOLATION"


class PluginRegistryError(PluginBuilderError):
    """The registry was asked for something it cannot provide."""

    code = "PLUGIN_REGISTRY_INVALID"


class PluginProtocolError(PluginBuilderError):
    """The plugin does not conform to the unified distillation protocol."""

    code = "PLUGIN_PROTOCOL_INVALID"


class PluginLibraryError(PluginBuilderError):
    """A core skill a plugin names is not declared in the library."""

    code = "PLUGIN_LIBRARY_INVALID"


#: Every code, for a test that asserts the set is stable.
ERROR_CODES: tuple[str, ...] = (
    "DOMAIN_NOT_FOUND",
    "DOMAIN_REQUEST_INVALID",
    "PLUGIN_SCHEMA_INVALID",
    "PLUGIN_RULE_INVALID",
    "PLUGIN_CAPABILITY_INVENTED",
    "PLUGIN_PROVENANCE_INVALID",
    "PLUGIN_ISOLATION_VIOLATION",
    "PLUGIN_LAYER_VIOLATION",
    "PLUGIN_REGISTRY_INVALID",
    "PLUGIN_PROTOCOL_INVALID",
    "PLUGIN_LIBRARY_INVALID",
)


# --------------------------------------------------------------------------
# The library: what a plugin is allowed to bind to
# --------------------------------------------------------------------------

#: The **universal Creator Skills** — the domain-free half of the library.
#:
#: These are the same skills for every domain. ``PLUGIN_CORE_SKILLS`` below is the
#: subset a *domain plugin* binds to; the meta skills build and check the plugins and
#: never appear inside one.
UNIVERSAL_SKILLS: Mapping[str, str] = {
    "identity-rules": "identity",
    "source-discovery": "source",
    "source-normalization": "source",
    "text-distillation": "distillation",
    "visual-distillation": "distillation",
    "template-extraction": "distillation",
    "quality-review": "review",
    "risk-review": "review",
    "publishing-interface": "publishing",
    "generation-interface": "generation",
}

#: The **meta skills** — the half of the library that builds and checks the other half.
META_SKILLS: Mapping[str, str] = {
    "domain-plugin-builder": "builder",
    "domain-plugin-validator": "validator",
    "skill-composer": "composer",
}

#: The core skills a *plugin* may bind to. Meta skills are excluded: a plugin is
#: built *by* them, it does not require them at run time.
PLUGIN_CORE_SKILLS: tuple[str, ...] = tuple(sorted(UNIVERSAL_SKILLS))

#: The six rule slots every domain plugin carries, in architecture order.
PLUGIN_SLOTS: tuple[str, ...] = (
    "identity_rules",
    "source_rules",
    "topic_rules",
    "text_distillation_rules",
    "visual_adaptation_rules",
    "risk_constraints",
)

#: The distillation shape every plugin must declare, in order.
#:
#: The *unified distillation protocol*: whichever domain a plugin describes, a
#: distilled artifact moves from an observation, through its context and mechanism,
#: to its consequence — and then to the evidence that supports it and the boundary
#: that limits it. A domain supplies its own vocabulary for each stage; the stage
#: sequence itself is the protocol and is not negotiable.
PROTOCOL_STAGES: tuple[str, ...] = (
    "observation",
    "context",
    "mechanism",
    "consequence",
    "evidence",
    "boundary",
)

#: Words that must never appear in a universal skill's declaration.
#:
#: Deliberately narrow: platform and style vocabulary is excluded, because this
#: project treats platforms as an axis separate from domains. What remains is
#: unambiguous domain vocabulary.
DOMAIN_MARKERS: tuple[str, ...] = (
    "finance",
    "financial",
    "business",
    "stock",
    "market",
    "investment",
    "investor",
    "portfolio",
    "revenue",
    "sports",
    "athlete",
    "fixture",
    "tournament",
    "league",
    "transfer",
    "football",
    "basketball",
    "technology",
    "software",
    "startup",
    "crypto",
    "health",
    "medical",
    "travel",
    "food",
)

#: Keys that mean a document is carrying a prompt rather than a declaration.
PROMPT_KEYS: tuple[str, ...] = (
    "prompt",
    "prompts",
    "system_prompt",
    "user_prompt",
    "prompt_template",
    "negative_prompt",
    "instruction",
    "instructions",
    "persona_prompt",
    "role_prompt",
)

#: Keys that mean a document is carrying runtime behaviour.
RUNTIME_KEYS: tuple[str, ...] = (
    "code",
    "source_code",
    "script",
    "entrypoint",
    "entry_point",
    "executor",
    "handler",
    "callback",
    "runtime",
    "deploy",
    "deployment",
    "endpoint",
    "webhook",
    "api_key",
    "credentials",
    "secret",
    "token",
    "model_call",
    "api_call",
    "agent_loop",
    "workflow_execution",
    "scheduler",
    "cron",
)

#: Phrase fragments that mean a document is trying to instruct a model.
PROMPT_PHRASES: tuple[str, ...] = (
    "you are a",
    "act as a",
    "system prompt",
    "write a viral",
    "generate image",
    "create image",
    "image prompt",
)

#: Suffixes that mean executable code.
RUNTIME_SUFFIXES: tuple[str, ...] = (
    ".py",
    ".pyc",
    ".sh",
    ".ps1",
    ".bat",
    ".js",
    ".ts",
    ".rb",
    ".exe",
    ".dll",
    ".so",
)

#: Modules a plugin must never reference.
FORBIDDEN_MODULES: tuple[str, ...] = (
    "runtime",
    "production",
    "workflows",
    "risk_evaluation",
    "multimodal_creator",
    "distillation_core",
    "plugins",
)


# --------------------------------------------------------------------------
# The plugin
# --------------------------------------------------------------------------


class RuleStatus(str, Enum):
    """How much of a declared rule actually exists.

    The same three-way honesty the rest of the factory uses: a rule is backed by an
    available asset, or declared with a reason, or absent entirely.
    """

    #: A real, available asset implements this rule.
    AVAILABLE = "available"
    #: The rule is named, its asset is registered, and the asset is not usable.
    DECLARED = "declared"
    #: No asset implements this rule at all.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class RuleBinding:
    """One rule: what implements it, whether that thing exists, and its values.

    ``values_source`` separates two things that would otherwise be conflated:

    - ``"asset"`` — the values were read from the asset this rule binds to, so they
      are traceable to a registered artifact.
    - ``"catalog"`` — the values are this domain's own taxonomy, declared by the
      catalog. That is legitimate: a domain's topic vocabulary *is* domain data,
      which is precisely why it lives in a plugin and not in a universal skill. But
      it is the architecture speaking, not a validated asset, and it is labelled so
      a reviewer can tell the difference.
    """

    slot: str
    core_skill: str
    source_asset: str
    asset_type: str
    status: str
    reason: str = ""
    values: tuple[str, ...] = ()
    values_source: str = "asset"
    deliverable: str = ""

    def __post_init__(self) -> None:
        if not self.slot:
            raise PluginRuleError("a rule needs a slot name")
        if self.core_skill not in PLUGIN_CORE_SKILLS:
            raise PluginLibraryError(
                f"rule {self.slot!r} binds to core skill {self.core_skill!r}, "
                "which the library does not declare",
                detail="declared core skills: " + ", ".join(PLUGIN_CORE_SKILLS),
            )
        if self.status not in tuple(status.value for status in RuleStatus):
            raise PluginRuleError(
                f"rule {self.slot!r} has unknown status {self.status!r}"
            )
        if self.values_source not in ("asset", "catalog"):
            raise PluginRuleError(
                f"rule {self.slot!r} has unknown values_source {self.values_source!r}",
                detail="expected 'asset' or 'catalog'",
            )
        if self.values and self.values_source == "asset" and not self.available:
            raise PluginCapabilityError(
                f"rule {self.slot!r} claims values read from "
                f"{self.source_asset!r}, which is not available",
                detail="values cannot come from an asset that does not exist",
            )
        if self.status != RuleStatus.AVAILABLE.value and not self.reason:
            raise PluginCapabilityError(
                f"rule {self.slot!r} is {self.status} but declares no reason",
                detail="an absent capability must say why it is absent",
            )

    @property
    def available(self) -> bool:
        return self.status == RuleStatus.AVAILABLE.value

    @property
    def value_count(self) -> int:
        return len(self.values)

    @property
    def asset_backed(self) -> bool:
        """Whether this rule's values came from a registered asset."""

        return self.values_source == "asset" and bool(self.values)

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "slot": self.slot,
            "core_skill": self.core_skill,
            "source_asset": self.source_asset,
            "asset_type": self.asset_type,
            "status": self.status,
            "available": self.available,
            "values_source": self.values_source,
            "values": list(self.values),
        }
        if self.reason:
            record["reason"] = self.reason
        if self.deliverable:
            record["deliverable"] = self.deliverable
        return record


@dataclass(frozen=True, slots=True)
class DistillationStage:
    """One stage of the unified distillation protocol, in this domain's words.

    ``stage`` is the protocol's own name and is fixed. ``domain_term`` is what this
    domain calls it, and ``questions`` are what a distiller asks at that stage. That
    pairing is the whole point: the protocol is universal, the vocabulary is not.
    """

    stage: str
    domain_term: str
    core_skill: str
    status: str
    order: int
    source_asset: str = ""
    reason: str = ""
    questions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.stage not in PROTOCOL_STAGES:
            raise PluginProtocolError(
                f"unknown protocol stage {self.stage!r}",
                detail="expected one of: " + ", ".join(PROTOCOL_STAGES),
            )
        if not self.domain_term:
            raise PluginProtocolError(
                f"protocol stage {self.stage!r} declares no domain term",
                detail="the protocol is universal; the vocabulary must be local",
            )
        if self.core_skill not in PLUGIN_CORE_SKILLS:
            raise PluginLibraryError(
                f"protocol stage {self.stage!r} binds to core skill "
                f"{self.core_skill!r}, which the library does not declare"
            )
        if self.order < 1:
            raise PluginProtocolError("a protocol stage needs a positive order")
        if self.status not in tuple(status.value for status in RuleStatus):
            raise PluginRuleError(
                f"protocol stage {self.stage!r} has unknown status {self.status!r}"
            )
        if self.status != RuleStatus.AVAILABLE.value and not self.reason:
            raise PluginCapabilityError(
                f"protocol stage {self.stage!r} is {self.status} "
                "but declares no reason"
            )

    @property
    def available(self) -> bool:
        return self.status == RuleStatus.AVAILABLE.value

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "stage": self.stage,
            "domain_term": self.domain_term,
            "core_skill": self.core_skill,
            "status": self.status,
            "available": self.available,
            "order": self.order,
            "questions": list(self.questions),
        }
        if self.source_asset:
            record["source_asset"] = self.source_asset
        if self.reason:
            record["reason"] = self.reason
        return record


@dataclass(frozen=True, slots=True)
class DomainIdentity:
    """Who this domain is about — a domain, never a persona.

    A persona is either produced by an identity skill or it is absent. Every
    persona-producing asset in this repository is registered but unusable, so
    ``persona_available`` is ``False`` and ``persona_reason`` says why. Writing a
    persona here would be the fabrication this whole programme exists to prevent.
    """

    domain: str
    display_name: str
    reference_sources: tuple[str, ...] = ()
    persona_available: bool = False
    persona_asset: str = ""
    persona_reason: str = ""
    keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.domain:
            raise PluginRuleError("a domain identity needs a domain")
        if not self.display_name:
            raise PluginRuleError("a domain identity needs a display name")
        if not self.persona_available and not self.persona_reason:
            raise PluginCapabilityError(
                f"domain {self.domain!r} has no persona and declares no reason",
                detail="an absent persona must say why it is absent",
            )

    @property
    def reference_source_count(self) -> int:
        return len(self.reference_sources)

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "display_name": self.display_name,
            "reference_sources": list(self.reference_sources),
            "keywords": list(self.keywords),
            "persona": {
                "available": self.persona_available,
                "source_asset": self.persona_asset or ABSENCE_MARKER + "no_persona_asset",
                "reason": self.persona_reason,
            },
        }


@dataclass(frozen=True, slots=True)
class PluginProvenance:
    """Where this plugin came from, and what it was built against.

    A plugin whose origin is unknown cannot be reviewed, versioned, or reproduced,
    so every field here is required.
    """

    generated_by: str
    generated_at: str
    domain: str
    request_digest: str
    catalog_version: str
    library_version: str
    source_assets: tuple[str, ...] = ()
    core_skills: tuple[str, ...] = ()
    unavailable_assets: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "generated_by",
            "generated_at",
            "domain",
            "request_digest",
            "catalog_version",
            "library_version",
        ):
            if not str(getattr(self, name)).strip():
                raise PluginProvenanceError(f"plugin provenance has an empty {name}")
        if not self.source_assets:
            raise PluginProvenanceError(
                "plugin provenance names no source asset",
                detail="a domain rule with no origin cannot be reviewed",
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_by": self.generated_by,
            "generated_at": self.generated_at,
            "domain": self.domain,
            "catalog_version": self.catalog_version,
            "library_version": self.library_version,
            "request_digest": self.request_digest,
            "source_assets": list(self.source_assets),
            "unavailable_assets": list(self.unavailable_assets),
            "core_skills": list(self.core_skills),
            "notes": list(self.notes),
        }


@dataclass(frozen=True, slots=True)
class DomainRequest:
    """What a caller asks for: a domain, a platform, and its reference sources.

    Mirrors ``domain_request.yaml``::

        domain: finance
        platform: xiaohongshu
        reference_sources:
          - creator_a
          - creator_b
    """

    domain: str
    platform: str = ""
    style: str = ""
    reference_sources: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.domain, str) or not self.domain.strip():
            raise DomainRequestError("a domain request needs a domain")
        if self.domain != self.domain.strip():
            raise DomainRequestError(
                "a domain request's domain must not have surrounding whitespace"
            )
        for source in self.reference_sources:
            if not isinstance(source, str) or not source.strip():
                raise DomainRequestError(
                    "a reference source must be a non-empty string"
                )

    @property
    def reference_source_count(self) -> int:
        return len(self.reference_sources)

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "platform": self.platform,
            "style": self.style,
            "reference_sources": list(self.reference_sources),
        }


@dataclass(frozen=True, slots=True)
class DomainPlugin:
    """A versioned, declarative domain plugin.

    It carries the six rule slots the architecture names, the protocol stages in its
    domain's own vocabulary, the universal skills it binds to, and its provenance.

    It carries **no runtime and no prompt**: both are refused by
    :mod:`creator_plugin_builder.validator`, not merely documented.
    """

    plugin_name: str
    domain: str
    version: str
    display_name: str
    identity: DomainIdentity
    identity_rules: tuple[RuleBinding, ...]
    source_rules: tuple[RuleBinding, ...]
    topic_rules: tuple[RuleBinding, ...]
    protocol_stages: tuple[DistillationStage, ...]
    text_distillation_rules: tuple[RuleBinding, ...]
    visual_adaptation_rules: tuple[RuleBinding, ...]
    risk_constraints: tuple[RuleBinding, ...]
    required_core_skills: tuple[str, ...]
    provenance: PluginProvenance
    format_version: str = PLUGIN_FORMAT_VERSION
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    #: The rule slots, in architecture order. A class attribute so it is available
    #: before construction — the schema builder needs it.
    SLOTS: tuple[str, ...] = PLUGIN_SLOTS

    def __post_init__(self) -> None:
        if not self.plugin_name:
            raise PluginRuleError("a domain plugin needs a name")
        if not self.plugin_name.startswith("domain_"):
            raise PluginRuleError(
                f"plugin name {self.plugin_name!r} must start with 'domain_'",
                detail="the name identifies the artefact as a domain plugin",
            )
        if not self.version:
            raise PluginRuleError(
                f"plugin {self.plugin_name!r} has no version",
                detail="a plugin must be versionable",
            )
        if self.domain != self.identity.domain:
            raise PluginRuleError(
                f"plugin {self.plugin_name!r} names domain {self.domain!r} "
                f"but its identity names {self.identity.domain!r}"
            )
        if not self.required_core_skills:
            raise PluginRuleError(
                f"plugin {self.plugin_name!r} requires no core skill",
                detail="a plugin exists to feed the core, not to replace it",
            )
        for skill in self.required_core_skills:
            if skill not in PLUGIN_CORE_SKILLS:
                raise PluginLibraryError(
                    f"plugin {self.plugin_name!r} requires {skill!r}, "
                    "which the library does not declare"
                )
        declared = tuple(stage.stage for stage in self.protocol_stages)
        if declared != PROTOCOL_STAGES:
            raise PluginProtocolError(
                f"plugin {self.plugin_name!r} does not implement the distillation "
                "protocol",
                detail=(
                    "expected stages in order: " + ", ".join(PROTOCOL_STAGES)
                    + "; found: " + (", ".join(declared) or "(none)")
                ),
            )

    # -- rule access ------------------------------------------------------

    def rules(self, slot: str) -> tuple[RuleBinding, ...]:
        """Return one rule slot, rejecting an unknown name."""

        if slot not in self.SLOTS:
            raise PluginRuleError(
                f"plugin {self.plugin_name!r} has no rule slot {slot!r}",
                detail="expected one of: " + ", ".join(self.SLOTS),
            )
        return tuple(getattr(self, slot))

    def bindings(self) -> tuple[RuleBinding, ...]:
        """Every :class:`RuleBinding`, across every slot, in slot order."""

        found: list[RuleBinding] = []
        for slot in self.SLOTS:
            found.extend(getattr(self, slot))
        return tuple(found)

    def rule_names(self) -> tuple[str, ...]:
        """Every rule's ``slot.name``, in slot order."""

        return tuple(f"{slot}.{rule.slot}" for slot in self.SLOTS
                     for rule in getattr(self, slot))

    # -- state ------------------------------------------------------------

    @property
    def available_rules(self) -> tuple[str, ...]:
        return tuple(
            f"{slot}.{rule.slot}"
            for slot in self.SLOTS
            for rule in getattr(self, slot)
            if rule.available
        )

    @property
    def declared_rules(self) -> tuple[str, ...]:
        return tuple(
            f"{slot}.{rule.slot}"
            for slot in self.SLOTS
            for rule in getattr(self, slot)
            if not rule.available
        )

    @property
    def available_stages(self) -> tuple[str, ...]:
        return tuple(s.stage for s in self.protocol_stages if s.available)

    @property
    def source_assets(self) -> tuple[str, ...]:
        return self.provenance.source_assets

    @property
    def unavailable_assets(self) -> tuple[str, ...]:
        return self.provenance.unavailable_assets

    @property
    def persona_available(self) -> bool:
        return self.identity.persona_available

    @property
    def usable(self) -> bool:
        """Whether at least one rule is backed by a real asset.

        A plugin with nothing available is still a valid, reviewable declaration —
        it simply cannot yet produce anything, and this says so rather than letting a
        caller assume otherwise.
        """

        return bool(self.available_rules)

    @property
    def fully_available(self) -> bool:
        return not self.declared_rules

    def values(self, slot: str) -> tuple[str, ...]:
        """Every value across one slot's rules, in order and de-duplicated."""

        seen: dict[str, None] = {}
        for rule in self.rules(slot):
            for value in rule.values:
                seen.setdefault(str(value), None)
        return tuple(seen)

    # -- serialisation ----------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        return {
            "plugin_name": self.plugin_name,
            "domain": self.domain,
            "version": self.version,
            "format_version": self.format_version,
            "display_name": self.display_name,
            "domain_identity": self.identity.as_dict(),
            "identity_rules": [r.as_dict() for r in self.identity_rules],
            "source_rules": [r.as_dict() for r in self.source_rules],
            "topic_rules": [r.as_dict() for r in self.topic_rules],
            "protocol_stages": [s.as_dict() for s in self.protocol_stages],
            "text_distillation_rules": [
                r.as_dict() for r in self.text_distillation_rules
            ],
            "visual_adaptation_rules": [
                r.as_dict() for r in self.visual_adaptation_rules
            ],
            "risk_constraints": [r.as_dict() for r in self.risk_constraints],
            "required_core_skills": list(self.required_core_skills),
            "compatibility": {
                str(key): value for key, value in sorted(self.compatibility.items())
            },
            "provenance": self.provenance.as_dict(),
            "notes": list(self.notes),
        }

    def summary(self) -> dict[str, Any]:
        """A one-document description of the plugin's state, for review."""

        return {
            "plugin_name": self.plugin_name,
            "domain": self.domain,
            "version": self.version,
            "usable": self.usable,
            "fully_available": self.fully_available,
            "rule_count": len(self.rule_names()),
            "available_rules": list(self.available_rules),
            "declared_rules": list(self.declared_rules),
            "protocol_stages": [s.stage for s in self.protocol_stages],
            "available_stages": list(self.available_stages),
            "required_core_skills": list(self.required_core_skills),
            "source_assets": list(self.source_assets),
            "unavailable_assets": list(self.unavailable_assets),
            "persona_available": self.persona_available,
        }


__all__ = [
    "ABSENCE_MARKER",
    "DEFAULT_TIMESTAMP",
    "DOMAIN_MARKERS",
    "ERROR_CODES",
    "FORBIDDEN_MODULES",
    "META_SKILLS",
    "NOT_RECORDED",
    "PLUGIN_CORE_SKILLS",
    "PLUGIN_FORMAT_VERSION",
    "PLUGIN_SLOTS",
    "PROMPT_KEYS",
    "PROMPT_PHRASES",
    "PROTOCOL_STAGES",
    "RUNTIME_KEYS",
    "RUNTIME_SUFFIXES",
    "UNIVERSAL_SKILLS",
    "DistillationStage",
    "DomainIdentity",
    "DomainNotFoundError",
    "DomainPlugin",
    "DomainRequest",
    "DomainRequestError",
    "PluginBuilderError",
    "PluginCapabilityError",
    "PluginIsolationError",
    "PluginLayerError",
    "PluginLibraryError",
    "PluginProvenance",
    "PluginProvenanceError",
    "PluginProtocolError",
    "PluginRegistryError",
    "PluginRuleError",
    "PluginSchemaError",
    "RuleBinding",
    "RuleStatus",
]
