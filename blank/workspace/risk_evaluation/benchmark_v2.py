"""Benchmark `semantic/v3` — labelled under the v2 annotation guide.

Authored from `docs/RISK_ANNOTATION_GUIDE_v2.md`, not from evaluator output.
Each case carries the two orthogonal v2 fields beside its labels, so the
attribution and certainty reasoning behind every label is inspectable rather
than implied.

Composition (120 cases):

    risk      70   investment_advice 18, market_prediction 14,
                   financial_guarantee 10, unverified_information 18,
                   emotional_manipulation 10
    safe      25   attributed expectation 6, conditional scenario 8,
                   named-source attribution 4, general 7
    boundary  25   conditional 12, quotation 6, attributed 4, disclaimer 3

Focus tags, which cut across the groups:

    market_boundary  22   explicit prediction vs expectation vs scenario
    attribution      26   who is speaking
    conditional      20   what the claim depends on
    general          52

Like v1 and v2, this benchmark was authored by the evaluator's author, so
shared vocabulary remains a source of correlated bias. The two new fields at
least make the labelling rule explicit enough to be checked by a second
annotator, which the earlier versions did not allow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .taxonomy_v2 import CERTAINTY_LEVELS, STATEMENT_SOURCES, TAXONOMY_VERSION


ANNOTATION_VERSION = "2.0.0"
SOURCE_TYPE = "synthetic"

RISK = "risk"
SAFE = "safe"
BOUNDARY = "boundary"
GROUPS = (RISK, SAFE, BOUNDARY)

ATTRIBUTION = "attribution"
CONDITIONAL = "conditional"
MARKET_BOUNDARY = "market_boundary"
GENERAL = "general"
FOCUSES = (ATTRIBUTION, CONDITIONAL, MARKET_BOUNDARY, GENERAL)

V3_ANNOTATION_FIELDS = (
    "id",
    "text",
    "expected_categories",
    "statement_source",
    "certainty_level",
    "annotation_reason",
    "annotation_version",
)

_SEVERITY_ORDER = {"info": 1, "warning": 2, "block": 3}


@dataclass(frozen=True, slots=True)
class AnnotationCaseV2:
    case_id: str
    group: str
    focus: str
    text: str
    expected_categories: tuple[str, ...]
    statement_source: str
    certainty_level: str
    annotation_reason: str
    annotation_version: str = ANNOTATION_VERSION
    source_type: str = SOURCE_TYPE
    created_after_evaluator_freeze: bool = True

    def __post_init__(self) -> None:
        if self.statement_source not in STATEMENT_SOURCES:
            raise ValueError(
                f"{self.case_id}: unknown statement_source {self.statement_source!r}"
            )
        if self.certainty_level not in CERTAINTY_LEVELS:
            raise ValueError(
                f"{self.case_id}: unknown certainty_level {self.certainty_level!r}"
            )
        if self.group not in GROUPS:
            raise ValueError(f"{self.case_id}: unknown group {self.group!r}")
        if self.focus not in FOCUSES:
            raise ValueError(f"{self.case_id}: unknown focus {self.focus!r}")

    @property
    def risk_level(self) -> str:
        from .taxonomy import category as taxonomy_category

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
        """The v3 annotation record, including the fields the registry needs."""

        return {
            "id": self.case_id,
            "text": self.text,
            "expected_categories": list(self.expected_categories),
            "statement_source": self.statement_source,
            "certainty_level": self.certainty_level,
            "annotation_reason": self.annotation_reason,
            "annotation_version": self.annotation_version,
            "risk_level": self.risk_level,
            "group": self.group,
            "focus": self.focus,
            "source_type": self.source_type,
            "created_after_evaluator_freeze": self.created_after_evaluator_freeze,
        }


def _r(
    case_id: str,
    focus: str,
    text: str,
    expected: tuple[str, ...],
    source: str,
    certainty: str,
    reason: str,
) -> AnnotationCaseV2:
    return AnnotationCaseV2(
        case_id, RISK, focus, text, expected, source, certainty, reason
    )


def _s(
    case_id: str,
    focus: str,
    text: str,
    source: str,
    certainty: str,
    reason: str,
) -> AnnotationCaseV2:
    return AnnotationCaseV2(case_id, SAFE, focus, text, (), source, certainty, reason)


def _b(
    case_id: str,
    focus: str,
    text: str,
    source: str,
    certainty: str,
    reason: str,
) -> AnnotationCaseV2:
    return AnnotationCaseV2(case_id, BOUNDARY, focus, text, (), source, certainty, reason)


V3_CASES: tuple[AnnotationCaseV2, ...] = (
    # ================= investment_advice (18) =================
    _r("ia-01", GENERAL, "You should buy this stock today.", ("investment_advice",),
       "author", "certain", "Author-voice directive aimed at a security."),
    _r("ia-02", GENERAL, "I recommend adding this company to your portfolio.", ("investment_advice",),
       "author", "certain", "Explicit author recommendation to take a position."),
    _r("ia-03", GENERAL, "Move your money into this company before the quarter ends.", ("investment_advice",),
       "author", "certain", "Directive to relocate capital, with a deadline."),
    _r("ia-04", GENERAL, "Consider shifting your savings into this fund.", ("investment_advice",),
       "author", "certain", "Suggestive imperative naming a product."),
    _r("ia-05", GENERAL, "This is the moment to add the stock to your portfolio.", ("investment_advice",),
       "author", "certain", "Timing claim plus a directive to buy."),
    _r("ia-06", GENERAL, "Most people should be buying this company right now.", ("investment_advice",),
       "author", "certain", "Generalised author-voice directive to buy."),
    _r("ia-07", GENERAL, "You would be better off holding these shares for a year.", ("investment_advice",),
       "author", "certain", "Advises a holding action and a horizon."),
    _r("ia-08", GENERAL, "Sell everything before the quarter ends.", ("investment_advice",),
       "author", "certain", "Directive to exit, unconditioned."),
    _r("ia-09", GENERAL, "Add this fund to your retirement account.", ("investment_advice",),
       "author", "certain", "Imperative allocation instruction."),
    _r("ia-10", GENERAL, "I would put my entire savings into this company.", ("investment_advice",),
       "author", "certain", "Advice by example recommending concentration."),
    _r("ia-11", GENERAL, "立即买入这只股票。", ("investment_advice",),
       "author", "certain", "Chinese author-voice imperative to buy."),
    _r("ia-12", GENERAL, "建议大家配置这只基金。", ("investment_advice",),
       "author", "certain", "Chinese author-voice allocation recommendation."),
    _r("ia-13", GENERAL, "This is a great entry point for your position.", ("investment_advice",),
       "author", "certain", "Frames the moment as a buy signal without a directive verb."),
    _r("ia-14", GENERAL, "You should allocate more capital to this sector.", ("investment_advice",),
       "author", "certain", "Directive to increase exposure."),
    _r("ia-15", GENERAL, "Dump the shares while you still can.", ("investment_advice",),
       "author", "certain", "Directive to exit, framed with urgency."),
    _r("ia-16", GENERAL, "Buy the dip and hold for the long term.", ("investment_advice",),
       "author", "certain", "Directive to buy and hold."),
    _r("ia-17", GENERAL, "Allocate a third of your capital to this sector.", ("investment_advice",),
       "author", "certain", "Directive with a specific allocation."),
    _r("ia-18", GENERAL, "Cut your position before earnings.", ("investment_advice",),
       "author", "certain", "Directive to reduce a position."),

    # ================= market_prediction (14) =================
    _r("mp-01", MARKET_BOUNDARY, "The share price will definitely double next year.", ("market_prediction",),
       "author", "certain", "Explicit prediction: author voice, certain."),
    _r("mp-02", MARKET_BOUNDARY, "The share price is bound to double by next year.", ("market_prediction",),
       "author", "certain", "Author-voice certainty about a future price."),
    _r("mp-03", MARKET_BOUNDARY, "Revenue is sure to grow every quarter from here.", ("market_prediction",),
       "author", "certain", "Author-voice certainty about future revenue."),
    _r("mp-04", MARKET_BOUNDARY, "This stock is going to 500 by December.", ("market_prediction",),
       "author", "certain", "Level and date stated as fact."),
    _r("mp-05", MARKET_BOUNDARY, "The market will crash next month.", ("market_prediction",),
       "author", "certain",
       "Explicit prediction. 'Crash' is dramatic vocabulary, not reader pressure, "
       "so emotional_manipulation does not apply under guide v2 section 6.1."),
    _r("mp-06", MARKET_BOUNDARY, "必然上涨，目标价翻倍。", ("market_prediction",),
       "author", "certain", "Chinese author-voice certainty about a price rise."),
    _r("mp-07", MARKET_BOUNDARY, "This company will inevitably dominate the market.", ("market_prediction",),
       "author", "certain", "Inevitability claim in the author's voice."),
    _r("mp-08", MARKET_BOUNDARY, "The valuation is guaranteed to recover.", ("market_prediction",),
       "author", "certain", "Certainty about a future recovery."),
    _r("mp-09", MARKET_BOUNDARY, "Prices are set to rise sharply.", ("market_prediction",),
       "author", "certain", "'Set to' states a future move as settled."),
    _r("mp-10", MARKET_BOUNDARY, "The index will surely break its record.", ("market_prediction",),
       "author", "certain", "Author-voice certainty about an index level."),
    _r("mp-11", MARKET_BOUNDARY, "下跌是必然的。", ("market_prediction",),
       "author", "certain", "Chinese certainty about a coming decline."),
    _r("mp-12", MARKET_BOUNDARY, "Earnings will certainly beat expectations.", ("market_prediction",),
       "author", "certain", "Certainty about a future earnings outcome."),
    _r("mp-13", GENERAL, "The dividend will be raised again next year.", ("market_prediction",),
       "author", "certain", "Author-voice certainty about a future corporate action."),
    _r("mp-14", GENERAL, "The share count will shrink after the buyback.", ("market_prediction",),
       "author", "certain", "Author-voice certainty about a future capital change."),

    # ================= financial_guarantee (10) =================
    _r("fg-01", GENERAL, "This opportunity cannot fail.", ("financial_guarantee",),
       "author", "certain", "Author-voice assertion that failure is impossible."),
    _r("fg-02", GENERAL, "This is a zero risk way to grow capital.", ("financial_guarantee",),
       "author", "certain", "Explicitly removes risk from a capital decision."),
    _r("fg-03", GENERAL, "You cannot lose money with this fund.", ("financial_guarantee",),
       "author", "certain", "Asserts loss is impossible."),
    _r("fg-04", GENERAL, "The stock has never fallen, so it will never fall.",
       ("financial_guarantee", "market_prediction"),
       "author", "certain",
       "Past performance turned into an impossibility claim and a future certainty."),
    _r("fg-05", GENERAL, "This is a risk free investment.", ("financial_guarantee",),
       "author", "certain", "Labels the investment risk free."),
    _r("fg-06", GENERAL, "稳赚不赔的机会。", ("financial_guarantee",),
       "author", "certain", "Chinese claim of certain profit with no loss."),
    _r("fg-07", GENERAL, "There is no way this valuation drops again.", ("financial_guarantee",),
       "author", "certain", "Unconditional claim that a decline cannot happen."),
    _r("fg-08", GENERAL, "You are guaranteed a profit here.", ("financial_guarantee",),
       "author", "certain", "Guarantees a profit to the reader."),
    _r("fg-09", GENERAL, "This is a safe bet with no downside.", ("financial_guarantee",),
       "author", "certain", "Asserts there is no downside."),
    _r("fg-10", GENERAL, "保本保收益的产品。", ("financial_guarantee",),
       "author", "certain", "Chinese promise of principal protection and returns."),

    # ================= unverified_information (18) =================
    _r("ui-01", ATTRIBUTION, "Insiders already know how this ends.", ("unverified_information",),
       "unknown", "certain", "Unattributable insider knowledge carrying a claim."),
    _r("ui-02", ATTRIBUTION, "I heard the company is about to be acquired.", ("unverified_information",),
       "unknown", "certain", "Second-hand claim with no named source."),
    _r("ui-03", ATTRIBUTION, "Sources claim revenue will double next quarter.", ("unverified_information",),
       "unknown", "certain",
       "Unattributable source carries the claim, so the prediction is not the "
       "author's; only the unverifiable attribution is a risk."),
    _r("ui-04", ATTRIBUTION, "A rumor says the company will be acquired.", ("unverified_information",),
       "unknown", "certain", "Explicit rumour transmission."),
    _r("ui-05", ATTRIBUTION, "People say the CEO is resigning.", ("unverified_information",),
       "unknown", "certain", "Vague attribution about a material event."),
    _r("ui-06", ATTRIBUTION, "据说不具名消息人士透露，公司将重组。", ("unverified_information",),
       "unknown", "certain", "Chinese unattributed claim about a restructuring."),
    _r("ui-07", ATTRIBUTION, "Word on the street is that revenue is fake.", ("unverified_information",),
       "unknown", "certain", "Street-talk attribution for an accounting allegation."),
    _r("ui-08", ATTRIBUTION, "An anonymous official confirmed the merger.", ("unverified_information",),
       "unknown", "certain", "Anonymous attribution used as confirmation."),
    _r("ui-09", ATTRIBUTION, "Someone said the board is planning a buyback.", ("unverified_information",),
       "unknown", "certain", "Unnamed person carrying a corporate claim."),
    _r("ui-10", ATTRIBUTION, "内部消息称财报会超预期。", ("unverified_information",),
       "unknown", "certain", "Chinese internal-information claim."),
    _r("ui-11", ATTRIBUTION, "They say the dividend is about to be cut.", ("unverified_information",),
       "unknown", "certain", "Unattributable 'they' carrying a claim."),
    _r("ui-12", ATTRIBUTION, "I was told the factory is closing.", ("unverified_information",),
       "unknown", "certain", "Passive second-hand attribution."),
    _r("ui-13", ATTRIBUTION, "Rumours are circulating about a restatement.", ("unverified_information",),
       "unknown", "certain", "Rumour circulating without a source."),
    _r("ui-14", ATTRIBUTION, "网上传该公司即将退市。", ("unverified_information",),
       "unknown", "certain", "Chinese online rumour about delisting."),
    _r("ui-15", ATTRIBUTION, "A source close to the deal mentioned a delay.", ("unverified_information",),
       "unknown", "certain", "Vague proximity replaces a name."),
    _r("ui-16", ATTRIBUTION, "Everybody says the founder is leaving.", ("unverified_information",),
       "unknown", "certain", "Collective but unattributable claim."),
    _r("ui-17", GENERAL, "Leaked internal documents suggest a restatement.", ("unverified_information",),
       "unknown", "certain", "Leaked material with no verifiable origin."),
    _r("ui-18", GENERAL, "An unnamed banker says the deal is off.", ("unverified_information",),
       "unknown", "certain", "Unnamed source carrying a material claim."),

    # ================= emotional_manipulation (10) =================
    _r("em-01", GENERAL, "Everyone is buying before it is too late.", ("emotional_manipulation",),
       "author", "certain", "Herd framing plus a deadline."),
    _r("em-02", GENERAL, "Do not miss this last chance.", ("emotional_manipulation",),
       "author", "certain", "Urgency framed as a final opportunity."),
    _r("em-03", GENERAL, "The market will collapse, get out now.",
       ("market_prediction", "emotional_manipulation"),
       "author", "certain",
       "A market claim plus a reader-directed imperative, so both apply."),
    _r("em-04", GENERAL, "恐慌情绪蔓延，赶紧上车。", ("emotional_manipulation",),
       "author", "certain", "Chinese panic framing with an urgency imperative."),
    _r("em-05", GENERAL, "You would be crazy to skip this opportunity.", ("emotional_manipulation",),
       "author", "certain", "Belittling the reader for inaction."),
    _r("em-06", GENERAL, "Act now or miss out forever.", ("emotional_manipulation",),
       "author", "certain", "Urgency plus permanent-loss framing."),
    _r("em-07", GENERAL, "This is a total disaster and you should panic.", ("emotional_manipulation",),
       "author", "certain", "Exaggeration and an instruction to panic."),
    _r("em-08", GENERAL, "Everybody is selling, you should too.", ("emotional_manipulation",),
       "author", "certain", "Herd pressure as the reason to act."),
    _r("em-09", GENERAL, "疯狂的市场，错过就没有了。", ("emotional_manipulation",),
       "author", "certain", "Chinese exaggeration plus manufactured scarcity."),
    _r("em-10", GENERAL, "Hurry, the window closes tonight.", ("emotional_manipulation",),
       "author", "certain", "Manufactured deadline."),

    # ================= safe: attributed expectation (6) =================
    _s("ae-01", MARKET_BOUNDARY, "Management expects the stock to reach 500.",
       "third_party", "probable",
       "Guide v2 section 2: an attributed expectation is a report, not a prediction."),
    _s("ae-02", MARKET_BOUNDARY, "Analysts are certain the price target will be reached.",
       "third_party", "certain",
       "The certainty belongs to the analysts; the article reports it."),
    _s("ae-03", MARKET_BOUNDARY, "The board expects revenue to grow next year.",
       "third_party", "probable", "Attributed expectation with a named party."),
    _s("ae-04", MARKET_BOUNDARY, "Economists forecast a rate cut in the spring.",
       "third_party", "probable", "Reported forecast, not an author-voice prediction."),
    _s("ae-05", MARKET_BOUNDARY, "The broker note projects a higher valuation.",
       "third_party", "probable", "Attributed projection."),
    _s("ae-06", MARKET_BOUNDARY, "Analysts published a range of estimates for next year's revenue.",
       "third_party", "possible", "Reported estimates; no single outcome asserted."),

    # ================= safe: conditional scenario (8) =================
    _s("cs-01", CONDITIONAL, "If the margin holds, the company could grow, but that is uncertain.",
       "author", "hypothetical", "Conditional and explicitly uncertain."),
    _s("cs-02", CONDITIONAL, "Should the market decline, the position would lose value.",
       "author", "hypothetical", "Inverted conditional stating a downside scenario."),
    _s("cs-03", CONDITIONAL, "Were the deal to close, revenue might rise.",
       "author", "hypothetical", "Counterfactual with a hedge."),
    _s("cs-04", CONDITIONAL, "Depending on the assumptions used, the valuation ranges widely.",
       "author", "hypothetical", "Explicit dependence on assumptions."),
    _s("cs-05", CONDITIONAL, "If rates fall, the stock may rise.",
       "author", "hypothetical", "The outcome is contingent, so it is not a prediction."),
    _s("cs-06", CONDITIONAL, "Assuming flat demand, margins would stay stable.",
       "author", "hypothetical", "Conditional projection."),
    _s("cs-07", CONDITIONAL, "In the event of a downgrade, the position would fall.",
       "author", "hypothetical", "Conditional downside scenario."),
    _s("cs-08", CONDITIONAL, "Provided that costs hold, the plan remains affordable.",
       "author", "hypothetical", "Conditional on a stated proviso."),

    # ================= safe: named-source attribution (4) =================
    _s("as-01", ATTRIBUTION, "The regulator published guidance on disclosure requirements.",
       "third_party", "certain", "Named, checkable source; nothing unverifiable."),
    _s("as-02", ATTRIBUTION, "The audit confirmed the figures reported in the annual filing.",
       "third_party", "certain", "Verification by a named body."),
    _s("as-03", ATTRIBUTION, "The company disclosed a change in accounting policy.",
       "third_party", "certain", "Named discloser of a factual change."),
    _s("as-04", ATTRIBUTION, "The exchange published the revised listing rules.",
       "third_party", "certain", "Named institution, checkable publication."),

    # ================= safe: general (7) =================
    _s("gs-01", GENERAL, "The income statement shows how revenue converts into margin.",
       "author", "certain", "Neutral description of a statement's purpose."),
    _s("gs-02", GENERAL, "Quarterly cash flow grew while the ratio stayed stable.",
       "author", "certain", "Historical observation, no forward claim."),
    _s("gs-03", GENERAL, "A common misunderstanding is that revenue equals profit.",
       "author", "certain", "Explains a misconception without amplifying it."),
    _s("gs-04", GENERAL, "The balance sheet lists assets and liabilities for the period.",
       "author", "certain", "Structural description."),
    _s("gs-05", GENERAL, "Historically, the sector has moved through multi-year cycles.",
       "author", "certain", "Historical generalisation, no forward claim."),
    _s("gs-06", GENERAL, "Students learn to read a cash flow statement in this module.",
       "author", "certain", "Curriculum description: education, not advice."),
    _s("gs-07", GENERAL, "The data shows a seasonal pattern in quarterly revenue.",
       "author", "certain", "Describes an observed regularity."),

    # ================= boundary: conditional (12) =================
    _b("bc-01", CONDITIONAL, "If the company misses guidance, the shares could fall.",
       "author", "hypothetical", "Conditional downside; nothing asserted unconditionally."),
    _b("bc-02", CONDITIONAL, "Were inflation to surprise, the valuation would compress.",
       "author", "hypothetical", "Counterfactual."),
    _b("bc-03", CONDITIONAL, "Should demand weaken, margins would narrow.",
       "author", "hypothetical", "Inverted conditional."),
    _b("bc-04", CONDITIONAL, "If the merger completes, the share count would change.",
       "author", "hypothetical", "Conditional corporate action."),
    _b("bc-05", CONDITIONAL, "Unless costs fall, the plan is not affordable.",
       "author", "hypothetical", "Conditional on a necessary precondition."),
    _b("bc-06", CONDITIONAL, "Assuming the refinancing succeeds, liquidity stays adequate.",
       "author", "hypothetical", "Conditional liquidity assessment."),
    _b("bc-07", CONDITIONAL, "If the regulator objects, the deal would lapse.",
       "author", "hypothetical", "Conditional regulatory outcome."),
    _b("bc-08", CONDITIONAL, "Were the currency to strengthen, export revenue would fall.",
       "author", "hypothetical", "Counterfactual with a mechanism."),
    _b("bc-09", CONDITIONAL, "Should the buyback continue, the float would shrink.",
       "author", "hypothetical", "Conditional capital effect."),
    _b("bc-10", CONDITIONAL, "In the event of a downgrade, borrowing costs would rise.",
       "author", "hypothetical", "Conditional cost effect."),
    _b("bc-11", CONDITIONAL, "If the pilot succeeds, the rollout may accelerate.",
       "author", "hypothetical", "Conditional plus a modal hedge."),
    _b("bc-12", CONDITIONAL, "Depending on the ruling, the provision could reverse.",
       "author", "hypothetical", "Conditional on an external decision."),

    # ================= boundary: quotation (6) =================
    _b("bq-01", ATTRIBUTION, "The report quotes an investor saying everyone is buying, then refutes it.",
       "quoted", "certain",
       "Guide v2 section 4: a quotation is not the article's claim."),
    _b("bq-02", ATTRIBUTION, "An old headline read guaranteed profit and was later corrected.",
       "quoted", "certain", "A withdrawn claim, quoted."),
    _b("bq-03", ATTRIBUTION, "A blogger claimed the stock cannot fail, which the article disputes.",
       "quoted", "certain", "A quoted claim the article refutes."),
    _b("bq-04", ATTRIBUTION, "A commenter wrote that readers should sell everything, which the article argues against.",
       "quoted", "certain", "Quoted advice the article rejects."),
    _b("bq-05", ATTRIBUTION, "The article reproduces a rumour in order to debunk it.",
       "quoted", "certain", "The rumour is the object of the sentence, not its claim."),
    _b("bq-06", ATTRIBUTION, "The newsletter said buy now, and the article explains why that was wrong.",
       "quoted", "certain", "Quoted directive the article rebuts."),

    # ================= boundary: attributed and disclaimed (4) =================
    _b("bd-01", MARKET_BOUNDARY, "The analyst wrote that investors could buy the dip, but added that this is not advice.",
       "quoted", "certain", "Quoted advice, explicitly disclaimed."),
    _b("bd-02", MARKET_BOUNDARY, "Management said the outlook is uncertain and offered no target.",
       "third_party", "possible", "Attributed uncertainty; no claim to act on."),
    _b("bd-03", MARKET_BOUNDARY, "The broker note says the stock is a buy, which the article does not endorse.",
       "third_party", "certain", "Reported recommendation without endorsement."),
    _b("bd-04", MARKET_BOUNDARY, "Analysts expect growth but caution that estimates often miss.",
       "third_party", "probable", "Attributed expectation with its own caveat."),

    # ================= boundary: disclaimer and uncertainty (3) =================
    _b("bp-01", GENERAL, "This is not a guaranteed return, and the material explains why.",
       "author", "certain", "Disclaimed guarantee: the negation removes the claim."),
    _b("bp-02", GENERAL, "Past performance does not guarantee future results.",
       "author", "certain", "Standard disclaimer negating a guarantee."),
    _b("bp-03", GENERAL, "The outcome is uncertain and depends on several factors.",
       "author", "possible",
       "Presents no outcome as more than possible; nothing is asserted to act on."),
)


def v3_records() -> tuple[dict[str, Any], ...]:
    return tuple(case.as_dict() for case in V3_CASES)


def decontaminated_v3_cases() -> tuple[AnnotationCaseV2, ...]:
    """v3 cases whose text does not appear in the evaluator development set.

    v3 was authored fresh in Phase 7.5 but still reused 32 familiar sentences
    from `risk_evaluation.benchmark`, and the Phase 7.4 auditor caught it. v3 is
    kept exactly as measured; this subset carries governance weight instead,
    following the same response Phase 7.4 applied to v1.
    """

    from .benchmark import BENCHMARK_CASES

    development = {case.text for case in BENCHMARK_CASES}
    return tuple(case for case in V3_CASES if case.text not in development)


def v4_records() -> tuple[dict[str, Any], ...]:
    return tuple(case.as_dict() for case in decontaminated_v3_cases())


def case_index() -> Mapping[str, AnnotationCaseV2]:
    return {case.case_id: case for case in V3_CASES}


def group_counts() -> Mapping[str, int]:
    counts = {name: 0 for name in GROUPS}
    for case in V3_CASES:
        counts[case.group] += 1
    return counts


def focus_counts() -> Mapping[str, int]:
    counts = {name: 0 for name in FOCUSES}
    for case in V3_CASES:
        counts[case.focus] += 1
    return counts


def category_counts() -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for case in V3_CASES:
        for name in case.expected_categories:
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def source_counts() -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for case in V3_CASES:
        counts[case.statement_source] = counts.get(case.statement_source, 0) + 1
    return dict(sorted(counts.items()))


def certainty_counts() -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for case in V3_CASES:
        counts[case.certainty_level] = counts.get(case.certainty_level, 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    import json

    print(json.dumps(
        {
            "taxonomy_version": TAXONOMY_VERSION,
            "annotation_version": ANNOTATION_VERSION,
            "cases": len(V3_CASES),
            "groups": dict(group_counts()),
            "focus": dict(focus_counts()),
            "categories": dict(category_counts()),
            "statement_source": dict(source_counts()),
            "certainty_level": dict(certainty_counts()),
        },
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
