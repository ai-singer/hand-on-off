"""Declared synonym, axis and frame tables — the candidate source.

Every repair this framework can propose comes from a table in this module. Nothing
is inferred at runtime and nothing is fetched: the tables are the whole input, the
frozen evaluator is the measuring instrument, and a human is the decision.

Why tables rather than guessing
------------------------------

A synonym whose canonical word the evaluator does not know cannot be an extension of
anything, so each axis names the word the evaluator *already* matches and
`validate()` fails loudly if that word is missing. This is not ceremony: the first
draft of the lexicon read only the evaluator's module-level constants and so missed
`_GUARANTEE_PREDICATE`, whose `assured` alternative would have been reported as a
lexical gap that does not exist. A canonical word is a claim about the evaluator, and
a claim about the evaluator is checked against the evaluator.

Why some axes are withheld
--------------------------

`withheld()` lists semantically adjacent wordings that this framework deliberately
does **not** turn into candidates. `Returns cannot be guaranteed.` is the worked
example: it sits one word away from `Returns are guaranteed.`, and the evaluator
returns no finding for it — which is correct, because a disclosure that a guarantee
does not exist is not a guarantee claim. Generating it from a naive
negation-variant rule would have manufactured a false positive and labelled it
`financial_guarantee`. The table records the refusal, with its reason, so the refusal
is part of the artifact rather than an omission from it.

Categories without relations
----------------------------

`emotional_manipulation` and `unverified_information` have no v3 relation; the
evaluator's own decision layer says so at `risk_evaluation/v3/decision.py`, noting the
semantic layer is genuinely their only detector. Their axes therefore carry
`relation=None`, and every candidate derived from them is routed to human review
rather than to a vocabulary extension. An extension needs something to extend.

Determinism
-----------

Everything here is a literal. `inflections()` derives word forms through the
evaluator's pure morphology functions, so no network, model or service is involved and
the same input yields byte-identical output.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, Sequence

from . import lexicon
from .taxonomy import (
    ATTRIBUTION_GAP,
    FRAME_GAP,
    LEXICAL_GAP,
    MORPHOLOGY_GAP,
    SYNONYM_GAP,
    UNKNOWN,
)

#: Axis modes. The mode says what a proposed word would have to do in a frame.
PREDICATE = "predicate"
MOVEMENT = "movement"
CERTAINTY = "certainty"
DIRECTIVE = "directive"
POSITION = "position"
SOURCING = "sourcing"
PRESSURE = "pressure"
MODES = (PREDICATE, MOVEMENT, CERTAINTY, DIRECTIVE, POSITION, SOURCING, PRESSURE)

#: Which failure type an axis's proposals are evidence of.
AXIS_FAILURE: Mapping[str, str] = {
    PREDICATE: SYNONYM_GAP,
    MOVEMENT: SYNONYM_GAP,
    CERTAINTY: SYNONYM_GAP,
    DIRECTIVE: SYNONYM_GAP,
    POSITION: SYNONYM_GAP,
    SOURCING: LEXICAL_GAP,
    PRESSURE: LEXICAL_GAP,
}

#: Relations the frozen evaluator actually defines, as of the Phase 8.9 freeze.
V3_RELATIONS = ("GUARANTEE", "RISK_REMOVED", "PREDICTION", "ADVICE")

#: Where an axis's canonical wording lives. `semantic_layer` means the category is
#: detected downstream of the pattern layer, so there is no v3 lexicon to extend.
CANONICAL_SOURCES = ("v3_lexicon", "semantic_layer")

#: Endings that betray a word inflected twice. `eded` and `eding` come from passing an
#: already-inflected word through the past-participle and gerund builders (`promised`
#: produced `promiseded` and `promiseding`); `inging` and `sses` are the same mistake on
#: a gerund and a sibilant stem. This constant is the single source: it used to be
#: declared here while `looks_inflected` hard-coded a shorter list, so `promiseding` —
#: one of the two forms the `Axis` docstring names — went unflagged and the declaration
#: was dead data.
_INFLECTED_ENDINGS = ("eded", "eding", "inging", "sses")


class SynonymError(Exception):
    """Raised when the declared tables contradict the evaluator."""


def looks_inflected(word: str) -> bool:
    """Whether a declared synonym looks inflected rather than lemma-shaped.

    Deliberately conservative: it flags only double-inflection artifacts, so a genuine
    word ending in `s` — `promised`, `guaranteed` — is not accused.
    """

    text = word.strip().lower()
    if " " in text or "-" in text or len(text) < 4:
        return False
    return any(text.endswith(ending) for ending in _INFLECTED_ENDINGS)


@dataclass(frozen=True, slots=True)
class Axis:
    """One semantic axis: a canonical word the evaluator knows, plus candidates.

    `synonyms` are **lemmas**, not inflected forms. Passing an inflected word to the
    morphology layer yields nonsense — `promised` produced `promiseded` and
    `promiseding` — so `validate()` reports a lemma that looks inflected instead of
    quietly proposing those forms to a reviewer.
    """

    name: str
    category: str
    mode: str
    canonical: tuple[str, ...]
    synonyms: tuple[str, ...]
    guide_basis: str
    relation: str | None = None
    needs_entity: bool = True
    canonical_source: str = "v3_lexicon"

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise SynonymError(f"axis {self.name!r} has unknown mode {self.mode!r}")
        if self.canonical_source not in CANONICAL_SOURCES:
            raise SynonymError(
                f"axis {self.name!r} has unknown canonical source "
                f"{self.canonical_source!r}"
            )
        if self.canonical_source == "v3_lexicon" and not self.canonical:
            raise SynonymError(
                f"axis {self.name!r} claims a v3 lexicon but names no canonical word"
            )
        if self.canonical_source == "semantic_layer" and self.canonical:
            raise SynonymError(
                f"axis {self.name!r} claims the semantic layer but names v3 words; "
                "there is no v3 lexicon for it to read"
            )
        if not self.synonyms:
            raise SynonymError(f"axis {self.name!r} declares no synonyms")
        if not self.guide_basis:
            raise SynonymError(f"axis {self.name!r} declares no guide basis")
        if self.relation is not None and self.relation not in V3_RELATIONS:
            raise SynonymError(
                f"axis {self.name!r} names relation {self.relation!r}, "
                f"which the evaluator does not define"
            )

    @property
    def failure_type(self) -> str:
        return AXIS_FAILURE[self.mode]

    @property
    def auto_generatable(self) -> bool:
        """Whether a candidate from this axis can be built mechanically.

        An axis with no relation cannot become a vocabulary extension, so its
        candidates are always for a human to judge.
        """

        return self.relation is not None

    @property
    def novel(self) -> tuple[str, ...]:
        """Declared synonyms the evaluator does not already match."""

        return tuple(word for word in self.synonyms if not lexicon.known(word))

    @property
    def redundant(self) -> tuple[str, ...]:
        """Declared synonyms the evaluator already matches — table rot, reported."""

        return tuple(word for word in self.synonyms if lexicon.known(word))

    @property
    def suspect(self) -> tuple[str, ...]:
        """Declared synonyms that look inflected rather than lemma-shaped."""

        return tuple(word for word in self.synonyms if looks_inflected(word))


#: The declared axes. `validate()` asserts every `v3_lexicon` canonical word is one
#: the evaluator really matches; the first draft of this table guessed several and
#: all of them failed the check, which is the check working.
AXES: tuple[Axis, ...] = (
    Axis(
        name="guarantee_predicate",
        category="financial_guarantee",
        mode=PREDICATE,
        canonical=("guaranteed", "assured", "protected"),
        synonyms=("promise", "pledge", "warrant", "vow"),
        relation="GUARANTEE",
        guide_basis=(
            "Guide v2 section 7 labels an outcome made unconditional; the evaluator "
            "already accepts assured and protected by meaning rather than by "
            "spelling, so the axis is widened by the same principle."
        ),
    ),
    Axis(
        name="risk_removed",
        category="financial_guarantee",
        mode=PREDICATE,
        canonical=("risk", "safe", "impossible"),
        synonyms=("riskless", "loss-proof", "downside-free", "capital-safe"),
        relation="RISK_REMOVED",
        guide_basis=(
            "Guide v2 section 7: risk denied outright without the word guarantee. The "
            "evaluator's own RISK_REMOVED frames already spell the idea three ways "
            "(risk-free, no risk, cannot fail), so the axis is the idea, not a spelling."
        ),
    ),
    Axis(
        name="movement_direction",
        category="market_prediction",
        mode=MOVEMENT,
        canonical=("rise", "fall", "double", "triple", "soar", "expand"),
        synonyms=(
            "plummet",
            "rocket",
            "skyrocket",
            "spike",
            "nosedive",
            "balloon",
            "quadruple",
            "halve",
            "sink",
            "slide",
        ),
        relation="PREDICTION",
        guide_basis=(
            "Guide v2 section 2: an author-voice certainty about a future outcome. "
            "The direction of the movement is not what makes it a prediction, so a "
            "verb naming a fall belongs to the same axis as one naming a rise."
        ),
    ),
    Axis(
        name="certainty_carrier",
        category="market_prediction",
        mode=CERTAINTY,
        canonical=("certain", "sure", "bound", "destined", "set", "poised", "guaranteed"),
        synonyms=("inevitable", "unavoidable", "inescapable", "unstoppable"),
        relation="PREDICTION",
        guide_basis=(
            "Guide v2 section 2: the certainty carrier is what admits the prediction, "
            "independently of which adjective spells it."
        ),
    ),
    Axis(
        name="directive_verb",
        category="investment_advice",
        mode=DIRECTIVE,
        canonical=("buy", "sell", "hold", "add", "trim", "reduce", "avoid", "invest"),
        synonyms=(
            "snap up",
            "load up on",
            "pile into",
            "steer clear of",
            "get out of",
            "add to",
            "trim back",
            "rotate into",
        ),
        relation="ADVICE",
        guide_basis=(
            "Guide v2 section 7: an action-directive aimed at the reader plus a "
            "financial object. A phrasal verb directs the reader as plainly as a "
            "single verb does, and the evaluator's DIRECTIVES table is single words. "
            "Every listed verb is transitive and takes the fund as its object: the "
            "first draft included `sit tight` and `take profit`, which cannot, so the "
            "generated sentences were ungrammatical and the guide's object requirement "
            "would not have been met."
        ),
    ),
    Axis(
        name="position_word",
        category="investment_advice",
        mode=POSITION,
        canonical=("overweight", "underweight", "hold", "stay", "remain"),
        synonyms=("long", "short", "defensive", "aggressive", "cautious"),
        relation="ADVICE",
        guide_basis=(
            "Guide v2 section 7: advice is named by the position it recommends, not "
            "only by an imperative. The evaluator lists overweight and underweight "
            "among its position lemmas, so the axis exists and is sparsely populated. "
            "The words are adjectival because the generated frame places them after a "
            "copula; a noun-shaped position word would produce a broken sentence."
        ),
    ),
    Axis(
        name="reported_source",
        category="unverified_information",
        mode=SOURCING,
        canonical=("say", "claim", "report", "confirm"),
        synonyms=("chatter", "rumour", "rumor", "scuttlebutt", "tip-off", "hearsay"),
        relation=None,
        guide_basis=(
            "Guide v2: a claim carried from a source that is not the author and is not "
            "named as authoritative. The evaluator has no v3 relation for this "
            "category, so a human decides. The words are nouns because the generated "
            "frame names the source as a thing that exists."
        ),
    ),
    Axis(
        name="urgency_pressure",
        category="emotional_manipulation",
        mode=PRESSURE,
        canonical=(),
        synonyms=(
            "last chance",
            "act fast",
            "only a few left",
            "you would be foolish to wait",
            "everyone is buying",
        ),
        relation=None,
        needs_entity=False,
        canonical_source="semantic_layer",
        guide_basis=(
            "Guide v2 section 8: pressure applied through urgency or social proof. The "
            "evaluator has no v3 relation and no v3 lexicon for this category — its "
            "decision layer records that the semantic layer is its only detector — so "
            "there is nothing here to extend and a human decides."
        ),
    ),
)


def axis(name: str) -> Axis:
    for item in AXES:
        if item.name == name:
            return item
    raise SynonymError(f"no axis named {name!r}")


@dataclass(frozen=True, slots=True)
class TableReport:
    """What `validate()` found when it checked the tables against the evaluator."""

    unknown_canonical: tuple[tuple[str, str], ...]
    redundant_synonyms: tuple[tuple[str, str], ...]
    novel_synonyms: tuple[tuple[str, str], ...]
    axes_without_relation: tuple[str, ...]
    suspect_lemmas: tuple[tuple[str, str], ...] = ()

    @property
    def ok(self) -> bool:
        return not self.unknown_canonical and not self.suspect_lemmas

    def describe(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "axes": len(AXES),
            "unknown_canonical": [
                {"axis": name, "word": word} for name, word in self.unknown_canonical
            ],
            "redundant_synonyms": [
                {"axis": name, "word": word} for name, word in self.redundant_synonyms
            ],
            "novel_synonyms": [
                {"axis": name, "word": word} for name, word in self.novel_synonyms
            ],
            "suspect_lemmas": [
                {"axis": name, "word": word} for name, word in self.suspect_lemmas
            ],
            "axes_without_relation": list(self.axes_without_relation),
        }


@lru_cache(maxsize=1)
def validate() -> TableReport:
    """Check every canonical word exists in the evaluator and sort the synonyms."""

    unknown: list[tuple[str, str]] = []
    redundant: list[tuple[str, str]] = []
    novel: list[tuple[str, str]] = []
    suspect: list[tuple[str, str]] = []
    no_relation: list[str] = []
    for item in AXES:
        if item.canonical_source == "v3_lexicon":
            for word in item.canonical:
                if not lexicon.known(word):
                    unknown.append((item.name, word))
        for word in item.synonyms:
            (redundant if lexicon.known(word) else novel).append((item.name, word))
        for word in item.suspect:
            suspect.append((item.name, word))
        if item.relation is None:
            no_relation.append(item.name)
    return TableReport(
        unknown_canonical=tuple(unknown),
        redundant_synonyms=tuple(redundant),
        novel_synonyms=tuple(novel),
        axes_without_relation=tuple(no_relation),
        suspect_lemmas=tuple(suspect),
    )


def inflections(word: str) -> tuple[str, ...]:
    """Word forms for a proposed addition, derived deterministically.

    A single-word proposal is expanded through the evaluator's pure morphology so a
    reviewer sees every spelling the extension would have to accept. Multi-word
    proposals are returned unchanged: the morphology layer inflects tokens, not
    phrases, and pretending otherwise would invent forms the evaluator never saw.
    """

    text = word.strip().lower()
    if not text or " " in text or "-" in text or not text.isalpha():
        return (text,)
    from ..v3.morphology import gerund, inflect

    forms: set[str] = {text}
    try:
        forms.update(inflect(text))
        forms.add(gerund(text))
    except Exception:  # noqa: BLE001 - the proposal stands on its own spelling
        return (text,)
    return tuple(sorted(form for form in forms if form.isalpha()))


#: Whether a chain's words are surface forms or lemmas. A chain quoting the spellings
#: the evaluator's lexicons list — `guaranteed`, `assured`, `promised` — must be
#: substituted verbatim, because inflecting an already-inflected word produced
#: `promiseded`. A chain listing lemmas — `plummet`, `skyrocket` — must be inflected,
#: because substituting a lemma into a third-person frame produced
#: `Turnover skyrocket next quarter.` Both defects were found by rendering the chains
#: through the wrong path, so the distinction is declared rather than assumed.
SURFACE = "surface"
LEMMA_FORMS = "lemma"
CHAIN_FORMS = (SURFACE, LEMMA_FORMS)


@dataclass(frozen=True, slots=True)
class Chain:
    """A declared semantic chain, for reporting which steps are already covered."""

    name: str
    category: str
    words: tuple[str, ...]
    guide_basis: str
    forms: str = SURFACE

    def __post_init__(self) -> None:
        if self.forms not in CHAIN_FORMS:
            raise SynonymError(
                f"chain {self.name!r} has unknown form {self.forms!r}; "
                f"expected one of {CHAIN_FORMS}"
            )

    @property
    def steps(self) -> tuple[tuple[str, bool], ...]:
        return tuple((word, lexicon.known(word)) for word in self.words)

    @property
    def first_missing(self) -> str | None:
        for word, present in self.steps:
            if not present:
                return word
        return None


#: The mandate's worked chain, spelled out so the framework reports which of its
#: steps the evaluator already accepts instead of asserting a gap it never checked.
CHAINS: tuple[Chain, ...] = (
    Chain(
        name="guarantee_weakening",
        category="financial_guarantee",
        words=("guaranteed", "assured", "certain", "promised"),
        guide_basis="Guide v2 section 7 via the evaluator's own predicate axis.",
        forms=SURFACE,
    ),
    Chain(
        name="movement_inflection",
        category="market_prediction",
        words=("expand", "expands", "expanded", "expanding"),
        guide_basis="Guide v2 section 2: a prediction needs a movement verb.",
        forms=SURFACE,
    ),
    Chain(
        name="movement_lexical",
        category="market_prediction",
        words=("rise", "climb", "surge", "soar", "skyrocket", "plummet"),
        guide_basis="Guide v2 section 2: direction is not what makes a prediction.",
        forms=LEMMA_FORMS,
    ),
    Chain(
        name="directive_phrasal",
        category="investment_advice",
        words=("buy", "add", "snap up", "load up on", "pile into"),
        guide_basis="Guide v2 section 7: a directive aimed at the reader.",
        forms=LEMMA_FORMS,
    ),
)


@dataclass(frozen=True, slots=True)
class FrameVariant:
    """A declared frame wording, with the label the guide gives it."""

    variant_id: str
    text: str
    category: str
    relation: str
    frame_kind: str
    guide_basis: str
    expects_finding: bool


#: Frame variants the mandate names, plus the negative control that keeps the
#: generator honest. `expects_finding` is the label the guide implies, not a
#: benchmark label: these texts are generated material and never enter a benchmark.
FRAME_VARIANTS: tuple[FrameVariant, ...] = (
    FrameVariant(
        variant_id="FRAME-GUAR-GUARANTEED",
        text="Returns are guaranteed.",
        category="financial_guarantee",
        relation="GUARANTEE",
        frame_kind="copular",
        guide_basis="Guide v2 section 7, the copular guarantee frame.",
        expects_finding=True,
    ),
    FrameVariant(
        variant_id="FRAME-GUAR-REPORTED",
        text="Returns are claimed to be guaranteed.",
        category="financial_guarantee",
        relation="GUARANTEE",
        frame_kind="reported",
        guide_basis=(
            "Guide v2 section 7 read with the Phase 8.6 ruling that the relation is "
            "labelled by meaning regardless of who asserts it. The evaluator has no "
            "reported-speech guarantee frame, so this is the frame gap the framework "
            "is built to find."
        ),
        expects_finding=True,
    ),
    FrameVariant(
        variant_id="FRAME-GUAR-NEGATED",
        text="Returns cannot be guaranteed.",
        category="financial_guarantee",
        relation="GUARANTEE",
        frame_kind="negated_copular",
        guide_basis=(
            "Guide v2 section 7 does not label a disclosure that no guarantee exists. "
            "The evaluator returns no finding, and that is correct, so this variant is "
            "a control: it must never become a repair candidate."
        ),
        expects_finding=False,
    ),
    FrameVariant(
        variant_id="FRAME-PRED-INEVITABLE",
        text="Returns are inevitable.",
        category="market_prediction",
        relation="PREDICTION",
        frame_kind="copular",
        guide_basis="Guide v2 section 2: author-voice certainty about a future outcome.",
        expects_finding=True,
    ),
    FrameVariant(
        variant_id="FRAME-PRED-REPORTED-TIP",
        text="A tip circulating on the forum says returns will triple.",
        category="unverified_information",
        relation="PREDICTION",
        frame_kind="reported",
        guide_basis=(
            "Guide v2: the author is not the speaker and the source is unnamed, so the "
            "claim is unverified rather than predicted. Human judgement, not vocabulary."
        ),
        expects_finding=True,
    ),
)


@dataclass(frozen=True, slots=True)
class Withheld:
    """A wording close to an axis that this framework refuses to generate."""

    text: str
    category: str
    reason: str


#: Refusals, recorded so they are reviewed rather than silently skipped.
WITHHELD: tuple[Withheld, ...] = (
    Withheld(
        text="Returns cannot be guaranteed.",
        category="financial_guarantee",
        reason=(
            "A disclosure that no guarantee exists is not a guarantee claim. Turning it "
            "into a candidate would trade a false negative for a false positive."
        ),
    ),
    Withheld(
        text="This is not investment advice.",
        category="investment_advice",
        reason=(
            "A disclaimer removes the directive it names; matching it as advice would "
            "punish the wording the guide expects publishers to use."
        ),
    ),
)


def novel_synonyms() -> tuple[tuple[str, str], ...]:
    """Pairs of axis name and a synonym the evaluator does not match."""

    return validate().novel_synonyms


def provenance(word: str) -> dict[str, object]:
    """Where a word stands: declared, already known, or unknown to both."""

    origins = lexicon.origin_of(word)
    return {
        "word": word,
        "known_to_evaluator": lexicon.known(word),
        "origins": list(origins),
        "inflects_to_known_lemma": lexicon.morphology_hit(word),
        "declared_axes": [item.name for item in AXES if word in item.synonyms],
        "inflections": list(inflections(word)),
    }


def describe() -> dict[str, object]:
    report = validate()
    return {
        "axes": [
            {
                "name": item.name,
                "category": item.category,
                "mode": item.mode,
                "relation": item.relation,
                "canonical": list(item.canonical),
                "novel": list(item.novel),
                "redundant": list(item.redundant),
                "failure_type": item.failure_type,
                "auto_generatable": item.auto_generatable,
            }
            for item in AXES
        ],
        "chains": [
            {"name": item.name, "steps": [list(step) for step in item.steps]}
            for item in CHAINS
        ],
        "frame_variants": [
            {
                "variant_id": item.variant_id,
                "text": item.text,
                "category": item.category,
                "expects_finding": item.expects_finding,
                "failure_type": FRAME_GAP if item.expects_finding else UNKNOWN,
            }
            for item in FRAME_VARIANTS
        ],
        "withheld": [
            {"text": item.text, "category": item.category, "reason": item.reason}
            for item in WITHHELD
        ],
        "report": report.describe(),
        "note": (
            "declared tables only; the frozen evaluator is the measuring instrument "
            "and no candidate is applied by this module"
        ),
    }


def axes_for_category(category: str) -> tuple[Axis, ...]:
    return tuple(item for item in AXES if item.category == category)


def categories() -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for item in AXES:
        seen.setdefault(item.category, None)
    return tuple(seen)


def words() -> tuple[str, ...]:
    """Every word the tables declare, for the provenance report."""

    out: dict[str, None] = {}
    for item in AXES:
        for word in item.canonical + item.synonyms:
            out.setdefault(word, None)
    for chain in CHAINS:
        for word in chain.words:
            out.setdefault(word, None)
    return tuple(out)
