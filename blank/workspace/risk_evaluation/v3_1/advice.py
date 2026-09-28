"""Capability 2: an action-directive aimed at the reader, told apart from education.

Guide v2 section 7 gives advice one sentence of definition and one of boundary:

    an action-directive aimed at the reader *and* a financial object.
    Educational explanation and method guidance are negative.

Both halves were measured as broken. Six false negatives and three false
positives across the two probes, and neither kind is rare:

    You ought to trim your position.                        no directive object found
    It would be prudent to trim your holdings.               no frame covers `prudent to`
    A sensible investor would avoid this fund.               the directive is hedged by
                                                            `would`, so it is declined
    To reduce risk, hold a diversified portfolio.            method guidance
    Investors should hold a diversified portfolio.           method guidance
    When rates hold steady, bond fund income is unchanged.   `hold` with a subject
    Custodians hold fund assets in safekeeping.              `hold` with a subject
    Keep your cash in this fund.                             `keep` is not in the lexicon
    Stay invested in this fund.                              `stay` is not in the lexicon
    Remain in the fund until the merger closes.              `remain` is not in the lexicon

The phase names this surface and is explicit that the answer is not to disable
`hold`. It is not: disabling `hold` would lose `Hold this fund through the
downturn.` and every other real directive that uses the word. Structure separates
them, and the load-bearing test is **clause position**.

**The imperative test.** A directive in the imperative mood has no subject, so
the verb begins its clause. The same verb later in a clause has a subject, and a
sentence with a subject is a statement about that subject rather than an
instruction to the reader:

    Hold this fund through the downturn.          clause-initial   -> a directive
    Custodians hold fund assets in safekeeping.   not              -> a statement
    When rates hold steady, income is unchanged.  not              -> a statement
    If you want higher returns, buy this stock.   clause-initial   -> still a directive

The fourth row is why the test is clause position and not sentence position.
Guide v2 section 5 says a conditional *directive* is still advice, and `buy`
begins its clause even though it does not begin the sentence.

Verb *form* is the second half. A finite `-s` or `-ed` form is never an
imperative, and a gerund or infinitive heading a clause is that clause's subject:
`Holding diversified assets reduces risk.` starts with a verb form and has a
subject, so it is neither a directive nor advice.

**The method test.** `hold a diversified portfolio` and `hold this fund` are the
same verb in the same grammatical frame. One names a practice, the other a
position, and guide section 7 makes practice guidance negative. So the object's
specificity is the signal rather than the verb's identity.

**`would` is constitutive here.** `A sensible investor would avoid this fund.` is
declined today because Phase 8.4 marks `would` as a hedge. For a *prediction* it
is one - `The position would lose value` is hypothetical. Inside an advisory frame
it is not, and Phase 8.5 already made this decision for `should` in
`DIRECTIVE_MODALS`: a marker that constitutes a relation cannot also hedge it.
The advisory frames are declared and named, so `would` never becomes constitutive
on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..v3.model import ADVICE, IntentEvidence
from ..v3.morphology import alternation, gerund, inflect
from ..v3.patterns import ENTITIES
from ..v3_repair.sources import REPORTING_VERBS
from .signals import (
    ADDRESS,
    ADVICE_BOUNDARY,
    FINANCIAL_ACTION_OBJECT,
    IMPERATIVE_STRUCTURE,
    POSITION_ACTION,
    Signal,
    SignalSet,
    build,
)

#: The financial objects an action can be aimed at, including instruments: advice
#: is usually about what to do with a holding, and a holding is not a return.
OBJECT_ENTITIES: tuple[str, ...] = ("RETURN", "CAPITAL", "VALUE", "OUTCOME", "INSTRUMENT")

OBJECT = ENTITIES.group(*OBJECT_ENTITIES)

#: Verbs that act on a position. Acting on a position is what a reader can do with
#: advice; the object decides whether it is a position or a practice.
POSITION_LEMMAS: tuple[str, ...] = (
    "buy",
    "sell",
    "hold",
    "keep",
    "stay",
    "remain",
    "add",
    "trim",
    "reduce",
    "avoid",
    "shift",
    "move",
    "allocate",
    "invest",
    "acquire",
    "exit",
    "ditch",
    "dump",
    "reallocate",
    "overweight",
    "underweight",
    "stash",
    "park",
)

#: Verbs that name a practice rather than an action on a position. Guide v2
#: section 7 makes method guidance negative, so these never carry advice on their
#: own; they are listed so the verdict can cite the reason instead of reporting
#: silence.
METHOD_LEMMAS: tuple[str, ...] = (
    "diversify",
    "rebalance",
    "spread",
    "review",
    "monitor",
    "plan",
    "understand",
    "learn",
    "study",
    "budget",
    "save",
    "compare",
    "research",
    "check",
)

#: Verbs that introduce an action without being the action: `recommend buying` is
#: advice about buying, so the head verb is transparent and the frame carries it.
TRANSPARENT_LEMMAS: tuple[str, ...] = ("consider", "recommend", "suggest", "urge", "advise")

#: The subset whose complement is a directive **whoever the subject is**. Phase 8.5
#: labels `The newsletter recommends buying this stock.` as an ADVICE relation, and
#: it is right to: the newsletter is directing its readers, and guide v2 section
#: 3.1 gives the attribution layer - not this one - the job of deciding whether the
#: article is the one advising. `consider` is deliberately not here: a fund that
#: considers moving its listing is not advising anybody.
RECOMMENDATION_LEMMAS: tuple[str, ...] = ("recommend", "suggest", "urge", "advise")

POSITION_VERBS = alternation(POSITION_LEMMAS)
METHOD_VERBS = alternation(METHOD_LEMMAS)
TRANSPARENT = alternation(TRANSPARENT_LEMMAS)

#: The bare forms, for tests that must tell a base verb from a gerund. An
#: imperative is a base form; `Buy this stock` is a directive and `Buying this
#: stock` is a subject, and the two differ only in that ending.
POSITION_BARE = "|".join(sorted(set(POSITION_LEMMAS), key=lambda item: (-len(item), item)))
METHOD_BARE = "|".join(sorted(set(METHOD_LEMMAS), key=lambda item: (-len(item), item)))
TRANSPARENT_BARE = "|".join(
    sorted(set(TRANSPARENT_LEMMAS), key=lambda item: (-len(item), item))
)
RECOMMENDATION_FORMS = alternation(RECOMMENDATION_LEMMAS)

#: Every inflection back to its lemma. A trace should name the action, not the
#: form: `Consider moving your capital` is advice about moving, and reporting the
#: directive as `moving` would make one action look like two depending on how the
#: sentence was written.
_DIRECTIVE_LEMMA: dict[str, str] = {}
for _lemma in (*POSITION_LEMMAS, *METHOD_LEMMAS):
    for _form in inflect(_lemma):
        _DIRECTIVE_LEMMA.setdefault(_form, _lemma)


def _lemma_of(form: str) -> str:
    return _DIRECTIVE_LEMMA.get(form.lower(), form.lower())

#: Gerunds, generated rather than listed - the same discipline as the movement
#: verbs. `Holding`, `keeping`, `staying` and `remaining` are all gerund subjects.
POSITION_GERUNDS = "|".join(
    sorted({gerund(lemma) for lemma in POSITION_LEMMAS}, key=lambda item: (-len(item), item))
)
METHOD_GERUNDS = "|".join(
    sorted({gerund(lemma) for lemma in METHOD_LEMMAS}, key=lambda item: (-len(item), item))
)
TRANSPARENT_GERUNDS = "|".join(
    sorted({gerund(lemma) for lemma in TRANSPARENT_LEMMAS}, key=lambda item: (-len(item), item))
)

#: Second-person and reader address. An imperative has no subject, so this is what
#: a non-imperative directive aimed at the reader looks like.
ADDRESSEES = (
    r"you|your|yourselves|readers?|investors?|clients?|customers?|savers?|holders?|"
    r"shareholders?|subscribers?"
)

#: A directive addressed to a role rather than to the reader. Reported, not written:
#: `The exchange said traders should reduce their exposure.` is a directive and the
#: attribution layer decides whose it is (guide 3.1). `Traders should reduce their
#: exposure.` with nothing reporting it is a statement about traders, and requiring
#: the reporting frame is what keeps that one out.
ROLE_ADDRESSEES = (
    r"traders?|brokers?|dealers?|analysts?|economists?|strategists?|commentators?|"
    r"observers?|fund\s+managers?|portfolio\s+managers?|managers?"
)

#: Modal address: an addressee plus a modal that constitutes the directive.
ADDRESS_MODALS = (
    r"should|ought\s+to|must|need\s+to|have\s+to|had\s+better|"
    r"may\s+want\s+to|might\s+want\s+to|will\s+want\s+to|are\s+better\s+off\s+to"
)

#: Clauses begin after these. A directive may begin any clause, not only the
#: sentence: guide v2 section 5 keeps `If you want higher returns, buy this
#: stock.` as advice.
_CLAUSE_SPLIT = re.compile(r"[,;:\u2013\u2014]|\s+but\s+|\s+yet\s+")

#: A purpose clause in front of the directive: `To reduce risk, hold ...`. The
#: directive begins the clause after it, and the purpose clause is what makes the
#: sentence read as guidance rather than as an instruction.
_PURPOSE = re.compile(r"^\s*to\s+(?P<verb>[a-z]+)\b[^,;]*[,;]\s*", re.IGNORECASE)

#: Advisory frames: a construction that makes what follows a recommendation in the
#: author's voice. Each is named, and each is what makes `would` constitutive
#: rather than hedging - the frame is the evidence, not the modal.
ADVISORY_FRAMES: tuple[tuple[str, str], ...] = (
    (
        "prudent_to",
        r"it\s+(?:would\s+be|is|seems|looks|may\s+be)\s+"
        r"(?:prudent|wise|sensible|better|advisable|reasonable)\s+to",
    ),
    (
        "sensible_investor",
        r"a\s+(?:sensible|prudent|cautious|wise|rational)\s+"
        r"(?:investor|reader|saver|holder)\s+would",
    ),
    (
        "would_be_wise",
        r"(?:investors?|readers?|you|clients?|savers?|holders?)\s+would\s+be\s+"
        r"(?:wise|prudent|better\s+off|sensible)\s+to",
    ),
    (
        "are_advised",
        r"(?:investors?|readers?|you|clients?|savers?|holders?)\s+(?:are|were)\s+"
        r"(?:advised|urged|recommended|counselled)\s+to",
    ),
    (
        "author_recommends",
        r"\b(?:we|i)\s+(?:would\s+|strongly\s+)?"
        r"(?:recommend|suggest|urge|advise)\b",
    ),
    (
        "now_is_the_time",
        r"now\s+is\s+(?:the|a)\s+(?:time|moment|good\s+time|good\s+moment)\s+to",
    ),
    (
        "best_move",
        r"(?:the\s+)?(?:sensible|obvious|best|only|right)\s+"
        r"(?:move|choice|action|option|course)\b[^.;]{0,40}?\b(?:is|would\s+be)\s+to",
    ),
    (
        "worth_doing",
        r"it\s+is\s+worth\s+(?:\w+ing)\b",
    ),
)

#: Objects that name a practice rather than a position. Guide v2 section 7: method
#: guidance is negative. These are indefinite or abstract, which is what makes them
#: methods: `a diversified portfolio` is a practice, `this fund` is a holding.
METHOD_OBJECTS: tuple[str, ...] = (
    r"a\s+diversified\s+portfolio",
    r"a\s+portfolio",
    r"portfolios?",
    r"diversified\s+assets?",
    r"a\s+mix\s+of\s+assets?",
    r"asset\s+classes?",
    r"asset\s+allocation",
    r"index\s+funds?",
    r"a\s+range\s+of\s+(?:funds?|assets?|holdings?)",
    r"cash\s+and\s+equivalents?",
    r"costs?",
    r"fees?",
    r"charges?",
    r"risks?",
    r"your\s+time\s+horizon",
    r"an?\s+emergency\s+fund",
)

METHOD_OBJECT = "(?:" + "|".join(METHOD_OBJECTS) + ")"

#: A definite or specific object: a position the reader holds or could hold.
_SPECIFIC_NOUNS = (
    r"fund|funds|stock|stocks|share|shares|bond|bonds|equity|equities|"
    r"position|positions|holding|holdings|portfolio|exposure|stake|"
    r"investment|investments|money|capital|savings|deposit|cash|account|"
    r"sector|index|trust|scheme|product|company|"
    r"shorter-dated\s+bonds|corporate\s+bonds|government\s+bonds"
)
_SPECIFIC_DETERMINERS = r"this|that|the|these|those|your|our|its|their"

SPECIFIC_OBJECT = rf"(?:{_SPECIFIC_DETERMINERS})\s+(?:{_SPECIFIC_NOUNS})"

#: A prepositional object: `Stay invested in this fund.` and `Remain in the fund.`
#: aim at a financial object with no direct object at all.
PREPOSITIONAL_OBJECT = (
    rf"\b(?:in|into|out\s+of|from|towards?|with)\s+"
    rf"(?:{_SPECIFIC_DETERMINERS})?\s*(?:{_SPECIFIC_NOUNS})\b"
)

#: Verbs that only apply to something holdable. `buy the dip` and `sell the
#: top` name their object in market shorthand that no noun list carries, and the
#: verb settles the question: you cannot buy or sell a practice. So for these
#: verbs a definite object is a financial object, and for the others it is not.
ACQUISITION_LEMMAS: tuple[str, ...] = (
    "buy",
    "sell",
    "acquire",
    "invest",
    "dump",
    "ditch",
    "exit",
    "stash",
    "park",
    "trim",
    "add",
)

ACQUISITION_BARE = "|".join(
    sorted(set(ACQUISITION_LEMMAS), key=lambda item: (-len(item), item))
)

#: Any definite object. Only consulted for an acquisition verb, where the verb
#: itself establishes that the object is holdable.
DEFINITE_OBJECT = rf"\b(?:{_SPECIFIC_DETERMINERS})\s+[a-z][a-z'\-]*"

#: Verdicts. `advice` is the only one that reports a relation; the rest name why
#: there is none.
ADVICE_VERDICT = "advice"
METHOD_GUIDANCE = "method_guidance"
GERUND_SUBJECT = "gerund_subject"
INFINITIVE_SUBJECT = "infinitive_subject"
THIRD_PERSON_SUBJECT = "third_person_subject"
PREPOSITIONAL_GERUND = "prepositional_gerund"
NO_ADDRESSEE = "no_addressee"
NO_FINANCIAL_OBJECT = "no_financial_object"
NO_DIRECTIVE = "no_directive"

VERDICTS: tuple[str, ...] = (
    ADVICE_VERDICT,
    METHOD_GUIDANCE,
    GERUND_SUBJECT,
    INFINITIVE_SUBJECT,
    THIRD_PERSON_SUBJECT,
    PREPOSITIONAL_GERUND,
    NO_ADDRESSEE,
    NO_FINANCIAL_OBJECT,
    NO_DIRECTIVE,
)

#: Verdicts that are positive evidence against advice, and so may decline the
#: category the semantic fallback would otherwise keep. The `no_*` verdicts are
#: excluded for the same reason as in the modal layer: "not my shape" is not
#: evidence that no advice is present.
DECLINING_VERDICTS: tuple[str, ...] = (
    GERUND_SUBJECT,
    INFINITIVE_SUBJECT,
    THIRD_PERSON_SUBJECT,
    PREPOSITIONAL_GERUND,
    METHOD_GUIDANCE,
)

#: A gerund that heads a noun phrase is a noun, not a verb in a clause.
#: `Diversification lowers the impact of any single holding.` has no directive in it
#: at all, and a layer that read `holding` as a verb reported the sentence as a
#: statement about a subject that does not exist.
_NOUN_PHRASE = re.compile(
    r"(?:^|\s)(?:the|a|an|this|that|these|those|any|each|every|no|its|their|our|"
    r"your|his|her|single|only|first|second|third|other|another|main|whole|total|"
    r"such)\s+(?:\w+\s+){0,2}$",
    re.IGNORECASE,
)


class AdviceError(Exception):
    """Raised when advice cannot be evaluated."""


@dataclass(frozen=True, slots=True)
class AdviceDetection:
    """What the advice layer found, and what it concluded."""

    verdict: str
    boundary: str
    signals: SignalSet = SignalSet(())
    span: tuple[int, int] = (0, 0)
    addressee: str = ""
    directive: str = ""
    target: str = ""
    structure: str = ""
    finding: IntentEvidence | None = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise AdviceError(f"unknown verdict {self.verdict!r}")

    @property
    def declared(self) -> bool:
        return self.finding is not None

    @property
    def declines(self) -> bool:
        return self.verdict in DECLINING_VERDICTS

    @property
    def declined_categories(self) -> tuple[str, ...]:
        return ("investment_advice",) if self.declines else ()

    @property
    def signal_names(self) -> tuple[str, ...]:
        return self.signals.names

    def as_dict(self) -> dict[str, object]:
        return {
            "capability": ADVICE_BOUNDARY,
            "verdict": self.verdict,
            "boundary": self.boundary,
            "signals": self.signals.as_dict(),
            "span": list(self.span),
            "addressee": self.addressee,
            "directive": self.directive,
            "target": self.target,
            "structure": self.structure,
            "declared": self.declared,
            "declines": self.declines,
            "declined_categories": list(self.declined_categories),
            "evidence": list(self.evidence),
        }


def clauses(text: str) -> tuple[tuple[int, str], ...]:
    """The clauses of `text`, with the offset each starts at.

    A directive may begin any clause. `If you want higher returns, buy this stock.`
    is advice in guide v2 section 5, and `buy` begins its clause without beginning
    the sentence.
    """

    parts: list[tuple[int, str]] = []
    position = 0
    for piece in _CLAUSE_SPLIT.split(text):
        if not piece:
            position += 1
            continue
        start = text.find(piece, position)
        if start < 0:  # pragma: no cover - defensive
            start = position
        parts.append((start, piece))
        position = start + len(piece)
    return tuple(parts)


def _specificity(text: str) -> tuple[str, str]:
    """The object's class: `specific`, `method`, or neither."""

    method = re.search(METHOD_OBJECT, text, re.IGNORECASE)
    specific = re.search(SPECIFIC_OBJECT, text, re.IGNORECASE)
    if method is not None and (specific is None or method.start() <= specific.start()):
        return "method", method.group(0).lower()
    if specific is not None:
        return "specific", specific.group(0).lower()
    return "", ""


def _signals(
    span: tuple[int, int],
    addressee: str,
    structure: str,
    directive: str,
    target: str,
    kind: str,
) -> SignalSet:
    found = [
        Signal(ADDRESS, span, addressee or "none", structure or "unknown"),
        Signal(IMPERATIVE_STRUCTURE, span, structure or "unknown", addressee or "none"),
    ]
    if target:
        found.append(
            Signal(FINANCIAL_ACTION_OBJECT, span, target, kind or "unknown")
        )
        found.append(
            Signal(POSITION_ACTION, span, directive or "", "position" if kind == "specific" else "method")
        )
    return build(*found)


def evaluate(text: str) -> AdviceDetection:
    """Evaluate one claim's text for an action-directive aimed at the reader."""

    if not isinstance(text, str):
        raise AdviceError(f"text must be a string, got {type(text).__name__}")

    # -- a gerund or infinitive heading a clause is that clause's subject, so it
    # is not a directive. The gerund is required, not merely a verb form: `Buy
    # this stock` is an imperative and `Buying this stock` is a subject, and a
    # test that could not tell them apart would lose every real directive.
    gerund_head = re.match(
        rf"\s*(?P<form>{POSITION_GERUNDS}|{METHOD_GERUNDS}|{TRANSPARENT_GERUNDS}|"
        rf"being|having)\s+",
        text,
        re.IGNORECASE,
    )
    if gerund_head is not None:
        return _decline(
            GERUND_SUBJECT,
            text,
            form=gerund_head.group("form").lower(),
            reason="the-verb-heads-a-subject-not-a-directive",
        )

    infinitive_head = re.match(r"\s*to\s+(?P<form>[a-z]+)\b", text, re.IGNORECASE)
    if infinitive_head is not None and re.search(
        r"\b(?:is|are|was|were)\s+to\b", text, re.IGNORECASE
    ):
        return _decline(
            INFINITIVE_SUBJECT,
            text,
            form=infinitive_head.group("form").lower(),
            reason="an-infinitive-subject-is-not-a-directive",
        )

    # -- a purpose clause in front of the directive. `To reduce risk, hold a
    # diversified portfolio.` is a directive in its main clause, and a layer that
    # only looked at the first word would see an infinitive and stop.
    purpose = _PURPOSE.match(text)
    main = text
    offset = 0
    if purpose is not None:
        trimmed = text[purpose.end():]
        if trimmed.strip():
            offset = purpose.end()
            main = trimmed

    # -- a gerund after a preposition: `the annual cost of holding a fund`. `to`
    # is not in the list: after a modal or an advisory frame it is the infinitive
    # marker, not a preposition, and `ought to trim` is a directive.
    prepositional = re.search(
        rf"\b(?:of|for|in|by|with|without|about|on|after|before)\s+"
        rf"(?P<form>{POSITION_GERUNDS})\b",
        main,
        re.IGNORECASE,
    )
    if prepositional is not None:
        return _decline(
            PREPOSITIONAL_GERUND,
            text,
            form=prepositional.group("form").lower(),
            reason="a-gerund-after-a-preposition-names-a-practice",
        )

    # -- the structure. Three shapes, checked in the order a reader would use
    # them: the directive itself, an addressed modal, then an advisory frame.
    address_match = re.search(
        rf"\b(?P<addressee>{ADDRESSEES})\s+(?P<modal>{ADDRESS_MODALS})\s+"
        rf"(?:(?P<transparent>{TRANSPARENT_BARE})\s+)?"
        rf"(?P<verb>{POSITION_BARE}|{METHOD_BARE})\b",
        main,
        re.IGNORECASE,
    )
    frame_name = ""
    frame_match = None
    for name, pattern in ADVISORY_FRAMES:
        found = re.search(pattern, main, re.IGNORECASE)
        if found is not None:
            frame_name, frame_match = name, found
            break

    imperative = _clause_initial_directive(main)

    # -- a recommendation verb whose complement is the directive. `The newsletter
    # recommends buying this stock.` directs its readers whatever the subject is,
    # and the ADVICE relation is present even though the article is only reporting
    # it. Guide section 3.1 hands that question to the attribution layer.
    recommended = re.search(
        rf"\b(?P<transparent>{RECOMMENDATION_FORMS})\s+"
        rf"(?P<verb>{POSITION_GERUNDS}|{POSITION_BARE})\b",
        main,
        re.IGNORECASE,
    )
    reported_address = re.search(
        rf"\b(?:{REPORTING_VERBS})\s+(?:the\s+|its\s+|their\s+)?"
        rf"(?P<addressee>{ROLE_ADDRESSEES})\s+(?P<modal>{ADDRESS_MODALS})\s+"
        rf"(?:(?P<transparent>{TRANSPARENT_BARE})\s+)?"
        rf"(?P<verb>{POSITION_BARE}|{METHOD_BARE})\b",
        main,
        re.IGNORECASE,
    )

    structure = ""
    addressee = ""
    directive = ""
    span = (0, 0)
    if imperative is not None:
        structure, addressee = "imperative", "reader"
        directive = _lemma_of(imperative.group("verb"))
        span = imperative.span()
    elif address_match is not None:
        structure = "modal_address"
        addressee = address_match.group("addressee").lower()
        directive = _lemma_of(address_match.group("verb"))
        span = address_match.span()
    elif frame_match is not None:
        structure = f"advisory_frame:{frame_name}"
        addressee = "reader"
        span = frame_match.span()
        following = re.search(
            rf"\b(?P<verb>{POSITION_BARE}|{METHOD_BARE})\b",
            main[frame_match.end():],
            re.IGNORECASE,
        )
        directive = _lemma_of(following.group("verb")) if following is not None else ""
    elif recommended is not None:
        structure = "reported_directive"
        addressee = "reported"
        directive = _lemma_of(recommended.group("verb"))
        span = recommended.span()
    elif reported_address is not None:
        structure = "reported_address"
        addressee = reported_address.group("addressee").lower()
        directive = _lemma_of(reported_address.group("verb"))
        span = reported_address.span()

    if not structure:
        # A directive verb later in a clause has a subject, so the sentence is a
        # statement about that subject. This is the test the phase is asking for:
        # it is what separates `Custodians hold fund assets.` from `Hold this fund.`
        # A gerund heading a noun phrase is skipped: `any single holding` is a noun.
        late = _verbal_positions(main)
        if late is not None:
            return _decline(
                THIRD_PERSON_SUBJECT,
                text,
                form=late.group("verb").lower(),
                reason="a-verb-with-a-subject-is-not-an-imperative",
            )
        method = re.search(rf"\b(?P<verb>{METHOD_BARE})\b", main, re.IGNORECASE)
        if method is not None:
            return _decline(
                METHOD_GUIDANCE,
                text,
                form=method.group("verb").lower(),
                reason="method-guidance-is-negative",
                addressee=addressee,
                structure="method",
            )
        return AdviceDetection(
            verdict=NO_DIRECTIVE,
            boundary=NO_DIRECTIVE,
            evidence=(f"capability:{ADVICE_BOUNDARY}:{NO_DIRECTIVE}",),
        )

    # -- the object decides whether it is a position or a practice
    kind, target = _specificity(main)
    if not target:
        prepositional_target = re.search(PREPOSITIONAL_OBJECT, main, re.IGNORECASE)
        if prepositional_target is not None:
            kind, target = "specific", prepositional_target.group(0).lower()
    if not target:
        entity = re.search(rf"\b(?:{OBJECT})", main, re.IGNORECASE)
        if entity is not None:
            kind, target = "specific", entity.group(0).lower()
    if not target and re.search(
        rf"\b(?:{ACQUISITION_BARE})\b", directive or "", re.IGNORECASE
    ):
        held = re.search(DEFINITE_OBJECT, main, re.IGNORECASE)
        if held is not None and not re.search(METHOD_OBJECT, held.group(0), re.IGNORECASE):
            kind, target = "specific", held.group(0).lower()

    shifted = (span[0] + offset, span[1] + offset)
    found = _signals(shifted, addressee, structure, directive, target, kind)

    if kind == "method" or directive in METHOD_LEMMAS:
        return AdviceDetection(
            verdict=METHOD_GUIDANCE,
            boundary=METHOD_GUIDANCE,
            signals=found,
            span=shifted,
            addressee=addressee,
            directive=directive,
            target=target,
            structure=structure,
            evidence=(
                f"capability:{ADVICE_BOUNDARY}:{METHOD_GUIDANCE}",
                f"capability:advice_boundary:practice-not-position:{target or directive}",
                *found.markers,
            ),
        )

    if not target:
        return AdviceDetection(
            verdict=NO_FINANCIAL_OBJECT,
            boundary=NO_FINANCIAL_OBJECT,
            signals=found,
            span=shifted,
            addressee=addressee,
            directive=directive,
            structure=structure,
            evidence=(
                f"capability:{ADVICE_BOUNDARY}:{NO_FINANCIAL_OBJECT}",
                "capability:advice_boundary:a-directive-needs-a-financial-object",
                *found.markers,
            ),
        )

    # -- the relation is reported whether or not the article is the one advising.
    # `Analysts say investors should buy the dip.` is a directive, and guide
    # section 3.1 gives the *attribution* layer the job of deciding whether it is
    # the article's, not this one.
    finding = IntentEvidence(
        relation=ADVICE,
        entity="",
        frame="active" if structure == "imperative" else "copular",
        predicate=directive,
        pattern_id=PATTERN_ID,
        span=shifted,
        signals=found.names,
        boundary=structure,
    )
    return AdviceDetection(
        verdict=ADVICE_VERDICT,
        boundary=structure,
        signals=found,
        span=shifted,
        addressee=addressee,
        directive=directive,
        target=target,
        structure=structure,
        finding=finding,
        evidence=(
            f"capability:{ADVICE_BOUNDARY}:{ADVICE_VERDICT}",
            f"capability:advice_boundary:structure:{structure}",
            f"capability:advice_boundary:addressee:{addressee}",
            *found.markers,
        ),
    )


def _verbal_positions(text: str):
    """The first position verb in `text` that is a verb rather than a noun.

    A gerund heading a noun phrase is skipped. `Diversification lowers the impact of
    any single holding.` contains a form of `hold`, and it is the object of a
    sentence that has no directive in it; reading it as a verb produced a
    third-person-subject verdict for a sentence with no verb to be the subject of.
    """

    for match in re.finditer(
        rf"\b(?P<verb>{alternation(POSITION_LEMMAS)[3:-1]})\b", text, re.IGNORECASE
    ):
        form = match.group("verb").lower()
        if form.endswith("ing") and _NOUN_PHRASE.search(text[: match.start()]):
            continue
        return match
    return None


def _clause_initial_directive(text: str):
    """A directive verb that begins one of the text's clauses, if there is one.

    Two shapes, and the second is why this is not a one-line test.
    `Hold this fund.` begins with the directive. `Consider moving your capital.`
    begins with a verb that introduces the directive instead of being it, and a
    layer that only knew the direct shape read `moving` as a gerund with a subject
    and declined the sentence - which is a false negative on text the Phase 8.5
    benchmark had right all along.
    """

    direct = r"\s*(?P<verb>{bare})\b".format(bare=POSITION_BARE)
    introduced = (
        r"\s*(?P<transparent>{transparent})\s+"
        r"(?P<verb>{bare}|{gerunds})\b"
    ).format(
        transparent=TRANSPARENT_BARE, bare=POSITION_BARE, gerunds=POSITION_GERUNDS
    )

    for start, piece in clauses(text):
        for pattern in (direct, introduced):
            match = re.match(pattern, piece, re.IGNORECASE)
            if match is not None:
                return _Shifted(match, start)
    for pattern in (direct, introduced):
        match = re.match(pattern, text, re.IGNORECASE)
        if match is not None:
            return _Shifted(match, 0)
    return None


class _Shifted:
    """A match whose spans are relative to an offset in the original text."""

    def __init__(self, match: re.Match[str], offset: int) -> None:
        self._match = match
        self._offset = offset

    def group(self, name: str) -> str:
        return self._match.group(name)

    def span(self, name: str | int = 0) -> tuple[int, int]:
        start, end = self._match.span(name)
        return start + self._offset, end + self._offset


def _decline(
    verdict: str,
    text: str,
    *,
    form: str,
    reason: str,
    addressee: str = "",
    structure: str = "",
) -> AdviceDetection:
    """A declined verdict, with the signal that carried it and why."""

    span = (0, len(text))
    found = _signals(span, addressee or "none", structure or reason, form, "", "")
    return AdviceDetection(
        verdict=verdict,
        boundary=verdict,
        signals=found,
        span=span,
        addressee=addressee,
        directive=_lemma_of(form),
        structure=structure,
        evidence=(
            f"capability:{ADVICE_BOUNDARY}:{verdict}",
            f"capability:advice_boundary:{reason}",
            *found.markers,
        ),
    )


#: The id an advice finding cites, so a trace names the layer that produced it.
PATTERN_ID = "v3.1-advice-boundary"


def describe() -> dict[str, object]:
    """The capability's declared surface, for the report and the tests."""

    return {
        "capability": ADVICE_BOUNDARY,
        "pattern_id": PATTERN_ID,
        "signals": [
            ADDRESS,
            IMPERATIVE_STRUCTURE,
            FINANCIAL_ACTION_OBJECT,
            POSITION_ACTION,
        ],
        "verdicts": list(VERDICTS),
        "declining_verdicts": list(DECLINING_VERDICTS),
        "rule": (
            "guide v2 section 7: an action-directive aimed at the reader and a "
            "financial object; educational explanation and method guidance are negative"
        ),
        "position_lemmas": list(POSITION_LEMMAS),
        "method_lemmas": list(METHOD_LEMMAS),
        "advisory_frames": [name for name, _ in ADVISORY_FRAMES],
        "would_is_constitutive": "inside a declared advisory frame only",
        "imperative_test": "clause-initial, base form, no subject",
    }
