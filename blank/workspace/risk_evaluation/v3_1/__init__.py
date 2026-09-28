"""Phase 8.8: the v3.1 capability expansion.

Two capabilities, both added under the frozen evaluation constraints Phase 8.6
and 8.7 established:

    modal_prediction   is a probability statement a prediction?
    advice_boundary    is a directive aimed at the reader advice?

Neither is a keyword list. Each is a set of named signals and a declared verdict,
because the questions are about *how strongly* and *about what* something is said,
and a frame either matching or not cannot answer either. `The market will probably
crash next month.` and `The market will certainly crash next month.` contain the
same words in the same shape and are different findings, and only a strength
classification can say so.

The layers sit inside the intent stage of the Phase 8.5 pipeline, not beside it:

    Claim -> Attribution -> Intent -> Decision

`detectors` runs the two layers over a claim after the Phase 8.4 frames and either
amends a frame's finding, vetoes it on evidence, or adds one of its own. Claim-level
evidence is preserved throughout: every finding carries the signals behind it, and
every capability verdict is recorded on the claim whether or not it fired, so a
trace can show that a layer looked and declined rather than never looked.

The benchmark is `v3_1/benchmark`: 80 cases in three groups, synthetic, and **not
independent** - its provenance says so in the artifact itself. Group C carries
twenty cases whose labels predate this phase, so the capability is measured against
labels it could not have been tuned to.
"""

from __future__ import annotations

from typing import Any

from . import advice, certainty, detectors, modal, signals

_EXPORTS: dict[str, str] = {
    # -- capability core ----------------------------------------------------
    "CAPABILITIES": "signals",
    "SIGNAL_NAMES": "signals",
    "SIGNAL_FAMILIES": "signals",
    "PREDICTION_SIGNALS": "signals",
    "ADVICE_SIGNALS": "signals",
    "Signal": "signals",
    "SignalSet": "signals",
    "SignalError": "signals",
    "MODAL_PREDICTION": "signals",
    "ADVICE_BOUNDARY": "signals",
    "Carrier": "certainty",
    "Strength": "certainty",
    "CertaintyError": "certainty",
    "ORDER": "certainty",
    "weakest": "certainty",
    "strongest": "certainty",
    "rank": "certainty",
    "ModalDetection": "modal",
    "ModalError": "modal",
    "AdviceDetection": "advice",
    "AdviceError": "advice",
    "Detection": "detectors",
    "DetectionError": "detectors",
    "Veto": "detectors",
    # -- benchmark ----------------------------------------------------------
    "CASES": "benchmark",
    "PROVENANCE": "benchmark",
    "GROUP_NAMES": "benchmark",
    "SUBGROUP_SIZES": "benchmark",
    "MINIMUM_CASES": "benchmark",
    "CapabilityCase": "benchmark",
    "ClaimLabel": "benchmark",
    "benchmark_payload": "benchmark",
    # -- governance and measurement ----------------------------------------
    "audit": "audit",
    "AuditReport": "audit",
    "Phase88AuditReport": "audit",
    "PRE_PUBLICATION_FINDINGS": "audit",
    "FROZEN_PHASE_SOURCES": "audit",
    "evaluate": "evaluation",
    "score": "evaluation",
    "analyse": "evaluation",
    "ErrorAnalysis": "evaluation",
    "Metrics": "evaluation",
    "build_gate": "regression",
    "GateReport": "regression",
    "dataset_hash": "regression",
    "build_capability_freeze": "freeze",
    "verify_capability_freeze": "freeze",
    "verify_baseline": "freeze",
    "capability_hashes": "freeze",
    "capability_table_hash": "freeze",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f".{module_name}", __name__), name)
