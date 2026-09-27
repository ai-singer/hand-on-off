"""Attribution-aware risk evaluation experiment.

An **offline experiment**. It asks one question: does knowing who is speaking
improve the risk evaluator's judgement about citations, rejections, attribution
and claim-level risk?

    Baseline     semantic_evaluator_v2(text)
    Experiment   AttributionAnalyzer -> per-claim semantic_evaluator_v2 -> merge

`semantic_evaluator_v2` is not modified, not wrapped and not replaced. It is
called, and both results are kept so a comparison never has to re-run anything.
Nothing here is registered in the runtime, imported by production code, or
connected to the Quality Gate.

    text
      |  AttributionAnalyzer        claims with speaker and stance
      v
    claims
      |  semantic_evaluator_v2      once per claim, unmodified
      v
    claim level detections
      |  decision policy            R1 raise, R2 and R3 suppress
      v
    AttributionAwareResult          claims, claim_results, final_decision, evidence

See `docs/PHASE_8_3_ATTRIBUTION_AWARE_EVALUATION_REPORT.md`.
"""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "AttributionAwareEvaluator": "evaluator",
    "AttributionAwareResult": "evaluator",
    "AUTHORIAL_EVALUATOR": "evaluator",
    "DEFAULT_EVALUATOR": "evaluator",
    "EXPERIMENT_NAME": "evaluator",
    "EXPERIMENT_VERSION": "evaluator",
    "attribution_aware": "evaluator",
    "categories_of": "evaluator",
    "compare_policies": "evaluator",
    "AUTHORIAL": "decision",
    "POLICIES": "decision",
    "STRICT": "decision",
    "ClaimDecision": "decision",
    "DecisionSummary": "decision",
    "R1_AUTHOR_ENDORSED": "decision",
    "R2_THIRD_PARTY_QUOTED": "decision",
    "R3_AUTHOR_REJECTED": "decision",
    "R4_ATTRIBUTION_AGNOSTIC": "decision",
    "R5_NOT_AUTHORIAL": "decision",
    "R6_BASELINE_VERDICT": "decision",
    "decide_claim": "decision",
    "is_attribution_agnostic": "decision",
    "is_author_rejection": "decision",
    "is_third_party_quotation": "decision",
    "merge_results": "decision",
    "raises_risk_weight": "decision",
    "summarise": "decision",
    "ATTRIBUTION_GROUPS": "cases",
    "DATASET_VERSION": "cases",
    "EXPERIMENT_CASES": "cases",
    "REPLAY_CASES": "cases",
    "REQUIRED_GROUP_SIZES": "cases",
    "ExperimentCase": "cases",
    "case_index": "cases",
    "dataset_payload": "cases",
    "group_cases": "cases",
    "group_sizes": "cases",
    "write_dataset": "cases",
    "CaseComparison": "comparison",
    "ComparisonReport": "comparison",
    "EvaluatorMetrics": "comparison",
    "compare_case": "comparison",
    "policy_sensitivity": "comparison",
    "replay_report": "comparison",
    "run_comparison": "comparison",
    "write_report": "comparison",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f".{module_name}", __name__), name)
