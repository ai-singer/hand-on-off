"""The Phase 8.3 experiment dataset, version v1.

Sixty cases in five groups, plus a twelve-case Phase 8.1 replay set.

    A  author risk           15   the article's own risky claim
    B  third-party citation  10   somebody else's claim, reported
    C  author rejection      10   a claim the article argues against
    D  mixed claim           10   a borrowed attribution beside the author's claim
    E  no-risk education     15   neutral explanatory text

Group D is the shape Phase 8.1 found: an unrelated attribution in the first
sentence withdraws every author-voice category in the second. Group E is the
control: text that a correct evaluator leaves alone, so over-correction is as
visible as under-correction.

Expectations follow annotation guide v2, not the evaluators:

    an author-voice category in a borrowed sentence is not expected
    a rejected claim is not the article's claim
    an uncheckable source is `unverified_information` whatever the voice
    a conditional or hedged statement is not a prediction

The dataset is **not registered as a benchmark**. Phase 8.3's allowed changes are
the experiment package, tests and docs; adding a version to the benchmark
registry would touch shared governance code and was not asked for. The set is
versioned here as `v1` and exported to `dataset_v1.json`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..taxonomy import RISK_TAXONOMY


DATASET_VERSION = "v1"
DATASET_PATH = Path(__file__).resolve().parent / "dataset_v1.json"

AUTHOR_RISK = "A"
THIRD_PARTY_CITATION = "B"
AUTHOR_REJECTION = "C"
MIXED_CLAIM = "D"
NO_RISK_EDUCATION = "E"

GROUP_NAMES: Mapping[str, str] = {
    AUTHOR_RISK: "author_risk",
    THIRD_PARTY_CITATION: "third_party_citation",
    AUTHOR_REJECTION: "author_rejection",
    MIXED_CLAIM: "mixed_claim",
    NO_RISK_EDUCATION: "no_risk_education",
}

#: Groups where an error is an attribution error rather than a category error.
ATTRIBUTION_GROUPS: tuple[str, ...] = (
    THIRD_PARTY_CITATION,
    AUTHOR_REJECTION,
    MIXED_CLAIM,
)

#: Required size per group, from the phase brief.
REQUIRED_GROUP_SIZES: Mapping[str, int] = {
    AUTHOR_RISK: 15,
    THIRD_PARTY_CITATION: 10,
    AUTHOR_REJECTION: 10,
    MIXED_CLAIM: 10,
    NO_RISK_EDUCATION: 15,
}


@dataclass(frozen=True, slots=True)
class ExperimentCase:
    case_id: str
    group: str
    text: str
    expected_categories: tuple[str, ...]
    note: str = ""
    origin: str = "phase-8.3"

    def __post_init__(self) -> None:
        if self.group not in GROUP_NAMES:
            raise ValueError(f"{self.case_id}: unknown group {self.group!r}")
        if not self.text.strip():
            raise ValueError(f"{self.case_id}: text must not be empty")
        known = {entry.name for entry in RISK_TAXONOMY}
        for name in self.expected_categories:
            if name not in known:
                raise ValueError(f"{self.case_id}: unknown category {name!r}")

    @property
    def group_name(self) -> str:
        return GROUP_NAMES[self.group]

    @property
    def expects_risk(self) -> bool:
        return bool(self.expected_categories)

    @property
    def is_attribution_case(self) -> bool:
        return self.group in ATTRIBUTION_GROUPS

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "group": self.group,
            "group_name": self.group_name,
            "text": self.text,
            "expected_categories": list(self.expected_categories),
            "expects_risk": self.expects_risk,
            "attribution_case": self.is_attribution_case,
            "note": self.note,
            "origin": self.origin,
        }


def _case(
    case_id: str,
    group: str,
    text: str,
    expected: Sequence[str] = (),
    note: str = "",
    origin: str = "phase-8.3",
) -> ExperimentCase:
    return ExperimentCase(case_id, group, text, tuple(expected), note, origin)


#: Sixty cases. Written from the guide's definitions, then measured: which ones
#: each evaluator gets right is the result of the experiment, not an input to it.
EXPERIMENT_CASES: tuple[ExperimentCase, ...] = (
    # -- A: the article's own risky claim --------------------------------
    _case("A-01", AUTHOR_RISK, "This fund cannot lose money.", ["financial_guarantee"], "unconditional outcome"),
    _case("A-02", AUTHOR_RISK, "This return is guaranteed.", ["financial_guarantee"], "plainest guarantee wording"),
    _case("A-03", AUTHOR_RISK, "You should buy this stock today.", ["investment_advice"], "directive plus object"),
    _case("A-04", AUTHOR_RISK, "Shift your savings into this fund.", ["investment_advice"], "directive plus object"),
    _case("A-05", AUTHOR_RISK, "The share price will certainly double next year.", ["market_prediction"], "author-voice certainty"),
    _case("A-06", AUTHOR_RISK, "Revenue will surely grow every quarter.", ["market_prediction"], "author-voice certainty"),
    _case("A-07", AUTHOR_RISK, "Do not miss this opportunity.", ["emotional_manipulation"], "pressure on the reader"),
    _case("A-08", AUTHOR_RISK, "Everyone is buying and there is no time left.", ["emotional_manipulation"], "herd framing plus deadline"),
    _case("A-09", AUTHOR_RISK, "Sources say the company will be acquired.", ["unverified_information"], "uncheckable source"),
    _case("A-10", AUTHOR_RISK, "Insiders say the dividend is about to be cut.", ["unverified_information"], "uncheckable source"),
    _case("A-11", AUTHOR_RISK, "We believe this fund cannot lose money.", ["financial_guarantee"], "author marker plus guarantee"),
    _case("A-12", AUTHOR_RISK, "Our analysis shows you should move your savings into this fund.", ["investment_advice"], "author marker plus directive"),
    _case("A-13", AUTHOR_RISK, "I think the stock will certainly reach 500.", ["market_prediction"], "author marker plus certainty"),
    _case("A-14", AUTHOR_RISK, "Act now before it is too late.", ["emotional_manipulation"], "deadline pressure"),
    _case("A-15", AUTHOR_RISK, "Rumour has it the merger is close.", ["unverified_information"], "unattributable source"),
    # -- B: somebody else's claim, reported ------------------------------
    _case("B-01", THIRD_PARTY_CITATION, "Analysts say this fund cannot lose money.", ["unverified_information"], "unnamed collective: source is uncheckable"),
    _case("B-02", THIRD_PARTY_CITATION, "The company said the fund cannot lose money.", [], "identifiable source: not the article's guarantee"),
    _case("B-03", THIRD_PARTY_CITATION, "According to the report, the fund cannot lose money.", [], "identifiable source"),
    _case("B-04", THIRD_PARTY_CITATION, "A broker told clients the fund cannot lose money.", [], "identifiable source"),
    _case("B-05", THIRD_PARTY_CITATION, "Management said the return is guaranteed.", [], "identifiable source"),
    _case("B-06", THIRD_PARTY_CITATION, "The report states the stock will certainly double.", [], "identifiable source, no reporting verb v2 knows"),
    _case("B-07", THIRD_PARTY_CITATION, "Officials said the fund cannot lose money.", [], "identifiable source"),
    _case("B-08", THIRD_PARTY_CITATION, "Commentators said the market will certainly crash.", [], "identifiable source"),
    _case("B-09", THIRD_PARTY_CITATION, "Economists forecast the stock will certainly double.", [], "identifiable source"),
    _case("B-10", THIRD_PARTY_CITATION, "The newsletter recommends buying this stock.", [], "identifiable source"),
    # -- C: a claim the article argues against ---------------------------
    _case("C-01", AUTHOR_REJECTION, "We disagree with the view that this fund cannot lose money.", [], "rejection precedes the claim"),
    _case("C-02", AUTHOR_REJECTION, "We disagree with the claim that the stock will certainly double.", [], "rejection precedes the claim"),
    _case("C-03", AUTHOR_REJECTION, "We doubt the fund cannot lose money.", [], "doubt is a rejection"),
    _case("C-04", AUTHOR_REJECTION, "Analysts say the fund cannot lose money. However, we disagree.", ["unverified_information"], "rejection leaves the sourcing risk standing"),
    _case("C-05", AUTHOR_REJECTION, "Experts expect the stock to rise. We are not convinced.", [], "reported claim then rejected"),
    _case("C-06", AUTHOR_REJECTION, "The marketing claims the fund cannot lose money. We do not endorse that.", [], "explicit non-endorsement"),
    _case("C-07", AUTHOR_REJECTION, "Do not miss this opportunity is what the advert says; we disagree.", [], "quoted pressure then rejected"),
    _case("C-08", AUTHOR_REJECTION, "This article rejects the idea that the fund cannot lose money.", [], "rejection with a self-reference"),
    _case("C-09", AUTHOR_REJECTION, "The claim that the stock will certainly double is incorrect.", [], "rejection without a first person"),
    _case("C-10", AUTHOR_REJECTION, "We are not convinced the fund cannot lose money.", [], "hedged rejection"),
    # -- D: borrowed attribution beside the author's claim ---------------
    _case("D-01", MIXED_CLAIM, "Economists forecast slower growth in Europe. This fund cannot lose money.", ["financial_guarantee"], "Phase 8.1 failure shape"),
    _case("D-02", MIXED_CLAIM, "Regulators published the revised disclosure rules. Do not miss this opportunity.", ["emotional_manipulation"], "Phase 8.1 failure shape"),
    _case("D-03", MIXED_CLAIM, "Analysts say the sector is volatile this year. Buy this stock before the quarter ends.", ["investment_advice"], "Phase 8.1 failure shape"),
    _case("D-04", MIXED_CLAIM, "The board said the timetable is unchanged. The share price will certainly double.", ["market_prediction"], "borrowed attribution plus prediction"),
    _case("D-05", MIXED_CLAIM, "Officials said the review is ongoing. Shift your savings into this fund.", ["investment_advice"], "borrowed attribution plus directive"),
    _case("D-06", MIXED_CLAIM, "Commentators said the quarter was mixed. This return is guaranteed.", ["financial_guarantee"], "borrowed attribution plus guarantee"),
    _case("D-07", MIXED_CLAIM, "The broker note described the sector. Act now before it is too late.", ["emotional_manipulation"], "borrowed attribution plus pressure"),
    _case("D-08", MIXED_CLAIM, "The newsletter described the fund. This fund cannot lose money.", ["financial_guarantee"], "borrowed publication plus guarantee"),
    _case("D-09", MIXED_CLAIM, "Regulators published the rules. We believe this fund cannot lose money.", ["financial_guarantee"], "borrowed attribution plus author marker"),
    _case("D-10", MIXED_CLAIM, "Analysts said the sector is volatile. You should buy this stock today.", ["investment_advice"], "borrowed attribution plus directive"),
    # -- E: no-risk explanatory text -------------------------------------
    _case("E-01", NO_RISK_EDUCATION, "The company reports its results in March.", [], "neutral statement"),
    _case("E-02", NO_RISK_EDUCATION, "A price-to-earnings ratio compares price with earnings per share.", [], "definition"),
    _case("E-03", NO_RISK_EDUCATION, "Diversification spreads risk across assets.", [], "method guidance"),
    _case("E-04", NO_RISK_EDUCATION, "If rates fall, the stock may rise.", [], "conditional outcome"),
    _case("E-05", NO_RISK_EDUCATION, "Panic is spreading through the sector.", [], "dramatic vocabulary, no reader pressure"),
    _case("E-06", NO_RISK_EDUCATION, "Compounding means returns are earned on earlier returns.", [], "definition"),
    _case("E-07", NO_RISK_EDUCATION, "The board meets on the second Tuesday of the month.", [], "neutral statement"),
    _case("E-08", NO_RISK_EDUCATION, "Interest rate changes affect bond prices inversely.", [], "explanation"),
    _case("E-09", NO_RISK_EDUCATION, "The fund's charges are set out in the prospectus.", [], "neutral statement"),
    _case("E-10", NO_RISK_EDUCATION, "Analysts' coverage of the sector has widened this year.", [], "neutral statement about coverage"),
    _case("E-11", NO_RISK_EDUCATION, "According to the prospectus, charges are capped.", [], "citation of a neutral fact"),
    _case("E-12", NO_RISK_EDUCATION, "A benchmark is a standard against which performance is measured.", [], "definition"),
    _case("E-13", NO_RISK_EDUCATION, "The audit covers the twelve months to December.", [], "neutral statement"),
    _case("E-14", NO_RISK_EDUCATION, "The index will probably be rebalanced in June.", [], "hedged, so not a prediction"),
    _case("E-15", NO_RISK_EDUCATION, "The marketing material should not be relied upon.", [], "negative guidance, not a guarantee"),
)


#: Phase 8.1's published `attribution_confusion` family has nine cases. Three
#: fresh cases of the same shape were authored here so the replay meets the
#: brief's ten-case minimum; they are marked `origin="phase-8.3"` and are the
#: only replay cases the layer has not been measured against before.
REPLAY_CASES: tuple[ExperimentCase, ...] = (
    _case("ATT-01", MIXED_CLAIM, "Analysts say the sector is volatile this year. Buy this stock before the quarter ends.", ["investment_advice"], "ADV-ATT-01, recorded failure ADV-F013", "phase-8.1"),
    _case("ATT-02", MIXED_CLAIM, "The company said costs were flat last quarter. The share price will certainly double next year.", ["market_prediction"], "ADV-ATT-02, passed by accident", "phase-8.1"),
    _case("ATT-03", MIXED_CLAIM, "Economists forecast slower growth in Europe. This fund cannot lose money.", ["financial_guarantee"], "ADV-ATT-03, recorded failure ADV-F014", "phase-8.1"),
    _case("ATT-04", MIXED_CLAIM, "The board said the timetable is unchanged. Sources say the company will be acquired.", ["unverified_information"], "ADV-ATT-04, voice-agnostic target", "phase-8.1"),
    _case("ATT-05", MIXED_CLAIM, "Regulators published the revised disclosure rules. Do not miss this opportunity.", ["emotional_manipulation"], "ADV-ATT-05, recorded failure ADV-F015", "phase-8.1"),
    _case("CTL-01", THIRD_PARTY_CITATION, "Analysts say this fund cannot lose money.", ["unverified_information"], "ADV-CTL-01 control", "phase-8.1"),
    _case("CTL-02", THIRD_PARTY_CITATION, "The newsletter recommends buying this stock.", [], "ADV-CTL-02 control", "phase-8.1"),
    _case("CTL-03", THIRD_PARTY_CITATION, "Management expects the share price to double.", [], "ADV-CTL-03 control", "phase-8.1"),
    _case("CTL-04", THIRD_PARTY_CITATION, "The article quotes a promoter saying do not miss this opportunity.", [], "ADV-CTL-04 control", "phase-8.1"),
    _case("NEW-01", MIXED_CLAIM, "The regulator said the fund is sound. This fund cannot lose money.", ["financial_guarantee"], "fresh case of the same shape", "phase-8.3"),
    _case("NEW-02", MIXED_CLAIM, "A broker note praised the sector. Buy this stock before the quarter ends.", ["investment_advice"], "fresh case of the same shape", "phase-8.3"),
    _case("NEW-03", MIXED_CLAIM, "Officials said the review continues. The fund cannot lose money.", ["financial_guarantee"], "fresh case of the same shape", "phase-8.3"),
)


def group_cases(
    group: str, cases: Sequence[ExperimentCase] | None = None
) -> tuple[ExperimentCase, ...]:
    active = cases if cases is not None else EXPERIMENT_CASES
    return tuple(case for case in active if case.group == group)


def group_sizes(
    cases: Sequence[ExperimentCase] | None = None,
) -> Mapping[str, int]:
    active = cases if cases is not None else EXPERIMENT_CASES
    return {
        group: sum(1 for case in active if case.group == group)
        for group in GROUP_NAMES
    }


def case_index(
    cases: Sequence[ExperimentCase] | None = None,
) -> Mapping[str, ExperimentCase]:
    active = cases if cases is not None else EXPERIMENT_CASES
    return {case.case_id: case for case in active}


def dataset_payload() -> dict[str, Any]:
    return {
        "dataset": "attribution_experiment",
        "version": DATASET_VERSION,
        "case_count": len(EXPERIMENT_CASES),
        "groups": {
            group: {"name": GROUP_NAMES[group], "count": size}
            for group, size in group_sizes().items()
        },
        "required_group_sizes": dict(REQUIRED_GROUP_SIZES),
        "attribution_groups": list(ATTRIBUTION_GROUPS),
        "replay_case_count": len(REPLAY_CASES),
        "cases": [case.as_dict() for case in EXPERIMENT_CASES],
        "replay_cases": [case.as_dict() for case in REPLAY_CASES],
    }


def write_dataset(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else DATASET_PATH
    target.write_text(
        json.dumps(dataset_payload(), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    print(f"attribution_experiment/{DATASET_VERSION}")
    for group, size in group_sizes().items():
        required = REQUIRED_GROUP_SIZES[group]
        mark = "ok" if size >= required else "SHORT"
        print(f"  {group} {GROUP_NAMES[group]:22} {size:3} / {required:3} {mark}")
    print(f"  total                    {len(EXPERIMENT_CASES):3}")
    print(f"  replay set               {len(REPLAY_CASES):3} (minimum 10)")
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_dataset()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
