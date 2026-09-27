"""Attribution-aware evaluator: an experiment, not a replacement.

    text
      |
      v  AttributionAnalyzer        claims with speaker and stance
    claims
      |
      v  semantic_evaluator_v2      run per claim, unmodified
    claim-level detections
      |
      v  decision policy            keep, drop, or elevate
    AttributionAwareResult

`semantic_evaluator_v2` is **not modified and not wrapped**. It is called, once
per claim, exactly as a caller would call it. The baseline result and the
experimental result are both returned, so a comparison never has to re-run
anything and the baseline output cannot be lost.

This module is not registered anywhere, is imported by nothing in the runtime,
and does not replace `semantic_evaluator_v2`. It exists to answer one question:
does knowing who is speaking improve the evaluator's judgement about citations,
rejections, attribution and claim-level risk?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..attribution.analyzer import AttributionAnalyzer, analyze
from ..attribution.model import AttributionResult, Claim
from ..model import RiskEvaluationResult
from ..semantic_evaluator_v2 import EVALUATOR_NAME as BASELINE_NAME
from ..semantic_evaluator_v2 import SemanticRiskEvaluatorV2
from .decision import (
    AUTHORIAL,
    POLICIES,
    STRICT,
    ClaimDecision,
    DecisionSummary,
    decide_claim,
    merge_results,
    summarise,
)


EXPERIMENT_NAME = "attribution-aware-experiment"
EXPERIMENT_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class AttributionAwareResult:
    """Everything the experiment produced for one text."""

    text: str
    attribution: AttributionResult
    claim_results: Mapping[str, tuple[RiskEvaluationResult, ...]]
    claim_decisions: tuple[ClaimDecision, ...]
    final_decision: tuple[RiskEvaluationResult, ...]
    baseline: tuple[RiskEvaluationResult, ...]
    policy: str = STRICT
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "claim_results",
            {str(k): tuple(v) for k, v in self.claim_results.items()},
        )
        object.__setattr__(self, "evidence", dict(self.evidence))

    @property
    def claims(self) -> tuple[Claim, ...]:
        return self.attribution.claims

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({item.category for item in self.final_decision}))

    @property
    def baseline_categories(self) -> tuple[str, ...]:
        return tuple(sorted({item.category for item in self.baseline}))

    @property
    def flagged(self) -> bool:
        return bool(self.final_decision)

    @property
    def baseline_flagged(self) -> bool:
        return bool(self.baseline)

    @property
    def changed(self) -> bool:
        """Did the attribution layer change the verdict at all?"""

        return self.categories != self.baseline_categories

    @property
    def summary(self) -> DecisionSummary:
        return summarise(self.claim_decisions)

    def decision_for(self, claim_id: str) -> ClaimDecision:
        for item in self.claim_decisions:
            if item.claim_id == claim_id:
                return item
        raise KeyError(claim_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "policy": self.policy,
            "baseline_categories": list(self.baseline_categories),
            "experiment_categories": list(self.categories),
            "changed": self.changed,
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "speaker": claim.speaker,
                    "stance": claim.stance,
                    "is_authorial": claim.is_authorial,
                    "evidence": list(claim.evidence),
                }
                for claim in self.claims
            ],
            "claim_decisions": [item.as_dict() for item in self.claim_decisions],
            "summary": self.summary.as_dict(),
            "evidence": dict(sorted(self.evidence.items(), key=lambda kv: kv[0])),
        }

    def render(self) -> str:
        lines = [
            f"text        : {self.text}",
            f"policy      : {self.policy}",
            f"baseline    : {list(self.baseline_categories)}",
            f"experiment  : {list(self.categories)}",
        ]
        for item in self.claim_decisions:
            lines.append(f"  {item.render()}")
        return "\n".join(lines)


class AttributionAwareEvaluator:
    """Runs the attribution layer, then the unmodified baseline per claim."""

    name = EXPERIMENT_NAME
    version = EXPERIMENT_VERSION

    def __init__(
        self,
        *,
        baseline: SemanticRiskEvaluatorV2 | None = None,
        analyzer: AttributionAnalyzer | None = None,
        policy: str = STRICT,
        source_ids: Sequence[str] = (),
    ) -> None:
        if policy not in POLICIES:
            raise ValueError(f"policy must be one of {POLICIES}, got {policy!r}")
        self._baseline = baseline if baseline is not None else SemanticRiskEvaluatorV2()
        self._analyzer = analyzer if analyzer is not None else AttributionAnalyzer()
        self._policy = policy
        self._source_ids = tuple(str(value) for value in source_ids)

    @property
    def policy(self) -> str:
        return self._policy

    @property
    def baseline_evaluator(self) -> str:
        return BASELINE_NAME

    def baseline_for(self, text: str) -> tuple[RiskEvaluationResult, ...]:
        """The unmodified evaluator's verdict on the whole text."""

        return tuple(self._baseline.evaluate_text(text))

    def evaluate_text(self, text: str) -> AttributionAwareResult:
        return self.evaluate(text)

    def evaluate(self, text: str) -> AttributionAwareResult:
        if not isinstance(text, str) or not text.strip():
            from ..model import RiskEvaluationError

            raise RiskEvaluationError("evaluate requires non-empty text")

        baseline = self.baseline_for(text)
        attribution = self._analyzer.analyze(text)

        claim_results: dict[str, tuple[RiskEvaluationResult, ...]] = {}
        decisions: list[ClaimDecision] = []
        for claim in attribution.claims:
            results = tuple(self._baseline.evaluate_text(claim.text))
            claim_results[claim.claim_id] = results
            decisions.append(
                decide_claim(
                    claim,
                    [item.category for item in results],
                    policy=self._policy,
                )
            )

        final = merge_results(decisions, claim_results)
        summary = summarise(decisions)

        return AttributionAwareResult(
            text=text,
            attribution=attribution,
            claim_results=claim_results,
            claim_decisions=tuple(decisions),
            final_decision=final,
            baseline=baseline,
            policy=self._policy,
            evidence={
                "evaluator": self.name,
                "version": self.version,
                "baseline_evaluator": BASELINE_NAME,
                "policy": self._policy,
                "claims": len(attribution.claims),
                "baseline_categories": sorted({r.category for r in baseline}),
                "dropped_categories": list(summary.dropped_categories),
                "suppressed_claims": summary.suppressed_claims,
                "weight_raised": summary.weight_raised,
                "attribution_mixed": bool(attribution.summary.get("mixed")),
                "attribution_has_rejection": bool(
                    attribution.summary.get("has_rejection")
                ),
            },
        )


#: Standard instances for callers that need no configuration.
DEFAULT_EVALUATOR = AttributionAwareEvaluator()
AUTHORIAL_EVALUATOR = AttributionAwareEvaluator(policy=AUTHORIAL)


def attribution_aware(text: str, *, policy: str = STRICT) -> AttributionAwareResult:
    """Module-level convenience, as the phase's sketch uses it."""

    evaluator = DEFAULT_EVALUATOR if policy == STRICT else AttributionAwareEvaluator(policy=policy)
    return evaluator.evaluate(text)


def compare_policies(text: str) -> Mapping[str, AttributionAwareResult]:
    """Both readings of R1, for the same text."""

    return {
        policy: AttributionAwareEvaluator(policy=policy).evaluate(text)
        for policy in POLICIES
    }


def categories_of(results: Sequence[RiskEvaluationResult]) -> tuple[str, ...]:
    return tuple(sorted({item.category for item in results}))
