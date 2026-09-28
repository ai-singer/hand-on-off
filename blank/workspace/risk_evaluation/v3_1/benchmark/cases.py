"""The Phase 8.8 capability benchmark: 80 cases in three groups.

    A  modal_prediction   30   is a probability statement a prediction?
    B  advice_boundary    30   is a directive aimed at the reader advice?
    C  regression         20   does the new capability still get the old cases right?

### What this benchmark is, and is not

It is **synthetic** and it is **not independent**. The same author who built the
capability wrote the cases, which is exactly the arrangement Phase 8.6 was created
to expose: on Phase 8.5's own benchmark the pipeline scored speaker accuracy 96.8%
and relation recall 100%, and on data it had not seen the numbers fell to 74.0% and
67.5%. A benchmark written after the capability and by its author cannot repeat
that finding, and nothing in this phase's results should be read as if it had.

What it can do, and does, is make the capability **falsifiable on named sentences**.
Each A and B case carries the guide section its label comes from, the capability
verdict expected, and the relation and category expected, so a reader can disagree
with a label and see the same evidence. Group C adds 20 cases whose labels were
written before this phase existed and are copied from the artifacts rather than
re-annotated, so the regression is measured against labels this phase could not
have tuned to.

The labels follow `docs/RISK_ANNOTATION_GUIDE_v2.md` and nothing else:

    section 1.2   the four certainty levels, and their markers
    section 2     market_prediction <=> author AND certainty == certain
    section 5     a conditional asserts nothing unconditionally
    section 7     advice is a directive aimed at the reader with a financial
                  object; educational explanation and method guidance are negative
    section 3.1   the author-voice requirement, and which layer decides it

### Group C: labels this phase did not write

Group C takes four cases from each of five frozen sources and reads their labels
from the source modules at import time. Nothing is transcribed, so nothing can be
transcribed differently:

    phase 8.1   the adversarial failure repository's recorded misses
    phase 8.3   the attribution experiment's replay and control cases
    phase 8.4   the intent pattern benchmark's guarantee positives
    phase 8.6   the independent benchmark's clean subset
    phase 8.7   the cases the targeted repair fixed, from the regression report

`83-CTL-04` is included deliberately. It is the Phase 8.3 control that Phase 8.7
found contradicted `IV-094`, and carrying it here means a later change that
resolves the conflict by adding `promoter` to the source lexicon fails immediately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...v3.model import ADVICE, PREDICTION, RELATIONS
from ...v3.replay import replay
from ...v3_validation.cases import case_index as phase_86_index
from ..advice import ADVICE_VERDICT, METHOD_GUIDANCE, THIRD_PERSON_SUBJECT
from ..advice import GERUND_SUBJECT
from ..modal import (
    NON_DIRECTIONAL_VERDICT,
    NON_PREDICTION_MODAL,
    PREDICTION_VERDICT,
    WEAK_PREDICTION,
)

BENCHMARK_ID = "capability_v3_1"
BENCHMARK_VERSION = "v1"
DATASET_PATH = Path(__file__).resolve().parent / "capability_v3_1.json"

#: Provenance, recorded because the phase requires it and because a benchmark
#: without it cannot be judged. `synthetic` and `independent` are the two fields
#: that matter most, and both are the honest answer rather than the flattering one.
PROVENANCE: Mapping[str, Any] = {
    "benchmark": f"{BENCHMARK_ID}/{BENCHMARK_VERSION}",
    "author": "ai-singer (the repository's single annotator of record)",
    "generated_by": "automated agent session, Phase 8.8",
    "generated_at": "2026-09-28",
    "source": (
        "authored for this phase against docs/RISK_ANNOTATION_GUIDE_v2.md; "
        "group C is copied from five frozen artifacts rather than authored"
    ),
    "synthetic": True,
    "independent": False,
    "independent_note": (
        "Groups A and B were written by the same author as the capability they "
        "measure. Phase 8.6 exists because that arrangement flatters a pipeline: "
        "speaker accuracy fell from 96.8% to 74.0% and relation recall from 100% "
        "to 67.5% when the same architecture met unseen sentences. No number in "
        "this benchmark carries that protection. Group C is a regression set, not "
        "an independence claim."
    ),
    "annotation": "single-annotator engineering validation only",
    "guide": "docs/RISK_ANNOTATION_GUIDE_v2.md",
    "protocol": "docs/INDEPENDENT_ANNOTATION_PROTOCOL_V2.md",
    "label_sources": {
        "A": "guide sections 1.2, 2, 5",
        "B": "guide sections 3.1, 4, 7",
        "C": "copied from the source artifacts; not re-annotated",
    },
}

#: Groups.
MODAL_PREDICTION = "modal_prediction"
ADVICE_BOUNDARY = "advice_boundary"
REGRESSION = "regression"

GROUP_NAMES: tuple[str, ...] = (MODAL_PREDICTION, ADVICE_BOUNDARY, REGRESSION)

#: Sub-groups, and the size each is required to reach. The phase names the
#: four kinds inside A and the four inside B, so they are declared rather than
#: left implicit in the case list.
STRONG_PREDICTION = "strong_prediction"
WEAK_PREDICTION_GROUP = "weak_prediction"
EDUCATIONAL_UNCERTAINTY = "educational_uncertainty"
NON_FINANCIAL_MODAL = "non_financial_modal"
DIRECT_ADVICE = "direct_advice"
INDIRECT_ADVICE = "indirect_advice"
EDUCATION = "education"
QUOTED_ADVICE = "quoted_advice"
FROZEN = "frozen"

SUBGROUP_SIZES: Mapping[str, int] = {
    STRONG_PREDICTION: 8,
    WEAK_PREDICTION_GROUP: 8,
    EDUCATIONAL_UNCERTAINTY: 8,
    NON_FINANCIAL_MODAL: 6,
    DIRECT_ADVICE: 8,
    INDIRECT_ADVICE: 8,
    EDUCATION: 8,
    QUOTED_ADVICE: 6,
    FROZEN: 20,
}

#: Frozen-source quotas inside group C, one per phase the phase names.
FROZEN_QUOTAS: Mapping[str, int] = {
    "phase-8.1": 4,
    "phase-8.3": 4,
    "phase-8.4": 4,
    "phase-8.6": 4,
    "phase-8.7": 4,
}

#: Which frozen cases group C carries. Named rather than sliced so the set is
#: stable when a source module gains a case.
FROZEN_CASE_IDS: Mapping[str, tuple[str, ...]] = {
    "phase-8.1": ("ADV-F001", "ADV-F002", "ADV-F003", "ADV-F014"),
    "phase-8.3": ("83-ATT-01", "83-ATT-03", "83-CTL-02", "83-CTL-04"),
    "phase-8.4": ("84-PG-01", "84-PG-03", "84-PG-05", "84-PG-07"),
    "phase-8.6": ("IV-001", "IV-005", "IV-033", "IV-072"),
    "phase-8.7": ("TQ-04", "TQ-06", "TQ-07", "IV-014"),
}

MINIMUM_CASES = 80

CATEGORIES: tuple[str, ...] = (
    "financial_guarantee",
    "investment_advice",
    "market_prediction",
    "unverified_information",
    "emotional_manipulation",
)


class BenchmarkError(Exception):
    """Raised when a case or the benchmark violates its contract."""


@dataclass(frozen=True, slots=True)
class ClaimLabel:
    """Who said one claim, in what stance, and which relation it carries."""

    speaker: str
    stance: str
    relation: str = ""

    def __post_init__(self) -> None:
        from ...attribution.model import SPEAKERS, STANCES

        if self.speaker not in SPEAKERS:
            raise BenchmarkError(f"unknown speaker {self.speaker!r}")
        if self.stance not in STANCES:
            raise BenchmarkError(f"unknown stance {self.stance!r}")
        if self.relation and self.relation not in RELATIONS:
            raise BenchmarkError(f"unknown relation {self.relation!r}")


@dataclass(frozen=True, slots=True)
class CapabilityCase:
    """One case, with the label, the guide section and the verdict expected."""

    case_id: str
    group: str
    subgroup: str
    text: str
    expected_categories: tuple[str, ...]
    claims: tuple[ClaimLabel, ...]
    basis: str
    #: The relation the case is a test of, if it is a test of one.
    relation: str = ""
    #: The capability verdict expected, for A and B cases. Empty for group C,
    #: whose point is the decision rather than the verdict.
    expected_verdict: str = ""
    origin: str = "phase-8.8/synthetic"
    #: For a group C case, the frozen phase whose artifact it was copied from. Kept
    #: as its own field rather than read out of `origin`, which is prose: the audit
    #: has to check provenance against a declared phase, and a descriptive string is
    #: not one.
    frozen_phase: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.group not in GROUP_NAMES:
            raise BenchmarkError(f"{self.case_id}: unknown group {self.group!r}")
        if self.subgroup not in SUBGROUP_SIZES:
            raise BenchmarkError(f"{self.case_id}: unknown subgroup {self.subgroup!r}")
        if not self.text.strip():
            raise BenchmarkError(f"{self.case_id}: empty text")
        if not self.basis.strip():
            raise BenchmarkError(f"{self.case_id}: a case must cite its guide section")
        for name in self.expected_categories:
            if name not in CATEGORIES:
                raise BenchmarkError(f"{self.case_id}: unknown category {name!r}")
        if not self.claims:
            raise BenchmarkError(f"{self.case_id}: a case must label its claims")

    @property
    def expects_risk(self) -> bool:
        return bool(self.expected_categories)

    @property
    def expected_relations(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(item.relation for item in self.claims if item.relation)
        )

    @property
    def expected_speakers(self) -> tuple[str, ...]:
        return tuple(item.speaker for item in self.claims)

    @property
    def expected_stances(self) -> tuple[str, ...]:
        return tuple(item.stance for item in self.claims)

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "group": self.group,
            "subgroup": self.subgroup,
            "text": self.text,
            "expected_categories": list(self.expected_categories),
            "expects_risk": self.expects_risk,
            "relation": self.relation,
            "expected_relations": list(self.expected_relations),
            "expected_verdict": self.expected_verdict,
            "claims": [
                {"speaker": c.speaker, "stance": c.stance, "relation": c.relation}
                for c in self.claims
            ],
            "basis": self.basis,
            "origin": self.origin,
            "frozen_phase": self.frozen_phase,
            "note": self.note,
        }


def _case(
    case_id: str,
    group: str,
    subgroup: str,
    text: str,
    categories: Sequence[str],
    basis: str,
    *,
    relation: str = "",
    verdict: str = "",
    speaker: str = "unknown",
    stance: str = "uncertain",
    note: str = "",
    also_relations: Sequence[str] = (),
) -> CapabilityCase:
    """One authored case. `also_relations` are relations the case carries beside
    the one under test - a modal disclosure that also disclaims a guarantee
    carries the GUARANTEE relation too, and saying so keeps relation precision
    honest instead of counting a correct finding as an extra."""

    claims = [
        ClaimLabel(speaker, stance, name) for name in (relation, *also_relations) if name
    ]
    return CapabilityCase(
        case_id=case_id,
        group=group,
        subgroup=subgroup,
        text=text,
        expected_categories=tuple(categories),
        claims=tuple(claims) or (ClaimLabel(speaker, stance),),
        basis=basis,
        relation=relation,
        expected_verdict=verdict,
        note=note,
    )


#: The one stance every author-voice capability case takes. Kept as constants so
#: a case cannot quietly label an author-voice category on an attributed claim.
_AUTHOR = ("author", "endorsed")

#: ---------------------------------------------------------------------------
#: Group A - modal prediction. 30 cases.
#: ---------------------------------------------------------------------------
_MODAL: tuple[CapabilityCase, ...] = (
    # -- A1: author voice, `certain` -> guide section 2 says this IS a prediction
    _case(
        "MP-A1-01", MODAL_PREDICTION, STRONG_PREDICTION,
        "The share price will rise next year.",
        ("market_prediction",), "guide 2: explicit prediction, author, certain",
        relation=PREDICTION, verdict=PREDICTION_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "MP-A1-02", MODAL_PREDICTION, STRONG_PREDICTION,
        "Yields will climb in the coming quarter.",
        ("market_prediction",), "guide 2: explicit prediction, author, certain",
        relation=PREDICTION, verdict=PREDICTION_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "MP-A1-03", MODAL_PREDICTION, STRONG_PREDICTION,
        "The index is going to fall this month.",
        ("market_prediction",), "guide 2: explicit prediction, author, certain",
        relation=PREDICTION, verdict=PREDICTION_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "MP-A1-04", MODAL_PREDICTION, STRONG_PREDICTION,
        "Earnings will double by 2030.",
        ("market_prediction",), "guide 2: explicit prediction, author, certain",
        relation=PREDICTION, verdict=PREDICTION_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "MP-A1-05", MODAL_PREDICTION, STRONG_PREDICTION,
        "The fund's value will recover from here.",
        ("market_prediction",), "guide 2: explicit prediction, author, certain",
        relation=PREDICTION, verdict=PREDICTION_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "MP-A1-06", MODAL_PREDICTION, STRONG_PREDICTION,
        "Turnover will grow over the next two years.",
        ("market_prediction",), "guide 2: explicit prediction, author, certain",
        relation=PREDICTION, verdict=PREDICTION_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "MP-A1-07", MODAL_PREDICTION, STRONG_PREDICTION,
        "The sector is certain to decline next quarter.",
        ("market_prediction",), "guide 1.2: `is certain to` is a certain marker",
        relation=PREDICTION, verdict=PREDICTION_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "MP-A1-08", MODAL_PREDICTION, STRONG_PREDICTION,
        "The share price is bound to reach 500.",
        ("market_prediction",), "guide 2 target price: the article asserts the level",
        relation=PREDICTION, verdict=PREDICTION_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    # -- A2: probable or possible -> guide 2 and 5 say NOT a prediction
    _case(
        "MP-A2-01", MODAL_PREDICTION, WEAK_PREDICTION_GROUP,
        "The index may recover next quarter.",
        (), "guide 1.2: `may` is possible; guide 2 excludes it",
        relation=PREDICTION, verdict=WEAK_PREDICTION,
    ),
    _case(
        "MP-A2-02", MODAL_PREDICTION, WEAK_PREDICTION_GROUP,
        "Yields could double this year.",
        (), "guide 1.2: `could` is possible; guide 2 excludes it",
        relation=PREDICTION, verdict=WEAK_PREDICTION,
    ),
    _case(
        "MP-A2-03", MODAL_PREDICTION, WEAK_PREDICTION_GROUP,
        "The share price is likely to rise.",
        (), "guide 1.2: `likely` is probable; guide 2 excludes it",
        relation=PREDICTION, verdict=WEAK_PREDICTION,
    ),
    _case(
        "MP-A2-04", MODAL_PREDICTION, WEAK_PREDICTION_GROUP,
        "Earnings will probably decline.",
        (), "guide 1.2: the adverb is probable and the adverb is the weaker carrier",
        relation=PREDICTION, verdict=WEAK_PREDICTION,
    ),
    _case(
        "MP-A2-05", MODAL_PREDICTION, WEAK_PREDICTION_GROUP,
        "The fund might outperform its benchmark next year.",
        (), "guide 1.2: `might` is possible; relative performance is directional",
        relation=PREDICTION, verdict=WEAK_PREDICTION,
    ),
    _case(
        "MP-A2-06", MODAL_PREDICTION, WEAK_PREDICTION_GROUP,
        "The valuation is expected to increase.",
        (), "guide 1.2: `expected to` is probable; guide 2 excludes it",
        relation=PREDICTION, verdict=WEAK_PREDICTION,
    ),
    _case(
        "MP-A2-07", MODAL_PREDICTION, WEAK_PREDICTION_GROUP,
        "The payout could grow over the next two years.",
        (), "guide 1.2: `could` is possible; guide 2 excludes it",
        relation=PREDICTION, verdict=WEAK_PREDICTION,
    ),
    _case(
        "MP-A2-08", MODAL_PREDICTION, WEAK_PREDICTION_GROUP,
        "Perhaps the share price will double this year.",
        (), "guide 1.2: the sentence adverb is possible and the weakest carrier wins",
        relation=PREDICTION, verdict=WEAK_PREDICTION,
        note=(
            "the first version of this case read `Perhaps the fund will outperform "
            "its benchmark.`, which is IV-098 verbatim. The contamination audit "
            "caught it before publication and the case was rewritten; both texts and "
            "the finding are recorded in risk_evaluation/v3_1/audit_report_v3_1.json"
        ),
    ),
    # -- A3: disclosure. A modal about a market quantity that names no direction
    _case(
        "MP-A3-01", MODAL_PREDICTION, EDUCATIONAL_UNCERTAINTY,
        "The value of investments may fall as well as rise.",
        (), "guide 5: a symmetric pair asserts no direction",
        verdict=NON_DIRECTIONAL_VERDICT,
    ),
    _case(
        "MP-A3-02", MODAL_PREDICTION, EDUCATIONAL_UNCERTAINTY,
        "Fund values can go down as well as up.",
        (), "guide 5: a symmetric pair asserts no direction",
        verdict=NON_DIRECTIONAL_VERDICT,
    ),
    _case(
        "MP-A3-03", MODAL_PREDICTION, EDUCATIONAL_UNCERTAINTY,
        "Returns may vary depending on market conditions.",
        (), "guide 5: `depending on` is conditional; `vary` names no direction",
        verdict=NON_DIRECTIONAL_VERDICT,
    ),
    _case(
        "MP-A3-04", MODAL_PREDICTION, EDUCATIONAL_UNCERTAINTY,
        "Market conditions may change without notice.",
        (), "guide 2: no market target is named; `change` names no direction",
        verdict="no_market_entity",
    ),
    _case(
        "MP-A3-05", MODAL_PREDICTION, EDUCATIONAL_UNCERTAINTY,
        "The price of units may fluctuate.",
        (), "guide 2: `fluctuate` names no direction, so nothing is predicted",
        verdict=NON_DIRECTIONAL_VERDICT,
    ),
    _case(
        "MP-A3-06", MODAL_PREDICTION, EDUCATIONAL_UNCERTAINTY,
        "Past performance is not a reliable indicator of future results.",
        (), "guide 2: no outcome is asserted",
        verdict="no_modal",
    ),
    _case(
        "MP-A3-07", MODAL_PREDICTION, EDUCATIONAL_UNCERTAINTY,
        "Yields may differ between share classes.",
        (), "guide 2: `differ` names no direction",
        verdict=NON_DIRECTIONAL_VERDICT,
    ),
    _case(
        "MP-A3-08", MODAL_PREDICTION, EDUCATIONAL_UNCERTAINTY,
        "Investment returns are not guaranteed and may go down as well as up.",
        (), "guide 5: a symmetric pair, and guide 7 on the disclaimed guarantee",
        verdict=NON_DIRECTIONAL_VERDICT,
        also_relations=("GUARANTEE",),
        note="the disclaimed guarantee carries the GUARANTEE relation, as IV-081 does",
    ),
    # -- A4: a modal whose complement explains rather than predicts
    _case(
        "MP-A4-01", MODAL_PREDICTION, NON_FINANCIAL_MODAL,
        "The fee may indicate a higher turnover.",
        (), "guide 2: the modal explains, it does not predict",
        verdict=NON_PREDICTION_MODAL,
    ),
    _case(
        "MP-A4-02", MODAL_PREDICTION, NON_FINANCIAL_MODAL,
        "This document may include forward-looking statements.",
        (), "guide 2: the modal explains, it does not predict",
        verdict=NON_PREDICTION_MODAL,
    ),
    _case(
        "MP-A4-03", MODAL_PREDICTION, NON_FINANCIAL_MODAL,
        "The index may refer to a benchmark maintained by the provider.",
        (), "guide 2: the modal explains, it does not predict",
        verdict=NON_PREDICTION_MODAL,
    ),
    _case(
        "MP-A4-04", MODAL_PREDICTION, NON_FINANCIAL_MODAL,
        "Charges may apply to early redemptions.",
        (), "guide 2: the modal explains, it does not predict",
        verdict=NON_PREDICTION_MODAL,
    ),
    _case(
        "MP-A4-05", MODAL_PREDICTION, NON_FINANCIAL_MODAL,
        "The fund's holdings may consist of cash and equivalents.",
        (), "guide 2: the modal explains, it does not predict",
        verdict=NON_PREDICTION_MODAL,
    ),
    _case(
        "MP-A4-06", MODAL_PREDICTION, NON_FINANCIAL_MODAL,
        "The report may reflect estimates rather than actual results.",
        (), "guide 2: the modal explains, it does not predict",
        verdict=NON_PREDICTION_MODAL,
    ),
)

#: ---------------------------------------------------------------------------
#: Group B - advice boundary. 30 cases.
#: ---------------------------------------------------------------------------
_ADVICE: tuple[CapabilityCase, ...] = (
    # -- B1: direct advice, GUIDE 7
    _case(
        "AB-B1-01", ADVICE_BOUNDARY, DIRECT_ADVICE,
        "You should hold this stock.",
        ("investment_advice",), "guide 3.2: an addressed directive with a financial object",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "AB-B1-02", ADVICE_BOUNDARY, DIRECT_ADVICE,
        "Buy this stock today.",
        ("investment_advice",), "guide 7: an imperative aimed at the reader",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "AB-B1-03", ADVICE_BOUNDARY, DIRECT_ADVICE,
        "Investors should allocate more to bonds.",
        ("investment_advice",), "guide 7: an addressed directive with a financial object",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "AB-B1-04", ADVICE_BOUNDARY, DIRECT_ADVICE,
        "Reduce your exposure to the sector.",
        ("investment_advice",), "guide 7: an imperative on a held position",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "AB-B1-05", ADVICE_BOUNDARY, DIRECT_ADVICE,
        "We recommend buying this fund.",
        ("investment_advice",), "guide 7: the author's own recommendation",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "AB-B1-06", ADVICE_BOUNDARY, DIRECT_ADVICE,
        "Avoid this fund until the charges change.",
        ("investment_advice",), "guide 7: an imperative on a specific instrument",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "AB-B1-07", ADVICE_BOUNDARY, DIRECT_ADVICE,
        "You ought to trim your position.",
        ("investment_advice",), "guide 7: `ought to` is constitutive of the directive",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
        note="a Phase 8.8 measured false negative",
    ),
    _case(
        "AB-B1-08", ADVICE_BOUNDARY, DIRECT_ADVICE,
        "Sell these shares now.",
        ("investment_advice",), "guide 7: an imperative aimed at the reader",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    # -- B2: indirect advice
    _case(
        "AB-B2-01", ADVICE_BOUNDARY, INDIRECT_ADVICE,
        "It would be prudent to trim your holdings.",
        ("investment_advice",), "guide 5: a conditional directive is still advice",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
        note="a Phase 8.8 measured false negative",
    ),
    _case(
        "AB-B2-02", ADVICE_BOUNDARY, INDIRECT_ADVICE,
        "A sensible investor would avoid this fund.",
        ("investment_advice",), "guide 5: the condition frames the directive, it does not remove it",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
        note="a Phase 8.8 measured false negative",
    ),
    _case(
        "AB-B2-03", ADVICE_BOUNDARY, INDIRECT_ADVICE,
        "Investors are advised to reduce exposure to the sector.",
        ("investment_advice",), "guide 7: an advisory frame carrying a directive",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "AB-B2-04", ADVICE_BOUNDARY, INDIRECT_ADVICE,
        "The sensible move is to shift into shorter-dated bonds.",
        ("investment_advice",), "guide 7: naming the sensible move is a directive",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    _case(
        "AB-B2-05", ADVICE_BOUNDARY, INDIRECT_ADVICE,
        "Investors would be wise to reduce their holdings.",
        ("investment_advice",), "guide 5: the condition frames the directive, it does not remove it",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
        note="a Phase 8.8 measured false negative",
    ),
    _case(
        "AB-B2-06", ADVICE_BOUNDARY, INDIRECT_ADVICE,
        "We would suggest selling the shares.",
        ("investment_advice",), "guide 7: the author's own recommendation",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
        note="a Phase 8.8 measured false negative",
    ),
    _case(
        "AB-B2-07", ADVICE_BOUNDARY, INDIRECT_ADVICE,
        "Now is the time to buy the dip.",
        ("investment_advice",), "guide 7: an advisory frame with a market object",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
        note="a Phase 8.8 measured false negative",
    ),
    _case(
        "AB-B2-08", ADVICE_BOUNDARY, INDIRECT_ADVICE,
        "The obvious choice for a cautious investor is to hold cash instead of this fund.",
        ("investment_advice",), "guide 7: naming the obvious choice is a directive",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker=_AUTHOR[0], stance=_AUTHOR[1],
    ),
    # -- B3: education. Guide 7 makes explanation and method guidance negative.
    _case(
        "AB-B3-01", ADVICE_BOUNDARY, EDUCATION,
        "Holding diversified assets reduces risk.",
        (), "guide 7: educational explanation is negative; the gerund heads a subject",
        verdict=GERUND_SUBJECT,
    ),
    _case(
        "AB-B3-02", ADVICE_BOUNDARY, EDUCATION,
        "To reduce risk, hold a diversified portfolio.",
        (), "guide 7: method guidance is negative",
        verdict=METHOD_GUIDANCE,
        note="a Phase 8.8 measured false positive",
    ),
    _case(
        "AB-B3-03", ADVICE_BOUNDARY, EDUCATION,
        "Investors should hold a diversified portfolio rather than a single stock.",
        (), "guide 7: method guidance is negative, however it is addressed",
        verdict=METHOD_GUIDANCE,
        note="a Phase 8.8 measured false positive",
    ),
    _case(
        "AB-B3-04", ADVICE_BOUNDARY, EDUCATION,
        "Diversification lowers the impact of any single holding.",
        (), "guide 7: educational explanation is negative",
        verdict="no_directive",
    ),
    _case(
        "AB-B3-05", ADVICE_BOUNDARY, EDUCATION,
        "Rebalancing restores a portfolio to its target allocation.",
        (), "guide 7: educational explanation is negative",
        verdict=GERUND_SUBJECT,
    ),
    _case(
        "AB-B3-06", ADVICE_BOUNDARY, EDUCATION,
        "A custodian holds fund assets in safekeeping.",
        (), "guide 7: a statement about a third party is not a directive",
        verdict=THIRD_PERSON_SUBJECT,
        note="a Phase 8.8 measured false positive",
    ),
    _case(
        "AB-B3-07", ADVICE_BOUNDARY, EDUCATION,
        "When rates hold steady, bond fund income is unchanged.",
        (), "guide 7: the verb has a subject, so it is a statement",
        verdict=THIRD_PERSON_SUBJECT,
        note="a Phase 8.8 measured false positive",
    ),
    _case(
        "AB-B3-08", ADVICE_BOUNDARY, EDUCATION,
        "An expense ratio expresses a fund's annual costs as a percentage of assets.",
        (), "guide 7: educational explanation is negative",
        verdict="no_directive",
    ),
    # -- B4: quoted advice. Guide 3.1 and 4 put this on the attribution layer.
    _case(
        "AB-B4-01", ADVICE_BOUNDARY, QUOTED_ADVICE,
        "The regulator said investors should avoid this fund.",
        (), "guide 3.1: a named checkable source is negative",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker="third_party", stance="quoted",
    ),
    _case(
        "AB-B4-02", ADVICE_BOUNDARY, QUOTED_ADVICE,
        "The exchange said traders should reduce their exposure.",
        (), "guide 3.1: a named checkable source is negative",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker="third_party", stance="quoted",
    ),
    _case(
        "AB-B4-03", ADVICE_BOUNDARY, QUOTED_ADVICE,
        "Analysts say investors should buy the dip.",
        ("unverified_information",), "guide 3.1: an uncheckable source is the risk",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker="third_party", stance="quoted",
    ),
    _case(
        "AB-B4-04", ADVICE_BOUNDARY, QUOTED_ADVICE,
        "Insiders say you should buy this stock.",
        ("unverified_information",), "guide 3.2: `Insiders say` is unknown/unverified",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker="third_party", stance="quoted",
    ),
    _case(
        "AB-B4-05", ADVICE_BOUNDARY, QUOTED_ADVICE,
        "An unnamed official said investors should reduce their holdings.",
        ("unverified_information",), "guide 3.1: an uncheckable source is the risk",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker="third_party", stance="quoted",
    ),
    _case(
        "AB-B4-06", ADVICE_BOUNDARY, QUOTED_ADVICE,
        "The advert says investors should buy the fund.",
        (), "guide 7: a checkable advert is negative",
        relation=ADVICE, verdict=ADVICE_VERDICT,
        speaker="third_party", stance="quoted",
    ),
)


def _frozen_cases() -> tuple[CapabilityCase, ...]:
    """Group C, with labels read from the frozen artifacts rather than written here."""

    cases: list[CapabilityCase] = []
    replay_report = replay()
    replay_index = {item.case_id: item for item in replay_report.outcomes}
    phase_86 = phase_86_index()
    phase_85 = {item.case_id: item for item in _phase_85_cases()}

    for phase in sorted(FROZEN_QUOTAS):
        wanted = FROZEN_CASE_IDS[phase]
        if len(wanted) != FROZEN_QUOTAS[phase]:  # pragma: no cover - declaration guard
            raise BenchmarkError(
                f"{phase}: {len(wanted)} ids for a quota of {FROZEN_QUOTAS[phase]}"
            )
        for case_id in wanted:
            if phase == "phase-8.6":
                case = phase_86[case_id]
                cases.append(
                    _from_frozen(
                        case_id,
                        phase,
                        case.text,
                        case.categories,
                        _phase_86_claims(case),
                    )
                )
                continue
            if phase == "phase-8.7":
                source = phase_85.get(case_id) or phase_86.get(case_id)
                if source is None:  # pragma: no cover - declaration guard
                    raise BenchmarkError(f"{phase}: no source case {case_id}")
                categories = getattr(source, "categories", None) or getattr(
                    source, "expected_categories", ()
                )
                cases.append(
                    _from_frozen(
                        case_id,
                        phase,
                        source.text,
                        tuple(categories),
                        _labels_of(source),
                    )
                )
                continue
            outcome = replay_index.get(case_id)
            if outcome is None:  # pragma: no cover - declaration guard
                raise BenchmarkError(f"{phase}: no replay case {case_id}")
            cases.append(
                CapabilityCase(
                    case_id=case_id,
                    group=REGRESSION,
                    subgroup=FROZEN,
                    text=outcome.case.text,
                    expected_categories=tuple(outcome.expected),
                    claims=(
                        ClaimLabel("unknown", "uncertain"),
                    ),
                    basis=f"{phase}: label copied from the frozen source, not re-annotated",
                    origin=outcome.case.origin,
                    frozen_phase=phase,
                    note=outcome.case.note,
                )
            )
    return tuple(cases)


def _labels_of(case) -> tuple[ClaimLabel, ...]:
    labels = []
    for item in getattr(case, "claims", ()):
        speaker = getattr(item, "speaker", "unknown")
        stance = getattr(item, "stance", "uncertain")
        relation = getattr(item, "relation", "")
        labels.append(ClaimLabel(speaker, stance, relation))
    return tuple(labels) or (ClaimLabel("unknown", "uncertain"),)


def _from_frozen(
    case_id: str,
    phase: str,
    text: str,
    categories: Sequence[str],
    labels: Sequence[ClaimLabel],
) -> CapabilityCase:
    return CapabilityCase(
        case_id=case_id,
        group=REGRESSION,
        subgroup=FROZEN,
        text=text,
        expected_categories=tuple(categories),
        claims=tuple(labels),
        basis=f"{phase}: label copied from the frozen source, not re-annotated",
        origin=f"{phase}/frozen",
        frozen_phase=phase,
    )


def _phase_85_cases():
    from ...v3.benchmark.cases import BENCHMARK_CASES

    return BENCHMARK_CASES


def _phase_86_claims(case):
    claims = []
    for item in case.claims:
        claims.append(
            ClaimLabel(item.speaker, item.stance, getattr(item, "relation", ""))
        )
    return tuple(claims)


#: Every case, in group order.
CASES: tuple[CapabilityCase, ...] = (*_MODAL, *_ADVICE, *_frozen_cases())


def case_index() -> Mapping[str, CapabilityCase]:
    return {case.case_id: case for case in CASES}


def group_cases(group: str) -> tuple[CapabilityCase, ...]:
    if group not in GROUP_NAMES:
        raise BenchmarkError(f"unknown group {group!r}")
    return tuple(case for case in CASES if case.group == group)


def subgroup_cases(subgroup: str) -> tuple[CapabilityCase, ...]:
    if subgroup not in SUBGROUP_SIZES:
        raise BenchmarkError(f"unknown subgroup {subgroup!r}")
    return tuple(case for case in CASES if case.subgroup == subgroup)


def group_sizes() -> Mapping[str, int]:
    return {group: len(group_cases(group)) for group in GROUP_NAMES}


def subgroup_sizes() -> Mapping[str, int]:
    return {name: len(subgroup_cases(name)) for name in SUBGROUP_SIZES}


def category_counts(cases: Sequence[CapabilityCase] | None = None) -> Mapping[str, int]:
    active = tuple(cases) if cases is not None else CASES
    counts: dict[str, int] = {}
    for case in active:
        for name in case.expected_categories:
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def relation_counts(cases: Sequence[CapabilityCase] | None = None) -> Mapping[str, int]:
    active = tuple(cases) if cases is not None else CASES
    counts: dict[str, int] = {}
    for case in active:
        for name in case.expected_relations:
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items()))


def verdict_counts(cases: Sequence[CapabilityCase] | None = None) -> Mapping[str, int]:
    active = tuple(cases) if cases is not None else CASES
    counts: dict[str, int] = {}
    for case in active:
        if case.expected_verdict:
            counts[case.expected_verdict] = counts.get(case.expected_verdict, 0) + 1
    return dict(sorted(counts.items()))


def blind_records(cases: Sequence[CapabilityCase] | None = None) -> tuple[dict[str, str], ...]:
    """Id and text only, so the evaluation stage cannot reach a label."""

    active = tuple(cases) if cases is not None else CASES
    return tuple({"id": case.case_id, "text": case.text} for case in active)


def dataset_payload(cases: Sequence[CapabilityCase] | None = None) -> dict[str, Any]:
    active = tuple(cases) if cases is not None else CASES
    return {
        "benchmark": f"{BENCHMARK_ID}/{BENCHMARK_VERSION}",
        "provenance": dict(PROVENANCE),
        "case_count": len(active),
        "groups": dict(group_sizes()),
        "subgroups": dict(subgroup_sizes()),
        "category_counts": dict(category_counts()),
        "relation_counts": dict(relation_counts()),
        "verdict_counts": dict(verdict_counts()),
        "frozen_quotas": dict(FROZEN_QUOTAS),
        "frozen_case_ids": {k: list(v) for k, v in FROZEN_CASE_IDS.items()},
        "cases": [case.as_dict() for case in active],
        "note": (
            "Groups A and B are synthetic and were written by the same author as "
            "the capability they measure; they are not an independence claim. "
            "Group C carries labels copied from frozen artifacts."
        ),
    }


def write_dataset(path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else DATASET_PATH
    target.write_text(
        json.dumps(dataset_payload(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target
