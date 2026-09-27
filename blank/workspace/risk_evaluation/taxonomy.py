"""The Creator Agent finance risk taxonomy.

Each category states what the risk *is* (definition), what the writer is trying
to do (intent), what evidence would have to accompany the claim, and the
framework's default severity and action.

The taxonomy is deliberately finer grained than the current keyword evaluator:
`financial_guarantee` is separated from `investment_advice`, and
`emotional_manipulation` is named explicitly. The mapping to what the existing
evaluator can actually distinguish is declared per category in
`evaluator_categories`, so the gap between the taxonomy and the current
capability is recorded data rather than an assumption.

This module defines policy only. It does not detect anything and it does not
modify the existing plugin rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .model import ACTIONS, SEVERITIES


@dataclass(frozen=True, slots=True)
class RiskCategory:
    """One taxonomy entry."""

    name: str
    definition: str
    intent: str
    evidence_required: tuple[str, ...]
    severity: str
    action: str
    #: Categories the current keyword evaluator can emit that belong here.
    evaluator_categories: tuple[str, ...]
    examples: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"{self.name}: unknown severity {self.severity!r}")
        if self.action not in ACTIONS:
            raise ValueError(f"{self.name}: unknown action {self.action!r}")
        if not self.evidence_required:
            raise ValueError(f"{self.name}: evidence requirements must not be empty")

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "definition": self.definition,
            "intent": self.intent,
            "evidence_required": list(self.evidence_required),
            "severity": self.severity,
            "action": self.action,
            "evaluator_categories": list(self.evaluator_categories),
            "examples": list(self.examples),
        }


RISK_TAXONOMY: tuple[RiskCategory, ...] = (
    RiskCategory(
        name="investment_advice",
        definition=(
            "Content that directs the reader to take a specific investment "
            "action, or that recommends a security, product or position."
        ),
        intent="Induce the reader to act on the market.",
        evidence_required=("disclaimer", "evidence", "uncertainty"),
        severity="block",
        action="block",
        evaluator_categories=("investment_advice",),
        examples=("buy", "sell", "invest", "should purchase"),
    ),
    RiskCategory(
        name="market_prediction",
        definition=(
            "Content that states a future market outcome as a certainty rather "
            "than as a conditional or hedged projection."
        ),
        intent="Replace the reader's uncertainty with the writer's certainty.",
        evidence_required=("source", "data", "time_range"),
        severity="warning",
        action="require_evidence",
        evaluator_categories=("market_prediction",),
        examples=("definitely rise", "guaranteed growth", "certain target price"),
    ),
    RiskCategory(
        name="financial_guarantee",
        definition=(
            "Content that promises a return or asserts that a loss is "
            "impossible, or that removes risk from a financial decision."
        ),
        intent="Remove the reader's perception of risk.",
        evidence_required=("basis", "counter_evidence", "uncertainty"),
        severity="block",
        action="block",
        # The current evaluator folds guarantee wording into investment_advice,
        # so it cannot report this category distinctly. Recorded, not hidden.
        evaluator_categories=("investment_advice",),
        examples=("risk free", "guaranteed profit", "cannot fail"),
    ),
    RiskCategory(
        name="unverified_information",
        definition=(
            "Content that circulates a claim without a reliable, checkable "
            "source, including rumour and anonymous attribution."
        ),
        intent="Borrow authority the writer cannot demonstrate.",
        evidence_required=("source", "verification"),
        severity="warning",
        action="require_evidence",
        evaluator_categories=("unverified_fact",),
        examples=("insider information", "rumor", "anonymous source"),
    ),
    RiskCategory(
        name="emotional_manipulation",
        definition=(
            "Content that bypasses reasoning through panic, urgency or "
            "exaggerated language instead of evidence."
        ),
        intent="Substitute emotional pressure for explanation.",
        evidence_required=("neutral_restatement",),
        severity="warning",
        action="downrank",
        evaluator_categories=("emotional_language",),
        examples=("panic", "everyone is buying", "you will miss out"),
    ),
)

_BY_NAME: Mapping[str, RiskCategory] = {item.name: item for item in RISK_TAXONOMY}


def category_names() -> tuple[str, ...]:
    return tuple(item.name for item in RISK_TAXONOMY)


def category(name: str) -> RiskCategory:
    """Return one taxonomy entry, or raise if it is not defined."""

    try:
        return _BY_NAME[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown risk category {name!r}; expected one of {category_names()}"
        ) from exc


def all_categories() -> Mapping[str, RiskCategory]:
    return dict(_BY_NAME)


def categories_for_evaluator_category(evaluator_category: str) -> tuple[str, ...]:
    """Map an evaluator category back to the taxonomy categories it may mean.

    A single evaluator category can correspond to more than one taxonomy
    category, which is exactly the ambiguity a finer evaluator would resolve.
    """

    return tuple(
        item.name
        for item in RISK_TAXONOMY
        if evaluator_category in item.evaluator_categories
    )
