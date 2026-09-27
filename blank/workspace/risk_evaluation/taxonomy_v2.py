"""Taxonomy v2: attribution, certainty and a repaired prediction definition.

Taxonomy v1 (`risk_evaluation/taxonomy.py`) is **not modified or replaced**. It
stays the standard that `semantic/v1` and `semantic/v2` were labelled under.
Version 2 layers three things on top:

1. **A repaired `market_prediction`.** v1 defines it as an outcome stated *as a
   certainty*, which left three different statements competing for one label:
   an explicit prediction, a reported expectation and a scenario analysis. v2
   states which of the three is the prediction.
2. **An orthogonal attribution dimension** (`statement_source`). Whether a claim
   is the author's is a separate question from which category it belongs to, so
   it is a separate field rather than a new risk category.
3. **A certainty dimension** (`certainty_level`), so hedging is recorded rather
   than inferred from vocabulary.

It also states the precedence rule that v1 left implicit: dramatic market
vocabulary is not, by itself, emotional manipulation.

No new risk categories are introduced, so the five v1 categories and their
severities are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .taxonomy import RISK_TAXONOMY, RiskCategory, category as category_v1


TAXONOMY_VERSION = "2.0.0"

#: Who makes the claim. Orthogonal to the category.
STATEMENT_SOURCES = ("author", "third_party", "quoted", "unknown")

#: How strongly the text asserts its claim.
CERTAINTY_LEVELS = ("certain", "probable", "possible", "hypothetical")

#: Categories that require the claim to be in the author's own voice. An
#: attributed recommendation is a report of advice, not advice; an attributed
#: guarantee is not the article's guarantee.
AUTHOR_VOICE_CATEGORIES = (
    "investment_advice",
    "market_prediction",
    "financial_guarantee",
    "emotional_manipulation",
)

#: Categories that are *about* attribution rather than expressed in a voice, so
#: they apply regardless of `statement_source`.
ATTRIBUTION_AGNOSTIC_CATEGORIES = ("unverified_information",)


@dataclass(frozen=True, slots=True)
class MarketClaimCase:
    """One of the three statements that compete for `market_prediction`."""

    name: str
    is_direct_prediction: bool
    definition: str
    example: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "is_direct_prediction": self.is_direct_prediction,
            "definition": self.definition,
            "example": self.example,
        }


MARKET_CLAIM_CASES: tuple[MarketClaimCase, ...] = (
    MarketClaimCase(
        name="explicit_prediction",
        is_direct_prediction=True,
        definition=(
            "The author asserts a future market outcome as a certainty in their "
            "own voice. This is the only case that is `market_prediction`."
        ),
        example="The stock will rise tomorrow.",
    ),
    MarketClaimCase(
        name="attribution_expectation",
        is_direct_prediction=False,
        definition=(
            "A future outcome reported as someone else's expectation, estimate "
            "or belief. Reporting an expectation is not making a prediction, so "
            "this is not `market_prediction`. It may still be "
            "`unverified_information` when the source cannot be checked."
        ),
        example="Management expects the stock to reach 500.",
    ),
    MarketClaimCase(
        name="scenario_analysis",
        is_direct_prediction=False,
        definition=(
            "A conditional or hypothetical outcome. The claim depends on a "
            "condition the text states, so it asserts nothing unconditionally "
            "and is not `market_prediction`."
        ),
        example="If rates fall, the stock may rise.",
    ),
)

#: v1 categories and severities are unchanged; this only names the v2 ordering
#: used to break ties.
CATEGORY_PRECEDENCE: tuple[str, ...] = (
    "investment_advice",
    "financial_guarantee",
    "market_prediction",
    "unverified_information",
    "emotional_manipulation",
)


def market_claim_case(
    *, statement_source: str, certainty_level: str
) -> MarketClaimCase:
    """Classify a market claim into one of the three v2 cases."""

    if statement_source not in STATEMENT_SOURCES:
        raise ValueError(
            f"statement_source must be one of {STATEMENT_SOURCES}, "
            f"got {statement_source!r}"
        )
    if certainty_level not in CERTAINTY_LEVELS:
        raise ValueError(
            f"certainty_level must be one of {CERTAINTY_LEVELS}, "
            f"got {certainty_level!r}"
        )
    if certainty_level == "hypothetical":
        return MARKET_CLAIM_CASES[2]
    if statement_source != "author":
        return MARKET_CLAIM_CASES[1]
    if certainty_level == "certain":
        return MARKET_CLAIM_CASES[0]
    # Hedged author claims -- probable or possible -- are neither certain
    # assertions nor attributions; v1 already excludes hedged projections, so
    # they fall under the scenario case.
    return MARKET_CLAIM_CASES[2]


def is_direct_prediction(*, statement_source: str, certainty_level: str) -> bool:
    """True only for an author-voice certainty about a future outcome."""

    return market_claim_case(
        statement_source=statement_source, certainty_level=certainty_level
    ).is_direct_prediction


def requires_author_voice(category: str) -> bool:
    return category in AUTHOR_VOICE_CATEGORIES


def applies_regardless_of_voice(category: str) -> bool:
    return category in ATTRIBUTION_AGNOSTIC_CATEGORIES


def resolve_category_conflicts(
    categories: Sequence[str],
    *,
    reader_pressure: bool,
    statement_source: str,
) -> tuple[str, ...]:
    """Apply the v2 precedence rule.

    The rule that v1 left implicit: **dramatic market vocabulary is not
    emotional manipulation.** A sentence that asserts a market outcome and uses
    a dramatic word for it ("the market will crash") is a prediction. Emotional
    manipulation requires pressure aimed at the reader -- an imperative to act,
    a deadline, or herd framing.

    Also drops author-voice categories when the claim is attributed, since an
    attributed claim is not the article's claim.
    """

    resolved = set(categories)
    if "emotional_manipulation" in resolved and not reader_pressure:
        resolved.discard("emotional_manipulation")
    if statement_source != "author":
        resolved.difference_update(AUTHOR_VOICE_CATEGORIES)
    return tuple(
        name for name in CATEGORY_PRECEDENCE if name in resolved
    ) + tuple(sorted(resolved - set(CATEGORY_PRECEDENCE)))


def categories_v2() -> Mapping[str, RiskCategory]:
    """The five v1 categories, unchanged. v2 adds no risk category."""

    return {entry.name: entry for entry in RISK_TAXONOMY}


def category_v2(name: str) -> RiskCategory:
    return category_v1(name)


def taxonomy_v2_payload() -> dict[str, object]:
    """Canonical description used for hashing."""

    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "categories": [entry.as_dict() for entry in RISK_TAXONOMY],
        "statement_sources": list(STATEMENT_SOURCES),
        "certainty_levels": list(CERTAINTY_LEVELS),
        "author_voice_categories": list(AUTHOR_VOICE_CATEGORIES),
        "attribution_agnostic_categories": list(ATTRIBUTION_AGNOSTIC_CATEGORIES),
        "category_precedence": list(CATEGORY_PRECEDENCE),
        "market_claim_cases": [case.as_dict() for case in MARKET_CLAIM_CASES],
    }
