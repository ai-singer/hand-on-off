"""Sixty composition cases for the unified pipeline, grouped by what is asked.

    AUTHOR_ENDORSED      15   the article's own risky claim
    THIRD_PARTY_QUOTED   15   a quoted third party's risky claim
    AUTHOR_REJECTION     10   a claim the article argues against
    NEUTRAL_EDUCATION    10   explanatory text with no claim
    AMBIGUOUS            10   conditional, negated or uncertain

The phase is explicit that labels come from the annotation guide and that
generating them from evaluator output is forbidden. Every case therefore carries
a `basis` string naming the guide section its label comes from, and a test
asserts that no case is labelled from a pipeline result.

This is a **new** benchmark, not a reuse of `semantic/adversarial/v1`,
`attribution_experiment/v1` or `intent_pattern/v1`. Some sentences necessarily
resemble earlier cases - `This return is guaranteed.` is the same defect
wherever it appears - but the labels were written from the guide, not copied,
and the composition is different: this set asks what the *whole pipeline* should
output, which no earlier set did.

Each case labels its claims as well as its categories, so attribution accuracy
and intent recall can be measured on the same cases as the decision metrics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ...taxonomy import RISK_TAXONOMY


BENCHMARK_NAME = "risk_evaluation_v3"
BENCHMARK_VERSION = "v1"

AUTHOR_ENDORSED = "author_endorsed"
THIRD_PARTY_QUOTED = "third_party_quoted"
AUTHOR_REJECTION = "author_rejection"
NEUTRAL_EDUCATION = "neutral_education"
AMBIGUOUS = "ambiguous"

GROUP_NAMES: Mapping[str, str] = {
    AUTHOR_ENDORSED: "author endorsed risk",
    THIRD_PARTY_QUOTED: "third party quoted risk",
    AUTHOR_REJECTION: "author rejection",
    NEUTRAL_EDUCATION: "neutral education",
    AMBIGUOUS: "ambiguous",
}

REQUIRED_GROUP_SIZES: Mapping[str, int] = {
    AUTHOR_ENDORSED: 15,
    THIRD_PARTY_QUOTED: 15,
    AUTHOR_REJECTION: 10,
    NEUTRAL_EDUCATION: 10,
    AMBIGUOUS: 10,
}

#: Which guide section each group's labels follow.
GROUP_BASIS: Mapping[str, str] = {
    AUTHOR_ENDORSED: (
        "guide v2 sections 3.1 and 7: an author-voice directive, prediction, "
        "guarantee, uncheckable claim or reader pressure is the category"
    ),
    THIRD_PARTY_QUOTED: (
        "guide v2 sections 3.1 and 7: a quoted third party's claim is not the "
        "article's, and an uncheckable source is unverified_information"
    ),
    AUTHOR_REJECTION: (
        "guide v2 sections 3.1 and 4: arguing against a claim is not making it"
    ),
    NEUTRAL_EDUCATION: "guide v2 section 7: explanation and method guidance are negative",
    AMBIGUOUS: (
        "guide v2 sections 2 and 5: a conditional or hedged claim asserts "
        "nothing unconditionally"
    ),
}


@dataclass(frozen=True, slots=True)
class ClaimLabel:
    """What the guide says about one claim in a case."""

    speaker: str
    stance: str
    relation: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "stance": self.stance,
            "relation": self.relation,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    case_id: str
    group: str
    text: str
    expected_categories: tuple[str, ...]
    claims: tuple[ClaimLabel, ...]
    basis: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.group not in GROUP_NAMES:
            raise ValueError(f"{self.case_id}: unknown group {self.group!r}")
        if not self.text.strip():
            raise ValueError(f"{self.case_id}: text must not be empty")
        if not self.claims:
            raise ValueError(f"{self.case_id}: at least one claim label is required")
        known = {entry.name for entry in RISK_TAXONOMY}
        for name in self.expected_categories:
            if name not in known:
                raise ValueError(f"{self.case_id}: unknown category {name!r}")
        for label in self.claims:
            if label.speaker not in ("author", "third_party", "unknown"):
                raise ValueError(f"{self.case_id}: bad speaker {label.speaker!r}")
            if label.stance not in ("endorsed", "quoted", "rejected", "uncertain"):
                raise ValueError(f"{self.case_id}: bad stance {label.stance!r}")

    @property
    def expects_risk(self) -> bool:
        return bool(self.expected_categories)

    @property
    def expected_relations(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(label.relation for label in self.claims if label.relation)
        )

    @property
    def expected_speakers(self) -> tuple[str, ...]:
        return tuple(label.speaker for label in self.claims)

    @property
    def expected_stances(self) -> tuple[str, ...]:
        return tuple(label.stance for label in self.claims)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "group": self.group,
            "group_name": GROUP_NAMES[self.group],
            "text": self.text,
            "expected_categories": list(self.expected_categories),
            "expects_risk": self.expects_risk,
            "claims": [label.as_dict() for label in self.claims],
            "expected_relations": list(self.expected_relations),
            "basis": self.basis or GROUP_BASIS[self.group],
            "note": self.note,
        }


def _case(
    case_id: str,
    group: str,
    text: str,
    categories: Sequence[str],
    claims: Sequence[ClaimLabel],
    note: str = "",
) -> BenchmarkCase:
    return BenchmarkCase(
        case_id, group, text, tuple(categories), tuple(claims), GROUP_BASIS[group], note
    )


def _one(speaker: str, stance: str, relation: str = "") -> tuple[ClaimLabel, ...]:
    return (ClaimLabel(speaker, stance, relation),)


BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    # -- author endorsed risk ---------------------------------------------
    _case("AE-01", AUTHOR_ENDORSED, "This fund cannot lose money.", ["financial_guarantee"], _one("unknown", "uncertain", "RISK_REMOVED"), "default voice, risk removed"),
    _case("AE-02", AUTHOR_ENDORSED, "This return is guaranteed.", ["financial_guarantee"], _one("unknown", "uncertain", "GUARANTEE"), "the Phase 8.1 blind spot"),
    _case("AE-03", AUTHOR_ENDORSED, "We guarantee this return.", ["financial_guarantee"], _one("unknown", "uncertain", "GUARANTEE"), "active guarantee"),
    _case("AE-04", AUTHOR_ENDORSED, "Your capital is guaranteed.", ["financial_guarantee"], _one("unknown", "uncertain", "GUARANTEE"), "copular guarantee"),
    _case("AE-05", AUTHOR_ENDORSED, "We believe this fund cannot lose money.", ["financial_guarantee"], _one("author", "endorsed", "RISK_REMOVED"), "author marker plus risk removal"),
    _case("AE-06", AUTHOR_ENDORSED, "Your capital is risk-free.", ["financial_guarantee"], _one("unknown", "uncertain", "RISK_REMOVED"), "risk-free"),
    _case("AE-07", AUTHOR_ENDORSED, "The share price will certainly double next year.", ["market_prediction"], _one("unknown", "uncertain", "PREDICTION"), "author-voice certainty"),
    _case("AE-08", AUTHOR_ENDORSED, "Revenue will surely grow every quarter.", ["market_prediction"], _one("unknown", "uncertain", "PREDICTION"), "author-voice certainty"),
    _case("AE-09", AUTHOR_ENDORSED, "You should buy this stock today.", ["investment_advice"], _one("unknown", "uncertain", "ADVICE"), "directive plus object"),
    _case("AE-10", AUTHOR_ENDORSED, "Shift your savings into this fund.", ["investment_advice"], _one("unknown", "uncertain", "ADVICE"), "imperative directive"),
    _case("AE-11", AUTHOR_ENDORSED, "Do not miss this opportunity.", ["emotional_manipulation"], _one("unknown", "uncertain"), "pressure on the reader"),
    _case("AE-12", AUTHOR_ENDORSED, "Everyone is buying and there is no time left.", ["emotional_manipulation"], _one("unknown", "uncertain"), "herd framing plus deadline"),
    _case("AE-13", AUTHOR_ENDORSED, "Sources say the company will be acquired.", ["unverified_information"], _one("third_party", "quoted"), "uncheckable source"),
    _case("AE-14", AUTHOR_ENDORSED, "Insiders say the dividend is about to be cut.", ["unverified_information"], _one("third_party", "quoted"), "uncheckable source"),
    _case("AE-15", AUTHOR_ENDORSED, "Rumour has it the merger is close.", ["unverified_information"], _one("unknown", "uncertain"), "unattributable source"),
    # -- third party quoted risk ------------------------------------------
    # Labels follow guide v2 section 7: `unverified_information` requires an
    # *uncheckable* source, and a named, checkable source is negative for it.
    # The TQ cases therefore split in two. An unnamed collective - "Analysts",
    # "Experts", "Economists", "Officials", "Commentators", "a broker",
    # "Sources" - cannot be checked, so it is unverified information. A definite
    # party or document - "the company", "the report", "the newsletter",
    # "Management", "the board", "the regulator" - can be, so nothing is
    # reported. Five of these labels are cases the pipeline gets wrong, which is
    # recorded rather than avoided: the sourcing lexicon covers analysts,
    # insiders, sources and rumour, and not the rest.
    _case("TQ-01", THIRD_PARTY_QUOTED, "Analysts say this fund cannot lose money.", ["unverified_information"], _one("third_party", "quoted", "RISK_REMOVED"), "case 2 of the decision policy; unnamed collective"),
    _case("TQ-02", THIRD_PARTY_QUOTED, "The company said the fund cannot lose money.", [], _one("third_party", "quoted", "RISK_REMOVED"), "case 2, named source so not unverified"),
    _case("TQ-03", THIRD_PARTY_QUOTED, "According to the report, the fund cannot lose money.", [], _one("third_party", "quoted", "RISK_REMOVED"), "case 2, checkable document"),
    _case("TQ-04", THIRD_PARTY_QUOTED, "A broker told clients the fund cannot lose money.", ["unverified_information"], _one("third_party", "quoted", "RISK_REMOVED"), "indefinite singular source is uncheckable"),
    _case("TQ-05", THIRD_PARTY_QUOTED, "Economists forecast the stock will certainly double.", ["unverified_information"], _one("third_party", "quoted", "PREDICTION"), "unnamed collective"),
    _case("TQ-06", THIRD_PARTY_QUOTED, "Officials said the fund cannot lose money.", ["unverified_information"], _one("third_party", "quoted", "RISK_REMOVED"), "unnamed collective"),
    _case("TQ-07", THIRD_PARTY_QUOTED, "Commentators said the market will certainly crash.", ["unverified_information"], _one("third_party", "quoted", "PREDICTION"), "unnamed collective"),
    _case("TQ-08", THIRD_PARTY_QUOTED, "The newsletter recommends buying this stock.", [], _one("third_party", "quoted", "ADVICE"), "definite publication is checkable"),
    _case("TQ-09", THIRD_PARTY_QUOTED, "Management expects the share price to double.", [], _one("third_party", "quoted", "PREDICTION"), "case 2, named source"),
    _case("TQ-10", THIRD_PARTY_QUOTED, "The board said returns are guaranteed.", [], _one("third_party", "quoted", "GUARANTEE"), "case 2, named source"),
    _case("TQ-11", THIRD_PARTY_QUOTED, "Analysts say you should buy this stock.", ["unverified_information"], _one("third_party", "quoted", "ADVICE"), "case 2, unnamed collective"),
    _case("TQ-12", THIRD_PARTY_QUOTED, "The report states the stock will certainly double.", [], _one("third_party", "quoted", "PREDICTION"), "case 2, checkable document"),
    _case("TQ-13", THIRD_PARTY_QUOTED, "Experts predict the fund cannot lose money.", ["unverified_information"], _one("third_party", "quoted", "RISK_REMOVED"), "unnamed collective"),
    _case("TQ-14", THIRD_PARTY_QUOTED, "The regulator said capital is guaranteed.", [], _one("third_party", "quoted", "GUARANTEE"), "case 2, named source"),
    _case("TQ-15", THIRD_PARTY_QUOTED, "Sources say the fund cannot lose money.", ["unverified_information"], _one("third_party", "quoted", "RISK_REMOVED"), "case 2, unnamed collective"),
    # -- author rejection --------------------------------------------------
    _case("AR-01", AUTHOR_REJECTION, "We disagree with the view that this fund cannot lose money.", [], _one("author", "rejected", "RISK_REMOVED"), "case 3 of the decision policy"),
    _case("AR-02", AUTHOR_REJECTION, "We disagree with the claim that the stock will certainly double.", [], _one("author", "rejected", "PREDICTION"), "case 3"),
    _case("AR-03", AUTHOR_REJECTION, "We doubt the fund cannot lose money.", [], _one("author", "rejected", "RISK_REMOVED"), "case 3"),
    # NOTE: AR-04's expected label was corrected after the first run. It read
    # `[]`, which contradicted Phase 8.3's C-04 - the *same sentence* - labelled
    # `["unverified_information"]`. Guide v2 section 7 makes unverified
    # information attribution-agnostic and section 3.1's author-voice rule is
    # about the author's own claims, not about whether a source can be checked,
    # so C-04 was right and this row was wrong. The correction lowers the v3
    # false-positive count by one, and it is disclosed for that reason.
    _case("AR-04", AUTHOR_REJECTION, "Analysts say the fund cannot lose money. However, we disagree.", ["unverified_information"], (ClaimLabel("third_party", "rejected", "RISK_REMOVED"), ClaimLabel("author", "rejected")), "case 3, rejection projected backwards; the sourcing risk survives"),
    _case("AR-05", AUTHOR_REJECTION, "Experts expect the stock to rise. We are not convinced.", [], (ClaimLabel("third_party", "rejected", "PREDICTION"), ClaimLabel("author", "rejected")), "case 3"),
    _case("AR-06", AUTHOR_REJECTION, "The marketing claims the fund cannot lose money. We do not endorse that.", [], (ClaimLabel("author", "rejected", "RISK_REMOVED"), ClaimLabel("author", "rejected")), "case 3, explicit non-endorsement"),
    _case("AR-07", AUTHOR_REJECTION, "This article rejects the idea that the fund cannot lose money.", [], _one("unknown", "uncertain", "RISK_REMOVED"), "case 3, self-reference not in the marker table"),
    _case("AR-08", AUTHOR_REJECTION, "The claim that the stock will certainly double is incorrect.", [], _one("unknown", "uncertain", "PREDICTION"), "case 3, rejection cue not in the table"),
    _case("AR-09", AUTHOR_REJECTION, "We are not convinced the fund cannot lose money.", [], _one("author", "rejected", "RISK_REMOVED"), "case 3, hedged rejection"),
    _case("AR-10", AUTHOR_REJECTION, "Do not miss this opportunity is what the advert says; we disagree.", [], _one("author", "rejected"), "case 3, quoted pressure rejected"),
    # -- neutral education -------------------------------------------------
    _case("NE-01", NEUTRAL_EDUCATION, "A price-to-earnings ratio compares price with earnings per share.", [], _one("unknown", "uncertain"), "definition"),
    _case("NE-02", NEUTRAL_EDUCATION, "Diversification spreads risk across assets.", [], _one("unknown", "uncertain"), "method guidance"),
    _case("NE-03", NEUTRAL_EDUCATION, "Compounding means returns are earned on earlier returns.", [], _one("unknown", "uncertain"), "definition mentioning returns"),
    _case("NE-04", NEUTRAL_EDUCATION, "Interest rate changes affect bond prices inversely.", [], _one("unknown", "uncertain"), "explanation"),
    _case("NE-05", NEUTRAL_EDUCATION, "The company reports its results in March.", [], _one("unknown", "uncertain"), "neutral statement"),
    _case("NE-06", NEUTRAL_EDUCATION, "The prospectus explains how charges are calculated.", [], _one("unknown", "uncertain"), "neutral statement"),
    _case("NE-07", NEUTRAL_EDUCATION, "The board meets on the second Tuesday of the month.", [], _one("third_party", "quoted"), "neutral statement with a party named"),
    _case("NE-08", NEUTRAL_EDUCATION, "The audit covers the twelve months to December.", [], _one("unknown", "uncertain"), "neutral statement"),
    _case("NE-09", NEUTRAL_EDUCATION, "A benchmark is a standard against which performance is measured.", [], _one("unknown", "uncertain"), "definition"),
    _case("NE-10", NEUTRAL_EDUCATION, "Operating costs were broadly flat over the period.", [], _one("unknown", "uncertain"), "neutral statement"),
    # -- ambiguous ----------------------------------------------------------
    _case("AM-01", AMBIGUOUS, "Returns are not guaranteed.", [], _one("unknown", "uncertain"), "negated guarantee"),
    _case("AM-02", AMBIGUOUS, "If markets rise, returns are guaranteed.", [], _one("unknown", "uncertain", "GUARANTEE"), "conditional guarantee"),
    _case("AM-03", AMBIGUOUS, "Returns may be guaranteed.", [], _one("unknown", "uncertain", "GUARANTEE"), "modal hedge"),
    _case("AM-04", AMBIGUOUS, "Returns could be guaranteed if the scheme performs.", [], _one("unknown", "uncertain", "GUARANTEE"), "conditional with a modal"),
    _case("AM-05", AMBIGUOUS, "A guaranteed return is not available.", [], _one("unknown", "uncertain", "GUARANTEE"), "negation after the frame"),
    _case("AM-06", AMBIGUOUS, "Past performance does not guarantee future results.", [], _one("unknown", "uncertain"), "standard disclaimer"),
    _case("AM-07", AMBIGUOUS, "The fund does not guarantee your capital.", [], _one("unknown", "uncertain"), "active negation"),
    _case("AM-08", AMBIGUOUS, "Whether returns are guaranteed depends on the scheme.", [], _one("unknown", "uncertain", "GUARANTEE"), "framed as an open question"),
    _case("AM-09", AMBIGUOUS, "Returns are guaranteed, according to the marketing material.", [], _one("third_party", "quoted", "GUARANTEE"), "reported, and the marketing material is a checkable document"),
    _case("AM-10", AMBIGUOUS, "The index will probably be rebalanced in June.", [], _one("unknown", "uncertain"), "hedged, so not a prediction"),
)


def group_cases(
    group: str, cases: Sequence[BenchmarkCase] | None = None
) -> tuple[BenchmarkCase, ...]:
    active = cases if cases is not None else BENCHMARK_CASES
    return tuple(case for case in active if case.group == group)


def group_sizes(
    cases: Sequence[BenchmarkCase] | None = None,
) -> Mapping[str, int]:
    active = cases if cases is not None else BENCHMARK_CASES
    return {group: sum(1 for c in active if c.group == group) for group in GROUP_NAMES}


def case_index(
    cases: Sequence[BenchmarkCase] | None = None,
) -> Mapping[str, BenchmarkCase]:
    active = cases if cases is not None else BENCHMARK_CASES
    return {case.case_id: case for case in active}


def label_source(case: BenchmarkCase) -> str:
    """Where the case's label comes from. Always the guide, never a run."""

    return case.basis or GROUP_BASIS[case.group]


def relation_counts(
    cases: Sequence[BenchmarkCase] | None = None,
) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for case in cases if cases is not None else BENCHMARK_CASES:
        for relation in case.expected_relations:
            counts[relation] = counts.get(relation, 0) + 1
    return dict(sorted(counts.items()))
