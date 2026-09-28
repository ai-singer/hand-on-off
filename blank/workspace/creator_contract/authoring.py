"""Builders that produce valid Creator Instance documents.

These exist so tests and later phases never hand-roll a document, and so the
contract has exactly one definition of "minimal valid instance".

Defaults are drawn from real artifacts rather than invented:

* identity shape follows the nuwa-generated ``tim-mediastorm-perspective``
  (identity card, mental models, decision heuristics, honest boundaries);
* source rules follow ``xhs-collection-strategy`` (dual-layer architecture,
  mandatory identity verification, tiering, rate limit);
* text rules follow the finance plugin's single structure template and the
  MediaStorm tone guidance;
* visual rules follow the M5 ``factory_config`` projection, whose
  ``visual_profile`` / ``attention`` / ``hierarchy`` / ``composition`` /
  ``constraints`` / ``provenance`` keys are mirrored exactly;
* risk categories mirror the finance plugin's four filter rules.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .artifacts import MODULE_NAMES
from .errors import CreatorContractError

#: The M5 projection this contract references. Mirrors
#: ``multimodal_creator.profile.serialization.factory_config``.
REFERENCE_VISUAL_PROFILE: dict[str, Any] = {
    "visual_profile": {
        "profile_id": "vcp-4fea7437238d4bca",
        "profile_version": "m5.0.0",
        "creator_id": "creator_a",
        "support": 10,
        "confidence": 0.7,
        "confidence_floor": 0.7,
    },
    "identity": {
        "style_family": "high_contrast__dense__full_bleed__display_led",
        "visual_language": "information_first",
        "complexity": "low",
        "density": "dense",
        "contrast": "high_contrast",
        "framing": "full_bleed",
        "typography": "display_led",
    },
    "composition": {
        "preferred_layout": ["top_entry"],
        "forbidden_layout": [
            "central_subject",
            "offset_subject",
            "full_bleed_subject",
            "bottom_anchor",
            "overlay_headline",
            "split_columns",
            "stacked_information",
            "centred_information",
        ],
    },
    "attention": {"first": "headline", "second": "subject", "third": "headline"},
    "hierarchy": {"primary": "hook"},
    "constraints": {
        "must_have": [
            "background_present",
            "headline_present",
            "headline_first",
            "headline_top_mid",
        ],
        "avoid": ["missing_information_support"],
    },
    "provenance": {
        "visual_identity": {
            "source": {"phase": "M4", "artifact": "strategy-family-creator_a", "artifact_kind": "CreatorStrategyPattern+VisualGrammar"},
            "derivation": "aggregated",
            "confidence": 0.775,
        }
    },
    "source_pattern_ids": ["strategy-family-creator_a"],
    "generated_by": "multimodal_creator.profile m5.0.0",
}


def build_visual_rules(profile: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Derive the ``visual_rules`` module from an M5 profile projection.

    The result carries vocabulary and constraints only. It is structurally
    incapable of carrying a prompt, a model reference, or image data, because the
    projection it reads from cannot carry them either.
    """

    source = dict(profile) if profile is not None else deepcopy(REFERENCE_VISUAL_PROFILE)
    envelope = source.get("visual_profile")
    if not isinstance(envelope, Mapping):
        raise CreatorContractError("M5 profile projection has no visual_profile envelope")
    identity = source.get("identity")
    if not isinstance(identity, Mapping):
        raise CreatorContractError("M5 profile projection has no identity block")

    return {
        "profile_id": envelope.get("profile_id"),
        "profile_version": envelope.get("profile_version"),
        "visual_language": identity.get("visual_language"),
        "attention_strategy": dict(source.get("attention", {})),
        "composition": {
            "preferred_layout": list(source.get("composition", {}).get("preferred_layout", [])),
            "forbidden_layout": list(source.get("composition", {}).get("forbidden_layout", [])),
        },
        "hierarchy": dict(source.get("hierarchy", {})),
        "constraints": {
            "must_have": list(source.get("constraints", {}).get("must_have", [])),
            "avoid": list(source.get("constraints", {}).get("avoid", [])),
        },
        "provenance": deepcopy(dict(source.get("provenance", {}))),
    }


def build_identity(
    *,
    creator_id: str = "finance-xia",
    name: str = "Finance Xia",
    domain: str = "finance",
    platform: str = "xiaohongshu",
    audience: str = "普通投资者与商业观察者",
    tone: str = "克制、机制解释优先、结论留边界",
    language: str = "zh",
    persona_mode: str = "reasoning_model",
) -> dict[str, Any]:
    """Build the ``identity`` module."""

    return {
        "creator_id": creator_id,
        "name": name,
        "domain": domain,
        "persona": {
            "mode": persona_mode,
            "identity_card": (
                f"{name} 是一个面向 {audience} 的 {domain} 内容创作者，"
                "以机制解释和证据优先的方式组织内容。"
            ),
            "mental_models": [
                {
                    "model_id": "mechanism-first",
                    "mechanism": "先解释价值、成本与激励如何连接，再给结论。",
                    "evidence": "多篇内容以商业模式与财务结构作为承重结构。",
                    "apply_when": "选题只有结论没有因果时。",
                    "failure_condition": "机制无法从可得证据中还原时失效。",
                },
                {
                    "model_id": "misconception-first",
                    "mechanism": "先指出一个常见误区，再分离事实与感知。",
                    "evidence": "内容反复以误区开篇建立信息落差。",
                    "apply_when": "受众已有稳定但错误的先验时。",
                    "failure_condition": "误区并不普遍时显得刻意。",
                },
                {
                    "model_id": "boundary-keeping",
                    "mechanism": "结论必须标注成立条件与不确定区间。",
                    "evidence": "材料中保留风险边界与反证。",
                    "apply_when": "结论涉及预测、收益或市场判断时。",
                    "failure_condition": "过度保留会削弱信息增量。",
                },
            ],
            "decision_heuristics": [
                "当选题只剩'很有意义'时，先找一个可核实的数据或案例。",
                "当结论涉及预测时，先写清成立条件再写结论。",
                "当素材来自社交平台时，只作为话题线索，不作为事实依据。",
            ],
            "honest_boundaries": [
                "本实例基于公开信息提炼，不代表任何被参考创作者本人。",
                "无法获知未公开的经营数据与私人动机。",
                "调研时间之后的变化未覆盖。",
            ],
        },
        "audience": audience,
        "tone": tone,
        "platform": platform,
        "language": language,
    }


def build_source(
    *,
    creator_name: str = "小Lin说",
    platform: str = "xiaohongshu",
    keywords: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the ``source`` module."""

    return {
        "reference_creators": [
            {
                "name": creator_name,
                "platform": platform,
                "user_id": "5abf90244eacab2c32c7c5e6",
                "identity_verified": True,
                "verification_method": "api:user/otherinfo nickname match",
                "role": "style_reference",
            }
        ],
        "data_sources": [
            {
                "source_id": "xhs-discovery",
                "layer": "discovery",
                "kind": "social_platform",
                "locator": "xiaohongshu",
            },
            {
                "source_id": "cninfo",
                "layer": "evidence",
                "kind": "official_disclosure",
                "locator": "https://www.cninfo.com.cn/",
            },
            {
                "source_id": "stats-gov",
                "layer": "evidence",
                "kind": "government_statistics",
                "locator": "https://www.stats.gov.cn/",
            },
        ],
        "collection_rules": {
            "min_notes": 100,
            "material_tiers": ["S", "A"],
            "rate_limit_seconds": 3,
            "dedupe_by": "note_id",
        },
        "keywords": keywords
        or [
            {"keyword": "商业分析", "weight": 1.0},
            {"keyword": "财务知识", "weight": 0.95},
            {"keyword": "企业经营", "weight": 0.9},
            {"keyword": "商业模式", "weight": 0.9},
        ],
    }


def build_text_rules() -> dict[str, Any]:
    """Build the ``text_rules`` module."""

    return {
        "title_formula": [
            "[具体对象]，到底[核心疑问]？",
            "[看似合理的现象]，真的[常识判断]吗？",
            "[数量或时间]只为[一个动作]，值得吗？",
        ],
        "structure": {
            "template_id": "mechanism-evidence-case-risk",
            "sections": [
                "question and scope",
                "business or economic mechanism",
                "data and evidence interpretation",
                "company or market case",
                "counter-evidence and risk boundary",
            ],
        },
        "tone": {
            "voice": "同行视角，先具体对象再抛问题",
            "certainty": "对亲历与已核实数据确定，对未来预测保留条件",
            "avoid": ["营销黑话", "空泛夸张", "无来源数字", "投资建议"],
        },
        "length": {"min_chars": 300, "max_chars": 1800},
        "knowledge_boundary": [
            "未核实数字以占位符标记，不虚构。",
            "预测类结论必须标注成立条件。",
            "社交平台内容不作为事实依据。",
        ],
    }


def build_risk_policy() -> dict[str, Any]:
    """Build the ``risk_policy`` module, mirroring the finance filter rules."""

    return {
        "risk_categories": [
            {
                "category_id": "investment_advice",
                "severity": "block",
                "action": "block",
                "definition": "直接买卖指令或保证收益表述。",
            },
            {
                "category_id": "market_prediction",
                "severity": "warning",
                "action": "require_evidence",
                "definition": "以确定性语气给出的预测或目标价。",
            },
            {
                "category_id": "emotional_language",
                "severity": "warning",
                "action": "downrank",
                "definition": "煽动、恐慌框架或夸张判断。",
            },
            {
                "category_id": "unverified_fact",
                "severity": "warning",
                "action": "require_evidence",
                "definition": "无来源数字或不可归属的说法。",
            },
        ],
        "review_rules": [
            {"when": "any risk category with severity 'block' matched", "decision": "block"},
            {"when": "domain score below pass_score", "decision": "require_review"},
            {"when": "no blocking risk and domain score at or above pass_score", "decision": "pass"},
        ],
        "blocked_patterns": [
            {"pattern": "立即买入", "category_id": "investment_advice"},
            {"pattern": "稳赚不赔", "category_id": "investment_advice"},
            {"pattern": "必然上涨", "category_id": "market_prediction"},
            {"pattern": "恐慌", "category_id": "emotional_language"},
            {"pattern": "据说", "category_id": "unverified_fact"},
        ],
        "evidence_requirement": {
            "require_source_ids": True,
            "min_first_party_ratio": 0.5,
            "evidence_layer_only_as_fact": True,
        },
    }


def build_generation(
    *,
    adapter_ref: str = "deployment.generation_adapter",
    output_format: str = "content_plan",
) -> dict[str, Any]:
    """Build the ``generation`` module (a routing declaration, not a model call)."""

    return {
        "adapter_ref": adapter_ref,
        "input": ["topic", "structure", "knowledge", "style", "domain_context", "constraints"],
        "output_format": output_format,
        "quality_gate": {
            "required_decision": "PASS",
            "controller_ref": "evaluation.quality_gate_controller.QualityGateController",
        },
        "enabled": False,
    }


def build_publishing(
    *,
    platform: str = "xiaohongshu",
    aspect_ratio: str = "4:5",
    schedule_mode: str = "manual",
) -> dict[str, Any]:
    """Build the ``publishing`` module (a target declaration, not a publisher)."""

    return {
        "platform": platform,
        "image_requirement": {
            "aspect_ratio": aspect_ratio,
            "min_width": 1080,
            "title_safe_area_ratio": 0.25,
            "count": 3,
        },
        "api": {
            "adapter_ref": "deployment.publishing_adapter",
            "idempotency_key": "creator_id + content_hash",
            "retry_policy": "bounded",
        },
        "schedule": {"mode": schedule_mode, "timezone": "Asia/Shanghai"},
        "requires_human_approval": True,
    }


def build_provenance(
    *,
    identity: str = "nuwa_skill",
    source: str = "xhs_collection_strategy",
    text_rules: str = "finance_plugin_value_rules",
    visual_rules: str = "M5_profile",
    risk_policy: str = "risk_evaluation_v3",
    generation: str = "runtime_generation_contract",
    publishing: str = "deployment_publishing_target",
    generated_by: str = "creator_contract.template_projection c0.1.0",
) -> dict[str, Any]:
    """Build the ``provenance`` module. Every module must be sourced."""

    return {
        "identity": {"source": identity, "derivation": "distilled"},
        "source": {"source": source, "derivation": "configured"},
        "text_rules": {"source": text_rules, "derivation": "configured"},
        "visual_rules": {"source": visual_rules, "derivation": "referenced"},
        "risk_policy": {"source": risk_policy, "derivation": "configured"},
        "generation": {"source": generation, "derivation": "declared"},
        "publishing": {"source": publishing, "derivation": "declared"},
        "generated_by": generated_by,
    }


def build_blank_instance(
    *,
    creator_id: str = "finance-xia",
    name: str = "Finance Xia",
    domain: str = "finance",
    platform: str = "xiaohongshu",
    visual_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a complete, schema-valid, isolation-clean instance."""

    return {
        "contract_version": "1.0.0",
        "identity": build_identity(
            creator_id=creator_id, name=name, domain=domain, platform=platform
        ),
        "source": build_source(platform=platform),
        "text_rules": build_text_rules(),
        "visual_rules": build_visual_rules(visual_profile),
        "risk_policy": build_risk_policy(),
        "generation": build_generation(),
        "publishing": build_publishing(platform=platform),
        "provenance": build_provenance(),
    }


def minimal_instance(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid instance, with optional module overrides.

    ``overrides`` keys must be module names or ``contract_version``.
    """

    instance = build_blank_instance(
        creator_id=overrides.pop("creator_id", "finance-xia"),
        name=overrides.pop("name", "Finance Xia"),
        domain=overrides.pop("domain", "finance"),
        platform=overrides.pop("platform", "xiaohongshu"),
        visual_profile=overrides.pop("visual_profile", None),
    )
    for key, value in overrides.items():
        if key not in MODULE_NAMES and key != "contract_version":
            raise CreatorContractError(f"unknown instance module {key!r}")
        instance[key] = value
    return instance


__all__ = [
    "REFERENCE_VISUAL_PROFILE",
    "build_blank_instance",
    "build_generation",
    "build_identity",
    "build_provenance",
    "build_publishing",
    "build_risk_policy",
    "build_source",
    "build_text_rules",
    "build_visual_rules",
    "minimal_instance",
]
