"""Phase 8.9 regression: the historical sets, against a frozen evaluator.

The phase requires Phase 8.1, 8.3, 8.4, 8.6 and 8.8 to replay with `broken = 0`. The
evaluator was frozen before the independent dataset was generated and was not
modified while it was measured, so the expected result is that every set scores
exactly what it scored in Phase 8.8. That is worth checking rather than assuming: a
replay that is identical because nothing ran is not the same as one that is identical
because nothing changed.

`broken` is measured against the pre-Phase-8.7 pipeline, which is the strictest
reference available: it catches a case Phase 8.7 fixed and a later phase damaged.

The gate also re-runs `freeze.guard()`. A regression that passed against a moved
pipeline would be a regression about a different program.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..v3_1.regression import (
    CAPABILITY_SET,
    PHASE_8_7_FLOORS,
    GateReport as Phase88Gate,
    build_gate as build_phase_88_gate,
)
from ..v3_validation.evaluation import predict as predict_8_6
from ..v3_validation.evaluation import score as score_8_6
from ..v3_validation.cases import blind_records as blind_8_6
from .freeze import guard

REGRESSION_PATH = Path(__file__).resolve().parent / "regression_v3_2.json"

#: The sets the phase names, and the floor each must reach. The floors are Phase
#: 8.7's measured results, so a set that was already wrong cannot improve by being
#: measured against itself.
REQUIRED_SETS: tuple[str, ...] = (
    "phase_8.1",
    "phase_8.3",
    "phase_8.4",
    "phase_8.6_independent_v2",
    CAPABILITY_SET,
)


class RegressionError(Exception):
    """Raised when the regression cannot run."""


@dataclass(frozen=True, slots=True)
class SetResult:
    set_name: str
    cases: int
    fixed: tuple[str, ...]
    broken: tuple[str, ...]
    still_right: tuple[str, ...]
    still_wrong: tuple[str, ...]
    correct: int
    floor: int

    @property
    def meets_floor(self) -> bool:
        return self.correct >= self.floor

    def as_dict(self) -> dict[str, Any]:
        return {
            "set_name": self.set_name,
            "cases": self.cases,
            "fixed": list(self.fixed),
            "broken": list(self.broken),
            "still_right": len(self.still_right),
            "still_wrong": list(self.still_wrong),
            "correct": self.correct,
            "floor": self.floor,
            "meets_floor": self.meets_floor,
        }

    def render(self) -> str:
        mark = "ok" if self.meets_floor else "BELOW FLOOR"
        return (
            f"{self.set_name:24} {self.cases:3} cases  correct {self.correct:3} "
            f"(floor {self.floor:3})  fixed {len(self.fixed):2}  "
            f"broken {len(self.broken):2}  still wrong {len(self.still_wrong):2}  {mark}"
        )


@dataclass(frozen=True, slots=True)
class RegressionGate:
    phase_8_8: Phase88Gate
    sets: tuple[SetResult, ...]
    phase_8_6_v1: Mapping[str, Any]
    freeze_verified: bool
    freeze_note: str

    @property
    def broken(self) -> tuple[str, ...]:
        return tuple(
            case_id for item in self.sets for case_id in item.broken
        )

    @property
    def floor_violations(self) -> tuple[str, ...]:
        return tuple(item.set_name for item in self.sets if not item.meets_floor)

    @property
    def passed(self) -> bool:
        return not self.broken and not self.floor_violations and self.freeze_verified

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "broken_count": len(self.broken),
            "broken": list(self.broken),
            "floor_violations": list(self.floor_violations),
            "sets": [item.as_dict() for item in self.sets],
            "phase_8_6_v1": dict(self.phase_8_6_v1),
            "freeze_verified": self.freeze_verified,
            "freeze_note": self.freeze_note,
            "evaluator_modified": False,
            "note": (
                "The evaluator was frozen before the independent dataset was built "
                "and was not modified while it was measured, so the historical sets "
                "are expected to score exactly what Phase 8.8 measured. broken is "
                "counted against the pre-Phase-8.7 pipeline."
            ),
        }

    def render(self) -> str:
        lines = [item.render() for item in self.sets]
        lines.append("")
        lines.append(
            "phase 8.6 independent_v1  correct {c}/{n}  precision {p}  recall {r}".format(
                c=self.phase_8_6_v1.get("correct"),
                n=self.phase_8_6_v1.get("cases"),
                p=self.phase_8_6_v1.get("precision"),
                r=self.phase_8_6_v1.get("recall"),
            )
        )
        lines.append("")
        lines.append(
            f"freeze : {'verified' if self.freeze_verified else 'MOVED'}  "
            f"{self.freeze_note}"
        )
        lines.append(
            f"status : {self.status}   broken {len(self.broken)}   "
            f"floor violations {len(self.floor_violations)}"
        )
        if self.broken:
            lines.append(f"BROKEN : {list(self.broken)}")
        if self.floor_violations:
            lines.append(f"BELOW FLOOR : {list(self.floor_violations)}")
        return "\n".join(lines)


def build() -> RegressionGate:
    """Run every required set against the frozen evaluator."""

    phase_8_8 = build_phase_88_gate()

    sets: list[SetResult] = []
    for item in phase_8_8.sets:
        if item.set_name not in REQUIRED_SETS:
            continue
        floor = PHASE_8_7_FLOORS.get(item.set_name, 0)
        sets.append(
            SetResult(
                set_name=item.set_name,
                cases=item.cases,
                fixed=item.fixed,
                broken=item.broken,
                still_right=item.still_right,
                still_wrong=item.still_wrong,
                correct=item.v3_correct,
                floor=floor,
            )
        )

    metrics = score_8_6(predict_8_6(blind_8_6()))
    decision = metrics.decision
    summary = {
        "cases": len(metrics.outcomes),
        "correct": decision.correct,
        "precision": decision.precision,
        "recall": decision.recall,
        "false_positives": decision.counts["fp"],
        "false_negatives": decision.counts["fn"],
    }

    verified = True
    note = "evaluator frozen and unchanged"
    try:
        guard()
    except Exception as error:  # noqa: BLE001 - the message is the finding
        verified = False
        note = str(error)

    return RegressionGate(
        phase_8_8=phase_8_8,
        sets=tuple(sets),
        phase_8_6_v1=summary,
        freeze_verified=verified,
        freeze_note=note,
    )


def write_report(
    path: str | Path | None = None, *, gate: RegressionGate | None = None
) -> Path:
    target = Path(path) if path is not None else REGRESSION_PATH
    active = gate if gate is not None else build()
    target.write_text(
        json.dumps(active.as_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    import sys

    gate = build()
    print(gate.render())
    if "--write" in sys.argv:
        print()
        print(f"wrote {write_report(gate=gate)}")
    return 0 if gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
