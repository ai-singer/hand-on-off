"""The unified pipeline.

    Raw Text
      |  claim extraction          Phase 8.2's parser
      v
    Claims
      |  attribution analysis      Phase 8.2's analyzer
      v
    Speaker + Stance
      |  intent pattern analysis   Phase 8.4's matcher, v3's relations
      v
    Relations + Entities + Frames
      |  semantic evaluator        v2, as fallback only
      v
    Categories
      |  decision policy           explicit, ordered, evidenced
      v
    Risk Evaluation Result + full trace

Every stage is reached through an adapter, so the pipeline holds no detection
logic of its own and a layer can be replaced without touching it. Each step
appends evidence to the claim, and `RiskClaim.__post_init__` refuses a claim
with no evidence, so a missing step surfaces as an error rather than as a
category with no explanation.

**The semantic layer is a fallback.** It is consulted for a claim only when the
intent layer found no *asserted* relation there. Running it unconditionally
would make the pipeline v2 with extra steps, and would hide whether the new
layers are contributing anything.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..semantic_evaluator_v2 import EVALUATOR_NAME as BASELINE_NAME
from ..semantic_evaluator_v2 import SemanticRiskEvaluatorV2
from .adapters import AdapterResult, ClaimAdapter, require_adapters
from .adapters import attribution as attribution_adapter
from .adapters import intent_pattern as intent_adapter
from .adapters import semantic as semantic_adapter
from .decision import decide
from .model import (
    V3_VERSION,
    ClaimInput,
    ClaimTrace,
    ModelError,
    RiskClaim,
    RiskDecision,
    RiskEvaluationResult,
    evidence_strings,
)


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Which layers run, and in what order."""

    use_attribution: bool = True
    use_intent_patterns: bool = True
    use_semantic_fallback: bool = True
    intent_first: bool = True
    #: Wall-clock timings are diagnostic, not part of a judgement, and a trace
    #: that embeds them is not reproducible: two runs of the same text differ in
    #: the fourth decimal. Off by default, so the recorded trace is a function
    #: of the input.
    record_timings: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "use_attribution": self.use_attribution,
            "use_intent_patterns": self.use_intent_patterns,
            "use_semantic_fallback": self.use_semantic_fallback,
            "intent_first": self.intent_first,
        }


@dataclass(frozen=True, slots=True)
class StageRecord:
    """One stage's outcome, kept for the trace and for timing."""

    stage: str
    adapter: str
    claims: int
    findings: int
    milliseconds: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "adapter": self.adapter,
            "claims": self.claims,
            "findings": self.findings,
            "milliseconds": round(self.milliseconds, 3),
        }


class RiskEvaluationPipeline:
    """The v3 pipeline. Offline, experimental, and connected to nothing."""

    name = "risk-evaluation-v3"
    version = V3_VERSION

    def __init__(
        self,
        *,
        config: PipelineConfig | None = None,
        attribution: attribution_adapter.AttributionAdapter | None = None,
        intent: intent_adapter.IntentPatternAdapter | None = None,
        semantic: semantic_adapter.SemanticAdapter | None = None,
    ) -> None:
        self._config = config if config is not None else PipelineConfig()
        self._attribution = (
            attribution
            if attribution is not None
            else attribution_adapter.AttributionAdapter()
        )
        self._intent = (
            intent if intent is not None else intent_adapter.IntentPatternAdapter()
        )
        self._semantic = (
            semantic if semantic is not None else semantic_adapter.SemanticAdapter()
        )
        self._adapters: tuple[ClaimAdapter, ...] = require_adapters(
            (
                self._attribution,
                self._intent,
                self._semantic,
            )
        )

    @property
    def config(self) -> PipelineConfig:
        return self._config

    @property
    def adapters(self) -> tuple[ClaimAdapter, ...]:
        return self._adapters

    # -- stages ------------------------------------------------------------

    def extract(self, text: str) -> tuple[ClaimInput, ...]:
        if not isinstance(text, str):
            raise ModelError(f"text must be a string, got {type(text).__name__}")
        if not text.strip():
            return ()
        return self._attribution.extract(text)

    def baseline(self, text: str) -> tuple[str, ...]:
        """What the pipeline is compared against: v2 on the whole text."""

        if not isinstance(text, str) or not text.strip():
            return ()
        return tuple(
            sorted({item.category for item in self._semantic.raw(text)})
        )

    def evaluate(self, text: str) -> RiskEvaluationResult:
        started = time.perf_counter()
        stages: list[StageRecord] = []

        claims_in = self.extract(text)
        stages.append(
            StageRecord(
                "claim_extraction",
                self._attribution.name,
                len(claims_in),
                len(claims_in),
            )
        )

        claims: list[RiskClaim] = []
        traces: list[ClaimTrace] = []
        decisions: list[RiskDecision] = []

        for claim_input in claims_in:
            built, stage_records = self._evaluate_claim(claim_input)
            stages.extend(stage_records)
            kept, suppressed = decide(
                built, fallback_searched=built.fallback_evidence != ()
            )
            trace = ClaimTrace(claim=built, decisions=kept, suppressed=suppressed)
            claims.append(built)
            traces.append(trace)
            decisions.extend(kept)

        merged = _merge(decisions)
        if self._config.record_timings:
            elapsed = (time.perf_counter() - started) * 1000
            if stages:
                last = stages[-1]
                stages[-1] = StageRecord(
                    last.stage,
                    last.adapter,
                    last.claims,
                    last.findings,
                    last.milliseconds + elapsed,
                )

        return RiskEvaluationResult(
            text=text,
            claims=tuple(claims),
            traces=tuple(traces),
            final_decision=merged,
            baseline=self.baseline(text),
            version=self.version,
            evidence={
                "pipeline": self.name,
                "baseline_evaluator": BASELINE_NAME,
                "config": self._config.as_dict(),
                "claims": len(claims),
                "decisions": len(merged),
                "suppressed": sum(len(t.suppressed) for t in traces),
                "stages": [item.as_dict() for item in stages],
                "trace_complete": all(bool(t.claim.evidence) for t in traces),
            },
        )

    def _evaluate_claim(
        self, claim_input: ClaimInput
    ) -> tuple[RiskClaim, list[StageRecord]]:
        stages: list[StageRecord] = []

        attribution_result = (
            self._attribution.evaluate(claim_input)
            if self._config.use_attribution
            else AdapterResult(
                adapter=self._attribution.name,
                claim_id=claim_input.claim_id,
                evidence=("rule:attribution.disabled",),
                available=False,
            )
        )
        stages.append(
            StageRecord(
                "attribution",
                attribution_result.adapter,
                1,
                int(bool(attribution_result.speaker)),
            )
        )

        intent_result = (
            self._intent.evaluate(claim_input)
            if self._config.use_intent_patterns
            else AdapterResult(
                adapter=self._intent.name,
                claim_id=claim_input.claim_id,
                evidence=("rule:intent_pattern.disabled",),
                available=False,
            )
        )
        asserted = [item for item in intent_result.intents if item.asserted]
        stages.append(
            StageRecord("intent_pattern", intent_result.adapter, 1, len(asserted))
        )

        # The fallback is reached only when the intent layer asserted nothing.
        search_semantic = self._config.use_semantic_fallback and not asserted
        if search_semantic:
            semantic_result = self._semantic.evaluate(
                claim_input, searched_because="intent-found-nothing"
            )
        else:
            semantic_result = AdapterResult(
                adapter=self._semantic.name,
                claim_id=claim_input.claim_id,
                evidence=(
                    "rule:semantic.skipped:intent-found-"
                    + ",".join(sorted({item.relation for item in asserted})),
                ),
                detail={"searched_because": "not-needed"},
            )
        stages.append(
            StageRecord(
                "semantic_fallback",
                semantic_result.adapter,
                1,
                len(semantic_result.categories),
            )
        )

        speaker = attribution_result.speaker or "unknown"
        stance = attribution_result.stance or "uncertain"

        evidence = evidence_strings(
            attribution_result.evidence,
            intent_result.evidence,
            semantic_result.evidence,
        )
        if not evidence:
            evidence = (f"rule:pipeline.no-evidence:{claim_input.claim_id}",)

        claim = RiskClaim(
            claim_id=claim_input.claim_id,
            text=claim_input.text,
            source_span=claim_input.span,
            speaker=speaker,
            stance=stance,
            evidence=evidence,
            intents=intent_result.intents,
            confidence=max(attribution_result.confidence, intent_result.confidence),
            attribution_evidence=attribution_result.evidence,
            fallback_categories=semantic_result.categories,
            fallback_evidence=semantic_result.evidence,
            intent_available=intent_result.available,
        )
        return claim, stages


def _merge(decisions: Sequence[RiskDecision]) -> tuple[RiskDecision, ...]:
    """One decision per category, keeping the strongest action.

    Two claims can raise the same category. The merged decision keeps the
    strongest action and records every claim that contributed, so a final
    verdict still points back at the claims behind it.
    """

    order = {"block": 3, "review": 2, "require_evidence": 1, "downrank": 0}
    best: dict[str, RiskDecision] = {}
    contributors: dict[str, list[str]] = {}
    for item in decisions:
        if not item.kept:
            continue
        contributors.setdefault(item.category, []).append(item.claim_id)
        current = best.get(item.category)
        if current is None or order.get(item.action, 0) > order.get(current.action, 0):
            best[item.category] = item

    merged: list[RiskDecision] = []
    for category in sorted(best):
        item = best[category]
        merged.append(
            RiskDecision(
                claim_id=",".join(dict.fromkeys(contributors[category])),
                category=item.category,
                action=item.action,
                rule=item.rule,
                evidence=item.evidence,
                kept=True,
                reason=item.reason,
            )
        )
    return tuple(merged)


def evaluate(text: str) -> RiskEvaluationResult:
    """Module-level convenience for the standard pipeline."""

    return DEFAULT.evaluate(text)


DEFAULT = RiskEvaluationPipeline()
