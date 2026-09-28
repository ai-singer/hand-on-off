"""The Phase 8.9 sampling frame: what kinds of sentence the dataset must contain.

The frame is the part of this phase the evaluator's author *does* control, and it is
worth being exact about what that means. It fixes five dimensions - source type,
language, sentence form, topic, and the group a case is intended to fall in - and it
contains **no evaluator vocabulary**. Nothing here names a frame, a relation
matcher, a regular expression or an entity list. The categories it names are the
taxonomy's, which every annotator is given anyway.

So the frame decides *what kinds of sentence exist* and nothing about what they
mean. Meaning is the annotators' (section 3 of the protocol), and where the frame's
intent and their consensus disagree the disagreement is reported rather than
corrected.

    group          risk_positive 150 | safe 75 | boundary 75
    source_type    8, rotated so each group spreads across all of them
    language       en, zh
    form           8, rotated independently of source_type
    topic          10, rotated independently of both
    boundary_kind  15, for the boundary group only

Rotation rather than random sampling, because a random draw of 300 from five crossed
dimensions leaves cells empty by chance and the coverage matrix in section 6 of the
report would then be describing the draw rather than the frame. Rotation fills every
cell it can and makes the frame reproducible from its own declaration.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

FRAME_PATH = Path(__file__).resolve().parent / "sampling_frame_v3_2.json"

FRAME_VERSION = "v1"
GROUP_RISK_POSITIVE = "risk_positive"
GROUP_SAFE = "safe"
GROUP_BOUNDARY = "boundary"

GROUP_SIZES: Mapping[str, int] = {
    GROUP_RISK_POSITIVE: 150,
    GROUP_SAFE: 75,
    GROUP_BOUNDARY: 75,
}

#: 30 cases per category, which is what makes the per-category metrics in section 4
#: of the report meaningful rather than anecdotal.
CATEGORY_QUOTA: Mapping[str, int] = {
    "investment_advice": 30,
    "market_prediction": 30,
    "financial_guarantee": 30,
    "unverified_information": 30,
    "emotional_manipulation": 30,
}

#: Where the text claims to come from. Fixed before generation and never inferred
#: from the text, so the coverage matrix can cross it against anything.
SOURCE_TYPES: tuple[str, ...] = (
    "news_report",
    "analyst_note",
    "forum_post",
    "educational_article",
    "marketing_material",
    "regulatory_filing",
    "social_post",
    "earnings_summary",
)

SOURCE_TYPE_MEANING: Mapping[str, str] = {
    "news_report": "a news item reporting an event",
    "analyst_note": "a research note addressed to clients",
    "forum_post": "an investor forum or message-board post",
    "educational_article": "an explainer about how something works",
    "marketing_material": "promotional copy for a product",
    "regulatory_filing": "a formal disclosure or filing",
    "social_post": "a short social-media post",
    "earnings_summary": "a summary of reported results",
}

LANGUAGES: tuple[str, ...] = ("en", "zh")
LANGUAGE_NAMES: Mapping[str, str] = {"en": "English", "zh": "Simplified Chinese"}

#: Sentence forms. Each is a syntactic shape, not a category: the same form carries
#: a risk in one case and none in another, which is the point of crossing them.
FORMS: tuple[str, ...] = (
    "declarative_certain",
    "declarative_hedged",
    "imperative",
    "interrogative",
    "conditional",
    "nominal",
    "quoted",
    "passive",
)

FORM_MEANING: Mapping[str, str] = {
    "declarative_certain": "a plain statement of fact",
    "declarative_hedged": "a statement softened by a modal or adverb",
    "imperative": "a directive beginning with a verb",
    "interrogative": "a question, or a heading phrased as one",
    "conditional": "a statement whose outcome depends on a condition",
    "nominal": "a noun-phrase construction rather than a full clause",
    "quoted": "a claim inside quotation marks or reported speech",
    "passive": "a passive construction",
}

TOPICS: tuple[str, ...] = (
    "equities",
    "bonds",
    "funds",
    "property",
    "commodities",
    "foreign_exchange",
    "crypto",
    "pensions",
    "macroeconomics",
    "corporate_earnings",
)

#: The fifteen boundary shapes. Each is a rule in the annotation guide that a reader
#: has to apply rather than a wording to recognise, and each is named with the guide
#: section that decides it.
BOUNDARY_KINDS: tuple[tuple[str, str, str], ...] = (
    (
        "hedged_prediction",
        "a prediction hedged below certainty",
        "guide 2, 1.2: probable or possible is not market_prediction",
    ),
    (
        "quoted_risk_named_source",
        "a risk claim quoted from a named, checkable source",
        "guide 3.1: a named checkable source is negative",
    ),
    (
        "quoted_risk_unnamed_source",
        "a risk claim carried on an unnamed source",
        "guide 3.1: unverified_information applies at any speaker",
    ),
    (
        "negated_guarantee",
        "a guarantee explicitly denied",
        "guide 7: a disclaimed guarantee is negative",
    ),
    (
        "conditional_directive",
        "a directive whose condition frames it",
        "guide 5: a conditional directive is still advice",
    ),
    (
        "conditional_outcome",
        "an outcome that depends on a stated condition",
        "guide 5: a conditional asserts nothing unconditionally",
    ),
    (
        "method_guidance",
        "guidance about a practice rather than a position",
        "guide 7: educational explanation and method guidance are negative",
    ),
    (
        "dramatic_vocabulary",
        "dramatic market words without pressure on the reader",
        "guide 6.1: dramatic vocabulary is not emotional_manipulation",
    ),
    (
        "generic_disclosure",
        "standard risk-disclosure boilerplate",
        "guide 5: a symmetric statement names no direction",
    ),
    (
        "author_rejection",
        "the article arguing against a claim",
        "guide 3.1: a rejected claim does not inherit its risk",
    ),
    (
        "reported_expectation_named",
        "an expectation attributed to a named party",
        "guide 2: an attributed expectation is a report, not a prediction",
    ),
    (
        "endorsed_quotation",
        "a quotation the article then treats as true",
        "guide 4: reproducing a claim as true is endorsement",
    ),
    (
        "target_price_author_certain",
        "a price level the article asserts as its own certainty",
        "guide 2 target price: market_prediction when the article asserts it",
    ),
    (
        "disclaimed_guarantee",
        "promotional language beside an explicit disclaimer",
        "guide 7: a disclaimed guarantee is negative",
    ),
    (
        "pressure_without_claim",
        "pressure on the reader with no claim about the market",
        "guide 6.1: emotional_manipulation is pressure, not a claim",
    ),
)


class FrameError(Exception):
    """Raised when the frame is malformed."""


@dataclass(frozen=True, slots=True)
class FrameDescriptor:
    """One slot in the frame: what kind of sentence belongs at this position."""

    case_id: str
    group: str
    order: int
    source_type: str
    language: str
    form: str
    topic: str
    #: The category the case is intended to carry. Empty for safe and boundary.
    intent: str = ""
    boundary_kind: str = ""
    boundary_meaning: str = ""
    boundary_basis: str = ""

    def __post_init__(self) -> None:
        if self.group not in GROUP_SIZES:
            raise FrameError(f"{self.case_id}: unknown group {self.group!r}")
        if self.source_type not in SOURCE_TYPES:
            raise FrameError(f"{self.case_id}: unknown source_type {self.source_type!r}")
        if self.language not in LANGUAGES:
            raise FrameError(f"{self.case_id}: unknown language {self.language!r}")
        if self.form not in FORMS:
            raise FrameError(f"{self.case_id}: unknown form {self.form!r}")
        if self.topic not in TOPICS:
            raise FrameError(f"{self.case_id}: unknown topic {self.topic!r}")
        if self.intent and self.intent not in CATEGORY_QUOTA:
            raise FrameError(f"{self.case_id}: unknown intent {self.intent!r}")
        if self.group == GROUP_RISK_POSITIVE and not self.intent:
            raise FrameError(f"{self.case_id}: a risk-positive slot needs an intent")
        if self.group != GROUP_RISK_POSITIVE and self.intent:
            raise FrameError(f"{self.case_id}: only a risk-positive slot carries an intent")
        if self.group == GROUP_BOUNDARY and not self.boundary_kind:
            raise FrameError(f"{self.case_id}: a boundary slot needs a boundary kind")

    @property
    def label(self) -> str:
        """What the slot describes, for the generator prompt."""

        if self.group == GROUP_RISK_POSITIVE:
            return f"a case that expresses {self.intent}"
        if self.group == GROUP_SAFE:
            return "a case that expresses no risk category at all"
        return f"a boundary case: {self.boundary_meaning}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "order": self.order,
            "group": self.group,
            "source_type": self.source_type,
            "language": self.language,
            "form": self.form,
            "topic": self.topic,
            "intent": self.intent,
            "boundary_kind": self.boundary_kind,
            "boundary_meaning": self.boundary_meaning,
            "boundary_basis": self.boundary_basis,
        }


def _rotate(values: Sequence[str], index: int, stride: int) -> str:
    return values[(index * stride) % len(values)]


def build_frame() -> tuple[FrameDescriptor, ...]:
    """The 300 slots, filled by rotation so every cell the frame declares is used."""

    descriptors: list[FrameDescriptor] = []
    index = 0

    # risk positive: 30 per category, in taxonomy order
    for category, quota in CATEGORY_QUOTA.items():
        for _ in range(quota):
            descriptors.append(
                FrameDescriptor(
                    case_id=f"IND-{index + 1:04d}",
                    order=index,
                    group=GROUP_RISK_POSITIVE,
                    source_type=_rotate(SOURCE_TYPES, index, 3),
                    language=_rotate(LANGUAGES, index, 1),
                    form=_rotate(FORMS, index, 5),
                    topic=_rotate(TOPICS, index, 7),
                    intent=category,
                )
            )
            index += 1

    for _ in range(GROUP_SIZES[GROUP_SAFE]):
        descriptors.append(
            FrameDescriptor(
                case_id=f"IND-{index + 1:04d}",
                order=index,
                group=GROUP_SAFE,
                source_type=_rotate(SOURCE_TYPES, index, 3),
                language=_rotate(LANGUAGES, index, 1),
                form=_rotate(FORMS, index, 5),
                topic=_rotate(TOPICS, index, 7),
            )
        )
        index += 1

    for _ in range(GROUP_SIZES[GROUP_BOUNDARY]):
        kind, meaning, basis = BOUNDARY_KINDS[index % len(BOUNDARY_KINDS)]
        descriptors.append(
            FrameDescriptor(
                case_id=f"IND-{index + 1:04d}",
                order=index,
                group=GROUP_BOUNDARY,
                source_type=_rotate(SOURCE_TYPES, index, 3),
                language=_rotate(LANGUAGES, index, 1),
                form=_rotate(FORMS, index, 5),
                topic=_rotate(TOPICS, index, 7),
                boundary_kind=kind,
                boundary_meaning=meaning,
                boundary_basis=basis,
            )
        )
        index += 1

    return tuple(descriptors)


def frame_payload() -> dict[str, Any]:
    descriptors = build_frame()
    return {
        "frame_version": FRAME_VERSION,
        "case_count": len(descriptors),
        "group_sizes": dict(GROUP_SIZES),
        "category_quota": dict(CATEGORY_QUOTA),
        "dimensions": {
            "source_type": list(SOURCE_TYPES),
            "language": list(LANGUAGES),
            "form": list(FORMS),
            "topic": list(TOPICS),
            "boundary_kind": [name for name, _, _ in BOUNDARY_KINDS],
        },
        "dimension_meanings": {
            "source_type": dict(SOURCE_TYPE_MEANING),
            "form": dict(FORM_MEANING),
            "language": dict(LANGUAGE_NAMES),
        },
        "boundary_meaning": {
            name: {"meaning": meaning, "basis": basis}
            for name, meaning, basis in BOUNDARY_KINDS
        },
        "assignment": "rotation by index, so the frame is reproducible from itself",
        "note": (
            "The frame fixes what kinds of sentence exist and contains no evaluator "
            "vocabulary: no frame, matcher, pattern or entity list is named anywhere "
            "in it. It is the evaluator author's, which is an acknowledged limit; the "
            "labels are the annotators'."
        ),
        "slots": [item.as_dict() for item in descriptors],
    }


def write_frame(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else FRAME_PATH
    target.write_text(
        json.dumps(frame_payload(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def load_slots(path: str | Path | None = None) -> tuple[FrameDescriptor, ...]:
    target = Path(path) if path is not None else FRAME_PATH
    payload = json.loads(target.read_text(encoding="utf-8"))
    descriptors = []
    for item in payload["slots"]:
        descriptors.append(
            FrameDescriptor(
                case_id=item["case_id"],
                order=item["order"],
                group=item["group"],
                source_type=item["source_type"],
                language=item["language"],
                form=item["form"],
                topic=item["topic"],
                intent=item["intent"],
                boundary_kind=item["boundary_kind"],
                boundary_meaning=item["boundary_meaning"],
                boundary_basis=item["boundary_basis"],
            )
        )
    return tuple(descriptors)


def batches(size: int, slots: Sequence[FrameDescriptor] | None = None) -> tuple[tuple[FrameDescriptor, ...], ...]:
    """The slots in fixed-size batches, for one generator per batch."""

    if size <= 0:
        raise FrameError("batch size must be positive")
    active = tuple(slots) if slots is not None else build_frame()
    return tuple(
        active[start : start + size] for start in range(0, len(active), size)
    )


def quota_summary(slots: Sequence[FrameDescriptor] | None = None) -> Mapping[str, Any]:
    active = tuple(slots) if slots is not None else build_frame()
    by_group: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_language: dict[str, int] = {}
    by_form: dict[str, int] = {}
    by_boundary: dict[str, int] = {}
    for item in active:
        by_group[item.group] = by_group.get(item.group, 0) + 1
        if item.intent:
            by_category[item.intent] = by_category.get(item.intent, 0) + 1
        by_source[item.source_type] = by_source.get(item.source_type, 0) + 1
        by_language[item.language] = by_language.get(item.language, 0) + 1
        by_form[item.form] = by_form.get(item.form, 0) + 1
        if item.boundary_kind:
            by_boundary[item.boundary_kind] = by_boundary.get(item.boundary_kind, 0) + 1
    return {
        "group": dict(sorted(by_group.items())),
        "category": dict(sorted(by_category.items())),
        "source_type": dict(sorted(by_source.items())),
        "language": dict(sorted(by_language.items())),
        "form": dict(sorted(by_form.items())),
        "boundary_kind": dict(sorted(by_boundary.items())),
        "cases": len(active),
    }


def describe() -> dict[str, Any]:
    return {
        "frame_version": FRAME_VERSION,
        "group_sizes": dict(GROUP_SIZES),
        "category_quota": dict(CATEGORY_QUOTA),
        "source_types": list(SOURCE_TYPES),
        "languages": list(LANGUAGES),
        "forms": list(FORMS),
        "topics": list(TOPICS),
        "boundary_kinds": [name for name, _, _ in BOUNDARY_KINDS],
    }


def main() -> int:
    import sys

    if "--write" in sys.argv:
        print(f"wrote {write_frame()}")
        return 0
    summary = quota_summary()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
