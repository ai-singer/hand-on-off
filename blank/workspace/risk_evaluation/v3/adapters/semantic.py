"""Semantic adapter: `semantic_evaluator_v2` as a fallback, behind the interface.

The phase is explicit that the semantic evaluator is a **fallback**, not a
replacement for the first two layers. The pipeline therefore consults it only
for claims the intent layer produced no relation for, and this adapter reports
which of those two situations it is in via `searched_because`.

`semantic_evaluator_v2` is called, never modified, never subclassed, and never
wrapped in anything that changes what it returns. The adapter's whole job is
protocol conversion: `RiskEvaluationResult` objects in, `AdapterResult` out.
"""

from __future__ import annotations

from typing import Any

from ...semantic_evaluator_v2 import EVALUATOR_NAME, SemanticRiskEvaluatorV2
from ..model import ClaimInput, evidence_strings
from . import AdapterError, AdapterResult


name = "semantic"


class SemanticAdapter:
    """v2's categories, used as the pipeline's fallback layer."""

    name = name

    def __init__(self, *, evaluator: SemanticRiskEvaluatorV2 | None = None) -> None:
        self._evaluator = (
            evaluator if evaluator is not None else SemanticRiskEvaluatorV2()
        )

    @property
    def evaluator_name(self) -> str:
        return EVALUATOR_NAME

    def raw(self, text: str):
        """The evaluator's own results, for callers that need them unchanged."""

        return self._evaluator.evaluate_text(text)

    def evaluate(
        self, claim: ClaimInput, *, searched_because: str = "fallback"
    ) -> AdapterResult:
        if not isinstance(claim, ClaimInput):
            raise AdapterError("semantic.evaluate expects a ClaimInput")

        results = self.raw(claim.text)
        categories = tuple(sorted({item.category for item in results}))
        evidence = [
            f"{item.category}:{item.evaluator}:confidence={item.confidence}"
            for item in results
        ]
        if not evidence:
            evidence.append(f"rule:semantic.no-category:{claim.claim_id}")

        return AdapterResult(
            adapter=self.name,
            claim_id=claim.claim_id,
            categories=categories,
            evidence=evidence_strings(
                evidence, (f"rule:semantic.searched-because:{searched_because}",)
            ),
            confidence=max((item.confidence for item in results), default=0.0),
            detail={
                "searched_because": searched_because,
                "evaluator": EVALUATOR_NAME,
                "results": [item.as_dict() for item in results],
            },
        )


def evaluate(claim: ClaimInput, *, searched_because: str = "fallback") -> AdapterResult:
    return DEFAULT.evaluate(claim, searched_because=searched_because)


DEFAULT = SemanticAdapter()
