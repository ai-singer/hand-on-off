"""Relation-level intent patterns: the `financial_guarantee` repair.

Phase 8.1 found that `This return is guaranteed.` is invisible to the risk
evaluator while `This is a guaranteed return.` is not. Phase 8.3 confirmed it:
the miss is the single largest defect shared by every evaluator built so far,
and it is `block` severity.

The cause is not a missing word. It is that the old rule encodes a fixed word
order:

    \\bguaranteed\\s+(?:return|returns|profit|...)\\b

The same relation is realised at least four other ways in English, and none of
them was matched. This package replaces the word-order rule with a relation rule
built on entities and frames:

    EntityType   RETURN, CAPITAL, VALUE, OUTCOME, GUARANTOR
    Relation     GUARANTEE, RISK_REMOVED
    Frame        active, passive, copular, attributive, nominal

    text -> frames -> role bindings -> PatternMatch(fired, negated, hedged)

Negation and hedging are properties of a match rather than filters, so a rule
that correctly declines to fire is visible as `scanned` rather than looking
identical to a rule that never ran.

It is a **prototype**. It does not modify `semantic_evaluator_v2`, is not
registered as an evaluator, and is imported by nothing outside its own tests.
See `docs/PHASE_8_4_INTENT_PATTERN_REPAIR_REPORT.md`.
"""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "ACTIVE": "model",
    "ATTRIBUTIVE": "model",
    "COPULAR": "model",
    "NOMINAL": "model",
    "PASSIVE": "model",
    "FRAME_KINDS": "model",
    "EntityLexicon": "model",
    "EntityMatch": "model",
    "EntityType": "model",
    "Frame": "model",
    "FrameMatch": "model",
    "IntentPattern": "model",
    "PatternError": "model",
    "PatternMatch": "model",
    "PatternSet": "model",
    "Relation": "model",
    "frame_kinds_covered": "model",
    "HEDGE_MARKERS": "matcher",
    "NEGATION_WINDOW": "matcher",
    "NEGATORS": "matcher",
    "RelationMatcher": "matcher",
    "MatcherError": "matcher",
    "frame_coverage": "matcher",
    "hedge_for": "matcher",
    "is_negated": "matcher",
    "require_frame_kinds": "matcher",
    "sentence_span": "matcher",
    "ENTITIES": "financial_guarantee",
    "FINANCIAL_GUARANTEE": "financial_guarantee",
    "GUARANTEE": "financial_guarantee",
    "GUARANTORS": "financial_guarantee",
    "PATTERNS": "financial_guarantee",
    "RISK_REMOVED": "financial_guarantee",
    "guarantee_frames": "financial_guarantee",
    "BENCHMARK_CASES": "evaluation",
    "BOUNDARY": "evaluation",
    "NEGATIVE": "evaluation",
    "POSITIVE": "evaluation",
    "PatternBenchmarkCase": "evaluation",
    "PatternMetrics": "evaluation",
    "attribution_combination": "evaluation",
    "benchmark_payload": "evaluation",
    "case_index": "evaluation",
    "compare_with_old": "evaluation",
    "evaluate_patterns": "evaluation",
    "group_cases": "evaluation",
    "run_benchmark": "evaluation",
    "write_benchmark": "evaluation",
    "write_comparison": "evaluation",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f".{module_name}", __name__), name)
