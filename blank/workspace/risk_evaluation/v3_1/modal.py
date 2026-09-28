"""Capability 1: a modal prediction, told apart from an uncertainty.

Guide v2 section 2 settles the category question with one rule:

    market_prediction  <=>  statement_source == author  AND  certainty_level == certain

so a modal prediction is never a `market_prediction`, and the layer that finds one
has to do two things a frame cannot: say how strong the statement is, and say what
the statement is about. Both were measured as broken before this module existed.

**Raised when it should not be.** Three false positives, each a modal that is not
a prediction:

    The market will probably crash next month.    `will` is certain, `probably` is
                                                 not, and the statement is the
                                                 weaker of the two
    There is a chance the shares will recover.    the possibility is in the
                                                 construction, not the modal
    It is possible that the price will double.    the same, as a clause

A keyword layer cannot see any of them: all three contain `will` and a market word.

**Not raised when it should be.** Seven of eight weak predictions produced no
relation at all, because the Phase 8.4 frames require `will | shall | is going to`
and `The valuation is expected to increase.` contains none of them. The relation
is what Phase 8.6 measured as failing, so the gaps are a coverage defect even where
the final category happened to come out right.

The detector is built from four signals, and the phase names the first three:

    market_entity                a financial target, from the v3 entity lexicon
    outcome_expression           a directional outcome, not a non-directional verb
    uncertain_prediction_modal   a strength carrier, classified
    future_marker                a horizon, or a construction that is future by grammar

`outcome_expression` is the signal that does the most work. `may fluctuate`,
`may vary`, `may change` and `may differ` are disclosures that state no direction,
and requiring a *directional* outcome is what separates them from
`may recover next quarter` without a list of disclosure formulas.

**Frame is structure, strength is a scan.** The frame matches
subject-carrier-outcome. The strength is then read from the whole sentence,
weakest wins, because `Perhaps the fund will outperform` puts its possibility
before the subject and outside the frame entirely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from ..v3.model import INSTRUMENT, OUTCOME, PREDICTION, REVENUE, RETURN, VALUE, IntentEvidence
from ..v3.patterns import ENTITIES, MOVEMENT_VERBS
from ..v3.morphology import alternation
from .certainty import CERTAIN, CARRIERS, HYPOTHETICAL, Strength, weakest
from .signals import (
    FUTURE_MARKER,
    MARKET_ENTITY,
    MODAL_PREDICTION,
    OUTCOME_EXPRESSION,
    UNCERTAIN_PREDICTION_MODAL,
    Signal,
    SignalSet,
    build,
)

#: The financial targets a prediction can be about. The same set the Phase 8.4
#: prediction frames use: a stock is not a return, but a prediction about a stock
#: is a prediction about its value, and VALUE covers the price and the index.
SUBJECT_ENTITIES: tuple[str, ...] = (VALUE, RETURN, REVENUE, OUTCOME, INSTRUMENT)

SUBJECT = ENTITIES.group(*SUBJECT_ENTITIES)

#: A short gap between the subject and its carrier. Bounded, because an unbounded
#: one matches across unrelated clauses.
_GAP = r"(?:\s+[A-Za-z'\-\u4e00-\u9fff]+){0,3}?"

#: Comparison outcomes. `rise` and `fall` were already covered by the movement
#: verbs; relative performance is a directional outcome too, and
#: `The fund might outperform its benchmark` is a prediction about the fund.
COMPARISON_LEMMAS: tuple[str, ...] = (
    "outperform",
    "underperform",
    "beat",
    "lag",
    "trail",
    "exceed",
    "match",
    "top",
    "outpace",
    "surpass",
)

#: Outcomes expressed as nouns. `A rally is possible` predicts the same thing as
#: `The index may rally`, and a layer that could only see verbs would miss it.
DIRECTIONAL_NOUNS = (
    r"gains?",
    r"loss(?:es)?",
    r"a\s+rise",
    r"a\s+fall",
    r"a\s+drop",
    r"a\s+decline",
    r"a\s+rally",
    r"a\s+recovery",
    r"a\s+correction",
    r"a\s+selloff",
    r"growth",
    r"appreciation",
    r"depreciation",
)

#: Directional outcomes: the movement verbs, relative performance, and outcomes
#: expressed as nouns. The movement verbs come from the Phase 8.7 morphology layer
#: rather than a new list, so a modal prediction and a certain prediction agree
#: about what counts as moving.
OUTCOME = (
    rf"(?:{alternation(tuple(COMPARISON_LEMMAS))[3:-1]}|"
    rf"{MOVEMENT_VERBS[3:-1]}|"
    rf"{'|'.join(DIRECTIONAL_NOUNS)})"
)

#: Verbs that state no direction. `may fluctuate` is a risk disclosure and says
#: nothing about which way anything goes; a prediction names one direction.
NON_DIRECTIONAL_LEMMAS: tuple[str, ...] = (
    "fluctuate",
    "vary",
    "change",
    "differ",
    "alter",
    "shift",
    "move",
    "behave",
    "perform",
)

NON_DIRECTIONAL = alternation(NON_DIRECTIONAL_LEMMAS)

#: A symmetric pair: `fall as well as rise`, `go down as well as up`, `rise or
#: fall`. A prediction names one direction; a pair names both and therefore
#: claims neither. This is structural, not lexical - it is the shape of the
#: sentence, not a formula that happens to contain it.
_SYMMETRIC = (
    r"(?P<first>rise|fall|increase|decrease|decline|gain|lose|go\s+up|go\s+down|"
    r"up|down)\s+(?:as\s+well\s+as|or|and)\s+"
    r"(?P<second>rise|fall|increase|decrease|decline|gain|lose|go\s+up|go\s+down|"
    r"up|down)"
)

SYMMETRIC_PAIR = re.compile(rf"\b{_SYMMETRIC}\b", re.IGNORECASE)
#: Without a leading boundary: `go down as well as up` starts mid-phrase.
SYMMETRIC_PAIR_LOOSE = re.compile(_SYMMETRIC, re.IGNORECASE)

#: Verbs whose complement is an explanation rather than an outcome. `may indicate`
#: is a modal about a definition; the modal layer declines it and says so, which
#: is why these are listed even though the outcome lexicon would exclude them
#: anyway - a named reason is what a trace can cite.
EPISTEMIC_LEMMAS: tuple[str, ...] = (
    "indicate",
    "include",
    "refer",
    "apply",
    "consist",
    "reflect",
    "mean",
    "represent",
    "relate",
    "constitute",
    "arise",
    "occur",
    "stem",
    "result",
    "depend",
    "correspond",
    "pertain",
)

EPISTEMIC = alternation(EPISTEMIC_LEMMAS)

#: Horizons. A prediction is about a future outcome, so a statement with no
#: horizon needs a construction that is future by grammar instead.
HORIZON = (
    r"next\s+(?:year|quarter|month|week|half|season|decade|few\s+years?)|"
    r"this\s+(?:year|quarter|month|week|half)|"
    r"over\s+the\s+next|in\s+the\s+coming|in\s+the\s+next|"
    r"by\s+(?:20\d\d|year-end|the\s+end\s+of|then)|"
    r"from\s+here|going\s+forward|in\s+(?:20\d\d|H[12]|the\s+second\s+half|"
    r"the\s+first\s+half)|"
    r"(?:short|medium|long)[\s-]term|"
    r"tomorrow|hereafter|"
    r"\u660e\u5e74|\u4e0b\u5b63\u5ea6|\u672a\u6765"
)

HORIZON_RE = re.compile(rf"\b(?:{HORIZON})\b", re.IGNORECASE)

#: Constructions that are future by grammar, so a horizon is not needed.
PROSPECTIVE_CONSTRUCTIONS: tuple[str, ...] = (
    r"is\s+going\s+to",
    r"are\s+going\s+to",
    r"was\s+going\s+to",
    r"is\s+likely\s+to",
    r"are\s+likely\s+to",
    r"is\s+expected\s+to",
    r"are\s+expected\s+to",
    r"is\s+set\s+to",
    r"are\s+set\s+to",
    r"is\s+poised\s+to",
    r"are\s+poised\s+to",
    r"is\s+due\s+to",
    r"are\s+due\s+to",
    r"is\s+bound\s+to",
    r"are\s+bound\s+to",
    r"will",
    r"shall",
    r"would",
)

#: Modals that are future-oriented on their own: a possibility about a directional
#: outcome can only be about what has not happened yet.
PROSPECTIVE_MODALS: tuple[str, ...] = (r"may", r"might", r"could")

PROSPECTIVE_RE = re.compile(
    rf"\b(?:{'|'.join((*PROSPECTIVE_CONSTRUCTIONS, *PROSPECTIVE_MODALS))})\b",
    re.IGNORECASE,
)

#: The carrier slot: an optional strength adverb, a modal verb or construction,
#: and an optional strength adverb after it. Both orders occur -
#: `will probably decline` and `will likely rise` - and the strength scan reads
#: both, so the frame accepts both rather than the layer picking a favourite.
_ADVERB_PATTERNS = "|".join(
    pattern for _, kind, pattern in CARRIERS if kind == "adverb"
)
_MODAL_PATTERNS = "|".join(
    pattern for _, kind, pattern in CARRIERS if kind in ("verb", "construction")
)

CARRIER = (
    rf"(?:(?:{_ADVERB_PATTERNS})\s+)?(?:{_MODAL_PATTERNS})"
    rf"(?:\s+(?:{_ADVERB_PATTERNS}))?"
)

#: The whole frame: a market target, a strength carrier, a directional outcome.
FRAME = re.compile(
    rf"\b(?P<subject>{SUBJECT}){_GAP}\s+(?P<carrier>{CARRIER})\s+"
    rf"(?P<outcome>{OUTCOME})\b",
    re.IGNORECASE,
)

#: A carrier followed by a non-directional verb, for the declined verdict.
NON_DIRECTIONAL_FRAME = re.compile(
    rf"\b(?P<subject>{SUBJECT}){_GAP}\s+(?P<carrier>{CARRIER})\s+"
    rf"(?P<outcome>{NON_DIRECTIONAL})\b",
    re.IGNORECASE,
)

#: A carrier followed by an epistemic verb.
EPISTEMIC_FRAME = re.compile(
    rf"\b(?P<carrier>{CARRIER})\s+(?P<outcome>{EPISTEMIC})\b",
    re.IGNORECASE,
)

#: Verdicts. A prediction, a prediction below `certain`, or one of the reasons
#: there is no prediction. Each declined verdict is a positive finding about the
#: sentence, not the absence of a match.
PREDICTION_VERDICT = "prediction"
WEAK_PREDICTION = "weak_prediction"
NON_DIRECTIONAL_VERDICT = "non_directional"
NON_PREDICTION_MODAL = "non_prediction_modal"
CONDITIONAL_SCENARIO = "conditional_scenario"
NO_MARKET_ENTITY = "no_market_entity"
NO_OUTCOME = "no_outcome"
NO_FUTURE_ORIENTATION = "no_future_orientation"
NO_MODAL = "no_modal"

VERDICTS: tuple[str, ...] = (
    PREDICTION_VERDICT,
    WEAK_PREDICTION,
    NON_DIRECTIONAL_VERDICT,
    NON_PREDICTION_MODAL,
    CONDITIONAL_SCENARIO,
    NO_MARKET_ENTITY,
    NO_OUTCOME,
    NO_FUTURE_ORIENTATION,
    NO_MODAL,
)

#: Verdicts that are positive evidence against a prediction, and so may be used
#: to decline a category the semantic fallback would otherwise keep. `no_outcome`
#: and `no_market_entity` are excluded: "this is not the shape I look for" is not
#: evidence that no prediction is present, and treating it as evidence would let
#: this layer veto wordings it simply does not cover.
DECLINING_VERDICTS: tuple[str, ...] = (
    NON_DIRECTIONAL_VERDICT,
    NON_PREDICTION_MODAL,
    CONDITIONAL_SCENARIO,
    WEAK_PREDICTION,
)


class ModalError(Exception):
    """Raised when a modal prediction cannot be evaluated."""


@dataclass(frozen=True, slots=True)
class ModalDetection:
    """What the modal layer found, and what it concluded."""

    verdict: str
    strength: Strength
    signals: SignalSet
    span: tuple[int, int] = (0, 0)
    entity: str = ""
    predicate: str = ""
    finding: IntentEvidence | None = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ModalError(f"unknown verdict {self.verdict!r}")

    @property
    def declared(self) -> bool:
        """Did a prediction relation come out of this?"""

        return self.finding is not None

    @property
    def declines(self) -> bool:
        return self.verdict in DECLINING_VERDICTS

    @property
    def declined_categories(self) -> tuple[str, ...]:
        return ("market_prediction",) if self.declines else ()

    @property
    def signal_names(self) -> tuple[str, ...]:
        return self.signals.names

    def as_dict(self) -> dict[str, object]:
        return {
            "capability": MODAL_PREDICTION,
            "verdict": self.verdict,
            "strength": self.strength.as_dict(),
            "signals": self.signals.as_dict(),
            "span": list(self.span),
            "entity": self.entity,
            "predicate": self.predicate,
            "declared": self.declared,
            "declines": self.declines,
            "declined_categories": list(self.declined_categories),
            "evidence": list(self.evidence),
        }


def strength_of(text: str) -> Strength:
    """The strength of `text`: the weakest carrier present, weakest wins."""

    from .certainty import INVERTED_CONDITIONALS

    carriers = []
    for level, kind, pattern in CARRIERS:
        for match in re.finditer(rf"\b(?:{pattern})\b", text, re.IGNORECASE):
            carriers.append(_carrier(level, kind, match.group(0), match.span()))
    # The inverted conditionals are declared separately because they are positional:
    # `Should the market decline` is a scenario and `The fund should outperform` is
    # not, and only a clause-initial test can tell them apart.
    for pattern in INVERTED_CONDITIONALS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            carriers.append(
                _carrier(HYPOTHETICAL, "conditional", match.group(0).strip(), match.span())
            )
    if not carriers:
        return Strength(CERTAIN)
    level = weakest(*(item.level for item in carriers))
    return Strength(level, tuple(carriers))


def _carrier(level, kind, marker, span):
    from .certainty import Carrier

    return Carrier(level=level, marker=marker.lower(), span=span, kind=kind)


def _entity_type(value: str) -> str:
    for name in SUBJECT_ENTITIES:
        if re.fullmatch(ENTITIES.get(name).pattern, value, re.IGNORECASE):
            return name
    return ""


def evaluate(text: str) -> ModalDetection:
    """Evaluate one claim's text for a modal prediction."""

    if not isinstance(text, str):
        raise ModalError(f"text must be a string, got {type(text).__name__}")

    strength = strength_of(text)
    horizon = HORIZON_RE.search(text)
    prospective = PROSPECTIVE_RE.search(text)
    future_signals = [
        Signal(
            FUTURE_MARKER,
            (horizon or prospective).span(),
            (horizon or prospective).group(0).lower(),
            "horizon" if horizon else "prospective_construction",
        )
    ] if (horizon or prospective) else []

    # -- a symmetric pair comes first, because it is decisive on its own. `Fund
    # values can go down as well as up.` names both directions and therefore
    # claims neither, and that is true whatever else the sentence contains.
    pair = SYMMETRIC_PAIR_LOOSE.search(text)
    if pair is not None:
        return ModalDetection(
            verdict=NON_DIRECTIONAL_VERDICT,
            strength=strength,
            signals=build(*future_signals),
            span=pair.span(),
            predicate=pair.group(0).lower(),
            evidence=(
                f"capability:{MODAL_PREDICTION}:{NON_DIRECTIONAL_VERDICT}",
                f"capability:{MODAL_PREDICTION}:symmetric-pair:{pair.group(0).lower()}",
            ),
        )

    # -- a non-directional outcome comes next, and before the epistemic check.
    # `Returns may vary` is a disclosure about a market quantity, which is a
    # stronger and more specific finding than "the modal's complement explains";
    # `vary` and `differ` are both. Ordering the disclosure first is what makes
    # the verdict name the reason a reader would give.
    non_directional = NON_DIRECTIONAL_FRAME.search(text)
    if non_directional is not None:
        signals = build(
            Signal(
                MARKET_ENTITY,
                non_directional.span("subject"),
                non_directional.group("subject"),
                _entity_type(non_directional.group("subject")) or "unknown",
            ),
            Signal(
                UNCERTAIN_PREDICTION_MODAL,
                non_directional.span("carrier"),
                non_directional.group("carrier").lower(),
                f"certainty:{strength.level}",
            ),
            *future_signals,
        )
        return ModalDetection(
            verdict=NON_DIRECTIONAL_VERDICT,
            strength=strength,
            signals=signals,
            span=non_directional.span(),
            entity=_entity_type(non_directional.group("subject")),
            predicate=non_directional.group("outcome").lower(),
            evidence=(
                f"capability:{MODAL_PREDICTION}:{NON_DIRECTIONAL_VERDICT}",
                f"capability:{MODAL_PREDICTION}:non-directional-outcome:"
                f"{non_directional.group('outcome').lower()}",
                *signals.markers,
            ),
        )

    # -- the epistemic case: a modal whose complement explains rather than
    # predicts. Checked before the frame, because `may indicate a higher
    # turnover` has a market word in it and no directional outcome at all.
    epistemic = EPISTEMIC_FRAME.search(text)
    if epistemic is not None:
        signal = Signal(
            UNCERTAIN_PREDICTION_MODAL,
            epistemic.span("carrier"),
            epistemic.group("carrier").lower(),
            f"certainty:{strength.level}",
        )
        return ModalDetection(
            verdict=NON_PREDICTION_MODAL,
            strength=strength,
            signals=build(signal, *future_signals),
            span=epistemic.span(),
            predicate=epistemic.group("outcome").lower(),
            evidence=(
                f"capability:{MODAL_PREDICTION}:{NON_PREDICTION_MODAL}",
                f"capability:{MODAL_PREDICTION}:explains-not-predicts:"
                f"{epistemic.group('outcome').lower()}",
                signal.marker,
            ),
        )

    frame = FRAME.search(text)
    if frame is None:
        return _absent(text, strength, horizon, prospective, future_signals)

    subject = frame.group("subject")
    entity = _entity_type(subject)
    outcome = frame.group("outcome")
    modal = frame.group("carrier")

    signals = [
        Signal(MARKET_ENTITY, frame.span("subject"), subject, entity or "unknown"),
        Signal(
            UNCERTAIN_PREDICTION_MODAL,
            frame.span("carrier"),
            modal.lower(),
            f"certainty:{strength.level}",
        ),
        Signal(OUTCOME_EXPRESSION, frame.span("outcome"), outcome.lower(), "directional"),
        *future_signals,
    ]
    found = build(*signals)

    # -- a conditional asserts nothing unconditionally, so there is no
    # prediction to report at all (guide 2 and 5)
    if strength.hypothetical:
        return ModalDetection(
            verdict=CONDITIONAL_SCENARIO,
            strength=strength,
            signals=found,
            span=frame.span(),
            entity=entity,
            predicate=outcome.lower(),
            evidence=(
                f"capability:{MODAL_PREDICTION}:{CONDITIONAL_SCENARIO}",
                f"capability:{MODAL_PREDICTION}:conditional-carrier:{strength.marker}",
                *found.markers,
            ),
        )

    # -- below `certain` the taxonomy does not call it a prediction, so the
    # relation is reported and hedged and the policy declines it (guide 2)
    verdict = PREDICTION_VERDICT if strength.certain else WEAK_PREDICTION
    hedge = "" if strength.certain else strength.marker or strength.level
    finding = IntentEvidence(
        relation=PREDICTION,
        entity=entity or "UNKNOWN",
        frame="active",
        predicate=outcome.lower(),
        pattern_id=PATTERN_ID,
        span=frame.span(),
        hedge=hedge,
        signals=found.names,
        certainty=strength.level,
        boundary=verdict,
    )
    return ModalDetection(
        verdict=verdict,
        strength=strength,
        signals=found,
        span=frame.span(),
        entity=entity,
        predicate=outcome.lower(),
        finding=finding,
        evidence=(
            f"capability:{MODAL_PREDICTION}:{verdict}",
            f"capability:{MODAL_PREDICTION}:certainty:{strength.level}",
            *found.markers,
        ),
    )


def _absent(
    text: str,
    strength: Strength,
    horizon,
    prospective,
    future_signals: Sequence[Signal],
) -> ModalDetection:
    """No frame matched. Say which signal was missing.

    Every verdict here except `conditional_scenario` is a statement about this
    layer's coverage rather than about the sentence, so none of them declines a
    category: see `DECLINING_VERDICTS`.
    """

    modal = re.search(rf"\b(?:{_MODAL_PATTERNS})\b", text, re.IGNORECASE)
    subject = re.search(rf"\b(?:{SUBJECT})", text, re.IGNORECASE)

    if modal is None:
        verdict = NO_MODAL
    elif strength.hypothetical:
        # A conditional statement asserts nothing unconditionally (guide 5), so
        # there is no prediction to report and the layer says so rather than
        # reporting nothing. Checked before the shape tests: whether the frame
        # matched is irrelevant once the statement is contingent.
        return ModalDetection(
            verdict=CONDITIONAL_SCENARIO,
            strength=strength,
            signals=build(*future_signals),
            evidence=(
                f"capability:{MODAL_PREDICTION}:{CONDITIONAL_SCENARIO}",
                f"capability:{MODAL_PREDICTION}:conditional-carrier:{strength.marker}",
            ),
        )
    elif subject is None:
        verdict = NO_MARKET_ENTITY
    elif not (horizon or prospective):
        verdict = NO_FUTURE_ORIENTATION
    else:
        verdict = NO_OUTCOME

    signals = build(*future_signals) if future_signals else SignalSet(())
    return ModalDetection(
        verdict=verdict,
        strength=strength,
        signals=signals,
        evidence=(f"capability:{MODAL_PREDICTION}:{verdict}",),
    )


#: The id a modal finding cites, so a trace names the layer that produced it.
PATTERN_ID = "v3.1-modal-prediction"


def describe() -> dict[str, object]:
    """The capability's declared surface, for the report and the tests."""

    return {
        "capability": MODAL_PREDICTION,
        "pattern_id": PATTERN_ID,
        "signals": [MARKET_ENTITY, OUTCOME_EXPRESSION, UNCERTAIN_PREDICTION_MODAL, FUTURE_MARKER],
        "verdicts": list(VERDICTS),
        "declining_verdicts": list(DECLINING_VERDICTS),
        "rule": "guide v2 section 2: market_prediction requires certainty == certain",
        "strength_rule": "weakest carrier wins; a construction can carry strength",
        "comparison_lemmas": list(COMPARISON_LEMMAS),
        "non_directional_lemmas": list(NON_DIRECTIONAL_LEMMAS),
    }
