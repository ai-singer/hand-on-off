"""The Phase 8.7 regression suite: five sets, before and after, fixed and broken.

The phase requires a frozen regression over the historical sets that reports
before, after, fixed **and broken**. Reporting only the improvements is the
failure mode the requirement exists to prevent, so `broken` is a first-class
field and the suite's own test asserts it is empty rather than merely printing it.

Five sets, and they are not the same kind of thing:

    phase 8.1   the adversarial failure repository's recorded misses
    phase 8.3   the attribution experiment's replay cases
    phase 8.4   the intent pattern benchmark's guarantee positives
    phase 8.5   the composition benchmark, 60 cases with hand labels
    phase 8.6   the independent benchmark's clean 99-case subset

Each case is scored three ways:

    expected     what the annotation says
    baseline     semantic_evaluator_v2 on the whole text - the "before" the
                 earlier phases reported
    v3           the pipeline as it stands now - the "after"
    pre_repair   the pipeline as it stood before Phase 8.7

`pre_repair` is read from `regression_baseline.json`, which was produced by
running this same harness against the unmodified commit before any Phase 8.7
change was made. Without it, `fixed` and `broken` could only be measured against
the v2 baseline, which would credit Phase 8.7 for what Phase 8.5 and 8.6 already
did - and, worse, could not see a repair that broke a case v3 previously got
right. That second comparison is the one this suite exists for.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..v3.benchmark.metrics import evaluate_benchmark
from ..v3.replay import PHASE_81, PHASE_83, PHASE_84, replay
from ..v3_validation.cases import decontaminated_cases
from ..v3_validation.evaluation import predict, score

BASELINE_PATH = Path(__file__).resolve().parent / "regression_baseline.json"
REPORT_PATH = Path(__file__).resolve().parent / "regression_report_v3_repair.json"

PHASE_85 = "phase_8.5"
PHASE_86 = "phase_8.6_independent_v2"

#: The five sets, in the order the phase lists them.
SET_NAMES: tuple[str, ...] = (
    "phase_8.1",
    "phase_8.3",
    "phase_8.4",
    PHASE_85,
    PHASE_86,
)

#: Transitions. `unchanged` covers both "right before and after" and "wrong
#: before and after"; the second is `still_wrong`, because a defect that survived
#: a repair is not the same finding as a case that was always right.
FIXED = "fixed"
BROKEN = "broken"
UNCHANGED = "unchanged"
STILL_WRONG = "still_wrong"

TRANSITIONS: tuple[str, ...] = (UNCHANGED, FIXED, BROKEN, STILL_WRONG)


class RegressionError(Exception):
    """Raised when the regression cannot be run or compared."""


def _transition(correct_before: bool, correct_after: bool) -> str:
    if correct_before and correct_after:
        return UNCHANGED
    if not correct_before and correct_after:
        return FIXED
    if correct_before and not correct_after:
        return BROKEN
    return STILL_WRONG


@dataclass(frozen=True, slots=True)
class CaseRecord:
    """One case, measured against expectation, baseline and the pre-repair v3."""

    set_name: str
    case_id: str
    text: str
    expected: tuple[str, ...]
    baseline: tuple[str, ...]
    v3: tuple[str, ...]
    pre_repair: tuple[str, ...] | None = None

    @property
    def case_matches(self) -> bool:
        return self.v3 == self.expected

    @property
    def baseline_matches(self) -> bool:
        return self.baseline == self.expected

    @property
    def pre_repair_matches(self) -> bool | None:
        if self.pre_repair is None:
            return None
        return self.pre_repair == self.expected

    @property
    def transition_vs_baseline(self) -> str:
        return _transition(self.baseline_matches, self.case_matches)

    @property
    def transition(self) -> str:
        """Fixed or broken, measured against the pre-repair pipeline."""

        before = self.pre_repair_matches
        if before is None:
            return self.transition_vs_baseline
        return _transition(before, self.case_matches)

    @property
    def flagged(self) -> bool:
        return bool(self.v3)

    @property
    def expected_flagged(self) -> bool:
        return bool(self.expected)

    def as_dict(self) -> dict[str, Any]:
        return {
            "set": self.set_name,
            "case_id": self.case_id,
            "text": self.text,
            "expected": list(self.expected),
            "baseline": list(self.baseline),
            "v3": list(self.v3),
            "pre_repair": list(self.pre_repair) if self.pre_repair is not None else None,
            "outcome": (
                "tp"
                if self.expected_flagged and self.flagged
                else "fp"
                if not self.expected_flagged and self.flagged
                else "fn"
                if self.expected_flagged and not self.flagged
                else "tn"
            ),
            "correct": self.case_matches,
            "baseline_correct": self.baseline_matches,
            "pre_repair_correct": self.pre_repair_matches,
            "transition": self.transition,
            "transition_vs_baseline": self.transition_vs_baseline,
        }


def load_baseline(path: str | Path | None = None) -> Mapping[str, Sequence[Mapping]]:
    """The recorded pre-repair results, per set.

    The file carries a `provenance` block naming the commit it was taken on and
    the harness that produced it, and a `sets` mapping of the records. Returning
    `sets` rather than the whole file keeps the provenance out of the comparison
    without hiding it from a reader.
    """

    target = Path(path) if path is not None else BASELINE_PATH
    if not target.is_file():
        raise RegressionError(f"no pre-repair baseline at {target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    if "sets" not in payload:
        raise RegressionError(f"{target} has no `sets` mapping")
    return payload["sets"]


def baseline_provenance(path: str | Path | None = None) -> Mapping[str, Any]:
    target = Path(path) if path is not None else BASELINE_PATH
    payload = json.loads(target.read_text(encoding="utf-8"))
    return payload.get("provenance", {})


def _from_replay() -> dict[str, list[CaseRecord]]:
    report = replay()
    buckets: dict[str, list[CaseRecord]] = {"phase_8.1": [], "phase_8.3": [], "phase_8.4": []}
    for phase, name in (
        (PHASE_81, "phase_8.1"),
        (PHASE_83, "phase_8.3"),
        (PHASE_84, "phase_8.4"),
    ):
        for item in report.by_phase(phase):
            buckets[name].append(
                CaseRecord(
                    set_name=name,
                    case_id=item.case_id,
                    text=item.case.text,
                    expected=tuple(item.expected),
                    baseline=tuple(item.before),
                    v3=tuple(item.after),
                )
            )
    return buckets


def _from_phase_8_5() -> list[CaseRecord]:
    return [
        CaseRecord(
            set_name=PHASE_85,
            case_id=item.case_id,
            text=item.case.text,
            expected=tuple(item.case.expected_categories),
            baseline=tuple(item.result.baseline),
            v3=tuple(item.result.categories),
        )
        for item in evaluate_benchmark().outcomes
    ]


def _from_phase_8_6() -> list[CaseRecord]:
    cases = decontaminated_cases()
    predictions = predict([{"id": c.case_id, "text": c.text} for c in cases])
    return [
        CaseRecord(
            set_name=PHASE_86,
            case_id=item.case_id,
            text=item.case.text,
            expected=tuple(item.case.categories),
            baseline=tuple(item.prediction.baseline),
            v3=tuple(item.prediction.categories),
        )
        for item in score(predictions, cases).outcomes
    ]


def run(
    *,
    baseline: Mapping[str, Sequence[Mapping]] | None = None,
    path: str | Path | None = None,
) -> tuple[CaseRecord, ...]:
    """Every case in every set, with the pre-repair result attached where known."""

    recorded = baseline if baseline is not None else load_baseline(path)
    by_set: dict[str, list[CaseRecord]] = {
        "phase_8.1": [],
        "phase_8.3": [],
        "phase_8.4": [],
        PHASE_85: [],
        PHASE_86: [],
    }
    by_set.update(_from_replay())
    by_set[PHASE_85] = _from_phase_8_5()
    by_set[PHASE_86] = _from_phase_8_6()

    index: dict[tuple[str, str], tuple[str, ...]] = {}
    for name, items in recorded.items():
        for item in items:
            index[(name, item["case_id"])] = tuple(item["v3"])

    records: list[CaseRecord] = []
    for name in SET_NAMES:
        for item in by_set[name]:
            records.append(
                CaseRecord(
                    set_name=item.set_name,
                    case_id=item.case_id,
                    text=item.text,
                    expected=item.expected,
                    baseline=item.baseline,
                    v3=item.v3,
                    pre_repair=index.get((name, item.case_id)),
                )
            )
    return tuple(records)


@dataclass(frozen=True, slots=True)
class SetSummary:
    """One set's counts, before and after, with the transitions."""

    set_name: str
    cases: int
    baseline_correct: int
    pre_repair_correct: int
    v3_correct: int
    fixed: tuple[str, ...]
    broken: tuple[str, ...]
    still_wrong: tuple[str, ...]
    #: Cases right before, wrong after, measured against the v2 baseline instead.
    #: Kept because a discrepancy between the two readings is itself a finding.
    broken_vs_baseline: tuple[str, ...]
    false_positives: int
    false_negatives: int

    @property
    def delta_vs_pre_repair(self) -> int:
        return self.v3_correct - self.pre_repair_correct

    def as_dict(self) -> dict[str, Any]:
        return {
            "set_name": self.set_name,
            "cases": self.cases,
            "baseline_correct": self.baseline_correct,
            "pre_repair_correct": self.pre_repair_correct,
            "v3_correct": self.v3_correct,
            "delta": self.delta_vs_pre_repair,
            "fixed": list(self.fixed),
            "fixed_count": len(self.fixed),
            "broken": list(self.broken),
            "broken_count": len(self.broken),
            "still_wrong": list(self.still_wrong),
            "broken_vs_baseline": list(self.broken_vs_baseline),
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
        }

    def render(self) -> str:
        return (
            f"{self.set_name:24} {self.cases:3} cases  "
            f"baseline {self.baseline_correct:3}  "
            f"pre-repair {self.pre_repair_correct:3}  "
            f"v3 {self.v3_correct:3}  "
            f"({self.delta_vs_pre_repair:+d})  "
            f"fixed {len(self.fixed)}  broken {len(self.broken)}  "
            f"still_wrong {len(self.still_wrong)}  "
            f"fp {self.false_positives}  fn {self.false_negatives}"
        )


@dataclass(frozen=True, slots=True)
class RegressionReport:
    records: tuple[CaseRecord, ...]
    summaries: tuple[SetSummary, ...]

    @property
    def broken(self) -> tuple[CaseRecord, ...]:
        return tuple(item for item in self.records if item.transition == BROKEN)

    @property
    def rebuilt_pre_repair_correct(self) -> int:
        return sum(1 for item in self.records if item.pre_repair_matches)

    @property
    def v3_correct(self) -> int:
        return sum(1 for item in self.records if item.case_matches)

    def summary_for(self, set_name: str) -> SetSummary:
        for item in self.summaries:
            if item.set_name == set_name:
                return item
        raise RegressionError(f"unknown set {set_name!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "sets": [item.as_dict() for item in self.summaries],
            "cases": len(self.records),
            "pre_repair_correct": self.rebuilt_pre_repair_correct,
            "v3_correct": self.v3_correct,
            "fixed_count": sum(len(item.fixed) for item in self.summaries),
            "broken_count": len(self.broken),
            "still_wrong_count": sum(len(item.still_wrong) for item in self.summaries),
            "baseline_correct": sum(item.baseline_correct for item in self.summaries),
            "baseline_provenance": dict(baseline_provenance()),
            "note": (
                "before/after are reported twice on purpose: against "
                "semantic_evaluator_v2, which is what the earlier phases meant by "
                "before, and against the pre-Phase-8.7 pipeline, which is the only "
                "comparison that can show a repair breaking a case v3 already had "
                "right."
            ),
            "records": [item.as_dict() for item in self.records],
        }

    def render(self) -> str:
        lines = [item.render() for item in self.summaries]
        lines.append("")
        lines.append(
            f"total: {len(self.records)} cases, "
            f"{self.rebuilt_pre_repair_correct} correct before -> {self.v3_correct} after"
        )
        for item in self.summaries:
            if item.fixed:
                lines.append(f"  {item.set_name} fixed      : {list(item.fixed)}")
            if item.broken:
                lines.append(f"  {item.set_name} BROKEN     : {list(item.broken)}")
        return "\n".join(lines)


def summarise(records: Sequence[CaseRecord]) -> tuple[SetSummary, ...]:
    summaries: list[SetSummary] = []
    for name in SET_NAMES:
        items = [item for item in records if item.set_name == name]
        if not items:
            continue
        summaries.append(
            SetSummary(
                set_name=name,
                cases=len(items),
                baseline_correct=sum(1 for item in items if item.baseline_matches),
                pre_repair_correct=sum(
                    1 for item in items if item.pre_repair_matches is True
                ),
                v3_correct=sum(1 for item in items if item.case_matches),
                fixed=tuple(item.case_id for item in items if item.transition == FIXED),
                broken=tuple(
                    item.case_id for item in items if item.transition == BROKEN
                ),
                still_wrong=tuple(
                    item.case_id for item in items if item.transition == STILL_WRONG
                ),
                broken_vs_baseline=tuple(
                    item.case_id
                    for item in items
                    if item.transition_vs_baseline == BROKEN
                ),
                false_positives=sum(
                    1 for item in items if item.flagged and not item.expected_flagged
                ),
                false_negatives=sum(
                    1 for item in items if item.expected_flagged and not item.flagged
                ),
            )
        )
    return tuple(summaries)


def build_regression(
    *, baseline: Mapping[str, Sequence[Mapping]] | None = None
) -> RegressionReport:
    records = run(baseline=baseline)
    return RegressionReport(records=records, summaries=summarise(records))


def write_report(
    path: str | Path | None = None,
    *,
    report: RegressionReport | None = None,
) -> Path:
    target = Path(path) if path is not None else REPORT_PATH
    active = report if report is not None else build_regression()
    target.write_text(
        json.dumps(active.as_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    report = build_regression()
    print(report.render())
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_report(report=report)}")
    return 0 if not report.broken else 1


if __name__ == "__main__":
    raise SystemExit(main())
