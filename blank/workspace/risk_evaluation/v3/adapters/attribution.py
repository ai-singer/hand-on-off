"""Attribution adapter: Phase 8.2's layer, behind the uniform interface.

Two jobs, both pure delegation:

* `extract_claims(text)` returns the claim spans the pipeline works on. Phase
  8.2's `ClaimParser` already does this, and re-splitting here would give the
  pipeline a different notion of "claim" from the one its own attribution
  answers are about.
* `evaluate(claim)` returns the speaker and stance for one claim.

`evaluate` re-runs the Phase 8.2 analyzer over the **source text**, not over the
claim text. That is not an optimisation to skip: stance is not a per-sentence
question. `Analysts expect growth. However, we disagree.` labels the *first*
claim `rejected` because of a connective in the second, and running the analyzer
on the claim alone would silently lose that. Results are cached per source text,
so a text with n claims runs the analyzer once.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Sequence

from ...attribution import analyze
from ...attribution.claim_parser import ClaimParser
from ...attribution.model import AttributionResult
from ..model import ClaimInput, ModelError, evidence_strings
from . import AdapterError, AdapterResult


name = "attribution"


@lru_cache(maxsize=256)
def _analyze_cached(text: str) -> AttributionResult:
    return analyze(text)


def clear_cache() -> None:
    _analyze_cached.cache_clear()


def extraction(text: str) -> AttributionResult:
    """The full Phase 8.2 result, cached per source text."""

    if not isinstance(text, str):
        raise AdapterError(f"text must be a string, got {type(text).__name__}")
    return _analyze_cached(text)


def extract_claims(text: str) -> tuple[ClaimInput, ...]:
    """Claim spans for the pipeline, from the Phase 8.2 parser."""

    result = extraction(text)
    claims: list[ClaimInput] = []
    for index, claim in enumerate(result.claims):
        span = claim.spans[0] if claim.spans else (0, 0)
        claims.append(
            ClaimInput(
                claim_id=claim.claim_id,
                text=claim.text,
                span=span,
                source_text=text,
                index=index,
            )
        )
    return tuple(claims)


def source_map(text: str) -> dict[str, Any]:
    """Claim ids the attribution layer produced, for cross-checking."""

    return {claim.claim_id: claim.text for claim in extraction(text).claims}


class AttributionAdapter:
    """Speaker and stance, from Phase 8.2."""

    name = name

    def __init__(self, *, parser: ClaimParser | None = None) -> None:
        self._parser = parser if parser is not None else ClaimParser()

    def extract(self, text: str) -> tuple[ClaimInput, ...]:
        return extract_claims(text)

    def evaluate(self, claim: ClaimInput) -> AdapterResult:
        result = extraction(claim.source_text)
        match = self._find(result, claim)
        if match is None:
            # The layer declined to produce this claim - for instance a fragment
            # below the parser's minimum length. Report it as unavailable rather
            # than guessing a speaker, so the pipeline can see the gap.
            return AdapterResult(
                adapter=self.name,
                claim_id=claim.claim_id,
                evidence=(f"rule:attribution.no-claim-for-span:{claim.index}",),
                available=False,
                detail={"reason": "the attribution layer produced no claim here"},
            )

        return AdapterResult(
            adapter=self.name,
            claim_id=claim.claim_id,
            speaker=match.speaker,
            stance=match.stance,
            confidence=match.confidence,
            evidence=evidence_strings(
                match.evidence, (f"rule:attribution.{match.speaker}/{match.stance}",)
            ),
            detail={
                "is_authorial": match.is_authorial,
                "is_default_voice": match.is_default_voice,
                "rules": list(match.rules()),
                "statement_source": _statement_source(match),
            },
        )

    def _find(self, result: AttributionResult, claim: ClaimInput):
        if 0 <= claim.index < len(result.claims):
            candidate = result.claims[claim.index]
            if candidate.text == claim.text:
                return candidate
        for candidate in result.claims:
            if candidate.claim_id == claim.claim_id or candidate.text == claim.text:
                return candidate
        return None


def _statement_source(claim) -> str:
    from ...attribution.analyzer import to_statement_source

    return to_statement_source(claim)


def evaluate(claim: ClaimInput) -> AdapterResult:
    """Module-level convenience using the default adapter."""

    return DEFAULT.evaluate(claim)


DEFAULT = AttributionAdapter()
