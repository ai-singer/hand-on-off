"""Independent validation of the Phase 8.5 architecture.

Phase 8.6 does not develop capability, tune rules or connect anything to
production. It asks one question:

    does the Phase 8.5 improvement hold on data that took no part in its
    development?

    cases.py       `independent_v1`: 100 cases written for this phase
    audit.py       exact, near, development overlap and label completeness
    freeze.py      `evaluation_freeze_v3.json`, taken before the run
    evaluation.py  blind prediction, then scoring, as separate steps
    claims.py      Phase 8.5's three claims, verified one at a time
    errors.py      every failure classified and explained

The pipeline is **not modified**. `risk_evaluation/v3` is frozen by hash before
the evaluation and verified after it, and the phase forbids adjusting a rule in
response to a result - which is what a mismatch would indicate had happened.

See `docs/PHASE_8_6_INDEPENDENT_VALIDATION_REPORT.md`.
"""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "BENCHMARK_ID": "cases",
    "BENCHMARK_VERSION": "cases",
    "CASES": "cases",
    "CONTAMINATED_CASE_IDS": "cases",
    "GROUP_NAMES": "cases",
    "MINIMUM_CASES": "cases",
    "TARGET_GROUP_SIZES": "cases",
    "ClaimLabel": "cases",
    "ValidationCase": "cases",
    "blind_records": "cases",
    "case_index": "cases",
    "category_counts": "cases",
    "dataset_payload": "cases",
    "decontaminated_cases": "cases",
    "group_cases": "cases",
    "group_sizes": "cases",
    "relation_counts": "cases",
    "write_dataset": "cases",
    "write_decontaminated": "cases",
    "AuditReport": "audit",
    "Finding": "audit",
    "audit": "audit",
    "historical_texts": "audit",
    "jaccard": "audit",
    "normalize_text": "audit",
    "write_report": "audit",
    "FreezeVerification": "freeze",
    "build_freeze": "freeze",
    "configuration_hash": "freeze",
    "dataset_hash": "freeze",
    "decision_policy_hash": "freeze",
    "evaluator_hash": "freeze",
    "load_freeze": "freeze",
    "taxonomy_hash": "freeze",
    "verify_freeze": "freeze",
    "write_freeze": "freeze",
    "Prediction": "evaluation",
    "ValidationMetrics": "evaluation",
    "join": "evaluation",
    "predict": "evaluation",
    "score": "evaluation",
    "write_metrics": "evaluation",
    "write_predictions": "evaluation",
    "ClaimVerdict": "claims",
    "SubClaim": "claims",
    "verify_attribution": "claims",
    "verify_claims": "claims",
    "verify_decision": "claims",
    "verify_intent": "claims",
    "ErrorAnalysis": "errors",
    "Diagnosis": "errors",
    "analyse": "errors",
    "diagnose": "errors",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f".{module_name}", __name__), name)
