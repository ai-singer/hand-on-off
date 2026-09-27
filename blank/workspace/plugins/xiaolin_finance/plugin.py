"""Finance-specific enhancement implemented entirely outside the core.

The plugin is declarative where it can be: `plugin.json` owns its identity and
contract, `rules/` owns what finance content should and must not distil, and
`evaluation/rubric.json` owns the scoring policy. This module only interprets
those files, so the domain policy stays inspectable and reviewable.

See `docs/CREATOR_SPECIFIC_PLUGIN_CONTRACT.md` for the contract this
implementation satisfies.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.models import RawSource
from plugin_interface.base import PluginContribution, PluginIdentity


_PACKAGE_ROOT = Path(__file__).resolve().parent

#: The five distillation sections the finance taxonomy produces, in report order.
DISTILLATION_SECTIONS = (
    "business_mechanism",
    "financial_structure",
    "data_expression_pattern",
    "case_selection_logic",
    "misconception_analysis",
)

#: Common artifact field -> the distillation role a source played for it.
_FIELD_ROLES = (
    ("topic_candidate", "topic_source"),
    ("knowledge_unit", "knowledge_source"),
    ("content_template", "structure_source"),
    ("style_pattern", "style_source"),
)


@lru_cache(maxsize=1)
def load_plugin_manifest() -> dict[str, Any]:
    """Return the declarative manifest shipped next to this module."""

    return _load_json("plugin.json")


def _load_json(relative_path: str) -> Any:
    return json.loads((_PACKAGE_ROOT / relative_path).read_text(encoding="utf-8"))


def _excerpt(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _referenced_source_ids(item: Mapping[str, Any]) -> list[str]:
    direct = item.get("source_ids", [])
    evidence = [
        ref.get("source_id")
        for ref in item.get("evidence_refs", [])
        if isinstance(ref, dict) and ref.get("source_id")
    ]
    return [str(value) for value in [*direct, *evidence] if value]


def _build_sections(
    value_signals: Sequence[Mapping[str, Any]],
    section_by_dimension: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    """Group matched signals into the five domain_extension sections."""

    sections: dict[str, dict[str, Any]] = {
        name: {"matched": False, "signals": [], "source_ids": []}
        for name in DISTILLATION_SECTIONS
    }
    for signal in value_signals:
        section_name = section_by_dimension.get(signal["dimension"])
        if section_name is None:
            continue
        section = sections[section_name]
        section["matched"] = True
        section["signals"].append(signal)
        section["source_ids"] = _unique([*section["source_ids"], *signal["source_ids"]])
    return sections


def _classify_sources(
    sources: Sequence[RawSource],
    common_signals: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    """Record which distillation role each source actually played.

    The classification is derived from where a source is referenced in the
    common extraction, so it reflects the run rather than a configured guess.
    """

    classified: list[dict[str, Any]] = []
    for source in sources:
        fields: list[str] = []
        roles: list[str] = []
        for field_name, role in _FIELD_ROLES:
            if any(
                source.source_id in _referenced_source_ids(item)
                for item in common_signals.get(field_name, ())
            ):
                fields.append(field_name)
                roles.append(role)
        classified.append(
            {
                "source_id": source.source_id,
                "roles": roles,
                "artifact_fields": fields,
            }
        )
    return classified


class XiaolinFinancePlugin:
    """Reference finance plugin; it structures evidence but writes no article."""

    @property
    def identity(self) -> PluginIdentity:
        declared = load_plugin_manifest()["plugin"]
        return PluginIdentity(
            name=declared["name"],
            version=declared["version"],
            domain=declared["domain"],
            creator_target=declared["creator_target"],
        )

    def enhance(
        self,
        raw_sources: Sequence[RawSource],
        common_signals: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> PluginContribution:
        value_rules = _load_json("rules/value_rules.json")
        filter_rules = _load_json("rules/filter_rules.json")
        templates = _load_json("rules/structure_templates.json")
        rubric = _load_json("evaluation/rubric.json")

        section_by_dimension = {
            rule["dimension"]: rule.get("section", rule["dimension"])
            for rule in value_rules["rules"]
        }
        category_by_rule = {
            rule["id"]: rule.get("category", rule["id"])
            for rule in filter_rules["rules"]
        }

        value_signals: list[dict[str, Any]] = []
        risk_constraints: list[dict[str, Any]] = []
        filtered_claims: list[dict[str, Any]] = []
        topic_enhancements: list[dict[str, Any]] = []

        for source in raw_sources:
            text = source.as_text()
            normalized = text.lower()
            for rule in value_rules["rules"]:
                matched = [keyword for keyword in rule["keywords"] if keyword.lower() in normalized]
                if not matched:
                    continue
                signal = {
                    "rule_id": rule["id"],
                    "dimension": rule["dimension"],
                    "section": rule.get("section", rule["dimension"]),
                    "weight": rule["weight"],
                    "matched_terms": matched,
                    "source_ids": [source.source_id],
                }
                value_signals.append(signal)
                topic_enhancements.append(
                    {
                        "label": f"{rule['label']}: {_excerpt(text, 72)}",
                        "rationale": rule["rationale"],
                        "source_ids": [source.source_id],
                        "confidence": min(0.95, 0.65 + float(rule["weight"]) * 0.2),
                        "origin": self.identity.name,
                    }
                )

            for rule in filter_rules["rules"]:
                matched = [keyword for keyword in rule["keywords"] if keyword.lower() in normalized]
                if not matched:
                    continue
                risk_constraints.append(
                    {
                        "rule_id": rule["id"],
                        "category": category_by_rule[rule["id"]],
                        "severity": rule["severity"],
                        "action": rule["action"],
                        "message": rule["message"],
                        "source_ids": [source.source_id],
                    }
                )
                filtered_claims.append(
                    {
                        "rule_id": rule["id"],
                        "category": category_by_rule[rule["id"]],
                        "source_id": source.source_id,
                        "matched_terms": matched,
                        "excerpt": _excerpt(text),
                    }
                )

        selected_template = templates["templates"][0]
        sections = _build_sections(value_signals, section_by_dimension)
        domain_score = _score_domain(value_signals, risk_constraints, rubric)
        return PluginContribution(
            domain_extension={
                "schema_version": load_plugin_manifest()["domain_schema"]["version"],
                "plugin_identity": self.identity.as_dict(),
                "value_signals": value_signals,
                "filtered_claims": filtered_claims,
                "recommended_structure": selected_template,
                "common_signal_counts": {
                    key: len(values) for key, values in common_signals.items()
                },
                **sections,
                "source_classification": _classify_sources(raw_sources, common_signals),
            },
            risk_constraints=risk_constraints,
            evaluation_result={
                "score": domain_score,
                "passed": domain_score >= rubric["pass_score"],
                "checks": {
                    "value_signal_count": len(value_signals),
                    "risk_constraint_count": len(risk_constraints),
                    "template_selected": bool(selected_template),
                    "matched_sections": sorted(
                        name for name, section in sections.items() if section["matched"]
                    ),
                },
                "rubric_version": rubric["version"],
                "inherited_checks": _inherited_checks(
                    value_signals, raw_sources, rubric, bool(selected_template)
                ),
                "finance_checks": _finance_checks(value_signals, risk_constraints, rubric),
            },
            field_enhancements={"topic_candidate": topic_enhancements},
        )


def _round(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _score_domain(
    value_signals: Sequence[Mapping[str, Any]],
    risks: Sequence[Mapping[str, Any]],
    rubric: Mapping[str, Any],
) -> float:
    """Apply the rubric's declared scoring policy to the matched evidence."""

    scoring = rubric["scoring"]
    dimensions = {signal["dimension"] for signal in value_signals}
    coverage = len(dimensions) / len(rubric["dimensions"])
    warning_count = sum(1 for item in risks if item["severity"] == "warning")
    warning_penalty = min(
        scoring["warning_penalty_cap"],
        warning_count * scoring["warning_penalty"],
    )
    score = (scoring["base"] + coverage * scoring["coverage_weight"]) - warning_penalty
    if any(item["severity"] == "block" for item in risks):
        score = min(score, scoring["blocking_score_cap"])
    return _round(score)


def _inherited_checks(
    value_signals: Sequence[Mapping[str, Any]],
    sources: Sequence[RawSource],
    rubric: Mapping[str, Any],
    template_selected: bool,
) -> dict[str, Any]:
    """Report the framework-level dimensions this plugin inherits."""

    dimensions = {signal["dimension"] for signal in value_signals}
    total_dimensions = len(rubric["dimensions"])
    contributing = {sid for signal in value_signals for sid in signal["source_ids"]}
    coverage = len(dimensions) / total_dimensions if total_dimensions else 0.0
    transferability = len(contributing) / len(sources) if sources else 0.0
    return {
        "performance": {
            "score": _round(coverage),
            "note": f"covered {len(dimensions)}/{total_dimensions} finance dimensions",
        },
        "structure_quality": {
            "score": 1.0 if template_selected else 0.0,
            "note": "structure template selected"
            if template_selected
            else "no structure template selected",
        },
        "transferability": {
            "score": _round(transferability),
            "note": f"{len(contributing)}/{len(sources)} sources contributed value signals",
        },
    }


def _finance_checks(
    value_signals: Sequence[Mapping[str, Any]],
    risks: Sequence[Mapping[str, Any]],
    rubric: Mapping[str, Any],
) -> dict[str, Any]:
    """Report the finance-specific checks declared by the rubric."""

    policy = rubric["finance_checks"]
    blocking = sum(1 for item in risks if item["severity"] == "block")
    warnings = sum(1 for item in risks if item["severity"] == "warning")

    boundary_policy = policy["risk_boundary"]
    if blocking:
        risk_boundary = boundary_policy["blocking_score"]
    else:
        risk_boundary = 1.0 - warnings * boundary_policy["warning_penalty"]

    credibility_policy = policy["data_credibility"]
    unverified = sum(
        1 for item in risks if item["rule_id"] in credibility_policy["rule_ids"]
    )
    data_credibility = 1.0 - unverified * credibility_policy["penalty_per_match"]

    required = list(policy["explanation_completeness"]["required_dimensions"])
    dimensions = {signal["dimension"] for signal in value_signals}
    present = [name for name in required if name in dimensions]
    completeness = len(present) / len(required) if required else 0.0

    return {
        "data_credibility": {
            "score": _round(data_credibility),
            "note": f"{unverified} unattributable-claim match(es)",
        },
        "explanation_completeness": {
            "score": _round(completeness),
            "note": "present dimensions: " + (", ".join(present) if present else "none"),
        },
        "risk_boundary": {
            "score": _round(risk_boundary),
            "note": f"blocking={blocking} warning={warnings}",
        },
    }
