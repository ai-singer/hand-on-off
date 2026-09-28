"""The independent validation benchmark, `independent_v1`.

One hundred cases written for Phase 8.6, none reused from any earlier benchmark.
The phase forbids reusing Phase 8.1's adversarial set, Phase 8.2's annotation
set, Phase 8.3's experiment dataset, Phase 8.4's pattern benchmark or Phase
8.5's composition benchmark, and the audit in `audit.py` checks that claim
mechanically rather than taking it on trust.

Composition:

    author_endorsed_risk   25   the article's own risky claim
    third_party_claim      20   somebody else's claim, reported
    author_rejection       15   a claim the article argues against
    neutral_education      20   explanatory text with no claim
    ambiguous_boundary     20   negated, conditional, reported or uncertain

All five categories are covered: `financial_guarantee`, `investment_advice`,
`market_prediction`, `unverified_information` and `emotional_manipulation`.

**Labels come from the annotation guide, never from an evaluator.** Every case
carries an `annotation_reason` naming the guide section its label follows.
Writing this set was deliberately separated from writing the pipeline: the cases
were drafted from `RISK_ANNOTATION_GUIDE_v2.md` and `INDEPENDENT_ANNOTATION_
PROTOCOL.md`, and the pipeline was not consulted while labelling.

The forms recur because the forms are the subject - a passive guarantee is a
passive guarantee - but the sentences are new, and the audit measures how much
text is shared with earlier benchmarks rather than assuming none is.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..taxonomy import RISK_TAXONOMY


BENCHMARK_ID = "independent_v1"
BENCHMARK_VERSION = "v1"
DATASET_PATH = Path(__file__).resolve().parent / "independent_v1.json"

AUTHOR_ENDORSED_RISK = "author_endorsed_risk"
THIRD_PARTY_CLAIM = "third_party_claim"
AUTHOR_REJECTION = "author_rejection"
NEUTRAL_EDUCATION = "neutral_education"
AMBIGUOUS_BOUNDARY = "ambiguous_boundary"

GROUP_NAMES: Mapping[str, str] = {
    AUTHOR_ENDORSED_RISK: "author endorsed risk",
    THIRD_PARTY_CLAIM: "third party claim",
    AUTHOR_REJECTION: "author rejection",
    NEUTRAL_EDUCATION: "neutral education",
    AMBIGUOUS_BOUNDARY: "ambiguous boundary",
}

TARGET_GROUP_SIZES: Mapping[str, int] = {
    AUTHOR_ENDORSED_RISK: 25,
    THIRD_PARTY_CLAIM: 20,
    AUTHOR_REJECTION: 15,
    NEUTRAL_EDUCATION: 20,
    AMBIGUOUS_BOUNDARY: 20,
}

MINIMUM_CASES = 100

#: Guide section each group's labels follow.
GROUP_BASIS: Mapping[str, str] = {
    AUTHOR_ENDORSED_RISK: (
        "guide v2 3.1 and 7: a directive, prediction, guarantee, uncheckable "
        "claim or reader pressure in the author's own voice is the category"
    ),
    THIRD_PARTY_CLAIM: (
        "guide v2 3.1 and 7: a reported claim is not the article's, and only an "
        "uncheckable source is unverified_information"
    ),
    AUTHOR_REJECTION: (
        "guide v2 3.1 and 4: arguing against a claim is not making it"
    ),
    NEUTRAL_EDUCATION: "guide v2 7: explanation and method guidance are negative",
    AMBIGUOUS_BOUNDARY: (
        "guide v2 2 and 5: a conditional, negated or hedged claim asserts "
        "nothing unconditionally"
    ),
}

RELATIONS = ("GUARANTEE", "RISK_REMOVED", "PREDICTION", "ADVICE")


@dataclass(frozen=True, slots=True)
class ClaimLabel:
    """What the guide says about one claim."""

    speaker: str
    stance: str
    relation: str = ""

    def __post_init__(self) -> None:
        if self.speaker not in ("author", "third_party", "unknown"):
            raise ValueError(f"bad speaker {self.speaker!r}")
        if self.stance not in ("endorsed", "quoted", "rejected", "uncertain"):
            raise ValueError(f"bad stance {self.stance!r}")
        if self.relation and self.relation not in RELATIONS:
            raise ValueError(f"bad relation {self.relation!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "stance": self.stance,
            "relation": self.relation,
        }


@dataclass(frozen=True, slots=True)
class ValidationCase:
    case_id: str
    group: str
    text: str
    categories: tuple[str, ...]
    claims: tuple[ClaimLabel, ...]
    annotation_reason: str

    def __post_init__(self) -> None:
        if self.group not in GROUP_NAMES:
            raise ValueError(f"{self.case_id}: unknown group {self.group!r}")
        if not self.text.strip():
            raise ValueError(f"{self.case_id}: text must not be empty")
        if not self.claims:
            raise ValueError(f"{self.case_id}: at least one claim label is required")
        if not self.annotation_reason.strip():
            raise ValueError(f"{self.case_id}: an annotation reason is required")
        known = {entry.name for entry in RISK_TAXONOMY}
        for name in self.categories:
            if name not in known:
                raise ValueError(f"{self.case_id}: unknown category {name!r}")

    @property
    def expects_risk(self) -> bool:
        return bool(self.categories)

    @property
    def expected_relations(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(c.relation for c in self.claims if c.relation))

    @property
    def expected_speakers(self) -> tuple[str, ...]:
        return tuple(c.speaker for c in self.claims)

    @property
    def expected_stances(self) -> tuple[str, ...]:
        return tuple(c.stance for c in self.claims)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "text": self.text,
            "labels": {
                "claims": [c.as_dict() for c in self.claims],
                "speakers": list(self.expected_speakers),
                "stances": list(self.expected_stances),
                "relations": list(self.expected_relations),
                "categories": list(self.categories),
                "expects_risk": self.expects_risk,
            },
            "group": self.group,
            "group_name": GROUP_NAMES[self.group],
            "annotation_reason": self.annotation_reason,
            "basis": GROUP_BASIS[self.group],
        }

    def blind_record(self) -> dict[str, str]:
        """The part of a case an evaluation may read: id and text, no labels."""

        return {"id": self.case_id, "text": self.text}


def _c(
    case_id: str,
    group: str,
    text: str,
    categories: Sequence[str],
    claims: Sequence[ClaimLabel],
    reason: str,
) -> ValidationCase:
    return ValidationCase(case_id, group, text, tuple(categories), tuple(claims), reason)


def _one(speaker: str, stance: str, relation: str = "") -> tuple[ClaimLabel, ...]:
    return (ClaimLabel(speaker, stance, relation),)


CASES: tuple[ValidationCase, ...] = (
    # ================= author endorsed risk (25) =================
    _c("IV-001", AUTHOR_ENDORSED_RISK, "Your money is guaranteed to be returned in full.", ["financial_guarantee"], _one("unknown", "uncertain", "GUARANTEE"), "guide 7: risk removed, copular guarantee"),
    _c("IV-002", AUTHOR_ENDORSED_RISK, "The scheme guarantees the return of your capital.", ["financial_guarantee"], _one("unknown", "uncertain", "GUARANTEE"), "guide 7: active guarantee"),
    _c("IV-003", AUTHOR_ENDORSED_RISK, "Capital protection is guaranteed under this plan.", ["financial_guarantee"], _one("unknown", "uncertain", "GUARANTEE"), "guide 7: copular guarantee with a compound subject"),
    _c("IV-004", AUTHOR_ENDORSED_RISK, "A guarantee on your principal is provided.", ["financial_guarantee"], _one("unknown", "uncertain", "GUARANTEE"), "guide 7: nominal guarantee"),
    _c("IV-005", AUTHOR_ENDORSED_RISK, "This product carries zero risk of loss.", ["financial_guarantee"], _one("unknown", "uncertain", "RISK_REMOVED"), "guide 7: risk denied outright"),
    _c("IV-006", AUTHOR_ENDORSED_RISK, "You cannot lose your principal here.", ["financial_guarantee"], _one("unknown", "uncertain", "RISK_REMOVED"), "guide 7: risk denied outright"),
    _c("IV-007", AUTHOR_ENDORSED_RISK, "Put your savings into this fund before the deadline.", ["investment_advice"], _one("unknown", "uncertain", "ADVICE"), "guide 7: imperative directive plus object"),
    _c("IV-008", AUTHOR_ENDORSED_RISK, "Investors should allocate more to this fund.", ["investment_advice"], _one("unknown", "uncertain", "ADVICE"), "guide 7: modal directive plus object"),
    _c("IV-009", AUTHOR_ENDORSED_RISK, "Buy into this fund while units are still available.", ["investment_advice"], _one("unknown", "uncertain", "ADVICE"), "guide 7: imperative directive plus object"),
    _c("IV-010", AUTHOR_ENDORSED_RISK, "The sensible choice is to hold these bonds for income.", ["investment_advice"], _one("unknown", "uncertain", "ADVICE"), "guide 7: implicit directive plus object"),
    _c("IV-011", AUTHOR_ENDORSED_RISK, "Consider moving your capital into the equity fund.", ["investment_advice"], _one("unknown", "uncertain", "ADVICE"), "guide 7: imperative directive plus object"),
    _c("IV-012", AUTHOR_ENDORSED_RISK, "The unit price will definitely climb by December.", ["market_prediction"], _one("unknown", "uncertain", "PREDICTION"), "guide 2: author-voice certainty about a future outcome"),
    _c("IV-013", AUTHOR_ENDORSED_RISK, "Yields are certain to rise over the coming months.", ["market_prediction"], _one("unknown", "uncertain", "PREDICTION"), "guide 2: copular certainty"),
    _c("IV-014", AUTHOR_ENDORSED_RISK, "Turnover expands sharply next quarter.", ["market_prediction"], _one("unknown", "uncertain", "PREDICTION"), "guide 2: present-tense assertion with a horizon"),
    _c("IV-015", AUTHOR_ENDORSED_RISK, "The index is going to rally from here.", ["market_prediction"], _one("unknown", "uncertain", "PREDICTION"), "guide 2: author-voice certainty"),
    _c("IV-016", AUTHOR_ENDORSED_RISK, "Earnings will surely multiply under the new plan.", ["market_prediction"], _one("unknown", "uncertain", "PREDICTION"), "guide 2: author-voice certainty"),
    _c("IV-017", AUTHOR_ENDORSED_RISK, "Word on the street is that the board will resign.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: carried on an uncheckable source"),
    _c("IV-018", AUTHOR_ENDORSED_RISK, "An unnamed official confirmed the restatement.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: explicitly anonymous source"),
    _c("IV-019", AUTHOR_ENDORSED_RISK, "A source claims the audit was qualified.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: uncheckable source"),
    _c("IV-020", AUTHOR_ENDORSED_RISK, "Reportedly the fund has suspended redemptions.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: reported without a checkable source"),
    _c("IV-021", AUTHOR_ENDORSED_RISK, "I heard the custodian is being replaced.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: first-person hearsay names no source"),
    _c("IV-022", AUTHOR_ENDORSED_RISK, "Hurry, this window closes tonight.", ["emotional_manipulation"], _one("unknown", "uncertain"), "guide 6.1: deadline pressure on the reader"),
    _c("IV-023", AUTHOR_ENDORSED_RISK, "Nobody wants to be the one who missed this.", ["emotional_manipulation"], _one("unknown", "uncertain"), "guide 6.1: herd framing"),
    _c("IV-024", AUTHOR_ENDORSED_RISK, "Act fast or watch others take the gains.", ["emotional_manipulation"], _one("unknown", "uncertain"), "guide 6.1: imperative pressure"),
    _c("IV-025", AUTHOR_ENDORSED_RISK, "This is a last chance to get in.", ["emotional_manipulation"], _one("unknown", "uncertain"), "guide 6.1: deadline pressure"),
    # ================= third party claim (20) =================
    _c("IV-026", THIRD_PARTY_CLAIM, "Analysts say the fund is about to gate redemptions.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: unnamed collective is uncheckable"),
    _c("IV-027", THIRD_PARTY_CLAIM, "Insiders say the dividend will be suspended.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: uncheckable source"),
    _c("IV-028", THIRD_PARTY_CLAIM, "Sources claim the merger talks have stalled.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: uncheckable source"),
    _c("IV-029", THIRD_PARTY_CLAIM, "Rumour has it the chief executive is leaving.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: rumour is unattributable"),
    _c("IV-030", THIRD_PARTY_CLAIM, "Reportedly the fund has changed its mandate.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: reported without a checkable source"),
    _c("IV-031", THIRD_PARTY_CLAIM, "Word on the street is that the audit is late.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: uncheckable source"),
    _c("IV-032", THIRD_PARTY_CLAIM, "A person familiar with the matter says the deal is off.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: anonymous person"),
    _c("IV-033", THIRD_PARTY_CLAIM, "Traders say the shares are cheap.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: unnamed collective is uncheckable"),
    _c("IV-034", THIRD_PARTY_CLAIM, "An anonymous official confirmed the probe.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: explicitly anonymous source"),
    _c("IV-035", THIRD_PARTY_CLAIM, "Market chatter suggests the float will be cut.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: unattributable chatter"),
    _c("IV-036", THIRD_PARTY_CLAIM, "The company said the timetable is unchanged.", [], _one("third_party", "quoted"), "guide 7: named, checkable source is negative"),
    _c("IV-037", THIRD_PARTY_CLAIM, "According to the prospectus, charges are capped.", [], _one("third_party", "quoted"), "guide 7: checkable document"),
    _c("IV-038", THIRD_PARTY_CLAIM, "The report states that revenue fell.", [], _one("third_party", "quoted"), "guide 7: checkable document"),
    _c("IV-039", THIRD_PARTY_CLAIM, "Management expects margins to hold.", [], _one("third_party", "quoted"), "guide 7: named, checkable source"),
    _c("IV-040", THIRD_PARTY_CLAIM, "The board said the dividend is unchanged.", [], _one("third_party", "quoted"), "guide 7: named, checkable source"),
    _c("IV-041", THIRD_PARTY_CLAIM, "The regulator said the review is ongoing.", [], _one("third_party", "quoted"), "guide 7: named, checkable source"),
    _c("IV-042", THIRD_PARTY_CLAIM, "The newsletter recommends holding the fund.", [], _one("third_party", "quoted"), "guide 7: definite publication is checkable"),
    _c("IV-043", THIRD_PARTY_CLAIM, "The custodian confirmed the transfer.", [], _one("third_party", "quoted"), "guide 7: named, checkable source"),
    _c("IV-044", THIRD_PARTY_CLAIM, "The trustee published the annual statement.", [], _one("third_party", "quoted"), "guide 7: named, checkable source"),
    _c("IV-045", THIRD_PARTY_CLAIM, "The exchange said trading was orderly.", [], _one("third_party", "quoted"), "guide 7: named, checkable source"),
    # ================= author rejection (15) =================
    _c("IV-046", AUTHOR_REJECTION, "We reject the suggestion that returns are guaranteed.", [], _one("author", "rejected", "GUARANTEE"), "guide 3.1: arguing against a claim is not making it"),
    _c("IV-047", AUTHOR_REJECTION, "We are unconvinced that capital is protected here.", [], _one("author", "rejected", "GUARANTEE"), "guide 3.1: rejection"),
    _c("IV-048", AUTHOR_REJECTION, "The idea that the fund cannot fall is not supported.", [], _one("author", "rejected", "RISK_REMOVED"), "guide 3.1: rejection"),
    _c("IV-049", AUTHOR_REJECTION, "We dispute the claim that yields will double.", [], _one("author", "rejected", "PREDICTION"), "guide 3.1: rejection"),
    _c("IV-050", AUTHOR_REJECTION, "Contrary to the marketing, the return is not guaranteed.", [], _one("author", "rejected", "GUARANTEE"), "guide 3.1: rejection"),
    _c("IV-051", AUTHOR_REJECTION, "We see no basis for the view that the price will triple.", [], _one("author", "rejected", "PREDICTION"), "guide 3.1: rejection"),
    _c("IV-052", AUTHOR_REJECTION, "The assertion that losses are impossible is false.", [], _one("author", "rejected", "RISK_REMOVED"), "guide 3.1: rejection"),
    _c("IV-053", AUTHOR_REJECTION, "We disagree that this is a suitable holding for retirees.", [], _one("author", "rejected", "ADVICE"), "guide 3.1: rejection"),
    _c("IV-054", AUTHOR_REJECTION, "Claims that the fund is risk-free are overstated.", [], _one("author", "rejected", "RISK_REMOVED"), "guide 3.1: rejection"),
    _c("IV-055", AUTHOR_REJECTION, "We do not accept that the index will recover.", [], _one("author", "rejected", "PREDICTION"), "guide 3.1: rejection"),
    _c("IV-056", AUTHOR_REJECTION, "The fund cannot lose money, or so the advert claims; we disagree.", [], _one("author", "rejected", "RISK_REMOVED"), "guide 4: quoted pressure rejected"),
    _c("IV-057", AUTHOR_REJECTION, "We doubt the projection that earnings will multiply.", [], _one("author", "rejected", "PREDICTION"), "guide 3.1: rejection"),
    _c("IV-058", AUTHOR_REJECTION, "That the shares are cheap is not something we accept.", [], _one("author", "rejected", "ADVICE"), "guide 3.1: rejection"),
    _c("IV-059", AUTHOR_REJECTION, "We would not describe this as a safe bet.", [], _one("author", "rejected", "RISK_REMOVED"), "guide 3.1: rejection"),
    _c("IV-060", AUTHOR_REJECTION, "There is no evidence for the claim that capital is protected.", [], _one("author", "rejected", "GUARANTEE"), "guide 3.1: rejection"),
    # ================= neutral education (20) =================
    _c("IV-061", NEUTRAL_EDUCATION, "A bond's duration measures its sensitivity to interest rates.", [], _one("unknown", "uncertain"), "guide 7: explanation is negative"),
    _c("IV-062", NEUTRAL_EDUCATION, "The expense ratio is the annual cost of holding a fund.", [], _one("unknown", "uncertain"), "guide 7: definition"),
    _c("IV-063", NEUTRAL_EDUCATION, "Real returns adjust nominal returns for inflation.", [], _one("unknown", "uncertain"), "guide 7: definition"),
    _c("IV-064", NEUTRAL_EDUCATION, "A limit order sets a maximum or minimum execution price.", [], _one("unknown", "uncertain"), "guide 7: explanation"),
    _c("IV-065", NEUTRAL_EDUCATION, "Rebalancing restores a portfolio to its target weights.", [], _one("unknown", "uncertain"), "guide 7: method guidance"),
    _c("IV-066", NEUTRAL_EDUCATION, "The yield curve plots yields against maturity.", [], _one("unknown", "uncertain"), "guide 7: definition"),
    _c("IV-067", NEUTRAL_EDUCATION, "Credit risk is the chance an issuer fails to pay.", [], _one("unknown", "uncertain"), "guide 7: definition of a risk concept, not a claim about a product"),
    _c("IV-068", NEUTRAL_EDUCATION, "A tracking error measures deviation from a benchmark.", [], _one("unknown", "uncertain"), "guide 7: definition"),
    _c("IV-069", NEUTRAL_EDUCATION, "The settlement cycle determines when cash changes hands.", [], _one("unknown", "uncertain"), "guide 7: explanation"),
    _c("IV-070", NEUTRAL_EDUCATION, "Dollar-cost averaging buys fixed amounts at regular intervals.", [], _one("unknown", "uncertain"), "guide 7: method guidance"),
    _c("IV-071", NEUTRAL_EDUCATION, "The prospectus sets out the fund's investment objective.", [], _one("unknown", "uncertain"), "guide 7: neutral statement"),
    _c("IV-072", NEUTRAL_EDUCATION, "Custodians hold assets on behalf of the fund.", [], _one("unknown", "uncertain"), "guide 7: explanation"),
    _c("IV-073", NEUTRAL_EDUCATION, "An index committee reviews the constituents quarterly.", [], _one("unknown", "uncertain"), "guide 7: neutral statement"),
    _c("IV-074", NEUTRAL_EDUCATION, "The audit committee meets four times a year.", [], _one("unknown", "uncertain"), "guide 7: neutral statement"),
    _c("IV-075", NEUTRAL_EDUCATION, "Stamp duty applies to certain share purchases.", [], _one("unknown", "uncertain"), "guide 7: explanation"),
    _c("IV-076", NEUTRAL_EDUCATION, "Withholding tax is deducted at source in some jurisdictions.", [], _one("unknown", "uncertain"), "guide 7: explanation"),
    _c("IV-077", NEUTRAL_EDUCATION, "A closed-end fund trades at a premium or a discount.", [], _one("unknown", "uncertain"), "guide 7: definition"),
    _c("IV-078", NEUTRAL_EDUCATION, "The fund's year end is the thirty-first of December.", [], _one("unknown", "uncertain"), "guide 7: neutral statement"),
    _c("IV-079", NEUTRAL_EDUCATION, "Units are priced once a day at the valuation point.", [], _one("unknown", "uncertain"), "guide 7: explanation"),
    _c("IV-080", NEUTRAL_EDUCATION, "The manager's report is published with the annual accounts.", [], _one("unknown", "uncertain"), "guide 7: neutral statement"),
    # ================= ambiguous boundary (20) =================
    _c("IV-081", AMBIGUOUS_BOUNDARY, "Returns are not guaranteed under any circumstances.", [], _one("unknown", "uncertain", "GUARANTEE"), "guide 5: negated claim asserts nothing"),
    _c("IV-082", AMBIGUOUS_BOUNDARY, "Capital protection is not offered on this share class.", [], _one("unknown", "uncertain"), "guide 5: negation"),
    _c("IV-083", AMBIGUOUS_BOUNDARY, "The fund does not guarantee income.", [], _one("unknown", "uncertain"), "guide 5: active negation"),
    _c("IV-084", AMBIGUOUS_BOUNDARY, "Past performance is no guide to future returns.", [], _one("unknown", "uncertain"), "guide 7: standard disclaimer"),
    _c("IV-085", AMBIGUOUS_BOUNDARY, "The scheme will not guarantee your principal.", [], _one("unknown", "uncertain"), "guide 5: future negation"),
    _c("IV-086", AMBIGUOUS_BOUNDARY, "No guarantee is given regarding distributions.", [], _one("unknown", "uncertain", "GUARANTEE"), "guide 5: negation"),
    _c("IV-087", AMBIGUOUS_BOUNDARY, "If inflation subsides, yields may rise.", [], _one("unknown", "uncertain", "PREDICTION"), "guide 5: conditional outcome"),
    _c("IV-088", AMBIGUOUS_BOUNDARY, "Should the index fall, the fund would underperform.", [], _one("unknown", "uncertain"), "guide 5: inverted conditional"),
    _c("IV-089", AMBIGUOUS_BOUNDARY, "Assuming rates hold, income is likely to be stable.", [], _one("unknown", "uncertain"), "guide 5: conditional"),
    _c("IV-090", AMBIGUOUS_BOUNDARY, "The return is guaranteed only if the plan is held for five years.", [], _one("unknown", "uncertain", "GUARANTEE"), "guide 5: conditional guarantee"),
    _c("IV-091", AMBIGUOUS_BOUNDARY, "Were the issuer to default, capital would be at risk.", [], _one("unknown", "uncertain"), "guide 5: subjunctive conditional"),
    _c("IV-092", AMBIGUOUS_BOUNDARY, "Depending on the outcome, the payout could double.", [], _one("unknown", "uncertain", "PREDICTION"), "guide 5: conditional"),
    _c("IV-093", AMBIGUOUS_BOUNDARY, "The marketing material states that returns are guaranteed.", [], _one("third_party", "quoted", "GUARANTEE"), "guide 7: checkable document, so negative"),
    _c("IV-094", AMBIGUOUS_BOUNDARY, "A promoter claimed the fund cannot lose money.", ["unverified_information"], _one("third_party", "quoted", "RISK_REMOVED"), "guide 7: indefinite promoter is uncheckable"),
    _c("IV-095", AMBIGUOUS_BOUNDARY, "The advert says the price will certainly double.", [], _one("third_party", "quoted", "PREDICTION"), "guide 7: checkable advert, so negative"),
    _c("IV-096", AMBIGUOUS_BOUNDARY, "Some commentators argue the shares are cheap.", ["unverified_information"], _one("third_party", "quoted"), "guide 7: unnamed collective is uncheckable"),
    _c("IV-097", AMBIGUOUS_BOUNDARY, "The index might recover later in the year.", [], _one("unknown", "uncertain"), "guide 2: hedged, not asserted as certain"),
    _c("IV-098", AMBIGUOUS_BOUNDARY, "Perhaps the fund will outperform its benchmark.", [], _one("unknown", "uncertain", "PREDICTION"), "guide 2: hedged"),
    _c("IV-099", AMBIGUOUS_BOUNDARY, "There is a possibility that yields fall.", [], _one("unknown", "uncertain"), "guide 2: hedged"),
    _c("IV-100", AMBIGUOUS_BOUNDARY, "The shares could be cheap at this level.", [], _one("unknown", "uncertain"), "guide 2: hedged"),
)


def group_cases(
    group: str, cases: Sequence[ValidationCase] | None = None
) -> tuple[ValidationCase, ...]:
    active = cases if cases is not None else CASES
    return tuple(c for c in active if c.group == group)


def group_sizes(cases: Sequence[ValidationCase] | None = None) -> Mapping[str, int]:
    active = cases if cases is not None else CASES
    return {g: sum(1 for c in active if c.group == g) for g in GROUP_NAMES}


def category_counts(
    cases: Sequence[ValidationCase] | None = None,
) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for case in cases if cases is not None else CASES:
        for name in case.categories:
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def relation_counts(
    cases: Sequence[ValidationCase] | None = None,
) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    for case in cases if cases is not None else CASES:
        for name in case.expected_relations:
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def case_index(
    cases: Sequence[ValidationCase] | None = None,
) -> Mapping[str, ValidationCase]:
    active = cases if cases is not None else CASES
    return {c.case_id: c for c in active}


#: The version `independent_v1` is published under alongside the clean subset.
DECONTAMINATED_VERSION = "v2"

#: Case ids the audit found in an earlier benchmark. Recorded by hand from the
#: audit output and **not** removed from v1: deleting a contaminated case and
#: recomputing is what the phase forbids. v2 is published beside v1 instead, the
#: same response Phase 7.4 applied to `semantic/v1`.
CONTAMINATED_CASE_IDS: tuple[str, ...] = ("IV-037",)


def decontaminated_cases(
    cases: Sequence[ValidationCase] | None = None,
) -> tuple[ValidationCase, ...]:
    """v1 minus the cases the audit flagged, published as `independent_v2`."""

    active = tuple(cases) if cases is not None else CASES
    excluded = set(CONTAMINATED_CASE_IDS)
    return tuple(case for case in active if case.case_id not in excluded)


def version_payload(
    version: str, cases: Sequence[ValidationCase]
) -> dict[str, Any]:
    payload = dataset_payload(cases)
    payload["version"] = version
    payload["derived_from"] = (
        f"{BENCHMARK_ID}/{BENCHMARK_VERSION}" if version != BENCHMARK_VERSION else ""
    )
    payload["excluded_case_ids"] = (
        list(CONTAMINATED_CASE_IDS) if version != BENCHMARK_VERSION else []
    )
    return payload


def blind_records(cases: Sequence[ValidationCase] | None = None) -> tuple[dict[str, str], ...]:
    """The benchmark as an evaluator may see it: id and text only.

    The blind evaluation reads this, not `CASES`, so there is no code path from
    the prediction stage to a label.
    """

    active = cases if cases is not None else CASES
    return tuple(case.blind_record() for case in active)


def dataset_payload(cases: Sequence[ValidationCase] | None = None) -> dict[str, Any]:
    active = tuple(cases) if cases is not None else CASES
    return {
        "benchmark": BENCHMARK_ID,
        "version": BENCHMARK_VERSION,
        "case_count": len(active),
        "annotation": "single-annotator engineering validation only",
        "groups": dict(group_sizes(active)),
        "target_group_sizes": dict(TARGET_GROUP_SIZES),
        "group_basis": dict(GROUP_BASIS),
        "category_counts": dict(category_counts(active)),
        "relation_counts": dict(relation_counts(active)),
        "cases": [case.as_dict() for case in active],
    }


def write_dataset(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else DATASET_PATH
    target.write_text(
        json.dumps(dataset_payload(), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return target


def write_decontaminated(path: str | Path | None = None) -> Path:
    """Write `independent_v2`, the clean subset, beside v1."""

    target = (
        Path(path)
        if path is not None
        else DATASET_PATH.with_name(f"independent_{DECONTAMINATED_VERSION}.json")
    )
    clean = decontaminated_cases()
    target.write_text(
        json.dumps(
            version_payload(DECONTAMINATED_VERSION, clean),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def write_blind(path: str | Path) -> Path:
    """Write the label-free view the blind evaluation consumes."""

    target = Path(path)
    target.write_text(
        json.dumps(list(blind_records()), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    print(f"{BENCHMARK_ID}/{BENCHMARK_VERSION}")
    for group, size in group_sizes().items():
        target = TARGET_GROUP_SIZES[group]
        mark = "ok" if size >= target else "SHORT"
        print(f"  {group:24} {size:3} / {target:3} {mark}")
    print(f"  {'total':24} {len(CASES):3} / {MINIMUM_CASES:3}")
    print(f"  categories  {dict(category_counts())}")
    print(f"  relations   {dict(relation_counts())}")
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_dataset()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
