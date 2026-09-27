"""Claim parser: split a paragraph into the claims it contains.

Rule-based and deliberately not perfect. The requirement is **explainability**,
not completeness: every split has to be attributable to a boundary rule, so a
disagreement about where a claim starts is a disagreement about a named rule
rather than about a model's internals.

Boundaries come from two places:

1. **Sentence ends** — `.`, `!`, `?` and the full-width equivalents.
2. **Contrastive connectives** — `However`, `But`, `Yet`, `Nevertheless`, and
   their Chinese equivalents. These are split points *and* stance evidence: a
   sentence opening with `However` is the author turning on what came before.

A segment keeps its leading connective, because the stance stage needs to see
it, and records the span it occupied in the source so every later determination
can be pointed back at the text.

The parser returns **segments, not `Claim` objects**. A `Claim` needs a speaker
and a stance and those are separate stages in this phase; assembling one here
would collapse the pipeline the phase asks for. `analyzer.analyze()` is what
returns claims.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence


#: Sentence terminators, ASCII and full width.
_TERMINATORS = ".!?\u3002\uff01\uff1f"

#: Contrastive connectives that start a sentence and signal a turn.
CONTRASTIVE_MARKERS: tuple[str, ...] = (
    "however",
    "but",
    "yet",
    "nevertheless",
    "nonetheless",
    "in contrast",
    "on the other hand",
    "on the contrary",
    "that said",
    "having said that",
    "even so",
    "by contrast",
)

#: Chinese contrastive connectives.
CONTRASTIVE_MARKERS_CJK: tuple[str, ...] = (
    "\u4f46\u662f",  # 但是
    "\u7136\u800c",  # 然而
    "\u4e0d\u8fc7",  # 不过
    "\u76f8\u53cd",  # 相反
)

#: Words that look like a sentence end but are not. Capitalised abbreviations
#: are matched case-sensitively, because the lower-case forms are ordinary
#: words: `The answer is no.` ends a sentence, `No. 5` does not.
_ABBREVIATIONS_CASED = (
    "Mr",
    "Mrs",
    "Ms",
    "Dr",
    "Prof",
    "Inc",
    "Ltd",
    "Co",
    "Corp",
    "No",
    "Fig",
)

#: Lower-case abbreviations, matched case-insensitively.
_ABBREVIATIONS_LOWER = ("vs", "etc", "approx", "est", "e.g", "i.e")

_ABBREV_CASED_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(item) for item in _ABBREVIATIONS_CASED) + r")\.$"
)
_ABBREV_LOWER_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(item) for item in _ABBREVIATIONS_LOWER) + r")\.",
    re.IGNORECASE,
)

_SENTENCE_RE = re.compile(rf"[^{re.escape(_TERMINATORS)}]+[{re.escape(_TERMINATORS)}]?")

_LEAD_RE = re.compile(
    r"^\s*(?P<lead>"
    + "|".join(
        re.escape(item) for item in (*CONTRASTIVE_MARKERS, *CONTRASTIVE_MARKERS_CJK)
    )
    + r")\b[\s,\u3001]*",
    re.IGNORECASE,
)


class ClaimParserError(Exception):
    """Raised when a paragraph cannot be parsed."""


@dataclass(frozen=True, slots=True)
class ClaimSegment:
    """One provisional claim: the text, where it sits, and its lead marker."""

    index: int
    text: str
    span: tuple[int, int]
    lead: str = ""
    lead_span: tuple[int, int] | None = None
    boundary_rule: str = ""

    @property
    def stripped(self) -> str:
        return self.text.strip()

    @property
    def opens_with_contrast(self) -> bool:
        return bool(self.lead)

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "index": self.index,
            "text": self.text,
            "span": list(self.span),
            "boundary_rule": self.boundary_rule,
        }
        if self.lead:
            payload["lead"] = self.lead
        return payload


def _is_abbreviation(chunk: str, rest: str) -> bool:
    """A trailing period after an abbreviation is not a sentence end.

    Only when something follows: a final `no.` at the end of a paragraph really
    is the end of a sentence.
    """

    if not rest.strip():
        return False
    stripped = chunk.strip()
    return bool(
        _ABBREV_CASED_RE.search(stripped) or _ABBREV_LOWER_RE.search(stripped)
    )


def _split_sentences(paragraph: str) -> list[tuple[str, int, int, str]]:
    """Return (text, start, end, rule) for each sentence-like chunk.

    A chunk ending in an abbreviation is carried forward into the next one,
    rather than closed: `Dr.` is a prefix of `Dr. Smith said …`, not a claim.
    """

    chunks: list[tuple[str, int, int, str]] = []
    pending_text = ""
    pending_start: int | None = None

    for match in _SENTENCE_RE.finditer(paragraph):
        text = match.group(0)
        if not text.strip():
            continue
        if pending_start is None:
            pending_start = match.start()
        pending_text += text
        if _is_abbreviation(text, paragraph[match.end() :]):
            continue
        chunks.append(
            (pending_text, pending_start, match.end(), "sentence-terminator")
        )
        pending_text, pending_start = "", None

    if pending_text and pending_start is not None:
        chunks.append(
            (pending_text, pending_start, len(paragraph), "sentence-terminator")
        )
    return chunks


def _apply_contrast_split(
    chunks: list[tuple[str, int, int, str]],
) -> list[tuple[str, int, int, str]]:
    """Split a chunk that opens with a contrastive connective.

    A sentence like "Analysts expect growth, however we disagree" carries two
    claims and only one terminator. Splitting on the connective recovers the
    second, which is the one the author actually makes.
    """

    result: list[tuple[str, int, int, str]] = []
    for text, start, end, rule in chunks:
        pieces = _split_on_internal_contrast(text)
        if len(pieces) == 1:
            result.append((text, start, end, rule))
            continue
        offset = start
        for piece, piece_start, piece_end in pieces:
            result.append((piece, offset + piece_start, offset + piece_end, "contrastive-connective"))
        del end
    return result


def _split_on_internal_contrast(text: str) -> list[tuple[str, int, int]]:
    """Find an internal contrastive marker and split around it."""

    lowered = text.lower()
    for marker in sorted(CONTRASTIVE_MARKERS, key=len, reverse=True):
        pattern = re.compile(rf"(?:^|[\s,;])(?P<marker>{re.escape(marker)})\b[\s,]*")
        for match in pattern.finditer(lowered):
            if match.start() == 0:
                continue  # already at the start: the lead, not an internal split
            tail = text[match.start() :]
            head = text[: match.start()]
            if not head.strip() or not tail.strip():
                continue
            return [
                (head.strip(), 0, match.start()),
                (tail.strip(), match.start(), len(text)),
            ]
    return [(text, 0, len(text))]


class ClaimParser:
    """Splits a paragraph into claim segments."""

    name = "rule-based-claim-parser"
    version = "1.0.0"

    def __init__(self, *, min_length: int = 3) -> None:
        self._min_length = min_length

    def parse(self, paragraph: str) -> tuple[ClaimSegment, ...]:
        """Claim segments, in reading order."""

        if not isinstance(paragraph, str):
            raise ClaimParserError(
                f"paragraph must be a string, got {type(paragraph).__name__}"
            )
        if not paragraph.strip():
            return ()

        chunks = _apply_contrast_split(_split_sentences(paragraph))
        segments: list[ClaimSegment] = []
        for text, start, end, rule in chunks:
            body = text.strip().rstrip(",").strip()
            if len(body) < self._min_length:
                continue
            lead, lead_span = self._lead_of(body, start)
            segments.append(
                ClaimSegment(
                    index=len(segments),
                    text=body,
                    span=(start, end),
                    lead=lead,
                    lead_span=lead_span,
                    boundary_rule=rule,
                )
            )
        return tuple(segments)

    def split(self, paragraph: str) -> tuple[str, ...]:
        """Just the claim texts, for callers that need nothing else."""

        return tuple(segment.text for segment in self.parse(paragraph))

    def _lead_of(self, body: str, offset: int) -> tuple[str, tuple[int, int] | None]:
        match = _LEAD_RE.match(body)
        if not match:
            return "", None
        lead = match.group("lead")
        start, end = match.span("lead")
        return lead.lower(), (offset + start, offset + end)


def claim_ids(count: int, *, prefix: str = "claim") -> tuple[str, ...]:
    """`claim-001`, `claim-002`, ... Zero-padded so they sort as text."""

    return tuple(f"{prefix}-{index:03d}" for index in range(1, count + 1))


def boundary_rules(segments: Sequence[ClaimSegment]) -> tuple[str, ...]:
    """The distinct boundary rules that produced these segments."""

    seen: dict[str, None] = {}
    for segment in segments:
        seen.setdefault(segment.boundary_rule, None)
    return tuple(seen)
