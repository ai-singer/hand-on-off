"""Rejection cues: the article arguing against a claim.

Phase 8.6's blind run had fifteen `author_rejection` cases and got five of them
right. The reason was not that rejection is hard to detect but that the Phase 8.2
cue table is short, and every one of the eight misses used a wording that is
plainly a rejection to a reader:

    We reject the suggestion that returns are guaranteed.
    We are unconvinced that capital is protected here.
    The idea that the fund cannot fall is not supported.
    We see no basis for the view that the price will triple.
    The assertion that losses are impossible is false.
    Claims that the fund is risk-free are overstated.
    We do not accept that the index will recover.
    We would not describe this as a safe bet.

The attribution layer is frozen for this phase, so the cues are declared here and
applied to its verdict rather than inside it.

Two things keep the expansion from becoming "any sentence containing `false`".
First, a cue is typed by **whose** rejection it is. A first-person refusal is the
author's. An impersonal denial - `is false`, `are overstated`, `is not supported`
- is the author's assessment of something the sentence presents, but only when
the sentence actually presents something to assess: `is false` needs a
proposition, which is a `that` clause or one of the claim nouns. Without that,
`The statement is false` and `The alarm is false` look alike, and only one of them
is about a claim.

Second, a rejection attributed to somebody else is reported as reported. `The
regulator rejected the claim that returns are guaranteed.` is the regulator's
act, not the article's, and overriding the stance to `rejected` there would
credit the article with an argument it is only relaying.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The article itself refuses or disputes a claim.
AUTHOR = "author"
#: Somebody else is reported as refusing or disputing it.
REPORTED = "reported"

VOICES: tuple[str, ...] = (AUTHOR, REPORTED)

#: Refusals in the first person. These need no proposition carrier: `we reject`
#: is a rejection whatever follows it.
_FIRST_PERSON: tuple[tuple[str, str], ...] = (
    (r"\bwe\s+(?:do\s+not|don't|would\s+not|wouldn't|will\s+not|won't)\s+accept\b", "refuse"),
    (r"\bwe\s+(?:do\s+not|don't)\s+accept\b", "refuse"),
    (r"\bwe\s+(?:would\s+not|wouldn't)\s+describe\b", "refuse"),
    (r"\bwe\s+reject\b|\bi\s+reject\b", "reject"),
    (r"\bwe\s+dispute\b|\bwe\s+contest\b", "dispute"),
    (r"\bwe\s+are\s+unconvinced\b|\bi\s+am\s+unconvinced\b", "unconvinced"),
    (r"\bwe\s+remain\s+unconvinced\b", "unconvinced"),
    (r"\bwe\s+(?:see|find)\s+no\s+(?:basis|evidence|reason)\b", "no-basis"),
    (r"\bwe\s+doubt\b|\bwe\s+question\s+(?:whether|that)\b", "doubt"),
    (r"\bwe\s+(?:do\s+not|don't)\s+(?:believe|agree|share)\b", "disagree"),
    (r"\bwe\s+(?:are\s+not|'re\s+not)\s+persuaded\b", "unconvinced"),
)

#: Impersonal denials of a proposition. Each needs a carrier in the sentence.
_IMPERSONAL: tuple[tuple[str, str], ...] = (
    (r"\b(?:is|are|was|were)\s+not\s+supported\b", "not-supported"),
    (r"\b(?:is|are|was|were)\s+unsupported\b", "not-supported"),
    (r"\b(?:is|are|was|were)\s+overstated\b", "overstated"),
    (r"\b(?:is|are|was|were)\s+(?:false|untrue|mistaken)\b", "declared-false"),
    (r"\bnot\s+(?:true|the\s+case|correct|accurate)\b", "not-true"),
    (r"\bthere\s+is\s+no\s+(?:evidence|basis|reason)\b", "no-evidence"),
    (r"\bno\s+evidence\s+(?:for|that|to\s+support)\b", "no-evidence"),
    (r"\bwithout\s+basis\b|\bunfounded\b|\bno\s+basis\s+for\b", "no-basis"),
    (r"\b(?:is|are)\s+a\s+myth\b", "declared-myth"),
    (r"\bcannot\s+be\s+substantiated\b", "not-substantiated"),
)

#: Contrasts that name what they are contradicting, so they carry their own
#: proposition and are not asked for one. `Contrary to the marketing, the return
#: is not guaranteed.` is the author disagreeing with a source it has just named.
_CONTRAST: tuple[tuple[str, str], ...] = (
    (
        r"\bcontrary\s+to\s+(?:the\s+|this\s+|that\s+)?"
        r"(?:marketing|advert|advertising|promotion|claim|claims|suggestion|"
        r"view|consensus|narrative|story|hype|sales\s+pitch)\b",
        "contrary-to",
    ),
    (r"\bdespite\s+(?:the\s+)?(?:marketing|advert|advertising|hype|claims?)\b", "despite"),
    (r"\bthis\s+contradicts\s+the\b", "contradicts"),
)

#: What an impersonal denial has to be *about* for it to be a rejection of a
#: claim rather than a comment on an object.
_PROPOSITION_CARRIER = re.compile(
    r"\b(?:that|claim|claims|assertion|assertions|idea|view|suggestion|"
    r"statement|statements|belief|notion|premise|assumption|thesis|argument|"
    r"story|narrative|implication)\b",
    re.IGNORECASE,
)

#: A rejection attributed to a third party.
_REPORTED: tuple[tuple[str, str], ...] = (
    (
        r"\b(?:regulators?|exchanges?|custodians?|trustees?|auditors?|analysts?|"
        r"traders?|officials?|the\s+bank|the\s+company|the\s+fund)\s+"
        r"(?:has\s+|have\s+)?(?:rejected|rejects|disputed|disputes|denied|denies|"
        r"refuted|refutes|dismissed|dismisses)\b",
        "reported-rejection",
    ),
)

#: Sentence terminators, matching the matcher's set.
_TERMINATORS = ".!?;\u3002\uff01\uff1f\uff1b\n"


class RejectionError(Exception):
    """Raised when a rejection finding is malformed."""


@dataclass(frozen=True, slots=True)
class RejectionFinding:
    """One rejection, with whose it is and what cue found it."""

    voice: str
    cue: str
    #: The matched cue text.
    text: str
    span: tuple[int, int]
    #: True when the sentence carried a proposition for the denial to be about.
    about_claim: bool = False

    def __post_init__(self) -> None:
        if self.voice not in VOICES:
            raise RejectionError(f"unknown rejection voice {self.voice!r}")
        if not self.text.strip():
            raise RejectionError("a rejection finding needs the text it matched")

    @property
    def is_authorial(self) -> bool:
        return self.voice == AUTHOR

    @property
    def marker(self) -> str:
        return f"rejection:{self.voice}:{self.cue}:{self.text.lower()}"

    def as_dict(self) -> dict[str, object]:
        return {
            "voice": self.voice,
            "cue": self.cue,
            "text": self.text,
            "span": list(self.span),
            "about_claim": self.about_claim,
        }


def sentence_span(text: str, position: int) -> tuple[int, int]:
    start = 0
    for index in range(min(position, len(text)) - 1, -1, -1):
        if text[index] in _TERMINATORS:
            start = index + 1
            break
    end = len(text)
    for index in range(max(position, 0), len(text)):
        if text[index] in _TERMINATORS:
            end = index + 1
            break
    return start, end


def _search(
    text: str, table: tuple[tuple[str, str], ...], voice: str
) -> RejectionFinding | None:
    best: tuple[int, str, str, tuple[int, int]] | None = None
    for pattern, cue in table:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is None:
            continue
        candidate = (match.start(), cue, match.group(0), match.span())
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        return None
    start, cue, matched, span = best
    _, sentence_end = sentence_span(text, start)
    sentence_start, _ = sentence_span(text, start)
    return RejectionFinding(
        voice=voice,
        cue=cue,
        text=matched,
        span=span,
        about_claim=bool(_PROPOSITION_CARRIER.search(text[sentence_start:sentence_end])),
    )


def detect(text: str) -> RejectionFinding | None:
    """The rejection this text expresses, if it expresses one.

    An author's refusal outranks a reported one: when the article both refuses a
    claim and reports somebody else refusing it, the article's own act is the one
    that decides the stance of the sentence it is in.
    """

    if not isinstance(text, str):
        raise RejectionError(f"text must be a string, got {type(text).__name__}")

    authorial = _search(text, _FIRST_PERSON, AUTHOR)
    if authorial is not None:
        return authorial

    contrast = _search(text, _CONTRAST, AUTHOR)
    if contrast is not None:
        return contrast

    impersonal = _search(text, _IMPERSONAL, AUTHOR)
    if impersonal is not None and impersonal.about_claim:
        return impersonal

    return _search(text, _REPORTED, REPORTED)


def describe() -> tuple[dict[str, object], ...]:
    """The cue table, for the report and the tests."""

    return tuple(
        {"voice": voice, "cue": cue, "pattern": pattern}
        for voice, table in (
            (AUTHOR, _FIRST_PERSON),
            (AUTHOR, _CONTRAST),
            (AUTHOR, _IMPERSONAL),
            (REPORTED, _REPORTED),
        )
        for pattern, cue in table
    )
