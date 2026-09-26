"""Finance-specific enhancement implemented entirely outside the core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.models import RawSource
from plugin_interface.base import PluginContribution, PluginIdentity


_PACKAGE_ROOT = Path(__file__).resolve().parent


def _load_json(relative_path: str) -> Any:
    return json.loads((_PACKAGE_ROOT / relative_path).read_text(encoding="utf-8"))


def _excerpt(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


class XiaolinFinancePlugin:
    """Reference finance plugin; it structures evidence but writes no article."""

    @property
    def identity(self) -> PluginIdentity:
        return PluginIdentity(
            name="xiaolin_finance",
            version="1.0.0",
            domain="finance",
            creator_target="xiaolin-style-finance-explainer",
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
                        "severity": rule["severity"],
                        "action": rule["action"],
                        "message": rule["message"],
                        "source_ids": [source.source_id],
                    }
                )
                filtered_claims.append(
                    {
                        "rule_id": rule["id"],
                        "source_id": source.source_id,
                        "matched_terms": matched,
                        "excerpt": _excerpt(text),
                    }
                )

        selected_template = templates["templates"][0]
        domain_score = _score_domain(value_signals, risk_constraints, rubric)
        return PluginContribution(
            domain_extension={
                "schema_version": "1.0.0",
                "plugin_identity": self.identity.as_dict(),
                "value_signals": value_signals,
                "filtered_claims": filtered_claims,
                "recommended_structure": selected_template,
                "common_signal_counts": {
                    key: len(values) for key, values in common_signals.items()
                },
            },
            risk_constraints=risk_constraints,
            evaluation_result={
                "score": domain_score,
                "passed": domain_score >= rubric["pass_score"],
                "checks": {
                    "value_signal_count": len(value_signals),
                    "risk_constraint_count": len(risk_constraints),
                    "template_selected": bool(selected_template),
                },
                "rubric_version": rubric["version"],
            },
            field_enhancements={"topic_candidate": topic_enhancements},
        )


def _score_domain(
    value_signals: Sequence[Mapping[str, Any]],
    risks: Sequence[Mapping[str, Any]],
    rubric: Mapping[str, Any],
) -> float:
    dimensions = {signal["dimension"] for signal in value_signals}
    coverage = len(dimensions) / len(rubric["dimensions"])
    blocking = any(item["severity"] == "block" for item in risks)
    warning_penalty = min(
        0.3,
        sum(1 for item in risks if item["severity"] == "warning") * 0.1,
    )
    score = (0.4 + coverage * 0.6) - warning_penalty
    if blocking:
        score = min(score, 0.2)
    return round(max(0.0, min(1.0, score)), 3)
