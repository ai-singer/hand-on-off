"""Read-only view of the evaluator's declared vocabulary.

The analyzer has to answer one question about every failing case: **is the concept
there, or only the wording?** That needs the evaluator's own lexicons, and this
module reads them without touching them.

Four rules it follows.

**Read, never register.** The evaluator's morphology module keeps a mutable lemma
index that `register()` extends. Calling it would mutate evaluator state at analysis
time, so instead every known lemma has its forms generated through the pure
`inflect`/`gerund` functions and inverted into a local map. Nothing in
`risk_evaluation/v3*` is written to, in memory or on disk — and `coverage.freeze`
proves the files are byte-identical afterwards.

**Enumerate the registry, not a hand-picked list.** Slices are derived by walking
`patterns.PATTERNS` and each relation's frames, so a frame added to the evaluator
shows up here without anyone editing this file. A hand-written inventory silently
rots; the first draft of this module read only the module-level constants and so
missed `_GUARANTEE_PREDICATE`, whose `assured` alternative would then have been
reported as a lexical gap that does not exist.

**Extract words as written.** Patterns are regular expressions, so `s?`-style
optional endings and genuine inflectional suffix groups — `(?:s|ed|ing)?` — are
expanded, and alternations are split, while character classes and escapes are
dropped. `returns?` yields `return` and `returns`; `guarantee(?:s|d)?` yields all
three forms. The extractor deliberately does *not* guess unseen forms: inventing
`expand` from a lone `expands` would make MORPHOLOGY_GAP unable to fire. It remains
approximate and says so — it feeds coverage and gap detection, never a match
decision.

**Say which declaration a word came from.** A candidate repair that adds `promised`
must name the axis it extends, and a reviewer must see where the current words live.
`origin_of()` records that.

The API the analyzer uses is four functions: `known(word)`, `morphology_hit(token)`,
`entity_hooks(text)` and `entity_types(text)`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping

#: Inflectional suffixes the evaluator writes as an optional group. Only these are
#: expanded, so `(?:s|d)?` becomes three words while `(?:es|did)?` is left alone.
_SUFFIXES = frozenset({"s", "es", "d", "ed", "ing", "ies", "ied"})

_OPTIONAL_SUFFIX = re.compile(r"([a-z])\(\?:([a-z|]+)\)\?")

#: Quantifiers whose expansion is safe because the evaluator's own matcher applies
#: them to the literal stem: `returns?` really does match both spellings.
_SAFE_QUANTIFIED = re.compile(r"([a-z]+?)(s|es|ed|ing|d)\?")

#: Everything that is regex syntax rather than a literal word. `\b` and the other
#: one-letter escapes are consumed whole: leaving the bare `b` behind would enter it
#: into the known-word set as if the evaluator listed it.
_SYNTAX = re.compile(r"\\[bBsSwWdD]|\(\?:|\(\?P<\w+>|\(\?[a-z]*:?|[()\[\]{}|^$*+?\\]")

_ALPHA = re.compile(r"^[a-z][a-z\-]*$")

#: Single letters that are real words in this vocabulary; everything else of length
#: one is a leftover of a character class or an escape, not a declaration.
_LONE_WORDS = frozenset({"a", "i"})


class LexiconError(Exception):
    """Raised when the evaluator's vocabulary cannot be read."""


def _first_suffix_group(variant: str) -> re.Match[str] | None:
    """The leftmost optional group that really is an inflectional suffix group.

    Skipping to the *next* match matters: the guarantee frame contains
    `(?:do(?:es|did)?\\s+|...)` before `guarantee(?:s|d)?`, and a scan that gives up
    at the first non-suffix group would never reach the second one — reporting
    `guarantees` as a lexical gap that does not exist.
    """

    for match in _OPTIONAL_SUFFIX.finditer(variant):
        options = match.group(2).split("|")
        if all(option in _SUFFIXES for option in options):
            return match
    return None


def _expand_variants(pattern: str, limit: int = 96) -> tuple[str, ...]:
    """Spell out optional inflectional suffix groups into concrete variants."""

    variants = [pattern]
    for _ in range(8):
        expanded: list[str] = []
        changed = False
        for variant in variants:
            match = _first_suffix_group(variant)
            if match is None:
                expanded.append(variant)
                continue
            changed = True
            head, stem = variant[: match.start()], match.group(1)
            tail = variant[match.end() :]
            expanded.append(head + stem + tail)
            for option in match.group(2).split("|"):
                expanded.append(head + stem + option + tail)
        variants = expanded[:limit]
        if not changed:
            break
    return tuple(variants)


def words_from_pattern(pattern: str) -> tuple[str, ...]:
    """Literal words in a regular expression, as the evaluator writes them.

    A `Frame` stores its pattern already compiled, so a compiled expression is
    unwrapped to its source rather than rejected.
    """

    source = getattr(pattern, "pattern", pattern)
    if not isinstance(source, str):
        raise LexiconError(f"pattern must be a string, got {type(pattern).__name__}")

    out: list[str] = []
    for variant in _expand_variants(source):
        for alternative in variant.split("|"):
            branch = _SAFE_QUANTIFIED.sub(
                lambda m: f"{m.group(1)} {m.group(1)}{m.group(2)}", alternative
            )
            branch = _SYNTAX.sub(" ", branch)
            for token in branch.split():
                token = token.strip("-").lower()
                if _ALPHA.match(token) and (len(token) > 1 or token in _LONE_WORDS):
                    out.append(token)
    seen: dict[str, None] = {}
    for item in out:
        seen.setdefault(item, None)
    return tuple(seen)


@dataclass(frozen=True, slots=True)
class LexiconSlice:
    """One declaration in the evaluator, and the words it contributes."""

    origin: str
    lemmas: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()
    entity: str | None = None

    @property
    def words(self) -> tuple[str, ...]:
        out: list[str] = [lemma.lower() for lemma in self.lemmas]
        for pattern in self.patterns:
            out.extend(words_from_pattern(pattern))
        seen: dict[str, None] = {}
        for item in out:
            seen.setdefault(item, None)
        return tuple(seen)


def _relation_slices() -> list[LexiconSlice]:
    """One slice per relation frame, walked from the live registry."""

    from ..v3 import patterns

    out: list[LexiconSlice] = []
    for intent in patterns.PATTERNS.patterns:
        for relation in intent.relations:
            for index, frame in enumerate(relation.frames):
                out.append(
                    LexiconSlice(
                        f"v3.patterns.{relation.name}.{frame.kind}[{index}]",
                        patterns=(frame.pattern,),
                    )
                )
    return out


def _slices() -> tuple[LexiconSlice, ...]:
    """Every declared vocabulary in the evaluator, read once."""

    from ..v3 import patterns
    from ..v3_1 import advice, certainty, modal
    from ..v3_repair import rejection, sources

    out: list[LexiconSlice] = []
    for name in patterns.ENTITIES.names():
        out.append(
            LexiconSlice(
                f"v3.patterns.ENTITIES.{name}",
                patterns=(patterns.ENTITIES.get(name).pattern,),
                entity=name,
            )
        )
    out.append(
        LexiconSlice("v3.patterns.GUARANTORS", patterns=(patterns.GUARANTORS.pattern,))
    )
    out.append(
        LexiconSlice("v3.patterns.MOVEMENT_LEMMAS", lemmas=patterns.MOVEMENT_LEMMAS)
    )
    out.append(LexiconSlice("v3.patterns.MOVEMENT_VERBS", patterns=(patterns.MOVEMENT_VERBS,)))
    out.append(
        LexiconSlice("v3.patterns.CERTAINTY_ADJECTIVES", patterns=(patterns.CERTAINTY_ADJECTIVES,))
    )
    out.append(LexiconSlice("v3.patterns.DIRECTIVES", patterns=(patterns.DIRECTIVES,)))
    out.extend(_relation_slices())
    out.append(LexiconSlice("v3_1.modal.COMPARISON_LEMMAS", lemmas=modal.COMPARISON_LEMMAS))
    out.append(
        LexiconSlice("v3_1.modal.NON_DIRECTIONAL_LEMMAS", lemmas=modal.NON_DIRECTIONAL_LEMMAS)
    )
    out.append(LexiconSlice("v3_1.modal.EPISTEMIC_LEMMAS", lemmas=modal.EPISTEMIC_LEMMAS))
    out.append(LexiconSlice("v3_1.advice.POSITION_LEMMAS", lemmas=advice.POSITION_LEMMAS))
    out.append(LexiconSlice("v3_1.advice.METHOD_LEMMAS", lemmas=advice.METHOD_LEMMAS))
    out.append(LexiconSlice("v3_1.advice.TRANSPARENT_LEMMAS", lemmas=advice.TRANSPARENT_LEMMAS))
    out.append(
        LexiconSlice("v3_1.advice.RECOMMENDATION_LEMMAS", lemmas=advice.RECOMMENDATION_LEMMAS)
    )
    out.append(
        LexiconSlice(
            "v3_1.certainty.CARRIERS",
            patterns=tuple(pattern for _lemma, _kind, pattern in certainty.CARRIERS),
        )
    )
    out.append(
        LexiconSlice("v3_repair.sources.REPORTING_LEMMAS", lemmas=sources.REPORTING_LEMMAS)
    )
    out.append(LexiconSlice("v3_repair.sources.HEARSAY_CUES", patterns=sources.HEARSAY_CUES))
    out.append(LexiconSlice("v3_repair.sources.REPORT_ADVERBS", patterns=(sources.REPORT_ADVERBS,)))
    out.append(
        LexiconSlice(
            "v3_repair.rejection.cues",
            patterns=tuple(
                pattern
                for table in (
                    rejection._FIRST_PERSON,
                    rejection._IMPERSONAL,
                    rejection._CONTRAST,
                    rejection._REPORTED,
                )
                for pattern, _cue in table
            ),
        )
    )
    return tuple(out)


@lru_cache(maxsize=1)
def slices() -> tuple[LexiconSlice, ...]:
    return _slices()


@lru_cache(maxsize=1)
def known_words() -> frozenset[str]:
    """Every word the evaluator spells out literally or lists as a lemma.

    Deliberately *excludes* inflected forms the evaluator never writes down: the gap
    between this set and `generated_forms()` is what MORPHOLOGY_GAP measures, so
    folding the two together would erase the signal.
    """

    out: set[str] = set()
    for item in slices():
        out.update(item.words)
    return frozenset(out)


@lru_cache(maxsize=1)
def declared_lemmas() -> frozenset[str]:
    """Lemmas the evaluator lists explicitly, before inflection."""

    out: set[str] = set()
    for item in slices():
        out.update(item.lemmas)
    return frozenset(out)


@lru_cache(maxsize=1)
def form_to_lemma() -> Mapping[str, str]:
    """Every inflected form the evaluator's morphology can generate, inverted.

    Built through the pure `inflect`/`gerund` functions rather than the evaluator's
    `register()`, so reading the vocabulary does not mutate it.
    """

    from ..v3.morphology import gerund, inflect

    mapping: dict[str, str] = {}
    for lemma in sorted(declared_lemmas()):
        if not lemma.isalpha():
            continue
        forms: set[str] = set()
        try:
            forms.update(inflect(lemma))
            forms.add(gerund(lemma))
        except Exception:  # noqa: BLE001 - a non-lemma simply contributes no forms
            continue
        for form in forms:
            if _ALPHA.match(form):
                mapping.setdefault(form.lower(), lemma)
    return dict(mapping)


@lru_cache(maxsize=1)
def generated_forms() -> frozenset[str]:
    """Forms the evaluator's morphology can build but never spells out itself."""

    return frozenset(form_to_lemma())


#: Function words that appear inside entity patterns as determiners or pronouns.
#: An entity hook must be a noun the claim is *about*, not a word sitting next to it.
_NON_ENTITY = frozenset(
    {
        "a", "an", "the", "this", "that", "these", "those", "it", "its", "their",
        "your", "our", "his", "her", "my", "own", "such", "each", "any", "some",
    }
)


@lru_cache(maxsize=1)
def entity_words() -> Mapping[str, str]:
    """Entity noun to the entity type it belongs to."""

    out: dict[str, str] = {}
    for item in slices():
        if item.entity is None:
            continue
        for word in item.words:
            if word in _NON_ENTITY:
                continue
            out.setdefault(word, item.entity)
    return dict(out)


@lru_cache(maxsize=1)
def _entity_matcher() -> re.Pattern[str]:
    words = sorted(entity_words(), key=len, reverse=True)
    if not words:
        return re.compile(r"(?!x)x")
    return re.compile("|".join(rf"\b{re.escape(w)}s?\b" for w in words), re.IGNORECASE)


def known(word: str) -> bool:
    return word.strip().lower() in known_words()


def origin_of(word: str) -> tuple[str, ...]:
    """Which declarations contain a word, for a candidate's provenance."""

    target = word.strip().lower()
    return tuple(item.origin for item in slices() if target in item.words)


def morphology_hit(token: str) -> str | None:
    """The known lemma this token inflects to, when the token itself is unlisted.

    Returns None when the evaluator already spells the token out, because then the
    wording is present and the gap lies elsewhere. That distinction is the whole of
    the MORPHOLOGY_GAP test, so it stays strict: only a lemma the evaluator declares
    may vouch for a form it never writes down.
    """

    text = token.strip().lower()
    if not text or not _ALPHA.match(text):
        return None
    if text in known_words():
        return None
    lemma = form_to_lemma().get(text)
    if lemma is None or lemma not in declared_lemmas():
        return None
    return lemma


def entity_hooks(text: str) -> tuple[str, ...]:
    """Entity nouns present in this text, in order of appearance."""

    if not isinstance(text, str):
        raise LexiconError(f"text must be a string, got {type(text).__name__}")
    words = entity_words()
    found: dict[str, None] = {}
    for match in _entity_matcher().finditer(text):
        word = match.group(0).lower()
        if word not in words and word.endswith("s") and word[:-1] in words:
            word = word[:-1]
        found.setdefault(word, None)
    return tuple(found)


def entity_types(text: str) -> tuple[str, ...]:
    """Entity *types* present in this text, deduplicated in order of appearance."""

    words = entity_words()
    found: dict[str, None] = {}
    for word in entity_hooks(text):
        kind = words.get(word)
        if kind is not None:
            found.setdefault(kind, None)
    return tuple(found)


def relation_frames() -> Mapping[str, tuple[str, ...]]:
    """Frame descriptions per relation, for FRAME_GAP evidence."""

    from ..v3 import patterns

    out: dict[str, list[str]] = {}
    for intent in patterns.PATTERNS.patterns:
        for relation in intent.relations:
            out.setdefault(relation.name, []).extend(
                frame.description for frame in relation.frames
            )
    return {name: tuple(items) for name, items in out.items()}


def tokens(text: str) -> tuple[str, ...]:
    """Alphabetic tokens, lowercased, in order."""

    return tuple(
        match.group(0).lower() for match in re.finditer(r"[A-Za-z][A-Za-z\-]*", text)
    )


def describe() -> dict[str, object]:
    return {
        "slices": len(slices()),
        "declared_lemmas": len(declared_lemmas()),
        "known_words": len(known_words()),
        "generated_forms": len(generated_forms()),
        "entity_words": len(entity_words()),
        "relations": sorted(relation_frames()),
        "note": (
            "read-only: no evaluator index is registered and no evaluator file is "
            "written; coverage.freeze verifies the sources are byte-identical"
        ),
    }
