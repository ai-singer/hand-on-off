"""The default Creator Skill catalog.

Thirteen skills across the seven taxonomy types, each bound to a **registered
asset** from ``creator_projection/assets.yaml``. The catalog is a declarative
list of documents; :mod:`creator_skill.registry` turns it into
:class:`~creator_skill.model.CreatorSkill` objects and validates every one.

Two entries are deliberately ``declared`` rather than available. Generation and
publishing capabilities do not exist in this repository - C0.2's asset registry
records them as unavailable - so their skills are declared as routing and target
capabilities that are not yet implemented. Marking them available would be the
exact false claim the C0.2 contract rejects.

Skills that depend on M5 carry an ``enhance`` edge rather than a ``require`` edge:
a creator without a visual profile is still a valid creator, it simply has no
visual style skill.
"""

from __future__ import annotations

from typing import Any

#: Catalog version, independent of individual skill versions.
CATALOG_VERSION = "1.0.0"

#: Deterministic generation timestamp (matching the projection convention).
CATALOG_TIMESTAMP = "1970-01-01T00:00:00Z"


def _provenance(source_kind: str, source_ref: str, version: str, confidence: float, note: str = "") -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_kind": source_kind,
        "source_ref": source_ref,
        "skill_version": version,
        "generated_at": CATALOG_TIMESTAMP,
        "confidence": confidence,
    }
    if note:
        record["note"] = note
    return record


#: The catalog. Every ``source_ref`` names a registered asset.
DEFAULT_SKILL_CATALOG: tuple[dict[str, Any], ...] = (
    # ---- identity -------------------------------------------------------
    {
        "skill_id": "finance-persona",
        "skill_type": "identity",
        "version": "1.0.0",
        "description": (
            "Finance explainer persona: mechanism-first reasoning, misconception "
            "analysis, boundary-keeping, and explicit honest boundaries."
        ),
        "capabilities": [
            "persona.identity_card",
            "persona.mental_models",
            "persona.decision_heuristics",
            "persona.expression_guidance",
            "persona.honest_boundaries",
        ],
        "inputs": ["creator_request", "persona_source"],
        "outputs": ["identity"],
        "dependencies": [],
        "compatibility": {
            "domains": ["finance"],
            "platforms": [],
            "styles": ["mechanism_explanation", "education"],
            "requires_contract_version": "1.0.0",
        },
        "provenance": _provenance(
            "projection",
            "text_distillation_rules",
            "1.0.0",
            0.4,
            "persona section projected from the template's declared value rules; "
            "no distilled persona asset is present in this repository",
        ),
        "status": "available",
        "reusable": True,
        "tags": ["persona", "finance"],
    },
    # ---- domain ---------------------------------------------------------
    {
        "skill_id": "business-finance-analysis",
        "skill_type": "domain",
        "version": "1.0.0",
        "description": (
            "Business and finance subject taxonomy: business mechanism, financial "
            "structure, data expression, case selection, misconception analysis."
        ),
        "capabilities": [
            "domain.business_mechanism",
            "domain.financial_structure",
            "domain.data_expression_pattern",
            "domain.case_selection_logic",
            "domain.misconception_analysis",
        ],
        "inputs": ["source_material"],
        "outputs": ["domain_extension", "value_signals"],
        "dependencies": [],
        "compatibility": {
            "domains": ["finance"],
            "platforms": [],
            "styles": [],
            "requires_contract_version": "1.0.0",
        },
        "provenance": _provenance("template", "text_distillation_rules", "1.0.0", 1.0),
        "status": "available",
        "reusable": True,
        "tags": ["domain", "finance", "business"],
    },
    {
        "skill_id": "technology-analysis",
        "skill_type": "domain",
        "version": "1.0.0",
        "description": (
            "Technology subject taxonomy: capability mechanism, technical trade-offs, "
            "adoption signals, product boundaries, and hype-versus-substance analysis. "
            "Bound to the same declared value rules as the finance taxonomy, because "
            "the repository ships one rule set; the domain-specific dimensions are "
            "therefore declared, not yet authored."
        ),
        "capabilities": [
            "domain.capability_mechanism",
            "domain.technical_tradeoffs",
            "domain.adoption_signals",
            "domain.product_boundaries",
            "domain.hype_versus_substance",
        ],
        "inputs": ["source_material"],
        "outputs": ["domain_extension", "value_signals"],
        "dependencies": [],
        "compatibility": {
            "domains": ["tech"],
            "platforms": [],
            "styles": [],
            "requires_contract_version": "1.0.0",
        },
        "provenance": _provenance(
            "template",
            "text_distillation_rules",
            "1.0.0",
            0.5,
            "taxonomy dimensions are declared for the tech domain but the repository "
            "ships only the finance rule set, so the dimensions are not sourced from "
            "authored tech rules",
        ),
        "status": "declared",
        "reason": "tech_domain_rules_not_authored: only the finance value rules exist",
        "reusable": True,
        "tags": ["domain", "tech", "ai"],
    },
    # ---- source ---------------------------------------------------------
    {
        "skill_id": "news-source",
        "skill_type": "source",
        "version": "1.0.0",
        "description": (
            "Platform-agnostic news and disclosure sourcing: government statistics, "
            "official disclosures and authoritative media as the evidence layer, "
            "with social platforms restricted to the discovery layer."
        ),
        "capabilities": [
            "source.evidence_layer_only_as_fact",
            "source.official_disclosure_sourcing",
            "source.statistics_sourcing",
            "source.deduplication",
        ],
        "inputs": ["domain_keywords", "creator_request"],
        "outputs": ["raw_source_set"],
        "dependencies": [],
        "compatibility": {
            "domains": [],
            "platforms": [],
            "styles": [],
            "requires_contract_version": "1.0.0",
        },
        "provenance": _provenance(
            "template",
            "evaluation_rubric",
            "1.0.0",
            0.5,
            "the evidence-layer rule is real and enforced; the fetching implementation "
            "is not present in this repository",
        ),
        "status": "declared",
        "reason": "source_collection_strategy asset unavailable; no acquisition "
        "implementation exists in this repository",
        "reusable": True,
        "tags": ["source", "news", "evidence"],
    },
    {
        "skill_id": "xiaohongshu-source",
        "skill_type": "source",
        "version": "1.0.0",
        "description": (
            "Dual-layer Xiaohongshu sourcing: discovery-layer material yields topics, "
            "evidence-layer material yields facts. The two may not substitute."
        ),
        "capabilities": [
            "source.dual_layer_architecture",
            "source.keyword_collection",
            "source.rate_limiting",
            "source.identity_verification",
            "source.deduplication",
        ],
        "inputs": ["domain_keywords", "creator_request"],
        "outputs": ["raw_source_set"],
        "dependencies": [],
        "compatibility": {
            "domains": [],
            "platforms": ["xiaohongshu"],
            "styles": [],
            "requires_contract_version": "1.0.0",
        },
        "provenance": _provenance(
            "projection",
            "text_distillation_rules",
            "1.0.0",
            0.4,
            "collection strategy asset is unavailable; declared from the template's "
            "own keyword rules",
        ),
        "status": "declared",
        "reason": "source_collection_strategy asset unavailable; no acquisition "
        "implementation exists in this repository",
        "reusable": True,
        "tags": ["source", "xiaohongshu"],
    },
    # ---- distillation ---------------------------------------------------
    {
        "skill_id": "text-distillation",
        "skill_type": "distillation",
        "version": "1.0.0",
        "description": (
            "Text distillation: turn collected material into content templates, "
            "knowledge units, topic candidates and style patterns."
        ),
        "capabilities": [
            "distillation.content_template",
            "distillation.knowledge_unit",
            "distillation.topic_candidate",
            "distillation.style_pattern",
        ],
        "inputs": ["raw_source_set"],
        "outputs": ["unified_distillation_artifact"],
        "dependencies": [
            {"target": "business-finance-analysis", "kind": "enhance", "reason": "domain rules sharpen the extraction"}
        ],
        "compatibility": {
            "domains": [],
            "platforms": [],
            "styles": [],
            "requires_contract_version": "1.0.0",
        },
        "provenance": _provenance(
            "template", "text_structure_templates", "1.0.0", 1.0
        ),
        "status": "available",
        "reusable": True,
        "tags": ["distillation", "text"],
    },
    {
        "skill_id": "visual-style-distillation",
        "skill_type": "distillation",
        "version": "1.0.0",
        "description": (
            "Visual distillation: reference an M5 VisualCreatorProfile's vocabulary "
            "and constraints. Carries vocabulary only, never a prompt."
        ),
        "capabilities": [
            "distillation.visual_language",
            "distillation.layout_constraints",
            "distillation.attention_strategy",
            "distillation.hierarchy_pattern",
        ],
        "inputs": ["visual_samples"],
        "outputs": ["visual_creator_profile"],
        "dependencies": [
            {"target": "text-distillation", "kind": "require", "reason": "visual patterns are paired with text signals"}
        ],
        "compatibility": {
            "domains": [],
            "platforms": [],
            "styles": [],
            "requires_contract_version": "1.0.0",
        },
        "provenance": _provenance(
            "distillation_artifact", "visual_profile_m5", "1.0.0", 1.0
        ),
        "status": "available",
        "reusable": True,
        "tags": ["distillation", "visual", "m5"],
    },
    # ---- generation -----------------------------------------------------
    {
        "skill_id": "xiaohongshu-article-generation",
        "skill_type": "generation",
        "version": "1.0.0",
        "description": (
            "Route a gate-approved artifact to an injected generation adapter, "
            "declaring the input projection and output format. The adapter itself "
            "is supplied by a deployment."
        ),
        "capabilities": [
            "generation.generation_request",
            "generation.input_projection",
            "generation.quality_gate_handoff",
        ],
        "inputs": ["unified_distillation_artifact", "quality_gate_decision"],
        "outputs": ["generation_request"],
        "dependencies": [
            {"target": "text-distillation", "kind": "require", "reason": "generation consumes the distilled artifact"}
        ],
        "compatibility": {
            "domains": [],
            "platforms": ["xiaohongshu"],
            "styles": [],
            "requires_contract_version": "1.0.0",
        },
        "provenance": _provenance(
            "template",
            "generation_capability",
            "1.0.0",
            0.0,
            "only a request contract exists; no generation adapter ships",
        ),
        "status": "declared",
        "reason": "generation_capability_not_available",
        "reusable": True,
        "tags": ["generation", "xiaohongshu"],
    },
    # ---- review ---------------------------------------------------------
    {
        "skill_id": "finance-risk-review",
        "skill_type": "review",
        "version": "1.0.0",
        "description": (
            "Finance risk review: prohibited categories, blocked patterns, review "
            "decisions and evidence requirements enforced before generation."
        ),
        "capabilities": [
            "review.risk_categories",
            "review.blocked_patterns",
            "review.review_decisions",
            "review.evidence_requirement",
        ],
        "inputs": ["unified_distillation_artifact", "evaluation_result"],
        "outputs": ["risk_constraints", "gate_decision"],
        "dependencies": [
            {"target": "text-distillation", "kind": "require", "reason": "review reads distilled claims"}
        ],
        "compatibility": {
            "domains": ["finance"],
            "platforms": [],
            "styles": [],
            "requires_contract_version": "1.0.0",
        },
        "provenance": _provenance("template", "risk_policy_reference", "1.0.0", 1.0),
        "status": "available",
        "reusable": True,
        "tags": ["review", "risk", "finance"],
    },
    {
        "skill_id": "evidence-review",
        "skill_type": "review",
        "version": "1.0.0",
        "description": (
            "Domain-neutral evidence review: source-reference coverage, first-party "
            "ratio and the rule that discovery-layer material is not a factual basis."
        ),
        "capabilities": [
            "review.source_reference_coverage",
            "review.first_party_ratio",
            "review.evidence_layer_only_as_fact",
        ],
        "inputs": ["unified_distillation_artifact"],
        "outputs": ["common_evaluation_result"],
        "dependencies": [
            {"target": "text-distillation", "kind": "require", "reason": "evidence review reads distilled claims"}
        ],
        "compatibility": {
            "domains": [],
            "platforms": [],
            "styles": [],
            "requires_contract_version": "1.0.0",
        },
        "provenance": _provenance("template", "evaluation_rubric", "1.0.0", 1.0),
        "status": "available",
        "reusable": True,
        "tags": ["review", "evidence"],
    },
    # ---- publishing -----------------------------------------------------
    {
        "skill_id": "xiaohongshu-publishing",
        "skill_type": "publishing",
        "version": "1.0.0",
        "description": (
            "Xiaohongshu publishing target: media requirements, idempotency key and "
            "schedule. Declares a target; the publisher is injected by a deployment."
        ),
        "capabilities": [
            "publishing.platform_target",
            "publishing.image_requirement",
            "publishing.idempotency",
            "publishing.schedule",
        ],
        "inputs": ["generated_content", "gate_decision"],
        "outputs": ["publishing_target"],
        "dependencies": [
            {"target": "xiaohongshu-article-generation", "kind": "require", "reason": "only generated content is published"}
        ],
        "compatibility": {
            "domains": [],
            "platforms": ["xiaohongshu"],
            "styles": [],
            "requires_contract_version": "1.0.0",
        },
        "provenance": _provenance(
            "template", "publishing_capability", "1.0.0", 0.0,
            "no publisher, CMS, or idempotency implementation exists",
        ),
        "status": "declared",
        "reason": "publishing_capability_not_available",
        "reusable": True,
        "tags": ["publishing", "xiaohongshu"],
    },
)


def catalog_document() -> dict[str, Any]:
    """Return the catalog as a plain document."""

    return {
        "catalog_version": CATALOG_VERSION,
        "generated_at": CATALOG_TIMESTAMP,
        "skills": [dict(entry) for entry in DEFAULT_SKILL_CATALOG],
    }


def catalog_asset_references() -> tuple[str, ...]:
    """Return every ``source_ref`` the catalog uses, sorted and deduplicated."""

    return tuple(
        sorted({str(entry["provenance"]["source_ref"]) for entry in DEFAULT_SKILL_CATALOG})
    )


__all__ = [
    "CATALOG_TIMESTAMP",
    "CATALOG_VERSION",
    "DEFAULT_SKILL_CATALOG",
    "catalog_asset_references",
    "catalog_document",
]
