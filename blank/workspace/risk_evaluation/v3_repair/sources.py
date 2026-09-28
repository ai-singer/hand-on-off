"""Who a reported statement came from, and whether that source can be checked.

Phase 8.6's blind run found the attribution layer answering `unknown/quoted` for
fourteen different wordings that all have a source. `The regulator said the
review is ongoing.` and `Traders say the shares are cheap.` came out the same,
and the benchmark annotates them differently for a reason that is stated in guide
v2 section 7 and not in the marker table:

    The regulator said the review is ongoing.   named, checkable source   -> no risk
    Traders say the shares are cheap.           unnamed collective        -> unverified
    An unnamed official confirmed the restatement.  explicitly anonymous  -> unverified
    The advert says the price will certainly double. checkable advert     -> no risk

So the gap is not "more source nouns". It is that `third_party` was the only
answer available, and `third_party` cannot distinguish a checkable source from an
uncheckable one. This module types the source and says whether it can be checked.

Three of the four types are the ones the phase names. The fourth is
`published_material`, and it is not a way of dodging the other three: `the
advert`, `the prospectus` and `the marketing material` are documents. They are
not authorities, they are not professional groups, and calling them "unknown
sources" would assert something false about a document whose provenance is
exactly what the sentence gives. Guide v2 section 7 makes them *negative* for
`unverified_information`, so folding them into `unnamed_source` would have
produced the wrong verdict on two benchmark cases as well as a wrong description.

A source is only read as a source when the sentence actually reports through it.
`The manager's report is published with the annual accounts.` names a manager and
the benchmark annotates it `unknown`, correctly: the manager is not the one
speaking, the report is the subject. Requiring a reporting verb immediately after
the source noun, with no possessive in between, is what separates the two, and it
is why this module is a detector rather than a noun list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A source whose identity makes the statement checkable.
NAMED_AUTHORITY = "named_authority"
#: A role collective: `traders`, `analysts`. Checkable only when a proper noun
#: says which ones.
PROFESSIONAL_GROUP = "professional_group"
#: A source the sentence itself declines to name.
UNNAMED_SOURCE = "unnamed_source"
#: A document: the advert, the prospectus, the filing.
PUBLISHED_MATERIAL = "published_material"
#: A source the sentence names that the lexicon cannot type. `According to the
#: report` names something specific, and calling that an "unknown source" because
#: this module has no entry for it would assert the opposite of what the sentence
#: says. It is checkable by virtue of being named.
NAMED_SOURCE = "named_source"

SOURCE_TYPES: tuple[str, ...] = (
    NAMED_AUTHORITY,
    PROFESSIONAL_GROUP,
    UNNAMED_SOURCE,
    PUBLISHED_MATERIAL,
    NAMED_SOURCE,
)

#: Types whose instances can be checked against. The default for a type not
#: listed here is that checkability depends on whether a proper noun names it.
_CHECKABLE_TYPES: frozenset[str] = frozenset(
    {NAMED_AUTHORITY, PUBLISHED_MATERIAL, NAMED_SOURCE}
)
#: Types that are uncheckable whatever else is true.
_UNCHECKABLE_TYPES: frozenset[str] = frozenset({UNNAMED_SOURCE})

#: Verbs whose subject is the one doing the reporting. Written as **lemmas** and
#: inflected here, because the hand-written list this replaces carried `claims`
#: and not `claim` - so `Sources claim the merger talks have stalled.` had a
#: perfectly good source noun and no verb to attach it to, and the source was
#: reported as unknown. That is the same defect as the movement verbs in Phase
#: 8.7 step 1, one layer down, and it is fixed the same way.
REPORTING_LEMMAS: tuple[str, ...] = (
    "say",
    "state",
    "confirm",
    "report",
    "announce",
    "tell",
    "note",
    "warn",
    "publish",
    "disclose",
    "indicate",
    "suggest",
    "write",
    "add",
    "deny",
    "testify",
    "decline",
    "claim",
    "argue",
    "assert",
    "contend",
    "maintain",
    "caution",
    "estimate",
    "expect",
    "reckon",
    "observe",
    "comment",
    "acknowledge",
    "recommend",
    "advise",
    "concede",
    "admit",
    "reveal",
)

#: Forms the regular endings do not produce.
REPORTING_IRREGULAR: tuple[str, ...] = (
    "said",
    "told",
    "wrote",
    "denied",
    "testified",
)


def _inflect(lemma: str) -> str:
    """The lemma and its regular forms, as one alternation."""

    if lemma.endswith("y") and lemma[-2:-1] not in "aeiou":
        stem = lemma[:-1]
        return rf"{lemma}(?:ing)?|{stem}(?:ies|ied)"
    if lemma.endswith(("s", "x", "ch", "sh")):
        return rf"{lemma}(?:es|ed|ing)?"
    return rf"{lemma}(?:s|ed|d|ing)?"


REPORTING_VERBS = "|".join(
    sorted(
        {_inflect(lemma) for lemma in REPORTING_LEMMAS}
        | set(REPORTING_IRREGULAR),
        key=lambda item: (-len(item), item),
    )
)

#: Phrases that report a claim while naming nobody: hearsay. Each is a cue in its
#: own right, because there is no source noun to attach a verb to.
HEARSAY_CUES: tuple[str, ...] = (
    r"word\s+on\s+the\s+street",
    r"the\s+word\s+is",
    r"word\s+is\s+that",
    r"rumou?r\s+has\s+it",
    r"talk\s+is\s+that",
    r"market\s+talk",
    r"i\s+heard",
    r"we\s+hear",
    r"i\s+understand",
    r"we\s+understand",
    r"people\s+say",
    r"they\s+say",
    r"it\s+is\s+said",
    r"it\s+is\s+understood",
    r"\u636e\u79f0|\u4f20\u95fb|\u542c\u8bf4",
)

#: Adverbs that report without naming anybody.
REPORT_ADVERBS = (
    r"reportedly|allegedly|apparently|"
    r"\u636e\u79f0|\u4f20\u95fb"
)

#: Institutions whose statements are on the record and can be checked. Bare nouns
#: only: the match is case-insensitive and scans the whole sentence, so a
#: `the\s+regulator` alternative would match first and report the name as
#: "The regulator" - an article in an evidence string rather than the source.
_AUTHORITIES = (
    r"regulators?",
    r"exchanges?",
    r"custodians?",
    r"trustees?",
    r"depositar(?:y|ies)",
    r"auditors?",
    r"supervisors?",
    r"central\s+bank",
    r"commission",
    r"authorit(?:y|ies)",
    r"agenc(?:y|ies)",
    r"clearing\s+house",
    r"administrators?",
    r"registrars?",
    r"board",
    r"committee",
)

#: Role collectives. An indefinite plural names a role, not an organisation.
#:
#: Financial intermediaries - `a promoter`, `an underwriter`, `a sponsor` - are
#: deliberately **not** here, and the reason is a measured contradiction rather
#: than an opinion. `A promoter claimed the fund cannot lose money.` (Phase 8.6,
#: IV-094) is annotated `unverified_information` with the reason "indefinite
#: promoter is uncheckable"; `The article quotes a promoter saying do not miss
#: this opportunity.` (Phase 8.3, 83-CTL-04, a control) is annotated as no risk.
#: Adding the noun fixes the first case and breaks the second, so the two labels
#: cannot both be honoured by a source lexicon. The frozen control wins, the
#: repair gains nothing, and the conflict is reported in section 6 of
#: `docs/PHASE_8_7_TARGETED_REPAIR_REPORT.md` instead of being tuned away.
_GROUPS = (
    r"analysts?",
    r"traders?",
    r"strategists?",
    r"economists?",
    r"brokers?",
    r"dealers?",
    r"fund\s+managers?",
    r"portfolio\s+managers?",
    r"managers?",
    r"advis(?:e|o)rs?",
    r"investors?",
    r"shareholders?",
    r"commentators?",
    r"observers?",
)

#: Wordings that name nobody.
_UNNAMED = (
    r"unnamed\s+(?:official|person|source|executive|banker|trader|figure)",
    r"anonymous\s+(?:official|person|source|executive|banker|trader|figure)",
    r"person\s+familiar\s+with\s+the\s+matter",
    r"people\s+familiar\s+with\s+the\s+matter",
    r"person\s+close\s+to\s+the\s+(?:deal|company|fund)",
    r"sources?",
    r"insiders?",
    r"officials?",
    r"market\s+chatter",
    r"chatter",
    r"speculation",
    r"rumou?rs?",
)

#: Documents whose provenance the sentence gives.
_MATERIAL = (
    r"marketing\s+material",
    r"adverts?(?:isement)?s?",
    r"prospectus",
    r"filing",
    r"annual\s+report",
    r"fact\s+sheet",
    r"brochure",
    r"press\s+release",
    r"disclosure\s+document",
    r"newsletters?",
    r"research\s+note",
    r"circular",
)

#: Capitalised words that begin a sentence without naming anybody. Without this,
#: `Some commentators argue the shares are cheap.` reads `Some ` as a proper noun
#: and rules the collective checkable - so the one thing that made it
#: uncheckable, that nobody is named, is exactly what the capital letter hides.
#: Sentence position is not a name.
_NOT_A_PROPER_NOUN: tuple[str, ...] = (
    "A",
    "All",
    "An",
    "Any",
    "Both",
    "Each",
    "Either",
    "Every",
    "Few",
    "Her",
    "His",
    "How",
    "However",
    "Its",
    "Many",
    "Most",
    "Neither",
    "No",
    "One",
    "Other",
    "Others",
    "Our",
    "Several",
    "Some",
    "Such",
    "That",
    "The",
    "Their",
    "These",
    "This",
    "Those",
    "Two",
    "What",
    "When",
    "Where",
    "Which",
    "While",
    "Your",
)

_PROPER_NOUN_WORD = (
    rf"(?!(?:{'|'.join(_NOT_A_PROPER_NOUN)})\b)[A-Z][A-Za-z&.\-]+"
)

#: A proper noun immediately before a group noun makes the group identifiable:
#: `Goldman analysts` is checkable, `traders` is not, and neither is `Some
#: commentators`.
_PROPER_NOUN = rf"(?:{_PROPER_NOUN_WORD}\s+){{1,3}}"

_REPORTING = rf"\s+(?:\w+ly\s+)?(?:{REPORTING_VERBS})\b"

_REPORT_ADVERB_RE = re.compile(rf"\b(?:{REPORT_ADVERBS})\b", re.IGNORECASE)
_HEARSAY_RE = re.compile(rf"\b(?:{'|'.join(HEARSAY_CUES)})", re.IGNORECASE)
_ACCORDING_TO_RE = re.compile(r"\baccording\s+to\s+(?P<name>[^,.;]{2,60})", re.IGNORECASE)

#: Cues that mean the claim is being relayed rather than asserted.
REPORTING_CUES: tuple[str, ...] = ("reporting_verb", "report_adverb", "according_to", "hearsay")


#: One compiled entry per source type, so a type can be exercised on its own.
_LEXICON: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        NAMED_AUTHORITY,
        re.compile(rf"\b(?P<name>{'|'.join(_AUTHORITIES)}){_REPORTING}", re.IGNORECASE),
    ),
    (
        PUBLISHED_MATERIAL,
        re.compile(rf"\b(?P<name>{'|'.join(_MATERIAL)}){_REPORTING}", re.IGNORECASE),
    ),
    (
        UNNAMED_SOURCE,
        re.compile(rf"\b(?P<name>{'|'.join(_UNNAMED)}){_REPORTING}", re.IGNORECASE),
    ),
    (
        PROFESSIONAL_GROUP,
        re.compile(
            rf"\b(?P<name>(?:{_PROPER_NOUN})?(?:{'|'.join(_GROUPS)})){_REPORTING}",
            re.IGNORECASE,
        ),
    ),
)


class SourceError(Exception):
    """Raised when a source finding is malformed."""


@dataclass(frozen=True, slots=True)
class SourceFinding:
    """One source a statement is reported through."""

    source_type: str
    name: str
    span: tuple[int, int]
    #: How the source was found: `reporting_verb`, `report_adverb`,
    #: `according_to`.
    cue: str
    #: Does the sentence give enough to check the statement against the source?
    checkable: bool

    def __post_init__(self) -> None:
        if self.source_type not in SOURCE_TYPES:
            raise SourceError(f"unknown source type {self.source_type!r}")
        if not self.name.strip():
            raise SourceError("a source finding needs the name it matched")

    @property
    def uncheckable(self) -> bool:
        return not self.checkable

    @property
    def marker(self) -> str:
        state = "checkable" if self.checkable else "uncheckable"
        return f"source:{self.source_type}:{self.name.lower()}:{state}"

    def as_dict(self) -> dict[str, object]:
        return {
            "source_type": self.source_type,
            "name": self.name,
            "span": list(self.span),
            "cue": self.cue,
            "checkable": self.checkable,
        }


def _named(match: re.Match[str]) -> bool:
    """Does a proper noun name this group, rather than an indefinite role?

    Only professional groups are asked. An authority or a document is checkable
    because of what it is; an unnamed source is uncheckable because of what the
    sentence refused to say. Asking the question of those would read a leading
    capital - `An unnamed official` - as a proper noun.
    """

    return bool(re.match(_PROPER_NOUN, match.group("name")))


def detect_type(text: str, source_type: str) -> SourceFinding | None:
    """The first source of one type in `text`."""

    for name, pattern in _LEXICON:
        if name != source_type:
            continue
        for match in pattern.finditer(text):
            checkable = (
                True
                if source_type in _CHECKABLE_TYPES
                else False
                if source_type in _UNCHECKABLE_TYPES
                else _named(match)
            )
            return SourceFinding(
                source_type=source_type,
                name=match.group("name").strip(),
                span=match.span("name"),
                cue="reporting_verb",
                checkable=checkable,
            )
    return None


def detect(text: str) -> SourceFinding | None:
    """The source the text reports through, typed and checkability-resolved.

    The earliest mention wins, because that is the subject the sentence is
    built around. Reports that name nobody carry their own cue.
    """

    if not isinstance(text, str):
        raise SourceError(f"text must be a string, got {type(text).__name__}")

    candidates: list[tuple[int, SourceFinding]] = []
    for source_type, _ in _LEXICON:
        found = detect_type(text, source_type)
        if found is not None:
            candidates.append((found.span[0], found))

    adverb = _REPORT_ADVERB_RE.search(text)
    if adverb is not None:
        candidates.append(
            (
                adverb.start(),
                SourceFinding(
                    source_type=UNNAMED_SOURCE,
                    name=adverb.group(0).lower(),
                    span=adverb.span(),
                    cue="report_adverb",
                    checkable=False,
                ),
            )
        )

    hearsay = _HEARSAY_RE.search(text)
    if hearsay is not None:
        candidates.append(
            (
                hearsay.start(),
                SourceFinding(
                    source_type=UNNAMED_SOURCE,
                    name=hearsay.group(0).lower(),
                    span=hearsay.span(),
                    cue="hearsay",
                    checkable=False,
                ),
            )
        )

    according = _ACCORDING_TO_RE.search(text)
    if according is not None:
        name = according.group("name").strip().rstrip(",")
        candidates.append(
            (
                according.start(),
                SourceFinding(
                    source_type=_type_of_name(name),
                    name=name,
                    span=according.span("name"),
                    cue="according_to",
                    checkable=_type_of_name(name) in _CHECKABLE_TYPES,
                ),
            )
        )

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], -len(item[1].name)))
    return candidates[0][1]


#: Names that appear after `according to` are matched against the same
#: lexicons, without requiring a reporting verb - there is no verb there.
_NAMED_AFTER_ACCORDING: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        NAMED_AUTHORITY,
        re.compile(rf"^(?:the\s+)?(?:{'|'.join(_AUTHORITIES)})$", re.IGNORECASE),
    ),
    (
        PUBLISHED_MATERIAL,
        re.compile(rf"^(?:the\s+|an?\s+)?(?:{'|'.join(_MATERIAL)})$", re.IGNORECASE),
    ),
    (
        UNNAMED_SOURCE,
        re.compile(rf"^(?:{'|'.join(_UNNAMED)})$", re.IGNORECASE),
    ),
    (
        PROFESSIONAL_GROUP,
        re.compile(rf"^(?:{_PROPER_NOUN})?(?:{'|'.join(_GROUPS)})$", re.IGNORECASE),
    ),
)


def _type_of_name(name: str) -> str:
    for source_type, pattern in _NAMED_AFTER_ACCORDING:
        if pattern.match(name.strip()):
            return source_type
    # An unrecognised name after `according to` is still a source the sentence
    # names. Saying so - and treating it as checkable, because a named source is
    # checkable - is what keeps `According to the report, ...` from being read as
    # an unverifiable claim.
    return NAMED_SOURCE


def describe() -> tuple[dict[str, object], ...]:
    """The source-type table, for the report and the tests."""

    return tuple(
        {"source_type": source_type, "meaning": meaning, "checkable": checkable}
        for source_type, meaning, checkable in (
            (NAMED_AUTHORITY, "an institution whose statements are on the record", True),
            (PUBLISHED_MATERIAL, "a document whose provenance is given", True),
            (
                NAMED_SOURCE,
                "a source the sentence names that the lexicon cannot type",
                True,
            ),
            (
                PROFESSIONAL_GROUP,
                "a role collective, checkable only when a proper noun names it",
                False,
            ),
            (UNNAMED_SOURCE, "a source the sentence declines to name", False),
        )
    )
