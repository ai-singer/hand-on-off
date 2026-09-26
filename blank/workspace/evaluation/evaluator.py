"""Domain-neutral quality checks used by the reference workflow."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from core.models import RawSource


def evaluate_distillation_artifact(
    signals: Mapping[str, Sequence[Mapping[str, Any]]],
    sources: Sequence[RawSource],
) -> dict[str, Any]:
    populated = [name for name, values in signals.items() if values]
    referenced = {
        source_id
        for values in signals.values()
        for item in values
        for source_id in _source_ids(item)
    }
    coverage = len(referenced) / len(sources) if sources else 0.0
    score = round((len(populated) / 4 * 0.5) + (coverage * 0.5), 3)
    return {
        "score": score,
        "checks": {
            "populated_signal_families": len(populated),
            "source_reference_coverage": round(coverage, 3),
        },
        "passed": score >= 0.5,
    }


def evaluate_pipeline_output(
    artifact: Mapping[str, Any], generated_output: Any | None
) -> dict[str, Any]:
    blocking = [
        item
        for item in artifact.get("risk_constraints", [])
        if item.get("severity") == "block"
    ]
    common_passed = bool(
        artifact.get("evaluation_result", {}).get("common", {}).get("passed")
    )
    domain_result = artifact.get("evaluation_result", {}).get("domain", {})
    domain_passed = bool(domain_result.get("passed", False))
    passed = common_passed and domain_passed and not blocking
    return {
        "passed": passed,
        "blocking_risk_count": len(blocking),
        "common_evaluation_passed": common_passed,
        "domain_evaluation_passed": domain_passed,
        "generation_adapter_invoked": generated_output is not None,
        "status": "pass" if passed else "review_required",
    }


def _source_ids(item: Mapping[str, Any]) -> list[str]:
    direct = item.get("source_ids", [])
    evidence = [
        ref.get("source_id")
        for ref in item.get("evidence_refs", [])
        if isinstance(ref, dict) and ref.get("source_id")
    ]
    return [str(value) for value in [*direct, *evidence] if value]
