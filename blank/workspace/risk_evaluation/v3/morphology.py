"""Word-form normalisation for the pattern vocabulary.

Phase 8.6 found the defect precisely: the prediction frames listed movement
verbs in their base form and followed each with `\\b`, so `expand` matched
`expand` and never `expands`, `expanded` or `expanding`. `Turnover expands
sharply next quarter.` matched no frame at all, which is why Phase 8.5 reported
100% relation recall on a development benchmark that happened to contain only
base forms.

The repair is **not** a longer word list. Adding `expands|expanded|expanding` by
hand is the same defect waiting to happen one verb later, and it hides the rule
that generated them. This module derives the forms from a lemma:

    inflect("expand")   -> ("expand", "expands", "expanded", "expanding")
    inflect("rise")     -> ("rise", "rises", "rose", "risen", "rising")
    normalize_token("expands") -> "expand"

Two directions, because they answer different questions. `inflect` builds the
alternation the frames match with. `normalize_token` reduces a token to its
lemma, which is what lets a diagnostic say *why* a token did not match and what
lets a test assert the mapping rather than the pattern text.

Strong verbs are listed explicitly - `rise/rose/risen` cannot be derived - and
the table is bounded to the vocabulary actually in use. Everything else follows
the regular English rules, including the CVC doubling that makes `drop` into
`dropped` rather than `droped`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


_VOWELS = frozenset("aeiou")
#: Final letters that are never doubled, even in a CVC shape.
_NO_DOUBLE = frozenset("wxy")
_SIBILANT_ENDINGS = ("s", "x", "z", "ch", "sh", "o")

#: Strong verbs, whose past forms cannot be derived. Bounded to the vocabulary
#: in use; a lemma absent from this table and not derivable by the rules is an
#: error rather than a silent base-form-only entry.
IRREGULAR: Mapping[str, tuple[str, str]] = {
    "rise": ("rose", "risen"),
    "fall": ("fell", "fallen"),
    "grow": ("grew", "grown"),
    "hold": ("held", "held"),
}


class MorphologyError(Exception):
    """Raised when a lemma cannot be inflected."""


def _is_consonant(character: str) -> bool:
    return character.isalpha() and character not in _VOWELS


def _syllables(lemma: str) -> int:
    """Vowel groups, as a spelling-level approximation of syllable count.

    English consonant doubling depends on stress, which spelling does not
    carry: `recover` does not double because the final syllable is unstressed
    and `drop` does because it is the only one. Requiring a single vowel group
    is the approximation that separates them without a pronunciation dictionary.
    """

    return len(re.findall(r"[aeiouy]+", lemma))


def _is_cvc(lemma: str) -> bool:
    """Does the lemma end consonant-vowel-consonant, needing a doubled final?"""

    if len(lemma) < 3:
        return False
    if _syllables(lemma) > 1:
        return False
    last, middle, first = lemma[-1], lemma[-2], lemma[-3]
    return (
        _is_consonant(last)
        and last not in _NO_DOUBLE
        and middle in _VOWELS
        and _is_consonant(first)
    )


def third_person(lemma: str) -> str:
    """`expand` -> `expands`, `reach` -> `reaches`, `rally` -> `rallies`."""

    if lemma.endswith(_SIBILANT_ENDINGS):
        return lemma + "es"
    if lemma.endswith("y") and len(lemma) > 1 and _is_consonant(lemma[-2]):
        return lemma[:-1] + "ies"
    return lemma + "s"


def past(lemma: str) -> str:
    """The simple past: `expand` -> `expanded`, `drop` -> `dropped`."""

    if lemma in IRREGULAR:
        return IRREGULAR[lemma][0]
    if lemma.endswith("e"):
        return lemma + "d"
    if lemma.endswith("y") and len(lemma) > 1 and _is_consonant(lemma[-2]):
        return lemma[:-1] + "ied"
    if _is_cvc(lemma):
        return lemma + lemma[-1] + "ed"
    return lemma + "ed"


def past_participle(lemma: str) -> str:
    """The participle: `expand` -> `expanded`, `rise` -> `risen`."""

    if lemma in IRREGULAR:
        return IRREGULAR[lemma][1]
    return past(lemma)


def gerund(lemma: str) -> str:
    """`expand` -> `expanding`, `drop` -> `dropping`, `surge` -> `surging`."""

    if lemma.endswith("ie"):
        return lemma[:-2] + "ying"
    if lemma.endswith("e") and not lemma.endswith(("ee", "oe", "ye")):
        return lemma[:-1] + "ing"
    if _is_cvc(lemma):
        return lemma + lemma[-1] + "ing"
    return lemma + "ing"


@dataclass(frozen=True, slots=True)
class VerbForms:
    lemma: str
    third_person: str
    past: str
    past_participle: str
    gerund: str

    @property
    def all(self) -> tuple[str, ...]:
        """Every form, in a stable order, de-duplicated."""

        return tuple(
            dict.fromkeys(
                (
                    self.lemma,
                    self.third_person,
                    self.past,
                    self.past_participle,
                    self.gerund,
                )
            )
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "lemma": self.lemma,
            "third_person": self.third_person,
            "past": self.past,
            "past_participle": self.past_participle,
            "gerund": self.gerund,
            "all": list(self.all),
        }


def forms(lemma: str) -> VerbForms:
    if not lemma.isalpha():
        raise MorphologyError(f"a lemma must be alphabetic, got {lemma!r}")
    return VerbForms(
        lemma=lemma,
        third_person=third_person(lemma),
        past=past(lemma),
        past_participle=past_participle(lemma),
        gerund=gerund(lemma),
    )


def inflect(lemma: str) -> tuple[str, ...]:
    """Every form of one lemma."""

    return forms(lemma).all


_LEMMA_INDEX: dict[str, str] = {}


def _lemma_index() -> dict[str, str]:
    """Inflected form -> lemma, built from the vocabulary that has been asked for."""

    return _LEMMA_INDEX


def register(lemmas: Iterable[str]) -> None:
    """Index a vocabulary so `normalize_token` can reduce its forms."""

    for lemma in lemmas:
        if not lemma.isalpha():
            continue
        for form in inflect(lemma):
            _LEMMA_INDEX.setdefault(form, lemma)


#: Suffixes stripped when deriving a lemma from an inflected token, longest
#: first so `ies` is tried before `s`.
_STRIPPABLE = ("ing", "ies", "ied", "es", "ed", "s", "d", "e", "y")


def derive_lemma(token: str) -> str:
    """Recover the lemma of a token by inverting the inflection rules.

    Candidate stems are generated by stripping each plausible suffix and by
    undoing the two artefacts that stripping creates: a doubled final consonant
    (`dropp`) and a `y` that became `i` (`multipli`). Every candidate whose own
    forms contain the token is kept, and the best is chosen by

        1. registered vocabulary first, so `multiply` beats the artefact `multipli`
        2. then the shortest stem
        3. then alphabetically, so the result is deterministic

    A token with no candidate is returned unchanged rather than forced onto an
    invented lemma.
    """

    lowered = token.strip().lower()
    if not lowered.isalpha() or len(lowered) < 3:
        return lowered

    index = _lemma_index()
    candidates: set[str] = set()
    for suffix in _STRIPPABLE:
        if not lowered.endswith(suffix):
            continue
        stem = lowered[: -len(suffix)]
        if len(stem) < 2:
            continue
        options = [stem, stem + "e", stem + stem[-1]]
        if stem.endswith("i"):
            options.append(stem[:-1] + "y")
        if len(stem) > 2 and stem[-1] == stem[-2]:
            options.append(stem[:-1])
        for candidate in options:
            if not candidate.isalpha():
                continue
            try:
                if lowered in inflect(candidate):
                    candidates.add(candidate)
            except MorphologyError:
                continue

    if not candidates:
        return lowered
    return min(candidates, key=lambda item: (item not in index, len(item), item))


def normalize_token(token: str) -> str:
    """Reduce an inflected token to its lemma, or return it unchanged.

    Serves diagnostics and tests rather than matching: a miss can then be
    explained as "the text has `expands`, whose lemma `expand` is in the
    vocabulary but whose form was not" rather than as an unexplained absence.

    Registered vocabulary is consulted first, so a strong verb's irregular form
    (`rose` -> `rise`) resolves; anything else falls back to inverting the rules.
    """

    lowered = token.strip().lower()
    if not lowered:
        return ""
    indexed = _lemma_index().get(lowered)
    if indexed is not None:
        return indexed
    return derive_lemma(lowered)


def alternation(lemmas: Sequence[str], *, word_boundary: bool = True) -> str:
    """A regex alternation covering every form of every lemma.

    Longest form first, so `rises` is preferred over `rise` when both could
    match and the roles a frame binds do not depend on match order.
    """

    collected: dict[str, None] = {}
    for lemma in lemmas:
        register([lemma])
        for form in inflect(lemma):
            collected.setdefault(form, None)
    ordered = sorted(collected, key=lambda item: (-len(item), item))
    body = "|".join(re.escape(item) for item in ordered)
    return f"(?:{body})" if word_boundary else f"(?:{body})"


def known_lemmas() -> tuple[str, ...]:
    return tuple(sorted(set(_lemma_index().values())))


def describe(lemmas: Sequence[str]) -> dict[str, object]:
    """Every lemma and its forms, for the report and for tests."""

    return {lemma: forms(lemma).as_dict() for lemma in lemmas}
