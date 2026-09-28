"""Phase 8.8's regression gate: Phase 8.7's suite, plus the capability benchmark.

The phase is explicit about the rule: Phase 8.7's regression must report
`broken = 0`, and if any case breaks, publication stops. So the gate is a
predicate rather than a report, and the predicate is checked in three places - the
suite, the freeze, and the phase's tests - because "we checked" is worth less than
"it cannot pass without checking".

Two things are added to Phase 8.7's five sets.

**The capability benchmark is scored as a regression set too.** Group C carries 20
cases whose labels predate this phase, and the whole 80 is scored, so a capability
that lifted its own two groups while damaging anything else fails here.

**The comparison is three-way.** `fixed`, `broken` and `unchanged`, where
`unchanged` is split into `still_right` and `still_wrong`. A case that was wrong
before and is wrong after is not the same finding as one that was always right, and
the phase asks for both to be visible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..v3_repair.regression import (
    SET_NAMES as PHASE_8_7_SETS,
    UNCHANGED,
    RegressionReport,
    build_regression,
)
from .benchmark.cases import CASES, CapabilityCase, dataset_payload
from .evaluation import predict, score
from .benchmark.cases import blind_records

REPORT_PATH = Path(__file__).resolve().parent / "regression_v3_1.json"

#: The Phase 8.8 benchmark, as a sixth set.
CAPABILITY_SET = "phase_8.8_capability"

#: The minimum each Phase 8.7 set must still score. Floors, not values: a later
#: phase may raise them, and nothing may lower them. Recorded from the Phase 8.7
#: report and re-measured here, so a regression in a set that was already wrong is
#: still visible as a lower number.
PHASE_8_7_FLOORS: Mapping[str, int] = {
    "phase_8.1": 6,
    "phase_8.3": 8,
    "phase_8.4": 16,
    "phase_8.5": 57,
    "phase_8.6_independent_v2": 96,
}


class RegressionGateError(Exception):
    """Raised when the regression gate cannot be evaluated."""


@dataclass(frozen=True, slots=True)
class SetOutcome:
    """One set's three-way comparison."""

    set_name: str
    cases: int
    fixed: tuple[str, ...]
    broken: tuple[str, ...]
    still_right: tuple[str, ...]
    still_wrong: tuple[str, ...]
    pre_repair_correct: int
    v3_correct: int

    @property
    def unchanged(self) -> tuple[str, ...]:
        return (*self.still_right, *self.still_wrong)

    def as_dict(self) -> dict[str, Any]:
        return {
            "set_name": self.set_name,
            "cases": self.cases,
            "fixed": list(self.fixed),
            "fixed_count": len(self.fixed),
            "broken": list(self.broken),
            "broken_count": len(self.broken),
            "unchanged": list(self.unchanged),
            "still_right": list(self.still_right),
            "still_wrong": list(self.still_wrong),
            "pre_repair_correct": self.pre_repair_correct,
            "v3_correct": self.v3_correct,
            "delta": self.v3_correct - self.pre_repair_correct,
        }

    def render(self) -> str:
        return (
            f"{self.set_name:26} {self.cases:3} cases  "
            f"{self.pre_repair_correct:3} -> {self.v3_correct:3} "
            f"({self.v3_correct - self.pre_repair_correct:+d})  "
            f"fixed {len(self.fixed):2}  broken {len(self.broken):2}  "
            f"unchanged {len(self.unchanged):2} "
            f"(still right {len(self.still_right)}, still wrong {len(self.still_wrong)})"
        )


@dataclass(frozen=True, slots=True)
class GateReport:
    """Phase 8.7's suite, plus the capability set, and the phase's own predicate."""

    phase_8_7: RegressionReport
    capability: SetOutcome
    floors: Mapping[str, int]

    @property
    def sets(self) -> tuple[SetOutcome, ...]:
        """Phase 8.7's five sets with `unchanged` split, plus the capability set.

        `still_right` is read from the record's own transition rather than inferred
        from the counts: a case that was right before the repair and is right now is
        `unchanged` *and* correct, and deriving it any other way could disagree with
        the report it comes from.
        """

        outcomes = []
        for name in PHASE_8_7_SETS:
            try:
                summary = self.phase_8_7.summary_for(name)
            except Exception:
                # A report that omits a set is a report that cannot be trusted, and
                # `broken` must not become empty because a set went missing. The
                # absence is recorded as a broken set rather than skipped: a gate
                # that silently ignores a missing set is worse than no gate.
                outcomes.append(
                    SetOutcome(
                        set_name=name,
                        cases=0,
                        fixed=(),
                        broken=(f"{name}:MISSING",),
                        still_right=(),
                        still_wrong=(),
                        pre_repair_correct=0,
                        v3_correct=0,
                    )
                )
                continue
            records = [
                item for item in self.phase_8_7.records if item.set_name == name
            ]
            outcomes.append(
                SetOutcome(
                    set_name=name,
                    cases=summary.cases,
                    fixed=summary.fixed,
                    broken=summary.broken,
                    still_right=tuple(
                        item.case_id
                        for item in records
                        if item.transition == UNCHANGED and item.case_matches
                    ),
                    still_wrong=summary.still_wrong,
                    pre_repair_correct=summary.pre_repair_correct,
                    v3_correct=summary.v3_correct,
                )
            )
        return (*outcomes, self.capability)

    @property
    def broken(self) -> tuple[str, ...]:
        return tuple(
            case_id
            for item in self.sets
            for case_id in item.broken
        )

    @property
    def fixed(self) -> int:
        return sum(len(item.fixed) for item in self.sets)

    @property
    def floor_violations(self) -> Mapping[str, tuple[int, int]]:
        """Sets that scored below their recorded floor."""

        problems: dict[str, tuple[int, int]] = {}
        for name, floor in self.floors.items():
            summary = self.phase_8_7.summary_for(name)
            if summary.v3_correct < floor:
                problems[name] = (summary.v3_correct, floor)
        return problems

    @property
    def passed(self) -> bool:
        return not self.broken and not self.floor_violations

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "phase_8_7": self.phase_8_7.as_dict(),
            "capability": self.capability.as_dict(),
            "sets": [item.as_dict() for item in self.sets],
            "broken_count": len(self.broken),
            "fixed_count": self.fixed,
            "floors": dict(self.floors),
            "floor_violations": {
                key: {"scored": value[0], "floor": value[1]}
                for key, value in self.floor_violations.items()
            },
            "note": (
                "The phase stops publication when a case breaks. `broken` is "
                "measured against the pre-Phase-8.7 pipeline, so a case Phase 8.7 "
                "fixed and Phase 8.8 damaged is caught here rather than hidden "
                "behind an unchanged total."
            ),
        }

    def render(self) -> str:
        lines = [item.render() for item in self.sets]
        lines.append("")
        lines.append(
            f"status        : {self.status}   broken {len(self.broken)}   "
            f"fixed {self.fixed}"
        )
        if self.broken:
            lines.append(f"BROKEN        : {list(self.broken)}")
        for name, (scored, floor) in sorted(self.floor_violations.items()):
            lines.append(f"BELOW FLOOR   : {name} scored {scored}, floor {floor}")
        return "\n".join(lines)


def _capability_outcome(
    cases: Sequence[CapabilityCase] | None = None,
) -> SetOutcome:
    """The Phase 8.8 benchmark, compared against the pre-Phase-8.7 pipeline.

    The comparison uses the semantic baseline as the `pre_repair` reference, which
    is the same reference Phase 8.7 used for the sets it did not have a recorded
    v3 measurement for. It is stated rather than implied because it is the weaker
    of the two available references.
    """

    active = tuple(cases) if cases is not None else CASES
    metrics = score(predict(blind_records(active)), active)
    fixed: list[str] = []
    broken: list[str] = []
    still_right: list[str] = []
    still_wrong: list[str] = []
    for item in metrics.outcomes:
        before = item.baseline_correct
        after = item.correct
        if before and after:
            still_right.append(item.case_id)
        elif not before and after:
            fixed.append(item.case_id)
        elif before and not after:
            broken.append(item.case_id)
        else:
            still_wrong.append(item.case_id)
    return SetOutcome(
        set_name=CAPABILITY_SET,
        cases=len(active),
        fixed=tuple(fixed),
        broken=tuple(broken),
        still_right=tuple(still_right),
        still_wrong=tuple(still_wrong),
        pre_repair_correct=sum(
            1 for item in metrics.outcomes if item.baseline_correct
        ),
        v3_correct=metrics.decision.correct,
    )


def build_gate(
    *,
    report: RegressionReport | None = None,
    cases: Sequence[CapabilityCase] | None = None,
    floors: Mapping[str, int] | None = None,
) -> GateReport:
    active_report = report if report is not None else build_regression()
    # Phase 8.7's own summary carries `fixed` and `still_wrong`, and `still_right` is
    # what is left: every case that was right before the repair and is right now. It
    # is derived from the records rather than re-measured, so the two reports cannot
    # disagree.
    active_floors = dict(floors if floors is not None else PHASE_8_7_FLOORS)
    return GateReport(
        phase_8_7=active_report,
        capability=_capability_outcome(cases),
        floors=active_floors,
    )


def dataset_hash(cases: Sequence[CapabilityCase] | None = None) -> str:
    """SHA-256 over the complete case records, for the freeze."""

    import hashlib

    active = tuple(cases) if cases is not None else CASES
    canonical = json.dumps(
        [case.as_dict() for case in active],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def write_report(
    path: str | Path | None = None, *, gate: GateReport | None = None
) -> Path:
    target = Path(path) if path is not None else REPORT_PATH
    active = gate if gate is not None else build_gate()
    payload = {
        **active.as_dict(),
        "benchmark": dataset_payload()["benchmark"],
        "dataset_hash": dataset_hash(),
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    gate = build_gate()
    print(gate.render())
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_report(gate=gate)}")
    return 0 if gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
