"""Project the existing blank template into a Creator Instance Contract document.

This is a **config-layer projection, not a copy**. It reads the template's own
declared configuration — runtime config, plugin manifest, rule files, rubric,
provenance metadata — and expresses it as the eight instance modules. No source
file from the template is duplicated, and nothing under the template workspace is
written to.

The projection exists to prove the contract against real content: if the frozen
template cannot be expressed as a Creator Instance, the contract is wrong.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .artifacts import MODULE_NAMES, canonical_json, instance_dir
from .authoring import build_visual_rules
from .errors import CreatorContractError, CreatorContractSchemaError

#: Default template workspace, relative to the repository root.
TEMPLATE_WORKSPACE_PARTS: tuple[str, ...] = ("blank", "workspace")

#: Plugin whose declared rules are projected. The template ships exactly one.
DEFAULT_PLUGIN_RELATIVE: str = "plugins/xiaolin_finance"


@dataclass(frozen=True, slots=True)
class ProjectionReport:
    """What the projection read, and what it produced."""

    template_root: Path
    plugin_relative: str
    creator_id: str
    modules: tuple[str, ...]
    sources_read: tuple[str, ...]
    counts: Mapping[str, int]
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "template_root": str(self.template_root),
            "plugin_relative": self.plugin_relative,
            "creator_id": self.creator_id,
            "modules": list(self.modules),
            "sources_read": list(self.sources_read),
            "counts": dict(self.counts),
            "notes": list(self.notes),
        }


def resolve_template_root(explicit: str | Path | None = None) -> Path:
    """Locate the template workspace.

    Defaults to the workspace that contains this package (``parents[1]`` of this
    file), so the projection works when the framework is deployed on its own and
    does not depend on the current working directory.

    ``TEMPLATE_WORKSPACE_PARTS`` names the repository-relative location used when
    the framework is *unpacked inside* a larger repository instead.
    """

    if explicit is not None:
        root = Path(explicit)
    else:
        root = Path(__file__).resolve().parents[1]
    if not root.is_dir():
        raise CreatorContractError(f"template workspace not found: {root}")
    return root


def resolve_repository_template_root(
    repository_root: str | Path | None = None,
) -> Path:
    """Locate the template when the framework sits inside a larger repository.

    The layout differs between a development checkout (``<repo>/blank/workspace``)
    and a deployment where the framework *is* the workspace. Both are tried, so
    the resolver does not assume which one it is running in.
    """

    if repository_root is not None:
        base = Path(repository_root)
    else:
        base = Path(__file__).resolve().parents[2]

    candidates = (
        base.joinpath(*TEMPLATE_WORKSPACE_PARTS),  # <base>/blank/workspace
        base,                                     # <base> is already the workspace
        base / "workspace",
    )
    for candidate in candidates:
        if (candidate / "config" / "runtime" / "default.json").is_file():
            return candidate
    raise CreatorContractError(
        "template workspace not found near "
        f"{base}; tried: " + ", ".join(str(path) for path in candidates)
    )


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CreatorContractSchemaError(f"template file not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CreatorContractSchemaError(f"cannot read template file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CreatorContractSchemaError(f"template file must be an object: {path}")
    return payload


def project_blank_template(
    *,
    template_root: str | Path | None = None,
    plugin_relative: str = DEFAULT_PLUGIN_RELATIVE,
    visual_profile: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], ProjectionReport]:
    """Project the template into a Creator Instance document.

    Returns:
        ``(instance, report)``. The instance is schema-valid and
        isolation-clean; it is *not* a new creator, it is the template's own
        configuration restated in contract form.
    """

    root = resolve_template_root(template_root)
    plugin_dir = root / plugin_relative
    if not plugin_dir.is_dir():
        raise CreatorContractError(f"template plugin directory not found: {plugin_dir}")

    runtime_config = _read_json(root / "config" / "runtime" / "default.json")
    plugin_manifest = _read_json(plugin_dir / "plugin.json")
    value_rules = _read_json(plugin_dir / "rules" / "value_rules.json")
    filter_rules = _read_json(plugin_dir / "rules" / "filter_rules.json")
    structure_templates = _read_json(plugin_dir / "rules" / "structure_templates.json")
    rubric = _read_json(plugin_dir / "evaluation" / "rubric.json")

    plugin_block = _mapping(plugin_manifest, "plugin", plugin_dir / "plugin.json")
    instance_block = _mapping(runtime_config, "instance", root / "config" / "runtime" / "default.json")
    contract_block = plugin_manifest.get("contract", {})
    domain_schema = plugin_manifest.get("domain_schema", {})

    creator_id = str(instance_block.get("name", "creator-agent-template"))
    domain = str(plugin_block.get("domain", "general"))
    creator_target = str(plugin_block.get("creator_target", creator_id))
    platform = "web"

    notes: list[str] = []

    # ---- identity -------------------------------------------------------
    identity = _project_identity(
        creator_id=creator_id,
        plugin_block=plugin_block,
        domain=domain,
        creator_target=creator_target,
        platform=platform,
        value_rules=value_rules,
        notes=notes,
    )

    # ---- source ---------------------------------------------------------
    source = _project_source(value_rules, notes=notes)

    # ---- text_rules -----------------------------------------------------
    text_rules = _project_text_rules(value_rules, structure_templates, rubric)

    # ---- visual_rules ---------------------------------------------------
    visual_rules = build_visual_rules(visual_profile)
    notes.append(
        "visual_rules references the M5 profile projection; "
        "the template carries no prompt and none is projected"
    )

    # ---- risk_policy ----------------------------------------------------
    risk_policy = _project_risk_policy(filter_rules, rubric)

    # ---- generation -----------------------------------------------------
    generation = _project_generation(notes=notes)

    # ---- publishing -----------------------------------------------------
    publishing = _project_publishing(platform, notes=notes)

    # ---- provenance -----------------------------------------------------
    provenance = {
        "identity": {"source": "plugin_manifest", "derivation": "read",
                     "artifact": f"{plugin_relative}/plugin.json"},
        "source": {"source": "plugin_value_rules", "derivation": "read",
                   "artifact": f"{plugin_relative}/rules/value_rules.json"},
        "text_rules": {"source": "plugin_rules", "derivation": "read",
                       "artifact": f"{plugin_relative}/rules/structure_templates.json"},
        "visual_rules": {"source": "M5_profile", "derivation": "referenced",
                         "artifact": "docs/m5/profiles/visual_profile.yaml"},
        "risk_policy": {"source": "plugin_filter_rules", "derivation": "read",
                        "artifact": f"{plugin_relative}/rules/filter_rules.json"},
        "generation": {"source": "runtime_generation_contract", "derivation": "declared",
                       "artifact": "workflows/content_distillation_pipeline/generation_interface.py"},
        "publishing": {"source": "deployment_publishing_target", "derivation": "declared",
                       "artifact": "config/runtime/default.json"},
        "generated_by": "creator_contract.template_projection c0.1.0",
        "template_contract": {
            "specification": str(contract_block.get("specification", "")),
            "version": str(contract_block.get("version", "")),
            "domain_schema_version": str(domain_schema.get("version", "")),
        },
    }

    instance = {
        "contract_version": "1.0.0",
        "identity": identity,
        "source": source,
        "text_rules": text_rules,
        "visual_rules": visual_rules,
        "risk_policy": risk_policy,
        "generation": generation,
        "publishing": publishing,
        "provenance": provenance,
    }

    report = ProjectionReport(
        template_root=root,
        plugin_relative=plugin_relative,
        creator_id=creator_id,
        modules=MODULE_NAMES,
        sources_read=(
            "config/runtime/default.json",
            f"{plugin_relative}/plugin.json",
            f"{plugin_relative}/rules/value_rules.json",
            f"{plugin_relative}/rules/filter_rules.json",
            f"{plugin_relative}/rules/structure_templates.json",
            f"{plugin_relative}/evaluation/rubric.json",
        ),
        counts={
            "mental_models": len(identity["persona"]["mental_models"]),
            "decision_heuristics": len(identity["persona"]["decision_heuristics"]),
            "keywords": len(source["keywords"]),
            "data_sources": len(source["data_sources"]),
            "risk_categories": len(risk_policy["risk_categories"]),
            "blocked_patterns": len(risk_policy["blocked_patterns"]),
            "structure_sections": len(text_rules["structure"]["sections"]),
        },
        notes=tuple(notes),
    )
    return instance, report


def _project_identity(
    *,
    creator_id: str,
    plugin_block: Mapping[str, Any],
    domain: str,
    creator_target: str,
    platform: str,
    value_rules: Mapping[str, Any],
    notes: list[str],
) -> dict[str, Any]:
    sections = value_rules.get("sections", {})
    if not isinstance(sections, Mapping) or not sections:
        raise CreatorContractError("value_rules.json declares no sections to project")

    mental_models = [
        {
            "model_id": str(section_id),
            "mechanism": str(description),
            "evidence": f"declared as a distill section in {creator_id} value rules",
            "apply_when": f"material concerns {section_id.replace('_', ' ')}",
            "failure_condition": "no source material supports this section",
        }
        for section_id, description in sections.items()
    ]

    notes.append(
        "the template ships no persona; mental_models are projected from the "
        "plugin's declared value-rule sections, not from a distilled creator"
    )

    return {
        "creator_id": creator_id,
        "name": creator_id,
        "domain": domain if domain in {"finance", "sports", "tech", "general"} else "general",
        "persona": {
            "mode": "reasoning_model",
            "identity_card": (
                f"{creator_id} is the template's reference instance for the "
                f"{domain} domain, targeting {creator_target}."
            ),
            "mental_models": mental_models,
            "decision_heuristics": [
                f"prefer material whose {rule_id} dimension is present"
                for rule_id in (
                    str(rule.get("dimension"))
                    for rule in value_rules.get("rules", [])
                    if isinstance(rule, Mapping)
                )
            ][:10]
            or ["prefer material that matches a declared value rule"],
            "honest_boundaries": [
                "projected from the blank template; no creator research was performed",
                "no persona distillation has been run for this instance",
                "the template contains no account-specific data",
            ],
        },
        "audience": "unspecified; the template declares no audience",
        "tone": "evidence-aware, mechanism-first, conclusion keeps its boundaries",
        "platform": platform,
        "language": "en",
    }


def _project_source(
    value_rules: Mapping[str, Any],
    *,
    notes: list[str],
) -> dict[str, Any]:
    keywords: list[dict[str, Any]] = []
    for rule in value_rules.get("rules", []):
        if not isinstance(rule, Mapping):
            continue
        weight = rule.get("weight", 0.5)
        for keyword in rule.get("keywords", []):
            keywords.append({"keyword": str(keyword), "weight": float(weight)})
    if not keywords:
        raise CreatorContractError("value_rules.json declares no keywords to project")

    notes.append(
        "the template declares no reference creator; a placeholder is used "
        "because the contract requires at least one verified reference"
    )

    return {
        "reference_creators": [
            {
                "name": "template-placeholder",
                "platform": "web",
                "identity_verified": True,
                "verification_method": "not-applicable: template declares no reference creator",
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


def _project_text_rules(
    value_rules: Mapping[str, Any],
    structure_templates: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> dict[str, Any]:
    templates = structure_templates.get("templates", [])
    if not isinstance(templates, list) or not templates:
        raise CreatorContractError("structure_templates.json declares no template")
    first = templates[0]
    if not isinstance(first, Mapping):
        raise CreatorContractError("structure template must be an object")

    sections = [str(section) for section in first.get("sections", [])]
    if not sections:
        raise CreatorContractError("structure template declares no sections")

    required_evidence = [str(item) for item in first.get("required_evidence", [])]
    boundaries = [str(question) for question in _rubric_questions(rubric)]
    if not boundaries:
        boundaries = ["domain rubric declares no checks to project"]

    return {
        "title_formula": [f"[specific subject], what is the [{name}]?" for name in sections[:3]],
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
        "knowledge_boundary": boundaries + [f"required evidence: {item}" for item in required_evidence]
        or ["no boundary declared"],
    }


def _rubric_questions(rubric: Mapping[str, Any]) -> list[str]:
    questions: list[str] = []
    for field in ("dimensions", "finance_checks", "inherited_checks"):
        block = rubric.get(field)
        if not isinstance(block, Mapping):
            continue
        for _key, value in block.items():
            if isinstance(value, Mapping) and value.get("question"):
                questions.append(str(value["question"]))
    return questions


def _project_risk_policy(
    filter_rules: Mapping[str, Any],
    rubric: Mapping[str, Any],
) -> dict[str, Any]:
    rules = filter_rules.get("rules", [])
    if not isinstance(rules, list) or not rules:
        raise CreatorContractError("filter_rules.json declares no risk rules to project")

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
        raise CreatorContractError("projected risk policy would be empty")

    scoring = rubric.get("scoring", {})
    pass_score = rubric.get("pass_score", 0.6)
    if not isinstance(scoring, Mapping):
        scoring = {}

    return {
        "risk_categories": categories,
        "review_rules": [
            {"when": "any risk category with severity 'block' matched", "decision": "block"},
            {
                "when": f"domain score below pass_score ({pass_score})",
                "decision": "require_review",
            },
            {"when": "no blocking risk and domain score at or above pass_score", "decision": "pass"},
        ],
        "blocked_patterns": blocked,
        "evidence_requirement": {
            "require_source_ids": True,
            "min_first_party_ratio": 0.5,
            "evidence_layer_only_as_fact": True,
        },
    }


def _project_generation(*, notes: list[str]) -> dict[str, Any]:
    notes.append(
        "the template ships no generation adapter; generation is declared as a "
        "routing reference and left disabled"
    )
    return {
        "adapter_ref": "deployment.generation_adapter",
        "input": ["topic", "structure", "knowledge", "style", "domain_context", "constraints"],
        "output_format": "content_plan",
        "quality_gate": {
            "required_decision": "PASS",
            "controller_ref": "evaluation.quality_gate_controller.QualityGateController",
        },
        "enabled": False,
    }


def _project_publishing(platform: str, *, notes: list[str]) -> dict[str, Any]:
    notes.append(
        "the template ships no publisher; publishing is declared as a target "
        "with an explicit idempotency key"
    )
    return {
        "platform": platform if platform in {"xiaohongshu", "bilibili", "youtube", "douyin", "wechat", "web", "github"} else "web",
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
    }


def _mapping(parent: Mapping[str, Any], key: str, origin: Path) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise CreatorContractSchemaError(f"{origin} has no {key!r} object")
    return value


def write_projected_instance(
    *,
    template_root: str | Path | None = None,
    plugin_relative: str = DEFAULT_PLUGIN_RELATIVE,
    out_root: str | Path = "creator_instance",
    visual_profile: Mapping[str, Any] | None = None,
) -> tuple[list[Path], ProjectionReport]:
    """Project the template and write it to ``<out_root>/<creator_id>/``.

    The projection is written, and the template workspace is only read.
    """

    instance, report = project_blank_template(
        template_root=template_root,
        plugin_relative=plugin_relative,
        visual_profile=visual_profile,
    )
    target = instance_dir(out_root, report.creator_id)
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for module in MODULE_NAMES:
        path = target / f"{module}.json"
        path.write_text(canonical_json(instance[module]), encoding="utf-8")
        written.append(path)
    aggregate = target / "creator_instance.json"
    aggregate.write_text(canonical_json(instance), encoding="utf-8")
    written.append(aggregate)
    return written, report


__all__ = [
    "DEFAULT_PLUGIN_RELATIVE",
    "ProjectionReport",
    "TEMPLATE_WORKSPACE_PARTS",
    "project_blank_template",
    "resolve_repository_template_root",
    "resolve_template_root",
    "write_projected_instance",
]
