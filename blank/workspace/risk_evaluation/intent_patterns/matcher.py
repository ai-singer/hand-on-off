"""Relation matcher: find a relation between an entity and a predicate.

Not keyword expansion. The matcher runs a pattern's *frames* over the text and
binds the roles each frame names, so the same relation is found in any of the
syntactic shapes that realise it:

    active       We guarantee this return.
    passive      Your returns are guaranteed by the scheme.
    copular      This return is guaranteed.
    attributive  This is a guaranteed return.
    nominal      The fund offers a guarantee of returns.

Negation and hedging are recorded **on the match**, not used to filter it out
silently. `not guaranteed` produces a matched frame with `negated=True`, and
`according to the marketing material` produces one with `hedge` set. That
distinction matters: a pattern that finds no guarantee vocabulary and a pattern
that finds guarantee vocabulary it correctly rejects are different results, and
only one of them is evidence the rule works.

`PatternMatch.scanned` exposes it. A silent rule and a working rule that declined
to fire look identical if only `fired` is reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .model import (
    ATTRIBUTIVE,
    COPULAR,
    PASSIVE,
    EntityLexicon,
    EntityMatch,
    Frame,
    FrameMatch,
    IntentPattern,
    PatternError,
    PatternMatch,
    PatternSet,
)


#: Characters that end a sentence, ASCII and full width.
_TERMINATORS = ".!?;\u3002\uff01\uff1f\uff1b\n"

#: A negator before the predicate suppresses it. Only *before*: the guard is
#: deliberately conservative, because a negator after the predicate usually
#: belongs to a different clause.
NEGATORS = re.compile(
    r"\b(?:not|no|never|neither|nor|without|cannot|can't|won't|don't|doesn't|"
    r"didn't|isn't|aren't|wasn't|weren't|n't)\b|(?:\u4e0d|\u6ca1|\u65e0|\u975e|\u672a)",
    re.IGNORECASE,
)

#: How far back a negator reaches.
NEGATION_WINDOW = 30

#: Negation that follows the match. Narrow on purpose: only predicates that
#: cancel the noun phrase rather than modify it.
POST_NEGATION = re.compile(
    r"\b(?:is|are|was|were|remains?|stays?)\s+not\s+"
    r"(?:available|offered|on offer|provided|possible|applicable|valid)\b",
    re.IGNORECASE,
)

#: Markers that make a claim conditional, reported or uncertain rather than
#: asserted. A hedged frame is found, not credited.
HEDGE_MARKERS: tuple[str, ...] = (
    "if",
    "unless",
    "whether",
    "depending",
    "depends",
    "may",
    "might",
    "could",
    "would",
    "should",
    "possibly",
    "perhaps",
    "allegedly",
    "reportedly",
    "according to",
    "said",
    "says",
    "say ",
    "claim",
    "claims",
    "claimed",
    "reported",
    "reports",
    "states",
    "stated",
    "advertises",
    "advertised",
    "promises",
    "promised",
    "seems",
    "appears",
    "suggests",
    "proposes",
    "hypothetical",
    "\u636e\u79f0",
    "\u4f20\u95fb",
    "\u5982\u679c",
    "\u53ef\u80fd",
)

_HEDGE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(item.strip()) for item in HEDGE_MARKERS if item.isascii()) + r")\b",
    re.IGNORECASE,
)


class MatcherError(Exception):
    """Raised when a pattern set cannot be applied."""


def sentence_span(text: str, position: int) -> tuple[int, int]:
    """The sentence around `position`."""

    start = 0
    for index in range(min(position, len(text)) - 1, -1, -1):
        if text[index] in _TERMINATORS:
            start = index + 1
            break
    end = len(text)
    for index in range(position, len(text)):
        if text[index] in _TERMINATORS:
            end = index + 1
            break
    return start, end


def is_negated(text: str, match_start: int) -> bool:
    """A negator within the window before the match, in the same sentence."""

    start = max(0, match_start - NEGATION_WINDOW)
    window = text[start:match_start]
    for terminator in _TERMINATORS:
        cut = window.rfind(terminator)
        if cut >= 0:
            window = window[cut + 1 :]
    return bool(NEGATORS.search(window))


def hedge_for(text: str, start: int, end: int) -> str:
    """The first hedge marker in the sentence containing the match."""

    span_start, span_end = sentence_span(text, start)
    sentence = text[span_start:span_end]
    match = _HEDGE_RE.search(sentence)
    if match:
        return match.group(0).lower()
    for marker in HEDGE_MARKERS:
        if not marker.isascii() and marker in sentence:
            return marker
    return ""


@dataclass(frozen=True, slots=True)
class RelationMatcher:
    """Applies a pattern set to text."""

    patterns: PatternSet
    detect_hedges: bool = True

    @property
    def lexicon(self) -> EntityLexicon:
        return self.patterns.lexicon

    def entities(self, text: str, pattern: IntentPattern) -> tuple[EntityMatch, ...]:
        """Every required entity occurrence, in reading order."""

        found: list[EntityMatch] = []
        for name in pattern.required_entities:
            entity = self.lexicon.get(name)
            for match in re.finditer(entity.pattern, text, re.IGNORECASE):
                found.append(EntityMatch(name, match.group(0), match.span()))
        return tuple(sorted(found, key=lambda item: item.span))

    def match_pattern(self, text: str, pattern: IntentPattern) -> PatternMatch:
        if not isinstance(text, str):
            raise MatcherError(f"text must be a string, got {type(text).__name__}")

        frames: list[FrameMatch] = []
        for relation in pattern.relations:
            frames.extend(self._match_relation(text, relation))

        return PatternMatch(
            pattern_id=pattern.pattern_id,
            category=pattern.category,
            confidence=pattern.confidence,
            frames=tuple(sorted(frames, key=lambda item: item.span)),
            entities=self.entities(text, pattern),
            evidence=pattern.evidence,
        )

    def match(self, text: str) -> tuple[PatternMatch, ...]:
        """Every pattern applied to the text."""

        return tuple(self.match_pattern(text, pattern) for pattern in self.patterns.patterns)

    def categories(self, text: str) -> tuple[str, ...]:
        """Categories with at least one asserted, unhedged frame."""

        return tuple(
            sorted({item.category for item in self.match(text) if item.fired})
        )

    def _match_relation(self, text: str, relation) -> list[FrameMatch]:
        found: list[FrameMatch] = []
        passive_starts: set[int] = set()

        for frame in relation.frames_of(PASSIVE):
            for item in self._run_frame(text, relation.name, frame):
                passive_starts.add(item.span[0])
                found.append(item)

        for frame in relation.frames:
            if frame.kind == PASSIVE:
                continue
            for item in self._run_frame(text, relation.name, frame):
                # A copular match starting where a passive match starts is the
                # same relation described twice: `Returns are guaranteed by the
                # scheme` is the passive, and reporting it as copular as well
                # would count one relation as two frames.
                if frame.kind == COPULAR and item.span[0] in passive_starts:
                    continue
                found.append(item)
        return found

    def _run_frame(self, text: str, relation: str, frame: Frame) -> list[FrameMatch]:
        compiled = frame.pattern
        found: list[FrameMatch] = []
        has_predicate = "predicate" in compiled.groupindex
        for match in compiled.finditer(text):
            groups = {
                name: (match.group(name) or "").strip()
                for name in frame.roles
                if name in compiled.groupindex
            }
            predicate = groups.pop("predicate", "") or match.group(0).strip()

            # Negation is checked from the predicate, not from the start of the
            # match. `Returns cannot be guaranteed.` puts the negator *inside*
            # the frame, between the object and the copula, so checking only
            # before the match would read it as an assertion.
            #
            # A self-negating frame is the exception: `cannot lose` and
            # `never falls` carry their own negator as the predicate, so the
            # window is measured from the start of the match instead.
            if frame.self_negating:
                anchor = match.start()
            elif has_predicate and match.group("predicate"):
                anchor = match.start("predicate")
            else:
                anchor = match.start()
            negated = is_negated(text, anchor)
            if not negated and frame.kind in (ATTRIBUTIVE, COPULAR, PASSIVE):
                negated = bool(POST_NEGATION.search(text[match.end() : match.end() + 48]))
            hedge = hedge_for(text, match.start(), match.end()) if self.detect_hedges else ""
            found.append(
                FrameMatch(
                    kind=frame.kind,
                    relation=relation,
                    span=match.span(),
                    predicate=predicate,
                    roles=groups,
                    negated=negated,
                    hedge=hedge,
                )
            )
        return found


def frame_coverage(patterns: PatternSet) -> Mapping[str, tuple[str, ...]]:
    """Frame kinds each pattern can realise, for the report and the tests."""

    coverage: dict[str, tuple[str, ...]] = {}
    for pattern in patterns.patterns:
        kinds: dict[str, None] = {}
        for relation in pattern.relations:
            for frame in relation.frames:
                kinds.setdefault(frame.kind, None)
        coverage[pattern.pattern_id] = tuple(kinds)
    return coverage


def require_frame_kinds(patterns: PatternSet, kinds: Sequence[str]) -> None:
    """Fail loudly if a pattern set cannot realise every required frame."""

    covered = {kind for values in frame_coverage(patterns).values() for kind in values}
    missing = [kind for kind in kinds if kind not in covered]
    if missing:
        raise PatternError(f"pattern set cannot realise frames: {missing}")
