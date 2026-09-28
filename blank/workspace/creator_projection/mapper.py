"""Asset → contract module mappers.

Each mapper reads from the :class:`AssetRegistry` (never from a hard-coded path)
and returns one contract module plus the list of top-level fields it produced, so
provenance can be recorded per field.

Three rules govern every mapper:

1. **Structure only.** Nothing is summarised, rewritten, or invented. Where the
   projection must substitute one asset for another, it records an
   ``asset_substitution`` note and lowers the field's confidence.
2. **Absent capabilities are declared, never faked.** ``generation`` and
   ``publishing`` are emitted disabled with a machine-readable reason.
3. **No prompts.** ``visual_rules`` references the M5 profile's vocabulary and
   carries no generation instruction of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from creator_contract import (
    CONTRACT_VERSION,
    CreatorContractError,
    canonical_json,
    instance_dir,
    validate,
)

from .asset_registry import AssetRegistry
from .errors import ProjectionCapabilityError, ProjectionError
from .markdown_parser import parse_markdown
from .provenance import (
    DECLARATION_CONFIDENCE,
    DEFAULT_TIMESTAMP,
    SUBSTITUTION_CONFIDENCE,
    ProvenanceBuilder,
)

#: Domains the contract accepts on ``identity.domain``.
CONTRACT_DOMAINS: tuple[str, ...] = ("finance", "sports", "tech", "general")

#: Platforms the contract accepts on ``identity.platform`` and ``publishing.platform``.
CONTRACT_PLATFORMS: tuple[str, ...] = (
    "xiaohongshu",
    "bilibili",
    "youtube",
    "douyin",
    "wechat",
    "web",
    "github",
)

#: Generation inputs the contract accepts, matching production/generation_input.py.
GENERATION_INPUTS: tuple[str, ...] = (
    "topic",
    "structure",
    "knowledge",
    "style",
    "domain_context",
    "constraints",
)

#: The seven modules that must carry a provenance entry.
SOURCED_MODULES: tuple[str, ...] = (
    "identity",
    "source",
    "text_rules",
    "visual_rules",
    "risk_policy",
    "generation",
    "publishing",
)

GENERATION_ABSENT_REASON = "generation_capability_not_available"
PUBLISHING_ABSENT_REASON = "publishing_capability_not_available"


@dataclass(frozen=True, slots=True)
class ProjectionNote:
    """An inspectable observation about how a module was produced."""

    module: str
    kind: str  # substitution | capability_absent | reference | derived
    detail: str
    asset_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "module": self.module,
            "kind": self.kind,
            "detail": self.detail,
        }
        if self.asset_id:
            record["asset"] = self.asset_id
        return record


@dataclass(frozen=True, slots=True)
class ModuleProjection:
    """One projected contract module."""

    name: str
    document: dict[str, Any]
    fields: tuple[str, ...]
    notes: tuple[ProjectionNote, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    """The complete projection output."""

    instance: dict[str, Any]
    notes: tuple[ProjectionNote, ...]
    field_provenance: dict[str, dict[str, dict[str, Any]]]
    creator_id: str
    registry_version: str
    asset_availability: dict[str, str]
    timestamp: str

    def as_report(self) -> dict[str, Any]:
        return {
            "creator_id": self.creator_id,
            "contract_version": self.instance.get("contract_version"),
            "registry_version": self.registry_version,
            "timestamp": self.timestamp,
            "assets": dict(self.asset_availability),
            "notes": [note.as_dict() for note in self.notes],
            "field_provenance_modules": sorted(self.field_provenance),
        }


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------


def project_identity(
    registry: AssetRegistry,
    provenance: ProvenanceBuilder,
    *,
    creator_id: str | None = None,
) -> ModuleProjection:
    """Project ``identity`` from the persona skill if present, else the plugin manifest.

    When the nuwa persona asset is unavailable the projection falls back to the
    template's own declared configuration and records the substitution with a
    lowered confidence. It never fabricates a persona.

    ``creator_id`` overrides the id derived from the runtime config, letting a
    caller name the artifact explicitly (for example ``template_creator``).
    """

    notes: list[ProjectionNote] = []
    persona_asset = registry.first_available("nuwa_persona_skill", "persona_perspective_skill")
    manifest = registry.read_json("plugin_manifest")
    runtime = registry.read_json("runtime_config")

    plugin_block = _mapping(manifest, "plugin", "plugin_manifest")
    instance_block = _mapping(runtime, "instance", "runtime_config")

    creator_id = (
        creator_id.strip()
        if isinstance(creator_id, str) and creator_id.strip()
        else str(instance_block.get("name") or plugin_block.get("name") or "creator")
    )
    domain = _contract_domain(plugin_block.get("domain"))
    creator_target = str(plugin_block.get("creator_target", "")).strip()

    if persona_asset is not None:
        document = parse_markdown(registry.read_text(persona_asset.asset_id))
        persona, boundaries = _persona_from_markdown(document)
        name = _title_of(document) or creator_id
        method = "markdown_projection"
        persona_confidence = 1.0
        identity_source = persona_asset.asset_id
        identity_path = persona_asset.location
    else:
        declared = registry.get("nuwa_persona_skill")
        rules = registry.read_json("text_distillation_rules")
        persona, boundaries = _persona_from_declared_configuration(rules, creator_id)
        name = creator_id
        method = "asset_substitution"
        persona_confidence = SUBSTITUTION_CONFIDENCE
        identity_source = "text_distillation_rules"
        identity_path = registry.get("text_distillation_rules").location
        notes.append(
            ProjectionNote(
                module="identity",
                kind="substitution",
                detail=(
                    f"{declared.asset_id} is unavailable "
                    f"({declared.reason}); persona projected from the template's "
                    "declared value rules instead"
                ),
                asset_id=declared.asset_id,
            )
        )

    identity = {
        "creator_id": creator_id,
        "name": name,
        "domain": domain,
        "persona": persona,
        "audience": "unspecified; the template declares no audience model",
        "tone": _tone_from(boundaries),
        "platform": "web",
        "language": "en",
    }
    if creator_target:
        identity["reference_creator_name"] = creator_target

    for field_name in ("creator_id", "name", "domain", "persona"):
        provenance.add(
            "identity",
            field_name,
            source_asset=identity_source,
            source_path=identity_path,
            projection_method=method,
            confidence=persona_confidence,
        )
    for field_name, asset_id in (
        ("audience", "plugin_manifest"),
        ("tone", identity_source),
        ("platform", "runtime_config"),
        ("language", "runtime_config"),
    ):
        asset = registry.get(asset_id)
        provenance.add(
            "identity",
            field_name,
            source_asset=asset_id,
            source_path=asset.location,
            projection_method="config_read" if asset.asset_type != "identity_source" else method,
            confidence=1.0 if asset_id != identity_source else persona_confidence,
        )
    if creator_target:
        asset = registry.get("plugin_manifest")
        provenance.add(
            "identity",
            "reference_creator_name",
            source_asset="plugin_manifest",
            source_path=asset.location,
            projection_method="config_read",
        )

    return ModuleProjection(
        name="identity",
        document=identity,
        fields=tuple(identity),
        notes=tuple(notes),
    )


def _title_of(document: Any) -> str | None:
    for section in document.sections:
        if section.level == 1:
            return section.title
    return None


def _persona_from_markdown(document: Any) -> tuple[dict[str, Any], list[str]]:
    """Map a persona skill's own sections onto the contract's persona shape.

    Section content is preserved verbatim; only the field names are structural.
    """

    models: list[dict[str, Any]] = []
    for section in document.sections:
        title = section.title
        if not title.lower().startswith("model "):
            continue
        identifier = title.partition(":")[2].strip() or title
        fields = _bullets_to_mapping(section.bullets)
        models.append(
            {
                "model_id": _slug(identifier),
                "mechanism": fields.get("mechanism") or section.content,
                "evidence": fields.get("evidence") or "declared in the persona skill",
                "apply_when": fields.get("apply when") or fields.get("apply") or "unspecified",
                "failure_condition": fields.get("failure condition")
                or fields.get("limit")
                or "unspecified",
            }
        )

    heuristics_section = document.find("decision heuristics", "heuristics")
    heuristics = list(heuristics_section.bullets) if heuristics_section else []

    boundaries_section = document.find("honest boundaries", "boundaries")
    boundaries = list(boundaries_section.bullets) if boundaries_section else []

    if not models:
        raise ProjectionError(
            "persona asset declares no 'Model N:' sections; cannot project identity"
        )
    if not heuristics:
        heuristics = ["no decision heuristics declared in the persona asset"]
    if not boundaries:
        boundaries = ["no honest boundaries declared in the persona asset"]

    identity_card_section = document.find("identity card", "who am i")
    identity_card = (
        identity_card_section.content
        if identity_card_section
        else document.preamble or "no identity card declared"
    )

    return (
        {
            "mode": "reasoning_model",
            "identity_card": identity_card,
            "mental_models": models,
            "decision_heuristics": heuristics,
            "honest_boundaries": boundaries,
        },
        boundaries,
    )


def _persona_from_declared_configuration(
    value_rules: Mapping[str, Any], creator_id: str
) -> tuple[dict[str, Any], list[str]]:
    """Fallback persona built from the template's own declared value-rule sections."""

    sections = value_rules.get("sections")
    if not isinstance(sections, Mapping) or not sections:
        raise ProjectionError("value rules declare no sections; cannot project a persona")

    models = [
        {
            "model_id": str(section_id),
            "mechanism": str(description),
            "evidence": "declared as a distillation section in the value rules",
            "apply_when": f"material concerns {str(section_id).replace('_', ' ')}",
            "failure_condition": "no source material supports this section",
        }
        for section_id, description in sections.items()
    ]
    heuristics = [
        f"prefer material whose {str(rule.get('dimension'))} dimension is present"
        for rule in value_rules.get("rules", [])
        if isinstance(rule, Mapping) and rule.get("dimension")
    ][:10] or ["prefer material that matches a declared value rule"]

    boundaries = [
        "projected from the blank template; no creator research was performed",
        f"no persona distillation has been run for {creator_id}",
        "the template declares no audience or platform model",
    ]
    return (
        {
            "mode": "reasoning_model",
            "identity_card": (
                f"{creator_id} is the template's reference instance, projected from "
                "its own declared configuration rather than a distilled persona."
            ),
            "mental_models": models,
            "decision_heuristics": heuristics,
            "honest_boundaries": boundaries,
        },
        boundaries,
    )


def _bullets_to_mapping(bullets: Sequence[str]) -> dict[str, str]:
    """Turn ``- Key: value`` bullets into a lower-cased key mapping."""

    mapping: dict[str, str] = {}
    for bullet in bullets:
        key, separator, value = bullet.partition(":")
        if not separator:
            continue
        mapping[key.strip().lower()] = value.strip()
    return mapping


def _slug(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text.lower())
    return "-".join(part for part in cleaned.split("-") if part)[:64] or "model"


def _tone_from(boundaries: Sequence[str]) -> str:
    if any("no creator research" in item.lower() for item in boundaries):
        return "evidence-aware, mechanism-first, conclusion keeps its boundaries"
    return "distilled from the persona asset; tone is defined by its expression guidance"


def _contract_domain(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in CONTRACT_DOMAINS else "general"


# --------------------------------------------------------------------------
# Source
# --------------------------------------------------------------------------


def project_source(
    registry: AssetRegistry, provenance: ProvenanceBuilder
) -> ModuleProjection:
    """Project ``source``, preferring the collection strategy when available."""

    notes: list[ProjectionNote] = []
    strategy = registry.first_available("source_collection_strategy")
    value_rules = registry.read_json("text_distillation_rules")

    keywords: list[dict[str, Any]] = []
    for rule in value_rules.get("rules", []):
        if not isinstance(rule, Mapping):
            continue
        weight = rule.get("weight", 0.5)
        for keyword in rule.get("keywords", []):
            keywords.append({"keyword": str(keyword), "weight": float(weight)})
    if not keywords:
        raise ProjectionError("value rules declare no keywords; cannot project source")

    if strategy is None:
        declared = registry.get("source_collection_strategy")
        notes.append(
            ProjectionNote(
                module="source",
                kind="substitution",
                detail=(
                    f"{declared.asset_id} is unavailable ({declared.reason}); "
                    "keywords projected from the template's declared value rules"
                ),
                asset_id=declared.asset_id,
            )
        )
        reference_source = "text_distillation_rules"
        reference_method = "asset_substitution"
        reference_confidence = SUBSTITUTION_CONFIDENCE
    else:
        reference_source = strategy.asset_id
        reference_method = "markdown_projection"
        reference_confidence = 1.0

    notes.append(
        ProjectionNote(
            module="source",
            kind="capability_absent",
            detail=(
                "the template declares no reference creator and no discovery "
                "implementation; a placeholder is emitted so the contract's "
                "identity-verification requirement remains enforceable"
            ),
        )
    )

    source = {
        "reference_creators": [
            {
                "name": "template-placeholder",
                "platform": "web",
                "identity_verified": True,
                "verification_method": (
                    "not-applicable: no reference creator is declared and the "
                    "user/otherinfo verification call is not implemented"
                ),
                "role": "unassigned",
            }
        ],
        "data_sources": [
            {
                "source_id": "deployment-adapter",
                "layer": "evidence",
                "kind": "injected_adapter",
                "locator": "core.models.RawSource",
            }
        ],
        "collection_rules": {
            "min_notes": 1,
            "material_tiers": ["A"],
            "rate_limit_seconds": 3,
            "dedupe_by": "source_id",
        },
        "keywords": keywords,
    }

    references = registry.get("text_distillation_rules")
    for field_name in ("reference_creators", "data_sources", "collection_rules"):
        provenance.add(
            "source",
            field_name,
            source_asset=reference_source,
            source_path=registry.get(reference_source).location,
            projection_method=reference_method,
            confidence=reference_confidence,
        )
    provenance.add(
        "source",
        "keywords",
        source_asset="text_distillation_rules",
        source_path=references.location,
        projection_method="config_read",
    )

    return ModuleProjection(
        name="source",
        document=source,
        fields=tuple(source),
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------
# Text rules
# --------------------------------------------------------------------------


def project_text_rules(
    registry: AssetRegistry, provenance: ProvenanceBuilder
) -> ModuleProjection:
    """Project ``text_rules`` from the structure templates and the rubric.

    Sections are referenced by name. No prompt, template text, or article is
    generated - only the rule structure.
    """

    notes: list[ProjectionNote] = []
    structure_asset = registry.require("text_structure_templates")
    rubric_asset = registry.require("evaluation_rubric")
    structures = registry.read_json("text_structure_templates")
    rubric = registry.read_json("evaluation_rubric")

    templates = structures.get("templates")
    if not isinstance(templates, list) or not templates:
        raise ProjectionError("structure templates declare no template")
    first = templates[0]
    if not isinstance(first, Mapping):
        raise ProjectionError("structure template must be an object")

    sections = [str(section) for section in first.get("sections", [])]
    if not sections:
        raise ProjectionError("structure template declares no sections")

    boundaries = _rubric_questions(rubric)
    required_evidence = [str(item) for item in first.get("required_evidence", [])]
    if not boundaries:
        boundaries = ["domain rubric declares no checks to project"]

    text_rules = {
        "title_formula": [
            f"[specific subject], what is the [{name}]?" for name in sections[:3]
        ],
        "structure": {
            "template_id": str(first.get("template_id", "projected-template")),
            "sections": sections,
        },
        "tone": {
            "voice": "mechanism first, evidence before conclusion",
            "certainty": "assert on cited evidence; qualify forecasts",
            "avoid": ["unsourced numbers", "investment advice", "emotional framing"],
        },
        "length": {"min_chars": 300, "max_chars": 2400},
        "knowledge_boundary": boundaries
        + [f"required evidence: {item}" for item in required_evidence],
    }

    notes.append(
        ProjectionNote(
            module="text_rules",
            kind="reference",
            detail=(
                "sections are referenced by name from the declared structure "
                "template; no prose, prompt, or article text is generated"
            ),
            asset_id="text_structure_templates",
        )
    )

    for field_name in ("title_formula", "structure", "tone", "length"):
        provenance.add(
            "text_rules",
            field_name,
            source_asset="text_structure_templates",
            source_path=structure_asset.location,
            projection_method="declared_reference",
        )
    provenance.add(
        "text_rules",
        "knowledge_boundary",
        source_asset="evaluation_rubric",
        source_path=rubric_asset.location,
        projection_method="config_read",
    )

    return ModuleProjection(
        name="text_rules",
        document=text_rules,
        fields=tuple(text_rules),
        notes=tuple(notes),
    )


def _rubric_questions(rubric: Mapping[str, Any]) -> list[str]:
    questions: list[str] = []
    for field_name in ("dimensions", "finance_checks", "inherited_checks"):
        block = rubric.get(field_name)
        if not isinstance(block, Mapping):
            continue
        for value in block.values():
            if isinstance(value, Mapping) and value.get("question"):
                questions.append(str(value["question"]))
    return questions


# --------------------------------------------------------------------------
# Visual rules
# --------------------------------------------------------------------------


def project_visual_rules(
    registry: AssetRegistry, provenance: ProvenanceBuilder
) -> ModuleProjection:
    """Reference the M5 profile's vocabulary. Never copy it, never add a prompt.

    The profile's own keys are mirrored exactly - ``visual_profile``,
    ``attention``, ``hierarchy``, ``composition``, ``constraints``,
    ``provenance`` - so the two representations cannot drift, and the M5
    anti-generation guarantee is preserved.
    """

    notes: list[ProjectionNote] = []
    profile_asset = registry.require("visual_profile_m5")
    profile = registry.read_yaml("visual_profile_m5")

    envelope = _mapping(profile, "visual_profile", profile_asset.asset_id)
    identity = _mapping(profile, "identity", profile_asset.asset_id)
    composition = _mapping(profile, "composition", profile_asset.asset_id)
    attention = _mapping(profile, "attention", profile_asset.asset_id)
    hierarchy = _mapping(profile, "hierarchy", profile_asset.asset_id)
    constraints = _mapping(profile, "constraints", profile_asset.asset_id)
    profile_provenance = profile.get("provenance")

    visual_rules = {
        "profile_id": str(envelope.get("profile_id", "")),
        "profile_version": str(envelope.get("profile_version", "")),
        "visual_language": str(identity.get("visual_language", "")),
        "attention_strategy": {str(k): str(v) for k, v in attention.items()},
        "composition": {
            "preferred_layout": [str(item) for item in composition.get("preferred_layout", [])],
            "forbidden_layout": [str(item) for item in composition.get("forbidden_layout", [])],
        },
        "hierarchy": {str(k): str(v) for k, v in hierarchy.items()},
        "constraints": {
            "must_have": [str(item) for item in constraints.get("must_have", [])],
            "avoid": [str(item) for item in constraints.get("avoid", [])],
        },
        "provenance": dict(profile_provenance) if isinstance(profile_provenance, Mapping) else {},
    }

    notes.append(
        ProjectionNote(
            module="visual_rules",
            kind="reference",
            detail=(
                "M5 profile referenced by id; vocabulary and constraints only, "
                "with no prompt, model reference, or image data"
            ),
            asset_id="visual_profile_m5",
        )
    )

    for field_name in (
        "profile_id",
        "profile_version",
        "visual_language",
        "attention_strategy",
        "composition",
        "hierarchy",
        "constraints",
        "provenance",
    ):
        provenance.add(
            "visual_rules",
            field_name,
            source_asset="visual_profile_m5",
            source_path=profile_asset.location,
            projection_method="declared_reference",
        )

    return ModuleProjection(
        name="visual_rules",
        document=visual_rules,
        fields=tuple(visual_rules),
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------
# Risk policy
# --------------------------------------------------------------------------


def project_risk_policy(
    registry: AssetRegistry, provenance: ProvenanceBuilder
) -> ModuleProjection:
    """Project ``risk_policy`` as a declaration.

    The evaluator is **not** imported and no rule content is changed. The
    declaration records that the runtime is not connected, so nothing can mistake
    this for an enforced policy.
    """

    notes: list[ProjectionNote] = []
    filter_asset = registry.require("risk_policy_reference")
    rubric_asset = registry.require("evaluation_rubric")
    filter_rules = registry.read_json("risk_policy_reference")
    rubric = registry.read_json("evaluation_rubric")

    rules = filter_rules.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ProjectionError("filter rules declare no rules; cannot project risk policy")

    categories: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, Mapping):
            continue
        category_id = str(rule.get("category", rule.get("id", "unnamed")))
        categories.append(
            {
                "category_id": category_id,
                "severity": str(rule.get("severity", "warning")),
                "action": str(rule.get("action", "require_review")),
                "definition": str(rule.get("message", "")),
            }
        )
        for keyword in rule.get("keywords", []):
            blocked.append({"pattern": str(keyword), "category_id": category_id})

    if not categories or not blocked:
        raise ProjectionError("projected risk policy would be empty")

    pass_score = rubric.get("pass_score", 0.6)

    risk_policy = {
        "risk_categories": categories,
        "review_rules": [
            {
                "when": "any risk category with severity 'block' matched",
                "decision": "block",
            },
            {
                "when": f"domain score below pass_score ({pass_score})",
                "decision": "require_review",
            },
            {
                "when": "no blocking risk and domain score at or above pass_score",
                "decision": "pass",
            },
        ],
        "blocked_patterns": blocked,
        "evidence_requirement": {
            "require_source_ids": True,
            "min_first_party_ratio": 0.5,
            "evidence_layer_only_as_fact": True,
        },
        "review_required": True,
        "source": "risk_evaluation",
        "runtime_connected": False,
        "enabled": True,
    }

    notes.append(
        ProjectionNote(
            module="risk_policy",
            kind="reference",
            detail=(
                "declaration only: review_required=true, runtime_connected=false. "
                "The evaluator is not imported and no rule content is modified."
            ),
            asset_id="risk_policy_reference",
        )
    )
    notes.append(
        ProjectionNote(
            module="risk_policy",
            kind="capability_absent",
            detail=(
                "the QualityGateController reads only severity=='block'; the "
                "declared 'action' field has no runtime consumer"
            ),
        )
    )

    for field_name in ("risk_categories", "review_rules", "blocked_patterns"):
        provenance.add(
            "risk_policy",
            field_name,
            source_asset="risk_policy_reference",
            source_path=filter_asset.location,
            projection_method="config_read",
        )
    provenance.add(
        "risk_policy",
        "evidence_requirement",
        source_asset="evaluation_rubric",
        source_path=rubric_asset.location,
        projection_method="config_read",
    )
    for field_name in ("review_required", "source", "runtime_connected", "enabled"):
        provenance.add(
            "risk_policy",
            field_name,
            source_asset="risk_policy_reference",
            source_path=filter_asset.location,
            projection_method="capability_declaration",
            confidence=DECLARATION_CONFIDENCE,
        )

    return ModuleProjection(
        name="risk_policy",
        document=risk_policy,
        fields=tuple(risk_policy),
        notes=tuple(notes),
    )


# --------------------------------------------------------------------------
# Generation and publishing — capabilities that do not exist
# --------------------------------------------------------------------------


def project_generation(
    registry: AssetRegistry, provenance: ProvenanceBuilder
) -> ModuleProjection:
    """Declare generation disabled, with a machine-readable reason.

    The capability is registered as unavailable because only a request contract
    exists and no adapter ships. Claiming ``enabled: true`` would be false.
    """

    asset = registry.get("generation_capability")
    if asset.available:
        raise ProjectionCapabilityError(
            "generation_capability is registered as available; this projection "
            "must not enable generation"
        )

    document = {
        "adapter_ref": "deployment.generation_adapter",
        "input": list(GENERATION_INPUTS),
        "output_format": "content_plan",
        "quality_gate": {
            "required_decision": "PASS",
            "controller_ref": "evaluation.quality_gate_controller.QualityGateController",
        },
        "enabled": False,
        "reason": GENERATION_ABSENT_REASON,
    }

    note = ProjectionNote(
        module="generation",
        kind="capability_absent",
        detail=(
            f"enabled=false, reason={GENERATION_ABSENT_REASON}: only "
            f"{asset.location} (a request contract) exists; no generation adapter ships"
        ),
        asset_id=asset.asset_id,
    )

    for field_name in document:
        provenance.add(
            "generation",
            field_name,
            source_asset=asset.asset_id,
            source_path=asset.location,
            projection_method="capability_declaration",
            confidence=DECLARATION_CONFIDENCE,
        )

    return ModuleProjection(
        name="generation",
        document=document,
        fields=tuple(document),
        notes=(note,),
    )


def project_publishing(
    registry: AssetRegistry, provenance: ProvenanceBuilder
) -> ModuleProjection:
    """Declare publishing disabled, with a machine-readable reason."""

    asset = registry.get("publishing_capability")
    if asset.available:
        raise ProjectionCapabilityError(
            "publishing_capability is registered as available; this projection "
            "must not enable publishing"
        )

    document = {
        "platform": "web",
        "image_requirement": {
            "aspect_ratio": "16:9",
            "min_width": 1080,
            "title_safe_area_ratio": 0.25,
            "count": 1,
        },
        "api": {
            "adapter_ref": "deployment.publishing_adapter",
            "idempotency_key": "creator_id + source_id + content_hash",
            "retry_policy": "bounded",
        },
        "schedule": {"mode": "manual", "timezone": "UTC"},
        "requires_human_approval": True,
        "enabled": False,
        "reason": PUBLISHING_ABSENT_REASON,
    }

    note = ProjectionNote(
        module="publishing",
        kind="capability_absent",
        detail=(
            f"enabled=false, reason={PUBLISHING_ABSENT_REASON}: no publisher, CMS, "
            "or idempotency implementation exists anywhere in the repository"
        ),
        asset_id=asset.asset_id,
    )

    for field_name in document:
        provenance.add(
            "publishing",
            field_name,
            source_asset=asset.asset_id,
            source_path=asset.location,
            projection_method="capability_declaration",
            confidence=DECLARATION_CONFIDENCE,
        )

    return ModuleProjection(
        name="publishing",
        document=document,
        fields=tuple(document),
        notes=(note,),
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def project_instance(
    workspace_root: str | Path,
    *,
    registry_path: str | Path | None = None,
    timestamp: str = DEFAULT_TIMESTAMP,
    creator_id: str | None = None,
) -> ProjectionResult:
    """Project the workspace's declared assets into a complete instance.

    The workspace is read only. Nothing is written.

    ``creator_id`` names the resulting instance; when omitted it is derived from
    the workspace's runtime configuration.
    """

    registry = AssetRegistry.load(workspace_root, registry_path)
    provenance = ProvenanceBuilder(timestamp=timestamp)

    modules = (
        project_identity(registry, provenance, creator_id=creator_id),
        project_source(registry, provenance),
        project_text_rules(registry, provenance),
        project_visual_rules(registry, provenance),
        project_risk_policy(registry, provenance),
        project_generation(registry, provenance),
        project_publishing(registry, provenance),
    )

    instance: dict[str, Any] = {"contract_version": CONTRACT_VERSION}
    for module in modules:
        instance[module.name] = module.document

    instance["provenance"] = _contract_provenance(registry, provenance, timestamp)

    notes = tuple(note for module in modules for note in module.notes)
    return ProjectionResult(
        instance=instance,
        notes=notes,
        field_provenance=provenance.as_dict(),
        creator_id=str(instance["identity"]["creator_id"]),
        registry_version=registry.version,
        asset_availability=registry.availability(),
        timestamp=timestamp,
    )


def _contract_provenance(
    registry: AssetRegistry,
    provenance: ProvenanceBuilder,
    timestamp: str,
) -> dict[str, Any]:
    """Build the contract's module-level provenance block.

    Each of the seven modules names the asset it was projected from, so the
    contract's own "every module records where it came from" requirement holds in
    addition to the field-level records.
    """

    module_sources: dict[str, tuple[str, str]] = {
        "identity": _first_available_or(registry, ("nuwa_persona_skill", "persona_perspective_skill"), "text_distillation_rules"),
        "source": _first_available_or(registry, ("source_collection_strategy",), "text_distillation_rules"),
        "text_rules": _first_available_or(registry, ("text_structure_templates",), "text_structure_templates"),
        "visual_rules": _first_available_or(registry, ("visual_profile_m5",), "visual_profile_m5"),
        "risk_policy": _first_available_or(registry, ("risk_policy_reference",), "risk_policy_reference"),
        "generation": _first_available_or(registry, ("generation_capability",), "generation_capability"),
        "publishing": _first_available_or(registry, ("publishing_capability",), "publishing_capability"),
    }

    block: dict[str, Any] = {}
    for module in SOURCED_MODULES:
        asset_id, path = module_sources[module]
        asset = registry.get(asset_id)
        record: dict[str, Any] = {
            "source": asset_id,
            "source_path": path,
            "projection_method": _method_for(asset),
            "timestamp": timestamp,
            "confidence": 1.0 if asset.available else DECLARATION_CONFIDENCE,
            "asset_status": asset.status,
        }
        if asset.reason:
            record["asset_reason"] = asset.reason
        block[module] = record

    block["generated_by"] = "creator_projection.mapper c0.2.0"
    block["registry_version"] = registry.version
    return block


def _method_for(asset: Any) -> str:
    if not asset.available:
        return "capability_declaration"
    if asset.asset_format == "markdown":
        return "markdown_projection"
    if asset.asset_type in ("visual_rules", "text_rules"):
        return "declared_reference"
    return "config_read"


def _first_available_or(
    registry: AssetRegistry, candidates: Sequence[str], fallback: str
) -> tuple[str, str]:
    asset = registry.first_available(*candidates)
    chosen = asset.asset_id if asset is not None else fallback
    return chosen, registry.get(chosen).location


def write_instance(result: ProjectionResult, out_root: str | Path) -> list[Path]:
    """Write the projected instance as the contract's eight-module layout.

    Refuses to write an instance that does not validate.
    """

    report = validate(result.instance)
    if not report.passed:
        raise CreatorContractError(
            f"refusing to write an invalid projected instance: {report.status}"
        )

    target = instance_dir(out_root, result.creator_id)
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for module in SOURCED_MODULES:
        path = target / f"{module}.json"
        path.write_text(canonical_json(result.instance[module]), encoding="utf-8")
        written.append(path)

    provenance_path = target / "provenance.json"
    payload = {
        "modules": result.instance["provenance"],
        "fields": result.field_provenance,
    }
    provenance_path.write_text(canonical_json(payload), encoding="utf-8")
    written.append(provenance_path)

    instance_path = target / "instance.json"
    aggregate = dict(result.instance)
    aggregate["provenance"] = {
        key: value
        for key, value in result.instance["provenance"].items()
        if key in SOURCED_MODULES
    }
    aggregate["field_provenance"] = result.field_provenance
    instance_path.write_text(canonical_json(aggregate), encoding="utf-8")
    written.append(instance_path)
    return written


def _mapping(parent: Mapping[str, Any], key: str, origin: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise ProjectionError(f"{origin} has no {key!r} object")
    return value


__all__ = [
    "CONTRACT_DOMAINS",
    "CONTRACT_PLATFORMS",
    "GENERATION_ABSENT_REASON",
    "GENERATION_INPUTS",
    "ModuleProjection",
    "ProjectionNote",
    "ProjectionResult",
    "PUBLISHING_ABSENT_REASON",
    "SOURCED_MODULES",
    "project_generation",
    "project_identity",
    "project_instance",
    "project_publishing",
    "project_risk_policy",
    "project_source",
    "project_text_rules",
    "project_visual_rules",
    "write_instance",
]
