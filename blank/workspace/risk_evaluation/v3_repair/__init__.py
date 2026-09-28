"""Phase 8.7 targeted repair layers, over the frozen Phase 8.2 and 8.4 packages.

Phase 8.6 validated v3 independently and confirmed three defects: inflected
movement verbs were invisible to the prediction frames, a guarantee's negation
had one undifferentiated result where three are needed, and the attribution layer
could not say who a reported statement came from or whether the source could be
checked. Phase 8.7 repairs them.

The repairs live here rather than inside the layers they correct, because
`risk_evaluation/attribution/` (Phase 8.2) and `risk_evaluation/intent_patterns/`
(Phase 8.4) are out of scope for this phase. Each module is a refinement over a
verdict those layers have already taken:

    negation     resolves the matcher's `negated` boolean into a scope
    sources      types the source a statement is reported through
    rejection    finds rejections the Phase 8.2 cue table does not carry
    attribution  applies the last three to Phase 8.2's speaker and stance
    freeze       the Phase 8.7 freeze, alongside the one it supersedes
    regression   the five-set before/after/fixed/broken suite

Nothing here imports `risk_evaluation.v3`; the dependency runs one way, from the
v3 pipeline into these modules, so a repair can be read without reading the
architecture it repairs. `regression` is the one exception and it is deliberate:
its whole job is to run the pipeline over historical sets, so it imports the
pipeline rather than the pipeline importing it.
"""

from __future__ import annotations

from typing import Any

from . import attribution, negation, rejection, sources
from .attribution import Refinement
from .attribution import refine as refine_attribution
from .negation import LOCAL, POSITIVE, PROPOSITIONAL, SCOPES, NegationScope
from .negation import classify as classify_negation
from .rejection import RejectionFinding
from .rejection import detect as detect_rejection
from .sources import SOURCE_TYPES, SourceFinding
from .sources import detect as detect_source

#: Names that live in `freeze` and `regression`. Both are imported lazily: the
#: classification layers above are pure and a caller reading one of them should
#: not pay for the regression suite, which runs the pipeline over 200 cases.
_EXPORTS: dict[str, str] = {
    "FREEZE_PATH": "freeze",
    "FREEZE_SCHEMA_VERSION": "freeze",
    "REPAIRS": "freeze",
    "REPAIR_MODULES": "freeze",
    "RepairFreezeError": "freeze",
    "RepairFreezeVerification": "freeze",
    "build_repair_freeze": "freeze",
    "load_repair_freeze": "freeze",
    "repair_hash": "freeze",
    "repair_hashes": "freeze",
    "table_hash": "freeze",
    "verify_repair_freeze": "freeze",
    "write_repair_freeze": "freeze",
    "BASELINE_PATH": "regression",
    "REPORT_PATH": "regression",
    "SET_NAMES": "regression",
    "TRANSITIONS": "regression",
    "CaseRecord": "regression",
    "RegressionError": "regression",
    "RegressionReport": "regression",
    "SetSummary": "regression",
    "baseline_provenance": "regression",
    "build_regression": "regression",
    "load_baseline": "regression",
    "run": "regression",
    "summarise": "regression",
    "write_report": "regression",
}

__all__ = sorted(
    {
        "LOCAL",
        "POSITIVE",
        "PROPOSITIONAL",
        "SCOPES",
        "SOURCE_TYPES",
        "NegationScope",
        "Refinement",
        "RejectionFinding",
        "SourceFinding",
        "attribution",
        "classify_negation",
        "detect_rejection",
        "detect_source",
        "negation",
        "refine_attribution",
        "rejection",
        "sources",
        *_EXPORTS,
    }
)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f".{module_name}", __name__), name)
