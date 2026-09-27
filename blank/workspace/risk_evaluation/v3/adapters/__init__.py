"""Adapters: a uniform interface over three layers, and nothing else.

Each adapter converts between the v3 model and one existing implementation. They
contain no detection logic of their own:

    AttributionAdapter    delegates to risk_evaluation.attribution
    IntentPatternAdapter  delegates to risk_evaluation.intent_patterns
    SemanticAdapter       delegates to semantic_evaluator_v2

The point of the uniform `evaluate(claim)` shape is that the pipeline can run
the adapters in a fixed order without knowing which layer is which - and that a
later phase can add or replace one without touching the pipeline. If an adapter
ever grows a rule of its own, the layer it wraps becomes two implementations of
the same thing, which is exactly the duplication this package exists to avoid.

Every adapter returns an `AdapterResult` carrying findings *and* evidence.
An adapter that returns a finding without evidence fails at construction:
Phase 8.5's constraint is that no judgement is reportable without a reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from ..model import ClaimInput, IntentEvidence, ModelError


class AdapterError(Exception):
    """Raised when an adapter cannot do its job."""


@dataclass(frozen=True, slots=True)
class AdapterResult:
    """What one adapter found in one claim."""

    adapter: str
    claim_id: str
    evidence: tuple[str, ...]
    categories: tuple[str, ...] = ()
    intents: tuple[IntentEvidence, ...] = ()
    speaker: str = ""
    stance: str = ""
    confidence: float = 0.0
    detail: Mapping[str, Any] = field(default_factory=dict)
    available: bool = True

    def __post_init__(self) -> None:
        if not self.adapter.strip():
            raise ModelError("an adapter result must name its adapter")
        if not self.claim_id.strip():
            raise ModelError("an adapter result must name its claim")
        if not self.evidence:
            raise ModelError(
                f"{self.adapter}/{self.claim_id}: an adapter may not return a "
                f"result without evidence"
            )
        object.__setattr__(self, "evidence", tuple(str(item) for item in self.evidence))
        object.__setattr__(self, "detail", dict(self.detail))

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "claim_id": self.claim_id,
            "available": self.available,
            "evidence": list(self.evidence),
            "categories": list(self.categories),
            "speaker": self.speaker,
            "stance": self.stance,
            "confidence": self.confidence,
            "intents": [item.as_dict() for item in self.intents],
            "detail": dict(sorted(self.detail.items(), key=lambda kv: kv[0])),
        }


@runtime_checkable
class ClaimAdapter(Protocol):
    """The uniform interface: one claim in, one evidenced result out."""

    name: str

    def evaluate(self, claim: ClaimInput) -> AdapterResult:  # pragma: no cover
        ...


def require_adapters(adapters: Sequence[ClaimAdapter]) -> tuple[ClaimAdapter, ...]:
    """Validate a pipeline's adapter list at construction."""

    if not adapters:
        raise AdapterError("a pipeline needs at least one adapter")
    names = [adapter.name for adapter in adapters]
    if len(names) != len(set(names)):
        raise AdapterError(f"adapter names must be unique, got {names}")
    for adapter in adapters:
        if not callable(getattr(adapter, "evaluate", None)):
            raise AdapterError(f"adapter {adapter.name!r} has no evaluate()")
    return tuple(adapters)
