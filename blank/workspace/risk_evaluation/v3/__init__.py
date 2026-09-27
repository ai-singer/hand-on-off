"""Unified risk evaluation architecture (Phase 8.5).

An **experimental** composition of the layers built in Phases 8.2 to 8.4:

    Raw text
      |  claim extraction        Phase 8.2's parser
      v
    Claims
      |  attribution analysis    Phase 8.2's analyzer
      v
    Speaker + stance
      |  intent analysis         Phase 8.4's matcher, four relations
      v
    Relation + entity + frame
      |  semantic fallback       semantic_evaluator_v2, only where intent was silent
      v
    Categories
      |  decision policy         explicit, ordered, evidenced
      v
    Risk evaluation result + full trace

Three properties are enforced in the model rather than promised in prose: every
claim carries evidence, no decision exists without evidence, and every claim
keeps the span it came from. A final category can therefore always be traced to
the characters, the speaker, the relation and the rule that produced it.

This is not a production integration. `semantic_evaluator_v2`, `taxonomy_v2`
and the runtime are untouched, nothing imports this package outside its tests,
and it is not registered as an evaluator or a benchmark.

See `docs/PHASE_8_5_UNIFIED_RISK_EVALUATION_REPORT.md`.
"""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "V3_VERSION": "model",
    "RELATIONS": "model",
    "ENTITY_NAMES": "model",
    "FRAMES": "model",
    "ClaimInput": "model",
    "ClaimTrace": "model",
    "IntentEvidence": "model",
    "ModelError": "model",
    "RiskClaim": "model",
    "RiskDecision": "model",
    "RiskEvaluationResult": "model",
    "evidence_strings": "model",
    "ENTITIES": "patterns",
    "PATTERNS": "patterns",
    "RELATION_CATEGORY": "patterns",
    "relation_names": "patterns",
    "pattern_for_category": "patterns",
    "BLOCK": "decision",
    "REVIEW": "decision",
    "REQUIRE_EVIDENCE": "decision",
    "RULES": "decision",
    "DecisionRule": "decision",
    "action_for": "decision",
    "decide": "decision",
    "policy_table": "decision",
    "relations_covered": "decision",
    "rule": "decision",
    "rule_ids": "decision",
    "uncovered_relations": "decision",
    "PipelineConfig": "pipeline",
    "RiskEvaluationPipeline": "pipeline",
    "StageRecord": "pipeline",
    "DEFAULT": "pipeline",
    "evaluate": "pipeline",
    "replay": "replay",
    "replay_cases": "replay",
    "ReplayCase": "replay",
    "ReplayOutcome": "replay",
    "ReplayReport": "replay",
    "PHASES": "replay",
    "AdapterResult": "adapters",
    "ClaimAdapter": "adapters",
    "require_adapters": "adapters",
    "AttributionAdapter": "adapters.attribution",
    "IntentPatternAdapter": "adapters.intent_pattern",
    "SemanticAdapter": "adapters.semantic",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    if "." in module_name:
        package, _, attribute = module_name.partition(".")
        module = import_module(f".{package}", __name__)
        return getattr(module, attribute)
    return getattr(import_module(f".{module_name}", __name__), name)
