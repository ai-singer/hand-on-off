"""Semantic risk evaluator v2: attribution, conditionality, category priority.

`semantic_evaluator.py` (v1) is **not modified**. v2 is a separate evaluator
that keeps v1's signal detection and adds the three capabilities benchmark
`semantic/v3` exists to measure:

1. **Attribution awareness.** v1 reads every text as one voice, so a claim the
   article quotes and then refutes is treated as the article's own claim. v2
   classifies `statement_source` and drops the categories that require the
   author's voice when the claim is not the author's.
2. **Conditional awareness.** v1 treats *"the market will crash"* and *"if
   rates fall, the stock may rise"* alike. v2 classifies `certainty_level` and
   only counts a market claim as a prediction when it is author-voice and
   certain.
3. **Category priority.** v2 separates pressure aimed at the reader from
   dramatic market vocabulary, so *"the market will crash"* is a prediction
   rather than emotional manipulation, while *"the market is collapsing, get
   out now"* is both.

It reads no plugin rule file, so a comparison against the keyword evaluator
still compares methods.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Sequence

from .model import RiskEvaluationError, RiskEvaluationResult
from .semantic_evaluator import SignalMatch, detect_signals
from .taxonomy import category as taxonomy_category
from .taxonomy_v2 import (
    CERTAINTY_LEVELS,
    STATEMENT_SOURCES,
    is_direct_prediction,
    market_claim_case,
    resolve_category_conflicts,
)


EVALUATOR_NAME = "semantic-intent-v2"

#: Pressure aimed at the reader. This is what makes emotional manipulation,
#: per guide v2 section 6.1 -- dramatic market vocabulary alone does not.
READER_PRESSURE_PATTERNS = (
    r"\b(?:do not miss|don't miss|miss out|missing out|last chance|now or never|hurry|act now|act fast|get out now|get in now|closes tonight|window closes)\b",
    r"\b(?:before it is too late|too late|no time left)\b",
    r"\b(?:you|readers?|investors?)\b[^.;]{0,20}?\b(?:crazy|foolish|mad|stupid)\b",
    r"\b(?:everyone|everybody|nobody)\b[^.;]{0,30}?\b(?:buying|selling|getting in|getting out|should|too|regrets?|missed)\b",
    r"(?:赶紧|赶快|错过|来不及|上车|疯狂|马上行动)",
)

#: Conditional markers. A sentence-initial "should" is an inversion ("should X
#: happen"), not a directive, which is why the position anchor matters.
CONDITIONAL_PATTERNS = (
    r"\bif\b",
    r"\bunless\b",
    r"\bassuming\b",
    r"\bdepending on\b",
    r"\bprovided that\b",
    r"\bin the event\b",
    r"\bwere\s+\w+\s+to\b",
    r"(?:^|(?<=[.!?;]\s))should\s+\w+",
    r"(?:^|(?<=[.!?;]\s))had\s+\w+",
)

POSSIBILITY_PATTERNS = (
    r"\b(?:may|might|could|possibly|perhaps|potentially|conceivably)\b",
    r"(?:可能|或许|也许)",
)

PROBABILITY_PATTERNS = (
    r"\b(?:probably|likely|expected to|expected that|anticipat\w+|project\w*\s+to|forecast\w*\s+to)\b",
    r"\bexpect(?:s|ed|ing)?\b",
)

#: Attribution to a named or reasonably identifiable party.
THIRD_PARTY_PATTERNS = (
    r"\b(?:analysts?|experts?|economists?|management|the board|regulators?|officials?|brokers?|bankers?|commentators?)\b[^.;]{0,40}?\b(?:say|says|said|expect|expects|expected|forecast|forecasts|forecasted|project|projects|projected|estimate|estimates|estimated|believe|believes|publish\w*|certain|confident|sure|note|notes|noted)\b",
    r"\b(?:the analyst|the broker|the newsletter|the broker note|management|the board)\b[^.;]{0,30}?\b(?:wrote|writes|says|said|projects|projected|expects|expected)\b",
)

#: Quotation framing: the claim is presented as someone else's words.
QUOTATION_PATTERNS = (
    r"[\"\u201c\u201d]",
    r"\b(?:quote|quotes|quoted|quoting)\b",
    r"\b(?:headline|commenter|blogger|newsletter)\b",
    r"\b(?:wrote|writes|wrote that|said that|saying)\b",
)

#: Rejection framing: the text mentions a claim in order to dismiss it. A text
#: that argues against a claim is not making it.
REJECTION_PATTERNS = (
    r"\b(?:refut\w+|debunk\w*|disput\w+|corrected|was wrong|were wrong|does not endorse|do not endorse|argues? against|in order to (?:debunk|refute|dismiss))\b",
    r"(?:反驳|澄清|辟谣)",
)


@dataclass(frozen=True, slots=True)
class V2IntentPattern:
    category: str
    required: tuple[str, ...]
    rationale: str


V2_INTENT_PATTERNS: tuple[V2IntentPattern, ...] = (
    V2IntentPattern(
        "investment_advice",
        ("directive", "financial_object"),
        "A directive aimed at a financial object tells the reader to act.",
    ),
    V2IntentPattern(
        "market_prediction",
        ("future_marker", "certainty_marker"),
        "A future outcome the author asserts with certainty.",
    ),
    V2IntentPattern(
        "financial_guarantee",
        ("risk_negation",),
        "Language that removes risk makes an outcome unconditional.",
    ),
    V2IntentPattern(
        "unverified_information",
        ("vague_source",),
        "An unattributable source cannot be checked.",
    ),
    V2IntentPattern(
        "emotional_manipulation",
        ("reader_pressure",),
        "Pressure aimed at the reader substitutes for explanation.",
    ),
)

_CONFIDENCE_BASE = 0.6
_CONFIDENCE_STEP = 0.1
_CONFIDENCE_CAP = 0.9


@dataclass(frozen=True, slots=True)
class AttributionAnalysis:
    statement_source: str
    markers: tuple[str, ...]

    def render(self) -> str:
        return f"statement_source={self.statement_source} markers={list(self.markers)}"


@dataclass(frozen=True, slots=True)
class CertaintyAnalysis:
    certainty_level: str
    markers: tuple[str, ...]

    def render(self) -> str:
        return f"certainty_level={self.certainty_level} markers={list(self.markers)}"


@dataclass(frozen=True, slots=True)
class RiskAnalysisV2:
    """Everything v2 determined, including what it suppressed and why."""

    statement_source: str
    certainty_level: str
    market_claim_case: str
    categories: tuple[str, ...]
    suppressed: tuple[str, ...]
    results: tuple[RiskEvaluationResult, ...]
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "statement_source": self.statement_source,
            "certainty_level": self.certainty_level,
            "market_claim_case": self.market_claim_case,
            "categories": list(self.categories),
            "suppressed": list(self.suppressed),
            "detail": self.detail,
            "results": [item.as_dict() for item in self.results],
        }


def _compile(patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern) for pattern in patterns)


@lru_cache(maxsize=1)
def _reader_pressure() -> tuple[re.Pattern[str], ...]:
    return _compile(READER_PRESSURE_PATTERNS)


@lru_cache(maxsize=1)
def _conditional() -> tuple[re.Pattern[str], ...]:
    return _compile(CONDITIONAL_PATTERNS)


@lru_cache(maxsize=1)
def _possibility() -> tuple[re.Pattern[str], ...]:
    return _compile(POSSIBILITY_PATTERNS)


@lru_cache(maxsize=1)
def _probability() -> tuple[re.Pattern[str], ...]:
    return _compile(PROBABILITY_PATTERNS)


@lru_cache(maxsize=1)
def _third_party() -> tuple[re.Pattern[str], ...]:
    return _compile(THIRD_PARTY_PATTERNS)


@lru_cache(maxsize=1)
def _quotation() -> tuple[re.Pattern[str], ...]:
    return _compile(QUOTATION_PATTERNS)


@lru_cache(maxsize=1)
def _rejection() -> tuple[re.Pattern[str], ...]:
    return _compile(REJECTION_PATTERNS)


def _matches(patterns: Sequence[re.Pattern[str]], lowered: str) -> list[str]:
    found: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(lowered):
            found.append(match.group(0).strip())
    return found


def detect_reader_pressure(text: str) -> tuple[str, ...]:
    return tuple(_matches(_reader_pressure(), text.lower()))


def analyze_attribution(text: str) -> AttributionAnalysis:
    """Classify who makes the claim, in the guide v2 precedence order.

    `quoted` beats `unknown` beats `third_party` beats `author`. Rejection
    framing counts as `quoted`: a text that argues against a claim is
    discussing someone else's words, not asserting them.
    """

    if not isinstance(text, str):
        raise RiskEvaluationError(f"text must be a string, got {type(text).__name__}")
    lowered = text.lower()

    rejection = _matches(_rejection(), lowered)
    if rejection:
        return AttributionAnalysis("quoted", tuple(rejection))

    quotation = _matches(_quotation(), lowered)
    if quotation:
        return AttributionAnalysis("quoted", tuple(quotation))

    signals = detect_signals(text)
    vague = tuple(
        match.render() for match in signals.get("vague_source", ()) if not match.negated
    )
    if vague:
        return AttributionAnalysis("unknown", vague)

    third_party = _matches(_third_party(), lowered)
    if third_party:
        return AttributionAnalysis("third_party", tuple(third_party))

    return AttributionAnalysis("author", ())


def analyze_certainty(text: str) -> CertaintyAnalysis:
    """Classify how strongly the text asserts its claim.

    Conditional beats modal: a possibility that depends on a condition is
    hypothetical, not possible.
    """

    lowered = text.lower()

    conditional = _matches(_conditional(), lowered)
    if conditional:
        return CertaintyAnalysis("hypothetical", tuple(conditional))

    possibility = _matches(_possibility(), lowered)
    if possibility:
        return CertaintyAnalysis("possible", tuple(possibility))

    probability = _matches(_probability(), lowered)
    if probability:
        return CertaintyAnalysis("probable", tuple(probability))

    return CertaintyAnalysis("certain", ())


class SemanticRiskEvaluatorV2:
    """Risk intent evaluator with attribution and conditionality awareness."""

    name = EVALUATOR_NAME

    def analyze(self, text: str) -> RiskAnalysisV2:
        if not isinstance(text, str) or not text.strip():
            raise RiskEvaluationError("analyze requires non-empty text")

        signals = detect_signals(text)
        attribution = analyze_attribution(text)
        certainty = analyze_certainty(text)
        pressure = detect_reader_pressure(text)

        matched: list[str] = []
        fired: dict[str, tuple[SignalMatch, ...]] = {}
        for pattern in V2_INTENT_PATTERNS:
            active = self._active_signals(pattern, signals, pressure)
            if active is None:
                continue
            matched.append(pattern.category)
            fired[pattern.category] = active

        resolved = set(
            resolve_category_conflicts(
                matched,
                reader_pressure=bool(pressure),
                statement_source=attribution.statement_source,
            )
        )
        # A market claim is a prediction only in the author's voice and certain.
        if "market_prediction" in resolved and not is_direct_prediction(
            statement_source=attribution.statement_source,
            certainty_level=certainty.certainty_level,
        ):
            resolved.discard("market_prediction")

        suppressed = tuple(
            name for name in matched if name not in resolved
        )

        results: list[RiskEvaluationResult] = []
        for category in sorted(resolved):
            entry = taxonomy_category(category)
            results.append(
                RiskEvaluationResult(
                    category=category,
                    intent=entry.intent,
                    confidence=self._confidence(fired.get(category, ())),
                    evidence_required=entry.evidence_required,
                    severity=entry.severity,
                    action=entry.action,
                    evaluator=self.name,
                    detail=self._detail(
                        category, fired.get(category, ()), attribution, certainty
                    ),
                    candidates=(category,),
                )
            )

        claim = market_claim_case(
            statement_source=attribution.statement_source,
            certainty_level=certainty.certainty_level,
        )
        return RiskAnalysisV2(
            statement_source=attribution.statement_source,
            certainty_level=certainty.certainty_level,
            market_claim_case=claim.name,
            categories=tuple(sorted(resolved)),
            suppressed=suppressed,
            results=tuple(results),
            detail=(
                f"{attribution.render()}; {certainty.render()}; "
                f"market_claim_case={claim.name}; pressure={list(pressure)}"
            ),
        )

    # -- protocol compatibility -------------------------------------------

    def evaluate_text(
        self, text: str, *, source_ids: Sequence[str] = ()
    ) -> tuple[RiskEvaluationResult, ...]:
        analysis = self.analyze(text)
        if not source_ids:
            return analysis.results
        return tuple(
            RiskEvaluationResult(
                category=item.category,
                intent=item.intent,
                confidence=item.confidence,
                evidence_required=item.evidence_required,
                severity=item.severity,
                action=item.action,
                evaluator=item.evaluator,
                detail=item.detail,
                source_ids=tuple(str(value) for value in source_ids),
                candidates=item.candidates,
            )
            for item in analysis.results
        )

    def evaluate_artifact(
        self, artifact: Mapping[str, Any]
    ) -> tuple[RiskEvaluationResult, ...]:
        if not isinstance(artifact, Mapping):
            raise RiskEvaluationError(
                f"artifact must be a mapping, got {type(artifact).__name__}"
            )
        fragments: list[str] = []
        for unit in artifact.get("knowledge_unit", ()):
            if isinstance(unit, Mapping) and unit.get("statement"):
                fragments.append(str(unit["statement"]))
        for candidate in artifact.get("topic_candidate", ()):
            if isinstance(candidate, Mapping) and candidate.get("label"):
                fragments.append(str(candidate["label"]))
        if not fragments:
            return ()
        return self.evaluate_text(" \n".join(fragments))

    # -- internals ---------------------------------------------------------

    def _active_signals(
        self,
        pattern: V2IntentPattern,
        signals: Mapping[str, tuple[SignalMatch, ...]],
        pressure: Sequence[str],
    ) -> tuple[SignalMatch, ...] | None:
        collected: list[SignalMatch] = []
        for required in pattern.required:
            if required == "reader_pressure":
                if not pressure:
                    return None
                continue
            active = [
                item for item in signals.get(required, ()) if not item.negated
            ]
            if not active:
                return None
            collected.extend(active)
        return tuple(sorted(collected, key=lambda item: item.start))

    def _confidence(self, fired: Sequence[SignalMatch]) -> float:
        classes = {item.signal for item in fired}
        extra = max(0, len(classes) - 1)
        return round(min(_CONFIDENCE_CAP, _CONFIDENCE_BASE + _CONFIDENCE_STEP * extra), 3)

    def _detail(
        self,
        category: str,
        fired: Sequence[SignalMatch],
        attribution: AttributionAnalysis,
        certainty: CertaintyAnalysis,
    ) -> str:
        signals = ", ".join(item.render() for item in fired) or "reader pressure"
        return (
            f"{category}: signals {signals}; "
            f"{attribution.statement_source}/{certainty.certainty_level}"
        )


def supported_dimensions() -> Mapping[str, tuple[str, ...]]:
    return {"statement_source": STATEMENT_SOURCES, "certainty_level": CERTAINTY_LEVELS}


def main() -> int:
    import sys

    if len(sys.argv) < 2:
        print("usage: python -m risk_evaluation.semantic_evaluator_v2 <text>")
        return 2
    analysis = SemanticRiskEvaluatorV2().analyze(" ".join(sys.argv[1:]))
    print(analysis.detail)
    for result in analysis.results:
        print(f"  [{result.category}] confidence={result.confidence}")
    if analysis.suppressed:
        print(f"  suppressed: {list(analysis.suppressed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
