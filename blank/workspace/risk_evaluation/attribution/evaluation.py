"""A 30-case synthetic annotation set, and the attribution metrics.

Phase 8.2 measures **attribution only**. Risk F1 is deliberately not computed
here: this layer does not classify risk, and reporting a risk score for it would
invite exactly the confusion the phase is meant to remove.

Three metrics, matching the phase brief:

    claim split accuracy   did the parser find the right number of claims?
    speaker accuracy       over claims in correctly-split cases
    stance accuracy        over claims in correctly-split cases

Speaker and stance are scored only where the split was right, because comparing
a two-claim prediction against a one-claim annotation position by position
measures nothing. The aligned-claim count is reported alongside, so an accuracy
over three claims cannot be mistaken for an accuracy over thirty cases.

Annotation convention, stated once because stance is otherwise ambiguous: a
segment whose own text performs a rejection (`However, we disagree.`) is
annotated `rejected`, and the claim it targets is also annotated `rejected`. The
two carry the same stance and differ in `speaker`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .analyzer import analyze
from .model import SPEAKERS, STANCES


REPORT_PATH = Path(__file__).resolve().parent / "annotation_report.json"
ANNOTATION_SET_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class AnnotationRow:
    """One annotated text: what the claims are, and who says each one."""

    case_id: str
    text: str
    speakers: tuple[str, ...]
    stances: tuple[str, ...]
    note: str = ""

    def __post_init__(self) -> None:
        if len(self.speakers) != len(self.stances):
            raise ValueError(
                f"{self.case_id}: {len(self.speakers)} speakers but "
                f"{len(self.stances)} stances"
            )
        if not self.speakers:
            raise ValueError(f"{self.case_id}: at least one claim is required")
        for name in self.speakers:
            if name not in SPEAKERS:
                raise ValueError(f"{self.case_id}: bad speaker {name!r}")
        for name in self.stances:
            if name not in STANCES:
                raise ValueError(f"{self.case_id}: bad stance {name!r}")

    @property
    def claim_count(self) -> int:
        return len(self.speakers)


def _row(
    case_id: str,
    text: str,
    speakers: Sequence[str],
    stances: Sequence[str],
    note: str = "",
) -> AnnotationRow:
    return AnnotationRow(case_id, text, tuple(speakers), tuple(stances), note)


#: 30 synthetic cases. Written against the definitions in the phase brief, not
#: against the implementation: the point of measuring is to find out where the
#: rules fall short, which they cannot do if the expectations were read back off
#: the code.
ANNOTATION_CASES: tuple[AnnotationRow, ...] = (
    # -- third-party speakers -------------------------------------------
    _row("AT-001", "Analysts said the stock will rise.", ["third_party"], ["quoted"], "named collective, reporting verb"),
    _row("AT-002", "Experts predict growth next year.", ["third_party"], ["quoted"], "reporting verb"),
    _row("AT-003", "Researchers say the effect is small.", ["third_party"], ["quoted"], "reporting verb"),
    _row("AT-004", "According to analysts, the outlook has improved.", ["third_party"], ["quoted"], "attribution phrase"),
    _row("AT-005", "Reports say the merger will complete.", ["third_party"], ["quoted"], "'reports say'"),
    _row("AT-006", "Some investors believe the rally will continue.", ["third_party"], ["quoted"], "'some investors'"),
    _row("AT-007", "Management expects margins to recover.", ["third_party"], ["quoted"], "corporate speaker"),
    # -- author speakers -------------------------------------------------
    _row("AT-008", "I think the stock is cheap.", ["author"], ["endorsed"], "'I think'"),
    _row("AT-009", "We believe the fund is well managed.", ["author"], ["endorsed"], "'we believe'"),
    _row("AT-010", "Our analysis shows revenue is durable.", ["author"], ["endorsed"], "'our analysis'"),
    _row("AT-011", "This article argues the fee is too high.", ["author"], ["endorsed"], "'this article argues'"),
    _row("AT-012", "We expect the sector to recover.", ["author"], ["endorsed"], "first person plus reporting verb"),
    _row("AT-013", "In our view the valuation is stretched.", ["author"], ["endorsed"], "'in our view'"),
    _row("AT-014", "Our research shows the effect is small.", ["author"], ["endorsed"], "'our research'"),
    # -- no speaker marker -----------------------------------------------
    _row("AT-015", "The quarter closed in March.", ["unknown"], ["uncertain"], "no attribution marker at all"),
    _row("AT-016", "Revenue rose four percent.", ["unknown"], ["uncertain"], "no attribution marker"),
    _row("AT-017", "Costs were flat over the period.", ["unknown"], ["uncertain"], "no attribution marker"),
    _row("AT-018", "The filing runs to forty pages.", ["unknown"], ["uncertain"], "no attribution marker"),
    # -- stance: quoted ---------------------------------------------------
    _row("AT-019", "Analysts say the dividend will be cut.", ["third_party"], ["quoted"], "quoted, no author attitude"),
    _row("AT-020", 'The report said "the outlook is improving".', ["third_party"], ["quoted"], "quotation marks plus reporting verb"),
    _row("AT-021", "Economists forecast slower growth.", ["third_party"], ["quoted"], "forecast frame"),
    # -- stance: endorsed -------------------------------------------------
    _row("AT-022", "Experts say the rally will continue, and we agree.", ["third_party"], ["endorsed"], "author takes up a third party's claim"),
    _row("AT-023", "Analysts expect growth, and this is correct.", ["third_party"], ["endorsed"], "'this is correct'"),
    _row("AT-024", "We believe the risk is contained.", ["author"], ["endorsed"], "author's own claim"),
    _row("AT-025", "Analysts expect higher margins, and indeed this is correct.", ["third_party"], ["endorsed"], "'indeed'"),
    # -- stance: rejected, and multi-claim splits -------------------------
    _row("AT-026", "Analysts believe the stock will rise. However, we disagree.", ["third_party", "author"], ["rejected", "rejected"], "contrastive lead rejects the previous claim"),
    _row("AT-027", "Experts predict growth. However, we are not convinced.", ["third_party", "author"], ["rejected", "rejected"], "rejection frame"),
    _row("AT-028", "Analysts expect a rebound. But evidence shows otherwise.", ["third_party", "author"], ["rejected", "rejected"], "rejection without a first-person marker"),
    _row("AT-029", "Analysts forecast a slowdown. However, this is misleading.", ["third_party", "author"], ["rejected", "rejected"], "'is misleading'"),
    _row("AT-030", "Experts predict growth. Yet we doubt the forecast.", ["third_party", "author"], ["rejected", "rejected"], "'we doubt'"),
)


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case_id: str
    text: str
    expected_speakers: tuple[str, ...]
    expected_stances: tuple[str, ...]
    predicted_speakers: tuple[str, ...]
    predicted_stances: tuple[str, ...]
    split_ok: bool
    note: str = ""

    @property
    def speaker_ok(self) -> tuple[bool, ...]:
        if not self.split_ok:
            return ()
        return tuple(
            a == b for a, b in zip(self.expected_speakers, self.predicted_speakers)
        )

    @property
    def stance_ok(self) -> tuple[bool, ...]:
        if not self.split_ok:
            return ()
        return tuple(
            a == b for a, b in zip(self.expected_stances, self.predicted_stances)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "text": self.text,
            "expected_speakers": list(self.expected_speakers),
            "expected_stances": list(self.expected_stances),
            "predicted_speakers": list(self.predicted_speakers),
            "predicted_stances": list(self.predicted_stances),
            "split_ok": self.split_ok,
            "speaker_ok": list(self.speaker_ok),
            "stance_ok": list(self.stance_ok),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class AttributionMetrics:
    outcomes: tuple[CaseOutcome, ...]
    speakers: tuple[str, ...] = SPEAKERS
    stances: tuple[str, ...] = STANCES

    @property
    def cases(self) -> int:
        return len(self.outcomes)

    @property
    def expected_claims(self) -> int:
        return sum(len(item.expected_speakers) for item in self.outcomes)

    @property
    def predicted_claims(self) -> int:
        return sum(len(item.predicted_speakers) for item in self.outcomes)

    @property
    def split_correct(self) -> int:
        return sum(1 for item in self.outcomes if item.split_ok)

    @property
    def split_accuracy(self) -> float:
        return _ratio(self.split_correct, self.cases)

    @property
    def aligned_claims(self) -> int:
        """Claims that could be compared: those in correctly split cases."""

        return sum(len(item.expected_speakers) for item in self.outcomes if item.split_ok)

    @property
    def speaker_correct(self) -> int:
        return sum(sum(item.speaker_ok) for item in self.outcomes)

    @property
    def stance_correct(self) -> int:
        return sum(sum(item.stance_ok) for item in self.outcomes)

    @property
    def speaker_accuracy(self) -> float:
        return _ratio(self.speaker_correct, self.aligned_claims)

    @property
    def stance_accuracy(self) -> float:
        return _ratio(self.stance_correct, self.aligned_claims)

    @property
    def pair_correct(self) -> int:
        return sum(
            sum(1 for s, t in zip(item.speaker_ok, item.stance_ok) if s and t)
            for item in self.outcomes
        )

    @property
    def pair_accuracy(self) -> float:
        return _ratio(self.pair_correct, self.aligned_claims)

    def per_speaker(self) -> Mapping[str, Mapping[str, float | int]]:
        return self._per_label(
            expected=lambda item: item.expected_speakers,
            correct=lambda item: item.speaker_ok,
            labels=self.speakers,
        )

    def per_stance(self) -> Mapping[str, Mapping[str, float | int]]:
        return self._per_label(
            expected=lambda item: item.expected_stances,
            correct=lambda item: item.stance_ok,
            labels=self.stances,
        )

    def _per_label(self, *, expected, correct, labels) -> Mapping[str, Mapping[str, float | int]]:
        totals = {name: 0 for name in labels}
        hits = {name: 0 for name in labels}
        for item in self.outcomes:
            for want, ok in zip(expected(item), correct(item)):
                totals[want] += 1
                hits[want] += int(ok)
        return {
            name: {
                "expected": totals[name],
                "correct": hits[name],
                "accuracy": _ratio(hits[name], totals[name]),
            }
            for name in labels
        }

    def split_errors(self) -> tuple[CaseOutcome, ...]:
        return tuple(item for item in self.outcomes if not item.split_ok)

    def label_errors(self) -> tuple[CaseOutcome, ...]:
        return tuple(
            item
            for item in self.outcomes
            if item.split_ok
            and not (all(item.speaker_ok) and all(item.stance_ok))
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "annotation_set_version": ANNOTATION_SET_VERSION,
            "cases": self.cases,
            "expected_claims": self.expected_claims,
            "predicted_claims": self.predicted_claims,
            "split_correct": self.split_correct,
            "split_accuracy": self.split_accuracy,
            "aligned_claims": self.aligned_claims,
            "speaker_correct": self.speaker_correct,
            "speaker_accuracy": self.speaker_accuracy,
            "stance_correct": self.stance_correct,
            "stance_accuracy": self.stance_accuracy,
            "pair_correct": self.pair_correct,
            "pair_accuracy": self.pair_accuracy,
            "per_speaker": {k: dict(v) for k, v in self.per_speaker().items()},
            "per_stance": {k: dict(v) for k, v in self.per_stance().items()},
            "split_error_cases": [item.case_id for item in self.split_errors()],
            "label_error_cases": [item.case_id for item in self.label_errors()],
        }

    def render(self) -> str:
        lines = [
            f"annotation set   : {ANNOTATION_SET_VERSION}",
            f"cases            : {self.cases}",
            f"claims expected  : {self.expected_claims}  predicted: {self.predicted_claims}",
            "",
            f"claim split accuracy : {self.split_accuracy:.1%}  ({self.split_correct}/{self.cases})",
            f"speaker accuracy     : {self.speaker_accuracy:.1%}  ({self.speaker_correct}/{self.aligned_claims} aligned claims)",
            f"stance accuracy      : {self.stance_accuracy:.1%}  ({self.stance_correct}/{self.aligned_claims} aligned claims)",
            f"speaker+stance both  : {self.pair_accuracy:.1%}  ({self.pair_correct}/{self.aligned_claims})",
        ]
        lines.append("")
        lines.append("per speaker:")
        for name, bucket in self.per_speaker().items():
            lines.append(
                f"  {name:12} {bucket['correct']}/{bucket['expected']}  "
                f"{bucket['accuracy']:.1%}"
            )
        lines.append("per stance:")
        for name, bucket in self.per_stance().items():
            lines.append(
                f"  {name:12} {bucket['correct']}/{bucket['expected']}  "
                f"{bucket['accuracy']:.1%}"
            )
        if self.split_errors():
            lines.append("")
            lines.append("split errors:")
            for item in self.split_errors():
                lines.append(
                    f"  {item.case_id}: expected {len(item.expected_speakers)} "
                    f"claim(s), got {len(item.predicted_speakers)}"
                )
        if self.label_errors():
            lines.append("")
            lines.append("label errors:")
            for item in self.label_errors():
                lines.append(
                    f"  {item.case_id}: expected "
                    f"{list(zip(item.expected_speakers, item.expected_stances))} "
                    f"got {list(zip(item.predicted_speakers, item.predicted_stances))}"
                )
        return "\n".join(lines)


def _ratio(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


#: A stress set, reported **separately** from the 30-case metric and never
#: folded into it. Expectations come from the same definitions, but every case
#: here carries an attribution shape the rule table has no phrase for: passive
#: attribution, unnamed speakers, nested quotation, Chinese hedging, and
#: disagreement phrased without the listed rejection cues.
#:
#: It is not a held-out set. It was written after the rules, by the same author,
#: so it measures where the boundary is rather than how well the layer
#: generalises. Reporting the 30-case figure alone would be misleading; this is
#: the number that keeps it honest.
COVERAGE_PROBES: tuple[AnnotationRow, ...] = (
    _row("PR-001", "Some say the rally is over.", ["third_party"], ["quoted"], "unnamed plural speaker"),
    _row("PR-002", "It is widely believed that rates will fall.", ["third_party"], ["quoted"], "passive attribution"),
    _row("PR-003", "There is a view that the fund is overpriced.", ["third_party"], ["quoted"], "nominalised attribution"),
    _row("PR-004", "According to the analysts, the market will rise.", ["third_party"], ["quoted"], "attribution phrase, no reporting verb"),
    _row("PR-005", "Management expects margins to recover, but we remain unconvinced.", ["third_party", "author"], ["rejected", "rejected"], "disagreement outside the cue list"),
    _row("PR-006", "Experts predict growth; we are not so sure.", ["third_party", "author"], ["rejected", "rejected"], "hedged disagreement"),
    _row("PR-007", "The report claims the fund never loses money. We have found no evidence for this.", ["third_party", "author"], ["rejected", "rejected"], "evidence-based rejection"),
    _row("PR-008", 'Analysts expect growth. "But we disagree," she wrote.', ["third_party", "author"], ["rejected", "rejected"], "rejection inside a quotation"),
    _row("PR-009", "\u636e\u5206\u6790\u5e08\u79f0\uff0c\u8be5\u57fa\u91d1\u4e0d\u4f1a\u4e8f\u635f\u3002", ["third_party"], ["quoted"], "Chinese attribution"),
    _row("PR-010", "\u6211\u4eec\u8ba4\u4e3a\u5e02\u573a\u5c06\u4e0a\u6da8\u3002", ["author"], ["endorsed"], "Chinese first person"),
    _row("PR-011", "Analysts said the stock would rise. However, the opposite happened.", ["third_party", "author"], ["rejected", "rejected"], "rejection by outcome, not by cue"),
    _row("PR-012", "We agree with analysts that the risk is contained.", ["author"], ["endorsed"], "agreement stated before the attribution"),
)


def run_case(row: AnnotationRow) -> CaseOutcome:
    result = analyze(row.text)
    return CaseOutcome(
        case_id=row.case_id,
        text=row.text,
        expected_speakers=row.speakers,
        expected_stances=row.stances,
        predicted_speakers=tuple(claim.speaker for claim in result.claims),
        predicted_stances=tuple(claim.stance for claim in result.claims),
        split_ok=len(result.claims) == row.claim_count,
        note=row.note,
    )


def evaluate_attribution(
    cases: Sequence[AnnotationRow] | None = None,
) -> AttributionMetrics:
    """Score the attribution layer on the annotation set."""

    active = cases if cases is not None else ANNOTATION_CASES
    return AttributionMetrics(outcomes=tuple(run_case(row) for row in active))


def probe_coverage(
    cases: Sequence[AnnotationRow] | None = None,
) -> AttributionMetrics:
    """Score the boundary stress set. Kept out of the headline metric."""

    active = cases if cases is not None else COVERAGE_PROBES
    return AttributionMetrics(outcomes=tuple(run_case(row) for row in active))


def write_report(
    path: str | Path | None = None,
    metrics: AttributionMetrics | None = None,
) -> Path:
    """Persist the metrics and the per-case outcomes."""

    target = Path(path) if path is not None else REPORT_PATH
    active = metrics if metrics is not None else evaluate_attribution()
    coverage = probe_coverage()
    payload = {
        **active.as_dict(),
        "annotation_set": "main",
        "coverage_probe": coverage.as_dict(),
        "cases_detail": [item.as_dict() for item in active.outcomes],
        "coverage_detail": [item.as_dict() for item in coverage.outcomes],
        "note": (
            "The 30-case metric and the coverage probe are reported separately. "
            "The probe was written after the rules and is a boundary stress set, "
            "not a held-out estimate."
        ),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    metrics = evaluate_attribution()
    print(metrics.render())
    print()
    print("=== coverage probe (boundary stress set, not held out) ===")
    print(probe_coverage().render())
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_report(metrics=metrics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
