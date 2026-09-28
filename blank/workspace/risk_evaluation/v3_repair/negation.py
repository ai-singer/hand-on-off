"""Which denial a `not` is making.

Phase 8.6 left three guarantee sentences in three different states and the
pipeline could not tell them apart:

    Case A   Returns are guaranteed.                    a guarantee is asserted
    Case B   Returns are not guaranteed.                the predicate is denied
    Case C   It is not true that returns are guaranteed. the *claim* is denied

The Phase 8.4 matcher reports one boolean, `negated`, and it is right about all
three: Case A is not negated, Cases B and C are. What the boolean cannot say is
*what* is being denied, and the difference matters for a different reason in each
case. Case B denies the outcome, so nothing is being promised. Case C denies that
anybody promised anything, which is a claim about a claim rather than about the
returns.

This module resolves the boolean into a scope. It does **not** touch the negation
guard: Phase 8.4's `is_negated` still decides *whether* a frame is negated, and
deleting or weakening it was explicitly ruled out. This is a refinement on top of
a verdict that has already been taken, which is why it can be added without
changing any frame's meaning.

The distinction is drawn from where the negation sits relative to the predicate:

    positive        no negator governs the predicate
    local           a negator governs the predicate itself
    propositional   a denial predicate governs a clause that contains the frame

A propositional marker sitting *inside* the predicate span is not propositional:
`Returns are not guaranteed.` has `not` inside the frame and it denies the
predicate, not the claim. Only a marker outside the predicate span can be scoping
over the whole proposition.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Scope names. `positive` is the absence of a denial, not a kind of one.
POSITIVE = "positive"
LOCAL = "local"
PROPOSITIONAL = "propositional"

SCOPES: tuple[str, ...] = (POSITIVE, LOCAL, PROPOSITIONAL)

#: Negators that govern the predicate. The list is the matcher's own, restated
#: here only for the report: which one was found is what makes the scope
#: auditable, so the marker text is carried in the evidence.
LOCAL_NEGATORS = re.compile(
    r"\b(?:not|never|no|neither|nor|without|cannot|can't|won't|don't|doesn't|"
    r"didn't|isn't|aren't|wasn't|weren't|n't)\b|(?:\u4e0d|\u6ca1|\u65e0|\u975e|\u672a)",
    re.IGNORECASE,
)

#: Predicates that deny a *proposition* rather than a predicate. Each entry is a
#: named rule, so a trace can cite which one fired and a test can exercise one at
#: a time. A phrase that denies a proposition without naming the proposition is
#: not here: `is false` on its own denies whatever precedes it, and the sentence
#: is what decides whether that is a claim.
PROPOSITIONAL_MARKERS: tuple[tuple[str, str], ...] = (
    (r"\bnot\s+(?:true|the\s+case|correct|accurate|so)\b", "not-true"),
    (r"\b(?:is|are|was|were)\s+(?:false|untrue|mistaken)\b", "declared-false"),
    (r"\b(?:is|are|was|were)\s+not\s+supported\b", "not-supported"),
    (r"\b(?:is|are|was|were)\s+unsupported\b", "not-supported"),
    (r"\b(?:is|are|was|were)\s+overstated\b", "overstated"),
    (r"\bno\s+evidence\s+(?:for|that|to\s+support)\b", "no-evidence"),
    (r"\bthere\s+is\s+no\s+(?:evidence|basis)\b", "no-evidence"),
    (r"\b(?:denies|denied|deny|disputes?|disputed|refutes?|refuted)\s+that\b", "denied"),
    (r"\brejects?\s+the\s+(?:claim|suggestion|idea|assertion|view)\b", "rejected-claim"),
    (r"\bwithout\s+basis\b|\bunfounded\b|\bno\s+basis\b", "no-basis"),
    (r"\bis\s+a\s+myth\b", "declared-myth"),
    (r"\bcontrary\s+to\b", "contrary-to"),
    (r"\bunconvinced\b", "unconvinced"),
)

_COMPILED: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), name)
    for pattern, name in PROPOSITIONAL_MARKERS
)

#: Sentence terminators, matching the matcher's set.
_TERMINATORS = ".!?;\u3002\uff01\uff1f\uff1b\n"


class NegationError(Exception):
    """Raised when a scope cannot be resolved."""


@dataclass(frozen=True, slots=True)
class NegationScope:
    """What a negation governs, with the marker that decided it."""

    scope: str
    #: The negator or denial predicate found, lowercased.
    marker: str = ""
    #: Where the marker is, in the text the frame was matched against.
    span: tuple[int, int] = (0, 0)

    def __post_init__(self) -> None:
        if self.scope not in SCOPES:
            raise NegationError(f"unknown negation scope {self.scope!r}")

    @property
    def negated(self) -> bool:
        return self.scope != POSITIVE

    @property
    def denies_claim(self) -> bool:
        """Is the claim itself denied, rather than its predicate?"""

        return self.scope == PROPOSITIONAL

    @property
    def marker_text(self) -> str:
        return f"{self.scope}:{self.marker}" if self.marker else self.scope

    def as_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "marker": self.marker,
            "span": list(self.span),
        }


def sentence_span(text: str, position: int) -> tuple[int, int]:
    """The sentence around `position`, as the matcher defines a sentence."""

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


def propositional_marker(
    text: str, *, outside: tuple[int, int]
) -> tuple[str, str, tuple[int, int]] | None:
    """The first denial predicate governing `text`, ignoring matches inside `outside`.

    `outside` is the predicate span. A marker that *is* the predicate is the
    predicate being denied, not a denial of the claim.
    """

    start, end = sentence_span(text, max(outside[0], 0))
    sentence = text[start:end]
    candidates: list[tuple[int, str, str]] = []
    for pattern, name in _COMPILED:
        for match in pattern.finditer(sentence):
            absolute = start + match.start()
            # A marker overlapping the predicate is the predicate's own denial.
            if absolute < outside[1] and (start + match.end()) > outside[0]:
                continue
            candidates.append((absolute, name, match.group(0)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    position, name, marker = candidates[0]
    return name, marker.lower(), (position, position + len(marker))


def local_negator(
    text: str, *, frame: tuple[int, int], predicate: tuple[int, int]
) -> tuple[str, tuple[int, int]] | None:
    """The negator inside or just before the frame, if there is one.

    The window may not cross a sentence boundary, and the boundary is searched for
    only *before* the predicate. Searching as far as the end of the predicate
    finds the sentence's own terminator - `Returns are not guaranteed.` ends one
    character after the predicate - and trimming there leaves an empty window, so
    a local negator would be reported with no marker at all.
    """

    window_start = max(0, frame[0] - 30)
    limit = max(predicate[0], frame[0])
    for terminator in _TERMINATORS:
        cut = text.rfind(terminator, window_start, limit)
        if cut >= 0:
            window_start = max(window_start, cut + 1)
    window = text[window_start : predicate[1]]
    match = LOCAL_NEGATORS.search(window)
    if not match:
        return None
    start = window_start + match.start()
    return match.group(0).lower(), (start, start + len(match.group(0)))


def classify(
    text: str,
    *,
    frame_span: tuple[int, int],
    predicate_span: tuple[int, int],
    negated: bool,
) -> NegationScope:
    """Resolve a frame's negation into the scope it actually governs.

    `negated` is the Phase 8.4 matcher's verdict and is treated as final: this
    function never turns a negated frame into an asserted one, and never invents
    a negation the guard did not find.
    """

    if not negated:
        return NegationScope(POSITIVE)

    denial = propositional_marker(text, outside=predicate_span)
    if denial is not None:
        name, marker, span = denial
        return NegationScope(PROPOSITIONAL, f"{name}:{marker}", span)

    found = local_negator(text, frame=frame_span, predicate=predicate_span)
    if found is None:
        # Negated, but by something this module cannot point at - the matcher's
        # guard reads a wider window than the frame. Report the local scope with
        # no marker rather than guessing a wider one.
        return NegationScope(LOCAL)
    marker, span = found
    return NegationScope(LOCAL, marker, span)


def describe() -> tuple[dict[str, object], ...]:
    """The scope table, for the report and the tests."""

    return tuple(
        {"scope": scope, "meaning": meaning}
        for scope, meaning in (
            (POSITIVE, "no negation governs the predicate"),
            (LOCAL, "a negator governs the predicate itself"),
            (PROPOSITIONAL, "a denial predicate governs the clause carrying the frame"),
        )
    )
