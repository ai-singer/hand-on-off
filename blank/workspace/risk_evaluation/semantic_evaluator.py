"""Explainable semantic risk evaluator prototype.

This is **not** a learned model and **not** a copy of the keyword rules. It
composes surface signals into intent patterns:

    intent pattern = required signal classes (AND) + optional boosters

So *"You should buy this stock today."* matches `investment_advice` because a
**directive** and a **financial object** are both present — not because the
phrase is enumerated anywhere. Swap the object to *"move your money into this
company"* and the same two signal classes still fire.

What makes it different from keyword matching:

- **Compositional, not literal.** Most categories need two independent signal
  classes, so no single phrase decides the outcome.
- **Morphological.** Signals match word families (`recommend`, `recommends`,
  `recommended`, `recommendation`), not one surface form each.
- **Negation aware.** A signal preceded by a negation cue inside a short window
  is suppressed, so *"this is not a guaranteed return"* is not a guarantee.
- **Explainable.** Every result names the signals that fired and why the
  category matched. There is no opaque score.

Honest framing: this is still a hand-written rule system. It approximates
semantic intent; it does not understand it. It is a prototype for measuring
whether a different evaluator can beat the keyword baseline on the same
benchmark, and it must not be described as production-ready detection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Sequence

from .model import RiskEvaluationError, RiskEvaluationResult
from .taxonomy import category as taxonomy_category


#: Distance, in characters, within which a negation cue suppresses a signal.
NEGATION_WINDOW = 24

#: Signal classes. Each is a word family rather than a single surface form.
#:
#: ASCII alternatives are anchored with ``\b``. Chinese alternatives are
#: deliberately **not** anchored: CJK characters are all ``\w`` in Python, so a
#: trailing ``\b`` after a Chinese term fails whenever the next character is
#: also Chinese ("恐慌情绪" never matched "恐慌\b"). Chinese is written without
#: word delimiters, so substring matching is the correct behaviour there.
SIGNAL_PATTERNS: Mapping[str, tuple[str, ...]] = {
    # Language that directs the reader toward an action.
    "directive": (
        r"\b(?:should|must|ought to|need to|have to|had better|better to)\b",
        r"\b(?:recommend|suggest|advise|urge|encourage)(?:s|ed|ing|ation|ations|ory)?\b",
        r"\b(?:buy|buys|buying|bought)\b",
        r"\b(?:sell|sells|selling|sold)\b",
        r"\binvest(?:s|ed|ing|ment|ments)?\b",
        r"\bpurchas(?:e|es|ed|ing)\b",
        r"\b(?:hold|holds|holding|holdings)\b",
        r"\ballocat(?:e|es|ed|ing|ion)\b",
        r"\b(?:move|moves|moved|moving|shift|shifts|shifted|put|puts|putting)\b",
        r"\b(?:add|adds|added|adding)\b",
        r"\b(?:exit|exits|exiting|dump|dumps|dumping|offload|offloads)\b",
        # Imperative mood: advice is delivered by telling the reader to act, so
        # a suggestion verb in sentence-initial position is a directive. The
        # position anchor is what separates "Consider shifting your savings"
        # from the third-person "the report considers revenue", which is not
        # advice and must not be flagged.
        r"(?:^|(?<=[.!?;]\s))(?:consider|avoid|prefer|choose|stick\s+with|stay\s+with|go\s+with)\b",
        r"(?:买入|卖出|买进|抛售|加仓|建仓|补仓|减仓|持仓|推荐|建议|投资|配置|换仓|抄底|清仓)",
    ),
    # A financial subject the action or claim is about.
    "financial_object": (
        r"\b(?:stock|stocks|share|shares|equity|equities)\b",
        r"\b(?:portfolio|position|positions|holding|holdings|fund|funds)\b",
        r"\b(?:asset|assets|savings|money|capital|investment|investments)\b",
        r"\b(?:market|markets|company|companies|business|businesses)\b",
        r"\b(?:earnings|revenue|profit|profits|margin|margins|valuation)\b",
        r"\b(?:price|prices|share price|target price)\b",
        r"(?:股票|股价|基金|仓位|资产|收益|财报|公司|企业|现金|利润|市值|估值|本金)",
    ),
    # Reference to a future outcome.
    "future_marker": (
        r"\b(?:will|won't|'ll)\b",
        r"\b(?:going to|gonna|is set to|are set to|poised to|on track to)\b",
        r"\b(?:expect|expects|expected|project|projects|projected|forecast|forecasts|forecasted)\b[^.;]{0,40}?\b(?:to|that)\b",
        r"\b(?:sure|certain|bound|destined|set|poised)\s+to\b",
        r"\bby (?:next|the end of|year end|december|march|june|september)\b",
        r"(?:会|将|将要|即将|上涨|下跌|翻倍|暴涨|暴跌|大涨|大跌|增长|突破|升值|贬值)",
    ),
    # Certainty about that outcome.
    "certainty_marker": (
        r"\b(?:definitely|certainly|certain|undoubtedly|unquestionably|surely|sure)\b",
        r"\bguarantee(?:d|s|ing)?\b",
        r"\b(?:inevitabl(?:e|y)|unavoidable|bound to|destined to)\b",
        r"\b(?:without doubt|no doubt|beyond doubt)\b",
        r"\b(?:always|never)\b",
        r"(?:必然|肯定|一定|必定|稳赚|保证|绝对|铁定)",
    ),
    # Language that removes risk or makes an outcome unconditional.
    "risk_negation": (
        r"\brisk[-\s]?free\b",
        r"\b(?:no|zero|without)\s+risk\b",
        r"\b(?:safe bet|sure thing|sure win|free money)\b",
        r"\bcan(?:not|'t)\s+(?:fail|lose|go wrong)\b",
        r"\b(?:impossible|no way)\s+to\s+lose\b",
        r"\bnever\s+(?:falls?|fallen|fails?|failed|loses?|lost|drops?|dropped|declines?|declined)\b",
        r"\bno way\s+(?:this|that|it|the|these|those)\b",
        r"\bguaranteed\s+(?:return|returns|profit|profits|gain|gains|income|outcome)\b",
        r"(?:稳赚不赔|包赚|零风险|无风险|不会亏|保本|必赚|躺赚)",
    ),
    # Attribution the reader cannot check.
    "vague_source": (
        r"\b(?:rumou?r|rumou?rs)\b",
        r"\b(?:people|they|some|many|someone|somebody|experts|analysts|insiders?)\b[^.;]{0,24}?\b(?:say|says|said|believe|believes|think|thinks|know|knows)\b",
        r"\b(?:source|sources|insider|insiders)\b[^.;]{0,24}?\b(?:say|says|said|claim|claims|claimed|suggest|suggests)\b",
        r"\b(?:anonymous|unnamed|unidentified)\s+(?:source|sources|person|people|official|officials)\b",
        r"\b(?:word is|word on the street|reportedly|allegedly|it is said|i heard|we heard)\b",
        r"\b(?:inside information|insider information|internal news|internal memo)\b",
        r"(?:据说|传闻|消息人士|内部消息|听说|网传|未经证实|小道消息)",
    ),
    # Pressure that replaces reasoning.
    "emotional_pressure": (
        r"\b(?:panic|panicking|panicked)\b",
        r"\b(?:crash|crashes|crashing|collapse|collapses|collapsing|meltdown)\b",
        r"\b(?:do not miss|don't miss|miss out|missing out|last chance|now or never|too late|hurry|fomo)\b",
        r"\b(?:everyone|everybody|nobody)\b[^.;]{0,24}?\b(?:buying|selling|getting in|getting out|regrets?|missed)\b",
        r"\b(?:get out now|get in now|act now|act fast|run for the exits)\b",
        r"(?:疯狂|恐慌|崩盘|赶紧|错过|来不及|上车|抄底|血亏|暴跌|赶快)",
    ),
}

#: Cues that suppress a following signal inside `NEGATION_WINDOW` characters.
NEGATION_CUES = (
    r"\b(?:not|no|never|none|neither|nor|without|cannot|can't|won't|don't|doesn't|didn't|isn't|aren't|wasn't|weren't)\b",
    r"\bn't\b",
    r"\b(?:不|没|无|非|未)\b",
)

#: Signals a negation cue may suppress.
#:
#: `risk_negation` is included: "not a guaranteed return" denies the guarantee
#: claim, so it must not be read as one. The guard only suppresses a cue that
#: *ends before* the match starts, so patterns that are themselves negative --
#: "no risk", "cannot fail", "never falls" -- still fire, because there the cue
#: is the match rather than a modifier of it.
NEGATABLE_SIGNALS = tuple(SIGNAL_PATTERNS)


@dataclass(frozen=True, slots=True)
class SignalMatch:
    signal: str
    value: str
    start: int
    end: int
    negated: bool = False

    def render(self) -> str:
        suffix = " (negated)" if self.negated else ""
        return f"{self.signal}({self.value}){suffix}"


@dataclass(frozen=True, slots=True)
class IntentPattern:
    """A category's detection rule, expressed as signal requirements."""

    category: str
    required: tuple[str, ...]
    boosters: tuple[str, ...]
    rationale: str


INTENT_PATTERNS: tuple[IntentPattern, ...] = (
    IntentPattern(
        category="investment_advice",
        required=("directive", "financial_object"),
        boosters=(),
        rationale="A directive aimed at a financial object tells the reader to act.",
    ),
    IntentPattern(
        category="market_prediction",
        required=("future_marker", "certainty_marker"),
        boosters=("financial_object",),
        rationale="A future outcome stated with certainty is a prediction.",
    ),
    IntentPattern(
        category="financial_guarantee",
        required=("risk_negation",),
        boosters=("financial_object",),
        rationale="Language that removes risk makes an outcome unconditional.",
    ),
    IntentPattern(
        category="unverified_information",
        required=("vague_source",),
        boosters=(),
        rationale="An unattributable source cannot be checked.",
    ),
    IntentPattern(
        category="emotional_manipulation",
        required=("emotional_pressure",),
        boosters=(),
        rationale="Pressure substitutes for explanation.",
    ),
)

_CONFIDENCE_BASE = 0.6
_CONFIDENCE_STEP = 0.1
_CONFIDENCE_CAP = 0.9


@dataclass(frozen=True, slots=True)
class EvaluationEvidence:
    """Why a category matched, in inspectable form."""

    category: str
    signals: tuple[SignalMatch, ...]
    rationale: str

    def render(self) -> str:
        fired = ", ".join(match.render() for match in self.signals)
        return f"{self.category}: {fired}"


@lru_cache(maxsize=1)
def _signal_regexes() -> Mapping[str, tuple[re.Pattern[str], ...]]:
    return {
        signal: tuple(re.compile(pattern) for pattern in patterns)
        for signal, patterns in SIGNAL_PATTERNS.items()
    }


@lru_cache(maxsize=1)
def _negation_regexes() -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern) for pattern in NEGATION_CUES)


def detect_signals(text: str) -> Mapping[str, tuple[SignalMatch, ...]]:
    """Detect every signal class in the text, with spans and negation state."""

    if not isinstance(text, str):
        raise RiskEvaluationError(f"text must be a string, got {type(text).__name__}")
    lowered = text.lower()
    negation_spans = [
        (match.end(), match.start())
        for pattern in _negation_regexes()
        for match in pattern.finditer(lowered)
    ]

    detected: dict[str, tuple[SignalMatch, ...]] = {}
    for signal, patterns in _signal_regexes().items():
        matches: list[SignalMatch] = []
        seen: set[tuple[int, int]] = set()
        for pattern in patterns:
            for match in pattern.finditer(lowered):
                span = (match.start(), match.end())
                if span in seen:
                    continue
                seen.add(span)
                negated = signal in NEGATABLE_SIGNALS and _is_negated(
                    match.start(), negation_spans
                )
                matches.append(
                    SignalMatch(
                        signal=signal,
                        value=text[match.start() : match.end()],
                        start=match.start(),
                        end=match.end(),
                        negated=negated,
                    )
                )
        detected[signal] = tuple(sorted(matches, key=lambda item: item.start))
    return detected


def _is_negated(
    position: int, negation_spans: Sequence[tuple[int, int]]
) -> bool:
    for end, start in negation_spans:
        if end <= position and position - end <= NEGATION_WINDOW and start < position:
            return True
    return False


class SemanticRiskEvaluator:
    """Evaluator that matches intent patterns instead of literal phrases.

    It is deliberately independent of `plugins/xiaolin_finance/rules`: it reads
    no rule file and shares no keyword list, so a comparison between the two
    evaluators compares methods rather than configurations.
    """

    name = "semantic-intent-v0"

    def evaluate_text(
        self, text: str, *, source_ids: Sequence[str] = ()
    ) -> tuple[RiskEvaluationResult, ...]:
        if not isinstance(text, str) or not text.strip():
            raise RiskEvaluationError("evaluate_text requires non-empty text")

        signals = detect_signals(text)
        results: list[RiskEvaluationResult] = []
        for pattern in INTENT_PATTERNS:
            evidence = self._match(pattern, signals)
            if evidence is None:
                continue
            entry = taxonomy_category(pattern.category)
            active = [item for item in evidence if not item.negated]
            results.append(
                RiskEvaluationResult(
                    category=pattern.category,
                    intent=entry.intent,
                    confidence=self._confidence(pattern, active),
                    evidence_required=entry.evidence_required,
                    severity=entry.severity,
                    action=entry.action,
                    evaluator=self.name,
                    detail=self._detail(pattern, active),
                    source_ids=tuple(str(item) for item in source_ids),
                    candidates=(pattern.category,),
                )
            )
        return tuple(sorted(results, key=lambda item: item.category))

    def evaluate_artifact(
        self, artifact: Mapping[str, Any]
    ) -> tuple[RiskEvaluationResult, ...]:
        """Evaluate the text an artifact carries.

        The artifact keeps summaries rather than raw material, so this
        re-evaluates `knowledge_unit` statements and `topic_candidate` labels.
        It deliberately does **not** re-read `risk_constraints`: those are the
        output of whichever evaluator ran during distillation, and feeding them
        back would make the comparison circular.
        """

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

    def _match(
        self,
        pattern: IntentPattern,
        signals: Mapping[str, tuple[SignalMatch, ...]],
    ) -> tuple[SignalMatch, ...] | None:
        fired: list[SignalMatch] = []
        for required in pattern.required:
            active = [item for item in signals.get(required, ()) if not item.negated]
            if not active:
                return None
            fired.extend(active)
        for booster in pattern.boosters:
            fired.extend(item for item in signals.get(booster, ()) if not item.negated)
        return tuple(sorted(fired, key=lambda item: item.start))

    def _confidence(
        self, pattern: IntentPattern, fired: Sequence[SignalMatch]
    ) -> float:
        required_count = len(pattern.required)
        extra = max(0, len({item.signal for item in fired}) - required_count)
        return round(
            min(_CONFIDENCE_CAP, _CONFIDENCE_BASE + _CONFIDENCE_STEP * extra), 3
        )

    def _detail(self, pattern: IntentPattern, fired: Sequence[SignalMatch]) -> str:
        fired_text = ", ".join(match.render() for match in fired)
        return f"{pattern.rationale} Signals: {fired_text}"


def main() -> int:
    """Evaluate text from the command line, for inspection."""

    import sys

    if len(sys.argv) < 2:
        print("usage: python -m risk_evaluation.semantic_evaluator <text>")
        return 2
    evaluator = SemanticRiskEvaluator()
    results = evaluator.evaluate_text(" ".join(sys.argv[1:]))
    if not results:
        print("no risk intent detected")
        return 0
    for result in results:
        print(f"[{result.category}] confidence={result.confidence}")
        print(f"  {result.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
