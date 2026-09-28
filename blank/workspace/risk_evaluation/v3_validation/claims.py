"""Verifying Phase 8.5's specific claims on independent data.

The phase is explicit that this is not about the overall score. Three claims
Phase 8.5 made are checked one at a time, and each returns a verdict rather than
a number:

    SUPPORTED            holds on the independent benchmark
    PARTIALLY_SUPPORTED  holds for some of what was claimed
    NOT_SUPPORTED        does not hold

A verdict is derived from counts, and every claim reports the cases behind it,
so a reader can disagree with the threshold and see the same evidence.

The three claims:

1. **Attribution** still resolves quoted risk and author rejection.
2. **Intent patterns** still resolve passive, copular and nominal guarantees.
3. **The decision policy** keeps false positives and false negatives low.

Claim 2 is checked by the frame kind the matcher actually reported, not by a
hand-written tag: for each guarantee case the trace says which frame fired, and
the claim is settled on that.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..v3.patterns import PATTERNS
from ..intent_patterns.matcher import RelationMatcher
from .cases import THIRD_PARTY_CLAIM, AUTHOR_REJECTION, ValidationCase
from .evaluation import CaseOutcome, ValidationMetrics

CLAIMS_PATH = Path(__file__).resolve().parent / "claim_verification.json"

SUPPORTED = "SUPPORTED"
PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
NOT_SUPPORTED = "NOT_SUPPORTED"

VERDICTS = (SUPPORTED, PARTIALLY_SUPPORTED, NOT_SUPPORTED)

#: A sub-claim is called supported at or above this rate.
SUPPORT_THRESHOLD = 0.75

GUARANTEE_FRAMES = ("passive", "copular", "nominal", "attributive", "active")


@dataclass(frozen=True, slots=True)
class SubClaim:
    name: str
    correct: int
    total: int
    verdict: str
    case_ids: tuple[str, ...] = ()
    failures: tuple[str, ...] = ()

    @property
    def rate(self) -> float:
        return round(self.correct / self.total, 4) if self.total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "correct": self.correct,
            "total": self.total,
            "rate": self.rate,
            "verdict": self.verdict,
            "failures": list(self.failures),
        }


@dataclass(frozen=True, slots=True)
class ClaimVerdict:
    claim: str
    verdict: str
    sub_claims: tuple[SubClaim, ...]
    summary: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "verdict": self.verdict,
            "summary": self.summary,
            "sub_claims": [s.as_dict() for s in self.sub_claims],
        }

    def render(self) -> str:
        lines = [f"{self.verdict}: {self.claim}", f"    {self.summary}"]
        for item in self.sub_claims:
            lines.append(
                f"    - {item.name:32} {item.correct}/{item.total} "
                f"({item.rate:.1%}) {item.verdict}"
            )
            for failure in item.failures:
                lines.append(f"        failure: {failure}")
        return "\n".join(lines)


def _verdict(correct: int, total: int, *, threshold: float = SUPPORT_THRESHOLD) -> str:
    if not total:
        return NOT_SUPPORTED
    rate = correct / total
    if rate >= threshold:
        return SUPPORTED
    if rate > 0:
        return PARTIALLY_SUPPORTED
    return NOT_SUPPORTED


def _sub(
    name: str, outcomes: Sequence[CaseOutcome], *, threshold: float = SUPPORT_THRESHOLD
) -> SubClaim:
    correct = sum(1 for item in outcomes if item.correct)
    total = len(outcomes)
    return SubClaim(
        name=name,
        correct=correct,
        total=total,
        verdict=_verdict(correct, total, threshold=threshold),
        case_ids=tuple(item.case_id for item in outcomes),
        failures=tuple(item.case_id for item in outcomes if not item.correct),
    )


def quoted_risk_outcomes(outcomes: Sequence[CaseOutcome]) -> tuple[CaseOutcome, ...]:
    return tuple(item for item in outcomes if item.case.group == THIRD_PARTY_CLAIM)


def rejection_outcomes(outcomes: Sequence[CaseOutcome]) -> tuple[CaseOutcome, ...]:
    return tuple(item for item in outcomes if item.case.group == AUTHOR_REJECTION)


def attribute_in_group(outcomes: Sequence[CaseOutcome], group: str) -> tuple[CaseOutcome, ...]:
    return tuple(item for item in outcomes if item.case.group == group)


def frame_kinds_for(case: ValidationCase) -> tuple[str, ...]:
    """Which GUARANTEE frames the matcher reports for a case's text.

    Run directly rather than read from the prediction, so the claim is settled
    on what the pattern layer does with the text rather than on what the
    pipeline happened to decide.
    """

    matcher = RelationMatcher(PATTERNS)
    kinds: list[str] = []
    for match in matcher.match(case.text):
        for frame in match.frames:
            if frame.relation in ("GUARANTEE", "RISK_REMOVED"):
                kinds.append(frame.kind)
    return tuple(dict.fromkeys(kinds))


def guarantee_form_outcomes(
    outcomes: Sequence[CaseOutcome],
) -> Mapping[str, tuple[CaseOutcome, ...]]:
    """Guarantee cases grouped by the frame kind their text realises."""

    buckets: dict[str, list[CaseOutcome]] = {kind: [] for kind in GUARANTEE_FRAMES}
    for item in outcomes:
        if not (set(item.case.expected_relations) & {"GUARANTEE", "RISK_REMOVED"}):
            continue
        kinds = frame_kinds_for(item.case)
        if not kinds:
            buckets.setdefault("unmatched", []).append(item)
            continue
        for kind in kinds:
            buckets.setdefault(kind, []).append(item)
    return {name: tuple(items) for name, items in buckets.items() if items}


def verify_attribution(metrics: ValidationMetrics) -> ClaimVerdict:
    outcomes = metrics.outcomes
    quoted = _sub("quoted third-party claims decided correctly", quoted_risk_outcomes(outcomes))
    rejected = _sub("author rejections decided correctly", rejection_outcomes(outcomes))
    speaker = SubClaim(
        name="speaker accuracy on aligned claims",
        correct=metrics.attribution.speaker_correct,
        total=metrics.attribution.aligned_claims,
        verdict=_verdict(
            metrics.attribution.speaker_correct, metrics.attribution.aligned_claims
        ),
        failures=tuple(item.case_id for item in metrics.attribution.errors()),
    )
    stance = SubClaim(
        name="stance accuracy on aligned claims",
        correct=metrics.attribution.stance_correct,
        total=metrics.attribution.aligned_claims,
        verdict=_verdict(
            metrics.attribution.stance_correct, metrics.attribution.aligned_claims
        ),
        failures=tuple(item.case_id for item in metrics.attribution.errors()),
    )
    subs = (quoted, rejected, speaker, stance)
    if all(s.verdict == SUPPORTED for s in subs):
        verdict = SUPPORTED
    elif any(s.verdict == NOT_SUPPORTED for s in subs):
        verdict = NOT_SUPPORTED
    else:
        verdict = PARTIALLY_SUPPORTED
    return ClaimVerdict(
        claim=(
            "Phase 8.5 claim 1: the attribution layer still resolves quoted risk "
            "and author rejection"
        ),
        verdict=verdict,
        sub_claims=subs,
        summary=(
            f"quoted {quoted.correct}/{quoted.total}, rejected {rejected.correct}/"
            f"{rejected.total}, speaker {speaker.rate:.1%}, stance {stance.rate:.1%}"
        ),
    )


def verify_intent(metrics: ValidationMetrics) -> ClaimVerdict:
    outcomes = metrics.outcomes
    by_form = guarantee_form_outcomes(outcomes)
    subs: list[SubClaim] = []
    for kind in GUARANTEE_FRAMES:
        items = by_form.get(kind, ())
        if items:
            subs.append(_sub(f"{kind} guarantee", items))
    unmatched = by_form.get("unmatched", ())
    if unmatched:
        subs.append(
            SubClaim(
                name="guarantee text no frame matched",
                correct=0,
                total=len(unmatched),
                verdict=NOT_SUPPORTED,
                failures=tuple(item.case_id for item in unmatched),
            )
        )
    subs.append(
        SubClaim(
            name="per-relation recall",
            correct=metrics.intent.recalled,
            total=metrics.intent.expected_total,
            verdict=_verdict(metrics.intent.recalled, metrics.intent.expected_total),
            failures=tuple(item.case_id for item in metrics.intent.misses()),
        )
    )
    if all(s.verdict == SUPPORTED for s in subs):
        verdict = SUPPORTED
    elif any(s.verdict == NOT_SUPPORTED for s in subs):
        verdict = NOT_SUPPORTED
    else:
        verdict = PARTIALLY_SUPPORTED
    return ClaimVerdict(
        claim=(
            "Phase 8.5 claim 2: the intent patterns still resolve passive, "
            "copular and nominal guarantees"
        ),
        verdict=verdict,
        sub_claims=tuple(subs),
        summary="; ".join(f"{s.name} {s.correct}/{s.total}" for s in subs),
    )


def verify_decision(metrics: ValidationMetrics) -> ClaimVerdict:
    decision = metrics.decision
    subs = (
        SubClaim(
            name="false positive rate",
            correct=decision.counts["tn"],
            total=decision.counts["tn"] + decision.counts["fp"],
            verdict=(
                SUPPORTED
                if decision.false_positive_rate <= 0.2
                else PARTIALLY_SUPPORTED
                if decision.false_positive_rate <= 0.35
                else NOT_SUPPORTED
            ),
            failures=tuple(
                item.case_id for item in decision.errors() if item.outcome == "fp"
            ),
        ),
        SubClaim(
            name="false negative rate",
            correct=decision.counts["tp"],
            total=decision.counts["tp"] + decision.counts["fn"],
            verdict=(
                SUPPORTED
                if decision.false_negative_rate <= 0.2
                else PARTIALLY_SUPPORTED
                if decision.false_negative_rate <= 0.35
                else NOT_SUPPORTED
            ),
            failures=tuple(
                item.case_id for item in decision.errors() if item.outcome == "fn"
            ),
        ),
        SubClaim(
            name="precision",
            correct=decision.counts["tp"],
            total=decision.counts["tp"] + decision.counts["fp"],
            verdict=_verdict(decision.counts["tp"], decision.counts["tp"] + decision.counts["fp"]),
        ),
        SubClaim(
            name="recall",
            correct=decision.counts["tp"],
            total=decision.counts["tp"] + decision.counts["fn"],
            verdict=_verdict(decision.counts["tp"], decision.counts["tp"] + decision.counts["fn"]),
        ),
    )
    verdicts = {s.verdict for s in subs}
    verdict = (
        SUPPORTED
        if verdicts == {SUPPORTED}
        else NOT_SUPPORTED
        if NOT_SUPPORTED in verdicts
        else PARTIALLY_SUPPORTED
    )
    return ClaimVerdict(
        claim=(
            "Phase 8.5 claim 3: the decision policy keeps false positives and "
            "false negatives low"
        ),
        verdict=verdict,
        sub_claims=subs,
        summary=(
            f"fpr {decision.false_positive_rate:.4f}, fnr "
            f"{decision.false_negative_rate:.4f}, precision {decision.precision:.4f}, "
            f"recall {decision.recall:.4f}"
        ),
    )


def verify_claims(metrics: ValidationMetrics) -> tuple[ClaimVerdict, ...]:
    return (
        verify_attribution(metrics),
        verify_intent(metrics),
        verify_decision(metrics),
    )


def payload(metrics: ValidationMetrics) -> dict[str, Any]:
    verdicts = verify_claims(metrics)
    return {
        "benchmark": "independent_v1",
        "threshold": SUPPORT_THRESHOLD,
        "claims": [item.as_dict() for item in verdicts],
        "summary": {item.claim: item.verdict for item in verdicts},
        "note": (
            "Each claim is settled on counts, and every claim reports the cases "
            "behind it so a reader can disagree with the threshold and see the "
            "same evidence."
        ),
    }


def write_report(path: str | Path | None = None) -> Path:
    from .cases import blind_records
    from .evaluation import predict, score

    target = Path(path) if path is not None else CLAIMS_PATH
    metrics = score(predict(blind_records()))
    target.write_text(
        json.dumps(payload(metrics), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    from .cases import blind_records
    from .evaluation import predict, score

    metrics = score(predict(blind_records()))
    for item in verify_claims(metrics):
        print(item.render())
        print()
    if "--write" in sys.argv:
        print(f"wrote {write_report()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
