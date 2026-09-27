"""Adversarial risk discovery: generated attacks against the risk evaluator.

The framework is **offline**. It generates text that tries to make a risk slip
past the evaluator, runs the existing evaluator over it, and records what got
through. Nothing here is wired into production, and nothing here changes the
evaluator: the point is to find out where the evaluator is weak, not to hide it.

    generator  ->  cases  ->  evaluator_bridge  ->  failure_repository
                                                          |
                                                 regression candidates

See `docs/PHASE_8_1_ADVERSARIAL_RISK_DISCOVERY_REPORT.md`.
"""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "AdversarialCase": "case",
    "case_id_for": "case",
    "detect_duplicates": "case",
    "normalize_text": "case",
    "AttackStrategy": "strategies",
    "STRATEGIES": "strategies",
    "StrategySpec": "strategies",
    "strategy_spec": "strategies",
    "DetectionResult": "evaluator_bridge",
    "evaluate_case": "evaluator_bridge",
    "evaluate_cases": "evaluator_bridge",
    "false_positives": "evaluator_bridge",
    "misses": "evaluator_bridge",
    "AdversarialRiskGenerator": "generator",
    "adversarial_records": "generator",
    "attack_counts": "generator",
    "control_counts": "generator",
    "default_cases": "generator",
    "summarise": "generator",
    "FailureRecord": "failure_repository",
    "FailureRepository": "failure_repository",
    "FAILURE_ROOT": "failure_repository",
    "DiscoveryRun": "failure_repository",
    "failure_id_for": "failure_repository",
    "record_from": "failure_repository",
    "regression_candidates": "failure_repository",
    "run_discovery": "failure_repository",
    "write_candidates": "failure_repository",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f".{module_name}", __name__), name)
