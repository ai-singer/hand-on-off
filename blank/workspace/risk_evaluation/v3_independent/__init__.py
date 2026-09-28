"""Phase 8.9: independent annotation and realistic adversarial validation.

Phase 8.8 closed two capability gaps and measured them on a benchmark it wrote
itself. This package asks whether the result survives contact with text and labels
the evaluator's author did not produce.

    Independent dataset      benchmarks/risk/independent/v1   (300 cases)
        |
    Independent annotation   two blind annotators, Cohen's kappa per field
        |
    Frozen evaluator         evaluation_freeze_v3_2.json
        |
    Evaluation               per category, two confusion matrices
        |
    Error analysis           five classes, six written proposals

The evaluator is **frozen for the duration**. If the independent data exposes a
defect, this phase records a proposal and stops there; it does not fix it. The
constraint is enforced rather than promised: `freeze.guard()` re-hashes every frozen
source file and raises if one changed, and the phase's tests call it.

Provenance is the other half. The text was written by thirty agents other than the
one that wrote the capabilities, from a published sampling frame that contains no
evaluator vocabulary; the labels come from two further agents that never saw the
evaluator; the disagreements were adjudicated by a third. The prompts are published
verbatim in the dataset manifest, so "they never saw the evaluator" is checkable
rather than merely asserted.

What it is **not** is human annotation, and no number here is a real-world accuracy.
`docs/PHASE_8_9_INDEPENDENT_VALIDATION_REPORT.md` says so in its limitations section
and so does the dataset manifest.
"""

from __future__ import annotations

from typing import Any

from . import freeze

_EXPORTS: dict[str, str] = {
    # -- the dataset -------------------------------------------------------
    "BENCHMARK_ID": "dataset",
    "BENCHMARK_VERSION": "dataset",
    "BENCHMARK_DIR": "dataset",
    "PROVENANCE": "dataset",
    "load_records": "dataset",
    "load_manifest": "dataset",
    "dataset_digest": "dataset",
    "achieved_distribution": "dataset",
    # -- the frame ---------------------------------------------------------
    "build_frame": "frame",
    "load_slots": "frame",
    "quota_summary": "frame",
    "FrameDescriptor": "frame",
    "FrameError": "frame",
    "GROUP_SIZES": "frame",
    "CATEGORY_QUOTA": "frame",
    # -- agreement and adjudication ---------------------------------------
    "cohen_kappa": "agreement",
    "measure": "agreement",
    "band_for": "agreement",
    "AgreementReport": "agreement",
    "FieldAgreement": "agreement",
    "Disagreement": "agreement",
    "adjudicate": "adjudication",
    "assemble_rulings": "adjudication",
    "Ruling": "adjudication",
    # -- evaluation --------------------------------------------------------
    "predict": "evaluation",
    "score": "evaluation",
    "evaluate": "evaluation",
    "CaseResult": "evaluation",
    "Metrics": "evaluation",
    "CategoryMetrics": "evaluation",
    "primary_category": "evaluation",
    # -- analysis ----------------------------------------------------------
    "analyse": "adversarial",
    "classify": "adversarial",
    "Analysis": "adversarial",
    "Diagnosis": "adversarial",
    "PROPOSALS": "adversarial",
    "ERROR_KINDS": "adversarial",
    "build_coverage": "coverage",
    "CoverageMatrix": "coverage",
    # -- gates -------------------------------------------------------------
    "build_regression": "regression",
    "RegressionGate": "regression",
    "scan": "isolation",
    "IsolationReport": "isolation",
    # -- freeze ------------------------------------------------------------
    "FREEZE_PATH": "freeze",
    "PROPOSALS_PATH": "freeze",
    "guard": "freeze",
    "verify_freeze_v3_2": "freeze",
    "build_freeze_v3_2": "freeze",
    "frozen_source_digests": "freeze",
    "FreezeError": "freeze",
    "FreezeVerification": "freeze",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f".{module_name}", __name__), name)
