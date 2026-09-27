"""Risk intent evaluation framework for Creator Agent instances.

    taxonomy  ->  evaluator  ->  RiskEvaluationResult  ->  risk constraints
                                                              |
                                                       quality gate (unchanged)

The framework defines what finance content risks are, a replaceable interface
for detecting them, a serializable result contract, and the evidence each
category requires. It changes no existing rule, gate, schema, workflow or
runtime behaviour. Today's only evaluator wraps the existing keyword rules and
exists so the current capability boundary can be measured rather than assumed.

Submodules are re-exported lazily (PEP 562): an eager import here would place
``risk_evaluation.benchmark`` in ``sys.modules`` before ``runpy`` executes it as
``__main__``, so ``python -m risk_evaluation.benchmark`` would run a second copy
of the module.
"""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "ADVERSARIAL": "benchmark",
    "BENCHMARK_CASES": "benchmark",
    "BENCHMARK_KINDS": "benchmark",
    "BenchmarkCase": "benchmark",
    "BenchmarkReport": "benchmark",
    "CaseOutcome": "benchmark",
    "ComparisonReport": "benchmark",
    "KEYWORD": "benchmark",
    "PARAPHRASE": "benchmark",
    "SAFE": "benchmark",
    "compare_evaluators": "benchmark",
    "run_benchmark": "benchmark",
    "DEFAULT_PLUGIN_MODULE_PATH": "evaluator",
    "KeywordRiskEvaluator": "evaluator",
    "RiskIntentEvaluator": "evaluator",
    "EvidenceRequirement": "evidence",
    "EvidenceStatus": "evidence",
    "assess_evidence": "evidence",
    "derivable_evidence": "evidence",
    "requirements_for": "evidence",
    "ACTIONS": "model",
    "SEVERITIES": "model",
    "RiskEvaluationError": "model",
    "RiskEvaluationResult": "model",
    "severity_effect": "model",
    "INTENT_PATTERNS": "semantic_evaluator",
    "NEGATION_WINDOW": "semantic_evaluator",
    "SIGNAL_PATTERNS": "semantic_evaluator",
    "SemanticRiskEvaluator": "semantic_evaluator",
    "SignalMatch": "semantic_evaluator",
    "detect_signals": "semantic_evaluator",
    "RISK_TAXONOMY": "taxonomy",
    "RiskCategory": "taxonomy",
    "categories_for_evaluator_category": "taxonomy",
    "category": "taxonomy",
    "category_names": "taxonomy",
    "FREEZE_PATH": "freeze",
    "FreezeStatus": "freeze",
    "build_baseline": "freeze",
    "decision_surface_hash": "freeze",
    "load_freeze": "freeze",
    "verify_freeze": "freeze",
    "write_freeze": "freeze",
    "ANNOTATION_FIELDS": "independent_benchmark",
    "INDEPENDENT_CASES": "independent_benchmark",
    "AnnotationCase": "independent_benchmark",
    "annotation_records": "independent_benchmark",
    "expected_distribution": "independent_benchmark",
    "group_counts": "independent_benchmark",
    "CaseResult": "validation",
    "CategoryMetrics": "validation",
    "ErrorFinding": "validation",
    "EvaluationMetrics": "validation",
    "ValidationReport": "validation",
    "classify_error": "validation",
    "run_validation": "validation",
    "BENCHMARK_EXPORTS": "benchmark_registry",
    "ANNOTATION_PROTOCOL": "benchmark_registry",
    "ANNOTATION_VERSION": "benchmark_registry",
    "BenchmarkRecord": "benchmark_registry",
    "BenchmarkRegistry": "benchmark_registry",
    "BenchmarkRegistryError": "benchmark_registry",
    "decontaminated_cases": "benchmark_registry",
    "dataset_hash": "benchmark_registry",
    "ContaminationFinding": "benchmark_audit",
    "ContaminationReport": "benchmark_audit",
    "NEAR_DUPLICATE_THRESHOLD": "benchmark_audit",
    "audit_all": "benchmark_audit",
    "audit_benchmark": "benchmark_audit",
    "audit_records": "benchmark_audit",
    "ChangedCase": "regression",
    "PRIMARY_METRIC": "regression",
    "RegressionError": "regression",
    "RegressionReport": "regression",
    "run_all": "regression",
    "run_regression": "regression",
    "write_baseline": "regression",
    "EvaluationFreezeError": "release_freeze",
    "build_freeze": "release_freeze",
    "evaluator_hash": "release_freeze",
    "load_evaluation_freeze": "release_freeze",
    "taxonomy_hash": "release_freeze",
    "verify_evaluation_freeze": "release_freeze",
    "write_evaluation_freeze": "release_freeze",
    # --- Phase 7.5: taxonomy v2, semantic-intent-v2, benchmark v3/v4 ---
    "ANNOTATION_VERSION_V2": "benchmark_registry",
    "ANNOTATION_PROTOCOL_V2": "benchmark_registry",
    "V3_ANNOTATION_FIELDS": "benchmark_v2",
    "AnnotationCaseV2": "benchmark_v2",
    "V3_CASES": "benchmark_v2",
    "case_index": "benchmark_v2",
    "decontaminated_v3_cases": "benchmark_v2",
    "v3_records": "benchmark_v2",
    "v4_records": "benchmark_v2",
    "AUTHOR_VOICE_CATEGORIES": "taxonomy_v2",
    "ATTRIBUTION_AGNOSTIC_CATEGORIES": "taxonomy_v2",
    "CATEGORY_PRECEDENCE": "taxonomy_v2",
    "CERTAINTY_LEVELS": "taxonomy_v2",
    "MARKET_CLAIM_CASES": "taxonomy_v2",
    "STATEMENT_SOURCES": "taxonomy_v2",
    "TAXONOMY_VERSION": "taxonomy_v2",
    "is_direct_prediction": "taxonomy_v2",
    "market_claim_case": "taxonomy_v2",
    "resolve_category_conflicts": "taxonomy_v2",
    "taxonomy_v2_payload": "taxonomy_v2",
    "AttributionAnalysis": "semantic_evaluator_v2",
    "CertaintyAnalysis": "semantic_evaluator_v2",
    "RiskAnalysisV2": "semantic_evaluator_v2",
    "SemanticRiskEvaluatorV2": "semantic_evaluator_v2",
    "V2_INTENT_PATTERNS": "semantic_evaluator_v2",
    "analyze_attribution": "semantic_evaluator_v2",
    "analyze_certainty": "semantic_evaluator_v2",
    "detect_reader_pressure": "semantic_evaluator_v2",
    "V2CaseResult": "validation_v2",
    "V2ComparisonReport": "validation_v2",
    "run_comparison": "validation_v2",
    "EvaluationFreezeV2Error": "release_freeze_v2",
    "FreezeV2Verification": "release_freeze_v2",
    "evaluator_v2_decision_surface": "release_freeze_v2",
    "verify_evaluation_freeze_v2": "release_freeze_v2",
    "MEASURED_BENCHMARK": "release_freeze_v2",
    "GOVERNED_BENCHMARK": "release_freeze_v2",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f".{module_name}", __name__), name)
