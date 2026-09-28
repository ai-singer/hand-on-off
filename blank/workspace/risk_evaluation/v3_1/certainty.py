"""Modal strength, in the taxonomy's own certainty vocabulary.

Guide v2 section 1.2 already declares four certainty levels, and section 2 turns
the whole `market_prediction` question on one of them:

    market_prediction  <=>  statement_source == author  AND  certainty_level == certain

So the modal layer's job is not "find a modal". It is to say *which* of the four
levels a statement is at, and the answer decides whether a category is raised at
all. That is why the levels are imported from the taxonomy rather than invented
here: the layer and the guide have to be using the same four words, or the
classification cannot be checked against the rule it serves.

Two things this module settles that a keyword list cannot.

**Strength is not the verb modal.** `The market will probably crash next month.`
has `will`, which is `certain` on its own, and `probably`, which is `probable`.
The statement is `probable`, and it is therefore not a `market_prediction` - a
false positive the pipeline produced before this layer existed. The rule is
**weakest wins**: the strength of a statement is the weakest carrier in it.

**A construction can carry strength with no modal verb at all.**
`There is a chance the shares will recover.` has `will` and is a `possible`
statement; the possibility is in the existential. Constructions are therefore
carriers in their own right, alongside verbs and adverbs.

Conditional markers are stronger than any modal: guide v2 section 5 says a
conditional statement asserts nothing unconditionally, so it is `hypothetical`
whatever else is present.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..taxonomy_v2 import CERTAINTY_LEVELS

#: The four levels, weakest first. The order is the whole of the "weakest wins"
#: rule, so it is declared once and used for every comparison.
ORDER: tuple[str, ...] = ("hypothetical", "possible", "probable", "certain")

if set(ORDER) != set(CERTAINTY_LEVELS):  # pragma: no cover - import guard
    raise ImportError(
        f"the certainty order {ORDER} does not match the taxonomy's "
        f"{CERTAINTY_LEVELS}"
    )

CERTAIN = "certain"
PROBABLE = "probable"
POSSIBLE = "possible"
HYPOTHETICAL = "hypothetical"


class CertaintyError(Exception):
    """Raised when a strength is not one of the taxonomy's levels."""


def rank(level: str) -> int:
    if level not in ORDER:
        raise CertaintyError(
            f"unknown certainty {level!r}; the taxonomy declares {CERTAINTY_LEVELS}"
        )
    return ORDER.index(level)


def weakest(*levels: str) -> str:
    """The weakest of the levels given, ignoring empty ones.

    Empty means "no carrier found", and a statement with no carrier at all is not
    hedged: it is asserted. So an all-empty call returns `certain`, and an empty
    argument never lowers anything.
    """

    present = [level for level in levels if level]
    if not present:
        return CERTAIN
    return min(present, key=rank)


def strongest(*levels: str) -> str:
    present = [level for level in levels if level]
    if not present:
        return CERTAIN
    return max(present, key=rank)


@dataclass(frozen=True, slots=True)
class Carrier:
    """One thing that puts a statement at a certainty level."""

    level: str
    marker: str
    span: tuple[int, int]
    #: `verb`, `adverb`, `construction` or `conditional`.
    kind: str

    def __post_init__(self) -> None:
        if self.level not in ORDER:
            raise CertaintyError(f"unknown certainty {self.level!r}")

    @property
    def marker_text(self) -> str:
        return f"certainty:{self.level}:{self.kind}:{self.marker}"

    def as_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "marker": self.marker,
            "kind": self.kind,
            "span": list(self.span),
        }


@dataclass(frozen=True, slots=True)
class Strength:
    """The strength of one piece of text, and what put it there."""

    level: str
    carriers: tuple[Carrier, ...] = ()

    def __post_init__(self) -> None:
        if self.level not in ORDER:
            raise CertaintyError(f"unknown certainty {self.level!r}")
        object.__setattr__(self, "carriers", tuple(self.carriers))

    @property
    def certain(self) -> bool:
        return self.level == CERTAIN

    @property
    def hypothetical(self) -> bool:
        return self.level == HYPOTHETICAL

    @property
    def hedged(self) -> bool:
        """Below `certain`, so the taxonomy does not call it a prediction.

        Guide v2 section 2 excludes both `probable` and `possible`, and section 5
        excludes `hypothetical`. Only `certain` survives, so this is the same test
        as "not a market_prediction".
        """

        return self.level != CERTAIN

    @property
    def decisive(self) -> Carrier | None:
        """The carrier that set the level. The weakest one, by construction."""

        for carrier in sorted(self.carriers, key=lambda item: rank(item.level)):
            if carrier.level == self.level:
                return carrier
        return None

    @property
    def marker(self) -> str:
        carrier = self.decisive
        return carrier.marker if carrier is not None else ""

    @property
    def markers(self) -> tuple[str, ...]:
        return tuple(item.marker_text for item in self.carriers)

    def as_dict(self) -> dict[str, object]:
        return {
            "level": self.level,
            "marker": self.marker,
            "carriers": [item.as_dict() for item in self.carriers],
        }


#: Modal verbs and constructions, by the strength they carry. Written as
#: patterns because most of these are multi-word, and grouped by level rather
#: than by word so the mapping cannot drift from the guide's table.
CARRIERS: tuple[tuple[str, str, str], ...] = (
    # -- certain: guide 1.2, "asserted as fact, no hedge"
    (CERTAIN, "verb", r"will|shall|must"),
    (CERTAIN, "construction", r"is\s+going\s+to|are\s+going\s+to|was\s+going\s+to"),
    (CERTAIN, "construction", r"is\s+(?:certain|sure|bound|destined)\s+to|"
                             r"are\s+(?:certain|sure|bound|destined)\s+to"),
    (CERTAIN, "adverb", r"certainly|definitely|surely|undoubtedly|inevitably|必然"),
    # -- probable: guide 1.2, "asserted with a probability hedge"
    (PROBABLE, "adverb", r"probably|likely|most\s+likely|in\s+all\s+likelihood|"
                         r"presumably|预期"),
    (PROBABLE, "construction", r"is\s+likely\s+to|are\s+likely\s+to|"
                               r"is\s+expected\s+to|are\s+expected\s+to|"
                               r"is\s+set\s+to|are\s+set\s+to|"
                               r"is\s+poised\s+to|are\s+poised\s+to|"
                               r"is\s+due\s+to|are\s+due\s+to"),
    (PROBABLE, "verb", r"should|ought\s+to"),
    # -- possible: guide 1.2, "asserted as one possibility"
    (POSSIBLE, "verb", r"may|might|could|can"),
    (POSSIBLE, "adverb", r"possibly|perhaps|maybe|conceivably|potentially|"
                         r"arguably|可能|或许"),
    (POSSIBLE, "construction", r"there\s+is\s+a\s+chance|there\s+is\s+a\s+risk|"
                               r"it\s+is\s+possible|it\s+is\s+conceivable|"
                               r"it\s+is\s+plausible|"
                               r"is\s+possible|are\s+possible|is\s+plausible|"
                               r"is\s+conceivable|is\s+conceivably|"
                               r"cannot\s+be\s+ruled\s+out"),
    # -- hypothetical: guide 5, "asserts nothing unconditionally"
    (HYPOTHETICAL, "verb", r"would|wouldn't|would\s+not"),
    (HYPOTHETICAL, "conditional", r"\bif\b|\bunless\b|\bassuming\b|"
                                  r"\bprovided\s+that\b|\bproviding\b|"
                                  r"\bdepending\s+on\b|\bin\s+the\s+event\b|"
                                  r"\bwere\s+(?!going\b)(?:\w+\s+){1,3}to\b|"
                                  r"\bhad\s+\w+\b|\bwhether\b|如果|假如"),
)

#: Markers that make a statement conditional even though the word `if` is absent.
#: Guide v2 section 5 names the inverted `should` and `were ... to` separately,
#: because they put the condition first.
#:
#: The inverted `should` is **clause-initial**, and that is the whole of the rule.
#: `Should the market decline, the position would lose value.` is a scenario;
#: `The fund should outperform.` is a `probable` statement about the fund. A pattern
#: that matched `should <word>` anywhere made the second one hypothetical, which is
#: the opposite of what the guide says about it.
INVERTED_CONDITIONALS: tuple[str, ...] = (
    r"(?:^|[,;:]\s*)should\s+(?:the|this|that|these|those|its|their|our|your|a|an)\b",
    r"\bwere\s+(?!going\b)(?:\w+\s+){1,3}to\b",
)

#: Levels a carrier may carry. Kept beside the table so a new row cannot invent one.
LEVELS: tuple[str, ...] = ORDER

__all__ = [
    "CARRIERS",
    "CERTAIN",
    "Carrier",
    "CertaintyError",
    "HYPOTHETICAL",
    "INVERTED_CONDITIONALS",
    "LEVELS",
    "ORDER",
    "POSSIBLE",
    "PROBABLE",
    "Strength",
    "rank",
    "strongest",
    "weakest",
]


def describe() -> tuple[dict[str, object], ...]:
    """The carrier table, for the report and the tests."""

    return tuple(
        {"level": level, "kind": kind, "pattern": pattern}
        for level, kind, pattern in CARRIERS
    )


def levels_used() -> Sequence[str]:
    return tuple(dict.fromkeys(level for level, _, _ in CARRIERS))
