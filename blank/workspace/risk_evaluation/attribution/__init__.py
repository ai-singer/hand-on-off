"""Attribution analysis: who is speaking, and what the author does with it.

Phase 8.1 found a structural defect, not a vocabulary gap: `semantic_evaluator_v2`
decides attribution once for a whole text, so an unrelated attribution anywhere
in a passage withdrew every author-voice category in it. A guarantee in the
second sentence disappeared because an economist was quoted in the first.

This package separates the two questions that were collapsed into one field:

    speaker   who is speaking       author | third_party | unknown
    stance    what the author does  endorsed | quoted | rejected | uncertain

It is a prototype. It does not modify `semantic_evaluator_v2`, does not touch
`taxonomy_v2`, and is not connected to the Quality Gate or the runtime. Nothing
here changes a risk verdict; it only produces the structure a future evaluator
would need in order to stop making the mistake Phase 8.1 found.

    text -> ClaimParser -> SpeakerDetector -> StanceDetector -> AttributionResult

See `docs/PHASE_8_2_ATTRIBUTION_LAYER_REPORT.md`.
"""

from __future__ import annotations

from typing import Any

_EXPORTS = {
    "AUTHORISING_STANCES": "model",
    "AttributionError": "model",
    "AttributionResult": "model",
    "Claim": "model",
    "DISTANCING_STANCES": "model",
    "SPEAKERS": "model",
    "STANCES": "model",
    "summarise": "model",
    "EvidenceLog": "evidence",
    "EvidenceMark": "evidence",
    "empty_log": "evidence",
    "ClaimParser": "claim_parser",
    "ClaimParserError": "claim_parser",
    "ClaimSegment": "claim_parser",
    "claim_ids": "claim_parser",
    "CONTRASTIVE_MARKERS": "claim_parser",
    "StanceDetector": "stance_detector",
    "StanceVerdict": "stance_detector",
    "ENDORSED": "stance_detector",
    "QUOTED": "stance_detector",
    "REJECTED": "stance_detector",
    "UNCERTAIN": "stance_detector",
    "AttributionAnalyzer": "analyzer",
    "ClaimView": "analyzer",
    "SpeakerDetector": "analyzer",
    "SpeakerVerdict": "analyzer",
    "analyze": "analyzer",
    "authorial_text": "analyzer",
    "claim_views": "analyzer",
    "to_statement_source": "analyzer",
    "ANNOTATION_CASES": "evaluation",
    "AnnotationRow": "evaluation",
    "AttributionMetrics": "evaluation",
    "evaluate_attribution": "evaluation",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f".{module_name}", __name__), name)
