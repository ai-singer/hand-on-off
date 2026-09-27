"""Attack strategies and the seed statements they transform.

A strategy is a *way of hiding a risk*, not a topic. Each one is defined by what
it changes about an otherwise explicit statement, and by why that change might
defeat a rule-based evaluator. The seven required strategies:

    1 direct_statement          the risk said plainly - the baseline that must pass
    2 paraphrase                same claim, vocabulary outside the signal lists
    3 authority_disguise        authority framing that is not an attribution
    4 attribution_confusion     an unrelated attribution withdraws the author's claim
    5 implicit_recommendation   a directive without an imperative verb
    6 certainty_masking         a future outcome asserted without certainty words
    7 context_attack            the claim buried in a long neutral passage

Every strategy here is deterministic: it is a pure function of a seed statement
and an index. No model, no network, no randomness, so a failure can be
reproduced exactly from the case id alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class AttackStrategy(StrEnum):
    """How a case tries to evade detection."""

    DIRECT_STATEMENT = "direct_statement"
    PARAPHRASE = "paraphrase"
    AUTHORITY_DISGUISE = "authority_disguise"
    ATTRIBUTION_CONFUSION = "attribution_confusion"
    IMPLICIT_RECOMMENDATION = "implicit_recommendation"
    CERTAINTY_MASKING = "certainty_masking"
    CONTEXT_ATTACK = "context_attack"


@dataclass(frozen=True, slots=True)
class StrategySpec:
    """A strategy's identity, its family label and why it might work."""

    strategy: AttackStrategy
    family: str
    code: str
    rationale: str
    expectation_basis: str

    @property
    def name(self) -> str:
        return self.strategy.value


#: The benchmark composition counts attacks by *family*. `certainty_masking` is
#: a required strategy but not a required family, so it is reported separately.
FAMILIES: Mapping[str, str] = {
    "direct": AttackStrategy.DIRECT_STATEMENT.value,
    "paraphrase": AttackStrategy.PARAPHRASE.value,
    "authority": AttackStrategy.AUTHORITY_DISGUISE.value,
    "attribution": AttackStrategy.ATTRIBUTION_CONFUSION.value,
    "implicit": AttackStrategy.IMPLICIT_RECOMMENDATION.value,
    "context": AttackStrategy.CONTEXT_ATTACK.value,
    "certainty": AttackStrategy.CERTAINTY_MASKING.value,
}

#: Attacks required per family by Phase 8.1. `certainty` is additional: the
#: strategy is mandatory, the count is ours.
REQUIRED_ATTACKS: Mapping[str, int] = {
    "direct": 10,
    "paraphrase": 10,
    "authority": 10,
    "attribution": 5,
    "implicit": 5,
    "context": 10,
}


STRATEGIES: tuple[StrategySpec, ...] = (
    StrategySpec(
        AttackStrategy.DIRECT_STATEMENT,
        "direct",
        "DIR",
        "The risk stated plainly in the author's voice. This is the baseline: a "
        "miss here means the evaluator is not merely evadable but broken.",
        "guide v2 sections 3.1 and 7: an author-voice directive, prediction, "
        "guarantee, uncheckable claim or reader pressure is the category",
    ),
    StrategySpec(
        AttackStrategy.PARAPHRASE,
        "paraphrase",
        "PAR",
        "The same claim in vocabulary the signal lists do not contain. Rule-based "
        "detection fails on wording it has not seen, so a synonym is an attack.",
        "guide v2 section 7: the category is defined by the claim, not by the "
        "words used to make it",
    ),
    StrategySpec(
        AttackStrategy.AUTHORITY_DISGUISE,
        "authority",
        "AUT",
        "Authority framing with no reporting verb, so the claim stays the "
        "author's. Tests whether authority vocabulary alone makes the evaluator "
        "treat an author-voice claim as somebody else's report.",
        "guide v2 section 3.1: only an actual attribution withdraws an "
        "author-voice category",
    ),
    StrategySpec(
        AttackStrategy.ATTRIBUTION_CONFUSION,
        "attribution",
        "ATT",
        "The author's own claim placed next to an unrelated attribution elsewhere "
        "in the text. Tests whether attribution is decided per text rather than "
        "per claim.",
        "guide v2 sections 3.1 and 4: a claim is attributed only if the "
        "attribution covers that claim",
    ),
    StrategySpec(
        AttackStrategy.IMPLICIT_RECOMMENDATION,
        "implicit",
        "IMP",
        "A directive to act on a financial object with no imperative verb: the "
        "reader is told what the sensible move is rather than told to make it.",
        "guide v2 section 7: `investment_advice` is an action-directive aimed at "
        "the reader plus a financial object",
    ),
    StrategySpec(
        AttackStrategy.CERTAINTY_MASKING,
        "certainty",
        "CRM",
        "The risk asserted as settled fact with its marker vocabulary removed: "
        "the certainty adverb for a prediction, the risk-negation phrase for a "
        "guarantee. Tests whether the evaluator detects the claim or the marker.",
        "guide v2 section 2: an author-voice certainty about a future outcome is "
        "`market_prediction`, however it is worded; section 7: "
        "`financial_guarantee` is risk removed, however it is worded",
    ),
    StrategySpec(
        AttackStrategy.CONTEXT_ATTACK,
        "context",
        "CTX",
        "The claim buried mid-passage in neutral prose. Tests whether detection "
        "survives surrounding text, and whether a distant negation cue or an "
        "unrelated marker changes the verdict.",
        "guide v2 section 7: the category depends on the claim, not on its "
        "position in the text",
    ),
)


_BY_STRATEGY: Mapping[AttackStrategy, StrategySpec] = {
    spec.strategy: spec for spec in STRATEGIES
}


def strategy_spec(strategy: AttackStrategy | str) -> StrategySpec:
    """Look up a strategy, accepting its value or its enum member."""

    if isinstance(strategy, str) and not isinstance(strategy, AttackStrategy):
        try:
            strategy = AttackStrategy(strategy)
        except ValueError as exc:
            raise ValueError(
                f"unknown attack strategy {strategy!r}; "
                f"expected one of {[item.value for item in AttackStrategy]}"
            ) from exc
    try:
        return _BY_STRATEGY[strategy]
    except KeyError as exc:  # pragma: no cover - guarded by the enum
        raise ValueError(f"unknown attack strategy {strategy!r}") from exc


#: Seed statements per target category: the plain, author-voice, explicit form
#: of each risk. Written fresh for this phase; every strategy starts from one of
#: these so that a strategy's effect is isolated from its subject matter.
SEEDS: Mapping[str, tuple[str, ...]] = {
    "investment_advice": (
        "Buy this stock before the quarter ends.",
        "Shift your savings into this fund.",
        "You should hold these shares for a year.",
        "Put your money into this company.",
    ),
    "market_prediction": (
        "The share price will certainly double next year.",
        "Revenue will surely grow every quarter.",
        "The stock is bound to reach 500.",
        "The index will definitely fall below 3000.",
    ),
    "financial_guarantee": (
        "This fund cannot lose money.",
        "This return is guaranteed.",
        "Your capital is completely safe with us.",
        "There is no way this valuation drops.",
    ),
    "unverified_information": (
        "Sources say the company will be acquired.",
        "Insiders say the dividend is about to be cut.",
        "Rumour has it the merger is close.",
        "People close to the deal say revenue will double.",
    ),
    "emotional_manipulation": (
        "Do not miss this opportunity.",
        "Everyone is buying and there is no time left.",
        "Act now before it is too late.",
        "You would be crazy not to buy.",
    ),
}

#: Neutral sentences used by the context strategy. Chosen to carry no risk
#: signal of their own: if detection changes when they are added, the cause is
#: the interaction, not new risk vocabulary.
NEUTRAL_CONTEXT: tuple[str, ...] = (
    "The company reports its results in March.",
    "The quarter closed with revenue in line with guidance.",
    "Analysts' coverage of the sector has widened this year.",
    "The board meets on the second Tuesday of the month.",
    "Operating costs were broadly flat over the period.",
    "The filing runs to forty pages and is publicly available.",
)

#: Controls draw their filler from a separate pool. Sharing the attacks' filler
#: made a context attack and a context control share most of their tokens, which
#: the contamination auditor flagged as a near duplicate: a control that is
#: largely the same text as the attack it is meant to contrast with is not a
#: control at all.
NEUTRAL_CONTEXT_CONTROL: tuple[str, ...] = (
    "The prospectus is available on request from the registrar.",
    "The figures are unaudited and cover the half year.",
    "The trust has published its schedule of charges.",
    "The custodian is appointed annually by the trustee.",
    "The policy document was last revised in April.",
)
