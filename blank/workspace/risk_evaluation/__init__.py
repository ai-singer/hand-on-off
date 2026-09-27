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
    "BENCHMARK_CASES": "benchmark",
    "BenchmarkCase": "benchmark",
    "BenchmarkReport": "benchmark",
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
    "RISK_TAXONOMY": "taxonomy",
    "RiskCategory": "taxonomy",
    "categories_for_evaluator_category": "taxonomy",
    "category": "taxonomy",
    "category_names": "taxonomy",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f".{module_name}", __name__), name)
