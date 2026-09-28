"""Human agreement evaluation (Phase M4, phase 7).

M3 measured pattern agreement against **generator labels**. That is a
self-consistency check, not validation: the labels were produced by the same
corpus that produced the images, so agreement only shows the pipeline is
internally coherent. M4 must measure agreement between **humans** about whether a
grammar matches the image and whether a strategy is reasonable.

The brief is explicit: *do not compute agreement without a second person.* This
module enforces that literally.

How it stays honest
-------------------

1. :func:`compute_agreement` **refuses to run with fewer than two raters.** It
   raises rather than returning a number that would imply independent judgement.
2. Ratings carry a ``rater_kind``. :data:`RATER_KINDS` includes ``model`` only so
   the type can express what a rating *is*; :func:`compute_agreement` requires at
   least two ``human``-kind raters by default, so an AI-generated rating set
   cannot masquerade as human agreement.
3. :class:`AgreementReport` records ``human_raters`` and
   ``is_human_agreement``, and its JSON says which it is. A provisional fixture
   set is therefore impossible to mistake for a measurement.

The protocol itself (packet generation, rating schema) is fully implemented and
tested. What M4 cannot supply is the humans.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

#: What kind of agent produced a rating. ``model`` exists so a rating set can
#: declare itself non-human; it is not accepted as human evidence.
RATER_KINDS: tuple[str, ...] = ("human", "model", "synthetic_fixture")

#: The two questions the brief requires raters to answer.
RATING_QUESTIONS: tuple[str, ...] = (
    "grammar_matches_image",
    "strategy_is_reasonable",
)

#: Verdicts a rater may give, mapped to a boolean for agreement counting.
VERDICTS: Mapping[str, bool] = {
    "yes": True,
    "no": False,
}

#: Minimum human raters required before agreement may be reported.
MINIMUM_HUMAN_RATERS = 2

PROTOCOL_VERSION = "m4.0.0"


class HumanEvaluationError(Exception):
    """Raised when agreement is requested without adequate human input."""


@dataclass(frozen=True, slots=True)
class Rater:
    """One person (or non-person) who produced ratings."""

    rater_id: str
    rater_kind: str = "human"
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.rater_id.strip():
            raise HumanEvaluationError("rater_id must be non-empty")
        if self.rater_kind not in RATER_KINDS:
            raise HumanEvaluationError(
                f"rater_kind must be one of {list(RATER_KINDS)!r}, got {self.rater_kind!r}"
            )

    @property
    def is_human(self) -> bool:
        return self.rater_kind == "human"

    def as_dict(self) -> dict[str, Any]:
        return {
            "rater_id": self.rater_id,
            "rater_kind": self.rater_kind,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class Rating:
    """One rater's answer to both questions about one item."""

    rater_id: str
    item_id: str
    grammar_matches_image: str
    strategy_is_reasonable: str
    comment: str = ""

    def __post_init__(self) -> None:
        for question in RATING_QUESTIONS:
            verdict = getattr(self, question)
            if verdict not in VERDICTS:
                raise HumanEvaluationError(
                    f"{question} must be one of {list(VERDICTS)!r}, got {verdict!r}"
                )
        if not self.rater_id.strip() or not self.item_id.strip():
            raise HumanEvaluationError("a rating needs both a rater_id and an item_id")

    def verdict(self, question: str) -> bool:
        if question not in RATING_QUESTIONS:
            raise HumanEvaluationError(f"unknown question {question!r}")
        return VERDICTS[getattr(self, question)]

    def as_dict(self) -> dict[str, Any]:
        return {
            "rater_id": self.rater_id,
            "item_id": self.item_id,
            "grammar_matches_image": self.grammar_matches_image,
            "strategy_is_reasonable": self.strategy_is_reasonable,
            "comment": self.comment,
        }


@dataclass(frozen=True, slots=True)
class DisagreementCase:
    """One item where raters did not agree, kept for review."""

    item_id: str
    question: str
    verdicts: Mapping[str, str]
    comments: Mapping[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "question": self.question,
            "verdicts": dict(sorted(self.verdicts.items())),
            "comments": dict(sorted(self.comments.items())),
        }


@dataclass(frozen=True, slots=True)
class AgreementReport:
    """Agreement between raters, with an explicit statement of who they were."""

    protocol_version: str
    item_count: int
    raters: tuple[Rater, ...]
    ratings: tuple[Rating, ...]
    per_question: Mapping[str, Mapping[str, Any]]
    overall_agreement: float
    unanimous_items: int
    disagreement_cases: tuple[DisagreementCase, ...]
    notes: tuple[str, ...] = ()

    @property
    def human_raters(self) -> tuple[Rater, ...]:
        return tuple(rater for rater in self.raters if rater.is_human)

    @property
    def is_human_agreement(self) -> bool:
        """True only when at least two *human* raters contributed."""

        return len(self.human_raters) >= MINIMUM_HUMAN_RATERS

    def as_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "item_count": self.item_count,
            "human_raters": len(self.human_raters),
            "is_human_agreement": self.is_human_agreement,
            "raters": [rater.as_dict() for rater in self.raters],
            "per_question": {
                name: dict(values) for name, values in sorted(self.per_question.items())
            },
            "overall_agreement": self.overall_agreement,
            "unanimous_items": self.unanimous_items,
            "disagreement_cases": [case.as_dict() for case in self.disagreement_cases],
            "notes": list(self.notes),
            "claim": (
                "human agreement measured across "
                f"{len(self.human_raters)} human raters"
                if self.is_human_agreement
                else "NOT human agreement: fewer than two human raters contributed, "
                "so this is an internal consistency check only"
            ),
        }

    def render(self) -> str:
        lines = [
            f"agreement report ({self.protocol_version})",
            f"  items: {self.item_count}  raters: {len(self.raters)} "
            f"({len(self.human_raters)} human)",
            f"  is_human_agreement: {self.is_human_agreement}",
        ]
        for question, values in sorted(self.per_question.items()):
            lines.append(
                f"  {question}: agreement={values['agreement']:.3f} "
                f"({values['agreeing_items']}/{values['items']})"
            )
        lines.append(f"  overall: {self.overall_agreement:.3f}")
        lines.append(f"  unanimous items: {self.unanimous_items}")
        if self.disagreement_cases:
            lines.append(f"  disagreement cases: {len(self.disagreement_cases)}")
        for note in self.notes:
            lines.append(f"  note: {note}")
        return "\n".join(lines)


def compute_agreement(
    ratings: Sequence[Rating],
    raters: Sequence[Rater],
    *,
    require_human: bool = True,
    minimum_human_raters: int = MINIMUM_HUMAN_RATERS,
) -> AgreementReport:
    """Compute per-question and overall agreement.

    Refuses to produce a number when the input cannot support the claim:

    * fewer than two raters overall,
    * fewer than two *human* raters when ``require_human`` is set (the default),
    * any rating from an unknown rater,
    * fewer than two verdicts for an item.

    Agreement is the fraction of rater *pairs* that gave the same verdict, which
    is the standard pairwise definition and does not depend on how many raters
    happened to participate per item.
    """

    if not ratings:
        raise HumanEvaluationError("cannot compute agreement from no ratings")

    by_id = {rater.rater_id: rater for rater in raters}
    unknown = sorted({rating.rater_id for rating in ratings} - set(by_id))
    if unknown:
        raise HumanEvaluationError(
            "ratings reference undeclared raters: " + ", ".join(unknown)
        )

    participating = {rating.rater_id for rating in ratings}
    if len(participating) < 2:
        raise HumanEvaluationError(
            f"agreement needs at least two raters; got {len(participating)}. A single "
            "rater cannot agree with anyone."
        )

    humans = {rid for rid in participating if by_id[rid].is_human}
    if require_human and len(humans) < minimum_human_raters:
        raise HumanEvaluationError(
            f"human agreement needs at least {minimum_human_raters} human raters; "
            f"got {len(humans)}. Refusing to compute a number that would imply "
            "independent human judgement."
        )

    grouped: dict[str, dict[str, Rating]] = {}
    for rating in ratings:
        grouped.setdefault(rating.item_id, {})[rating.rater_id] = rating

    per_question: dict[str, dict[str, Any]] = {}
    disagreements: list[DisagreementCase] = []
    unanimous_items = 0

    for question in RATING_QUESTIONS:
        agreeing_pairs = 0
        total_pairs = 0
        items_scored = 0
        agree_items = 0
        for item_id in sorted(grouped):
            entries = grouped[item_id]
            if len(entries) < 2:
                continue
            items_scored += 1
            verdicts = {rid: r.verdict(question) for rid, r in entries.items()}
            item_agrees = True
            for left, right in combinations(sorted(verdicts), 2):
                total_pairs += 1
                if verdicts[left] == verdicts[right]:
                    agreeing_pairs += 1
                else:
                    item_agrees = False
            if item_agrees:
                agree_items += 1
            else:
                disagreements.append(
                    DisagreementCase(
                        item_id=item_id,
                        question=question,
                        verdicts={
                            rid: getattr(entries[rid], question) for rid in sorted(entries)
                        },
                        comments={
                            rid: entries[rid].comment
                            for rid in sorted(entries)
                            if entries[rid].comment
                        },
                    )
                )
        if items_scored == 0:
            raise HumanEvaluationError(
                f"no item has two verdicts for {question!r}; agreement is undefined"
            )
        per_question[question] = {
            "items": items_scored,
            "agreeing_items": agree_items,
            "agreement": round(agreeing_pairs / total_pairs, 6) if total_pairs else 0.0,
            "pair_count": total_pairs,
        }

    for item_id in sorted(grouped):
        entries = grouped[item_id]
        if len(entries) < 2:
            continue
        if all(
            len({r.verdict(question) for r in entries.values()}) == 1
            for question in RATING_QUESTIONS
        ):
            unanimous_items += 1

    overall = (
        round(
            sum(values["agreement"] * values["pair_count"] for values in per_question.values())
            / sum(values["pair_count"] for values in per_question.values()),
            6,
        )
        if per_question
        else 0.0
    )

    notes: list[str] = []
    if not any(by_id[rid].is_human for rid in participating):
        notes.append(
            "no human rater contributed; this report is an internal consistency check "
            "and must not be presented as human agreement"
        )
    notes.append(
        "agreement is the fraction of rater pairs giving the same verdict, so it does "
        "not depend on how many raters scored each item"
    )

    return AgreementReport(
        protocol_version=PROTOCOL_VERSION,
        item_count=sum(1 for entries in grouped.values() if len(entries) >= 2),
        raters=tuple(sorted(raters, key=lambda r: r.rater_id)),
        ratings=tuple(ratings),
        per_question=per_question,
        overall_agreement=overall,
        unanimous_items=unanimous_items,
        disagreement_cases=tuple(
            sorted(disagreements, key=lambda c: (c.question, c.item_id))
        ),
        notes=tuple(notes),
    )


def build_rating_packet(
    items: Iterable[Mapping[str, Any]],
    *,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build a blank packet for human raters.

    Each item carries the rendered image reference, the extracted grammar as
    readable text, and the distilled strategy statement, plus blank verdict
    fields. Raters see the system's *claim* and judge it — they are not asked to
    reproduce the extraction, because the question is whether the claim is right,
    not whether they would have made it.
    """

    packet_items: list[dict[str, Any]] = []
    for item in items:
        packet_items.append(
            {
                "item_id": str(item["item_id"]),
                "image_reference": str(item.get("image_reference", "")),
                "grammar_summary": str(item.get("grammar_summary", "")),
                "strategy_summary": str(item.get("strategy_summary", "")),
                "ratings": {
                    "grammar_matches_image": None,
                    "strategy_is_reasonable": None,
                    "comment": "",
                },
            }
        )

    packet = {
        "protocol_version": PROTOCOL_VERSION,
        "instructions": (
            "For each item, read the grammar and strategy the system produced for the "
            "image, then answer both questions with 'yes' or 'no'. Judge whether the "
            "claim is correct for the image, not whether you would have described it "
            "the same way. Add a comment whenever you answer 'no'."
        ),
        "questions": {
            "grammar_matches_image": (
                "Does the described grammar match what the image actually shows?"
            ),
            "strategy_is_reasonable": (
                "Is the described strategy a reasonable account of how this creator "
                "composes?"
            ),
        },
        "allowed_verdicts": sorted(VERDICTS),
        "minimum_raters": MINIMUM_HUMAN_RATERS,
        "items": packet_items,
    }

    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return packet


def write_agreement_report(report: AgreementReport, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


__all__ = [
    "MINIMUM_HUMAN_RATERS",
    "PROTOCOL_VERSION",
    "RATER_KINDS",
    "RATING_QUESTIONS",
    "VERDICTS",
    "AgreementReport",
    "DisagreementCase",
    "HumanEvaluationError",
    "Rating",
    "Rater",
    "build_rating_packet",
    "compute_agreement",
    "write_agreement_report",
]
