"""Independent benchmark for Phase 7.3 validation.

**Provenance and independence.** These 100 cases were authored *after*
`risk_evaluation/frozen_baseline.json` was written, and the labels were derived
from the taxonomy definitions in `risk_evaluation/taxonomy.py`, not from
evaluator output. No case was added, removed, relabelled or reworded after the
first evaluation run. The frozen hash is asserted by the test suite, so an edit
to the evaluator during validation would break the build.

**Honest limitation.** This is *methodological* independence, not *authorial*
independence: the same person wrote the taxonomy, the evaluator and these
cases. The labels follow the taxonomy rather than the code, and the cases do
not reuse the 50 development cases, but shared authorship remains a source of
correlated bias. The report states this plainly and does not treat the
resulting numbers as clean out-of-sample estimates.

Annotation records carry the format required by the phase:

    id, text, expected_categories, risk_level, annotation_reason,
    source_type, created_after_evaluator_freeze
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .taxonomy import category as taxonomy_category


FREEZE_REFERENCE = "risk_evaluation/frozen_baseline.json"
SOURCE_TYPE = "synthetic"

RISK = "risk"
SAFE = "safe"
BOUNDARY = "boundary"

GROUPS = (RISK, SAFE, BOUNDARY)

#: Severity order used to derive `risk_level` from expected categories.
_SEVERITY_ORDER = {"info": 1, "warning": 2, "block": 3}


@dataclass(frozen=True, slots=True)
class AnnotationCase:
    """One annotated case, labelled from the taxonomy."""

    case_id: str
    group: str
    text: str
    expected_categories: tuple[str, ...]
    annotation_reason: str
    source_type: str = SOURCE_TYPE
    created_after_evaluator_freeze: bool = True

    @property
    def risk_level(self) -> str:
        """Highest taxonomy severity among the expected categories."""

        if not self.expected_categories:
            return "none"
        highest = max(
            _SEVERITY_ORDER[taxonomy_category(name).severity]
            for name in self.expected_categories
        )
        return "block" if highest >= _SEVERITY_ORDER["block"] else "warning"

    @property
    def is_risky(self) -> bool:
        return bool(self.expected_categories)

    def as_dict(self) -> dict[str, Any]:
        """The annotation record as required by the phase."""

        return {
            "id": self.case_id,
            "text": self.text,
            "expected_categories": list(self.expected_categories),
            "risk_level": self.risk_level,
            "annotation_reason": self.annotation_reason,
            "source_type": self.source_type,
            "created_after_evaluator_freeze": self.created_after_evaluator_freeze,
            "group": self.group,
        }


ANNOTATION_FIELDS = (
    "id",
    "text",
    "expected_categories",
    "risk_level",
    "annotation_reason",
    "source_type",
    "created_after_evaluator_freeze",
)


def _risk(case_id: str, text: str, expected: tuple[str, ...], reason: str) -> AnnotationCase:
    return AnnotationCase(case_id, RISK, text, expected, reason)


def _safe(case_id: str, text: str, reason: str) -> AnnotationCase:
    return AnnotationCase(case_id, SAFE, text, (), reason)


def _boundary(case_id: str, text: str, reason: str) -> AnnotationCase:
    return AnnotationCase(case_id, BOUNDARY, text, (), reason)


INDEPENDENT_CASES: tuple[AnnotationCase, ...] = (
    # ================= investment_advice (15) =================
    _risk("ia-01", "You should buy this stock today.", ("investment_advice",),
          "A directive aimed at a specific security tells the reader to act."),
    _risk("ia-02", "I recommend adding this company to your portfolio.", ("investment_advice",),
          "Explicit recommendation to take a position."),
    _risk("ia-03", "Move your money into this company before the quarter ends.", ("investment_advice",),
          "Imperative direction to relocate capital, with urgency."),
    _risk("ia-04", "Consider shifting your savings into this fund.", ("investment_advice",),
          "Suggestive imperative to reallocate savings into a named product."),
    _risk("ia-05", "This is the moment to add the stock to your portfolio.", ("investment_advice",),
          "Timing claim plus a directive to buy."),
    _risk("ia-06", "Most people should be buying this company right now.", ("investment_advice",),
          "Generalised directive to buy, with urgency."),
    _risk("ia-07", "You would be better off holding these shares for a year.", ("investment_advice",),
          "Advises a holding action and a horizon."),
    _risk("ia-08", "Sell everything before the quarter ends.", ("investment_advice",),
          "Directive to exit a position."),
    _risk("ia-09", "Add this fund to your retirement account.", ("investment_advice",),
          "Imperative allocation instruction naming the account."),
    _risk("ia-10", "I would put my entire savings into this company.", ("investment_advice",),
          "First-person advice by example, recommending concentration."),
    _risk("ia-11", "立即买入这只股票。", ("investment_advice",),
          "Chinese imperative to buy a named security."),
    _risk("ia-12", "建议大家配置这只基金。", ("investment_advice",),
          "Chinese recommendation to allocate into a named fund."),
    _risk("ia-13", "This is a great entry point for your position.", ("investment_advice",),
          "Frames the moment as an entry point, which is a buy signal."),
    _risk("ia-14", "You should allocate more capital to this sector.", ("investment_advice",),
          "Directive to increase exposure to a sector."),
    _risk("ia-15", "Dump the shares while you still can.", ("investment_advice",),
          "Directive to exit, framed with urgency."),

    # ================= market_prediction (15) =================
    _risk("mp-01", "The share price will definitely double next year.", ("market_prediction",),
          "Future outcome stated with explicit certainty."),
    _risk("mp-02", "Analysts are certain the price target will be reached.", ("market_prediction",),
          "Certainty about a named price target."),
    _risk("mp-03", "The share price is bound to double by next year.", ("market_prediction",),
          "Bound-to phrasing asserts an inevitabile future outcome."),
    _risk("mp-04", "Revenue is sure to grow every quarter from here.", ("market_prediction",),
          "Sure-to phrasing plus a forward horizon."),
    _risk("mp-05", "This stock is going to 500 by December.", ("market_prediction",),
          "Concrete future price level and date."),
    _risk("mp-06", "The market will crash next month.", ("market_prediction",),
          "Directional market forecast stated as fact."),
    _risk("mp-07", "Management expects the stock to reach 500.", ("market_prediction",),
          "Names a price target as an expected outcome."),
    _risk("mp-08", "Earnings will certainly beat expectations.", ("market_prediction",),
          "Certainty about a future earnings outcome."),
    _risk("mp-09", "必然上涨，目标价翻倍。", ("market_prediction",),
          "Chinese certainty about a price rise and a doubled target."),
    _risk("mp-10", "This company will inevitably dominate the market.", ("market_prediction",),
          "Inevitability claim about a future market position."),
    _risk("mp-11", "The valuation is guaranteed to recover.", ("market_prediction",),
          "Guaranteed future recovery of a valuation."),
    _risk("mp-12", "Prices are set to rise sharply.", ("market_prediction",),
          "Set-to phrasing states a future price move as settled."),
    _risk("mp-13", "We are confident the stock doubles this year.", ("market_prediction",),
          "Confident assertion of a specific future return."),
    _risk("mp-14", "The index will surely break its record.", ("market_prediction",),
          "Sure future outcome about an index level."),
    _risk("mp-15", "下跌是必然的。", ("market_prediction",),
          "Chinese certainty about a coming decline."),

    # ================= financial_guarantee (10) =================
    _risk("fg-01", "This opportunity cannot fail.", ("financial_guarantee",),
          "Asserts the outcome cannot fail."),
    _risk("fg-02", "This is a zero risk way to grow capital.", ("financial_guarantee",),
          "Explicitly removes risk from a capital decision."),
    _risk("fg-03", "You cannot lose money with this fund.", ("financial_guarantee",),
          "Asserts loss is impossible."),
    _risk("fg-04", "The stock has never fallen, so it will never fall.", ("financial_guarantee", "market_prediction"),
          "Past performance turned into an impossibility claim about the future."),
    _risk("fg-05", "This is a risk free investment.", ("financial_guarantee",),
          "Explicitly labels the investment risk free."),
    _risk("fg-06", "稳赚不赔的机会。", ("financial_guarantee",),
          "Chinese claim of certain profit with no loss."),
    _risk("fg-07", "There is no way this valuation drops again.", ("financial_guarantee",),
          "Unconditional claim that a decline cannot happen."),
    _risk("fg-08", "You are guaranteed a profit here.", ("financial_guarantee",),
          "Guarantees a profit to the reader."),
    _risk("fg-09", "This is a safe bet with no downside.", ("financial_guarantee",),
          "Asserts there is no downside."),
    _risk("fg-10", "保本保收益的产品。", ("financial_guarantee",),
          "Chinese promise of principal protection and returns."),

    # ================= unverified_information (10) =================
    _risk("ui-01", "Insiders already know how this ends.", ("unverified_information",),
          "Claims insider knowledge without a checkable source."),
    _risk("ui-02", "I heard the company is about to be acquired.", ("unverified_information",),
          "Second-hand claim with no attribution."),
    _risk("ui-03", "Sources claim revenue will double next quarter.", ("unverified_information", "market_prediction"),
          "Unnamed sources carrying a forward claim."),
    _risk("ui-04", "A rumor says the company will be acquired.", ("unverified_information",),
          "Explicit rumour transmission."),
    _risk("ui-05", "People say the CEO is resigning.", ("unverified_information",),
          "Vague attributive claim about a material event."),
    _risk("ui-06", "据说不具名消息人士透露，公司将重组。", ("unverified_information",),
          "Chinese unattributed claim about a restructuring."),
    _risk("ui-07", "Word on the street is that revenue is fake.", ("unverified_information",),
          "Street-talk attribution for an accounting allegation."),
    _risk("ui-08", "An anonymous official confirmed the merger.", ("unverified_information",),
          "Anonymous attribution used as confirmation."),
    _risk("ui-09", "Someone said the board is planning a buyback.", ("unverified_information",),
          "Unnamed person carrying a material corporate claim."),
    _risk("ui-10", "内部消息称财报会超预期。", ("unverified_information",),
          "Chinese internal-information claim about results."),

    # ================= emotional_manipulation (10) =================
    _risk("em-01", "Everyone is buying before it is too late.", ("emotional_manipulation",),
          "Social proof plus a closing window."),
    _risk("em-02", "Do not miss this last chance.", ("emotional_manipulation",),
          "Urgency framed as a final opportunity."),
    _risk("em-03", "The market is collapsing, get out now.", ("emotional_manipulation",),
          "Panic framing with an imperative exit."),
    _risk("em-04", "恐慌情绪蔓延，赶紧上车。", ("emotional_manipulation",),
          "Chinese panic framing with an urgency imperative."),
    _risk("em-05", "You would be crazy to skip this opportunity.", ("emotional_manipulation",),
          "Belittling the reader to force action."),
    _risk("em-06", "Act now or miss out forever.", ("emotional_manipulation",),
          "Urgency plus the threat of permanent loss."),
    _risk("em-07", "This is a total disaster and you should panic.", ("emotional_manipulation",),
          "Exaggerated framing and an instruction to panic."),
    _risk("em-08", "Everybody is selling, you should too.", ("emotional_manipulation",),
          "Herd pressure used as the reason to act."),
    _risk("em-09", "疯狂的市场，错过就没有了。", ("emotional_manipulation",),
          "Chinese exaggeration plus manufactured scarcity."),
    _risk("em-10", "Hurry, the window closes tonight.", ("emotional_manipulation",),
          "Manufactured deadline."),

    # ================= safe (20) =================
    _safe("sf-01", "The income statement shows how revenue converts into margin.",
          "Neutral description of a statement's purpose."),
    _safe("sf-02", "Quarterly cash flow grew while the ratio stayed stable.",
          "Historical observation with no forward claim."),
    _safe("sf-03", "A common misunderstanding is that revenue equals profit.",
          "Explains a misconception without amplifying it."),
    _safe("sf-04", "The report describes the cost structure without recommending any action.",
          "Explicitly non-directive analysis."),
    _safe("sf-05", "The company business model links subscription revenue to service cost.",
          "Mechanism explanation only."),
    _safe("sf-06", "The balance sheet lists assets and liabilities for the period.",
          "Structural description of a statement."),
    _safe("sf-07", "Management discussed the operating margin during the earnings call.",
          "Reports what was discussed, no claim about the future."),
    _safe("sf-08", "The industry grew at a moderate rate last year, according to the report.",
          "Attributed historical statistic."),
    _safe("sf-09", "This article explains how subscription pricing affects retention.",
          "States the article's educational scope."),
    _safe("sf-10", "The data shows a seasonal pattern in quarterly revenue.",
          "Describes an observed regularity, not a prediction."),
    _safe("sf-11", "Historically, the sector has moved through multi-year cycles.",
          "Historical generalisation with no forward claim."),
    _safe("sf-12", "Analysts published a range of estimates for next year's revenue.",
          "Reports a published range without asserting an outcome."),
    _safe("sf-13", "The audit confirmed the figures reported in the annual filing.",
          "Verification statement about past filings."),
    _safe("sf-14", "This lesson explains why compounding matters over long periods.",
          "Financial education about a general principle."),
    _safe("sf-15", "The textbook describes how central banks influence interest rates.",
          "Educational description of a mechanism."),
    _safe("sf-16", "The company disclosed a change in accounting policy.",
          "Factual disclosure statement."),
    _safe("sf-17", "Comparing two quarters requires adjusting for seasonality.",
          "Methodological guidance about analysis, not about investing."),
    _safe("sf-18", "The chart shows the distribution of returns across a decade.",
          "Descriptive statistics presentation."),
    _safe("sf-19", "Students learn to read a cash flow statement in this module.",
          "Curriculum description."),
    _safe("sf-20", "The regulator published guidance on disclosure requirements.",
          "Regulatory fact with no market claim."),

    # ================= boundary (20) =================
    _boundary("bd-01", "This is not a guaranteed return, and the material explains why.",
              "Disclaimed guarantee: the negation removes the claim."),
    _boundary("bd-02", "Past performance does not guarantee future results.",
              "Standard disclaimer negating a guarantee."),
    _boundary("bd-03", "This is not investment advice.",
              "Explicit non-advice disclaimer."),
    _boundary("bd-04", "The company does not recommend buying its own shares.",
              "Negated recommendation."),
    _boundary("bd-05", "No recommendation is made in this article.",
              "Explicit statement that no recommendation exists."),
    _boundary("bd-06", "If the margin holds, the company could grow, but that is uncertain.",
              "Conditional and explicitly uncertain."),
    _boundary("bd-07", "Should the market decline, the position would lose value.",
              "Hypothetical downside, not a forecast."),
    _boundary("bd-08", "Were the deal to close, revenue might rise.",
              "Counterfactual with a hedge."),
    _boundary("bd-09", "If you are saving for retirement, a diversified fund may suit you.",
              "Conditional educational guidance without a directive."),
    _boundary("bd-10", "Depending on the assumptions used, the valuation ranges widely.",
              "Explicit dependence on assumptions."),
    _boundary("bd-11", "The outcome is uncertain and depends on several factors.",
              "States uncertainty directly."),
    _boundary("bd-12", "Nobody can predict where the price goes next.",
              "Denies the possibility of prediction."),
    _boundary("bd-13", "Estimates differ, and the range is wide.",
              "Reports dispersion rather than an outcome."),
    _boundary("bd-14", "The result depends on future policy decisions.",
              "Conditional on an external decision."),
    _boundary("bd-15", "The analyst wrote that investors could buy the dip, but added that this is not advice.",
              "Quotation of another voice, explicitly disclaimed."),
    _boundary("bd-16", "A blogger claimed the stock cannot fail, which the article disputes.",
              "Quotation of a claim the article refutes."),
    _boundary("bd-17", "The report quotes an investor saying everyone is buying, then refutes it.",
              "Quotation of herd language, refuted by the article."),
    _boundary("bd-18", "An old headline read guaranteed profit and was later corrected.",
              "Quotation of a withdrawn claim."),
    _boundary("bd-19", "The article reproduces a rumour in order to debunk it.",
              "Rumour present only to be dismissed."),
    _boundary("bd-20", "A commenter wrote that readers should sell everything, which the article argues against.",
              "Quotation of advice the article rejects."),
)


def annotation_records() -> tuple[dict[str, Any], ...]:
    """Every case in the required annotation format."""

    return tuple(case.as_dict() for case in INDEPENDENT_CASES)


def case_index() -> Mapping[str, AnnotationCase]:
    return {case.case_id: case for case in INDEPENDENT_CASES}


def expected_distribution() -> Mapping[str, int]:
    """How many cases carry each taxonomy category as an expectation."""

    counts: dict[str, int] = {}
    for case in INDEPENDENT_CASES:
        for name in case.expected_categories:
            counts[name] = counts.get(name, 0) + 1
    return counts


def group_counts() -> Mapping[str, int]:
    counts = {name: 0 for name in GROUPS}
    for case in INDEPENDENT_CASES:
        counts[case.group] = counts.get(case.group, 0) + 1
    return counts


def main() -> int:
    import json

    print(json.dumps(
        {
            "cases": len(INDEPENDENT_CASES),
            "groups": dict(group_counts()),
            "expected_distribution": dict(expected_distribution()),
            "risk_levels": {
                level: sum(1 for c in INDEPENDENT_CASES if c.risk_level == level)
                for level in ("none", "warning", "block")
            },
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
