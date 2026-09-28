"""Cached fixtures and record builders shared by the coverage test modules.

This module is deliberately *not* named `test*.py`, so `unittest discover` never
collects it. It exists for two reasons.

**Cost.** `analyzer.analyze()` runs the frozen evaluator over all 300 benchmark cases
and `generator.payload()` runs it over the 64 generated ones. Both are pure functions
of frozen inputs, so they are computed once per test process and shared.

**Honest defaults.** The builders below produce the smallest legal instance of each
record, so a test only states the field it is actually about.
"""

from __future__ import annotations

import functools
from typing import Any, Mapping, Sequence

from risk_evaluation.coverage import generator, pipeline, registry
from risk_evaluation.coverage import analyzer as analyzer_module
from risk_evaluation.coverage.model import (
    Evidence,
    FailureAnalysis,
    FailureRecord,
    GeneratedCase,
    CoverageCandidate,
)
from risk_evaluation.coverage.taxonomy import LEXICAL_GAP, SYNONYM_GAP


# --------------------------------------------------------------------------- fixtures


@functools.lru_cache(maxsize=1)
def analysis() -> FailureAnalysis:
    """The failure analysis of the Phase 8.9 benchmark, computed once."""

    return analyzer_module.analyze()


@functools.lru_cache(maxsize=1)
def metrics() -> Mapping[str, Any]:
    return analyzer_module.metrics()


@functools.lru_cache(maxsize=1)
def summary() -> Mapping[str, Any]:
    return analyzer_module.summary(analysis())


@functools.lru_cache(maxsize=1)
def generated() -> tuple[GeneratedCase, ...]:
    return generator.generate()


@functools.lru_cache(maxsize=1)
def generated_payload() -> Mapping[str, Any]:
    return generator.payload(generated())


@functools.lru_cache(maxsize=1)
def candidates() -> tuple[CoverageCandidate, ...]:
    return registry.build(analysis(), generated())


@functools.lru_cache(maxsize=1)
def registry_report() -> registry.RegistryReport:
    pending, rejected = registry.partition(candidates())
    return registry.RegistryReport(pending=pending, rejected=rejected, accepted=())


@functools.lru_cache(maxsize=1)
def registry_payload() -> Mapping[str, Any]:
    return registry_report().as_dict()


# --------------------------------------------------------------------------- builders


def evidence(name: str, kind: str = "direct", detail: str | None = None) -> Evidence:
    return Evidence(
        name=name,
        detail=detail if detail is not None else f"{name} was observed",
        kind=kind,
    )


def failure_record(**overrides: Any) -> FailureRecord:
    """One minimal, legal failure record with individual fields overridable."""

    base: dict[str, Any] = {
        "case_id": "IND-0001",
        "input_text": "Returns are assured.",
        "expected": ("financial_guarantee",),
        "actual": (),
        "failure_type": LEXICAL_GAP,
        "evidence": (evidence("no_hook_at_all", "inferred"),),
        "required_evidence": ("no_hook_at_all",),
    }
    base.update(overrides)
    return FailureRecord(**base)


def failure_analysis(records: Sequence[FailureRecord], cases: int | None = None) -> FailureAnalysis:
    return FailureAnalysis(
        cases=len(records) if cases is None else cases,
        failures=tuple(records),
    )


def generated_case(**overrides: Any) -> GeneratedCase:
    base: dict[str, Any] = {
        "case_id": "GEN-R1-TEST-0001",
        "text": "Returns are assured.",
        "expected_categories": ("financial_guarantee",),
        "generation_rule": "template:TPL-GUAR-COPULAR:axis:guarantee_predicate:assure",
        "generation_reason": "Guide v2 section 7: an outcome made unconditional.",
        "failure_type": SYNONYM_GAP,
        "risk_category": "financial_guarantee",
        "parent_case": "",
    }
    base.update(overrides)
    return GeneratedCase(**base)


def candidate(**overrides: Any) -> CoverageCandidate:
    base: dict[str, Any] = {
        "candidate_id": "CAND-R1-0001",
        "source_case": "IND-0001",
        "failure_type": SYNONYM_GAP,
        "proposal": "extend the movement_direction axis by adding zoomy",
        "risk_category": "market_prediction",
        "expected_impact": "would give 2 failing case(s) the vocabulary they lack",
        "covers_cases": ("IND-0001", "IND-0002"),
        "additions": ("zoomy",),
    }
    base.update(overrides)
    return CoverageCandidate(**base)


def pipeline_artifacts(root: Any) -> dict[str, Any]:
    """Every file a writing pipeline run produced under `root`, by relative name."""

    from pathlib import Path

    directory = Path(root)
    return {
        str(path.relative_to(directory)).replace("\\", "/"): path
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


__all__ = [
    "analysis",
    "metrics",
    "summary",
    "generated",
    "generated_payload",
    "candidates",
    "registry_report",
    "registry_payload",
    "evidence",
    "failure_record",
    "failure_analysis",
    "generated_case",
    "candidate",
    "pipeline_artifacts",
    "pipeline",
]
